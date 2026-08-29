"""The uncertainty contract — the property the whole system rests on."""
import pytest

from app.core.fusion import SourceScore, apply_quality_cap, fuse
from app.core.uncertainty import Interval, Mode, compare, compare_categorical, overlaps


class TestIntervalConstruction:
    def test_exact_is_a_degenerate_interval(self):
        i = Interval.exact(25)
        assert (i.lo, i.hi, i.mode) == (25.0, 25.0, Mode.EXACT)
        assert i.known and i.width == 0

    def test_range_orders_its_bounds(self):
        assert Interval.range(27, 23).lo == 23

    def test_range_collapsing_to_a_point_is_exact(self):
        assert Interval.range(30, 30).mode is Mode.EXACT

    def test_unknown_is_not_zero(self):
        u = Interval.unknown()
        assert not u.known
        assert u.lo is None and u.hi is None

    def test_half_open_range_degrades_to_exact(self):
        assert Interval.range(20, None).mode is Mode.EXACT

    @pytest.mark.parametrize("mode,lo,hi", [("unknown", None, None), (None, None, None)])
    def test_from_record_handles_absent_values(self, mode, lo, hi):
        assert not Interval.from_record(mode, lo, hi).known


class TestComparison:
    def test_unknown_yields_no_evidence_not_zero(self):
        assert compare(Interval.unknown(), Interval.exact(25), decay=3) is None
        assert compare(Interval.exact(25), Interval.unknown(), decay=3) is None

    def test_identical_points_score_one(self):
        assert compare(Interval.exact(25), Interval.exact(25), decay=3) == 1.0

    def test_identical_ranges_score_one(self):
        assert compare(Interval.range(23, 27), Interval.range(23, 27), decay=3) == 1.0

    def test_partial_overlap_scores_between(self):
        s = compare(Interval.range(23, 27), Interval.range(25, 31), decay=3)
        assert 0 < s < 1

    def test_tight_agreement_beats_vague_agreement(self):
        tight = compare(Interval.range(24, 26), Interval.range(24, 26), decay=3)
        vague = compare(Interval.range(20, 40), Interval.range(24, 26), decay=3)
        assert tight > vague

    def test_disjoint_intervals_decay_rather_than_zero(self):
        near = compare(Interval.range(23, 27), Interval.range(28, 30), decay=3)
        far = compare(Interval.range(23, 27), Interval.range(50, 55), decay=3)
        assert 0 < far < near < 1

    def test_decay_is_monotonic_in_the_gap(self):
        scores = [compare(Interval.exact(20), Interval.exact(20 + g), decay=3) for g in (1, 3, 6, 12)]
        assert scores == sorted(scores, reverse=True)

    def test_overlaps_never_excludes_on_unknown(self):
        assert overlaps(Interval.unknown(), Interval.exact(5)) is True
        assert overlaps(Interval.exact(1), Interval.exact(99)) is False


class TestCategorical:
    def test_missing_side_is_no_evidence(self):
        assert compare_categorical(None, "Female") is None
        assert compare_categorical("", "Female") is None

    def test_agreement_and_mismatch(self):
        assert compare_categorical("Female", "female") == 1.0
        assert compare_categorical("Female", "Male") == 0.0
        assert compare_categorical("Female", "Male", mismatch=0.3) == 0.3


class TestFusion:
    def test_unknown_sources_do_not_drag_the_score_down(self):
        both_known = fuse([SourceScore("a", 0.9, 0.5), SourceScore("b", 0.9, 0.5)])
        one_missing = fuse([SourceScore("a", 0.9, 0.5), SourceScore("b", None, 0.5)])
        # The missing source lowers confidence only through coverage shrinkage,
        # never by being counted as a zero.
        as_zero = fuse([SourceScore("a", 0.9, 0.5), SourceScore("b", 0.0, 0.5)])
        assert one_missing.confidence > as_zero.confidence
        assert one_missing.confidence < both_known.confidence

    def test_coverage_reflects_available_weight(self):
        r = fuse([SourceScore("a", 0.8, 0.75), SourceScore("b", None, 0.25)])
        assert r.coverage == pytest.approx(0.75)

    def test_thin_evidence_cannot_reach_certainty(self):
        thin = fuse([SourceScore("a", 1.0, 0.1), SourceScore("b", None, 0.9)])
        assert thin.confidence < 0.65

    def test_full_coverage_is_the_plain_weighted_mean(self):
        r = fuse([SourceScore("a", 1.0, 0.5), SourceScore("b", 0.5, 0.5)])
        assert r.confidence == pytest.approx(0.75)

    def test_no_sources_at_all(self):
        assert fuse([]).confidence == 0.0
        assert fuse([SourceScore("a", None, 1.0)]).confidence == 0.0


class TestQualityCap:
    def test_lower_quality_governs(self):
        adjusted, limit = apply_quality_cap(0.94, 0.92, 0.81)
        assert limit == pytest.approx(0.81)
        assert adjusted == pytest.approx(0.94 * 0.81)

    def test_absent_face_score_stays_absent(self):
        assert apply_quality_cap(None, 0.9, 0.9)[0] is None

    def test_missing_quality_falls_back_to_a_penalty(self):
        adjusted, limit = apply_quality_cap(1.0, None, None)
        assert 0 < limit < 1 and adjusted == limit
