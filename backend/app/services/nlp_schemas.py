"""Pydantic models for NLP output.

The contract with the language model is enforced here, not assumed. Anything the
model returns is parsed through these models before it reaches the rest of the
application; output that does not validate is discarded and the caller falls
back to deterministic extraction. A model that hallucinates an extra field, an
unexpected enum value or a string where a number belongs cannot reach the
matching engine.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MarkType = Literal["scar", "tattoo", "birthmark", "piercing", "amputation", "deformity", "other"]
Side = Literal["left", "right", "centre", "front", "back", "unknown"]

# Accepted spellings the model may return, normalised to our vocabulary.
_TYPE_ALIASES = {
    "scars": "scar", "scarring": "scar", "cicatrix": "scar", "surgical scar": "scar",
    "tattoos": "tattoo", "tattooed": "tattoo", "ink": "tattoo",
    "birth mark": "birthmark", "birthmarks": "birthmark", "mole": "birthmark",
    "naevus": "birthmark", "nevus": "birthmark", "mark": "birthmark",
    "piercings": "piercing", "amputated": "amputation",
    "deformities": "deformity", "disfigurement": "deformity",
}
_SIDE_ALIASES = {
    "l": "left", "lt": "left", "left-hand": "left", "left hand side": "left",
    "r": "right", "rt": "right", "right-hand": "right",
    "center": "centre", "middle": "centre", "midline": "centre",
    "rear": "back", "posterior": "back", "nape": "back",
    "anterior": "front", "not recorded": "unknown", "": "unknown", "none": "unknown",
    "n/a": "unknown", "null": "unknown",
}


class ExtractedMark(BaseModel):
    """One distinguishing characteristic pulled out of free text."""

    type: MarkType = "other"
    description: str = Field(default="", max_length=400)
    location: str | None = Field(default=None, max_length=120)
    side: Side = "unknown"
    size_text: str | None = Field(default=None, max_length=40)
    size_cm: float | None = Field(default=None, ge=0, le=300)
    shape: str | None = Field(default=None, max_length=60)
    attributes: list[str] = Field(default_factory=list, max_length=12)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("type", mode="before")
    @classmethod
    def _normalise_type(cls, v):
        if not isinstance(v, str):
            return "other"
        key = v.strip().lower()
        key = _TYPE_ALIASES.get(key, key)
        return key if key in MarkType.__args__ else "other"      # type: ignore[attr-defined]

    @field_validator("side", mode="before")
    @classmethod
    def _normalise_side(cls, v):
        if not isinstance(v, str):
            return "unknown"
        key = v.strip().lower()
        key = _SIDE_ALIASES.get(key, key)
        return key if key in Side.__args__ else "unknown"        # type: ignore[attr-defined]

    @field_validator("location", "shape", "size_text", mode="before")
    @classmethod
    def _clean_optional(cls, v):
        if v is None:
            return None
        text = str(v).strip()
        return text or None

    @field_validator("attributes", mode="before")
    @classmethod
    def _clean_attributes(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            return []
        return [str(a).strip() for a in v if str(a).strip()][:12]

    @model_validator(mode="after")
    def _derive_size(self) -> "ExtractedMark":
        """Fill size_cm from size_text when the model gave only prose."""
        if self.size_cm is None and self.size_text:
            match = re.search(
                r"(\d+(?:\.\d+)?)\s*(cm|centimet(?:er|re)s?|mm|millimet(?:er|re)s?|in(?:ch(?:es)?)?)",
                self.size_text.lower(),
            )
            if match:
                value, unit = float(match.group(1)), match.group(2)
                if unit.startswith(("mm", "millimet")):
                    value /= 10.0
                elif unit.startswith("in"):
                    value *= 2.54
                object.__setattr__(self, "size_cm", round(value, 2))
        return self

    def canonical_text(self) -> str:
        """One normalised sentence, used as the embedding input.

        Embedding a consistent rendering rather than the officer's raw phrasing
        means two records describing the same mark start closer together before
        the model is even consulted.
        """
        parts: list[str] = []
        if self.size_text:
            parts.append(self.size_text)
        if self.shape:
            parts.append(self.shape.lower())
        parts.append(self.type)
        if self.side != "unknown":
            parts.append(f"on the {self.side}")
        if self.location:
            parts.append(self.location.lower() if self.side != "unknown" else f"on the {self.location.lower()}")
        text = " ".join(p for p in parts if p)
        extras = ", ".join(self.attributes)
        return f"{text} ({extras})" if extras else text


class ExtractedFeatures(BaseModel):
    """Everything one free-text passage yielded."""

    marks: list[ExtractedMark] = Field(default_factory=list, max_length=20)
    clothing: list[str] = Field(default_factory=list, max_length=15)
    other_details: list[str] = Field(default_factory=list, max_length=15)

    # Provenance — always populated by the client, never by the model.
    source: str = "unknown"
    degraded: bool = False
    warnings: list[str] = Field(default_factory=list)

    @field_validator("clothing", "other_details", mode="before")
    @classmethod
    def _clean_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            return []
        return [str(a).strip() for a in v if str(a).strip()][:15]

    @property
    def is_empty(self) -> bool:
        return not (self.marks or self.clothing or self.other_details)


# The JSON schema handed to the model. Kept deliberately flat and closed:
# the fewer degrees of freedom, the less there is to validate away afterwards.
GEMINI_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "marks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string",
                             "enum": ["scar", "tattoo", "birthmark", "piercing",
                                      "amputation", "deformity", "other"]},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                    "side": {"type": "string",
                             "enum": ["left", "right", "centre", "front", "back", "unknown"]},
                    "size_text": {"type": "string"},
                    "shape": {"type": "string"},
                    "attributes": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
                "required": ["type", "description", "side"],
            },
        },
        "clothing": {"type": "array", "items": {"type": "string"}},
        "other_details": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["marks"],
}

EXTRACTION_SYSTEM_PROMPT = (
    "You extract structured data from a police officer's free-text description of a "
    "missing or unidentified person, for a case-matching system.\n\n"
    "Rules:\n"
    "- Return one entry in `marks` for EACH distinguishing physical characteristic "
    "mentioned: scars, tattoos, birthmarks, piercings, amputations, deformities.\n"
    "- `location` is the body part only (for example 'eyebrow', 'forearm', 'cheek'). "
    "Put the side in `side`, not in `location`.\n"
    "- `attributes` holds extra qualifiers that do not fit the other fields, such as "
    "'approximately 5 cm', 'faded', 'raised'.\n"
    "- Record clothing in `clothing`, and anything else potentially identifying in "
    "`other_details`.\n"
    "- Extract only what the text states or clearly implies. Never invent details. "
    "If a field is not stated, omit it or use 'unknown'.\n"
    "- Do not identify, name, or speculate about who the person is. Do not compare "
    "them to anyone. You are extracting text, not making a determination."
)
