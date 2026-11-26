"""Regression tests for the PR #1 independent review findings R1-R4 (synthetic inputs only)."""
import sqlite3

import pytest

from app.models.schemas import TargetMatch
from app.observer import pipeline
from app.observer.classifiers.base import ClassificationInput, ClassificationResult, Classifier
from app.observer.classifiers.mock import MockClassifier
from app.services import ProtocolError, accept_sample, compute_plan, compute_summary
from app.storage.db import SCHEMA_VERSION, Database
from app.storage.repository import Repository
from app.taste_engine.profiles import LEGACY_V1_BIATHLON_KEYWORDS, ensure_exp001

LABELS = dict(target_match="unrelated", topic_label="synthetic", review_status="confirmed",
              recommendation_status="recommended", is_ad=False, classifier_version="human-manual")


def _three_item_session(repo):
    sid = repo.create_session("EXP-001", checkpoint="T0", capture_method="synthetic")["session_id"]
    repo.add_frames(sid, [dict(frame_index=i, offset_seconds=float(i), path="synthetic.jpg", ahash=f"{i:016x}")
                          for i in range(12)])
    pipeline.set_manual_boundaries(repo, sid, [4.0, 8.0])
    rows = repo.list_observations(session_id=sid)
    for i, o in enumerate(rows):
        repo.update_observation(o["observation_id"], {**LABELS, "topic_label": f"synthetic-{i}"})
    return sid, repo.list_observations(session_id=sid)


LABEL_KEYS = ("observation_id", "target_match", "topic_label", "review_status", "recommendation_status", "is_ad",
              "classifier_version", "video_offset_seconds", "segment_end_seconds")


def _labels(o):
    return {k: o[k] for k in LABEL_KEYS}


# ---------------------------------------------------------------- R1

def test_merge_keeps_untouched_reel(repo):
    sid, before = _three_item_session(repo)
    after = pipeline.merge_with_next(repo, before[0]["observation_id"])
    assert len(after) == 2
    # untouched third Reel keeps ID, labels, eligibility, ad state, review status and provenance
    assert _labels(after[1]) == _labels(before[2])
    assert after[1]["sequence_number"] == 2
    # the changed Reel keeps its ID but must be re-reviewed; the absorbed Reel is recorded as evidence
    merged = after[0]
    assert merged["observation_id"] == before[0]["observation_id"]
    assert merged["review_status"] == "needs_review" and merged["segment_end_seconds"] == before[1]["segment_end_seconds"]
    assert any(before[1]["observation_id"] in e for e in merged["classification_evidence"])
    assert repo.get_session(sid)["observation_count"] == 2


def test_split_keeps_other_reels(repo):
    sid, before = _three_item_session(repo)
    after = pipeline.split_at(repo, before[1]["observation_id"], 6.0)
    assert len(after) == 4
    assert _labels(after[0]) == _labels(before[0]) and _labels(after[3]) == _labels(before[2])
    assert after[1]["observation_id"] == before[1]["observation_id"] and after[1]["review_status"] == "needs_review"
    assert after[2]["review_status"] == "pending" and after[2]["target_match"] == "unknown"
    assert after[2]["recommendation_status"] == "undetermined"
    assert [o["sequence_number"] for o in after] == [1, 2, 3, 4]


def test_invalid_split_changes_nothing(repo):
    sid, before = _three_item_session(repo)
    with pytest.raises(ValueError):
        pipeline.split_at(repo, before[1]["observation_id"], 99.0)
    assert repo.list_observations(session_id=sid) == before


def test_failed_reconciliation_rolls_back(repo, monkeypatch):
    sid, before = _three_item_session(repo)
    real = repo.apply_segment_plan

    def broken(session_id, plan, delete_ids):
        # a plan referencing a row that no longer exists fails mid-transaction
        return real(session_id, plan + [("keep", {"observation_id": "obs_missing"})], delete_ids)

    monkeypatch.setattr(repo, "apply_segment_plan", broken)
    with pytest.raises(RuntimeError):
        pipeline.merge_with_next(repo, before[0]["observation_id"])
    assert repo.list_observations(session_id=sid) == before
    assert repo.get_session(sid)["observation_count"] == 3


