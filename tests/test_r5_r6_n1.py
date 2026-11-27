"""Regression tests for R5 (corrections), R6 (capture time) and N1 (gate UI parity). Synthetic inputs only."""
import csv
import io
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from app import cli
from app.evaluator.metrics import experiment_summary
from app.models.schemas import normalize_timestamp, parse_stored_timestamp
from app.observer import media, pipeline
from app.services import accept_sample, compute_plan, compute_summary, export_csv, export_json
from app.storage.db import Database
from app.storage.repository import Repository
from app.taste_engine.profiles import ensure_exp001
from tests.conftest import needs_ffmpeg
from tests.fixtures.synthetic_video import make_reels_video

HAS_NODE = shutil.which("node") is not None


def _obs(client, **values):
    r = client.app.state.repo
    sid = r.create_session("EXP-001", checkpoint="T0", capture_method="synthetic")["session_id"]
    row = {"target_match": "direct", "topic_label": "biathlon", "confidence": 0.8, "review_status": "auto_accepted",
           "recommendation_status": "recommended", "is_ad": True, "caption_text": "Synthetic caption",
           "creator_handle": "synthetic_creator", "classifier_version": "mock-v1",
           "machine_label_json": {"target_match": "direct", "confidence": 0.8}, **values}
    return r.add_observation(sid, row)


def _patch(client, oid, body):
    return client.patch(f"/api/observations/{oid}", json=body)


# ---------------------------------------------------------------- R5


def test_omitted_fields_are_unchanged(client):
    o = _obs(client)
    out = _patch(client, o["observation_id"], {"notes": "checked"}).json()
    for k in ("is_ad", "caption_text", "topic_label", "creator_handle", "confidence", "target_match", "review_status"):
        assert out[k] == o[k], k
    assert out["notes"] == "checked"


def test_explicit_null_clears_ad_caption_topic_and_creator(client):
    o = _obs(client)
    out = _patch(client, o["observation_id"], {"is_ad": None, "caption_text": None, "creator_handle": None}).json()
    assert out["is_ad"] is None and out["caption_text"] is None and out["creator_handle"] is None
    assert out["topic_label"] == "biathlon" and out["review_status"] == "auto_accepted"  # not a label change
    out = _patch(client, o["observation_id"], {"topic_label": None}).json()
    assert out["topic_label"] is None and out["review_status"] == "corrected"
    assert out["confidence"] is None  # no invented certainty for a human edit


def test_correction_to_unknown_has_no_confidence(client):
    o = _obs(client)
    out = _patch(client, o["observation_id"], {"target_match": "unknown", "topic_label": None}).json()
    assert out["target_match"] == "unknown" and out["review_status"] == "corrected"
    assert out["confidence"] is None
    assert out["machine_label_json"]["confidence"] == 0.8  # machine provenance kept
    resp = _patch(client, o["observation_id"], {"confidence": 0.9})
    assert resp.status_code == 400  # UNKNOWN cannot carry a confidence


def test_correction_confidence_is_explicit_only(client):
    o = _obs(client)
    out = _patch(client, o["observation_id"], {"target_match": "adjacent"}).json()
    assert out["review_status"] == "corrected" and out["confidence"] is None
    out = _patch(client, o["observation_id"], {"target_match": "direct", "confidence": 0.6}).json()
    assert out["confidence"] == 0.6
    assert _patch(client, o["observation_id"], {"confidence": 1.5}).status_code == 422


@pytest.mark.parametrize("field", ["target_match", "recommendation_status", "hashtags", "notes"])
def test_null_on_required_field_is_rejected(client, field):
    o = _obs(client)
    assert _patch(client, o["observation_id"], {field: None}).status_code == 422
    assert client.app.state.repo.get_observation(o["observation_id"])[field] == o[field]


def _ui_save(o, **override):
    """The exact payload app.js sends on 'Save' (viewSession): every form field, empty input -> null."""
    body = {"target_match": o["target_match"], "topic_label": o.get("topic_label") or None,
            "recommendation_status": o["recommendation_status"],
            "is_ad": o["is_ad"], "caption_text": o.get("caption_text") or None}
    return {**body, **override}


