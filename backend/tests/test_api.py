"""End-to-end API tests, including the property that matters most:
a record with unknown fields still reaches the ranking.
"""
import io

import pytest

from app.synthetic import portrait


def _png(subject: int, variant: int = 0, **kw) -> bytes:
    import cv2
    ok, buf = cv2.imencode(".png", portrait(subject, variant, **kw))
    assert ok
    return buf.tobytes()


@pytest.fixture(scope="module")
def seeded(client):
    """A small purpose-built corpus: one true match, one near-miss, one sparse record."""
    probe = client.post("/api/cases", json={
        "case_number": "T-PROBE-001", "case_type": "missing", "name": "Test Subject",
        "age": {"mode": "range", "min": 23, "max": 27},
        "height": {"mode": "range", "min": 158, "max": 164},
        "sex": "Female", "build": "Slim", "last_seen_at": "2026-03-14T19:40:00",
        "location_text": "Bengaluru, Karnataka", "state": "Karnataka",
        "lat": 12.9716, "lon": 77.5946, "officer": "Insp. Test",
        "marks": [{"kind": "Scar", "body_location": "Eyebrow", "side": "Left",
                   "size_cm": 3.0, "shape": "Linear",
                   "description": "3 cm horizontal scar above the left eyebrow"}],
    }).json()

    true_match = client.post("/api/cases", json={
        "case_number": "T-CAND-TRUE", "case_type": "unidentified",
        "age": {"mode": "range", "min": 21, "max": 26},
        "height": {"mode": "range", "min": 160, "max": 166},
        "sex": "Female", "build": "Slim", "last_seen_at": "2026-08-03T22:30:00",
        "location_text": "Chennai, Tamil Nadu", "state": "Tamil Nadu",
        "lat": 13.0827, "lon": 80.2707,
        "marks": [{"kind": "Scar", "body_location": "Eyebrow", "side": "Left",
                   "size_cm": 3.0, "shape": "Linear",
                   "description": "small linear scar just over the left eyebrow"}],
    }).json()

    near_miss = client.post("/api/cases", json={
        "case_number": "T-CAND-SIDE", "case_type": "unidentified",
        "age": {"mode": "range", "min": 22, "max": 27},
        "height": {"mode": "range", "min": 159, "max": 165},
        "sex": "Female", "build": "Slim", "last_seen_at": "2026-07-01T09:00:00",
        "location_text": "Chennai, Tamil Nadu", "state": "Tamil Nadu",
        "lat": 13.08, "lon": 80.27,
        "marks": [{"kind": "Scar", "body_location": "Eyebrow", "side": "Right",
                   "size_cm": 3.0, "shape": "Linear",
                   "description": "short linear scar above the right eyebrow"}],
    }).json()

    sparse = client.post("/api/cases", json={
        "case_number": "T-CAND-SPARSE", "case_type": "unidentified",
        "age": {"mode": "unknown"}, "height": {"mode": "unknown"},
        "sex": None, "last_seen_at": "2026-06-01T09:00:00",
        "location_text": "Chennai, Tamil Nadu", "state": "Tamil Nadu",
        "lat": 13.08, "lon": 80.27,
    }).json()

    return {"probe": probe, "true": true_match, "near": near_miss, "sparse": sparse}


