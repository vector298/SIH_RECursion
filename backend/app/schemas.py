"""Request and response models.

The API speaks the same uncertainty vocabulary as the schema: an attribute is
``{"mode": "exact"|"range"|"unknown", ...}``, never a bare value that silently
loses whether it was measured or guessed.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Mode = Literal["exact", "range", "unknown"]


class UncertainValue(BaseModel):
    mode: Mode = "unknown"
    exact: float | None = None
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def _check(self) -> "UncertainValue":
        if self.mode == "exact" and self.exact is None:
            raise ValueError("mode 'exact' requires 'exact'")
        if self.mode == "range" and (self.min is None or self.max is None):
            raise ValueError("mode 'range' requires 'min' and 'max'")
        return self

    def to_bounds(self) -> tuple[str, float | None, float | None]:
        if self.mode == "unknown":
            return "unknown", None, None
        if self.mode == "exact":
            return "exact", self.exact, self.exact
        lo, hi = float(self.min), float(self.max)  # type: ignore[arg-type]
        return ("range" if lo != hi else "exact"), min(lo, hi), max(lo, hi)

    @staticmethod
    def from_bounds(mode: str | None, lo: float | None, hi: float | None) -> "UncertainValue":
        if mode == "unknown" or (lo is None and hi is None):
            return UncertainValue(mode="unknown")
        if mode == "exact" or lo == hi:
            return UncertainValue(mode="exact", exact=lo)
        return UncertainValue(mode="range", min=lo, max=hi)


# ---------------------------------------------------------------------------
class MarkIn(BaseModel):
    kind: str | None = None
    body_location: str | None = None
    side: str | None = None
    size_text: str | None = None
    size_cm: float | None = None
    shape: str | None = None
    description: str = ""


class MarkOut(MarkIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    extracted_by: str
    embedding_model: str | None = None


class ImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    slot: str
    width: int | None = None
    height: int | None = None
    quality_score: float | None = None
    resolution_label: str | None = None
    face_detected: bool = False
    face_visibility: float | None = None
    quality_detail: dict | None = None
    embedding_model: str | None = None
    # The embedding itself is never serialised.


class CaseIn(BaseModel):
    case_number: str | None = None
    case_type: Literal["missing", "unidentified"]

    name: str | None = None
    age: UncertainValue = Field(default_factory=UncertainValue)
    age_observed_on: date | None = None
    height: UncertainValue = Field(default_factory=UncertainValue)
    sex: str | None = None
    build: str | None = None
    blood_type: str | None = None

    last_seen_at: datetime | None = None
    location_text: str | None = None
    district: str | None = None
    state: str | None = None
    lat: float | None = None
    lon: float | None = None

    circumstances: str | None = None
    clothing: str | None = None
    appearance: str | None = None

    priority: str = "ACTIVE"
    status: str | None = None
    officer: str | None = None
    marks: list[MarkIn] = Field(default_factory=list)


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_number: str
    case_type: str
    status: str
    priority: str
    name: str | None
    name_known: bool
    age: UncertainValue
    age_observed_on: date | None
    height: UncertainValue
    sex: str | None
    build: str | None
    blood_type: str | None
    last_seen_at: datetime | None
    location_text: str | None
    district: str | None
    state: str | None
    lat: float | None
    lon: float | None
    circumstances: str | None
    clothing: str | None
    appearance: str | None
    officer: str | None
    created_at: datetime
    marks: list[MarkOut] = Field(default_factory=list)
    images: list[ImageOut] = Field(default_factory=list)

    @staticmethod
    def of(case) -> "CaseOut":
        return CaseOut(
            id=case.id, case_number=case.case_number, case_type=case.case_type,
            status=case.status, priority=case.priority, name=case.name,
            name_known=case.name_known,
            age=UncertainValue.from_bounds(case.age_mode, case.age_lo, case.age_hi),
            age_observed_on=case.age_observed_on,
            height=UncertainValue.from_bounds(case.height_mode, case.height_lo, case.height_hi),
            sex=case.sex, build=case.build, blood_type=case.blood_type,
            last_seen_at=case.last_seen_at, location_text=case.location_text,
            district=case.district, state=case.state, lat=case.lat, lon=case.lon,
            circumstances=case.circumstances, clothing=case.clothing,
            appearance=case.appearance, officer=case.officer, created_at=case.created_at,
            marks=[MarkOut.model_validate(m) for m in case.marks],
            images=[ImageOut.model_validate(i) for i in case.images],
        )


class CaseSummary(BaseModel):
    id: str
    case_number: str
    case_type: str
    status: str
    priority: str
    name: str | None
    name_known: bool
    age: UncertainValue
    height: UncertainValue
    sex: str | None
    location_text: str | None
    state: str | None
    lat: float | None
    lon: float | None
    last_seen_at: datetime | None
    mark_count: int
    image_count: int
    top_confidence: float | None = None
    candidate_count: int | None = None

    @staticmethod
    def of(case, top_confidence: float | None = None, candidate_count: int | None = None) -> "CaseSummary":
        return CaseSummary(
            id=case.id, case_number=case.case_number, case_type=case.case_type,
            status=case.status, priority=case.priority, name=case.name,
            name_known=case.name_known,
            age=UncertainValue.from_bounds(case.age_mode, case.age_lo, case.age_hi),
            height=UncertainValue.from_bounds(case.height_mode, case.height_lo, case.height_hi),
            sex=case.sex, location_text=case.location_text, state=case.state,
            lat=case.lat, lon=case.lon, last_seen_at=case.last_seen_at,
            mark_count=len(case.marks), image_count=len(case.images),
            top_confidence=top_confidence, candidate_count=candidate_count,
        )


# ---------------------------------------------------------------------------
class ExtractRequest(BaseModel):
    text: str


class ExtractResponse(BaseModel):
    kind: str | None = None
    body_location: str | None = None
    side: str | None = None
    size_text: str | None = None
    size_cm: float | None = None
    shape: str | None = None
    confidence: float | None = None
    source: str
    embedding_generated: bool = False
    embedding_model: str | None = None
    embedding_dim: int | None = None


class CandidateOut(BaseModel):
    rank: int
    case: CaseSummary
    confidence: float
    coverage: float
    scores: dict[str, Any]
    sources: dict[str, Any]
    detail: dict[str, Any]
    evidence: list[str]
    concerns: list[str]
    confidence_before: float | None = None
    officer_confirmed: bool | None = None


class MatchRunOut(BaseModel):
    id: str
    case_id: str
    case_number: str
    corpus_size: int
    duration_ms: float
    stages: list[dict]
    backends: dict[str, Any]
    candidates: list[CandidateOut]
    adaptive_question: dict | None = None
    created_at: datetime


class AnswerRequest(BaseModel):
    chosen_case_id: str
    officer: str | None = None


class VerificationRequest(BaseModel):
    candidate_case_id: str
    decision: Literal["verified", "rejected", "more_evidence"]
    officer: str | None = None
    note: str | None = None


class VerificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    case_id: str
    candidate_case_id: str
    decision: str
    officer: str | None
    note: str | None
    created_at: datetime
    disclaimer: str = (
        "Recorded as an investigative decision. This does not constitute a "
        "confirmed identification; physical or documentary verification is required."
    )


class HealthOut(BaseModel):
    status: str
    version: str
    database: str
    backends: dict[str, Any]
    counts: dict[str, int]
