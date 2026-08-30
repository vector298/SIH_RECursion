"""Hard search — the cheap deterministic reduction that runs before any model.

The expensive stages (text embedding, then face embedding comparison) cost
orders of magnitude more per record than an indexed SQL predicate. Running them
across a national index is not viable, so they are only ever asked about records
that survived filters a database can evaluate directly.

The ordering rule is: cheapest filter with the highest selectivity first.

    corpus                          every opposite-type record
    -> sex + case type              indexed equality, huge cut
    -> time window                  indexed range on last_seen_at
    -> geographic bounding box      indexed range on lat/lon

Every filter is written so that **NULL never excludes**. ``sex IS NULL`` on
either side keeps the record: an unrecorded field means the system knows less,
not that the record is wrong. That single property is what stops the funnel from
quietly discarding the sparse records this system exists to resolve.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db.models import Case


@dataclass
class FunnelStep:
    stage: str
    label: str
    remaining: int
    removed: int
    predicate: str


def opposite_type(case_type: str) -> str:
    return "unidentified" if case_type == "missing" else "missing"


def run(db: Session, probe: Case, *, time_grace_days: int = 30, time_window_years: float = 12.0):
    """Return (candidate_cases, funnel_steps)."""
    target_type = opposite_type(probe.case_type)
    steps: list[FunnelStep] = []

    base = select(Case).where(Case.id != probe.id, Case.case_type == target_type)

    def count_of(stmt) -> int:
        return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)

    corpus = count_of(base)
    steps.append(FunnelStep("corpus", "Records of the opposite type in the national index",
                            corpus, 0, f"case_type = '{target_type}'"))

    # --- sex ---------------------------------------------------------------
    # A recorded mismatch eliminates: two records that both state a sex, and
    # state different ones, are not the same person. A record that states none
    # is retained — silence is not disagreement.
    if probe.sex:
        stmt = base.where(or_(Case.sex.is_(None), Case.sex == probe.sex))
        predicate = f"sex IS NULL OR sex = '{probe.sex}'  (recorded mismatch eliminates)"
    else:
        stmt = base
        predicate = "sex unknown on probe — no filter applied"
    n = count_of(stmt)
    steps.append(FunnelStep("hard", "After sex filter (unknown retained)", n, corpus - n, predicate))
    prev = n

    # --- blood type --------------------------------------------------------
    # The strongest hard filter available: blood group does not change, so two
    # records stating different groups cannot describe one person. Like sex, it
    # only fires when BOTH sides recorded a value — and unknown is common enough
    # at intake that this usually removes nothing at all.
    if probe.blood_type:
        stmt = stmt.where(or_(Case.blood_type.is_(None), Case.blood_type == probe.blood_type))
        predicate = f"blood_type IS NULL OR blood_type = '{probe.blood_type}'  (recorded mismatch eliminates)"
    else:
        predicate = "blood type unknown on probe — no filter applied"
    n = count_of(stmt)
    steps.append(FunnelStep("hard", "After blood type (unknown retained)", n, prev - n, predicate))
    prev = n

    # --- time window -------------------------------------------------------
    if probe.last_seen_at:
        lower = probe.last_seen_at - timedelta(days=time_grace_days)
        upper = probe.last_seen_at + timedelta(days=int(time_window_years * 365.2425))
        stmt = stmt.where(or_(
            Case.last_seen_at.is_(None),
            and_(Case.last_seen_at >= lower, Case.last_seen_at <= upper),
        ))
        predicate = f"last_seen_at IS NULL OR between {lower.date()} and {upper.date()}"
    else:
        predicate = "no reference date on probe — no filter applied"
    n = count_of(stmt)
    steps.append(FunnelStep("hard", "After time window (unknown retained)", n, prev - n, predicate))
    prev = n

    # --- geography ---------------------------------------------------------
    if probe.lat is not None and probe.lon is not None:
        d = settings.hard_search_geo_degrees
        stmt = stmt.where(or_(
            Case.lat.is_(None), Case.lon.is_(None),
            and_(Case.lat.between(probe.lat - d, probe.lat + d),
                 Case.lon.between(probe.lon - d, probe.lon + d)),
        ))
        predicate = f"coords IS NULL OR within ±{d}° of ({probe.lat:.3f}, {probe.lon:.3f})"
    else:
        predicate = "no coordinates on probe — no filter applied"
    n = count_of(stmt)
    steps.append(FunnelStep("hard", "After geographic bounding box (unknown retained)", n, prev - n, predicate))

    candidates = list(db.scalars(
        stmt.options(selectinload(Case.marks), selectinload(Case.images))
    ).unique())

    return candidates, steps
