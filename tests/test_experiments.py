import csv
import io
import json

import pytest

from app.actuator.base import ActuatorUnavailable, FutureAuthorizedActuator, ManualActuator, MockActuator
from app.adapters.instagram_manual import InstagramManualAdapter
from app.demo import DEMO_ID, seed_demo
from app.services import compute_plan, compute_summary, export_csv, export_json
from tests.conftest import needs_ffmpeg
from tests.fixtures.synthetic_video import make_reels_video


def test_actuators_respect_authorization(repo):
    exp = repo.get_experiment("EXP-001")
    ad = InstagramManualAdapter()
    with pytest.raises(ActuatorUnavailable):
        MockActuator(ad).plan(exp, "search_and_watch_target", {}, "")
    with pytest.raises(ActuatorUnavailable):
        FutureAuthorizedActuator(ad).plan(exp, "search_and_watch_target", {}, "")
    v = ManualActuator(ad).plan(exp, "search_and_watch_target", {"query": "biathlon"}, "")
    assert v["status"] == "pending_user" and "biathlon" in v["instructions"] and v["authorization"] is None
    a = repo.add_intervention("EXP-001", v)
    done = ManualActuator(ad).complete(a, completed_at=None, evidence_notes="watched 10", skipped=False)
    assert done["authorization"] == "user_manual" and done["status"] == "completed"


def test_demo_is_separated_and_labelled(repo):
    seed_demo(repo)
    demo = compute_summary(repo, DEMO_ID)
    real = compute_summary(repo, "EXP-001")
    assert demo["is_demo"] is True and real["is_demo"] is False
    assert real["sessions"] == [] and len(demo["sessions"]) == 6
    assert all(o["is_demo"] for o in repo.list_observations(experiment_id=DEMO_ID))
    assert export_json(repo, DEMO_ID)["data_label"].startswith("SIMULATED")
    assert demo["baseline"]["exposures_eligible"] > 0 and demo["time_to_first_target"]["measurable"]
    # reseeding is deterministic and replaces the old demo
    seed_demo(repo)
    again = compute_summary(repo, DEMO_ID)
    assert again["trend"][2]["direct_share"] == demo["trend"][2]["direct_share"]


def test_strategist_flow(repo):
    plan = compute_plan(repo, "EXP-001")
    assert plan["status"] == "collect_baseline" and plan["next_checkpoint"]["checkpoint"] == "T0"
    for label in ("A", "B"):
        s = repo.create_session("EXP-001", checkpoint="T0", capture_method="manual_entry", label=label)
        for i in range(50):
            repo.add_observation(s["session_id"], {"target_match": "unrelated", "recommendation_status": "recommended",
                                                   "review_status": "confirmed"})
    plan = compute_plan(repo, "EXP-001")
    assert plan["status"] == "intervene" and plan["recommended_actions"][0]["action_type"] == "search_and_watch_target"
    assert plan["next_checkpoint"]["checkpoint"] == "T1"


def test_api_manual_baseline_compare_and_export(client):
    exps = client.get("/api/experiments").json()
    assert [e["experiment_id"] for e in exps] == ["EXP-001"]
    ids = {}
    for cp, label, direct in (("T0", "A", 0), ("T0", "B", 1), ("T2", "post", 10)):
        s = client.post("/api/experiments/EXP-001/sessions",
                        json={"checkpoint": cp, "label": label, "capture_method": "manual_entry"}).json()
        ids[label] = s["session_id"]
        body = [{"target_match": "direct", "topic_label": "biathlon", "recommendation_status": "recommended"}] * direct
        body += [{"target_match": "unrelated", "recommendation_status": "recommended"}] * (50 - direct)
        assert len(client.post(f"/api/sessions/{s['session_id']}/observations/bulk", json=body).json()) == 50
        if cp == "T0" and label == "B":
            a = client.post("/api/experiments/EXP-001/interventions",
                            json={"action_type": "search_and_watch_target", "actuator": "manual"}).json()
            r = client.post(f"/api/interventions/{a['action_id']}/complete", json={"evidence_notes": "done"})
            assert r.json()["status"] == "completed"
    d = client.get("/api/experiments/EXP-001").json()
    assert d["summary"]["baseline"]["direct_share"] == 0.01
    assert d["summary"]["latest"]["vs_baseline"]["change_pp"] == 19.0
    assert client.post("/api/experiments/EXP-001/metrics").status_code == 200

    # correction
    o = client.get(f"/api/sessions/{ids['post']}").json()["observations"][-1]
    p = client.patch(f"/api/observations/{o['observation_id']}", json={"target_match": "adjacent"}).json()
    assert p["review_status"] == "corrected"

    # exports
    r = client.get("/api/experiments/EXP-001/export?format=csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 150 and rows[0]["experiment_id"] == "EXP-001" and "checkpoint" in rows[0]
    j = json.loads(client.get("/api/experiments/EXP-001/export?format=json").text)
    assert j["is_demo"] is False and len(j["observations"]) == 150 and j["derived_metrics"]["baseline"]

    # mock actuator refused on real experiment; authorized actuator always refused
    assert client.post("/api/experiments/EXP-001/interventions",
                       json={"action_type": "engage_target", "actuator": "mock"}).status_code == 403
    assert client.post("/api/experiments/EXP-001/interventions",
                       json={"action_type": "engage_target", "actuator": "authorized"}).status_code == 403

    # external classifier blocked by default
    r = client.post(f"/api/sessions/{ids['A']}/classify", json={"classifier": "anthropic"})
    assert r.status_code == 403

    # delete session removes derived data
    assert client.delete(f"/api/sessions/{ids['A']}").status_code == 200
    assert client.get(f"/api/sessions/{ids['A']}").status_code == 404


def test_api_serves_dashboard(client):
    r = client.get("/")
    assert r.status_code == 200 and "AMAS Control Center" in r.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/status").json()["external_providers_enabled"] is False


@needs_ffmpeg
def test_api_upload_recording(client, tmp_path):
    video = make_reels_video(tmp_path / "rec.mov", [5, 6, 7])
    s = client.post("/api/experiments/EXP-001/sessions", json={"checkpoint": "T0", "label": "rec"}).json()
    with open(video, "rb") as f:
        r = client.post(f"/api/sessions/{s['session_id']}/recording", files={"file": ("rec.mov", f, "video/quicktime")})
    assert r.status_code == 200, r.text
    d = client.get(f"/api/sessions/{s['session_id']}").json()
    assert len(d["observations"]) == 3 and d["frame_count"] >= 17
    fid = d["observations"][0]["representative_frame_id"]
    assert client.get(f"/api/frames/{fid}").headers["content-type"] == "image/jpeg"
    assert client.post(f"/api/sessions/{s['session_id']}/classify", json={"classifier": "mock"}).status_code == 200
    r = client.post(f"/api/sessions/{s['session_id']}/eligibility", json={"recommendation_status": "recommended"})
    assert r.json()["updated"] == 3
