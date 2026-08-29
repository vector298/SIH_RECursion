from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core import adaptive, pipeline
from app.db.models import AdaptiveQuestion, AuditLog, Candidate, Case, MatchRun, Verification
from app.db.session import get_db
from app.schemas import (
    AnswerRequest, CandidateOut, CaseSummary, MatchRunOut, VerificationOut, VerificationRequest,
)

router = APIRouter(prefix="/api", tags=["matching"])

HUMAN_LOOP_NOTICE = (
    "AI prioritisation — officer verification required. Ranked output is decision "
    "support only and does not constitute a confirmed identification."
)


def _load_case(db: Session, case_id: str) -> Case:
    stmt = select(Case).options(selectinload(Case.marks), selectinload(Case.images))
    case = db.scalar(stmt.where(Case.id == case_id)) or db.scalar(stmt.where(Case.case_number == case_id))
    if not case:
        raise HTTPException(404, f"No case {case_id}")
    return case


def _serialise(run: MatchRun, case: Case, result: dict, question: dict | None,
               candidates: list[dict]) -> MatchRunOut:
    return MatchRunOut(
        id=run.id, case_id=case.id, case_number=case.case_number,
        corpus_size=result["corpus_size"],
        duration_ms=round(result["duration_ms"], 2),
        stages=result["stages"],
        backends=result["backends"],
        created_at=run.created_at,
        adaptive_question=question,
        candidates=[
            CandidateOut(
                rank=c["rank"],
                case=CaseSummary.of(c["case"]),
                confidence=round(c["confidence"], 4),
                coverage=round(c["coverage"], 4),
                scores=c["scores"], sources=c["sources"], detail=c["detail"],
                evidence=c["evidence"], concerns=c["concerns"],
                confidence_before=c.get("confidence_before"),
                officer_confirmed=c.get("officer_confirmed"),
            )
            for c in candidates
        ],
    )


@router.post("/cases/{case_id}/match", response_model=MatchRunOut)
def run_match(case_id: str, limit: int | None = Query(None, le=50), db: Session = Depends(get_db)):
    """Execute the seven-stage pipeline and persist the run.

    Stage timings are measured and funnel counts are the real surviving set
    sizes — nothing here is scripted.
    """
    case = _load_case(db, case_id)
    result = pipeline.run_match(db, case, limit=limit)

    run = MatchRun(
        case_id=case.id,
        corpus_size=result["corpus_size"],
        stages=result["stages"],
        weights={"backends": result["backends"]},
        duration_ms=result["duration_ms"],
    )
    db.add(run)
    db.flush()

    for c in result["candidates"]:
        db.add(Candidate(
            match_run_id=run.id, candidate_case_id=c["case"].id, rank=c["rank"],
            confidence=c["confidence"], coverage=c["coverage"],
            scores=c["scores"], evidence=c["evidence"], concerns=c["concerns"],
        ))

    question_payload = None
    question = adaptive.generate(case, result["candidates"])
    if question:
        row = AdaptiveQuestion(
            match_run_id=run.id, question=question.question, rationale=question.rationale,
            attribute=question.attribute, options=question.options,
        )
        db.add(row)
        db.flush()
        question_payload = {"id": row.id, **question.as_dict()}

    db.add(AuditLog(action="match.run", entity="case", entity_id=case.id,
                    payload={"run_id": run.id, "candidates": len(result["candidates"])}))
    db.commit()
    db.refresh(run)

    return _serialise(run, case, result, question_payload, result["candidates"])


@router.get("/cases/{case_id}/matches", response_model=list[dict])
def list_runs(case_id: str, db: Session = Depends(get_db)):
    case = _load_case(db, case_id)
    runs = db.scalars(
        select(MatchRun).where(MatchRun.case_id == case.id).order_by(MatchRun.created_at.desc())
    ).all()
    return [
        {
            "id": r.id, "created_at": r.created_at, "corpus_size": r.corpus_size,
            "duration_ms": r.duration_ms, "candidates": len(r.candidates),
            "top_confidence": max((c.confidence for c in r.candidates), default=None),
        }
        for r in runs
    ]


