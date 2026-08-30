"""Time-aware reasoning and semantic mark comparison."""
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.core import geo, semantic, temporal
from app.core.uncertainty import Interval


def mark(description, kind="Scar", body_location="Eyebrow", side="Left", size_cm=3.0):
    return SimpleNamespace(
        description=description, kind=kind, body_location=body_location,
        side=side, size_cm=size_cm, embedding=None,
    )


class TestAgeProjection:
    def test_age_moves_forward_by_the_elapsed_time(self):
        projected = temporal.project_age(Interval.exact(8), date(2019, 1, 1), date(2026, 1, 1))
        assert projected.midpoint == pytest.approx(15.0, abs=0.05)

    def test_children_widen_faster_than_adults(self):
        child = temporal.project_age(Interval.exact(8), date(2019, 1, 1), date(2026, 1, 1))
        adult = temporal.project_age(Interval.exact(40), date(2019, 1, 1), date(2026, 1, 1))
        assert child.width > adult.width

    def test_unknown_age_stays_unknown(self):
        assert not temporal.project_age(Interval.unknown(), date(2019, 1, 1)).known

    def test_no_reference_date_means_no_projection(self):
        original = Interval.range(20, 24)
        assert temporal.project_age(original, None) == original

    def test_a_2019_child_case_reaches_a_teenage_band(self):
        """The case the whole time-aware feature exists for."""
        projected = temporal.project_age(Interval.exact(8), date(2019, 8, 11), date(2026, 8, 29))
        assert projected.lo < 16 < projected.hi


class TestWeightDecay:
    def test_stable_attributes_do_not_decay(self):
        assert temporal.decay_multiplier("marks", 20.0) == 1.0

    def test_dynamic_attributes_decay(self):
        assert temporal.decay_multiplier("height", 6.0) == pytest.approx(0.5, abs=0.01)
        assert temporal.decay_multiplier("clothing", 2.0) < 0.01

    def test_minors_decay_faster_on_physical_attributes(self):
        adult = temporal.decay_multiplier("height", 7.0, subject_was_minor=False)
        minor = temporal.decay_multiplier("height", 7.0, subject_was_minor=True)
        assert minor < adult

    def test_marks_outrank_height_after_seven_years(self):
        ctx = temporal.TemporalContext(7.0, True, 0.8)
        assert ctx.weight_for("marks") > ctx.weight_for("face") > ctx.weight_for("height")


class TestTemporalPlausibility:
    def test_records_predating_the_disappearance_are_penalised(self):
        before = temporal.temporal_plausibility(datetime(2026, 6, 1), datetime(2024, 1, 1))
        after = temporal.temporal_plausibility(datetime(2026, 6, 1), datetime(2026, 8, 1))
        assert before < 0.1 < after

    def test_a_short_grace_window_is_allowed(self):
        assert temporal.temporal_plausibility(datetime(2026, 6, 1), datetime(2026, 5, 25)) > 0.5

    def test_long_gaps_decay_gently_not_off_a_cliff(self):
        assert temporal.temporal_plausibility(datetime(2019, 1, 1), datetime(2026, 1, 1)) > 0.65

    def test_missing_dates_give_no_evidence(self):
        assert temporal.temporal_plausibility(None, datetime(2026, 1, 1)) is None


class TestGeo:
    def test_known_distance(self):
        # Bengaluru -> Chennai is roughly 290 km.
        assert geo.haversine_km(12.9716, 77.5946, 13.0827, 80.2707) == pytest.approx(290, abs=15)

    def test_reach_grows_with_elapsed_time(self):
        assert geo.reach_km(0) < geo.reach_km(3) < geo.reach_km(10)

    def test_distance_is_scored_against_elapsed_time(self):
        near_term, _ = geo.location_compatibility(12.97, 77.59, 22.57, 88.36, 0.05)
        long_term, _ = geo.location_compatibility(12.97, 77.59, 22.57, 88.36, 7.0)
        assert long_term > near_term

    def test_missing_coordinates_give_no_evidence(self):
        score, distance = geo.location_compatibility(None, None, 13.0, 80.2, 1.0)
        assert score is None and distance is None


class TestSemanticMarks:
    def test_differently_worded_descriptions_of_one_scar_match(self):
        a = "3 cm horizontal scar above the left eyebrow"
        b = "small linear scar just over the left eyebrow"
        assert semantic.lexical_similarity(a, b) > 0.5

    def test_unrelated_marks_do_not_match(self):
        a = "3 cm horizontal scar above the left eyebrow"
        b = "faded blue anchor tattoo on the left shoulder blade"
        assert semantic.lexical_similarity(a, b) < 0.3

    def test_domain_synonyms_are_normalised(self):
        assert "eyebrow" in semantic.normalise_tokens("scar over the brow")
        assert "birthmark" in semantic.normalise_tokens("a small mole on the arm")

    def test_opposite_sides_are_counter_evidence(self):
        same, _ = semantic.compare_marks(
            [mark("3 cm scar above the left eyebrow", side="Left")],
            [mark("linear scar over the left eyebrow", side="Left")],
        )
        opposite, pairings = semantic.compare_marks(
            [mark("3 cm scar above the left eyebrow", side="Left")],
            [mark("linear scar over the right eyebrow", side="Right")],
        )
        assert opposite < same
        assert pairings[0]["side_conflict"] is True

    def test_empty_mark_sets_give_no_evidence(self):
        assert semantic.compare_marks([], [mark("anything")])[0] is None
        assert semantic.compare_marks([mark("anything")], [])[0] is None

    def test_every_probe_mark_must_find_support(self):
        one_of_two, _ = semantic.compare_marks(
            [mark("scar above the left eyebrow"),
             mark("anchor tattoo on the left shoulder", kind="Tattoo", body_location="Shoulder")],
            [mark("linear scar over the left eyebrow")],
        )
        both, _ = semantic.compare_marks(
            [mark("scar above the left eyebrow")],
            [mark("linear scar over the left eyebrow")],
        )
        assert one_of_two < both
