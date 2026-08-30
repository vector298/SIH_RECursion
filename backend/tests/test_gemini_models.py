"""Model negotiation: surviving Google's retirement schedule.

Three things went wrong on a real key while this project was being built, and
all three are pinned here:

* ``text-embedding-004`` was withdrawn — a 404 on every embedding call.
* ``gemini-2.5-flash`` was *listed* by ListModels and still answered 404 with
  "no longer available to new users", so a catalogue lookup alone is not proof.
* The replacement embedding family rejects the ``taskType`` field that its
  predecessor required, with a 400.

A hard-coded model name cannot survive any of these. The provider therefore
treats the configured name as a preference and negotiates.
"""
import pytest

from app.services.gemini import CHAT, EMBED, GeminiProvider, _rank
from app.services.nlp import NlpClient


class FakeApi:
    """A Gemini-shaped API whose failures are configurable per model."""

    def __init__(self, models, *, dead=(), no_task_type=(), embed_dim=3072):
        self.models = models                  # {name: [methods]}
        self.dead = set(dead)                 # listed, but 404 when called
        self.no_task_type = set(no_task_type)  # 400 when taskType is sent
        self.embed_dim = embed_dim
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, method, path, *, json=None, params=None):
        self.calls.append((path, json or {}))

        if path == "models":
            return {"models": [{"name": f"models/{n}", "supportedGenerationMethods": m}
                               for n, m in self.models.items()]}, 200

        name = path.split("models/")[1].split(":")[0]
        if name in self.dead or name not in self.models:
            return None, 404
        if "embedContent" in path:
            if name in self.no_task_type and "taskType" in json:
                return None, 400
            dim = json.get("outputDimensionality") or self.embed_dim
            return {"embedding": {"values": [0.1] * dim}}, 200
        return {"candidates": [{"content": {"parts": [{"text": '{"marks": []}'}]}}]}, 200


def provider_with(api, **kwargs) -> GeminiProvider:
    p = GeminiProvider(api_key="test-key", **kwargs)
    p._request = api                                          # noqa: SLF001
    return p


CURRENT = {
    "gemini-3.6-flash": ["generateContent"],
    "gemini-3.7-flash": ["generateContent"],
    "gemini-3.5-flash-lite": ["generateContent"],
    "gemini-3.7-pro": ["generateContent"],
    "gemini-embedding-001": ["embedContent"],
    "gemini-embedding-2-preview": ["embedContent"],
}


# ------------------------------------------------------------ substitution --
def test_configured_model_is_used_when_available():
    api = FakeApi(CURRENT)
    p = provider_with(api, model="gemini-3.6-flash", embed_model="gemini-embedding-001")
    assert p.resolve(CHAT) == "gemini-3.6-flash"
    assert p.resolve(EMBED) == "gemini-embedding-001"


def test_retired_embedding_model_is_substituted():
    """text-embedding-004 is gone; the key must still get embeddings."""
    api = FakeApi(CURRENT)
    p = provider_with(api, embed_model="text-embedding-004")
    chosen = p.resolve(EMBED)
    assert chosen in CURRENT and "embedContent" in CURRENT[chosen]
    assert p.embed("a scar") is not None


def test_listed_but_dead_model_is_retired_on_404_and_the_call_still_succeeds():
    """The gemini-2.5-flash case: present in ListModels, 404 when called."""
    models = {"gemini-2.5-flash": ["generateContent"], **CURRENT}
    api = FakeApi(models, dead={"gemini-2.5-flash"})
    p = provider_with(api, model="gemini-2.5-flash")

    assert p.resolve(CHAT) == "gemini-2.5-flash"              # catalogue says fine
    assert p.structured("text", schema={}, system="") == {"marks": []}
    assert p.resolve(CHAT) != "gemini-2.5-flash"              # the call says otherwise
    assert "gemini-2.5-flash" in p._unusable                  # noqa: SLF001


def test_substitution_prefers_a_stable_flash_release():
    api = FakeApi({
        "gemini-3.8-flash-preview": ["generateContent"],
        "gemini-3.5-flash-lite": ["generateContent"],
        "gemini-3.7-pro": ["generateContent"],
        "gemini-3.6-flash": ["generateContent"],
    })
    p = provider_with(api, model="gemini-2.5-flash")
    # Newest *stable* flash, not the newer preview and not the pro.
    assert p.resolve(CHAT) == "gemini-3.6-flash"


def test_embedding_models_are_never_offered_for_chat():
    api = FakeApi({"gemini-embedding-001": ["embedContent"]})
    p = provider_with(api, model="gemini-2.5-flash")
    assert p.resolve(CHAT) is None


def test_image_and_audio_models_are_never_offered_for_chat():
    api = FakeApi({
        "imagen-4.0-generate": ["generateContent"],
        "gemini-2.5-flash-tts": ["generateContent"],
        "gemini-3.6-flash": ["generateContent"],
    })
    p = provider_with(api, model="nonexistent-model")
    assert p.resolve(CHAT) == "gemini-3.6-flash"


def test_pinning_refuses_to_substitute():
    api = FakeApi(CURRENT)
    p = provider_with(api, model="gemini-2.5-flash")
    p.pin_models = True
    assert p.resolve(CHAT) is None


# ----------------------------------------------------------- field handling --
def test_task_type_is_dropped_when_the_model_rejects_it():
    """gemini-embedding-2 dropped taskType; a 400 must not kill the embedding."""
    api = FakeApi({"gemini-embedding-2-preview": ["embedContent"]},
                  no_task_type={"gemini-embedding-2-preview"})
    p = provider_with(api, embed_model="gemini-embedding-2-preview")

    vector = p.embed("a scar above the left eyebrow")
    assert vector and len(vector) == 3072

    embed_calls = [body for path, body in api.calls if "embedContent" in path]
    assert "taskType" in embed_calls[0]        # tried, because it improves quality
    assert "taskType" not in embed_calls[1]    # and dropped once refused


