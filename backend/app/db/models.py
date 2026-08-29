"""ORM models.

The uncertainty-aware schema is the important part. Every bounded attribute is
stored as (mode, lo, hi):

    exact    -> lo == hi == value
    range    -> lo <  hi
    unknown  -> lo IS NULL AND hi IS NULL

Storing exact values as a degenerate interval means SQL overlap predicates work
for both cases without branching, and NULL cleanly means "not recorded" rather
than being overloaded as zero. Categorical attributes use NULL for unknown.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    case_type: Mapped[str] = mapped_column(String(16), index=True)  # missing | unidentified

    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    priority: Mapped[str] = mapped_column(String(32), default="ACTIVE")

    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    name_known: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- uncertainty-aware attributes ---
    age_mode: Mapped[str] = mapped_column(String(8), default="unknown")
    age_lo: Mapped[float | None] = mapped_column(Float, nullable=True)
    age_hi: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The date the age above was true. Ages are projected forward from here, so
    # a case filed in 2019 is never searched with its 2019 age.
    age_observed_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    height_mode: Mapped[str] = mapped_column(String(8), default="unknown")
    height_lo: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_hi: Mapped[float | None] = mapped_column(Float, nullable=True)

    sex: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    build: Mapped[str | None] = mapped_column(String(32), nullable=True)
    blood_type: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # --- last known information ---
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    location_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    circumstances: Mapped[str | None] = mapped_column(Text, nullable=True)
    clothing: Mapped[str | None] = mapped_column(Text, nullable=True)
    appearance: Mapped[str | None] = mapped_column(Text, nullable=True)

    officer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    marks: Mapped[list[Mark]] = relationship(back_populates="case", cascade="all, delete-orphan")
    images: Mapped[list[Image]] = relationship(back_populates="case", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_cases_type_sex", "case_type", "sex"),
        Index("ix_cases_geo", "lat", "lon"),
    )


class Mark(Base):
    """A distinguishing characteristic: scar, tattoo, birthmark or other feature."""

    __tablename__ = "marks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)

    kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    body_location: Mapped[str | None] = mapped_column(String(64), nullable=True)
    side: Mapped[str | None] = mapped_column(String(16), nullable=True)
    size_text: Mapped[str | None] = mapped_column(String(32), nullable=True)
    size_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    shape: Mapped[str | None] = mapped_column(String(32), nullable=True)

    description: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extracted_by: Mapped[str] = mapped_column(String(24), default="manual")  # gemini | heuristic | manual

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    case: Mapped[Case] = relationship(back_populates="marks")


class Image(Base):
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)

    slot: Mapped[str] = mapped_column(String(16), default="face")  # face | body | side | other
    path: Mapped[str] = mapped_column(String(400))
    mime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # quality assessment (OpenCV, optionally corroborated by Gemini)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    blur_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    brightness: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolution_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    face_visibility: Mapped[float | None] = mapped_column(Float, nullable=True)
    face_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    quality_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ArcFace embedding — stored, never exposed through the API
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    case: Mapped[Case] = relationship(back_populates="images")


class MatchRun(Base):
    __tablename__ = "match_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)

    corpus_size: Mapped[int] = mapped_column(Integer, default=0)
    stages: Mapped[list] = mapped_column(JSON, default=list)   # timings + funnel counts
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    candidates: Mapped[list[Candidate]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Candidate.rank"
    )


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    match_run_id: Mapped[str] = mapped_column(ForeignKey("match_runs.id", ondelete="CASCADE"), index=True)
    candidate_case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)

    rank: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    coverage: Mapped[float] = mapped_column(Float, default=0.0)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    concerns: Mapped[list] = mapped_column(JSON, default=list)

    run: Mapped[MatchRun] = relationship(back_populates="candidates")


class Verification(Base):
    """Officer decisions. This table is the human-in-the-loop record."""

    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    candidate_case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"))

    decision: Mapped[str] = mapped_column(String(24))  # verified | rejected | more_evidence
    officer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AdaptiveQuestion(Base):
    __tablename__ = "adaptive_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    match_run_id: Mapped[str] = mapped_column(ForeignKey("match_runs.id", ondelete="CASCADE"), index=True)

    question: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    attribute: Mapped[str | None] = mapped_column(String(64), nullable=True)
    options: Mapped[list] = mapped_column(JSON, default=list)

    answered_case_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
