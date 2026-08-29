"""Weighted evidence fusion.

Every stage produces a score in [0, 1] or ``None``. Fusion turns those into one
confidence number, and the design constraints are:

* A source that produced no evidence must not drag the score down. It is
  dropped from the weighted mean, not counted as zero.
* But a record that produced *almost no* evidence must not be able to reach a
  very high confidence either, or a single lucky attribute match on an empty
  record outranks a thoroughly corroborated one. So the mean is shrunk toward a
  neutral prior in proportion to how little of the total weight was covered.
* Facial evidence is capped by image quality. A 0.97 cosine similarity computed
  from a blurred 80×80 crop is not 0.97 worth of evidence.
* Weights decay with elapsed time (see temporal.py), so the mix rebalances
  itself on long-duration cases toward the attributes that survive.

The result carries its own explanation: per-source score, effective weight and
contribution, so the UI can show why a number came out the way it did rather
than asserting it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Base weights before temporal decay and quality capping.
BASE_WEIGHTS: dict[str, float] = {
    "face": 0.34,
    "marks": 0.26,
    "demographic": 0.18,
    "time": 0.13,
    "location": 0.09,
}

# With zero coverage the score collapses to this; with full coverage it is the
# weighted mean untouched.
NEUTRAL_PRIOR = 0.0
MIN_SHRINK = 0.55


@dataclass
class SourceScore:
    name: str
    score: float | None
    weight: float
    note: str | None = None

    @property
    def available(self) -> bool:
        return self.score is not None


@dataclass
class FusionResult:
    confidence: float
    coverage: float
    sources: dict[str, dict] = field(default_factory=dict)

    def as_percentages(self) -> dict[str, int]:
        return {
            name: round((d["score"] or 0.0) * 100)
            for name, d in self.sources.items()
            if d["score"] is not None
        }


def apply_quality_cap(face_score: float | None, quality_a: float | None, quality_b: float | None) -> tuple[float | None, float]:
    """Scale facial similarity by the *lower* of the two image qualities.

    The weaker image governs: a pristine probe compared against a poor candidate
    photograph yields evidence only as strong as the poor one supports. Returns
    the adjusted score and the limiting quality actually applied.
    """
    if face_score is None:
        return None, 1.0
    qualities = [q for q in (quality_a, quality_b) if q is not None]
    limiting = min(qualities) if qualities else 0.5
    limiting = max(0.0, min(1.0, limiting))
    return face_score * limiting, limiting


def fuse(sources: list[SourceScore]) -> FusionResult:
    total_weight = sum(s.weight for s in sources if s.weight > 0)
    if total_weight <= 0:
        return FusionResult(0.0, 0.0, {})

    available = [s for s in sources if s.available and s.weight > 0]
    covered_weight = sum(s.weight for s in available)
    coverage = covered_weight / total_weight if total_weight else 0.0

    if covered_weight <= 0:
        weighted_mean = NEUTRAL_PRIOR
    else:
        weighted_mean = sum(s.score * s.weight for s in available) / covered_weight

    # Shrink toward the prior when little of the evidence budget was covered.
    shrink = MIN_SHRINK + (1.0 - MIN_SHRINK) * coverage
    confidence = NEUTRAL_PRIOR + (weighted_mean - NEUTRAL_PRIOR) * shrink

    detail = {
        s.name: {
            "score": s.score,
            "weight": round(s.weight, 4),
            "share": round(s.weight / total_weight, 4),
            "contribution": round((s.score or 0.0) * s.weight / covered_weight, 4) if covered_weight else 0.0,
            "available": s.available,
            "note": s.note,
        }
        for s in sources
    }

    return FusionResult(
        confidence=max(0.0, min(1.0, confidence)),
        coverage=coverage,
        sources=detail,
    )


def effective_weights(
    temporal_ctx,
    quality_limit: float = 1.0,
    face_reliability: float = 1.0,
) -> dict[str, float]:
    """Base weights adjusted for elapsed time, image quality and backend trust.

    ``face_reliability`` is the measured discriminative power of whichever face
    backend is actually loaded (see ``services.face.CALIBRATION``). Running on a
    fallback descriptor must not let facial similarity speak with the authority
    of a trained ArcFace model, so the weight — not just the score — shrinks.
    """
    weights = dict(BASE_WEIGHTS)
    for name in weights:
        weights[name] *= temporal_ctx.weight_for(name if name != "demographic" else "age")
    # A face we can barely see should not hold a third of the budget.
    weights["face"] *= max(0.15, quality_limit) * max(0.0, min(1.0, face_reliability))
    return weights