def test_ui_save_payloads(client):
    o = _obs(client)
    out = _patch(client, o["observation_id"], _ui_save(o)).json()  # unchanged form
    assert out["review_status"] == "auto_accepted" and out["confidence"] == 0.8
    assert "Corrected by human reviewer." not in out["classification_evidence"]
    assert out["eligibility_source"] == "human_review"  # explicit per-Reel ruling, as before
    out = _patch(client, o["observation_id"], _ui_save(out, is_ad=None, caption_text=None)).json()  # "not identified"
    assert out["is_ad"] is None and out["caption_text"] is None and out["review_status"] == "auto_accepted"
    out = _patch(client, o["observation_id"], _ui_save(out, target_match="unknown", topic_label=None)).json()
    assert out["target_match"] == "unknown" and out["confidence"] is None and out["review_status"] == "corrected"


def test_cleared_values_round_trip_through_exports(client):
    r = client.app.state.repo
    o = _obs(client)
    _patch(client, o["observation_id"], {"is_ad": None, "caption_text": None, "target_match": "unknown",
                                         "topic_label": None})
    j = json.loads(json.dumps(export_json(r, "EXP-001")))
    row = next(x for x in j["observations"] if x["observation_id"] == o["observation_id"])
    assert row["is_ad"] is None and row["caption_text"] is None and row["topic_label"] is None
    assert row["confidence"] is None and row["target_match"] == "unknown"
    c = next(x for x in csv.DictReader(io.StringIO(export_csv(r, "EXP-001")))
             if x["observation_id"] == o["observation_id"])
    assert c["is_ad"] == "" and c["caption_text"] == "" and c["topic_label"] == "" and c["confidence"] == ""
    assert c["captured_at_source"] == "session_created" and c["captured_at"]


def test_manual_label_does_not_get_confidence_one(client):
    r = client.app.state.repo
    sid = r.create_session("EXP-001", checkpoint="T0", capture_method="manual_entry")["session_id"]
    a = client.post(f"/api/sessions/{sid}/observations", json={"target_match": "direct"}).json()
    b = client.post(f"/api/sessions/{sid}/observations", json={"target_match": "unknown", "confidence": 0.7}).json()
    c = client.post(f"/api/sessions/{sid}/observations", json={"target_match": "adjacent", "confidence": 0.7}).json()
    assert a["confidence"] is None and a["review_status"] == "confirmed"
    assert b["confidence"] is None and c["confidence"] == 0.7


# ---------------------------------------------------------------- R6: entry validation


@pytest.mark.parametrize("value", ["2026-11-27T09:00:00", "not a date", "2026-13-01T00:00:00Z"])
def test_naive_or_malformed_timestamps_are_rejected(client, value):
    r = client.app.state.repo
    assert client.post("/api/experiments/EXP-001/sessions",
                       json={"checkpoint": "T0", "captured_at": value}).status_code == 422
    sid = r.create_session("EXP-001", checkpoint="T0", capture_method="manual_entry")["session_id"]
    assert client.post(f"/api/sessions/{sid}/observations",
                       json={"target_match": "unknown", "observed_at": value}).status_code == 422
    with pytest.raises(ValueError):
        r.create_session("EXP-001", checkpoint="T0", capture_method="manual_entry", captured_at=value)


def test_offsets_are_normalised_to_utc(client):
    s = client.post("/api/experiments/EXP-001/sessions",
                    json={"checkpoint": "T0", "captured_at": "2026-11-27T10:30:00+01:00"}).json()
    assert s["captured_at"] == "2026-11-27T09:30:00+00:00" and s["captured_at_source"] == "user"
    assert s["created_at"] != s["captured_at"]
    s = client.post("/api/experiments/EXP-001/sessions", json={"checkpoint": "T0"}).json()
    assert s["captured_at_source"] == "session_created"


