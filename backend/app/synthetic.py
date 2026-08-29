"""Synthetic portrait generation — for seeding and tests only.

These are drawn shapes, not photographs and not generated likenesses of anyone.
A demonstration corpus must not contain invented faces attached to invented case
records, so the seed uses these instead. They exist so the image pipeline
(quality assessment -> embedding -> cosine comparison) actually executes on real
pixels rather than being stubbed.

``variant`` lets the same underlying subject be re-drawn with different pose,
lighting and blur, which is how the seed produces a genuinely matching pair.
"""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def portrait(
    subject_seed: int,
    variant: int = 0,
    size: int = 320,
    *,
    blur: float = 0.0,
    brightness: float = 1.0,
    noise: float = 0.0,
) -> np.ndarray:
    """Draw a schematic frontal portrait for ``subject_seed``.

    Subject identity drives geometry (face width, eye spacing, brow, nose, jaw);
    ``variant`` perturbs pose and shading only. Two variants of one subject are
    therefore genuinely more similar than two different subjects.
    """
    r = _rng(subject_seed)
    v = _rng(subject_seed * 7919 + variant)

    img = np.zeros((size, size, 3), dtype=np.uint8)

    skin = np.array([
        int(r.integers(120, 190)), int(r.integers(150, 205)), int(r.integers(180, 235))
    ], dtype=np.int16)                                    # BGR
    bg = int(r.integers(30, 70))
    img[:] = (bg, bg + 6, bg + 12)

    cx = size // 2 + int(v.integers(-8, 9))
    cy = int(size * 0.50) + int(v.integers(-6, 7))
    face_w = int(size * (0.27 + r.random() * 0.06))
    face_h = int(face_w * (1.24 + r.random() * 0.16))

    # neck and shoulders
    cv2.rectangle(img, (cx - face_w // 3, cy + face_h - 20), (cx + face_w // 3, size),
                  tuple(int(c * 0.86) for c in skin), -1)
    cv2.ellipse(img, (cx, size + int(size * 0.16)), (int(size * 0.55), int(size * 0.30)),
                0, 180, 360, (bg + 30, bg + 34, bg + 40), -1)

    # head
    cv2.ellipse(img, (cx, cy), (face_w, face_h), 0, 0, 360, tuple(int(c) for c in skin), -1)

    # hair
    hair_tone = int(r.integers(20, 70))
    hair_h = 0.30 + r.random() * 0.34
    cv2.ellipse(img, (cx, cy - int(face_h * 0.42)), (int(face_w * 1.04), int(face_h * hair_h)),
                0, 180, 360, (hair_tone, hair_tone - 4, hair_tone - 8), -1)

    eye_dx = int(face_w * (0.40 + r.random() * 0.12))
    eye_dy = int(face_h * (0.12 + r.random() * 0.07))
    eye_r = max(3, int(face_w * (0.13 + r.random() * 0.05)))

    for sign in (-1, 1):
        ex, ey = cx + sign * eye_dx, cy - eye_dy
        cv2.ellipse(img, (ex, ey), (eye_r, int(eye_r * 0.62)), 0, 0, 360, (250, 250, 250), -1)
        iris = int(r.integers(40, 110))
        cv2.circle(img, (ex, ey), max(2, int(eye_r * 0.48)), (iris, iris - 10, iris - 20), -1)
        cv2.circle(img, (ex, ey), max(1, int(eye_r * 0.20)), (12, 12, 12), -1)
        # brow
        cv2.ellipse(img, (ex, ey - int(eye_r * 1.5)), (int(eye_r * 1.25), max(2, int(eye_r * 0.4))),
                    0, 180, 360, (hair_tone, hair_tone, hair_tone), -1)

    # nose
    nose_len = int(face_h * (0.20 + r.random() * 0.10))
    cv2.line(img, (cx, cy - int(eye_dy * 0.2)), (cx - int(face_w * 0.10), cy + nose_len),
             tuple(int(c * 0.80) for c in skin), max(2, face_w // 22))
    cv2.line(img, (cx - int(face_w * 0.10), cy + nose_len), (cx + int(face_w * 0.12), cy + nose_len),
             tuple(int(c * 0.80) for c in skin), max(2, face_w // 24))

    # mouth
    mouth_y = cy + int(face_h * (0.46 + r.random() * 0.10))
    cv2.ellipse(img, (cx, mouth_y), (int(face_w * (0.34 + r.random() * 0.12)), max(3, int(face_h * 0.07))),
                0, 0, 180, (int(skin[0] * 0.55), int(skin[1] * 0.45), int(skin[2] * 0.60)), -1)

    # directional shading, so variants differ in lighting the way photos do
    angle = float(v.random() * math.tau)
    gx = np.linspace(-1, 1, size)[None, :] * math.cos(angle)
    gy = np.linspace(-1, 1, size)[:, None] * math.sin(angle)
    shade = 1.0 + 0.18 * (gx + gy)
    img = np.clip(img.astype(np.float32) * shade[..., None] * brightness, 0, 255).astype(np.uint8)

    if blur > 0:
        k = int(blur) * 2 + 1
        img = cv2.GaussianBlur(img, (k, k), 0)
    if noise > 0:
        img = np.clip(img.astype(np.float32) + v.normal(0, noise * 255, img.shape), 0, 255).astype(np.uint8)

    return img


def write_portrait(path: str | Path, subject_seed: int, variant: int = 0, **kwargs) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(p), portrait(subject_seed, variant, **kwargs))
    return p
