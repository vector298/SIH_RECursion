from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import case as sa_case
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core import semantic
from app.db.models import Candidate, Case, Image, Mark, MatchRun, Verification
from app.db.session import get_db
from app.schemas import HealthOut
from app.services import face as face_service
from app.services import gemini

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)):
    """Reports which backends are actually live.

    Worth calling before a demo: it tells you whether you are running on real
    ArcFace weights and a real Gemini key, or on the local fallbacks.
    """
    counts = {
        "cases": db.scalar(select(func.count()).select_from(Case)) or 0,
        "missing": db.scalar(select(func.count()).select_from(Case).where(Case.case_type == "missing")) or 0,
        "unidentified": db.scalar(select(func.count()).select_from(Case).where(Case.case_type == "unidentified")) or 0,
        "marks": db.scalar(select(func.count()).select_from(Mark)) or 0,
        "images": db.scalar(select(func.count()).select_from(Image)) or 0,
        "match_runs": db.scalar(select(func.count()).select_from(MatchRun)) or 0,
        "verifications": db.scalar(select(func.count()).select_from(Verification)) or 0,
    }
    return HealthOut(
        status="ok",
        version=settings.version,
        database="postgresql" if not settings.is_sqlite else "sqlite",
        backends={
            "face_embedding": face_service.backend_name(),
            "face_is_real_arcface": face_service.is_real_arcface(),
            "semantic": semantic.backend_name(),
            "language": gemini.backend_name(),
            "gemini_configured": gemini.available(),
        },
        counts=counts,
    )


@router.get("/analytics/summary")
def summary(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(Case)) or 0
    missing = db.scalar(select(func.count()).select_from(Case).where(Case.case_type == "missing")) or 0
    unidentified = total - missing
    high_priority = db.scalar(
        select(func.count()).select_from(Case).where(Case.priority == "HIGH PRIORITY")
    ) or 0
    resolved = db.scalar(
        select(func.count()).select_from(Case).where(Case.status.in_(["RESOLVED", "CLOSED"]))
    ) or 0
    potential = db.scalar(select(func.count()).select_from(Candidate)) or 0

    return {
        "active_missing": missing,
        "unidentified": unidentified,
        "potential_matches": potential,
        "high_priority": high_priority,
        "resolved": resolved,
        "total_records": total,
    }


@router.get("/analytics/by-state")
def by_state(db: Session = Depends(get_db)):
    rows = db.execute(
        select(
            Case.state,
            func.sum(sa_case((Case.case_type == "missing", 1), else_=0)).label("missing"),
            func.sum(sa_case((Case.case_type == "unidentified", 1), else_=0)).label("unidentified"),
        )
        .where(Case.state.is_not(None))
        .group_by(Case.state)
        .order_by(func.count().desc())
    ).all()
    return [{"state": r[0], "missing": int(r[1] or 0), "unidentified": int(r[2] or 0)} for r in rows]


@router.get("/analytics/confidence-distribution")
def confidence_distribution(db: Session = Depends(get_db)):
    buckets = [(0.0, 0.2, "0–20"), (0.2, 0.4, "20–40"), (0.4, 0.6, "40–60"),
               (0.6, 0.75, "60–75"), (0.75, 0.85, "75–85"), (0.85, 0.95, "85–95"), (0.95, 1.01, "95+")]
    scores = [c for (c,) in db.execute(select(Candidate.confidence)).all()]
    return [
        {"bucket": label, "n": sum(1 for s in scores if lo <= s < hi)}
        for lo, hi, label in buckets
    ]


@router.get("/analytics/map")
def map_points(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Case).where(Case.lat.is_not(None), Case.lon.is_not(None))
    ).all()
    return [
        {
            "id": c.id, "case_number": c.case_number, "kind": c.case_type,
            "lat": c.lat, "lon": c.lon, "city": (c.location_text or "").split(",")[0].strip(),
            "state": c.state, "status": c.status, "priority": c.priority,
        }
        for c in rows
    ]
