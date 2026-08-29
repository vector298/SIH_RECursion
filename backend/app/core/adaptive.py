"""Adaptive investigation.

When the top candidates sit within a few points of each other, more computation
will not separate them — the models have already used everything in the records.
What *would* separate them is one fact only a person can supply.

So the system looks for the attribute with the highest **discriminative value**
across the tied group: something recorded on the probe that the candidates
disagree about, or that is missing from some of them. It asks about that, and
nothing else. Asking about an attribute they all share teaches it nothing.

The officer's answer enters the ranking as a high-reliability evidence source
and the fusion is re-run. It is weighted heavily but not absolutely — an officer
can be mistaken too, and a single answer should not be able to drive a candidate
to certainty on its own.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.fusion import SourceScore, fuse
from app.db.models import Case

# How close two candidates must be, in confidence, before a question is worth asking.
TIE_BAND = 0.08
MIN_GROUP = 2
MAX_GROUP = 4

# Weight of officer testimony relative to the model sources (see fusion.BASE_WEIGHTS,
# whose entries sum to 1.0). Deliberately dominant, deliberately not absolute.
OFFICER_WEIGHT = 0.55


@dataclass
class Question:
    question: str
    rationale: str
    attribute: str
    options: list[dict]

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "rationale": self.rationale,
            "attribute": self.attribute,
            "options": self.options,
        }


def _tied_group(candidates: list[dict]) -> list[dict]:
    if len(candidates) < MIN_GROUP:
        return []
    top = candidates[0]["confidence"]
    group = [c for c in candidates if top - c["confidence"] <= TIE_BAND]
    return group[:MAX_GROUP] if len(group) >= MIN_GROUP else []


def _mark_discriminator(probe: Case, group: list[dict]) -> Question | None:
    """A mark recorded on the probe that the candidates do not agree about."""
    for pm in probe.marks:
        if not pm.description:
            continue

        states: list[tuple[dict, str]] = []
        for cand in group:
            case: Case = cand["case"]
            same_kind = [m for m in case.marks if (m.kind or "").lower() == (pm.kind or "").lower()]
            if not same_kind:
                states.append((cand, "absent"))
                continue
            same_site = [
                m for m in same_kind
                if (m.body_location or "").lower() == (pm.body_location or "").lower()
                and (not m.side or not pm.side or m.side.lower() == pm.side.lower())
            ]
            states.append((cand, "present" if same_site else "conflicting"))

        distinct = {s for _, s in states}
        if len(distinct) < 2:
            continue    # every candidate is in the same state — asking teaches nothing

        descriptor = pm.description.strip().rstrip(".")
        side = f"{pm.side.lower()} " if pm.side and pm.side != "Not recorded" else ""
        site = (pm.body_location or "").lower()
        subject = f"a {(pm.kind or 'mark').lower()}"
        where = f" on the {side}{site}" if site else ""

        return Question(
            question=f"Which candidate has {subject}{where}, as recorded on this case — “{descriptor}”?",
            rationale=(
                "This mark is recorded on the subject case but the candidate records disagree "
                "about it. A direct observation resolves what the models cannot."
            ),
            attribute=f"mark:{pm.id}",
            options=[
                {
                    "case_id": c["case"].id,
                    "case_number": c["case"].case_number,
                    "confidence": round(c["confidence"], 4),
                    "current_state": state,
                }
                for c, state in states
            ],
        )
    return None


def _attribute_discriminator(probe: Case, group: list[dict]) -> Question | None:
    """Fall back to a plain attribute the candidates differ on."""
    checks = [
        ("build", "build or body type", lambda c: c.build),
        ("blood_type", "blood type", lambda c: c.blood_type),
        ("sex", "recorded sex", lambda c: c.sex),
    ]
    for attr, label, getter in checks:
        values = [(c, getter(c["case"])) for c in group]
        distinct = {v for _, v in values}
        if len(distinct) < 2:
            continue
        return Question(
            question=f"Which candidate's {label} matches the subject as you observe it?",
            rationale=(
                f"The candidates disagree on {label}, and it is "
                f"{'unrecorded' if getter(probe) is None else 'recorded but unconfirmed'} on the subject case."
            ),
            attribute=attr,
            options=[
                {
                    "case_id": c["case"].id,
                    "case_number": c["case"].case_number,
                    "confidence": round(c["confidence"], 4),
                    "current_state": value or "unknown",
                }
                for c, value in values
            ],
        )
    return None


def generate(probe: Case, candidates: list[dict]) -> Question | None:
    """Return a targeted question, or None when the ranking is already decisive."""
    group = _tied_group(candidates)
    if not group:
        return None
    return _mark_discriminator(probe, group) or _attribute_discriminator(probe, group)


def apply_answer(candidates: list[dict], chosen_case_id: str) -> list[dict]:
    """Fold officer testimony into the ranking and re-sort.

    The answer is added as an extra evidence source rather than overwriting the
    computed scores, so the audit trail still shows what the models found and
    what the officer contributed, separately.
    """
    updated: list[dict] = []
    for cand in candidates:
        sources = [
            SourceScore(name, d["score"], d["weight"])
            for name, d in cand["sources"].items()
        ]
        confirmed = cand["case"].id == chosen_case_id
        sources.append(SourceScore(
            "officer_verification",
            1.0 if confirmed else 0.0,
            OFFICER_WEIGHT,
            note="officer-confirmed" if confirmed else "excluded by officer observation",
        ))

        fused = fuse(sources)
        item = dict(cand)
        item["confidence_before"] = cand["confidence"]
        item["confidence"] = fused.confidence
        item["coverage"] = fused.coverage
        item["sources"] = fused.sources
        item["officer_confirmed"] = confirmed
        updated.append(item)

    updated.sort(key=lambda c: c["confidence"], reverse=True)
    for position, item in enumerate(updated, start=1):
        item["rank_before"] = item.get("rank")
        item["rank"] = position
    return updated
