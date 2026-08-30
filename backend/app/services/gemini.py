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
import re
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger(__name__)

CHAT, EMBED = "chat", "embed"

# One retry is enough to step past a retired model or an unsupported field
# without turning a single embedding into an unbounded walk of the catalogue.
MAX_MODEL_ATTEMPTS = 3

# Substrings that disqualify a model outright for our two uses.
_CHAT_EXCLUDE = ("embedding", "aqa", "tts", "image-generation", "imagen", "veo")
_DOWNRANK = ("preview", "exp", "-exp-", "thinking", "-lite", "-8b", "learnlm")

_VERSION = re.compile(r"(\d+)(?:\.(\d+))?")


def _rank(name: str, kind: str) -> tuple:
    """Score a model for substitution. Higher is preferred.

    The ordering that matters: never pick something that cannot do the job;
    prefer a stable release over a preview; then prefer the same *tier* as was
    asked for — flash over pro — before preferring a newer version. Tier
    outranks version deliberately. Substituting a pro model for a withdrawn
    flash one would quietly multiply the cost and burn a free-tier quota during
    a demo; a version behind is a far smaller surprise than a bill. Ties break
    on the shorter name, which is Google's convention for the canonical alias.
    """
    if kind == CHAT and any(bad in name for bad in _CHAT_EXCLUDE):
        return (-1,)
    if kind == EMBED and "embedding" not in name and "embed" not in name:
        return (-1,)

    stable = 0 if any(flag in name for flag in _DOWNRANK) else 1

    match = _VERSION.search(name)
    version = float(f"{match.group(1)}.{match.group(2) or 0}") if match else 0.0

    tier = 2 if "flash" in name else 1 if "pro" in name else 0
    return (stable, tier, version, -len(name))


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
        self.pin_models = settings.gemini_pin_models

        # Model negotiation state. Populated lazily on the first call so that
        # constructing a provider stays free and offline-safe.
        self._catalogue: dict[str, set[str]] | None = None
        self._chosen: dict[str, str | None] = {}
        self._unusable: set[str] = set()
        self._bare_payload: set[str] = set()
        self._confirmed: set[str] = set()

    # -- capability ------------------------------------------------------
    def available(self) -> bool:
        return bool(self._api_key)

    def embedding_model_name(self) -> str:
        return f"gemini:{self.resolve(EMBED) or self.embed_model}"

    def chat_model_name(self) -> str:
        return f"gemini:{self.resolve(CHAT) or self.model}"

    def verified(self, kind: str = CHAT) -> bool:
        """Whether a real call has succeeded on the model now selected.

        Being listed by ListModels is not the same as being callable — a model
        can be advertised to the key and still answer 404 on use. Before a demo
        this distinction is the whole question, so it is reported rather than
        glossed: "configured" means a key is set, "verified" means it worked.
        """
        chosen = self.resolve(kind)
        return bool(chosen and chosen in self._confirmed)

    def status(self) -> dict:
        return {
            "configured": self.available(),
            "chat_model": self.resolve(CHAT) if self.available() else None,
            "embed_model": self.resolve(EMBED) if self.available() else None,
            "chat_verified": self.verified(CHAT),
            "embed_verified": self.verified(EMBED),
            "substituted": {
                kind: chosen
                for kind, configured in ((CHAT, self.model), (EMBED, self.embed_model))
                if (chosen := self.resolve(kind)) and chosen != configured
            } if self.available() else {},
        }

    def __repr__(self) -> str:                                # pragma: no cover
        return f"<GeminiProvider model={self.model} configured={self.available()}>"

    # -- model negotiation -----------------------------------------------
    def catalogue(self, *, refresh: bool = False) -> dict[str, set[str]]:
        """What this key can actually reach: ``{model_id: {methods}}``.

        Cached for the life of the provider. An empty dict means the call
        failed, which is treated as "unknown" rather than "nothing available" —
        the configured names are then tried directly.
        """
        if self._catalogue is not None and not refresh:
            return self._catalogue

        if not self.available():
            self._catalogue = {}
            return self._catalogue

        found: dict[str, set[str]] = {}
        page_token, pages = None, 0
        while pages < 5:                                  # bounded; ~250 models
            params = {"pageSize": 50}
            if page_token:
                params["pageToken"] = page_token
            data = self._get("models", params)
            if not data:
                break
            for entry in data.get("models", []):
                name = str(entry.get("name", "")).removeprefix("models/")
                if name:
                    found[name] = set(entry.get("supportedGenerationMethods", []))
            page_token = data.get("nextPageToken")
            pages += 1
            if not page_token:
                break

        # A failed listing is cached as "unknown", not as "nothing available":
        # leaving it uncached lets a later call retry after a transient outage,
        # which matters because retirement fallback needs this list to work.
        if found:
            self._catalogue = found
        return found

    def resolve(self, kind: str) -> str | None:
        """Pick a usable model for ``kind``, preferring the configured name.

        Google retires model IDs on its own schedule. Rather than fail when the
        configured name has been withdrawn, ask the key what it can reach and
        take the nearest equivalent — logging the substitution loudly, because
        silently switching models is how a demo produces different numbers than
        the one that was tested.
        """
        if kind in self._chosen:
            return self._chosen[kind]

        method = "embedContent" if kind == EMBED else "generateContent"
        preferred = self.embed_model if kind == EMBED else self.model

        catalogue = self.catalogue()
        usable = {name for name, methods in catalogue.items()
                  if method in methods and name not in self._unusable}

        chosen: str | None
        if preferred not in self._unusable and (preferred in usable or not catalogue):
            # Either it is listed, or the catalogue is unavailable and the
            # configured name deserves the benefit of the doubt.
            chosen = preferred
        elif self.pin_models:
            log.error("Gemini model %s is unavailable and CASEINTEL_GEMINI_PIN_MODELS "
                      "is set, so no substitute will be used.", preferred)
            chosen = None
        else:
            ranked = sorted(usable, key=lambda n: _rank(n, kind), reverse=True)
            chosen = ranked[0] if ranked else None
            if chosen:
                setting = "CASEINTEL_GEMINI_EMBED_MODEL" if kind == EMBED else "CASEINTEL_GEMINI_MODEL"
                log.warning("Gemini model %s is unavailable to this key; using %s instead. "
                            "Set %s=%s in backend/.env to make this explicit.",
                            preferred, chosen, setting, chosen)
            else:
                log.error("No Gemini model supporting %s is available to this key.", method)

        self._chosen[kind] = chosen
        return chosen

    def _retire(self, kind: str, model: str) -> None:
        """Mark a model unusable and force the next call to re-resolve.

        ListModels is not authoritative: a model can be listed and still answer
        404 ("no longer available to new users") when called. Only the call
        itself proves reachability.
        """
        self._unusable.add(model)
        self._chosen.pop(kind, None)

    # -- transport -------------------------------------------------------
    def _get(self, path: str, params: dict | None = None) -> dict | None:
        return self._request("GET", path, params=params)[0]

    def _post(self, path: str, payload: dict) -> dict | None:
        return self._request("POST", path, json=payload)[0]

    def _request(self, method: str, path: str, *, json: dict | None = None,
                 params: dict | None = None) -> tuple[dict | None, int | None]:
        """One HTTP call. Returns ``(body, status)``; never raises.

        Distinguishing the failure modes matters operationally — a 429 means
        back off, a 401 means the key is wrong, a 404 means the model name has
        been retired, a timeout means try later — so they are logged
        differently even though they all degrade the same way. The status is
        returned so callers can react (retire a model, drop an unsupported
        field) rather than merely give up.
        """
        if not self.available():
            return None, None

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(
                    method, f"{self.base_url}/{path}",
                    json=json, params=params,
                    headers={"x-goog-api-key": self._api_key},
                )
        except httpx.TimeoutException:
            log.warning("Gemini timed out after %.1fs on %s", self.timeout, path)
            return None, None
        except httpx.HTTPError as exc:
            log.warning("Gemini transport error on %s: %s", path, exc)
            return None, None

        status = response.status_code
        if status == 429:
            log.warning("Gemini quota or rate limit hit on %s — falling back", path)
            return None, status
        if status in (401, 403):
            log.error("Gemini rejected the API key (HTTP %d). Check CASEINTEL_GEMINI_API_KEY.",
                      status)
            return None, status
        if status >= 400:
            log.warning("Gemini returned HTTP %d on %s: %s", status, path, response.text[:200])
            return None, status

        try:
            return response.json(), status
        except ValueError:
            log.warning("Gemini returned a non-JSON body on %s", path)
            return None, status

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

        data = None
        for _ in range(MAX_MODEL_ATTEMPTS):
            model = self.resolve(CHAT)
            if not model:
                return None
            data, status = self._request(
                "POST", f"models/{model}:generateContent", json=payload)
            if data:
                self._confirmed.add(model)
                break
            if status == 404:
                # Listed but closed to this key. Retire it and try the next.
                self._retire(CHAT, model)
                continue
            return None

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
        data = None
        for _ in range(MAX_MODEL_ATTEMPTS):
            model = self.resolve(EMBED)
            if not model:
                return None

            payload: dict[str, Any] = {
                "model": f"models/{model}",
                "content": {"parts": [{"text": text}]},
            }
            # gemini-embedding-001 takes taskType and outputDimensionality and
            # is measurably better with them; the gemini-embedding-2 family
            # dropped taskType and rejects the request outright. Send the
            # optional fields, and learn per model when to stop.
            if model not in self._bare_payload:
                payload["taskType"] = "SEMANTIC_SIMILARITY"
                if settings.gemini_embed_dim:
                    payload["outputDimensionality"] = settings.gemini_embed_dim

            data, status = self._request(
                "POST", f"models/{model}:embedContent", json=payload)
            if data:
                self._confirmed.add(model)
                break
            if status == 404:
                self._retire(EMBED, model)
                continue
            if status == 400 and model not in self._bare_payload:
                # A rejected optional field is not a dead model. Drop the
                # extras and try this same model once more.
                log.info("Gemini embedding model %s rejected the optional fields; "
                         "retrying with a bare request", model)
                self._bare_payload.add(model)
                continue
            return None

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
            out["source"] = self.chat_model_name()
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
    """Re-read configuration and drop negotiation state — used by tests.

    Also resets the NlpClient, which holds a reference to the provider that is
    being discarded.
    """
    global _provider
    _provider = None

    from app.services.nlp import reset_client
    reset_client()


def available() -> bool:
    return get_provider().available()


def backend_name() -> str:
    p = get_provider()
    return p.chat_model_name() if p.available() else "local-rules"


def describe_image(path: str | Path) -> dict | None:
    return get_provider().describe_image(path)


def narrate_evidence(context: dict) -> list[str] | None:
    return get_provider().narrate_evidence(context)
