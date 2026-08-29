"""ArcFace — Additive Angular Margin Loss (Deng et al., CVPR 2019).

Two things are commonly confused, so both are here and kept distinct:

*   **The loss** is a training-time object. It is a classification head that
    normalises both the embedding and the class weights onto a hypersphere,
    adds an angular margin ``m`` to the ground-truth class angle, rescales by
    ``s``, and then applies ordinary softmax cross-entropy. Penalising the angle
    rather than the logit is what makes the learned embeddings cluster tightly
    by identity and spread apart between identities.

*   **Inference** does not use the loss at all. You keep the trained backbone,
    take its 512-D output, L2-normalise it, and compare two embeddings with
    cosine similarity. That path lives in ``app/services/face.py``.

The maths, for the target class y:

    cos θ_y  = ŵ_y · x̂                       (both L2-normalised)
    logit_y  = s · cos(θ_y + m)
    logit_j  = s · cos(θ_j)          for j ≠ y
    L        = CrossEntropy(logits, y)

``cos(θ + m)`` is expanded as ``cos θ cos m − sin θ sin m`` rather than by
calling ``arccos``, which is numerically unstable near ±1.

Monotonicity guard: ``cos(θ + m)`` stops decreasing once ``θ + m > π``. Past
that point the penalty would start *rewarding* a worse angle, so beyond the
threshold the paper substitutes the linear fallback ``cos θ − m·sin(m)``.
"""
from __future__ import annotations

import math

import numpy as np

try:  # torch is only needed for training
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    _HAS_TORCH = True
except Exception:                                            # pragma: no cover
    _HAS_TORCH = False


DEFAULT_SCALE = 64.0
DEFAULT_MARGIN = 0.50


# ---------------------------------------------------------------------------
# NumPy reference implementation — dependency-free, used to verify the torch
# module produces identical numbers.
# ---------------------------------------------------------------------------
def _l2_normalise(a: np.ndarray, axis: int = -1, eps: float = 1e-10) -> np.ndarray:
    return a / np.clip(np.linalg.norm(a, axis=axis, keepdims=True), eps, None)


def arcface_logits_numpy(
    embeddings: np.ndarray,
    weights: np.ndarray,
    labels: np.ndarray,
    *,
    scale: float = DEFAULT_SCALE,
    margin: float = DEFAULT_MARGIN,
    easy_margin: bool = False,
) -> np.ndarray:
    """Reference ArcFace logits. embeddings (N, D), weights (C, D), labels (N,)."""
    x = _l2_normalise(np.asarray(embeddings, dtype=np.float64))
    w = _l2_normalise(np.asarray(weights, dtype=np.float64))

    cos_t = np.clip(x @ w.T, -1.0 + 1e-7, 1.0 - 1e-7)
    sin_t = np.sqrt(np.clip(1.0 - cos_t ** 2, 0.0, 1.0))

    cos_m, sin_m = math.cos(margin), math.sin(margin)
    cos_t_m = cos_t * cos_m - sin_t * sin_m          # cos(θ + m)

    if easy_margin:
        cos_t_m = np.where(cos_t > 0, cos_t_m, cos_t)
    else:
        threshold = math.cos(math.pi - margin)       # θ + m > π beyond this
        mm = math.sin(math.pi - margin) * margin     # = m · sin(m)
        cos_t_m = np.where(cos_t > threshold, cos_t_m, cos_t - mm)

    one_hot = np.zeros_like(cos_t)
    one_hot[np.arange(len(labels)), np.asarray(labels)] = 1.0

    return scale * (one_hot * cos_t_m + (1.0 - one_hot) * cos_t)


def cross_entropy_numpy(logits: np.ndarray, labels: np.ndarray) -> float:
    shifted = logits - logits.max(axis=1, keepdims=True)
    log_probs = shifted - np.log(np.exp(shifted).sum(axis=1, keepdims=True))
    return float(-log_probs[np.arange(len(labels)), np.asarray(labels)].mean())