def test_a_rejected_field_retires_the_field_not_the_model():
    api = FakeApi({"gemini-embedding-2-preview": ["embedContent"]},
                  no_task_type={"gemini-embedding-2-preview"})
    p = provider_with(api, embed_model="gemini-embedding-2-preview")
    p.embed("first")
    assert p.resolve(EMBED) == "gemini-embedding-2-preview"
    assert "gemini-embedding-2-preview" not in p._unusable     # noqa: SLF001


def test_requested_dimensionality_is_honoured(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "gemini_embed_dim", 768)
    api = FakeApi(CURRENT)
    p = provider_with(api, embed_model="gemini-embedding-001")
    assert len(p.embed("text")) == 768


# --------------------------------------------------------------- exhaustion --
def test_a_bounded_number_of_models_is_tried():
    """Every model dead must terminate, not walk the catalogue forever."""
    api = FakeApi(CURRENT, dead=set(CURRENT))
    p = provider_with(api)
    assert p.structured("text", schema={}, system="") is None
    generate_calls = [c for c, _ in api.calls if "generateContent" in c]
    assert len(generate_calls) <= 3


def test_an_unreachable_catalogue_still_tries_the_configured_name():
    """A listing outage must not disable Gemini outright."""
    def offline(method, path, *, json=None, params=None):
        if path == "models":
            return None, None
        return {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}, 200

    p = GeminiProvider(api_key="test-key", model="gemini-3.6-flash")
    p._request = offline                                       # noqa: SLF001
    assert p.resolve(CHAT) == "gemini-3.6-flash"
    assert p.structured("text", schema={}, system="") == {}


def test_a_failed_listing_is_not_cached_as_empty():
    """Otherwise one transient blip disables substitution for the process."""
    state = {"fail": True}

    def flaky(method, path, *, json=None, params=None):
        if path == "models":
            if state["fail"]:
                return None, None
            return {"models": [{"name": "models/gemini-3.6-flash",
                                "supportedGenerationMethods": ["generateContent"]}]}, 200
        return None, 404

    p = GeminiProvider(api_key="test-key")
    p._request = flaky                                         # noqa: SLF001
    assert p.catalogue() == {}
    state["fail"] = False
    assert "gemini-3.6-flash" in p.catalogue()


def test_the_client_and_the_health_endpoint_share_one_provider():
    """Otherwise /api/health names a different model than the one answering.

    Negotiation state lives on the provider instance. A second instance repeats
    the discovery calls and learns nothing from the first one's retirements, so
    health would report the configured name long after it had been substituted.
    """
    from app.services import gemini
    from app.services.nlp import get_client, reset_client

    gemini.reset_provider()
    reset_client()
    try:
        assert get_client().provider is gemini.get_provider()
    finally:
        gemini.reset_provider()


# ------------------------------------------------------- ranking heuristic --
@pytest.mark.parametrize("better,worse", [
    ("gemini-3.7-flash", "gemini-3.6-flash"),          # newer wins
    ("gemini-3.6-flash", "gemini-3.8-flash-preview"),  # stable beats preview
    ("gemini-3.6-flash", "gemini-3.6-pro"),            # flash beats pro
    ("gemini-3.6-flash", "gemini-3.6-flash-lite"),     # full beats lite
])
def test_ranking_order(better, worse):
    assert _rank(better, CHAT) > _rank(worse, CHAT)


# ------------------------------------------- cross-model vector comparison --
class StubProvider:
    name = "stub"

    def __init__(self, model="gemini:current"):
        self.model = model
        self.embeds = 0

    def available(self):
        return True

    def embedding_model_name(self):
        return self.model

    def structured(self, text, *, schema, system):
        return None

    def embed(self, text):
        self.embeds += 1
        return [1.0, 0.0, 0.0]


def test_vectors_from_different_models_are_not_compared():
    """Same width, unrelated coordinate systems — the cosine would be noise."""
    provider = StubProvider()
    client = NlpClient(provider)

    result = client.semantic_similarity(
        "star tattoo on right forearm", "tattoo of a star on the right arm",
        vector_a=[1.0, 0.0, 0.0], vector_b=[0.0, 1.0, 0.0],
        model_a="gemini:text-embedding-004", model_b="gemini:gemini-embedding-001",
    )
    # Both stale vectors are discarded and re-embedded on the current model.
    assert provider.embeds == 2
    assert result.method == "embedding"


def test_matching_model_labels_use_the_stored_vectors():
    provider = StubProvider()
    client = NlpClient(provider)

    client.semantic_similarity(
        "a", "b", vector_a=[1.0, 0.0], vector_b=[0.0, 1.0],
        model_a="gemini:same", model_b="gemini:same",
    )
    assert provider.embeds == 0        # nothing re-embedded


def test_unlabelled_vectors_are_still_usable():
    """Records written before the label existed must not all go lexical."""
    provider = StubProvider()
    client = NlpClient(provider)

    result = client.semantic_similarity("a", "b", vector_a=[1.0, 0.0], vector_b=[1.0, 0.0])
    assert provider.embeds == 0
    assert result.method == "embedding"
    assert result.score == pytest.approx(1.0)


def test_a_stale_vector_is_re_embedded_but_a_current_one_is_kept():
    provider = StubProvider("gemini:current")
    client = NlpClient(provider)

    client.semantic_similarity(
        "a", "b", vector_a=[0.0, 1.0, 0.0], vector_b=[1.0, 0.0, 0.0],
        model_a="gemini:retired", model_b="gemini:current",
    )
    assert provider.embeds == 1        # only the stale side
