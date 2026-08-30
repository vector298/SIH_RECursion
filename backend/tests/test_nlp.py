"""NlpClient: extraction, embeddings, similarity — and every way they can fail.

The governing requirement is that an NLP outage degrades the result and never
breaks the request, so most of this file is about failure.
"""
import httpx
import pytest

from app.services.nlp import (
    EmbeddingResult, NlpClient, NullProvider, cosine, heuristic_extract, lexical_similarity,
)
from app.services.nlp_schemas import ExtractedFeatures, ExtractedMark

BRIEF_EXAMPLE = (
    "The person has a scar above his left eyebrow and a tattoo of a star on his "
    "right forearm. He was last seen wearing a blue shirt."
)


# ---------------------------------------------------------------- providers --
class FakeProvider:
    """Configurable stand-in so every failure mode is reachable in a test."""

    name = "fake"

    def __init__(self, structured=None, embedding=None, raises=None, is_available=True):
        self._structured = structured
        self._embedding = embedding
        self._raises = raises
        self._available = is_available
        self.calls = 0

    def available(self):
        return self._available

    def embedding_model_name(self):
        return "fake:embed-001"

    def structured(self, text, *, schema, system):
        self.calls += 1
        if self._raises:
            raise self._raises
        return self._structured

    def embed(self, text):
        self.calls += 1
        if self._raises:
            raise self._raises
        return self._embedding


@pytest.fixture
def offline():
    return NlpClient(NullProvider())


# ---------------------------------------------------------------- extraction -
class TestExtraction:
    def test_several_marks_from_one_passage(self, offline):
        features = offline.extract_features(BRIEF_EXAMPLE)
        assert {m.type for m in features.marks} == {"scar", "tattoo"}

    def test_side_and_location_are_separated(self, offline):
        marks = {m.type: m for m in offline.extract_features(BRIEF_EXAMPLE).marks}
        assert (marks["scar"].location, marks["scar"].side) == ("eyebrow", "left")
        assert (marks["tattoo"].location, marks["tattoo"].side) == ("forearm", "right")

    def test_clothing_is_captured_separately_from_marks(self, offline):
        features = offline.extract_features(BRIEF_EXAMPLE)
        assert any("blue shirt" in c for c in features.clothing)

    def test_measurements_are_parsed_to_centimetres(self, offline):
        marks = offline.extract_features(
            "long scar on the left cheek, approximately 5 cm").marks
        assert marks[0].size_cm == pytest.approx(5.0)

    def test_millimetres_and_inches_convert(self, offline):
        assert offline.extract_features("40 mm scar on the arm").marks[0].size_cm == pytest.approx(4.0)
        assert offline.extract_features("2 inch scar on the arm").marks[0].size_cm == pytest.approx(5.08)

    def test_empty_input_is_not_an_error(self, offline):
        assert offline.extract_features("").marks == []
        assert offline.extract_features("   ").source == "empty"

    def test_text_with_no_marks_yields_none(self, offline):
        assert offline.extract_features("The weather was cold that evening.").marks == []

    def test_provider_output_is_used_when_valid(self):
        client = NlpClient(FakeProvider(structured={
            "marks": [{"type": "tattoo", "description": "star tattoo",
                       "location": "forearm", "side": "right"}],
            "clothing": [], "other_details": [],
        }))
        features = client.extract_features("anything")
        assert features.source == "fake"
        assert features.degraded is False
        assert features.marks[0].location == "forearm"


# ------------------------------------------------------------------ failures -
class TestFailureHandling:
    """Every one of these must return usable output, not raise."""

    @pytest.mark.parametrize("failure", [
        httpx.TimeoutException("timed out"),
        httpx.ConnectError("refused"),
        RuntimeError("quota exceeded"),
        ValueError("garbage"),
    ])
    def test_provider_exceptions_fall_back_to_rules(self, failure):
        client = NlpClient(FakeProvider(raises=failure))
        features = client.extract_features(BRIEF_EXAMPLE)
        assert features.source == "rules"
        assert features.degraded is True
        assert features.warnings
        assert len(features.marks) == 2          # still extracted, deterministically

    def test_none_response_falls_back(self):
        client = NlpClient(FakeProvider(structured=None))
        assert client.extract_features(BRIEF_EXAMPLE).source == "rules"

    def test_output_failing_schema_validation_is_discarded(self):
        """A model answering in the wrong shape must not reach the matcher."""
        client = NlpClient(FakeProvider(structured={"marks": "not-a-list"}))
        features = client.extract_features(BRIEF_EXAMPLE)
        assert features.source == "rules"
        assert any("validation" in w for w in features.warnings)

    def test_unknown_enum_values_are_normalised_not_rejected(self):
        client = NlpClient(FakeProvider(structured={
            "marks": [{"type": "SCARRING", "description": "x", "side": "LT"}],
        }))
        mark = client.extract_features("x").marks[0]
        assert mark.type == "scar" and mark.side == "left"

    def test_junk_enum_degrades_to_safe_defaults(self):
        client = NlpClient(FakeProvider(structured={
            "marks": [{"type": "banana", "description": "x", "side": "sideways"}],
        }))
        mark = client.extract_features("x").marks[0]
        assert mark.type == "other" and mark.side == "unknown"

    def test_empty_model_output_defers_to_rules(self):
        client = NlpClient(FakeProvider(structured={"marks": [], "clothing": []}))
        features = client.extract_features(BRIEF_EXAMPLE)
        assert len(features.marks) == 2
        assert any("returned nothing" in w for w in features.warnings)

    def test_embedding_failure_returns_null_vector(self):
        client = NlpClient(FakeProvider(raises=httpx.TimeoutException("t")))
        result = client.generate_embedding("scar")
        assert result.vector is None and result.degraded is True

    def test_similarity_still_works_with_no_provider(self, offline):
        result = offline.semantic_similarity("star tattoo on right forearm",
                                             "tattoo of a star on the right arm")
        assert result.method == "lexical" and result.score > 0.4