def test_reapplying_same_boundaries_is_lossless(repo):
    sid, before = _three_item_session(repo)
    after = pipeline.set_manual_boundaries(repo, sid, [4.0, 8.0])
    assert [_labels(o) for o in after] == [_labels(o) for o in before]


def test_manual_entries_survive_boundary_edit(repo):
    sid, before = _three_item_session(repo)
    manual = repo.add_observation(sid, {**LABELS, "segmentation_method": "manual_entry"})
    after = pipeline.merge_with_next(repo, before[0]["observation_id"])
    assert after[-1]["observation_id"] == manual["observation_id"] and after[-1]["review_status"] == "confirmed"


# ---------------------------------------------------------------- R2

def _classify(repo, text):
    profile = repo.get_profile("PRF-EXP-001-biathlon")
    return MockClassifier().classify(ClassificationInput("synthetic", profile, caption_text=text))


@pytest.mark.parametrize("text", [
    "Police pursuit on the highway",
    "Mass start in cycling",
    "Sprint relay at the athletics track",
    "IBU announcement today",
    "Shooting range day with friends",
])
def test_ambiguous_terms_are_not_direct(repo, text):
    r = _classify(repo, text)
    assert r.target_match == TargetMatch.UNKNOWN and r.confidence < 0.5


@pytest.mark.parametrize("text", ["Follow", "Follow · Like · Share", "Reels", "Original audio"])
def test_ui_only_text_is_unknown(repo, text):
    r = _classify(repo, text)
    assert r.target_match == TargetMatch.UNKNOWN and r.confidence == 0


@pytest.mark.parametrize("text", [
    "Biathlon mass start in Oberhof",
    "#biathlon",
    "Биатлон: гонка преследования",
    "IBU World Cup pursuit highlights",
])
def test_explicit_biathlon_is_direct(repo, text):
    r = _classify(repo, text)
    assert r.target_match == TargetMatch.DIRECT and r.topic_label == "biathlon"


@pytest.mark.parametrize("text,topic", [
    ("Cross-country skiing sprint in Davos", "cross_country_skiing"),
    ("Ski jumping at the Winter Olympics", "winter_sports"),
])
def test_adjacent_winter_sports_still_supported(repo, text, topic):
    r = _classify(repo, text)
    assert r.target_match == TargetMatch.ADJACENT and r.topic_label == topic


def test_legacy_profile_keywords_are_context_only(repo):
    # A user database created by Sprint 1 still holds the old DIRECT keyword list.
    legacy = {"topic_id": "biathlon", "label": "Biathlon", "tier": "direct", "keywords": sorted(LEGACY_V1_BIATHLON_KEYWORDS)}
    profile = {"topics": [legacy]}
    r = MockClassifier().classify(ClassificationInput("x", profile, caption_text="Police pursuit on the highway"))
    assert r.target_match == TargetMatch.UNKNOWN


def test_legacy_exp001_profile_is_upgraded_once(settings):
    repo = Repository(Database(settings.db_path), settings.data_dir)
    ensure_exp001(repo)
    pid = "PRF-EXP-001-biathlon"
    topics = repo.get_profile(pid)["topics"]
    topics[0] = {**topics[0], "keywords": sorted(LEGACY_V1_BIATHLON_KEYWORDS), "context_keywords": []}
    repo.db.update("interest_profiles", "profile_id", pid, {"topics_json": topics})
    v_before = repo.get_profile(pid)["version"]
    ensure_exp001(repo)
    upgraded = repo.get_profile(pid)
    assert upgraded["version"] == v_before + 1 and "pursuit" in upgraded["topics"][0]["context_keywords"]
    assert "pursuit" not in upgraded["topics"][0]["keywords"]
    ensure_exp001(repo)
    assert repo.get_profile(pid)["version"] == v_before + 1


def test_user_edited_profile_is_not_upgraded(repo):
    pid = "PRF-EXP-001-biathlon"
    topics = repo.get_profile(pid)["topics"]
    topics[0] = {**topics[0], "keywords": ["biathlon", "my own term"]}
    edited = repo.update_profile(pid, {"topics": topics})
    ensure_exp001(repo)
    assert repo.get_profile(pid)["version"] == edited["version"]


# ---------------------------------------------------------------- R3