def test_intervention_completion_requires_timezone(client):
    a = client.post("/api/experiments/EXP-001/interventions", json={
        "action_type": "search_and_watch_target", "actuator": "manual", "override_baseline_check": True,
        "override_reason": "Synthetic test"}).json()
    assert client.post(f"/api/interventions/{a['action_id']}/complete",
                       json={"completed_at": "2026-11-27T09:00:00"}).status_code == 422
    done = client.post(f"/api/interventions/{a['action_id']}/complete",
                       json={"completed_at": "2026-11-27T09:00:00-05:00"}).json()
    assert done["completed_at"] == "2026-11-27T14:00:00+00:00"


def test_mixed_naive_and_aware_timestamps_do_not_crash(client):
    """The original R6 reproduction: legacy naive capture time plus an aware intervention completion."""
    r = client.app.state.repo
    t2 = r.create_session("EXP-001", checkpoint="T2", capture_method="manual_entry")["session_id"]
    r.update_session(t2, {"captured_at": "2026-11-27T12:00:00"})  # legacy naive value written before D-027
    r.add_observation(t2, {"target_match": "direct", "recommendation_status": "recommended",
                           "review_status": "confirmed", "is_ad": False, "observed_at": "2026-11-27T12:05:00"})
    r.add_intervention("EXP-001", {"action_type": "search_and_watch_target", "description": "synthetic",
                                   "parameters_json": {}, "instructions": "", "actuator": "manual",
                                   "status": "completed", "completed_at": "2026-11-27T10:00:00+00:00"})
    s = compute_summary(r, "EXP-001")
    row = next(x for x in s["sessions"] if x["session_id"] == t2)
    assert row["hours_after_intervention"] == 2.0 and row["timezone_assumed_utc"]
    assert not row["capture_time_verified"]
    assert s["time_to_first_target"]["hours_after_intervention"] == pytest.approx(2.08, abs=0.01)
    assert any("read as UTC" in w for w in s["warnings"])
    assert compute_plan(r, "EXP-001")  # strategist anchor path no longer crashes either
    assert client.get("/api/experiments/EXP-001").status_code == 200


def test_chronology_uses_instants_not_strings():
    exp = {"experiment_id": "X", "target_topic": "biathlon", "target_share": 0.2}
    # 00:30+01:00 is 23:30Z on the previous day, i.e. before 23:45Z, although it sorts after it as a string.
    sessions = [{"session_id": "late", "checkpoint": "T2", "captured_at": "2026-01-01T23:45:00+00:00",
                 "captured_at_source": "user"},
                {"session_id": "early", "checkpoint": "T2", "captured_at": "2026-01-02T00:30:00+01:00",
                 "captured_at_source": "user"}]
    rows = [{"session_id": sid, "sequence_number": 1, "target_match": "unrelated",
             "recommendation_status": "recommended", "review_status": "confirmed", "is_ad": False}
            for sid in ("late", "early")]
    s = experiment_summary(exp, sessions, rows, [])
    assert [r["session_id"] for r in s["sessions"]] == ["early", "late"]
    assert s["latest"]["session_id"] == "late"


def _persistence_case(captured_at, source="user"):
    exp = {"experiment_id": "X", "target_topic": "biathlon", "target_share": 0.2}
    sessions = [{"session_id": "b", "checkpoint": "T0", "captured_at": "2026-01-01T08:00:00+00:00",
                 "captured_at_source": "user"},
                {"session_id": "t3", "checkpoint": "T3", "captured_at": captured_at, "captured_at_source": source}]
    rows = [{"session_id": sid, "sequence_number": i, "target_match": "direct" if i == 1 else "unrelated",
             "recommendation_status": "recommended", "review_status": "confirmed", "is_ad": False}
            for sid in ("b", "t3") for i in range(1, 11)]
    acts = [{"action_id": "a1", "status": "completed", "completed_at": "2026-01-01T10:00:00+00:00"}]
    s = experiment_summary(exp, sessions, rows, acts)
    return next(p for p in s["persistence"] if p["checkpoint"] == "T3"), s["warnings"]


def test_persistence_reports_actual_elapsed_time():
    p, warnings = _persistence_case("2026-01-02T16:00:00+00:00")
    assert p["nominal_hours"] == 24 and p["actual_hours_after_intervention"] == 30.0
    assert p["hours_from_nominal"] == 6.0 and p["capture_time_verified"] and not p["captured_before_intervention"]
    assert not any("T3 t3" in w for w in warnings)


