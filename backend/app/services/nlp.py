"""NlpClient — the only part of the system that knows an LLM exists.

The matching engine never imports Gemini. It asks this client for three things:

    extract_features(text)          free text -> validated ExtractedFeatures
    generate_embedding(text)        text      -> vector (or None)
    semantic_similarity(a, b)       two texts -> score in [0, 1]

Swapping Gemini for another provider means writing one class that satisfies
``LlmProvider``; nothing in ``core/`` changes.

**Failure is normal, not exceptional.** A missing key, a timeout, a quota
rejection, a 500, or JSON that does not satisfy the Pydantic contract all resolve
to the same thing: log it, mark the result degraded, and return deterministic
output so the request completes. No method here raises into the matching path —
an NLP outage must never take down a search.

**What the model is not allowed to do.** It extracts and it embeds. It never
scores a candidate, ranks anything, or asserts that two records are the same
person. That decision belongs to ``core/pipeline.py`` and, ultimately, to the
officer.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from app.services.nlp_schemas import (
    EXTRACTION_SYSTEM_PROMPT, GEMINI_EXTRACTION_SCHEMA, ExtractedFeatures, ExtractedMark,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------
@runtime_checkable
class LlmProvider(Protocol):
    """What NlpClient needs from a language-model backend."""

    name: str

    def available(self) -> bool: ...
    def structured(self, text: str, *, schema: dict, system: str) -> dict | None: ...
    def embed(self, text: str) -> list[float] | None: ...


class NullProvider:
    """Used when nothing is configured. Every call politely returns nothing."""

    name = "none"

    def available(self) -> bool:
        return False

    def structured(self, text: str, *, schema: dict, system: str) -> dict | None:
        return None

    def embed(self, text: str) -> list[float] | None:
        return None


# ---------------------------------------------------------------------------
# Deterministic fallback extraction
# ---------------------------------------------------------------------------
BODY_PARTS = [
    "eyebrow", "brow", "forehead", "temple", "cheek", "chin", "jaw", "nose", "lip",
    "ear", "earlobe", "neck", "nape", "throat", "shoulder", "collarbone", "chest",
    "back", "abdomen", "stomach", "torso", "upper arm", "forearm", "elbow", "wrist",
    "hand", "palm", "finger", "thumb", "hip", "thigh", "knee", "shin", "calf",
    "ankle", "foot", "toe", "scalp", "head",
]

MARK_KEYWORDS = {
    "scar": "scar", "scarring": "scar", "stitches": "scar", "surgical": "scar", "cicatrix": "scar",
    "tattoo": "tattoo", "tattooed": "tattoo", "ink": "tattoo",
    "birthmark": "birthmark", "birth mark": "birthmark", "mole": "birthmark",
    "naevus": "birthmark", "nevus": "birthmark", "patch": "birthmark",
    "piercing": "piercing", "pierced": "piercing", "stud": "piercing",
    "amputation": "amputation", "amputated": "amputation", "missing finger": "amputation",
    "deformity": "deformity", "disfigured": "deformity",
}

SHAPE_WORDS = {
    "linear": "Linear", "horizontal": "Linear", "straight": "Linear", "line": "Linear",
    "long": "Linear", "curved": "Curved", "crescent": "Curved", "oval": "Oval",
    "elliptical": "Oval", "circular": "Circular", "round": "Circular",
    "irregular": "Irregular", "jagged": "Irregular", "star": "Pictorial",
    "anchor": "Pictorial", "heart": "Pictorial", "cross": "Pictorial",
    "script": "Script", "lettering": "Script", "name": "Script", "word": "Script",
}

SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(cm|centimet(?:er|re)s?|mm|millimet(?:er|re)s?|in(?:ch(?:es)?)?)",
    re.IGNORECASE,
)
CLOTHING_RE = re.compile(r"\b(?:wearing|dressed in|clothed in|had on)\b(.{3,120})", re.IGNORECASE)

# Clause boundaries — a single sentence routinely contains several marks
# ("a scar above his left eyebrow and a tattoo on his right forearm").
CLAUSE_SPLIT = re.compile(r"(?:\.|;|\band also\b|\band\b|\bplus\b|,\s*(?=(?:a|an|the)\b))", re.IGNORECASE)


def _size_to_cm(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit.startswith(("mm", "millimet")):
        return value / 10.0
    if unit.startswith("in"):
        return value * 2.54
    return value


def heuristic_extract(text: str) -> ExtractedFeatures:
    """Rule-based extraction. Always available, never raises.

    Deliberately conservative: it would rather miss a detail than invent one,
    because a fabricated identification mark is worse than an absent one.
    """
    features = ExtractedFeatures(source="rules", degraded=True)
    if not (text or "").strip():
        return features

    for match in CLOTHING_RE.finditer(text):
        item = match.group(1).strip(" .,;")
        if item:
            features.clothing.append(item)

    for raw_clause in CLAUSE_SPLIT.split(text):
        clause = (raw_clause or "").strip(" .,;\n")
        if len(clause) < 3:
            continue
        lowered = clause.lower()

        kind = next(
            (v for k, v in sorted(MARK_KEYWORDS.items(), key=lambda kv: -len(kv[0])) if k in lowered),
            None,
        )
        if kind is None:
            continue

        location = next(
            (p for p in sorted(BODY_PARTS, key=len, reverse=True) if p in lowered), None
        )
        if location == "brow":
            location = "eyebrow"

        if re.search(r"\bleft\b", lowered):
            side = "left"
        elif re.search(r"\bright\b", lowered):
            side = "right"
        elif re.search(r"\bnape\b|\bback\b|\bbehind\b", lowered):
            side = "back"
        elif re.search(r"\bcentre\b|\bcenter\b|\bmiddle\b", lowered):
            side = "centre"
        else:
            side = "unknown"

        size_text, size_cm = None, None
        if (m := SIZE_RE.search(clause)):
            size_text = f"{float(m.group(1)):g} {m.group(2).lower()}"
            size_cm = round(_size_to_cm(float(m.group(1)), m.group(2)), 2)

        shape = next((v for k, v in SHAPE_WORDS.items() if re.search(rf"\b{k}", lowered)), None)

        attributes = [
            word for word in ("faded", "raised", "healed", "fresh", "old", "large",
                              "small", "prominent", "faint", "dark", "pale")
            if re.search(rf"\b{word}\b", lowered)
        ]

        try:
            features.marks.append(ExtractedMark(
                type=kind, description=clause[:400], location=location, side=side,
                size_text=size_text, size_cm=size_cm, shape=shape,
                attributes=attributes, confidence=0.55,
            ))
        except ValidationError:                                # pragma: no cover
            log.debug("heuristic produced an invalid mark for clause: %r", clause[:80])

    return features


# ---------------------------------------------------------------------------
# Lexical similarity fallback
# ---------------------------------------------------------------------------
SYNONYMS = {
    "brow": "eyebrow", "brows": "eyebrow", "eyebrows": "eyebrow",
    "mole": "birthmark", "naevus": "birthmark", "nevus": "birthmark",
    "ink": "tattoo", "tattooed": "tattoo", "tattoos": "tattoo",
    "scarring": "scar", "scars": "scar", "cicatrix": "scar",
    "horizontal": "linear", "straight": "linear", "line": "linear", "long": "linear",
    "crescent": "curved", "elliptical": "oval", "round": "circular", "circle": "circular",
    "arm": "forearm", "forearms": "forearm", "nape": "neck",
    "five-pointed": "star", "fivepointed": "star", "resembling": "like",
    "above": "over", "atop": "over", "small": "minor", "large": "major",
    "faded": "faint", "approximately": "about", "approx": "about",
}
STOPWORDS = {
    "a", "an", "the", "of", "on", "in", "at", "to", "and", "or", "with", "just",
    "is", "was", "has", "have", "his", "her", "their", "its", "there", "person",
    "about", "some", "very", "quite", "near", "by", "that", "this", "it",
}
LOW_INFORMATION = {"scar", "tattoo", "birthmark", "mark", "feature", "cm", "mm"}


def normalise_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?", (text or "").lower())
    return [SYNONYMS.get(t, t) for t in tokens if SYNONYMS.get(t, t) not in STOPWORDS]


def lexical_similarity(a: str, b: str) -> float:
    """Domain-normalised bag-of-terms cosine. Deterministic, no network."""
    def vector(text: str) -> dict[str, float]:
        tokens = normalise_tokens(text)
        vec: dict[str, float] = {}
        for tok in tokens:
            vec[tok] = vec.get(tok, 0.0) + (0.35 if tok in LOW_INFORMATION else 1.0)
        for x, y in zip(tokens, tokens[1:]):
            key = f"{x}_{y}"
            vec[key] = vec.get(key, 0.0) + 0.6
        return vec

    va, vb = vector(a), vector(b)
    if not va or not vb:
        return 0.0
    dot = sum(va[t] * vb[t] for t in va.keys() & vb.keys())
    na = math.sqrt(sum(v * v for v in va.values()))
    nb = math.sqrt(sum(v * v for v in vb.values()))
    return float(dot / (na * nb)) if na and nb else 0.0


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return float(max(-1.0, min(1.0, dot / (na * nb))))


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------
@dataclass
class EmbeddingResult:
    vector: list[float] | None
    model: str
    degraded: bool = False


@dataclass
class SimilarityResult:
    score: float
    method: str
    degraded: bool = False
    detail: dict = field(default_factory=dict)


class NlpClient:
    """Provider-agnostic NLP façade. Construct once; it is stateless and cheap."""

    def __init__(self, provider: LlmProvider | None = None) -> None:
        if provider is None:
            # The shared instance, not a fresh one. A provider accumulates
            # negotiation state — which models this key can reach, which are
            # retired, which reject an optional field — and a second instance
            # would repeat the discovery calls and disagree with the first
            # about which model is live, so /api/health would describe a
            # different backend than the one actually answering requests.
            from app.services.gemini import get_provider
            provider = get_provider()
        self.provider = provider

    # -- health ----------------------------------------------------------
    @property
    def backend(self) -> str:
        return self.provider.name if self.provider.available() else "rules+lexical"

    def health(self) -> dict:
        return {
            "provider": self.provider.name,
            "available": self.provider.available(),
            "extraction": self.provider.name if self.provider.available() else "rules",
            "embeddings": self.provider.name if self.provider.available() else "lexical",
        }

    # -- 1. extraction ---------------------------------------------------
    def extract_features(self, text: str) -> ExtractedFeatures:
        """Free text -> validated structure. Never raises."""
        if not (text or "").strip():
            return ExtractedFeatures(source="empty")

        if not self.provider.available():
            return heuristic_extract(text)

        try:
            raw = self.provider.structured(
                text, schema=GEMINI_EXTRACTION_SCHEMA, system=EXTRACTION_SYSTEM_PROMPT
            )
        except Exception as exc:                              # noqa: BLE001 - provider may raise anything
            log.warning("NLP extraction call failed (%s: %s) — using rules", type(exc).__name__, exc)
            fallback = heuristic_extract(text)
            fallback.warnings.append(f"{self.provider.name} unavailable: {type(exc).__name__}")
            return fallback

        if raw is None:
            fallback = heuristic_extract(text)
            fallback.warnings.append(f"{self.provider.name} returned no result")
            return fallback

        try:
            features = ExtractedFeatures.model_validate(raw)
        except ValidationError as exc:
            # The model answered, but not in the shape we require. Trusting it
            # here is exactly how malformed data reaches the matching engine.
            log.warning("NLP output failed validation (%d error(s)) — using rules",
                        exc.error_count())
            fallback = heuristic_extract(text)
            fallback.warnings.append("model output failed schema validation")
            return fallback

        features.source = self.provider.name
        features.degraded = False

        if features.is_empty:
            # Nothing extracted: fall back rather than return a confident blank.
            rules = heuristic_extract(text)
            if not rules.is_empty:
                rules.warnings.append(f"{self.provider.name} returned nothing; rules found marks")
                return rules

        return features

    # -- 2. embeddings ---------------------------------------------------
    def generate_embedding(self, text: str) -> EmbeddingResult:
        """Text -> vector. Returns a null vector rather than raising."""
        if not (text or "").strip():
            return EmbeddingResult(None, "empty", degraded=True)

        if not self.provider.available():
            return EmbeddingResult(None, "lexical", degraded=True)

        try:
            vector = self.provider.embed(text)
        except Exception as exc:                              # noqa: BLE001
            log.warning("Embedding call failed (%s: %s) — comparison will use lexical",
                        type(exc).__name__, exc)
            return EmbeddingResult(None, "lexical", degraded=True)

        if not vector:
            return EmbeddingResult(None, "lexical", degraded=True)
        return EmbeddingResult(vector, self.provider.embedding_model_name(), degraded=False)

    # -- 3. similarity ---------------------------------------------------
    def semantic_similarity(
        self,
        text_a: str,
        text_b: str,
        *,
        vector_a: list[float] | None = None,
        vector_b: list[float] | None = None,
        model_a: str | None = None,
        model_b: str | None = None,
    ) -> SimilarityResult:
        """Similarity in [0, 1]. Uses stored vectors when supplied.

        Callers pass vectors that were computed when the records were written,
        so a match run does not re-embed the corpus. Only when a vector is
        missing does this reach for the provider, and only when that fails does
        it fall back to lexical comparison.

        **Vectors from different models are never compared.** Two embedding
        models place the same sentence in unrelated coordinate systems, so the
        cosine between them is noise wearing the costume of a similarity score —
        and when the dimensions happen to agree, nothing about the shape of the
        data reveals the mistake. Google's retirement of one embedding model in
        favour of another makes a mixed corpus the normal case, not an edge one,
        so a stored vector is trusted only alongside the name of the model that
        produced it. Mismatched pairs re-embed or fall back to lexical.
        """
        if not (text_a or "").strip() or not (text_b or "").strip():
            return SimilarityResult(0.0, "empty", degraded=True)

        comparable = _same_model(model_a, model_b)

        if comparable and vector_a and vector_b and len(vector_a) == len(vector_b):
            raw = cosine(vector_a, vector_b)
            # Embedding cosines live in [-1, 1]; map to [0, 1].
            return SimilarityResult(max(0.0, (raw + 1.0) / 2.0), "embedding",
                                    detail={"cosine": round(raw, 4)})

        if self.provider.available():
            current = self.provider.embedding_model_name()
            # Re-embed whatever does not already come from the live model.
            a = vector_a if (vector_a and _same_model(model_a, current)) else \
                self.generate_embedding(text_a).vector
            b = vector_b if (vector_b and _same_model(model_b, current)) else \
                self.generate_embedding(text_b).vector
            if a and b and len(a) == len(b):
                raw = cosine(a, b)
                return SimilarityResult(max(0.0, (raw + 1.0) / 2.0), "embedding",
                                        detail={"cosine": round(raw, 4)})

        return SimilarityResult(lexical_similarity(text_a, text_b), "lexical", degraded=True)


def _same_model(a: str | None, b: str | None) -> bool:
    """Whether two vectors may be compared.

    An unlabelled vector is treated as compatible: records written before the
    label existed would otherwise all fall back to lexical, which would be a
    silent quality regression across the whole corpus. Once a label is present
    on both sides it must match.
    """
    if not a or not b:
        return True
    return a.strip().lower() == b.strip().lower()


# Module-level default, so callers need not thread a client through every call.
_default_client: NlpClient | None = None


def get_client() -> NlpClient:
    global _default_client
    if _default_client is None:
        _default_client = NlpClient()
    return _default_client


def reset_client() -> None:
    """Drop the cached client — used by tests that swap providers."""
    global _default_client
    _default_client = None