class FollowedFixture(Classifier):
    name = "synthetic-followed"

    def classify(self, item):
        return ClassificationResult(TargetMatch.DIRECT, "biathlon", 0.95, ["SYNTHETIC followed-account indicator"],
                                    self.classifier_version, followed_indicator=True)


def _one_reel(repo):
    sid = repo.create_session("EXP-001", checkpoint="T2", capture_method="synthetic")["session_id"]
    o = repo.add_observation(sid, {"video_offset_seconds": 0.0, "segment_end_seconds": 5.0, "is_ad": False})
    return sid, o["observation_id"]


def _primary(repo, sid):
    m = compute_summary(repo, "EXP-001")
    return next(r["metrics"] for r in m["sessions"] if r["session_id"] == sid)


def test_classify_then_bulk_recommended(repo, settings):
    sid, oid = _one_reel(repo)
    pipeline.classify_session(repo, settings, sid, FollowedFixture())
    o = repo.get_observation(oid)
    assert o["recommendation_status"] == "followed_account" and o["followed_signal"] is True
    assert o["eligibility_source"] == "classifier"
    # default bulk only touches undetermined rows: the followed row stays excluded
    assert pipeline.bulk_set_eligibility(repo, sid, "recommended")["updated"] == 0
    # forcing bulk over every row cannot silently make it eligible
    res = pipeline.bulk_set_eligibility(repo, sid, "recommended", only_undetermined=False)
    assert res == {"updated": 1, "conflicts": 1}
    o = repo.get_observation(oid)
    assert o["eligibility_conflict"] is True
    m = _primary(repo, sid)
    assert m["exposures_eligible"] == 0 and m["eligibility"]["conflicts"] == 1


def test_bulk_recommended_then_classify(repo, settings):
    sid, oid = _one_reel(repo)
    pipeline.bulk_set_eligibility(repo, sid, "recommended")
    assert repo.get_observation(oid)["eligibility_source"] == "bulk_assumption"
    assert _primary(repo, sid)["exposures_eligible"] == 1
    pipeline.classify_session(repo, settings, sid, FollowedFixture())
    o = repo.get_observation(oid)
    assert o["recommendation_status"] == "recommended" and o["eligibility_conflict"] is True
    assert any("Eligibility conflict" in e for e in o["classification_evidence"])
    m = _primary(repo, sid)
    assert m["exposures_eligible"] == 0 and m["eligibility"]["conflicts"] == 1
    assert any("conflicting eligibility" in w for w in compute_summary(repo, "EXP-001")["warnings"])
    plan = compute_plan(repo, "EXP-001")
    assert any("conflicting eligibility" in f for f in plan["findings"]) or plan["status"] == "collect_baseline"


def test_human_ruling_is_not_overridden_and_resolves_conflict(repo, settings):
    sid, oid = _one_reel(repo)
    pipeline.apply_correction(repo, oid, {"recommendation_status": "recommended", "confirm": True})
    assert repo.get_observation(oid)["eligibility_source"] == "human_review"
    pipeline.classify_session(repo, settings, sid, FollowedFixture(), include_reviewed=True)
    o = repo.get_observation(oid)
    assert o["recommendation_status"] == "recommended" and o["eligibility_conflict"] is True
    # the human looks again and keeps 'recommended': conflict resolved, row counts again
    pipeline.apply_correction(repo, oid, {"recommendation_status": "recommended", "confirm": True})
    o = repo.get_observation(oid)
    assert o["eligibility_conflict"] is False and o["followed_signal"] is True
    assert _primary(repo, sid)["exposures_eligible"] == 1


def test_bulk_endpoint_reports_conflicts(client):
    s = client.post("/api/experiments/EXP-001/sessions", json={"checkpoint": "T2", "capture_method": "synthetic"}).json()
    client.post(f"/api/sessions/{s['session_id']}/observations", json={"recommendation_status": "followed_account"})
    r = client.post(f"/api/sessions/{s['session_id']}/eligibility", json={"recommendation_status": "recommended"})
    assert r.status_code == 200 and r.json() == {"updated": 0, "conflicts": 0}


# ---------------------------------------------------------------- R4

