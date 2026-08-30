"""Semantic comparison of identification marks.

Two officers rarely describe the same mark the same way:

    "star tattoo on right forearm"
    "tattoo resembling a five-pointed star on the right arm"

String equality scores those at zero, discarding the most discriminative
evidence in the record. So descriptions are embedded and compared by cosine
similarity, via ``NlpClient`` — this module never imports Gemini.

**Where the boundary sits.** The client supplies a similarity number for a pair
of strings. Everything after that — how marks are paired up, how structured
fields are weighted against the text, and how a side conflict is penalised — is
deterministic logic that lives here and is unit-tested. The language model
contributes evidence; it does not score candidates.
"""
from __future__ import annotations

import logging

from app.services.nlp import get_client, lexical_similarity, normalise_tokens  # noqa: F401

log = logging.getLogger(__name__)

# How much of a mark's score comes from each source. Free text dominates because
# it carries detail the structured fields cannot ("resembling a five-pointed
# star"), but structured agreement anchors it.
TEXT_WEIGHT = 0.55
KIND_WEIGHT = 0.15
LOCATION_WEIGHT = 0.15
SIDE_WEIGHT = 0.10
SIZE_WEIGHT = 0.05

# A left-side mark against a right-side mark is evidence *against*, not a
# missing field, so it is subtracted after weighting rather than merely
# scoring zero.
SIDE_CONFLICT_PENALTY = 0.25


def backend_name() -> str:
    client = get_client()
    return client.provider.embedding_model_name() if client.provider.available() else "lexical-domain-v1"


def embed(text: str) -> tuple[list[float] | None, str]:
    """Embed a description at write time. Returns (vector, backend label)."""
    result = get_client().generate_embedding(text)
    return result.vector, (result.model if result.vector else backend_name())


def text_similarity(a: str, b: str,
                    vec_a: list[float] | None = None,
                    vec_b: list[float] | None = None) -> float:
    """Similarity in [0, 1] between two free-text descriptions."""
    return get_client().semantic_similarity(a, b, vector_a=vec_a, vector_b=vec_b).score


def _size_similarity(a_cm: float | None, b_cm: float | None) -> float | None:
    if not a_cm or not b_cm or a_cm <= 0 or b_cm <= 0:
        return None
    return float((min(a_cm, b_cm) / max(a_cm, b_cm)) ** 0.6)


def _pair_score(probe_mark, candidate_mark) -> dict:
    """Score one probe mark against one candidate mark."""
    client = get_client()
    similarity = client.semantic_similarity(
        probe_mark.description or "", candidate_mark.description or "",
        vector_a=probe_mark.embedding, vector_b=candidate_mark.embedding,
    )

    parts: list[tuple[float, float]] = [(similarity.score, TEXT_WEIGHT)]

    if probe_mark.kind and candidate_mark.kind:
        agree = probe_mark.kind.strip().lower() == candidate_mark.kind.strip().lower()
        parts.append((1.0 if agree else 0.15, KIND_WEIGHT))

    if probe_mark.body_location and candidate_mark.body_location:
        agree = probe_mark.body_location.strip().lower() == candidate_mark.body_location.strip().lower()
        parts.append((1.0 if agree else 0.10, LOCATION_WEIGHT))

    penalty = 0.0
    recorded = {"not recorded", "unknown", ""}
    p_side = (probe_mark.side or "").strip().lower()
    c_side = (candidate_mark.side or "").strip().lower()
    if p_side not in recorded and c_side not in recorded:
        if p_side == c_side:
            parts.append((1.0, SIDE_WEIGHT))
        else:
            parts.append((0.0, SIDE_WEIGHT))
            penalty = SIDE_CONFLICT_PENALTY

    size = _size_similarity(probe_mark.size_cm, candidate_mark.size_cm)
    if size is not None:
        parts.append((size, SIZE_WEIGHT))

    total_weight = sum(w for _, w in parts)
    score = sum(s * w for s, w in parts) / total_weight if total_weight else 0.0

    return {
        "probe_mark": probe_mark.description,
        "candidate_mark": candidate_mark.description,
        "score": round(max(0.0, score - penalty), 4),
        "text_similarity": round(similarity.score, 4),
        "method": similarity.method,
        "side_conflict": penalty > 0,
    }


def compare_marks(probe_marks: list, candidate_marks: list) -> tuple[float | None, list[dict]]:
    """Best-match pairing between two sets of identification marks.

    Each probe mark is scored against its best candidate counterpart, and the
    overall score is the mean of those bests — so a probe carrying three
    recorded marks needs broad agreement rather than one lucky hit.

    Returns ``(None, [])`` when either side has no marks: absent marks are no
    evidence, not evidence against.
    """
    if not probe_marks or not candidate_marks:
        return None, []

    pairings: list[dict] = []
    for probe_mark in probe_marks:
        best: dict | None = None
        for candidate_mark in candidate_marks:
            try:
                scored = _pair_score(probe_mark, candidate_mark)
            except Exception as exc:                          # noqa: BLE001
                # A comparison failing must not abort the whole match run.
                log.warning("Mark comparison failed (%s) — skipping this pair", exc)
                continue
            if best is None or scored["score"] > best["score"]:
                best = scored
        if best:
            pairings.append(best)

    if not pairings:
        return None, []

    overall = sum(p["score"] for p in pairings) / len(pairings)
    return float(max(0.0, min(1.0, overall))), pairings
