"""Regression tests for the PR #7 independent review findings V1 and V2 (synthetic inputs only)."""
import csv
import io
import json

from app.evaluator.metrics import experiment_summary
from app.observer import pipeline
from app.observer.classifiers.mock import MockClassifier
from app.services import export_csv, export_json


def _classified_unknown(client, caption="Police pursuit on the highway"):
    """Run the real local classifier on a synthetic caption: UNKNOWN with machine confidence 0.3."""
    r = client.app.state.repo
    sid = r.create_session("EXP-001", checkpoint="T0", capture_method="synthetic")["session_id"]
    o = r.add_observation(sid, {"target_match": "unknown", "review_status": "pending", "caption_text": caption,
                                "recommendation_status": "recommended", "is_ad": False})
    pipeline.classify_session(r, client.app.state.settings, sid, MockClassifier())
    return r.get_observation(o["observation_id"])


def _exports(client, oid):
    r = client.app.state.repo
    j = next(x for x in json.loads(json.dumps(export_json(r, "EXP-001")))["observations"]
             if x["observation_id"] == oid)
    c = next(x for x in csv.DictReader(io.StringIO(export_csv(r, "EXP-001"))) if x["observation_id"] == oid)
    return j, c


# ---------------------------------------------------------------- V1


def test_confirming_unknown_clears_exposed_confidence(client):
    o = _classified_unknown(client)
    assert o["target_match"] == "unknown" and o["confidence"] == 0.3
    resp = client.patch(f"/api/observations/{o['observation_id']}", json={"confirm": True})  # "Confirm label"
    assert resp.status_code == 200
    out = resp.json()
    assert out["review_status"] == "confirmed" and out["target_match"] == "unknown"
    assert out["confidence"] is None and out["machine_label_json"]["confidence"] == 0.3
    j, c = _exports(client, o["observation_id"])
    assert j["confidence"] is None and j["machine_label_json"]["confidence"] == 0.3
    assert c["confidence"] == "" and c["review_status"] == "confirmed"
    # A non-null confidence on UNKNOWN is still refused, consistently with the confirm path.
    assert client.patch(f"/api/observations/{o['observation_id']}", json={"confidence": 0.3}).status_code == 400


def test_known_topic_changed_to_unknown_clears_confidence(client):
    o = _classified_unknown(client, caption="Biathlon World Cup sprint")
    assert o["target_match"] == "direct" and o["confidence"] is not None
    machine = o["confidence"]
    out = client.patch(f"/api/observations/{o['observation_id']}", json={"target_match": "unknown"}).json()
    assert out["confidence"] is None and out["machine_label_json"]["confidence"] == machine
    resp = client.patch(f"/api/observations/{o['observation_id']}",
                        json={"target_match": "unknown", "confidence": 0.5})
    assert resp.status_code == 400


def test_unrelated_edit_of_unknown_keeps_omitted_semantics(client):
    o = _classified_unknown(client)
    out = client.patch(f"/api/observations/{o['observation_id']}", json={"notes": "checked later"}).json()
    assert out["confidence"] == 0.3 and out["review_status"] == o["review_status"]


def test_confirming_known_label_keeps_confidence(client):
    o = _classified_unknown(client, caption="Biathlon World Cup sprint")
    out = client.patch(f"/api/observations/{o['observation_id']}", json={"confirm": True}).json()
    assert out["review_status"] == "confirmed" and out["confidence"] == o["confidence"]


def test_machine_confidence_is_saved_before_clearing_when_missing(client):
    r = client.app.state.repo
    sid = r.create_session("EXP-001", checkpoint="T0", capture_method="synthetic")["session_id"]
    o = r.add_observation(sid, {"target_match": "unknown", "confidence": 0.25, "classifier_version": "older-v0",
                                "review_status": "needs_review", "recommendation_status": "recommended"})
    out = client.patch(f"/api/observations/{o['observation_id']}", json={"confirm": True}).json()
    assert out["confidence"] is None and out["machine_label_json"] == {"confidence": 0.25}


# ---------------------------------------------------------------- V2


def _ttf_case(observed_at, captured_at="2026-06-01T10:00:00Z", completed_at="2026-06-01T09:00:00+00:00"):
    exp = {"experiment_id": "X", "target_topic": "biathlon", "target_share": 0.2}
    sessions = [{"session_id": "t2", "checkpoint": "T2", "captured_at": captured_at, "captured_at_source": "user"}]
    rows = [{"session_id": "t2", "sequence_number": 1, "target_match": "direct", "observed_at": observed_at,
             "recommendation_status": "recommended", "review_status": "confirmed", "is_ad": False}]
    acts = [{"action_id": "a1", "status": "completed", "completed_at": completed_at}]
    return experiment_summary(exp, sessions, rows, acts)


def _tz_warnings(s):
    return [w for w in s["warnings"] if "timezone" in w.lower() or "read as utc" in w.lower()]


def test_isolated_naive_observed_at_is_reported():
    s = _ttf_case("2026-06-01T10:05:00")  # legacy, no offset; session and intervention are valid
    ttf = s["time_to_first_target"]
    assert ttf["measurable"] and ttf["hours_after_intervention"] == 1.08
    assert s["sessions"][0]["capture_time_verified"]
    assert ttf["exposure_time_source"] == "observed_at" and ttf["exposure_timezone_assumed_utc"]
    assert not ttf["intervention_timezone_assumed_utc"] and ttf["time_verified"] is False
    assert ttf["exposure_time_used"] == "2026-06-01T10:05:00+00:00"
    assert any("Time to first target is unverified" in w and "exposure time" in w for w in _tz_warnings(s))


def test_all_aware_timestamps_have_no_assumption_warning():
    s = _ttf_case("2026-06-01T11:05:00+01:00")
    ttf = s["time_to_first_target"]
    assert ttf["hours_after_intervention"] == 1.08 and ttf["time_verified"]
    assert not ttf["exposure_timezone_assumed_utc"] and not ttf["intervention_timezone_assumed_utc"]
    assert _tz_warnings(s) == []


def test_naive_intervention_anchor_is_reported():
    s = _ttf_case("2026-06-01T10:05:00Z", completed_at="2026-06-01T09:00:00")
    ttf = s["time_to_first_target"]
    assert ttf["intervention_timezone_assumed_utc"] and not ttf["exposure_timezone_assumed_utc"]
    assert not ttf["time_verified"]
    assert any("intervention completion time" in w for w in s["warnings"])


def test_session_fallback_exposure_time_provenance():
    s = _ttf_case(None, captured_at="2026-06-01T10:00:00")  # no observed_at; legacy naive session time
    ttf = s["time_to_first_target"]
    assert ttf["exposure_time_source"] == "session_captured_at" and ttf["exposure_timezone_assumed_utc"]
    assert not ttf["time_verified"]
    s = _ttf_case(None)  # valid session time is used and verified
    assert s["time_to_first_target"]["time_verified"] and _tz_warnings(s) == []
