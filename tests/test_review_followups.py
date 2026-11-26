"""Regression tests for the PR #3 independent review findings C1-C4 (synthetic inputs only)."""
import csv
import io
import json
import sqlite3

import pytest

from app.observer import pipeline
from app.observer.classifiers.mock import MockClassifier
from app.services import ProtocolError, accept_sample, compute_plan, compute_summary, export_csv, export_json
from app.storage.db import SCHEMA_VERSION, Database
from app.storage.repository import Repository
from app.taste_engine.profiles import ensure_exp001, legacy_v1_topics

PID = "PRF-EXP-001-biathlon"


def _set_topics(repo, topics):
    """Write topics straight into the active profile (as an older AMAS would have stored them)."""
    repo.db.update("interest_profiles", "profile_id", PID, {"topics_json": topics})


def _restart(settings):
    """A fresh Repository on the same database file mimics an application restart."""
    repo = Repository(Database(settings.db_path), settings.data_dir)
    ensure_exp001(repo)
    return repo


# ---------------------------------------------------------------- C1


def test_untouched_legacy_profile_is_upgraded_once(settings):
    repo = _restart(settings)
    _set_topics(repo, legacy_v1_topics())
    v = repo.get_profile(PID)["version"]
    repo = _restart(settings)
    p = repo.get_profile(PID)
    assert p["version"] == v + 1 and "pursuit" in p["topics"][0]["context_keywords"]
    repo = _restart(settings)
    assert repo.get_profile(PID)["version"] == v + 1  # idempotent


def _edit_adjacent(t):
    t[1]["keywords"].append("user-adjacent-keyword")


def _add_topic(t):
    t.append({"topic_id": "user-topic", "label": "User topic", "tier": "adjacent", "polarity": "positive",
              "keywords": ["custom sport"]})


def _edit_weight(t):
    t[0]["target_weight"] = 0.35


def _edit_description(t):
    t[0]["description"] = "User-authored description"


def _edit_context(t):
    t[0]["context_keywords"] = ["user-context"]


@pytest.mark.parametrize("edit", [_edit_adjacent, _add_topic, _edit_weight, _edit_description, _edit_context])
def test_edited_legacy_profile_survives_restarts(settings, edit):
    repo = _restart(settings)
    topics = legacy_v1_topics()
    edit(topics)
    edited = repo.update_profile(PID, {"topics": topics})
    for _ in range(2):
        repo = _restart(settings)
        p = repo.get_profile(PID)
        assert p["version"] == edited["version"] and p["topics"] == edited["topics"]


def test_profile_upgrade_never_relabels_observations(settings):
    repo = _restart(settings)
    _set_topics(repo, legacy_v1_topics())
    sid = repo.create_session("EXP-001", checkpoint="T0", capture_method="manual_entry")["session_id"]
    o = repo.add_observation(sid, {"target_match": "direct", "topic_label": "biathlon", "review_status": "auto_accepted",
                                   "caption_text": "Police pursuit", "classifier_version": "mock-keyword-v1"})
    repo = _restart(settings)
    assert repo.get_observation(o["observation_id"])["target_match"] == "direct"


# ---------------------------------------------------------------- C2


def _t0(repo, n, **values):
    sid = repo.create_session("EXP-001", checkpoint="T0", capture_method="manual_entry")["session_id"]
    row = {"target_match": "unrelated", "recommendation_status": "recommended", "review_status": "confirmed",
           "is_ad": False, **values}
    for _ in range(n):
        repo.add_observation(sid, dict(row))
    return sid


def _ready(repo):
    return compute_summary(repo, "EXP-001")["baseline_readiness"]["ready"]


def _short_and_full(repo):
    a, b = _t0(repo, 40), _t0(repo, 50)
    accept_sample(repo, a, deviation_note="Recording stopped after 40 Reels; size deviation only.")
    accept_sample(repo, b)
    assert _ready(repo)
    return a, b


def test_unchanged_short_sample_with_deviation_still_counts(repo):
    _short_and_full(repo)
    assert compute_plan(repo, "EXP-001")["status"] == "intervene"


def _needs_review(repo, sid):
    o = repo.list_observations(session_id=sid)[0]
    repo.update_observation(o["observation_id"], {"review_status": "needs_review"})


def _conflict(repo, sid):
    o = repo.list_observations(session_id=sid)[0]
    repo.update_observation(o["observation_id"], {"eligibility_conflict": True})


def _relabel(repo, sid):
    o = repo.list_observations(session_id=sid)[0]
    pipeline.apply_correction(repo, o["observation_id"], {"target_match": "direct", "topic_label": "biathlon"})


def _add(repo, sid):
    repo.add_observation(sid, {"target_match": "unrelated", "recommendation_status": "recommended",
                               "review_status": "confirmed", "is_ad": False})


def _delete(repo, sid):
    repo.delete_observation(repo.list_observations(session_id=sid)[-1]["observation_id"])


EDITS = [_needs_review, _conflict, _relabel, _add, _delete]


