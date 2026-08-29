"""Adaptive investigation and image quality, tested directly."""
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.core import adaptive, quality
from app.core.fusion import BASE_WEIGHTS
from app.synthetic import portrait


def _mark(kind="Scar", loc="Eyebrow", side="Left", text="scar above the left eyebrow"):
    return SimpleNamespace(id="m1", kind=kind, body_location=loc, side=side,
                           size_cm=3.0, description=text, embedding=None)


def _case(number, marks=(), build=None, blood=None, sex="Female"):
    return SimpleNamespace(id=f"id-{number}", case_number=number, marks=list(marks),
                           build=build, blood_type=blood, sex=sex)


def _candidate(case, confidence):
    return {
        "case": case, "confidence": confidence, "coverage": 1.0,
        "rank": 0, "scores": {}, "evidence": [], "concerns": [],
        "sources": {name: {"score": 0.7, "weight": w, "available": True}
                    for name, w in BASE_WEIGHTS.items()},
    }


class TestQuestionGeneration:
    def test_no_question_when_the_leader_is_clear(self):
        probe = _case("P", [_mark()])
        candidates = [_candidate(_case("A", [_mark()]), 0.91),
                      _candidate(_case("B", [_mark()]), 0.42)]
        assert adaptive.generate(probe, candidates) is None

    def test_no_question_with_a_single_candidate(self):
        probe = _case("P", [_mark()])
        assert adaptive.generate(probe, [_candidate(_case("A"), 0.9)]) is None

    def test_a_mark_the_candidates_disagree_about_is_chosen(self):
        probe = _case("P", [_mark()])
        candidates = [
            _candidate(_case("A", [_mark()]), 0.84),                       # present
            _candidate(_case("B", []), 0.82),                              # absent
            _candidate(_case("C", [_mark(side="Right")]), 0.80),           # conflicting
        ]
        q = adaptive.generate(probe, candidates)
        assert q is not None
        assert q.attribute.startswith("mark:")
        assert "eyebrow" in q.question.lower()
        assert {o["current_state"] for o in q.options} == {"present", "absent", "conflicting"}

    def test_no_question_when_every_candidate_is_in_the_same_state(self):
        """Asking about something they all share would teach nothing."""
        probe = _case("P", [_mark()])
        candidates = [_candidate(_case(n, [_mark()]), c)
                      for n, c in (("A", 0.84), ("B", 0.82), ("C", 0.80))]
        q = adaptive.generate(probe, candidates)
        assert q is None or not q.attribute.startswith("mark:")

    def test_falls_back_to_a_differing_attribute(self):
        probe = _case("P", [])
        candidates = [
            _candidate(_case("A", build="Slim"), 0.84),
            _candidate(_case("B", build="Heavy"), 0.82),
        ]
        q = adaptive.generate(probe, candidates)
        assert q is not None and q.attribute == "build"

    def test_options_are_capped(self):
        probe = _case("P", [_mark()])
        candidates = [_candidate(_case(str(i), [] if i % 2 else [_mark()]), 0.84 - i * 0.005)
                      for i in range(8)]
        q = adaptive.generate(probe, candidates)
        assert q is not None and len(q.options) <= 4


class TestAnswerFolding:
    def test_the_confirmed_candidate_rises_and_others_fall(self):
        candidates = [_candidate(_case("A"), 0.84), _candidate(_case("B"), 0.82),
                      _candidate(_case("C"), 0.80)]
        updated = adaptive.apply_answer(candidates, "id-C")

        by_number = {c["case"].case_number: c for c in updated}
        assert by_number["C"]["confidence"] > by_number["C"]["confidence_before"]
        assert by_number["A"]["confidence"] < by_number["A"]["confidence_before"]
        assert updated[0]["case"].case_number == "C"
        assert updated[0]["rank"] == 1

    def test_officer_testimony_is_recorded_as_its_own_source(self):
        updated = adaptive.apply_answer([_candidate(_case("A"), 0.8)], "id-A")
        assert "officer_verification" in updated[0]["sources"]
        assert updated[0]["officer_confirmed"] is True

    def test_one_answer_cannot_produce_certainty(self):
        """Officers can be mistaken too — a single answer must not saturate."""
        updated = adaptive.apply_answer([_candidate(_case("A"), 0.5)], "id-A")
        assert updated[0]["confidence"] < 0.99

    def test_model_scores_survive_the_update(self):
        candidates = [_candidate(_case("A"), 0.84)]
        updated = adaptive.apply_answer(candidates, "id-A")
        assert updated[0]["sources"]["marks"]["score"] == 0.7


class TestImageQuality:
    def _write(self, tmp_path, name, **kw):
        path = tmp_path / name
        cv2.imwrite(str(path), portrait(5150, 0, **kw))
        return path

    def test_a_clean_portrait_scores_well(self, tmp_path):
        report = quality.assess(self._write(tmp_path, "clean.png"))
        assert report["quality_score"] > 0.6
        assert report["face_detected"] is True

    def test_blur_lowers_the_score(self, tmp_path):
        clean = quality.assess(self._write(tmp_path, "a.png"))
        blurred = quality.assess(self._write(tmp_path, "b.png", blur=8))
        assert blurred["quality_score"] < clean["quality_score"]

    def test_noise_cannot_masquerade_as_sharpness(self, tmp_path):
        """Plain Laplacian variance fails this: grain reads as detail."""
        clean = quality.assess(self._write(tmp_path, "a.png"))
        noisy_blur = quality.assess(self._write(tmp_path, "c.png", blur=6, noise=0.05))
        assert noisy_blur["quality_score"] < clean["quality_score"]
        assert noisy_blur["raw"]["noise_sigma"] > clean["raw"]["noise_sigma"]

    def test_darkness_lowers_the_score(self, tmp_path):
        clean = quality.assess(self._write(tmp_path, "a.png"))
        dark = quality.assess(self._write(tmp_path, "d.png", brightness=0.18))
        assert dark["quality_score"] < clean["quality_score"]

    def test_an_image_with_no_face_is_penalised(self, tmp_path):
        path = tmp_path / "noise.png"
        rng = np.random.default_rng(0)
        cv2.imwrite(str(path), rng.integers(0, 255, (300, 300, 3), dtype=np.uint8))
        report = quality.assess(path)
        assert report["face_detected"] is False
        assert report["quality_score"] < 0.6

    def test_unreadable_files_are_reported_not_raised(self, tmp_path):
        path = tmp_path / "broken.png"
        path.write_bytes(b"definitely not a png")
        assert quality.assess(path)["quality_score"] is None

    def test_components_are_exposed_for_the_officer(self, tmp_path):
        report = quality.assess(self._write(tmp_path, "a.png"))
        assert set(report["components"]) == {"sharpness", "exposure", "resolution", "visibility"}