def _t0(repo, n, **values):
    sid = repo.create_session("EXP-001", checkpoint="T0", capture_method="manual_entry")["session_id"]
    row = {"target_match": "unrelated", "recommendation_status": "recommended", "review_status": "confirmed",
           "is_ad": False, **values}
    for _ in range(n):
        repo.add_observation(sid, dict(row))
    return sid


def _readiness(repo):
    return compute_summary(repo, "EXP-001")["baseline_readiness"]


def test_empty_baseline_does_not_unlock(repo):
    _t0(repo, 0), _t0(repo, 0)
    assert not _readiness(repo)["ready"]
    plan = compute_plan(repo, "EXP-001")
    assert plan["status"] == "collect_baseline" and plan["recommended_actions"] == []
    assert plan["next_checkpoint"]["checkpoint"] == "T0"


def test_two_single_item_baselines_do_not_unlock(repo):
    sids = [_t0(repo, 1), _t0(repo, 1)]
    for sid in sids:
        with pytest.raises(ProtocolError):
            accept_sample(repo, sid)
    plan = compute_plan(repo, "EXP-001")
    assert plan["status"] == "collect_baseline" and plan["recommended_actions"] == []
    assert any("1 of 50 Reels" in p for p in _readiness(repo)["problems"])


@pytest.mark.parametrize("values", [
    {"review_status": "auto_accepted"},
    {"review_status": "needs_review"},
    {"recommendation_status": "undetermined"},
    {"eligibility_conflict": True},
])
def test_unreviewed_or_unresolved_baseline_does_not_unlock(repo, values):
    sids = [_t0(repo, 50, **values), _t0(repo, 50, **values)]
    for sid in sids:
        with pytest.raises(ProtocolError):
            accept_sample(repo, sid)
    assert not _readiness(repo)["ready"]
    assert compute_plan(repo, "EXP-001")["status"] == "collect_baseline"


def test_accepted_complete_baseline_unlocks(repo):
    sids = [_t0(repo, 50), _t0(repo, 50)]
    assert not _readiness(repo)["ready"]  # complete but not accepted
    for sid in sids:
        accept_sample(repo, sid)
    r = _readiness(repo)
    assert r["ready"] and r["counted_sessions"] == 2 and r["deviations"] == []
    plan = compute_plan(repo, "EXP-001")
    assert plan["status"] == "intervene" and plan["next_checkpoint"]["checkpoint"] == "T1"


def test_unknown_ad_status_is_allowed_but_reported(repo):
    sids = [_t0(repo, 50, is_ad=None), _t0(repo, 50)]
    for sid in sids:
        accept_sample(repo, sid)
    r = _readiness(repo)
    assert r["ready"] and r["sessions"][0]["unknown_ad_status"] == 50


def test_edit_after_acceptance_revokes_readiness(repo):
    sids = [_t0(repo, 50), _t0(repo, 50)]
    for sid in sids:
        accept_sample(repo, sid)
    o = repo.list_observations(session_id=sids[0])[0]
    repo.update_observation(o["observation_id"], {"review_status": "needs_review"})
    assert not _readiness(repo)["ready"]


def test_deviation_is_explicit_and_recorded(repo):
    sids = [_t0(repo, 40), _t0(repo, 50)]
    with pytest.raises(ProtocolError):
        accept_sample(repo, sids[0], deviation_note="   ")
    accept_sample(repo, sids[0], deviation_note="Feed stopped loading after 40 Reels.")
    accept_sample(repo, sids[1], deviation_note="ignored for complete samples")
    assert repo.get_session(sids[1])["deviation_note"] is None
    r = _readiness(repo)
    assert r["ready"] and r["deviations"][0]["note"] == "Feed stopped loading after 40 Reels."
    assert any("Protocol deviation" in w for w in compute_summary(repo, "EXP-001")["warnings"])


def test_intervention_api_gated_on_baseline(client):
    body = {"action_type": "search_and_watch_target", "actuator": "manual"}
    r = client.post("/api/experiments/EXP-001/interventions", json=body)
    assert r.status_code == 409 and r.json()["detail"]["problems"]
    r = client.post("/api/experiments/EXP-001/interventions", json={**body, "override_baseline_check": True})
    assert r.status_code == 400
    r = client.post("/api/experiments/EXP-001/interventions",
                    json={**body, "override_baseline_check": True, "override_reason": "Pilot run, synthetic test"})
    assert r.status_code == 200
    assert r.json()["parameters"]["baseline_override"]["reason"] == "Pilot run, synthetic test"


