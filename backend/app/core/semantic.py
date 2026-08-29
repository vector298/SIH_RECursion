"""Semantic comparison of identification-mark descriptions.

Two officers rarely describe the same scar the same way:

    "3 cm horizontal scar above the left eyebrow"
    "small linear scar just over the left eyebrow"

String equality scores those at zero, which throws away the single most
discriminative piece of evidence in the whole record. So descriptions are
embedded and compared by cosine similarity.

Embedding backends, in order of preference:

1. Gemini ``text-embedding-004`` — when an API key is configured.
2. ``sentence-transformers`` — when installed locally.
3. A domain-normalised lexical vector — always available. It canonicalises the
   vocabulary of this domain (brow→eyebrow, mole→birthmark, horizontal→linear)
   and weights rare terms above common ones, so the two descriptions above
   score highly without any model download.

On top of embedding similarity, structured fields (side, body location, size)
are compared directly. Side disagreement is a genuine negative signal: a
left-eyebrow scar and a right-eyebrow scar are evidence *against*, not merely
absence of evidence, so it is penalised rather than ignored.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter

from app.core.arcface import cosine_similarity
from app.services import gemini

log = logging.getLogger(__name__)

# Domain vocabulary canonicalisation.
SYNONYMS: dict[str, str] = {
    "brow": "eyebrow", "brows": "eyebrow", "eyebrows": "eyebrow", "supraorbital": "eyebrow",
    "mole": "birthmark", "naevus": "birthmark", "nevus": "birthmark", "patch": "birthmark",
    "ink": "tattoo", "tattooed": "tattoo", "tattoos": "tattoo",
    "scarring": "scar", "cicatrix": "scar", "scars": "scar", "stitches": "scar", "suture": "scar",
    "horizontal": "linear", "straight": "linear", "line": "linear", "streak": "linear",
    "crescent": "curved", "arc": "curved", "arced": "curved", "curving": "curved",
    "elliptical": "oval", "ellipse": "oval",
    "round": "circular", "circle": "circular", "rounded": "circular",
    "arm": "forearm", "forearms": "forearm",
    "nape": "neck", "throat": "neck",
    "belly": "abdomen", "stomach": "abdomen", "tummy": "abdomen",
    "cheekbone": "cheek", "temple": "forehead",
    "above": "over", "atop": "over", "upon": "over",
    "small": "minor", "tiny": "minor", "little": "minor", "slight": "minor",
    "large": "major", "big": "major", "prominent": "major",
    "faded": "faint", "pale": "faint", "light": "faint",
    "coloured": "colour", "colored": "colour", "color": "colour",
}

STOPWORDS = {
    "a", "an", "the", "of", "on", "in", "at", "to", "and", "or", "with", "just",
    "is", "was", "has", "have", "there", "his", "her", "their", "its", "approximately",
    "approx", "about", "around", "some", "very", "quite", "near", "by",
}

# Terms that carry little discriminative power because nearly every record has them.
LOW_INFORMATION = {"scar", "tattoo", "birthmark", "mark", "feature", "cm", "mm"}


def normalise(text: str) -> list[str]:
    tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?", (text or "").lower())
    out: list[str] = []
    for tok in tokens:
        tok = SYNONYMS.get(tok, tok)
        if tok in STOPWORDS:
            continue
        out.append(tok)
    return out


def lexical_vector(text: str) -> Counter:
    """Term-frequency vector with domain weighting."""
    vec: Counter = Counter()
    tokens = normalise(text)
    for tok in tokens:
        vec[tok] += 0.35 if tok in LOW_INFORMATION else 1.0
    # Adjacent pairs capture "left eyebrow" vs "left forearm".
    for a, b in zip(tokens, tokens[1:]):
        vec[f"{a}_{b}"] += 0.6
    return vec


def lexical_similarity(a: str, b: str) -> float:
    va, vb = lexical_vector(a), lexical_vector(b)
    if not va or not vb:
        return 0.0
    shared = set(va) & set(vb)
    dot = sum(va[t] * vb[t] for t in shared)
    na = math.sqrt(sum(v * v for v in va.values()))
    nb = math.sqrt(sum(v * v for v in vb.values()))
    return float(dot / (na * nb)) if na and nb else 0.0


# ---------------------------------------------------------------------------
# embedding backends
# ---------------------------------------------------------------------------
_st_model = None
_st_tried = False


def _sentence_transformer():
    global _st_model, _st_tried
    if _st_tried:
        return _st_model
    _st_tried = True
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        _st_model = SentenceTransformer("all-MiniLM-L6-v2")
        log.info("sentence-transformers loaded for semantic matching")
    except Exception as exc:
        log.info("sentence-transformers unavailable (%s) — using lexical backend", exc)
        _st_model = None
    return _st_model


def embed(text: str) -> tuple[list[float] | None, str]:
    """Embed a description. Returns (vector, backend). Vector may be None when
    only the lexical backend is available — comparison then happens directly."""
    vec, backend = gemini.embed_text(text)
    if vec:
        return vec, backend

    model = _sentence_transformer()
    if model is not None:                                     # pragma: no cover
        try:
            return model.encode(text, normalize_embeddings=True).tolist(), "sentence-transformers:all-MiniLM-L6-v2"
        except Exception:
            pass

    return None, "lexical-domain-v1"


def backend_name() -> str:
    if gemini.available():
        return f"gemini:{gemini.settings.gemini_embed_model}"
    return "sentence-transformers:all-MiniLM-L6-v2" if _sentence_transformer() else "lexical-domain-v1"


def text_similarity(a: str, b: str, vec_a: list[float] | None = None, vec_b: list[float] | None = None) -> float:
    """Similarity in [0, 1] between two free-text descriptions."""
    if vec_a and vec_b and len(vec_a) == len(vec_b):
        # Cosine on embeddings sits in [-1, 1]; map to [0, 1].
        return float(max(0.0, (cosine_similarity(vec_a, vec_b) + 1.0) / 2.0))
    return lexical_similarity(a, b)


# ---------------------------------------------------------------------------
# mark-level comparison
# ---------------------------------------------------------------------------
def _size_similarity(a_cm: float | None, b_cm: float | None) -> float | None:
    if a_cm is None or b_cm is None:
        return None
    if a_cm <= 0 or b_cm <= 0:
        return None
    ratio = min(a_cm, b_cm) / max(a_cm, b_cm)
    return float(ratio ** 0.6)


def compare_marks(probe_marks: list, candidate_marks: list) -> tuple[float | None, list[dict]]:
    """Best-match pairing between two sets of identification marks.

    Each probe mark is scored against its best candidate counterpart. The
    overall score is the mean of those best matches, so a probe with three
    recorded marks needs broad agreement rather than one lucky hit.
    """
    if not probe_marks or not candidate_marks:
        return None, []

    pairings: list[dict] = []
    for pm in probe_marks:
        best: dict | None = None
        for cm in candidate_marks:
            text = text_similarity(
                pm.description or "", cm.description or "",
                pm.embedding, cm.embedding,
            )

            parts: list[tuple[float, float]] = [(text, 0.55)]

            if pm.kind and cm.kind:
                parts.append((1.0 if pm.kind.lower() == cm.kind.lower() else 0.15, 0.15))
            if pm.body_location and cm.body_location:
                parts.append((1.0 if pm.body_location.lower() == cm.body_location.lower() else 0.1, 0.15))

            side_penalty = 0.0
            if pm.side and cm.side and pm.side not in ("Not recorded",) and cm.side not in ("Not recorded",):
                if pm.side.lower() == cm.side.lower():
                    parts.append((1.0, 0.10))
                else:
                    # Genuine counter-evidence, not merely a missing field.
                    parts.append((0.0, 0.10))
                    side_penalty = 0.25

            size = _size_similarity(pm.size_cm, cm.size_cm)
            if size is not None:
                parts.append((size, 0.05))

            total_w = sum(w for _, w in parts)
            score = sum(s * w for s, w in parts) / total_w if total_w else 0.0
            score = max(0.0, score - side_penalty)

            if best is None or score > best["score"]:
                best = {
                    "probe_mark": pm.description,
                    "candidate_mark": cm.description,
                    "score": round(score, 4),
                    "text_similarity": round(text, 4),
                    "side_conflict": side_penalty > 0,
                }
        if best:
            pairings.append(best)

    if not pairings:
        return None, []

    overall = sum(p["score"] for p in pairings) / len(pairings)
    return float(max(0.0, min(1.0, overall))), pairings