@pytest.mark.parametrize("edit", EDITS)
@pytest.mark.parametrize("which", ["deviation", "ordinary"])
def test_edit_after_acceptance_requires_reacceptance(repo, edit, which):
    a, b = _short_and_full(repo)
    edit(repo, a if which == "deviation" else b)
    r = compute_summary(repo, "EXP-001")["baseline_readiness"]
    assert not r["ready"] and any("changed since acceptance" in p for p in r["problems"])
    assert compute_plan(repo, "EXP-001")["status"] == "collect_baseline"


def test_boundary_edit_and_reclassification_after_acceptance(repo, settings):
    sid = repo.create_session("EXP-001", checkpoint="T0", capture_method="synthetic")["session_id"]
    repo.add_frames(sid, [dict(frame_index=i, offset_seconds=float(i), path="synthetic.jpg") for i in range(12)])
    rows = pipeline.set_manual_boundaries(repo, sid, [4.0, 8.0])
    for row in rows:
        repo.update_observation(row["observation_id"], {"target_match": "unrelated", "review_status": "confirmed",
                                                        "recommendation_status": "recommended", "is_ad": False})
    accept_sample(repo, sid, deviation_note="Synthetic three-Reel sample.")
    accept_sample(repo, _t0(repo, 50))
    assert _ready(repo)
    pipeline.merge_with_next(repo, rows[0]["observation_id"])
    assert not _ready(repo)
    # re-accepting the changed sample is refused while a Reel needs review, even with the old deviation note
    with pytest.raises(ProtocolError):
        accept_sample(repo, sid)
    pipeline.classify_session(repo, settings, sid, MockClassifier())
    assert not _ready(repo)


def test_new_deviation_scope_requires_new_acceptance(repo):
    """A size-only deviation does not authorise a later review problem, even if the revision were unchanged."""
    a, _ = _short_and_full(repo)
    s = repo.get_session(a)
    assert s["deviation_scope"] == ["40 of 50 Reels recorded"]
    _needs_review(repo, a)
    with pytest.raises(ProtocolError):
        accept_sample(repo, a)  # still incomplete and no note: refused
    accept_sample(repo, a, deviation_note="Short recording and one Reel I cannot judge; founder-approved.")
    assert _ready(repo)
    assert len(repo.get_session(a)["deviation_scope"]) == 2


def test_api_and_strategist_agree_after_new_problem(client):
    r = client.app.state.repo
    a, _ = _short_and_full(r)
    _needs_review(r, a)
    _conflict(r, a)
    plan = client.get("/api/experiments/EXP-001/plan").json()
    assert plan["status"] in ("collect_baseline", "review_data") and plan["recommended_actions"] == []
    body = {"action_type": "search_and_watch_target", "actuator": "manual"}
    resp = client.post("/api/experiments/EXP-001/interventions", json=body)
    assert resp.status_code == 409
    resp = client.post("/api/experiments/EXP-001/interventions",
                       json={**body, "override_baseline_check": True, "override_reason": "Founder-approved test"})
    assert resp.status_code == 200 and resp.json()["parameters"]["baseline_override"]["problems"]


def test_api_blocks_on_open_review_items_outside_baseline(client):
    """The strategist withholds suggestions for review items in any pre-intervention session; so does the API."""
    r = client.app.state.repo
    for _ in range(2):
        accept_sample(r, _t0(r, 50))
    adhoc = r.create_session("EXP-001", checkpoint="ADHOC", capture_method="manual_entry")["session_id"]
    r.add_observation(adhoc, {"review_status": "pending"})
    assert client.get("/api/experiments/EXP-001/plan").json()["status"] == "review_data"
    resp = client.post("/api/experiments/EXP-001/interventions",
                       json={"action_type": "search_and_watch_target", "actuator": "manual"})
    assert resp.status_code == 409


# ---------------------------------------------------------------- C3


def _merged_session(repo):
    sid = repo.create_session("EXP-001", checkpoint="T0", capture_method="synthetic")["session_id"]
    repo.add_frames(sid, [dict(frame_index=i, offset_seconds=float(i), path="synthetic.jpg") for i in range(12)])
    rows = pipeline.set_manual_boundaries(repo, sid, [4.0, 8.0])
    for i, row in enumerate(rows):
        repo.update_observation(row["observation_id"], {"target_match": "unrelated", "topic_label": f"label-{i}",
                                                        "review_status": "confirmed",
                                                        "recommendation_status": "recommended", "is_ad": False})
    first, absorbed = rows[0]["observation_id"], rows[1]["observation_id"]
    pipeline.merge_with_next(repo, first)
    return sid, first, absorbed


def _history_ok(o, absorbed):
    h = o["boundary_history"]
    return (len(h) == 1 and h[0]["old"] == [0.0, 4.0] and h[0]["new"] == [0.0, 8.0]
            and h[0]["absorbed"][0]["observation_id"] == absorbed and h[0]["absorbed"][0]["topic_label"] == "label-1"
            and h[0]["previous_labels"]["review_status"] == "confirmed")