def test_accept_endpoint(client):
    s = client.post("/api/experiments/EXP-001/sessions", json={"checkpoint": "T0", "capture_method": "manual_entry"}).json()
    sid = s["session_id"]
    assert client.post(f"/api/sessions/{sid}/accept", json={}).status_code == 409  # empty
    client.post(f"/api/sessions/{sid}/observations/bulk",
                json=[{"target_match": "unrelated", "recommendation_status": "recommended"}] * 3)
    r = client.post(f"/api/sessions/{sid}/accept", json={})
    assert r.status_code == 409 and any("3 of 50" in p for p in r.json()["detail"]["problems"])
    r = client.post(f"/api/sessions/{sid}/accept", json={"deviation_note": "Synthetic API test"})
    assert r.status_code == 200 and r.json()["sample_status"] == "accepted"
    r = client.post(f"/api/sessions/{sid}/accept", json={"accepted": False})
    assert r.json()["sample_status"] == "provisional" and r.json()["deviation_note"] is None


# ---------------------------------------------------------------- migration

def test_schema_v1_database_is_migrated_without_data_loss(tmp_path):
    path = tmp_path / "v1.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE observation_sessions (session_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL,
            checkpoint TEXT NOT NULL, label TEXT NOT NULL DEFAULT '', capture_method TEXT NOT NULL,
            captured_at TEXT NOT NULL, platform TEXT NOT NULL, surface TEXT NOT NULL, recording_ref TEXT,
            recording_sha256 TEXT, recording_duration_seconds REAL, observation_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'created', segmentation_json TEXT, notes TEXT NOT NULL DEFAULT '',
            is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE content_observations (observation_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL,
            session_id TEXT NOT NULL, platform TEXT NOT NULL, surface TEXT NOT NULL, sequence_number INTEGER NOT NULL,
            observed_at TEXT, video_offset_seconds REAL, segment_end_seconds REAL, frame_count INTEGER,
            representative_frame_id INTEGER, topic_label TEXT, target_match TEXT NOT NULL DEFAULT 'unknown',
            confidence REAL, classification_evidence TEXT NOT NULL DEFAULT '[]', caption_text TEXT,
            hashtags TEXT NOT NULL DEFAULT '[]', creator_handle TEXT,
            recommendation_status TEXT NOT NULL DEFAULT 'undetermined', is_ad INTEGER, content_fingerprint TEXT,
            classifier_version TEXT, machine_label_json TEXT, review_status TEXT NOT NULL DEFAULT 'pending',
            segmentation_method TEXT, notes TEXT NOT NULL DEFAULT '', is_demo INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        INSERT INTO observation_sessions (session_id, experiment_id, checkpoint, capture_method, captured_at,
            platform, surface, created_at) VALUES ('ses_old', 'EXP-001', 'T0', 'manual_entry', '2026-11-01T10:00:00+00:00',
            'instagram', 'reels_desktop_web', '2026-11-01T10:00:00+00:00');
        INSERT INTO content_observations (observation_id, experiment_id, session_id, platform, surface,
            sequence_number, target_match, recommendation_status, review_status, created_at, updated_at)
            VALUES ('obs_old', 'EXP-001', 'ses_old', 'instagram', 'reels_desktop_web', 1, 'direct', 'recommended',
            'confirmed', '2026-11-01T10:00:00+00:00', '2026-11-01T10:00:00+00:00');
    """)
    con.commit()
    con.close()
    db = Database(path)
    o = db.query_one("SELECT * FROM content_observations WHERE observation_id = 'obs_old'")
    assert o["target_match"] == "direct" and o["review_status"] == "confirmed"
    assert o["eligibility_conflict"] is False and o["followed_signal"] is None and o["eligibility_source"] is None
    s = db.query_one("SELECT * FROM observation_sessions WHERE session_id = 'ses_old'")
    assert s["sample_status"] == "provisional" and s["deviation_note"] is None
    assert db.query_one("SELECT value FROM meta WHERE key = 'schema_version'")["value"] == str(SCHEMA_VERSION)
    db.close()
    Database(path).close()  # re-opening is idempotent