class TestMeta:
    def test_health_reports_live_backends(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert "face_embedding" in body["backends"]
        assert isinstance(body["backends"]["face_is_real_arcface"], bool)

    def test_root_carries_the_human_loop_notice(self, client):
        assert "identification" in client.get("/").json()["notice"].lower()


class TestCaseCreation:
    def test_uncertainty_modes_round_trip(self, client, seeded):
        body = client.get(f"/api/cases/{seeded['probe']['id']}").json()
        assert body["age"] == {"mode": "range", "exact": None, "min": 23.0, "max": 27.0}
        assert body["height"]["mode"] == "range"

    def test_unknown_is_preserved_as_unknown(self, client, seeded):
        body = client.get(f"/api/cases/{seeded['sparse']['id']}").json()
        assert body["age"]["mode"] == "unknown"
        assert body["age"]["min"] is None

    def test_range_requires_both_bounds(self, client):
        r = client.post("/api/cases", json={
            "case_type": "missing", "age": {"mode": "range", "min": 20},
        })
        assert r.status_code == 422

    def test_duplicate_case_number_is_rejected(self, client, seeded):
        r = client.post("/api/cases", json={"case_number": "T-PROBE-001", "case_type": "missing"})
        assert r.status_code == 409

    def test_case_numbers_are_generated_when_absent(self, client):
        r = client.post("/api/cases", json={"case_type": "unidentified"})
        assert r.status_code == 201
        assert r.json()["case_number"].startswith("CASE-")

    def test_marks_are_embedded_on_creation(self, client, seeded):
        marks = client.get(f"/api/cases/{seeded['probe']['id']}").json()["marks"]
        assert marks[0]["embedding_model"]

    def test_unknown_case_returns_404(self, client):
        assert client.get("/api/cases/does-not-exist").status_code == 404


class TestExtraction:
    def test_free_text_becomes_structured_fields(self, client):
        body = client.post("/api/marks/extract", json={
            "text": "3 cm horizontal scar above the left eyebrow"
        }).json()
        assert len(body["marks"]) == 1
        mark = body["marks"][0]
        assert mark["type"] == "scar"
        assert mark["location"] == "eyebrow"
        assert mark["side"] == "left"
        assert mark["size_cm"] == pytest.approx(3.0)
        assert mark["shape"] == "Linear"

    def test_tattoo_and_millimetres(self, client):
        body = client.post("/api/marks/extract", json={
            "text": "faded 40 mm anchor tattoo on the right shoulder"
        }).json()
        mark = body["marks"][0]
        assert mark["type"] == "tattoo"
        assert mark["side"] == "right"
        assert mark["size_cm"] == pytest.approx(4.0)
        assert "faded" in mark["attributes"]

    def test_one_passage_yields_several_marks(self, client):
        """The case the old single-mark contract silently dropped."""
        body = client.post("/api/marks/extract", json={
            "text": ("The person has a scar above his left eyebrow and a tattoo of a star "
                     "on his right forearm. He was last seen wearing a blue shirt.")
        }).json()
        kinds = {m["type"] for m in body["marks"]}
        assert kinds == {"scar", "tattoo"}

        scar = next(m for m in body["marks"] if m["type"] == "scar")
        tattoo = next(m for m in body["marks"] if m["type"] == "tattoo")
        assert (scar["location"], scar["side"]) == ("eyebrow", "left")
        assert (tattoo["location"], tattoo["side"]) == ("forearm", "right")
        assert any("blue shirt" in c for c in body["clothing"])

    def test_response_declares_its_provenance(self, client):
        body = client.post("/api/marks/extract", json={"text": "scar on the left cheek"}).json()
        assert body["source"] in ("rules", "gemini")
        assert isinstance(body["degraded"], bool)

    def test_empty_text_is_handled(self, client):
        body = client.post("/api/marks/extract", json={"text": "   "})
        assert body.status_code == 200
        assert body.json()["marks"] == []


class TestMatching:
    def test_the_true_match_ranks_first(self, client, seeded):
        body = client.post(f"/api/cases/{seeded['probe']['id']}/match").json()
        assert body["candidates"], "expected at least one candidate"
        assert body["candidates"][0]["case"]["case_number"] == "T-CAND-TRUE"

    def test_opposite_side_mark_is_ranked_below(self, client, seeded):
        body = client.post(f"/api/cases/{seeded['probe']['id']}/match").json()
        by_number = {c["case"]["case_number"]: c for c in body["candidates"]}
        assert by_number["T-CAND-TRUE"]["scores"]["marks"] > by_number["T-CAND-SIDE"]["scores"]["marks"]

    def test_a_record_with_unknown_fields_still_reaches_the_ranking(self, client, seeded):
        """The core promise: blank fields reduce evidence, never eligibility."""
        body = client.post(f"/api/cases/{seeded['probe']['id']}/match").json()
        numbers = [c["case"]["case_number"] for c in body["candidates"]]
        assert "T-CAND-SPARSE" in numbers

    def test_sparse_records_have_lower_coverage(self, client, seeded):
        body = client.post(f"/api/cases/{seeded['probe']['id']}/match").json()
        by_number = {c["case"]["case_number"]: c for c in body["candidates"]}
        assert by_number["T-CAND-SPARSE"]["coverage"] < by_number["T-CAND-TRUE"]["coverage"]

    def test_stage_timings_are_measured(self, client, seeded):
        body = client.post(f"/api/cases/{seeded['probe']['id']}/match").json()
        assert [s["id"] for s in body["stages"]] == [
            "ingest", "hard", "attr", "semantic", "face", "quality", "rank"
        ]
        assert all(s["duration_ms"] >= 0 for s in body["stages"])
        assert body["duration_ms"] > 0

    def test_hard_search_reports_a_real_funnel(self, client, seeded):
        body = client.post(f"/api/cases/{seeded['probe']['id']}/match").json()
        funnel = body["stages"][1]["substeps"]
        counts = [s["remaining"] for s in funnel]
        assert counts == sorted(counts, reverse=True)
        assert all(s["predicate"] for s in funnel)

    def test_evidence_and_concerns_are_populated(self, client, seeded):
        body = client.post(f"/api/cases/{seeded['probe']['id']}/match").json()
        top = body["candidates"][0]
        assert top["evidence"]
        assert isinstance(top["concerns"], list)

    def test_per_source_breakdown_is_returned(self, client, seeded):
        top = client.post(f"/api/cases/{seeded['probe']['id']}/match").json()["candidates"][0]
        assert set(top["sources"]) >= {"face", "marks", "demographic", "time", "location"}
        assert all("weight" in v for v in top["sources"].values())

    def test_runs_are_persisted(self, client, seeded):
        client.post(f"/api/cases/{seeded['probe']['id']}/match")
        runs = client.get(f"/api/cases/{seeded['probe']['id']}/matches").json()
        assert len(runs) >= 1


class TestImagesAndQuality:
    def test_upload_assesses_quality_and_embeds(self, client, seeded):
        r = client.post(
            f"/api/cases/{seeded['probe']['id']}/images",
            files={"file": ("face.png", io.BytesIO(_png(9001, 0)), "image/png")},
            data={"slot": "face"},
        )
        assert r.status_code == 201
        body = r.json()
        assert 0 <= body["quality_score"] <= 1
        assert body["embedding_model"]

    def test_embeddings_are_never_returned(self, client, seeded):
        images = client.get(f"/api/cases/{seeded['probe']['id']}").json()["images"]
        assert images
        assert all("embedding" not in i for i in images)

    def test_blurred_images_score_lower(self, client, seeded):
        sharp = client.post(
            f"/api/cases/{seeded['true']['id']}/images",
            files={"file": ("a.png", io.BytesIO(_png(9002, 0)), "image/png")},
            data={"slot": "face"},
        ).json()
        blurred = client.post(
            f"/api/cases/{seeded['true']['id']}/images",
            files={"file": ("b.png", io.BytesIO(_png(9002, 0, blur=6, noise=0.05)), "image/png")},
            data={"slot": "other"},
        ).json()
        assert blurred["quality_score"] < sharp["quality_score"]

    def test_non_image_uploads_are_rejected(self, client, seeded):
        r = client.post(
            f"/api/cases/{seeded['probe']['id']}/images",
            files={"file": ("x.txt", io.BytesIO(b"not an image"), "text/plain")},
        )
        assert r.status_code == 415


class TestHumanInTheLoop:
    def test_officer_answer_reorders_the_shortlist(self, client, seeded):
        run = client.post(f"/api/cases/{seeded['probe']['id']}/match").json()
        if not run.get("adaptive_question"):
            pytest.skip("candidates were not close enough to warrant a question")

        chosen = run["adaptive_question"]["options"][-1]["case_id"]
        after = client.post(f"/api/matches/{run['id']}/answer",
                            json={"chosen_case_id": chosen, "officer": "Insp. Test"}).json()
        confirmed = [c for c in after["candidates"] if c["officer_confirmed"]]
        assert confirmed and confirmed[0]["confidence"] > confirmed[0]["confidence_before"]

    def test_answering_with_a_non_candidate_is_rejected(self, client, seeded):
        run = client.post(f"/api/cases/{seeded['probe']['id']}/match").json()
        r = client.post(f"/api/matches/{run['id']}/answer",
                        json={"chosen_case_id": seeded["probe"]["id"]})
        assert r.status_code == 400

    def test_verification_never_asserts_identity(self, client, seeded):
        r = client.post(f"/api/cases/{seeded['probe']['id']}/verify", json={
            "candidate_case_id": seeded["true"]["id"],
            "decision": "verified", "officer": "Insp. Test",
        })
        assert r.status_code == 201
        assert "not constitute a confirmed identification" in r.json()["disclaimer"]

        case = client.get(f"/api/cases/{seeded['probe']['id']}").json()
        assert case["status"] == "PENDING PHYSICAL VERIFICATION"
        assert case["name"] == "Test Subject"     # identity untouched by the match

    def test_decisions_are_listed(self, client, seeded):
        rows = client.get(f"/api/cases/{seeded['probe']['id']}/verifications").json()
        assert any(r["decision"] == "verified" for r in rows)

    def test_invalid_decision_rejected(self, client, seeded):
        r = client.post(f"/api/cases/{seeded['probe']['id']}/verify", json={
            "candidate_case_id": seeded["true"]["id"], "decision": "confirmed_identity",
        })
        assert r.status_code == 422


class TestAnalytics:
    def test_summary(self, client, seeded):
        body = client.get("/api/analytics/summary").json()
        assert body["total_records"] >= 4

    def test_by_state(self, client, seeded):
        rows = client.get("/api/analytics/by-state").json()
        assert any(r["state"] == "Tamil Nadu" for r in rows)

    def test_map_points_carry_coordinates(self, client, seeded):
        rows = client.get("/api/analytics/map").json()
        assert rows and all(r["lat"] is not None and r["lon"] is not None for r in rows)

    def test_confidence_distribution_buckets(self, client, seeded):
        rows = client.get("/api/analytics/confidence-distribution").json()
        assert len(rows) == 7 and all("bucket" in r for r in rows)
