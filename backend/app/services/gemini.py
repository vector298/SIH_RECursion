"""Google Gemini integration.

Gemini does four jobs here, all of them language or description tasks:

1. **Structured extraction** — turns an officer's free-text description of a
   scar, tattoo or birthmark into typed fields (kind, body location, side, size,
   shape) via a constrained JSON response schema.
2. **Text embeddings** — ``text-embedding-004`` vectors for identification-mark
   descriptions, so differently-worded accounts of the same mark still match.
3. **Evidence narratives** — the plain-English "why this candidate ranked
   highly" text, written strictly from scores the deterministic pipeline already
   computed. It explains a ranking; it never produces one.
4. **Image description** — quality observations and *soft* attributes
   (apparent age band, visible marks, occlusion, lighting) from a photograph.

What Gemini deliberately does **not** do: identify or recognise anyone. It has
no face-embedding endpoint, and identifying individuals from images falls
outside its acceptable-use policy. Identity comparison is ArcFace's job, in
``app/services/face.py``.

Every call has a local fallback, so a missing or rate-limited API key degrades
the output rather than breaking the request.
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger(__name__)

MARK_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["Scar", "Tattoo", "Birthmark", "Other feature"]},
        "body_location": {"type": "string"},
        "side": {"type": "string", "enum": ["Left", "Right", "Centre", "Front", "Back", "Not recorded"]},
        "size_text": {"type": "string"},
        "size_cm": {"type": "number"},
        "shape": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["kind", "body_location", "side", "shape"],
}


def available() -> bool:
    return bool(settings.gemini_api_key)


def backend_name() -> str:
    return f"gemini:{settings.gemini_model}" if available() else "local-heuristic"


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------
def _post(path: str, payload: dict) -> dict | None:
    if not available():
        return None
    url = f"{settings.gemini_base_url}/{path}"
    try:
        with httpx.Client(timeout=settings.gemini_timeout_s) as client:
            r = client.post(url, json=payload, headers={"x-goog-api-key": settings.gemini_api_key})
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        log.warning("Gemini call to %s failed: %s", path, exc)
        return None


def _generate(parts: list[dict], *, schema: dict | None = None, system: str | None = None) -> str | None:
    payload: dict[str, Any] = {"contents": [{"parts": parts}]}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    if schema:
        payload["generationConfig"] = {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "temperature": 0.1,
        }
    else:
        payload["generationConfig"] = {"temperature": 0.3}

    data = _post(f"models/{settings.gemini_model}:generateContent", payload)
    if not data:
        return None
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        log.warning("Unexpected Gemini response shape: %s", str(data)[:300])
        return None


# ---------------------------------------------------------------------------
# 1. structured extraction
# ---------------------------------------------------------------------------
BODY_PARTS = [
    "eyebrow", "forehead", "cheek", "chin", "nose", "lip", "ear", "neck", "throat",
    "shoulder", "chest", "back", "abdomen", "torso", "upper arm", "forearm", "wrist",
    "hand", "finger", "thigh", "knee", "shin", "calf", "ankle", "foot",
]
SHAPE_WORDS = {
    "linear": "Linear", "horizontal": "Linear", "straight": "Linear", "line": "Linear",
    "curved": "Curved", "crescent": "Curved", "arc": "Curved",
    "oval": "Oval", "elliptical": "Oval",
    "circular": "Circular", "round": "Circular",
    "irregular": "Irregular", "jagged": "Irregular", "blotchy": "Irregular",
    "script": "Script", "lettering": "Script", "text": "Script", "name": "Script",
    "pictorial": "Pictorial", "figure": "Pictorial", "design": "Pictorial", "anchor": "Pictorial",
}


def _heuristic_extract(text: str) -> dict:
    """Rule-based extraction. Used when no API key is configured."""
    t = (text or "").lower()

    if "tattoo" in t or " ink" in t:
        kind = "Tattoo"
    elif "birthmark" in t or "mole" in t or "nevus" in t:
        kind = "Birthmark"
    elif "scar" in t or "stitch" in t or "surgical" in t:
        kind = "Scar"
    else:
        kind = "Other feature"

    location = next((p for p in sorted(BODY_PARTS, key=len, reverse=True) if p in t), "")
    location = location.title() if location else ""

    if "left" in t:
        side = "Left"
    elif "right" in t:
        side = "Right"
    elif "nape" in t or "back" in t:
        side = "Back"
    elif "centre" in t or "center" in t or "middle" in t:
        side = "Centre"
    else:
        side = "Not recorded"

    size_cm, size_text = None, ""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(cm|centimet(?:er|re)s?|mm|millimet(?:er|re)s?|in(?:ch(?:es)?)?)", t)
    if m:
        value, unit = float(m.group(1)), m.group(2)
        size_cm = value / 10.0 if unit.startswith("mm") or unit.startswith("millimet") else \
                  value * 2.54 if unit.startswith("in") else value
        size_text = f"{value:g} {'mm' if unit.startswith(('mm', 'millimet')) else 'inch' if unit.startswith('in') else 'cm'}"

    shape = next((v for k, v in SHAPE_WORDS.items() if re.search(rf"\b{k}", t)), "")

    return {
        "kind": kind, "body_location": location, "side": side,
        "size_text": size_text, "size_cm": size_cm, "shape": shape,
        "confidence": 0.55, "source": "local-heuristic",
    }


def extract_mark(text: str) -> dict:
    """Free-text description -> structured identification-mark fields."""
    if not (text or "").strip():
        return {"source": backend_name(), "kind": "", "body_location": "", "side": "",
                "size_text": "", "size_cm": None, "shape": "", "confidence": 0.0}

    raw = _generate(
        [{"text": f"Description of an identifying physical characteristic:\n\n{text}"}],
        schema=MARK_SCHEMA,
        system=(
            "You extract structured identification-mark data for a police missing-persons "
            "system. Return only the fields present or clearly implied in the description. "
            "Use 'Not recorded' for side when the text does not state one. Never invent "
            "details. Never attempt to identify or describe a specific individual."
        ),
    )
    if raw:
        try:
            parsed = json.loads(raw)
            parsed.setdefault("size_cm", None)
            parsed.setdefault("size_text", "")
            parsed["source"] = backend_name()
            return parsed
        except json.JSONDecodeError:
            log.warning("Gemini returned non-JSON for mark extraction")

    return _heuristic_extract(text)


# ---------------------------------------------------------------------------
# 2. text embeddings
# ---------------------------------------------------------------------------
def embed_text(text: str) -> tuple[list[float] | None, str]:
    if not available() or not (text or "").strip():
        return None, "unavailable"
    data = _post(
        f"models/{settings.gemini_embed_model}:embedContent",
        {
            "model": f"models/{settings.gemini_embed_model}",
            "content": {"parts": [{"text": text}]},
            "taskType": "SEMANTIC_SIMILARITY",
        },
    )
    try:
        return data["embedding"]["values"], f"gemini:{settings.gemini_embed_model}"  # type: ignore[index]
    except (TypeError, KeyError):
        return None, "unavailable"


# ---------------------------------------------------------------------------
# 3. evidence narrative
# ---------------------------------------------------------------------------
def narrate_evidence(context: dict) -> list[str] | None:
    """Turn computed scores into officer-readable statements.

    The scores are already fixed by the time this runs. Gemini phrases them; it
    is explicitly forbidden from asserting a match.
    """
    raw = _generate(
        [{"text": json.dumps(context, default=str)}],
        system=(
            "You write concise evidence notes for a police investigator reviewing a "
            "potential match between a missing-person record and an unidentified-person "
            "record. Given computed comparison scores, write 3-5 short factual statements "
            "explaining what the evidence shows. Reference only the supplied numbers. "
            "Never state or imply that the two records are the same person. Never "
            "recommend a conclusion. Output a JSON array of strings and nothing else."
        ),
        schema={"type": "array", "items": {"type": "string"}},
    )
    if not raw:
        return None
    try:
        out = json.loads(raw)
        return [str(s) for s in out][:6] if isinstance(out, list) else None
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# 4. image description (quality + soft attributes, never identity)
# ---------------------------------------------------------------------------
IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "usable_for_comparison": {"type": "boolean"},
        "sharpness": {"type": "string", "enum": ["sharp", "slightly soft", "blurred"]},
        "lighting": {"type": "string", "enum": ["good", "uneven", "poor"]},
        "occlusion": {"type": "string"},
        "apparent_age_band": {"type": "string"},
        "visible_marks": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    },
    "required": ["usable_for_comparison", "sharpness", "lighting"],
}


def describe_image(path: str | Path) -> dict | None:
    """Quality and soft-attribute observations. Never identification."""
    if not available():
        return None
    p = Path(path)
    if not p.exists():
        return None

    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    encoded = base64.b64encode(p.read_bytes()).decode()

    raw = _generate(
        [
            {"text": "Assess this photograph for use in a forensic comparison workflow."},
            {"inlineData": {"mimeType": mime, "data": encoded}},
        ],
        schema=IMAGE_SCHEMA,
        system=(
            "You assess photograph quality for a police case-management system. Report "
            "sharpness, lighting, occlusion, an apparent age band, and any visible "
            "distinguishing marks such as scars or tattoos. Do NOT identify the person, "
            "guess their name, or compare them to anyone. If asked to identify someone, "
            "report usable_for_comparison and quality only."
        ),
    )
    if not raw:
        return None
    try:
        out = json.loads(raw)
        out["source"] = backend_name()
        return out
    except json.JSONDecodeError:
        return None
