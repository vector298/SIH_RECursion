"""Image quality assessment.

Quality is not cosmetic here — it is the cap on how much facial similarity is
allowed to influence the ranking (see ``fusion.apply_quality_cap``). Four
measurable properties feed a single score:

* **Sharpness** — variance of the Laplacian. Low variance means few edges,
  which in a portrait means blur.
* **Exposure** — mean luminance, penalised as it drifts from mid-grey, plus
  contrast from the luminance spread.
* **Resolution** — the pixel area actually available *on the face*, not the
  file dimensions. A 4000×3000 photo of a crowd is a poor face image.
* **Face visibility** — face box area relative to the frame, and whether a
  face was detected at all.

Every sub-score is reported alongside the total so an officer can see which
property let the image down rather than being handed one opaque number.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.services.face import detect_face_box

WEIGHTS = {"sharpness": 0.34, "exposure": 0.18, "resolution": 0.24, "visibility": 0.24}


def _clamp01(v: float) -> float:
    return float(max(0.0, min(1.0, v)))


def _sharpness_score(gray: np.ndarray) -> tuple[float, float, float]:
    """Blur estimate that sensor noise cannot fake.

    Plain Laplacian variance is the textbook blur metric and it has a nasty
    failure mode: noise is high-frequency, so a blurred *noisy* image can score
    as sharper than a clean one. Since low-light case photographs are exactly
    where both problems appear together, the Laplacian is taken over a
    median-filtered copy — which suppresses noise while preserving real edges —
    and the residual that the filter removed is scored separately as noise.
    """
    denoised = cv2.medianBlur(gray, 3)
    lap_var = float(cv2.Laplacian(denoised, cv2.CV_64F).var())

    residual = gray.astype(np.float32) - denoised.astype(np.float32)
    noise_sigma = float(residual.std())

    # ~500 is a crisp photo; ~20 is badly blurred.
    sharpness = _clamp01(np.log1p(lap_var) / np.log1p(500.0))
    # Grain beyond ~4 levels starts eating real detail.
    noise_penalty = _clamp01(noise_sigma / 18.0)
    return _clamp01(sharpness * (1.0 - 0.55 * noise_penalty)), lap_var, noise_sigma


def _exposure_score(gray: np.ndarray) -> tuple[float, float, float]:
    mean = float(gray.mean())
    std = float(gray.std())
    balance = 1.0 - abs(mean - 128.0) / 128.0
    contrast = _clamp01(std / 60.0)
    return _clamp01(0.6 * balance + 0.4 * contrast), mean, std


def _resolution_score(face_pixels: float) -> tuple[float, str]:
    # ArcFace is trained on 112×112 crops; below that, detail is being invented.
    side = float(np.sqrt(max(face_pixels, 1.0)))
    score = _clamp01((side - 40.0) / (224.0 - 40.0))
    if side >= 180:
        label = "High"
    elif side >= 112:
        label = "Adequate"
    elif side >= 64:
        label = "Low"
    else:
        label = "Very low"
    return score, label


def assess(path: str | Path) -> dict:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return {
            "quality_score": None, "error": "unreadable image",
            "face_detected": False, "face_visibility": None,
        }

    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    box = detect_face_box(gray)
    if box is not None:
        x, y, w, h = box
        face_pixels = float(w * h)
        visibility = _clamp01(np.sqrt(face_pixels / float(width * height)) * 2.4)
        region = gray[y:y + h, x:x + w]
    else:
        face_pixels = float(width * height) * 0.10   # assume the face is a small part
        visibility = 0.0
        region = gray

    sharpness, lap_var, noise_sigma = _sharpness_score(region if region.size else gray)
    exposure, mean, std = _exposure_score(region if region.size else gray)
    resolution, res_label = _resolution_score(face_pixels)

    total = (
        WEIGHTS["sharpness"] * sharpness
        + WEIGHTS["exposure"] * exposure
        + WEIGHTS["resolution"] * resolution
        + WEIGHTS["visibility"] * visibility
    )
    if box is None:
        # No detectable face: the image may still carry marks or clothing
        # evidence, but it cannot support facial comparison.
        total *= 0.45

    blur_label = "Low" if sharpness > 0.62 else "Moderate" if sharpness > 0.35 else "High"
    light_label = "Good" if exposure > 0.66 else "Uneven" if exposure > 0.4 else "Poor"

    return {
        "quality_score": round(_clamp01(total), 4),
        "face_detected": box is not None,
        "face_visibility": round(visibility, 4),
        "resolution_label": res_label,
        "blur_label": blur_label,
        "lighting_label": light_label,
        "width": width,
        "height": height,
        "components": {
            "sharpness": round(sharpness, 4),
            "exposure": round(exposure, 4),
            "resolution": round(resolution, 4),
            "visibility": round(visibility, 4),
        },
        "raw": {
            "laplacian_variance": round(lap_var, 2),
            "noise_sigma": round(noise_sigma, 2),
            "mean_luminance": round(mean, 2),
            "luminance_std": round(std, 2),
            "face_box": list(box) if box else None,
        },
    }