def test_merge_history_survives_classification_correction_and_export(repo, settings):
    sid, first, absorbed = _merged_session(repo)
    assert repo.get_observation(absorbed, missing_ok=True) is None
    assert _history_ok(repo.get_observation(first), absorbed)
    for _ in range(2):  # repeated classification
        pipeline.classify_session(repo, settings, sid, MockClassifier())
        o = repo.get_observation(first)
        assert _history_ok(o, absorbed)
        assert any(absorbed in e and e.startswith("Boundaries changed") for e in o["classification_evidence"])
    pipeline.apply_correction(repo, first, {"target_match": "unrelated", "topic_label": "human"})
    assert _history_ok(repo.get_observation(first), absorbed)
    pipeline.classify_session(repo, settings, sid, MockClassifier(), include_reviewed=True)
    assert _history_ok(repo.get_observation(first), absorbed)
    exported = next(o for o in export_json(repo, "EXP-001")["observations"] if o["observation_id"] == first)
    assert _history_ok(exported, absorbed)
    rows = list(csv.DictReader(io.StringIO(export_csv(repo, "EXP-001"))))
    row = next(r for r in rows if r["observation_id"] == first)
    assert absorbed in row["boundary_history"] and json.loads(row["boundary_history"])[0]["new"] == [0.0, 8.0]


def test_chained_merges_keep_earlier_history(repo):
    sid, first, absorbed = _merged_session(repo)
    pipeline.merge_with_next(repo, first)  # absorb the third Reel too
    h = repo.get_observation(first)["boundary_history"]
    assert len(h) == 2 and h[0]["absorbed"][0]["observation_id"] == absorbed
    assert h[1]["old"] == [0.0, 8.0] and h[1]["new"] == [0.0, 12.0]


def test_untouched_rows_keep_empty_history(repo):
    sid, first, _ = _merged_session(repo)
    others = [o for o in repo.list_observations(session_id=sid) if o["observation_id"] != first]
    assert others and all(o["boundary_history"] == [] for o in others)


# ---------------------------------------------------------------- C4


@pytest.mark.parametrize("values", [
    {"is_ad": True},
    {"recommendation_status": "followed_account"},
    {"recommendation_status": "search_result"},
])
def test_baseline_without_eligible_exposures_does_not_unlock(repo, values):
    for _ in range(2):
        accept_sample(repo, _t0(repo, 50, **values))
    s = compute_summary(repo, "EXP-001")
    r = s["baseline_readiness"]
    assert r["counted_sessions"] == 2 and r["eligible_exposures"] == 0 and not r["ready"]
    assert any("no eligible recommendation exposures" in p for p in r["problems"])
    plan = compute_plan(repo, "EXP-001")
    assert plan["status"] == "collect_baseline" and plan["recommended_actions"] == []


def test_baseline_with_eligible_exposures_unlocks(repo):
    accept_sample(repo, _t0(repo, 50, is_ad=True))
    sid = _t0(repo, 45)
    for _ in range(5):
        repo.add_observation(sid, {"target_match": "unrelated", "recommendation_status": "recommended",
                                   "review_status": "confirmed", "is_ad": True})
    accept_sample(repo, sid)
    r = compute_summary(repo, "EXP-001")["baseline_readiness"]
    assert r["ready"] and r["eligible_exposures"] == 45
    assert compute_plan(repo, "EXP-001")["status"] == "intervene"


def test_zero_eligible_baseline_override_is_recorded(client):
    r = client.app.state.repo
    for _ in range(2):
        accept_sample(r, _t0(r, 50, is_ad=True))
    body = {"action_type": "search_and_watch_target", "actuator": "manual"}
    assert client.post("/api/experiments/EXP-001/interventions", json=body).status_code == 409
    resp = client.post("/api/experiments/EXP-001/interventions",
                       json={**body, "override_baseline_check": True, "override_reason": "Founder exception"})
    assert resp.status_code == 200
    assert any("no eligible" in p for p in resp.json()["parameters"]["baseline_override"]["problems"])


# ---------------------------------------------------------------- migration v2 -> v3


def test_v2_database_migrates_and_old_acceptances_need_renewal(settings):
    repo = _restart(settings)
    sid = _t0(repo, 50)
    repo.db.close()
    con = sqlite3.connect(settings.db_path)
    # emulate a v2 database: accepted without revision tracking, no boundary_history column
    con.execute("UPDATE observation_sessions SET sample_status='accepted', accepted_at='2026-11-26T12:00:00+00:00'")
    con.execute("ALTER TABLE content_observations DROP COLUMN boundary_history")
    con.execute("ALTER TABLE observation_sessions DROP COLUMN accepted_revision")
    con.execute("ALTER TABLE observation_sessions DROP COLUMN deviation_scope")
    con.execute("UPDATE meta SET value='2' WHERE key='schema_version'")
    con.commit()
    con.close()
    repo = _restart(settings)
    assert repo.db.query_one("SELECT value FROM meta WHERE key='schema_version'")["value"] == str(SCHEMA_VERSION)
    o = repo.list_observations(session_id=sid)[0]
    assert o["boundary_history"] == [] and o["review_status"] == "confirmed"
    r = compute_summary(repo, "EXP-001")["baseline_readiness"]
    assert r["sessions"][0]["accepted"] and not r["sessions"][0]["counts"]
    assert any("accepted before revision tracking" in p for p in r["problems"])