def test_t3_label_alone_is_not_evidence_of_24h():
    p, warnings = _persistence_case("2026-01-01T09:00:00+00:00")
    assert p["captured_before_intervention"] and p["actual_hours_after_intervention"] == -1.0
    assert any("before the first completed intervention" in w for w in warnings)
    p, warnings = _persistence_case("2026-01-02T10:00:00+00:00", source="session_created")
    assert p["actual_hours_after_intervention"] == 24.0 and not p["capture_time_verified"]
    assert any("not verified" in w for w in warnings)
    p, _ = _persistence_case("2026-01-02T10:00:00+00:00", source=None)  # legacy row
    assert p["captured_at_source"] == "not_recorded" and not p["capture_time_verified"]


def test_stored_timestamp_parser():
    assert parse_stored_timestamp("2026-01-01T10:00:00")[1] is True
    assert parse_stored_timestamp("2026-01-01T10:00:00Z")[0].isoformat() == "2026-01-01T10:00:00+00:00"
    assert parse_stored_timestamp("garbage") == (None, False)
    assert normalize_timestamp("") is None


# ---------------------------------------------------------------- R6: recording metadata


def test_container_creation_time_tags():
    info = {"format": {"tags": {"creation_time": "2026-11-26T10:00:05.000000Z",
                                "com.apple.quicktime.creationdate": "2026-11-26T10:00:00+0000"}}}
    assert media.container_creation_time(info)["tag"] == "com.apple.quicktime.creationdate"
    assert media.container_creation_time({"format": {"tags": {"creation_time": "1970-01-01T00:00:00Z"}}}) is None
    assert media.container_creation_time({"format": {"tags": {"creation_time": "2026-11-26T10:00:00"}}}) is None
    assert media.container_creation_time({"format": {}, "streams": [
        {"tags": {"creation_time": "2026-11-26T09:00:00Z"}}]})["value"] == "2026-11-26T09:00:00+00:00"
    assert media.container_creation_time({"format": {"tags": {"creation_time": "garbage"}}}) is None


def _video(tmp_path, name, creation_time=None):
    raw = make_reels_video(tmp_path / f"raw-{name}.mp4", [3, 3])
    out = tmp_path / f"{name}.mp4"
    meta = ["-metadata", f"creation_time={creation_time}"] if creation_time else []
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-map_metadata", "-1", *meta, "-c", "copy",
                    str(out)], check=True)
    return out


@needs_ffmpeg
def test_import_uses_recording_metadata_and_separates_import_time(repo, settings, tmp_path):
    video = _video(tmp_path, "old", "2026-11-20T08:15:00Z")  # an old recording imported today
    sid = repo.create_session("EXP-001", checkpoint="T0", capture_method="screen_recording")["session_id"]
    s = pipeline.import_recording(repo, settings, sid, video)
    assert s["captured_at"] == "2026-11-20T08:15:00+00:00" and s["captured_at_source"] == "recording_metadata"
    assert s["recording_created_at"] == s["captured_at"]
    assert s["imported_at"] and s["imported_at"] > s["captured_at"]


@needs_ffmpeg
def test_import_without_metadata_falls_back_and_is_flagged(repo, settings, tmp_path):
    video = _video(tmp_path, "bare")
    sid = repo.create_session("EXP-001", checkpoint="T0", capture_method="screen_recording")["session_id"]
    created = repo.get_session(sid)["captured_at"]
    s = pipeline.import_recording(repo, settings, sid, video)
    assert s["recording_created_at"] is None and s["captured_at"] == created
    assert s["captured_at_source"] == "session_created"
    row = compute_summary(repo, "EXP-001")["sessions"][0]
    assert not row["capture_time_verified"]


