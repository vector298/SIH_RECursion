"""The uncertainty primitive the whole matcher is built on.

Three states, and the third is the one that matters:

    EXACT    a single value       -> stored as a degenerate interval [v, v]
    RANGE    a bounded estimate   -> [lo, hi]
    UNKNOWN  not recorded         -> no interval at all

Comparing two intervals returns ``None`` when either side is unknown. ``None``
means "this source produced no evidence", which is different from 0.0, meaning
"this source produced evidence *against*". The fusion step drops ``None``
sources from the weighted average and reports the resulting coverage, so a
sparse record scores lower because it has less evidence behind it — never
because a blank field was silently treated as a mismatch.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class Mode(str, Enum):
    EXACT = "exact"
    RANGE = "range"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Interval:
    """A closed interval [lo, hi], or the unknown interval."""

    lo: float | None = None
    hi: float | None = None
    mode: Mode = Mode.UNKNOWN

    # ---------------------------------------------------------------- build
    @staticmethod
    def exact(value: float | None) -> "Interval":
        if value is None:
            return Interval.unknown()
        return Interval(float(value), float(value), Mode.EXACT)

    @staticmethod
    def range(lo: float | None, hi: float | None) -> "Interval":
        if lo is None and hi is None:
            return Interval.unknown()
        if lo is None or hi is None:                 # half-open: treat as exact
            v = lo if lo is not None else hi
            return Interval.exact(v)
        lo, hi = float(lo), float(hi)
        if hi < lo:
            lo, hi = hi, lo
        return Interval(lo, hi, Mode.EXACT if lo == hi else Mode.RANGE)

    @staticmethod
    def unknown() -> "Interval":
        return Interval(None, None, Mode.UNKNOWN)

    @staticmethod
    def from_record(mode: str | None, lo: float | None, hi: float | None) -> "Interval":
        if mode == Mode.UNKNOWN or (lo is None and hi is None):
            return Interval.unknown()
        if mode == Mode.EXACT:
            return Interval.exact(lo if lo is not None else hi)
        return Interval.range(lo, hi)

    # ----------------------------------------------------------- inspection
    @property
    def known(self) -> bool:
        return self.mode is not Mode.UNKNOWN and self.lo is not None and self.hi is not None

    @property
    def width(self) -> float:
        return 0.0 if not self.known else self.hi - self.lo

    @property
    def midpoint(self) -> float | None:
        return None if not self.known else (self.lo + self.hi) / 2.0

    def widened(self, by: float) -> "Interval":
        if not self.known:
            return self
        return Interval(self.lo - by, self.hi + by, Mode.RANGE if by > 0 else self.mode)

    def shifted(self, by: float) -> "Interval":
        if not self.known:
            return self
        return Interval(self.lo + by, self.hi + by, self.mode)

    def to_dict(self) -> dict:
        return {"mode": self.mode.value, "lo": self.lo, "hi": self.hi}

    def __str__(self) -> str:
        if not self.known:
            return "unknown"
        lo, hi = round(self.lo, 1), round(self.hi, 1)
        return f"{lo:g}" if lo == hi else f"{lo:g}–{hi:g}"


def overlaps(a: Interval, b: Interval) -> bool:
    """Cheap boolean used by the hard-search stage. Unknown never excludes."""
    if not a.known or not b.known:
        return True
    return a.lo <= b.hi and b.lo <= a.hi


def compare(a: Interval, b: Interval, *, decay: float) -> float | None:
    """Score how compatible two intervals are, in [0, 1], or None if unknown.

    Overlapping intervals score by Intersection over Union, so a tight interval
    agreeing with another tight interval beats two vague ones that merely
    overlap — the score reflects how much the pair actually constrains things.

    Disjoint intervals do not score zero. They decay exponentially with the gap
    between them, scaled by ``decay`` (the distance at which the score falls to
    1/e). A 23–27 report against a 28–30 candidate is weak evidence, not proof
    of a different person: estimates are wrong by a year all the time.
    """
    if not a.known or not b.known:
        return None

    inter = min(a.hi, b.hi) - max(a.lo, b.lo)
    if inter >= 0:
        union = max(a.hi, b.hi) - min(a.lo, b.lo)
        if union <= 0:                       # two identical point values
            return 1.0
        return max(0.0, min(1.0, inter / union))

    gap = -inter
    return float(math.exp(-gap / max(decay, 1e-6)))


def compare_categorical(a: str | None, b: str | None, *, mismatch: float = 0.0) -> float | None:
    """Categorical agreement. None on either side means no evidence."""
    if a is None or b is None:
        return None
    if not str(a).strip() or not str(b).strip():
        return None
    return 1.0 if str(a).strip().lower() == str(b).strip().lower() else mismatch
