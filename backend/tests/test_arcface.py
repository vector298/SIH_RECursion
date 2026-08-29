"""ArcFace loss — verified against an independent NumPy reference."""
import math

import numpy as np
import pytest

from app.core.arcface import (
    DEFAULT_MARGIN, DEFAULT_SCALE, arcface_logits_numpy, cosine_similarity,
    cross_entropy_numpy, similarity_to_score,
)

torch = pytest.importorskip("torch")
from app.core.arcface import ArcFaceLoss, ArcMarginProduct  # noqa: E402


@pytest.fixture
def batch():
    rng = np.random.default_rng(0)
    torch.manual_seed(0)
    n, d, c = 8, 32, 6
    return rng.standard_normal((n, d)), rng.integers(0, c, size=n), d, c


class TestAgainstReference:
    def test_torch_matches_numpy(self, batch):
        emb, labels, d, c = batch
        head = ArcMarginProduct(d, c)
        w = head.weight.detach().numpy().astype(np.float64)

        got = head(torch.tensor(emb, dtype=torch.float32), torch.tensor(labels)).detach().numpy()
        want = arcface_logits_numpy(emb, w, labels)
        assert np.abs(got - want).max() < 1e-4

    def test_zero_margin_degenerates_to_scaled_cosine(self, batch):
        emb, labels, d, c = batch
        head = ArcMarginProduct(d, c, margin=0.0)
        w = head.weight.detach().numpy().astype(np.float64)

        x = emb / np.linalg.norm(emb, axis=1, keepdims=True)
        wn = w / np.linalg.norm(w, axis=1, keepdims=True)
        assert np.allclose(arcface_logits_numpy(emb, w, labels, margin=0.0), DEFAULT_SCALE * (x @ wn.T))


class TestMarginBehaviour:
    def test_margin_penalises_only_the_target_class(self, batch):
        emb, labels, d, c = batch
        rng = np.random.default_rng(1)
        w = rng.standard_normal((c, d))

        arc = arcface_logits_numpy(emb, w, labels)
        plain = arcface_logits_numpy(emb, w, labels, margin=0.0)

        rows = np.arange(len(labels))
        assert (arc[rows, labels] < plain[rows, labels]).all()

        mask = np.ones_like(arc, dtype=bool)
        mask[rows, labels] = False
        assert np.allclose(arc[mask], plain[mask])

    def test_larger_margin_means_larger_loss(self, batch):
        emb, labels, d, c = batch
        rng = np.random.default_rng(2)
        w = rng.standard_normal((c, d))
        losses = [
            cross_entropy_numpy(arcface_logits_numpy(emb, w, labels, margin=m), labels)
            for m in (0.0, 0.2, 0.5)
        ]
        assert losses == sorted(losses)

    def test_monotonicity_guard_beyond_pi(self):
        """Past θ + m > π the cosine turns back upward; the guard must prevent that."""
        d, c, m = 4, 2, DEFAULT_MARGIN
        # An embedding pointing away from its class weight gives θ near π.
        emb = np.array([[1.0, 0, 0, 0]])
        w = np.array([[-1.0, 0, 0, 0], [0, 1.0, 0, 0]])
        labels = np.array([0])

        guarded = arcface_logits_numpy(emb, w, labels, margin=m, easy_margin=False)[0, 0]
        cos_theta = -1.0 + 1e-7
        expected = DEFAULT_SCALE * (cos_theta - math.sin(math.pi - m) * m)
        assert guarded == pytest.approx(expected, rel=1e-5)

    def test_loss_module_is_finite_and_differentiable(self, batch):
        emb, labels, d, c = batch
        loss_fn = ArcFaceLoss(d, c)
        x = torch.tensor(emb, dtype=torch.float32, requires_grad=True)
        loss = loss_fn(x, torch.tensor(labels))
        loss.backward()
        assert torch.isfinite(loss)
        assert x.grad is not None and torch.isfinite(x.grad).all()


class TestInferenceHelpers:
    def test_cosine_is_scale_invariant(self):
        v = np.random.default_rng(3).standard_normal(512)
        assert cosine_similarity(v, v * 7.5) == pytest.approx(1.0)
        assert cosine_similarity(v, -v) == pytest.approx(-1.0)

    def test_similarity_score_is_monotonic_and_bounded(self):
        scores = [similarity_to_score(c) for c in (-0.5, 0.0, 0.1, 0.28, 0.6, 1.0)]
        assert scores[0] == 0.0 and scores[-1] == pytest.approx(1.0)
        assert scores == sorted(scores)

    def test_threshold_moves_the_midpoint(self):
        assert similarity_to_score(0.28, threshold=0.28) == pytest.approx(0.5)
        assert similarity_to_score(0.76, threshold=0.76) == pytest.approx(0.5)
