from __future__ import annotations

import shutil
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.core import quality, semantic
from app.db.models import AuditLog, Candidate, Case, Image, Mark, MatchRun
from app.db.session import get_db
from app.schemas import (
    CaseIn, CaseOut, CaseSummary, ExtractedMarkOut, ExtractRequest, ExtractResponse,
    ImageOut, MarkIn, MarkOut,
)
from app.services import face as face_service
from app.services import gemini
from app.services.nlp import get_client

router = APIRouter(prefix="/api/cases", tags=["cases"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
MAX_IMAGE_BYTES = 12 * 1024 * 1024


def _audit(db: Session, action: str, entity: str, entity_id: str, payload: dict | None = None,
           actor: str | None = None) -> None:
    db.add(AuditLog(actor=actor, action=action, entity=entity, entity_id=entity_id, payload=payload))


def _next_case_number(db: Session) -> str:
    year = date.today().year
    prefix = f"CASE-{year}-"
    n = db.scalar(select(func.count()).select_from(Case).where(Case.case_number.like(f"{prefix}%"))) or 0
    while True:
        n += 1
        number = f"{prefix}{n:04d}"
        if not db.scalar(select(Case.id).where(Case.case_number == number)):
            return number


def _attach_mark(db: Session, case: Case, payload: MarkIn, extracted_by: str = "manual") -> Mark:
    vector, backend = semantic.embed(payload.description or "")
    mark = Mark(
        case_id=case.id,
        kind=payload.kind, body_location=payload.body_location, side=payload.side,
        size_text=payload.size_text, size_cm=payload.size_cm, shape=payload.shape,
        description=payload.description or "",
        embedding=vector, embedding_model=backend if vector else semantic.backend_name(),
        extracted_by=extracted_by,
    )
    db.add(mark)
    return mark


# ---------------------------------------------------------------------------
@router.post("", response_model=CaseOut, status_code=201)
def create_case(payload: CaseIn, db: Session = Depends(get_db)):
    """Register a case. Unknown fields are stored as unknown, not as blanks."""
    case_number = payload.case_number or _next_case_number(db)
    if db.scalar(select(Case.id).where(Case.case_number == case_number)):
        raise HTTPException(409, f"Case number {case_number} already exists")

    age_mode, age_lo, age_hi = payload.age.to_bounds()
    h_mode, h_lo, h_hi = payload.height.to_bounds()

    # If an age was given without a reference date, it was true when last seen.
    observed = payload.age_observed_on
    if observed is None and age_mode != "unknown":
        observed = payload.last_seen_at.date() if payload.last_seen_at else date.today()

    case = Case(
        case_number=case_number,
        case_type=payload.case_type,
        status=payload.status or ("UNIDENTIFIED" if payload.case_type == "unidentified" else "ACTIVE"),
        priority=payload.priority,
        name=payload.name,
        name_known=bool(payload.name),
        age_mode=age_mode, age_lo=age_lo, age_hi=age_hi, age_observed_on=observed,
        height_mode=h_mode, height_lo=h_lo, height_hi=h_hi,
        sex=payload.sex, build=payload.build, blood_type=payload.blood_type,
        last_seen_at=payload.last_seen_at,
        location_text=payload.location_text, district=payload.district, state=payload.state,
        lat=payload.lat, lon=payload.lon,
        circumstances=payload.circumstances, clothing=payload.clothing, appearance=payload.appearance,
        officer=payload.officer,
    )
    db.add(case)
    db.flush()

    for mark in payload.marks:
        _attach_mark(db, case, mark)

    _audit(db, "case.create", "case", case.id, {"case_number": case_number}, payload.officer)
    db.commit()
    db.refresh(case)
    return CaseOut.of(case)


@router.get("", response_model=list[CaseSummary])
def list_cases(
    db: Session = Depends(get_db),
    case_type: str | None = Query(None, pattern="^(missing|unidentified)$"),
    state: str | None = None,
    priority: str | None = None,
    q: str | None = Query(None, description="Search case number, name, location or state"),
    limit: int = Query(60, le=250),
    offset: int = 0,
):
    stmt = select(Case).options(selectinload(Case.marks), selectinload(Case.images))
    if case_type:
        stmt = stmt.where(Case.case_type == case_type)
    if state:
        stmt = stmt.where(Case.state == state)
    if priority:
        stmt = stmt.where(Case.priority == priority)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            Case.case_number.ilike(like) | Case.name.ilike(like)
            | Case.location_text.ilike(like) | Case.state.ilike(like)
        )
    stmt = stmt.order_by(Case.created_at.desc()).limit(limit).offset(offset)
    rows = list(db.scalars(stmt).unique())
    if not rows:
        return []

    # Attach each case's best result from its most recent matching run, in one
    # query rather than N. A case with no run reports None, not zero — "not yet
    # searched" and "searched, found nothing" are different facts.
    latest = (
        select(MatchRun.case_id, func.max(MatchRun.created_at).label("newest"))
        .where(MatchRun.case_id.in_([c.id for c in rows]))
        .group_by(MatchRun.case_id)
        .subquery()
    )
    summary = db.execute(
        select(
            MatchRun.case_id,
            func.max(Candidate.confidence).label("top"),
            func.count(Candidate.id).label("n"),
        )
        .join(latest, and_(MatchRun.case_id == latest.c.case_id,
                           MatchRun.created_at == latest.c.newest))
        .join(Candidate, Candidate.match_run_id == MatchRun.id)
        .group_by(MatchRun.case_id)
    ).all()
    scores = {case_id: (top, n) for case_id, top, n in summary}

    return [
        CaseSummary.of(c, *scores.get(c.id, (None, None)))
        for c in rows
    ]


@router.get("/{case_id}", response_model=CaseOut)
def get_case(case_id: str, db: Session = Depends(get_db)):
    case = _load(db, case_id)
    return CaseOut.of(case)


def _load(db: Session, case_id: str) -> Case:
    stmt = select(Case).options(selectinload(Case.marks), selectinload(Case.images))
    case = db.scalar(stmt.where(Case.id == case_id)) or db.scalar(stmt.where(Case.case_number == case_id))
    if not case:
        raise HTTPException(404, f"No case {case_id}")
    return case


@router.delete("/{case_id}", status_code=204)
def delete_case(case_id: str, db: Session = Depends(get_db)):
    case = _load(db, case_id)
    _audit(db, "case.delete", "case", case.id, {"case_number": case.case_number})
    db.delete(case)
    db.commit()


# ---------------------------------------------------------------------------
# identification marks
# ---------------------------------------------------------------------------
@router.post("/{case_id}/marks", response_model=MarkOut, status_code=201)
def add_mark(case_id: str, payload: MarkIn, db: Session = Depends(get_db)):
    case = _load(db, case_id)
    mark = _attach_mark(db, case, payload)
    _audit(db, "mark.create", "case", case.id, {"kind": payload.kind})
    db.commit()
    db.refresh(mark)
    return MarkOut.model_validate(mark)


@router.delete("/{case_id}/marks/{mark_id}", status_code=204)
def delete_mark(case_id: str, mark_id: str, db: Session = Depends(get_db)):
    case = _load(db, case_id)
    mark = next((m for m in case.marks if m.id == mark_id), None)
    if not mark:
        raise HTTPException(404, "No such mark on this case")
    db.delete(mark)
    db.commit()


# ---------------------------------------------------------------------------
# images
# ---------------------------------------------------------------------------
@router.post("/{case_id}/images", response_model=ImageOut, status_code=201)
async def upload_image(
    case_id: str,
    file: UploadFile = File(...),
    slot: str = Form("face"),
    db: Session = Depends(get_db),
):
    """Store a photograph, assess its quality, and generate a face embedding.

    The embedding is persisted but never returned: the API exposes similarity
    scores, not biometric vectors.
    """
    case = _load(db, case_id)

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, f"Unsupported image type {file.content_type}")

    case_dir = settings.media_root / case.id
    case_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "upload.jpg").suffix or ".jpg"
    path = case_dir / f"{uuid.uuid4().hex}{suffix}"

    size = 0
    with path.open("wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_IMAGE_BYTES:
                out.close()
                path.unlink(missing_ok=True)
                raise HTTPException(413, "Image exceeds 12 MB")
            out.write(chunk)

    report = quality.assess(path)
    if report.get("quality_score") is None:
        path.unlink(missing_ok=True)
        raise HTTPException(400, "Image could not be decoded")

    embedding, model_name, detected = face_service.embed_image(path)

    # Gemini corroborates quality and reads soft attributes — never identity.
    gemini_view = gemini.describe_image(path) if slot in ("face", "side") else None
    if gemini_view:
        report["gemini"] = gemini_view

    image = Image(
        case_id=case.id, slot=slot, path=str(path), mime=file.content_type,
        width=report.get("width"), height=report.get("height"),
        quality_score=report.get("quality_score"),
        blur_score=report.get("components", {}).get("sharpness"),
        brightness=report.get("raw", {}).get("mean_luminance"),
        resolution_label=report.get("resolution_label"),
        face_visibility=report.get("face_visibility"),
        face_detected=bool(detected or report.get("face_detected")),
        quality_detail=report,
        embedding=embedding, embedding_model=model_name if embedding else None,
    )
    db.add(image)
    _audit(db, "image.upload", "case", case.id,
           {"slot": slot, "quality": report.get("quality_score"), "model": model_name})
    db.commit()
    db.refresh(image)
    return ImageOut.model_validate(image)


@router.delete("/{case_id}/images/{image_id}", status_code=204)
def delete_image(case_id: str, image_id: str, db: Session = Depends(get_db)):
    case = _load(db, case_id)
    image = next((i for i in case.images if i.id == image_id), None)
    if not image:
        raise HTTPException(404, "No such image on this case")
    Path(image.path).unlink(missing_ok=True)
    db.delete(image)
    db.commit()


# ---------------------------------------------------------------------------
# free-text extraction (Gemini, with a rule-based fallback)
# ---------------------------------------------------------------------------
extract_router = APIRouter(prefix="/api/marks", tags=["marks"])


@extract_router.post("/extract", response_model=ExtractResponse)
def extract(payload: ExtractRequest):
    """Free text -> structured identification marks.

    One passage routinely describes several marks ("a scar above his left
    eyebrow and a tattoo of a star on his right forearm"), so the response is
    always a list. Output is validated against the Pydantic contract before it
    is returned; if the model answers in an unexpected shape, the deterministic
    extractor supplies the result instead and `degraded` says so.

    This endpoint never fails because of an NLP outage.
    """
    features = get_client().extract_features(payload.text)

    # One probe embedding tells the caller which backend is live and how wide
    # the vectors are, without embedding every mark up front — that happens on
    # write, in _attach_mark.
    probe = get_client().generate_embedding(features.marks[0].canonical_text()) \
        if features.marks else None

    return ExtractResponse(
        marks=[
            ExtractedMarkOut(
                type=m.type, description=m.description, location=m.location,
                side=m.side, size_text=m.size_text, size_cm=m.size_cm,
                shape=m.shape, attributes=m.attributes, confidence=m.confidence,
                canonical_text=m.canonical_text(),
            )
            for m in features.marks
        ],
        clothing=features.clothing,
        other_details=features.other_details,
        source=features.source,
        degraded=features.degraded,
        warnings=features.warnings,
        embedding_model=(probe.model if probe and probe.vector else semantic.backend_name()),
        embedding_dim=len(probe.vector) if probe and probe.vector else None,
    )
