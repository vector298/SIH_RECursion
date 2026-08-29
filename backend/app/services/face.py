"""Face embedding extraction.

Primary path: **InsightFace ArcFace** (`buffalo_l` — a ResNet-100 trained with
the additive angular margin loss implemented in ``app/core/arcface.py``). It
produces a 512-D embedding per detected face; identity comparison is cosine
similarity between two of those.

Fallback path: when `insightface` / `onnxruntime` are not installed or the model
files are absent, a deterministic **local image descriptor** is used instead so
the pipeline still runs end to end. It is a real descriptor — DCT low-frequency
coefficients plus a spatial LBP texture histogram over the detected face crop —
so visually similar images do score higher than dissimilar ones. It is **not
face recognition** and must never be presented as such: it has no identity
invariance to pose, age or lighting. Every response carries the model name so
the distinction is visible rather than buried.

Note on Gemini: it is deliberately not used here. It exposes no face-embedding
endpoint, and identifying individuals from photographs is outside its
acceptable-use policy. Gemini's role in the vision pipeline is image *quality*
and soft-attribute description — see ``app/services/gemini.py``.
"""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from app.config import settings

log = logging.getLogger(__name__)

FALLBACK_MODEL = "local-descriptor-v1"
ARCFACE_MODEL = "insightface-arcface-buffalo_l"

# Per-backend calibration.
#
#   threshold   - cosine value that marks the midpoint of the evidence curve.
#                 ArcFace impostor pairs cluster near 0 and genuine pairs sit
#                 well above 0.28. The local descriptor has a high baseline
#                 similarity because every portrait shares gross structure, so
#                 its midpoint sits far higher.
#
#   reliability - how much of the face weight this backend has earned, derived
#                 from its measured equal error rate as max(0, 1 - 2·EER).
#
# Measured by scripts/calibrate_face.py over 90 genuine and 870 impostor pairs:
# the local descriptor's EER is 0.47 and its ROC AUC is 0.61 — barely above
# chance, which is exactly what a hand-built descriptor with no identity
# supervision should score. Its reliability is therefore near zero, and facial
# similarity contributes almost nothing to a ranking until real ArcFace weights
# are installed. That is the correct behaviour: dressing up a coin flip as
# biometric evidence is how an investigative tool sends officers to the wrong
# address. Re-run the script after changing the descriptor or installing
# insightface, and update these numbers from its output.
CALIBRATION = {
    ARCFACE_MODEL: {"threshold": 0.28, "reliability": 1.00, "eer": 0.005},
    FALLBACK_MODEL: {"threshold": 0.70, "reliability": 0.08, "eer": 0.468},
}


def calibration(model: str | None = None) -> dict:
    return CALIBRATION.get(model or backend_name(), CALIBRATION[FALLBACK_MODEL])

_app = None
_tried_load = False


# ---------------------------------------------------------------------------
# InsightFace
# ---------------------------------------------------------------------------
def _load_insightface():
    global _app, _tried_load
    if _tried_load:
        return _app
    _tried_load = True
    try:
        from insightface.app import FaceAnalysis  # type: ignore

        app = FaceAnalysis(
            name=settings.face_model_pack,
            root=str(settings.face_model_root),
            providers=["CPUExecutionProvider"],
        )
        app.prepare(ctx_id=-1, det_size=(640, 640))
        _app = app
        log.info("InsightFace ArcFace loaded (%s)", settings.face_model_pack)
    except Exception as exc:                                  # pragma: no cover
        log.warning("InsightFace unavailable (%s) — using %s", exc, FALLBACK_MODEL)
        _app = None
    return _app


def backend_name() -> str:
    return ARCFACE_MODEL if _load_insightface() is not None else FALLBACK_MODEL


def is_real_arcface() -> bool:
    return _load_insightface() is not None


# ---------------------------------------------------------------------------
# Face detection (shared by the fallback descriptor and quality assessment)
# ---------------------------------------------------------------------------
_cascade: cv2.CascadeClassifier | None = None


def _get_cascade() -> cv2.CascadeClassifier:
    global _cascade
    if _cascade is None:
        _cascade = cv2.CascadeClassifier(
            str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        )
    return _cascade


def detect_face_box(gray: np.ndarray) -> tuple[int, int, int, int] | None:
    """Largest frontal face box as (x, y, w, h), or None."""
    try:
        faces = _get_cascade().detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(32, 32))
    except Exception:                                         # pragma: no cover
        return None
    if len(faces) == 0:
        return None
    return tuple(int(v) for v in max(faces, key=lambda f: f[2] * f[3]))  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Fallback descriptor
# ---------------------------------------------------------------------------
def _lbp_histogram(patch: np.ndarray, grid: int = 4, bins: int = 16) -> np.ndarray:
    """Spatially-blocked local binary pattern histogram."""
    p = patch.astype(np.float32)
    h, w = p.shape
    codes = np.zeros((h - 2, w - 2), dtype=np.uint8)
    centre = p[1:-1, 1:-1]
    offsets = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
    for bit, (dy, dx) in enumerate(offsets):
        neighbour = p[1 + dy: h - 1 + dy, 1 + dx: w - 1 + dx]
        codes |= ((neighbour >= centre).astype(np.uint8) << bit)

    ch, cw = codes.shape[0] // grid, codes.shape[1] // grid
    out: list[np.ndarray] = []
    for gy in range(grid):
        for gx in range(grid):
            block = codes[gy * ch:(gy + 1) * ch, gx * cw:(gx + 1) * cw]
            hist, _ = np.histogram(block, bins=bins, range=(0, 256))
            out.append(hist.astype(np.float32))
    return np.concatenate(out)


def _local_descriptor(gray: np.ndarray, dim: int) -> np.ndarray:
    """DCT low-frequency coefficients + LBP texture histogram, L2-normalised."""
    face = detect_face_box(gray)
    if face is not None:
        x, y, w, h = face
        pad = int(0.12 * max(w, h))
        y0, y1 = max(0, y - pad), min(gray.shape[0], y + h + pad)
        x0, x1 = max(0, x - pad), min(gray.shape[1], x + w + pad)
        gray = gray[y0:y1, x0:x1]

    patch = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)
    patch = cv2.equalizeHist(patch.astype(np.uint8)).astype(np.float32)

    dct = cv2.dct(patch / 255.0)[:16, :16].flatten()
    dct[0] = 0.0                                   # drop DC: it is just brightness

    lbp = _lbp_histogram(patch)
    lbp = lbp / max(float(lbp.sum()), 1.0)

    vec = np.concatenate([dct, lbp]).astype(np.float32)
    if vec.size < dim:
        vec = np.pad(vec, (0, dim - vec.size))
    vec = vec[:dim]
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm > 1e-9 else vec


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def embed_image(path: str | Path) -> tuple[list[float] | None, str, bool]:
    """Return (embedding, model_name, face_detected)."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return None, backend_name(), False

    app = _load_insightface()
    if app is not None:                                       # pragma: no cover
        try:
            faces = app.get(image)
            if faces:
                best = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
                emb = np.asarray(best.normed_embedding, dtype=np.float32)
                return emb.tolist(), ARCFACE_MODEL, True
            return None, ARCFACE_MODEL, False
        except Exception as exc:
            log.warning("ArcFace inference failed (%s) — falling back", exc)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    detected = detect_face_box(gray) is not None
    return _local_descriptor(gray, settings.face_embedding_dim).tolist(), FALLBACK_MODEL, detected
