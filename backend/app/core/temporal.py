"""Time-aware reasoning.

Two separate ideas live here, and conflating them is the usual bug:

1. **Age projection.** An age recorded in 2019 is not the subject's age today.
   Elapsed time is added deterministically. What *is* uncertain is the original
   estimate, and that uncertainty grows for subjects who were children, because
   apparent-age estimates drift as a face matures. So the interval is shifted by
   the exact elapsed years and widened by an estimate-drift term.

2. **Attribute weight decay.** Some attributes stop being evidence as time
   passes. A scar is still a scar after seven years; a child's height is not.
   Each attribute gets a half-life, and minors decay faster on the physical
   attributes because they are still growing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime

from app.core.uncertainty import Interval

DAYS_PER_YEAR = 365.2425

# Half-life in years: the elapsed time after which an attribute carries half the
# weight it had at intake. None means the attribute does not decay.
HALF_LIFE_YEARS: dict[str, float | None] = {
    "marks": None,        # scars, tattoos and birthmarks are stable
    "face": 14.0,         # bone structure persists; appearance drifts
    "age": None,          # projected forward exactly, so it does not decay
    "height": 6.0,        # dynamic, and dominated by growth in minors
    "build": 4.0,         # highly variable
    "appearance": 1.5,    # hair, weight, grooming
    "clothing": 0.25,     # effectively worthless within months
    "location": 3.0,      # people move
}

# Minors are still growing, so the physical attributes decay faster for them.
MINOR_DECAY_MULTIPLIER: dict[str, float] = {
    "face": 2.6,
    "height": 3.2,
    "build": 2.4,
    "appearance": 1.6,
}


def _as_date(value: date | datetime | None) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def years_between(start: date | datetime | None, end: date | datetime | None) -> float:
    a, b = _as_date(start), _as_date(end)
    if a is None or b is None:
        return 0.0
    return (b - a).days / DAYS_PER_YEAR


def estimate_drift(age_at_observation: float | None, elapsed_years: float) -> float:
    """Extra half-width, in years, to allow for drift in the original estimate.

    An adult described as "about 40" is still plausibly "about 47" seven years
    later with the same confidence. A child described as "about 8" could
    reasonably present as 14 to 16 at the same remove, so the interval has to
    open up or the true match gets filtered out on demographics.
    """
    if elapsed_years <= 0:
        return 0.0
    if age_at_observation is None:
        return 0.35 * elapsed_years
    if age_at_observation < 18:
        return 0.42 * elapsed_years          # growth + rapid facial change
    if age_at_observation < 30:
        return 0.18 * elapsed_years
    return 0.10 * elapsed_years


def project_age(
    age: Interval,
    observed_on: date | datetime | None,
    target: date | datetime | None = None,
) -> Interval:
    """Carry an age interval forward to ``target`` (default: today)."""
    if not age.known or observed_on is None:
        return age

    target = target or date.today()
    elapsed = years_between(observed_on, target)
    if elapsed <= 0:
        return age

    drift = estimate_drift(age.midpoint, elapsed)
    return age.shifted(elapsed).widened(drift)


def decay_multiplier(attribute: str, elapsed_years: float, *, subject_was_minor: bool = False) -> float:
    """Weight multiplier in (0, 1] for ``attribute`` after ``elapsed_years``."""
    half_life = HALF_LIFE_YEARS.get(attribute)
    if half_life is None or elapsed_years <= 0:
        return 1.0
    if subject_was_minor:
        half_life = half_life / MINOR_DECAY_MULTIPLIER.get(attribute, 1.0)
    return float(math.pow(0.5, elapsed_years / max(half_life, 1e-6)))


@dataclass(frozen=True)
class TemporalContext:
    """Everything the scorer needs to know about time for one comparison."""

    elapsed_years: float
    subject_was_minor: bool
    plausibility: float | None

    def weight_for(self, attribute: str) -> float:
        return decay_multiplier(attribute, self.elapsed_years, subject_was_minor=self.subject_was_minor)


def temporal_plausibility(
    probe_last_seen: date | datetime | None,
    candidate_recorded: date | datetime | None,
    *,
    grace_days: float = 21.0,
    scale_years: float = 6.0,
) -> float | None:
    """Could the candidate record correspond to this case, on timing alone?

    A person cannot be recovered as unidentified meaningfully *before* they went
    missing, so records predating the disappearance are penalised — but only
    softly, and with a grace window, because reported "last seen" dates are
    frequently approximate and sometimes plain wrong.

    After the disappearance, plausibility decays slowly: a match seven years
    later is entirely ordinary in this domain, so the decay is gentle rather
    than a cutoff.
    """
    if probe_last_seen is None or candidate_recorded is None:
        return None

    delta_years = years_between(probe_last_seen, candidate_recorded)
    grace_years = grace_days / DAYS_PER_YEAR

    if delta_years < -grace_years:
        # Recorded before the person went missing.
        return float(math.exp((delta_years + grace_years) / 0.5))

    if delta_years < 0:
        return 0.9

    return float(0.55 + 0.45 * math.exp(-delta_years / scale_years))


def build_context(
    probe_last_seen: date | datetime | None,
    candidate_recorded: date | datetime | None,
    probe_age_at_report: float | None,
) -> TemporalContext:
    elapsed = max(0.0, years_between(probe_last_seen, candidate_recorded or date.today()))
    return TemporalContext(
        elapsed_years=elapsed,
        subject_was_minor=probe_age_at_report is not None and probe_age_at_report < 18,
        plausibility=temporal_plausibility(probe_last_seen, candidate_recorded),
    )
