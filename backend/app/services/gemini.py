"""Gemini provider — the only file that knows Gemini's wire format.

Everything else talks to ``NlpClient`` (``app/services/nlp.py``). Replacing
Gemini means writing another class with ``available`` / ``structured`` /
``embed`` and passing it to ``NlpClient``; no other file changes.

Gemini's remit here is language work:

* structured extraction from an officer's free text,
* text embeddings for semantic comparison of identification marks,
* plain-English narration of scores the deterministic pipeline already computed,
* image quality and *soft* attribute observations.

It is deliberately not used for face identification. Gemini exposes no
face-embedding endpoint, and identifying individuals from photographs is outside
its acceptable-use policy. Identity comparison is ArcFace's job
(``app/services/face.py``), and candidate scoring is the matching engine's.

The API key is read from configuration only — never hard-coded, never logged.
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger(__name__)


class GeminiProvider:
    """Implements ``nlp.LlmProvider`` over the Gemini REST API."""

    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 embed_model: str | None = None) -> None:
        self._api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.embed_model = embed_model or settings.gemini_embed_model
        self.base_url = settings.gemini_base_url.rstrip("/")
        self.timeout = settings.gemini_timeout_s

    # -- capability ------------------------------------------------------
    def available(self) -> bool:
        return bool(self._api_key)

    def embedding_model_name(self) -> str:
        return f"gemini:{self.embed_model}"

    def __repr__(self) -> str:                                # pragma: no cover
        return f"<GeminiProvider model={self.model} configured={self.available()}>"

    # -- transport -------------------------------------------------------
    def _post(self, path: str, payload: dict) -> dict | None:
        """One HTTP call. Returns None on any failure; never raises.

        Distinguishing the failure modes matters operationally — a 429 means
        back off, a 401 means the key is wrong, a timeout means try later — so
        they are logged differently even though they all degrade the same way.
        """
        if not self.available():
            return None

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/{path}",
                    json=payload,
                    headers={"x-goog-api-key": self._api_key},
                )
        except httpx.TimeoutException:
            log.warning("Gemini timed out after %.1fs on %s", self.timeout, path)
            return None
        except httpx.HTTPError as exc:
            log.warning("Gemini transport error on %s: %s", path, exc)
            return None

        if response.status_code == 429:
            log.warning("Gemini quota or rate limit hit on %s — falling back", path)
            return None
        if response.status_code in (401, 403):
            log.error("Gemini rejected the API key (HTTP %d). Check CASEINTEL_GEMINI_API_KEY.",
                      response.status_code)
            return None
        if response.status_code >= 400:
            log.warning("Gemini returned HTTP %d on %s: %s",
                        response.status_code, path, response.text[:200])
            return None

        try:
            return response.json()
        except ValueError:
            log.warning("Gemini returned a non-JSON body on %s", path)
            return None

    def _generate(self, parts: list[dict], *, schema: dict | None = None,
                  system: str | None = None, temperature: float = 0.1) -> str | None:
        payload: dict[str, Any] = {"contents": [{"parts": parts}]}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        payload["generationConfig"] = (
            {"responseMimeType": "application/json", "responseSchema": schema,
             "temperature": temperature}
            if schema else {"temperature": temperature}
        )

        data = self._post(f"models/{self.model}:generateContent", payload)
        if not data:
            return None

        try:
            candidate = data["candidates"][0]
            if candidate.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT"):
                log.warning("Gemini refused the request (finishReason=%s)",
                            candidate.get("finishReason"))
                return None
            return candidate["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            log.warning("Unexpected Gemini response shape: %s", str(data)[:200])
            return None

    # -- LlmProvider -----------------------------------------------------
    def structured(self, text: str, *, schema: dict, system: str) -> dict | None:
        raw = self._generate(
            [{"text": f"Description to extract from:\n\n{text}"}],
            schema=schema, system=system,
        )
        if raw is None:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Gemini returned malformed JSON despite a response schema")
            return None
        return parsed if isinstance(parsed, dict) else None

    def embed(self, text: str) -> list[float] | None:
        data = self._post(
            f"models/{self.embed_model}:embedContent",
            {
                "model": f"models/{self.embed_model}",
                "content": {"parts": [{"text": text}]},
                "taskType": "SEMANTIC_SIMILARITY",
            },
        )
        try:
            values = data["embedding"]["values"]              # type: ignore[index]
        except (TypeError, KeyError):
            return None
        return values if isinstance(values, list) and values else None

    # -- extras used elsewhere in the app --------------------------------
    def narrate_evidence(self, context: dict) -> list[str] | None:
        """Phrase already-computed scores. Cannot change a ranking."""
        raw = self._generate(
            [{"text": json.dumps(context, default=str)}],
            schema={"type": "array", "items": {"type": "string"}},
            system=(
                "You write concise evidence notes for a police investigator reviewing a "
                "potential match between a missing-person record and an unidentified-person "
                "record. Given comparison scores that have ALREADY been computed, write 3-5 "
                "short factual statements describing what the evidence shows. Reference only "
                "the supplied numbers. Never state or imply the records are the same person. "
                "Never recommend a conclusion. Output a JSON array of strings, nothing else."
            ),
            temperature=0.3,
        )
        if not raw:
            return None
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return [str(s) for s in out][:6] if isinstance(out, list) else None

    def describe_image(self, path: str | Path) -> dict | None:
        """Quality and soft attributes only — never identification."""
        p = Path(path)
        if not self.available() or not p.exists():
            return None
        try:
            encoded = base64.b64encode(p.read_bytes()).decode()
        except OSError as exc:
            log.warning("Could not read image for description: %s", exc)
            return None

        raw = self._generate(
            [
                {"text": "Assess this photograph for use in a forensic comparison workflow."},
                {"inlineData": {"mimeType": mimetypes.guess_type(p.name)[0] or "image/jpeg",
                                "data": encoded}},
            ],
            schema={
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
            },
            system=(
                "You assess photograph quality for a police case-management system. Report "
                "sharpness, lighting, occlusion, an apparent age band, and any visible "
                "distinguishing marks such as scars or tattoos. Do NOT identify the person, "
                "guess their name, or compare them to anyone."
            ),
        )
        if not raw:
            return None
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(out, dict):
            out["source"] = f"gemini:{self.model}"
            return out
        return None


# ---------------------------------------------------------------------------
# Convenience wrappers for the rest of the app
# ---------------------------------------------------------------------------
_provider: GeminiProvider | None = None


def get_provider() -> GeminiProvider:
    global _provider
    if _provider is None:
        _provider = GeminiProvider()
    return _provider


def reset_provider() -> None:
    """Re-read configuration — used by tests."""
    global _provider
    _provider = None


def available() -> bool:
    return get_provider().available()


def backend_name() -> str:
    p = get_provider()
    return f"gemini:{p.model}" if p.available() else "local-rules"


def describe_image(path: str | Path) -> dict | None:
    return get_provider().describe_image(path)


def narrate_evidence(context: dict) -> list[str] | None:
    return get_provider().narrate_evidence(context)