@router.post("/matches/{run_id}/answer", response_model=MatchRunOut)
def answer_question(run_id: str, payload: AnswerRequest, db: Session = Depends(get_db)):
    """Fold an officer's answer to the adaptive question into the ranking.

    The candidates are re-fused with officer testimony as an additional
    high-reliability source, then re-sorted. The prior confidence is returned
    alongside the new one so the change is auditable.
    """
    run = db.get(MatchRun, run_id)
    if not run:
        raise HTTPException(404, "No such match run")

    case = _load_case(db, run.case_id)
    stored = db.scalars(
        select(Candidate).where(Candidate.match_run_id == run.id).order_by(Candidate.rank)
    ).all()
    if not stored:
        raise HTTPException(409, "This run has no candidates to re-rank")

    chosen = db.get(Case, payload.chosen_case_id)
    if not chosen:
        raise HTTPException(404, "Chosen candidate case not found")
    if payload.chosen_case_id not in {c.candidate_case_id for c in stored}:
        raise HTTPException(400, "Chosen case is not a candidate on this run")

    # Rebuild the shape adaptive.apply_answer expects, from persisted state.
    rebuilt = []
    for row in stored:
        cand_case = _load_case(db, row.candidate_case_id)
        sources = {
            name: {"score": row.scores.get(name), "weight": weight, "available": row.scores.get(name) is not None}
            for name, weight in _weights_from(row).items()
        }
        rebuilt.append({
            "rank": row.rank, "case": cand_case, "confidence": row.confidence,
            "coverage": row.coverage, "scores": row.scores, "sources": sources,
            "detail": {}, "evidence": row.evidence, "concerns": row.concerns,
        })

    updated = adaptive.apply_answer(rebuilt, payload.chosen_case_id)

    by_id = {c.candidate_case_id: c for c in stored}
    for item in updated:
        row = by_id[item["case"].id]
        row.rank = item["rank"]
        row.confidence = item["confidence"]
        row.coverage = item["coverage"]

    question = db.scalar(select(AdaptiveQuestion).where(AdaptiveQuestion.match_run_id == run.id))
    if question:
        question.answered_case_id = payload.chosen_case_id
        question.answered_at = datetime.now(timezone.utc)

    db.add(AuditLog(actor=payload.officer, action="adaptive.answer", entity="match_run",
                    entity_id=run.id, payload={"chosen": payload.chosen_case_id}))
    db.commit()

    result = {
        "corpus_size": run.corpus_size, "stages": run.stages,
        "duration_ms": run.duration_ms,
        "backends": (run.weights or {}).get("backends", {}),
    }
    return _serialise(run, case, result, None, updated)


def _weights_from(row: Candidate) -> dict[str, float]:
    from app.core.fusion import BASE_WEIGHTS
    return {k: v for k, v in BASE_WEIGHTS.items()}


@router.post("/cases/{case_id}/verify", response_model=VerificationOut, status_code=201)
def record_verification(case_id: str, payload: VerificationRequest, db: Session = Depends(get_db)):
    """Record an officer decision on a candidate.

    Note what this endpoint does not do: it never sets an identity on the case.
    A 'verified' decision flags the pair for physical verification and nothing
    more — the system has no route by which software alone can confirm identity.
    """
    case = _load_case(db, case_id)
    candidate = db.get(Case, payload.candidate_case_id)
    if not candidate:
        raise HTTPException(404, "Candidate case not found")

    record = Verification(
        case_id=case.id, candidate_case_id=candidate.id,
        decision=payload.decision, officer=payload.officer, note=payload.note,
    )
    db.add(record)

    if payload.decision == "verified":
        case.status = "PENDING PHYSICAL VERIFICATION"
    elif payload.decision == "more_evidence":
        case.status = "UNDER REVIEW"

    db.add(AuditLog(actor=payload.officer, action=f"verification.{payload.decision}",
                    entity="case", entity_id=case.id,
                    payload={"candidate": candidate.case_number}))
    db.commit()
    db.refresh(record)
    return VerificationOut.model_validate(record)


@router.get("/cases/{case_id}/verifications", response_model=list[VerificationOut])
def list_verifications(case_id: str, db: Session = Depends(get_db)):
    case = _load_case(db, case_id)
    rows = db.scalars(
        select(Verification).where(Verification.case_id == case.id)
        .order_by(Verification.created_at.desc())
    ).all()
    return [VerificationOut.model_validate(r) for r in rows]


@router.get("/notice")
def human_loop_notice():
    return {"notice": HUMAN_LOOP_NOTICE}