# ---------------------------------------------------------------- embeddings -
class TestEmbeddings:
    def test_vector_is_returned_when_the_provider_works(self):
        client = NlpClient(FakeProvider(embedding=[0.1, 0.2, 0.3]))
        result = client.generate_embedding("scar above the left eyebrow")
        assert result.vector == [0.1, 0.2, 0.3]
        assert result.degraded is False

    def test_stored_vectors_are_reused_rather_than_re_embedded(self):
        provider = FakeProvider(embedding=[1.0, 0.0])
        client = NlpClient(provider)
        client.semantic_similarity("a", "b", vector_a=[1.0, 0.0], vector_b=[0.9, 0.1])
        assert provider.calls == 0, "should not call the provider when vectors are supplied"

    def test_identical_vectors_score_one(self):
        client = NlpClient(FakeProvider())
        r = client.semantic_similarity("a", "b", vector_a=[1.0, 2.0], vector_b=[1.0, 2.0])
        assert r.score == pytest.approx(1.0) and r.method == "embedding"

    def test_opposite_vectors_score_zero(self):
        client = NlpClient(FakeProvider())
        r = client.semantic_similarity("a", "b", vector_a=[1.0, 0.0], vector_b=[-1.0, 0.0])
        assert r.score == pytest.approx(0.0)

    def test_mismatched_dimensions_fall_back_to_lexical(self):
        client = NlpClient(NullProvider())
        r = client.semantic_similarity("scar", "scar", vector_a=[1.0], vector_b=[1.0, 2.0])
        assert r.method == "lexical"

    def test_cosine_edge_cases(self):
        assert cosine([], []) == 0.0
        assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
        assert cosine([1.0, 1.0], [2.0, 2.0]) == pytest.approx(1.0)


# ---------------------------------------------------------------- similarity -
class TestLexicalSimilarity:
    def test_the_pair_from_the_brief_scores_high(self):
        assert lexical_similarity(
            "star tattoo on right forearm",
            "tattoo resembling a five-pointed star on the right arm",
        ) > 0.45

    def test_different_marks_score_low(self):
        assert lexical_similarity(
            "star tattoo on right forearm",
            "3 cm scar above the left eyebrow",
        ) < 0.2

    def test_empty_strings_score_zero(self):
        assert lexical_similarity("", "scar") == 0.0


# ------------------------------------------------------------------- schemas -
class TestSchemas:
    def test_canonical_text_normalises_phrasing(self):
        mark = ExtractedMark(type="tattoo", description="a star!", location="Forearm",
                             side="right", shape="Pictorial")
        assert mark.canonical_text() == "pictorial tattoo on the right forearm"

    def test_size_is_derived_from_prose(self):
        assert ExtractedMark(type="scar", size_text="about 5 cm").size_cm == pytest.approx(5.0)

    def test_absurd_sizes_are_rejected(self):
        with pytest.raises(Exception):
            ExtractedMark(type="scar", size_cm=5000)

    def test_attributes_accept_a_bare_string(self):
        assert ExtractedMark(type="scar", attributes="faded").attributes == ["faded"]

    def test_lists_are_bounded(self):
        with pytest.raises(Exception):
            ExtractedFeatures(marks=[ExtractedMark(type="scar")] * 25)


def test_heuristics_never_raise_on_hostile_input():
    for text in ["", "   ", "🙂🙂🙂", "a" * 5000, "scar " * 400, "and and and", "...;;;,,,"]:
        assert isinstance(heuristic_extract(text), ExtractedFeatures)