@needs_ffmpeg
def test_explicit_capture_time_wins_over_metadata(repo, settings, tmp_path):
    video = _video(tmp_path, "meta", "2026-11-20T08:15:00Z")
    sid = repo.create_session("EXP-001", checkpoint="T0", capture_method="screen_recording",
                              captured_at="2026-11-20T09:00:00+01:00")["session_id"]
    s = pipeline.import_recording(repo, settings, sid, video)  # owner-entered value is kept
    assert s["captured_at"] == "2026-11-20T08:00:00+00:00" and s["captured_at_source"] == "user"
    assert s["recording_created_at"] == "2026-11-20T08:15:00+00:00"  # metadata kept as provenance
    s = pipeline.import_recording(repo, settings, sid, video, captured_at="2026-11-20T07:00:00Z")
    assert s["captured_at"] == "2026-11-20T07:00:00+00:00"
    with pytest.raises(ValueError):
        pipeline.import_recording(repo, settings, sid, video, captured_at="2026-11-20T07:00:00")


@needs_ffmpeg
def test_cli_capture_time_option(settings, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    video = _video(tmp_path, "cli", "2026-11-20T08:15:00Z")
    assert cli.main(["import", str(video), "--captured-at", "2026-11-19T21:00:00+00:00"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["captured_at"] == "2026-11-19T21:00:00+00:00" and out["captured_at_source"] == "user"
    assert out["imported_at"] != out["captured_at"]
    assert cli.main(["new-session", "--captured-at", "2026-11-19T22:00:00Z"]) == 0
    with pytest.raises(SystemExit):
        cli.main(["import", str(video), "--captured-at", "2026-11-19T21:00:00"])  # naive: rejected
    r = Repository(Database(settings.db_path), settings.data_dir)
    assert len(r.list_sessions("EXP-001")) == 2  # the rejected call created no session


def test_legacy_v3_database_gains_capture_columns_without_rewriting(settings):
    r = Repository(Database(settings.db_path), settings.data_dir)
    ensure_exp001(r)
    sid = r.create_session("EXP-001", checkpoint="T0", capture_method="manual_entry",
                           captured_at="2026-11-26T09:00:00+00:00")["session_id"]
    r.db.close()
    con = sqlite3.connect(settings.db_path)
    for col in ("captured_at_source", "imported_at", "recording_created_at"):
        con.execute(f"ALTER TABLE observation_sessions DROP COLUMN {col}")
    con.execute("UPDATE observation_sessions SET captured_at='2026-11-26T09:00:00'")  # legacy naive value
    con.execute("UPDATE meta SET value='3' WHERE key='schema_version'")
    con.commit()
    con.close()
    r = Repository(Database(settings.db_path), settings.data_dir)
    s = r.get_session(sid)
    assert s["captured_at"] == "2026-11-26T09:00:00" and s["captured_at_source"] is None  # value not rewritten
    row = compute_summary(r, "EXP-001")["sessions"][0]
    assert row["captured_at_source"] == "not_recorded" and row["timezone_assumed_utc"]


# ---------------------------------------------------------------- N1


def _t0(repo, n=50):
    sid = repo.create_session("EXP-001", checkpoint="T0", capture_method="synthetic")["session_id"]
    for _ in range(n):
        repo.add_observation(sid, {"target_match": "unrelated", "review_status": "confirmed",
                                   "recommendation_status": "recommended", "is_ad": False})
    return sid


def _state(client, name):
    r = client.app.state.repo
    if name in ("review_open", "ready"):
        for _ in range(2):
            accept_sample(r, _t0(r))
    if name == "review_open":
        sid = r.create_session("EXP-001", checkpoint="ADHOC", capture_method="synthetic")["session_id"]
        r.add_observation(sid, {"target_match": "unknown", "review_status": "pending",
                                "recommendation_status": "recommended", "is_ad": False})


GATE_STATES = [("baseline_unready", False, 409), ("review_open", False, 409), ("ready", True, 200)]


@pytest.mark.parametrize("name,open_,code", GATE_STATES)
def test_plan_exposes_the_gate_the_api_enforces(client, name, open_, code):
    _state(client, name)
    gate = client.get("/api/experiments/EXP-001/plan").json()["intervention_gate"]
    assert gate["open"] is open_ and bool(gate["problems"]) is not open_
    body = {"action_type": "search_and_watch_target", "actuator": "manual"}
    resp = client.post("/api/experiments/EXP-001/interventions", json=body)
    assert resp.status_code == code
    if not open_:
        assert resp.json()["detail"]["problems"] == gate["problems"]
        assert client.post("/api/experiments/EXP-001/interventions",
                           json={**body, "override_baseline_check": True, "override_reason": "  "}).status_code == 400


RENDER = r"""
const fs = require('fs'), vm = require('vm');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = fs.readFileSync(payload.source, 'utf8');
const start = source.indexOf('async function viewInterventions(id) {');
const end = source.indexOf('async function viewProfiles()', start);
const view = {innerHTML: '', querySelectorAll: () => []};
const elements = {};
const document = {getElementById(id) {
  if (!view.innerHTML.includes(`id="${id}"`)) return null;
  return elements[id] ||= {value: '', checked: false};
}};
const posted = [];
const ctx = vm.createContext({$view: view, document, expNav() {}, markNav() {}, demoBanner() { return ''; },
  esc: v => String(v ?? ''), dt: v => String(v ?? ''), toast(m) { posted.push('toast:' + m); },
  api: async (path, opts) => { if (opts) { posted.push(opts.json); return {}; } return payload.responses[path]; }});
vm.runInContext(source.slice(start, end), ctx);
(async () => {
  await ctx.viewInterventions('EXP-001');
  const btn = elements.aplan || document.getElementById('aplan');
  const out = {html: view.innerHTML, disabled_initially: !!btn.disabled};
  await btn.onclick();
  out.clicked_without_exception = posted.slice();
  if (elements.aoverride) {
    elements.aoverride.checked = true; elements.aoverride.onchange();
    out.disabled_checkbox_only = !!btn.disabled;
    elements.areason.value = 'Founder exception (synthetic)'; elements.areason.oninput();
    out.disabled_with_reason = !!btn.disabled;
    posted.length = 0; await btn.onclick(); out.posted_with_exception = posted.slice();
  }
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e); process.exitCode = 1; });
"""


@pytest.mark.skipif(not HAS_NODE, reason="node not installed")
@pytest.mark.parametrize("name,open_,code", GATE_STATES)
def test_intervention_view_matches_api_gate(client, name, open_, code):
    _state(client, name)
    paths = ["/experiments/EXP-001", "/experiments/EXP-001/actions", "/experiments/EXP-001/plan"]
    responses = {p: client.get("/api" + p).json() for p in paths}
    payload = {"source": str(Path("app/web/app.js").resolve()), "responses": responses}
    out = json.loads(subprocess.run(["node", "-e", RENDER], input=json.dumps(payload), text=True,
                                    capture_output=True, check=True).stdout)
    problems = responses[paths[2]]["intervention_gate"]["problems"]
    if open_:
        assert "banner warn" not in out["html"] and 'id="aoverride"' not in out["html"]
        assert not out["disabled_initially"]
        assert out["clicked_without_exception"][0].get("override_baseline_check") is None
        return
    assert "banner warn" in out["html"] and all(p in out["html"] for p in problems)
    title = "Open review items block" if name == "review_open" else "Baseline not ready"
    assert title in out["html"]
    assert out["disabled_initially"] and out["disabled_checkbox_only"] and not out["disabled_with_reason"]
    assert out["clicked_without_exception"][0].startswith("toast:")  # no request without the exception
    sent = out["posted_with_exception"][0]
    assert sent["override_baseline_check"] is True and sent["override_reason"] == "Founder exception (synthetic)"


@needs_ffmpeg
def test_reimport_into_legacy_session_keeps_its_capture_time(repo, settings, tmp_path):
    video = _video(tmp_path, "legacy", "2026-11-20T08:15:00Z")
    sid = repo.create_session("EXP-001", checkpoint="T0", capture_method="screen_recording",
                              captured_at="2026-11-26T09:00:00+00:00")["session_id"]
    repo.update_session(sid, {"captured_at_source": None})  # as migrated from schema v3
    s = pipeline.import_recording(repo, settings, sid, video)
    assert s["captured_at"] == "2026-11-26T09:00:00+00:00" and s["captured_at_source"] is None
    assert s["recording_created_at"] == "2026-11-20T08:15:00+00:00"