# ---------------------------------------------------------------------------
# PyTorch training head
# ---------------------------------------------------------------------------
if _HAS_TORCH:

    class ArcMarginProduct(nn.Module):
        """The ArcFace head: embeddings in, margin-penalised logits out.

        Drop this on top of any backbone and train with ordinary
        ``nn.CrossEntropyLoss``. After training, discard the head and keep the
        backbone — the embedding is the product, not the classifier.

        Args:
            in_features:  embedding dimension (512 for the standard ArcFace).
            out_features: number of identities in the training set.
            scale:        ``s``, the hypersphere radius. Larger = sharper softmax.
            margin:       ``m``, the additive angular margin in radians.
            easy_margin:  use the softer guard from the reference implementation.
        """

        def __init__(
            self,
            in_features: int,
            out_features: int,
            scale: float = DEFAULT_SCALE,
            margin: float = DEFAULT_MARGIN,
            easy_margin: bool = False,
        ) -> None:
            super().__init__()
            self.in_features = in_features
            self.out_features = out_features
            self.scale = scale
            self.margin = margin
            self.easy_margin = easy_margin

            self.weight = nn.Parameter(torch.empty(out_features, in_features))
            nn.init.xavier_uniform_(self.weight)

            self.register_buffer("cos_m", torch.tensor(math.cos(margin)))
            self.register_buffer("sin_m", torch.tensor(math.sin(margin)))
            self.register_buffer("threshold", torch.tensor(math.cos(math.pi - margin)))
            self.register_buffer("mm", torch.tensor(math.sin(math.pi - margin) * margin))

        def forward(self, embeddings: "torch.Tensor", labels: "torch.Tensor") -> "torch.Tensor":
            cos_t = F.linear(F.normalize(embeddings), F.normalize(self.weight))
            cos_t = cos_t.clamp(-1.0 + 1e-7, 1.0 - 1e-7)
            sin_t = torch.sqrt((1.0 - cos_t.pow(2)).clamp_min(0.0))

            cos_t_m = cos_t * self.cos_m - sin_t * self.sin_m

            if self.easy_margin:
                cos_t_m = torch.where(cos_t > 0, cos_t_m, cos_t)
            else:
                cos_t_m = torch.where(cos_t > self.threshold, cos_t_m, cos_t - self.mm)

            one_hot = torch.zeros_like(cos_t)
            one_hot.scatter_(1, labels.view(-1, 1).long(), 1.0)

            return self.scale * (one_hot * cos_t_m + (1.0 - one_hot) * cos_t)

        def extra_repr(self) -> str:                          # pragma: no cover
            return (f"in_features={self.in_features}, out_features={self.out_features}, "
                    f"scale={self.scale}, margin={self.margin}")

    class ArcFaceLoss(nn.Module):
        """``ArcMarginProduct`` plus cross-entropy, for convenience."""

        def __init__(self, in_features: int, out_features: int, **kwargs) -> None:
            super().__init__()
            self.head = ArcMarginProduct(in_features, out_features, **kwargs)
            self.criterion = nn.CrossEntropyLoss()

        def forward(self, embeddings: "torch.Tensor", labels: "torch.Tensor") -> "torch.Tensor":
            return self.criterion(self.head(embeddings, labels), labels)

else:                                                        # pragma: no cover
    class _TorchMissing:
        def __init__(self, *_a, **_k):
            raise ImportError(
                "PyTorch is required for the ArcFace training head. "
                "Install it with:  pip install -r requirements-train.txt"
            )

    ArcMarginProduct = _TorchMissing   # type: ignore[assignment]
    ArcFaceLoss = _TorchMissing        # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Inference-side helper
# ---------------------------------------------------------------------------
def cosine_similarity(a, b) -> float:
    """Cosine similarity between two embeddings, in [-1, 1]."""
    va = _l2_normalise(np.asarray(a, dtype=np.float64).ravel())
    vb = _l2_normalise(np.asarray(b, dtype=np.float64).ravel())
    return float(np.clip(va @ vb, -1.0, 1.0))


def similarity_to_score(cosine: float, *, threshold: float = 0.28) -> float:
    """Map ArcFace cosine similarity onto a [0, 1] evidence score.

    ArcFace similarities for genuine pairs typically sit well above ~0.28 while
    impostor pairs cluster near 0, so the threshold anchors the midpoint of the
    curve rather than acting as a hard accept/reject boundary — the officer, not
    the model, decides.
    """
    if cosine <= 0:
        return 0.0
    span = max(1e-6, 1.0 - threshold)
    if cosine <= threshold:
        return float(0.5 * (cosine / max(threshold, 1e-6)) ** 1.5)
    return float(0.5 + 0.5 * ((cosine - threshold) / span) ** 0.8)
