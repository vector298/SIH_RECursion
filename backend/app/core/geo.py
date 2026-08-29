"""Geospatial plausibility.

Distance is not a filter. Someone who disappeared in Bengaluru turning up in
Chennai is unremarkable; turning up in Guwahati is less likely but entirely
possible, and long-distance displacement is exactly the pattern a cross-state
system exists to catch. So distance is scored against *elapsed time* — how far
could this person plausibly have travelled — rather than against a fixed radius.
"""
from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088

# Beyond ordinary movement, this is the distance scale over which plausibility
# falls away once elapsed time is accounted for.
BASE_REACH_KM = 350.0
REACH_PER_YEAR_KM = 900.0
MAX_REACH_KM = 3500.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def reach_km(elapsed_years: float) -> float:
    """How far someone could plausibly have moved in the elapsed time."""
    return min(MAX_REACH_KM, BASE_REACH_KM + REACH_PER_YEAR_KM * max(0.0, elapsed_years))


def location_compatibility(
    lat1: float | None, lon1: float | None,
    lat2: float | None, lon2: float | None,
    elapsed_years: float = 0.0,
) -> tuple[float | None, float | None]:
    """Return (score, distance_km). Score is None when either side lacks coords."""
    if None in (lat1, lon1, lat2, lon2):
        return None, None

    distance = haversine_km(lat1, lon1, lat2, lon2)
    reach = reach_km(elapsed_years)

    # Full credit well within reach, then a smooth decay rather than a cliff.
    score = math.exp(-((distance / reach) ** 1.6))
    return float(max(0.0, min(1.0, score))), float(distance)


def bounding_box(lat: float, lon: float, degrees: float) -> tuple[float, float, float, float]:
    """Cheap SQL prefilter box. Deliberately generous — it only removes records
    that no plausible travel model would reach."""
    return (lat - degrees, lat + degrees, lon - degrees, lon + degrees)
