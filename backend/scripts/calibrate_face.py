"""Measure the face backend's discriminative power, and print the calibration.

    python scripts/calibrate_face.py --subjects 40

Builds genuine pairs (same synthetic subject, different pose/lighting/blur) and
impostor pairs (different subjects), then reports the score distributions, the
equal-error-rate threshold and the ROC AUC.

Why this exists: ``services.face.CALIBRATION`` scales how much weight facial
evidence receives, and those numbers must be measured rather than guessed. Run
this after changing the descriptor, and again once real ArcFace weights are
installed — the numbers should improve dramatically, and the reliability figure
in CALIBRATION should be raised to match.

Real evaluation belongs on a labelled benchmark (LFW, IJB-C) with real
photographs. This script exercises the plumbing and gives an honest lower bound;
it is not a substitute for that.
"""
from __future__ import annotations

import argparse
import itertools
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.arcface import cosine_similarity, similarity_to_score  # noqa: E402
from app.services import face as face_service  # noqa: E402
from app.synthetic import write_portrait  # noqa: E402

DEGRADATIONS = [
    {},
    {"blur": 1, "brightness": 0.85, "noise": 0.010},
    {"blur": 2, "brightness": 1.12, "noise": 0.004},
]


def roc_auc(genuine: np.ndarray, impostor: np.ndarray) -> float:
    """Probability a random genuine pair outscores a random impostor pair."""
    scores = np.concatenate([genuine, impostor])
    labels = np.concatenate([np.ones_like(genuine), np.zeros_like(impostor)])
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    n_pos, n_neg = len(genuine), len(impostor)
    return float((ranks[labels == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subjects", type=int, default=32)
    args = parser.parse_args()

    workdir = Path(tempfile.mkdtemp(prefix="caseintel-calib-"))
    subjects = list(range(9000, 9000 + args.subjects))

    embeddings: dict[tuple[int, int], list[float]] = {}
    for subject in subjects:
        for variant, degradation in enumerate(DEGRADATIONS):
            path = write_portrait(workdir / f"{subject}_{variant}.png",
                                  subject, variant * 4, **degradation)
            vector, _model, _ = face_service.embed_image(path)
            if vector:
                embeddings[(subject, variant)] = vector

    genuine = np.array([
        cosine_similarity(embeddings[(s, a)], embeddings[(s, b)])
        for s in subjects
        for a, b in itertools.combinations(range(len(DEGRADATIONS)), 2)
        if (s, a) in embeddings and (s, b) in embeddings
    ])
    impostor = np.array([
        cosine_similarity(embeddings[(a, 0)], embeddings[(b, 1)])
        for a, b in itertools.permutations(subjects, 2)
        if (a, 0) in embeddings and (b, 1) in embeddings
    ])

    backend = face_service.backend_name()
    print(f"backend : {backend}")
    print(f"real ArcFace: {face_service.is_real_arcface()}")
    print(f"genuine  n={len(genuine):5d}  mean={genuine.mean():.4f}  sd={genuine.std():.4f}  "
          f"p05={np.percentile(genuine, 5):.4f}")
    print(f"impostor n={len(impostor):5d}  mean={impostor.mean():.4f}  sd={impostor.std():.4f}  "
          f"p95={np.percentile(impostor, 95):.4f}")

    best = None
    for threshold in np.arange(-0.2, 1.0, 0.002):
        far = float((impostor >= threshold).mean())
        frr = float((genuine < threshold).mean())
        if best is None or abs(far - frr) < abs(best[1] - best[2]):
            best = (float(threshold), far, frr)

    threshold, far, frr = best
    eer = (far + frr) / 2
    print(f"\nEER threshold = {threshold:.3f}   FAR={far:.3f}  FRR={frr:.3f}  EER={eer:.3f}")
    print(f"ROC AUC       = {roc_auc(genuine, impostor):.4f}")

    reliability = max(0.0, min(1.0, 1.0 - 2.0 * eer))
    print("\nSuggested entry for services/face.CALIBRATION:")
    print(f'    "{backend}": {{"threshold": {threshold:.2f}, '
          f'"reliability": {reliability:.2f}, "eer": {eer:.3f}}},')
    print(f"\n(current: {face_service.calibration(backend)})")
    print(f"\nmidpoint check: similarity_to_score({threshold:.2f}) = "
          f"{similarity_to_score(threshold, threshold=threshold):.2f}")


if __name__ == "__main__":
    main()
