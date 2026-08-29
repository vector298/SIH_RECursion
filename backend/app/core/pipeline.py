"""The seven-stage matching pipeline.

    01 Data ingestion       normalise the probe, resolve uncertainty modes
    02 Hard search          indexed SQL reduction (hard_search.py)
    03 Attribute filtering  interval comparison with temporal projection
    04 Semantic comparison  identification-mark embeddings (semantic.py)
    05 Facial comparison    ArcFace embeddings (services/face.py)
    06 Quality adjustment   image quality caps facial evidence (quality.py)
    07 Confidence ranking   weighted fusion (fusion.py)

Stage timings reported to the UI are measured, not scripted, and the funnel
counts are the real sizes of the surviving candidate set at each step.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.core import geo, hard_search, semantic, temporal
from app.core.arcface import cosine_similarity, similarity_to_score
from app.core.fusion import SourceScore, apply_quality_cap, effective_weights, fuse
from app.core.uncertainty import Interval, Mode, compare, compare_categorical, overlaps
from app.db.models import Case
from app.services import face as face_service
from app.services import gemini

log = logging.getLogger(__name__)

# Gap at which a disjoint pair of intervals decays to 1/e. These are tuned so a
# near-miss keeps meaningful credit while a real separation loses it: with a
# 2.5-year scale, projected ages 3 years apart score 0.30 and 6 years apart 0.09.
AGE_DECAY_YEARS = 2.5
HEIGHT_DECAY_CM = 7.0

# An age recorded as a *range* is an estimate — someone looked at a person and
# guessed. Published work on apparent-age estimation puts human error around
# ±4 years for adults even for trained observers, so a recorded 19–24 is really
# "somewhere near 19–24". Comparing the stated bands directly makes two honest
# estimates of the same person look like a mismatch. Both sides are therefore
# widened by an estimator-error term before comparison. Exact ages (from a
# document or a relative) are not widened — they are not estimates.
AGE_ESTIMATE_TOLERANCE_YEARS = 1.6
HEIGHT_ESTIMATE_TOLERANCE_CM = 3.0


@dataclass
class Stage:
    id: str
    label: str
    duration_ms: float = 0.0
    remaining: int | None = None
    removed: int | None = None
    detail: str | None = None
    substeps: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "label": self.label,
            "duration_ms": round(self.duration_ms, 2),
            "remaining": self.remaining, "removed": self.removed,
            "detail": self.detail, "substeps": self.substeps,
        }


class _Timer:
    def __init__(self, stage: Stage) -> None:
        self.stage = stage

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self.stage

    def __exit__(self, *_exc):
        self.stage.duration_ms = (time.perf_counter() - self._t0) * 1000.0
        return False


# ---------------------------------------------------------------------------
def _age_interval(case: Case) -> Interval:
    return Interval.from_record(case.age_mode, case.age_lo, case.age_hi)


def _height_interval(case: Case) -> Interval:
    return Interval.from_record(case.height_mode, case.height_lo, case.height_hi)


def _with_estimate_tolerance(projected: Interval, original: Interval, tolerance: float) -> Interval:
    """Widen an interval that was recorded as an estimate, not a measurement."""
    if not projected.known or original.mode is not Mode.RANGE:
        return projected
    return projected.widened(tolerance)


def _best_face(case: Case):
    """Highest-quality image that actually carries an embedding."""
    usable = [i for i in case.images if i.embedding]
    if not usable:
        return None
    return max(usable, key=lambda i: (i.quality_score or 0.0))


def _demographic_score(probe: Case, cand: Case, target: date) -> tuple[float | None, dict]:
    """Age, height, build and blood type, all interval- and unknown-aware."""
    probe_age = temporal.project_age(_age_interval(probe), probe.age_observed_on, target)
    cand_age = temporal.project_age(_age_interval(cand), cand.age_observed_on, target)

    parts: list[tuple[float, float]] = []

    # Compare the tolerance-widened intervals, and report those same intervals —
    # quoting the raw projection next to a score computed from the widened one
    # produces explanations that contradict their own numbers.
    probe_cmp = _with_estimate_tolerance(probe_age, _age_interval(probe), AGE_ESTIMATE_TOLERANCE_YEARS)
    cand_cmp = _with_estimate_tolerance(cand_age, _age_interval(cand), AGE_ESTIMATE_TOLERANCE_YEARS)

    detail: dict = {
        "probe_age_projected": str(probe_age),
        "candidate_age_projected": str(cand_age),
        "probe_age_compared": str(probe_cmp),
        "candidate_age_compared": str(cand_cmp),
        "age_intervals_overlap": bool(overlaps(probe_cmp, cand_cmp)),
    }

    age = compare(probe_cmp, cand_cmp, decay=AGE_DECAY_YEARS)
    detail["age"] = age
    if age is not None:
        parts.append((age, 0.45))

    probe_h, cand_h = _height_interval(probe), _height_interval(cand)
    height = compare(
        _with_estimate_tolerance(probe_h, probe_h, HEIGHT_ESTIMATE_TOLERANCE_CM),
        _with_estimate_tolerance(cand_h, cand_h, HEIGHT_ESTIMATE_TOLERANCE_CM),
        decay=HEIGHT_DECAY_CM,
    )
    detail["height"] = height
    if height is not None:
        parts.append((height, 0.25))

    build = compare_categorical(probe.build, cand.build, mismatch=0.35)
    detail["build"] = build
    if build is not None:
        parts.append((build, 0.15))

    blood = compare_categorical(probe.blood_type, cand.blood_type, mismatch=0.05)
    detail["blood_type"] = blood
    if blood is not None:
        parts.append((blood, 0.15))

    if not parts:
        return None, detail

    total = sum(w for _, w in parts)
    return sum(s * w for s, w in parts) / total, detail


def _build_narrative(probe: Case, cand: Case, scores: dict, detail: dict) -> tuple[list[str], list[str]]:
    """Deterministic evidence statements, optionally rephrased by Gemini."""
    evidence: list[str] = []
    concerns: list[str] = []

    demo = detail.get("demographic", {})
    if demo.get("age") is not None:
        span = f"{demo.get('probe_age_compared')} vs {demo.get('candidate_age_compared')} years"
        overlapping = demo.get("age_intervals_overlap")
        if overlapping and demo["age"] > 0.6:
            evidence.append(f"Projected age intervals overlap substantially ({span}).")
        elif overlapping:
            evidence.append(f"Projected age intervals overlap, though only partially ({span}).")
        elif demo["age"] > 0.5:
            evidence.append(
                f"Projected age intervals do not overlap but sit adjacent ({span}), "
                "within ordinary estimation error."
            )
        else:
            concerns.append(f"Projected age intervals are separated ({span}).")

    if scores.get("location") is not None:
        km = detail.get("distance_km")
        if scores["location"] > 0.5:
            evidence.append(
                f"Last-known locations are geographically compatible"
                + (f" ({km:.0f} km apart, within plausible travel for the elapsed time)." if km else ".")
            )
        else:
            concerns.append(
                f"Geographic separation is large for the elapsed interval"
                + (f" ({km:.0f} km)." if km else ".")
            )

    pairings = detail.get("mark_pairings") or []
    strong = [p for p in pairings if p["score"] > 0.7]
    if strong:
        evidence.append(
            f"{len(strong)} identification-mark description(s) are semantically close — "
            f"e.g. “{strong[0]['probe_mark']}” vs “{strong[0]['candidate_mark']}” "
            f"(similarity {strong[0]['text_similarity']:.2f})."
        )
    conflicts = [p for p in pairings if p.get("side_conflict")]
    if conflicts:
        concerns.append("An identification mark is recorded on opposite sides of the body on the two records.")

    if scores.get("face") is not None:
        limit = detail.get("quality_limit")
        if scores["face"] > 0.7:
            evidence.append(f"Facial similarity is strong and the imagery supports it (limiting quality {limit:.2f}).")
        elif limit is not None and limit < 0.7:
            concerns.append(
                f"Facial evidence is discounted — the weaker of the two images scores {limit:.2f} on quality."
            )
    else:
        concerns.append("No comparable facial imagery on at least one record; facial evidence is unavailable.")

    unknown_fields = [
        name for name, value in (
            ("blood type", demo.get("blood_type")),
            ("height", demo.get("height")),
            ("build", demo.get("build")),
        ) if value is None
    ]
    if unknown_fields:
        concerns.append(
            f"Unknown on one or both records: {', '.join(unknown_fields)} — "
            "contributes no evidence either way."
        )

    if gemini.available():
        phrased = gemini.narrate_evidence({
            "scores": scores, "detail": {k: v for k, v in detail.items() if k != "mark_pairings"},
            "deterministic_evidence": evidence, "deterministic_concerns": concerns,
        })
        if phrased:
            evidence = phrased

    return evidence, concerns


# ---------------------------------------------------------------------------
def run_match(db: Session, probe: Case, *, limit: int | None = None) -> dict:
    """Execute the full pipeline for one probe case."""
    limit = limit or settings.max_candidates_returned
    started = time.perf_counter()
    target_date = date.today()
    stages: list[Stage] = []

    # --- 01 ingestion ------------------------------------------------------
    ingest = Stage("ingest", "Data Ingestion")
    with _Timer(ingest):
        probe_age = _age_interval(probe)
        probe_marks = list(probe.marks)
        probe_face = _best_face(probe)
        ingest.detail = (
            f"age={probe_age}, height={_height_interval(probe)}, "
            f"sex={probe.sex or 'unknown'}, marks={len(probe_marks)}, "
            f"face_embedding={'yes' if probe_face else 'no'}"
        )
    stages.append(ingest)

    # --- 02 hard search ----------------------------------------------------
    hard = Stage("hard", "Hard Search")
    with _Timer(hard):
        candidates, funnel = hard_search.run(db, probe)
        hard.substeps = [f.__dict__ for f in funnel]
        hard.remaining = len(candidates)
        hard.removed = (funnel[0].remaining - len(candidates)) if funnel else 0
        hard.detail = "Indexed SQL predicates; NULL never excludes a record."
    corpus_size = funnel[0].remaining if funnel else 0
    stages.append(hard)

    # --- 03 attribute filtering -------------------------------------------
    attr = Stage("attr", "Attribute Filtering")
    rows: list[dict] = []
    with _Timer(attr):
        for cand in candidates:
            ctx = temporal.build_context(
                probe.last_seen_at, cand.last_seen_at,
                probe_age.midpoint if probe_age.known else None,
            )
            demo_score, demo_detail = _demographic_score(probe, cand, target_date)
            loc_score, distance = geo.location_compatibility(
                probe.lat, probe.lon, cand.lat, cand.lon, ctx.elapsed_years
            )
            rows.append({
                "case": cand, "ctx": ctx,
                "scores": {"demographic": demo_score, "time": ctx.plausibility, "location": loc_score},
                "detail": {"demographic": demo_detail, "distance_km": distance,
                           "elapsed_years": round(ctx.elapsed_years, 2)},
            })
        # Only drop records that are affirmatively incompatible on demographics.
        before = len(rows)
        rows = [r for r in rows if (r["scores"]["demographic"] is None or r["scores"]["demographic"] > 0.02)]
        attr.remaining, attr.removed = len(rows), before - len(rows)
        attr.detail = "Interval overlap with time-projected ages; unknown attributes stay neutral."
    stages.append(attr)

    # --- 04 semantic comparison -------------------------------------------
    sem = Stage("semantic", "Semantic Comparison")
    with _Timer(sem):
        for r in rows:
            score, pairings = semantic.compare_marks(probe_marks, list(r["case"].marks))
            r["scores"]["marks"] = score
            r["detail"]["mark_pairings"] = pairings
        sem.remaining = len(rows)
        sem.removed = 0
        sem.detail = f"Identification-mark descriptions compared via {semantic.backend_name()}."
    stages.append(sem)

    # --- 05 facial comparison ---------------------------------------------
    facial = Stage("face", "Facial Comparison")
    comparisons = 0
    with _Timer(facial):
        for r in rows:
            cand_face = _best_face(r["case"])
            if probe_face and cand_face and probe_face.embedding_model == cand_face.embedding_model:
                calib = face_service.calibration(probe_face.embedding_model)
                cos = cosine_similarity(probe_face.embedding, cand_face.embedding)
                r["scores"]["face_raw"] = similarity_to_score(cos, threshold=calib["threshold"])
                r["detail"]["face_cosine"] = round(cos, 4)
                r["detail"]["face_model"] = probe_face.embedding_model
                r["detail"]["face_reliability"] = calib["reliability"]
                r["detail"]["probe_quality"] = probe_face.quality_score
                r["detail"]["candidate_quality"] = cand_face.quality_score
                comparisons += 1
            else:
                r["scores"]["face_raw"] = None
                if probe_face and cand_face:
                    r["detail"]["face_note"] = "embedding models differ; comparison skipped"
        facial.remaining = len(rows)
        facial.detail = (
            f"{comparisons} embedding comparison(s) using {face_service.backend_name()}"
            f" — instead of {corpus_size} across the full index."
        )
    stages.append(facial)

    # --- 06 quality adjustment --------------------------------------------
    qual = Stage("quality", "Quality Adjustment")
    with _Timer(qual):
        for r in rows:
            adjusted, quality_limit = apply_quality_cap(
                r["scores"].get("face_raw"),
                r["detail"].get("probe_quality"),
                r["detail"].get("candidate_quality"),
            )
            r["scores"]["face"] = adjusted
            r["detail"]["quality_limit"] = quality_limit
        qual.remaining = len(rows)
        qual.detail = "Facial similarity scaled by the lower of the two image-quality scores."
    stages.append(qual)

    # --- 07 confidence ranking --------------------------------------------
    rank = Stage("rank", "Confidence Ranking")
    with _Timer(rank):
        results = []
        for r in rows:
            weights = effective_weights(
                r["ctx"],
                r["detail"].get("quality_limit", 1.0),
                r["detail"].get("face_reliability", 1.0),
            )
            fused = fuse([
                SourceScore("face", r["scores"].get("face"), weights["face"]),
                SourceScore("marks", r["scores"].get("marks"), weights["marks"]),
                SourceScore("demographic", r["scores"].get("demographic"), weights["demographic"]),
                SourceScore("time", r["scores"].get("time"), weights["time"]),
                SourceScore("location", r["scores"].get("location"), weights["location"]),
            ])
            results.append({"row": r, "fused": fused, "weights": weights})

        results.sort(key=lambda x: x["fused"].confidence, reverse=True)
        results = [x for x in results if x["fused"].confidence >= settings.min_confidence_returned][:limit]
        rank.remaining = len(results)
        rank.detail = "Weighted evidence fusion, shrunk toward neutral by evidence coverage."
    stages.append(rank)

    # --- assemble ----------------------------------------------------------
    candidates_out = []
    for position, item in enumerate(results, start=1):
        r, fused = item["row"], item["fused"]
        scores_pct = {
            "face": r["scores"].get("face"),
            "marks": r["scores"].get("marks"),
            "demographic": r["scores"].get("demographic"),
            "time": r["scores"].get("time"),
            "location": r["scores"].get("location"),
            "quality": r["detail"].get("quality_limit"),
        }
        evidence, concerns = _build_narrative(probe, r["case"], scores_pct, r["detail"])
        candidates_out.append({
            "rank": position,
            "case": r["case"],
            "confidence": fused.confidence,
            "coverage": fused.coverage,
            "scores": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in scores_pct.items()},
            "sources": fused.sources,
            "detail": r["detail"],
            "evidence": evidence,
            "concerns": concerns,
        })

    return {
        "corpus_size": corpus_size,
        "stages": [s.as_dict() for s in stages],
        "candidates": candidates_out,
        "duration_ms": (time.perf_counter() - started) * 1000.0,
        "backends": {
            "face": face_service.backend_name(),
            "semantic": semantic.backend_name(),
            "language": gemini.backend_name(),
            "arcface_real": face_service.is_real_arcface(),
            "face_calibration": face_service.calibration(),
            "face_notice": (
                None if face_service.is_real_arcface() else
                "Facial evidence is running on a local image descriptor, not face "
                "recognition. Its weight is reduced accordingly. Install insightface "
                "and the ArcFace model pack for identity-grade comparison."
            ),
        },
    }
