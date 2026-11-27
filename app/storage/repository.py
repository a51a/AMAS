"""Repository: typed-ish CRUD on top of Database. Keeps SQL out of the API layer."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from app.models.schemas import (
    CaptureTimeSource,
    ExperimentCreate,
    InterestProfile,
    ManualObservation,
    ReviewStatus,
    normalize_timestamp,
    utcnow,
)
from app.storage.db import Database


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class NotFound(Exception):
    pass


class Repository:
    def __init__(self, db: Database, data_dir: Path):
        self.db = db
        self.data_dir = Path(data_dir)

    # ---------------- profiles ----------------
    def upsert_profile(self, profile: InterestProfile) -> dict:
        existing = self.get_profile(profile.profile_id, missing_ok=True)
        topics = [t.model_dump(mode="json") for t in profile.topics]
        if existing is None:
            self.db.insert(
                "interest_profiles",
                {
                    "profile_id": profile.profile_id,
                    "name": profile.name,
                    "description": profile.description,
                    "topics_json": topics,
                    "version": profile.version,
                    "is_demo": profile.is_demo,
                    "created_at": profile.created_at,
                    "updated_at": profile.updated_at,
                },
            )
            self._snapshot_profile(profile.profile_id)
        return self.get_profile(profile.profile_id)

    def update_profile(self, profile_id: str, changes: dict[str, Any]) -> dict:
        current = self.get_profile(profile_id)
        values: dict[str, Any] = {}
        if changes.get("name") is not None:
            values["name"] = changes["name"]
        if changes.get("description") is not None:
            values["description"] = changes["description"]
        if changes.get("topics") is not None:
            values["topics_json"] = changes["topics"]
        if not values:
            return current
        values["version"] = current["version"] + 1
        values["updated_at"] = utcnow()
        self.db.update("interest_profiles", "profile_id", profile_id, values)
        self._snapshot_profile(profile_id)
        return self.get_profile(profile_id)

    def _snapshot_profile(self, profile_id: str) -> None:
        p = self.get_profile(profile_id)
        self.db.execute(
            "INSERT OR REPLACE INTO interest_profile_versions(profile_id, version, snapshot_json, created_at) "
            "VALUES (?, ?, json(?), ?)",
            (profile_id, p["version"], _json(p), utcnow()),
        )

    def get_profile(self, profile_id: str, missing_ok: bool = False) -> dict | None:
        row = self.db.query_one("SELECT * FROM interest_profiles WHERE profile_id = ?", (profile_id,))
        if row is None and not missing_ok:
            raise NotFound(f"profile {profile_id}")
        if row:
            row["topics"] = row.pop("topics_json")
        return row

    def list_profiles(self) -> list[dict]:
        rows = self.db.query("SELECT * FROM interest_profiles ORDER BY is_demo, profile_id")
        for r in rows:
            r["topics"] = r.pop("topics_json")
        return rows

    def profile_versions(self, profile_id: str) -> list[dict]:
        return self.db.query(
            "SELECT version, created_at, snapshot_json FROM interest_profile_versions "
            "WHERE profile_id = ? ORDER BY version DESC",
            (profile_id,),
        )

    # ---------------- experiments ----------------
    def create_experiment(self, exp: ExperimentCreate) -> dict:
        now = utcnow()
        self.db.insert(
            "experiments",
            {
                "experiment_id": exp.experiment_id,
                "name": exp.name,
                "research_question": exp.research_question,
                "platform": exp.platform,
                "surface": exp.surface,
                "profile_id": exp.profile_id,
                "target_topic": exp.target_topic,
                "target_share": exp.target_share,
                "is_demo": exp.is_demo,
                "config_json": exp.config,
                "created_at": now,
                "updated_at": now,
            },
        )
        return self.get_experiment(exp.experiment_id)

    def get_experiment(self, experiment_id: str, missing_ok: bool = False) -> dict | None:
        row = self.db.query_one("SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,))
        if row is None and not missing_ok:
            raise NotFound(f"experiment {experiment_id}")
        if row:
            row["config"] = row.pop("config_json")
        return row

    def list_experiments(self) -> list[dict]:
        rows = self.db.query("SELECT * FROM experiments ORDER BY is_demo, created_at")
        for r in rows:
            r["config"] = r.pop("config_json")
        return rows

    def set_external_consent(self, experiment_id: str, consent: bool) -> dict:
        self.db.update(
            "experiments",
            "experiment_id",
            experiment_id,
            {
                "external_provider_consent": consent,
                "external_provider_consent_at": utcnow() if consent else None,
                "updated_at": utcnow(),
            },
        )
        return self.get_experiment(experiment_id)

    def delete_experiment(self, experiment_id: str) -> None:
        for s in self.list_sessions(experiment_id):
            self.delete_session(s["session_id"])
        self.db.execute("DELETE FROM experiments WHERE experiment_id = ?", (experiment_id,))

    # ---------------- sessions ----------------
    def create_session(self, experiment_id: str, *, checkpoint: str, capture_method: str,
                       label: str = "", captured_at: str | None = None, notes: str = "",
                       captured_at_source: str | None = None) -> dict:
        """Create a session. `captured_at` must be timezone-aware (R6, D-027); it is stored in UTC.

        Without it the creation time is used and recorded as the `session_created` fallback, which is not
        evidence of when the feed was seen; a later recording import may replace it with recording metadata.
        """
        exp = self.get_experiment(experiment_id)
        sid = new_id("ses")
        now = utcnow()
        captured = normalize_timestamp(captured_at, field="captured_at")
        source = captured_at_source or (CaptureTimeSource.USER.value if captured else
                                        CaptureTimeSource.SESSION_CREATED.value)
        self.db.insert(
            "observation_sessions",
            {
                "session_id": sid,
                "experiment_id": experiment_id,
                "checkpoint": checkpoint,
                "label": label,
                "capture_method": capture_method,
                "captured_at": captured or now,
                "captured_at_source": source,
                "platform": exp["platform"],
                "surface": exp["surface"],
                "notes": notes,
                "is_demo": exp["is_demo"],
                "created_at": now,
            },
        )
        return self.get_session(sid)

    def get_session(self, session_id: str, missing_ok: bool = False) -> dict | None:
        row = self.db.query_one("SELECT * FROM observation_sessions WHERE session_id = ?", (session_id,))
        if row is None and not missing_ok:
            raise NotFound(f"session {session_id}")
        return row

    def list_sessions(self, experiment_id: str) -> list[dict]:
        return self.db.query(
            "SELECT * FROM observation_sessions WHERE experiment_id = ? ORDER BY captured_at, created_at",
            (experiment_id,),
        )

    def update_session(self, session_id: str, values: dict[str, Any]) -> dict:
        self.db.update("observation_sessions", "session_id", session_id, values)
        return self.get_session(session_id)

    def session_dir(self, session_id: str) -> Path:
        return self.data_dir / "recordings" / session_id

    def delete_recording(self, session_id: str) -> dict:
        """Delete the recording file and extracted frames; keep observations (labels)."""
        d = self.session_dir(session_id)
        if d.exists():
            shutil.rmtree(d)
        self.db.execute("DELETE FROM recording_frames WHERE session_id = ?", (session_id,))
        self.db.execute(
            "UPDATE content_observations SET representative_frame_id = NULL WHERE session_id = ?", (session_id,)
        )
        return self.update_session(session_id, {"recording_ref": None})

    def delete_session(self, session_id: str) -> None:
        """Delete a session with its recording, frames, observations and derived metrics."""
        self.delete_recording(session_id)
        self.db.execute("DELETE FROM experiment_metrics WHERE session_id = ?", (session_id,))
        self.db.execute("DELETE FROM content_observations WHERE session_id = ?", (session_id,))
        self.db.execute("DELETE FROM observation_sessions WHERE session_id = ?", (session_id,))

    # ---------------- frames ----------------
    def add_frames(self, session_id: str, frames: list[dict]) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM recording_frames WHERE session_id = ?", (session_id,))
            c.executemany(
                "INSERT INTO recording_frames(session_id, frame_index, offset_seconds, path, diff_score, ahash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (session_id, f["frame_index"], f["offset_seconds"], f["path"], f.get("diff_score"), f.get("ahash"))
                    for f in frames
                ],
            )

    def list_frames(self, session_id: str) -> list[dict]:
        return self.db.query(
            "SELECT * FROM recording_frames WHERE session_id = ? ORDER BY frame_index", (session_id,)
        )

    def get_frame(self, frame_id: int) -> dict | None:
        return self.db.query_one("SELECT * FROM recording_frames WHERE frame_id = ?", (frame_id,))

    # ---------------- observations ----------------
    def add_observation(self, session_id: str, values: dict[str, Any]) -> dict:
        s = self.get_session(session_id)
        now = utcnow()
        oid = values.pop("observation_id", None) or new_id("obs")
        seq = values.pop("sequence_number", None)
        if seq is None:
            r = self.db.query_one(
                "SELECT COALESCE(MAX(sequence_number), 0) AS m FROM content_observations WHERE session_id = ?",
                (session_id,),
            )
            seq = r["m"] + 1
        row = {
            "observation_id": oid,
            "experiment_id": s["experiment_id"],
            "session_id": session_id,
            "platform": s["platform"],
            "surface": s["surface"],
            "sequence_number": seq,
            "is_demo": s["is_demo"],
            "created_at": now,
            "updated_at": now,
        }
        row.update(values)
        self.db.insert("content_observations", row)
        self._refresh_count(session_id)
        return self.get_observation(oid)

    def add_manual_observation(self, session_id: str, m: ManualObservation) -> dict:
        data = m.model_dump(mode="json")
        evidence = data.pop("classification_evidence") or []
        if m.target_match.value != "unknown" and not evidence:
            evidence = ["Manually labelled by the account owner."]
        values = {
            **data,
            "classification_evidence": evidence,
            "classifier_version": "human-manual",
            "review_status": ReviewStatus.CONFIRMED.value if m.target_match.value != "unknown" else ReviewStatus.NEEDS_REVIEW.value,
            "segmentation_method": "manual_entry",
        }
        # R5 (D-026): a human label is reviewed, not certain. Keep only an explicitly stated confidence, and
        # never attach one to UNKNOWN.
        if m.target_match.value == "unknown":
            values["confidence"] = None
        return self.add_observation(session_id, values)

    def get_observation(self, observation_id: str, missing_ok: bool = False) -> dict | None:
        row = self.db.query_one(
            "SELECT * FROM content_observations WHERE observation_id = ?", (observation_id,)
        )
        if row is None and not missing_ok:
            raise NotFound(f"observation {observation_id}")
        return row

    def list_observations(self, *, session_id: str | None = None, experiment_id: str | None = None) -> list[dict]:
        if session_id:
            return self.db.query(
                "SELECT * FROM content_observations WHERE session_id = ? ORDER BY sequence_number", (session_id,)
            )
        return self.db.query(
            "SELECT o.* FROM content_observations o JOIN observation_sessions s USING(session_id) "
            "WHERE o.experiment_id = ? ORDER BY s.captured_at, o.sequence_number",
            (experiment_id,),
        )

    def update_observation(self, observation_id: str, values: dict[str, Any]) -> dict:
        values = {**values, "updated_at": utcnow()}
        self.db.update("content_observations", "observation_id", observation_id, values)
        return self.get_observation(observation_id)

    def delete_observation(self, observation_id: str) -> None:
        o = self.get_observation(observation_id)
        self.db.execute("DELETE FROM content_observations WHERE observation_id = ?", (observation_id,))
        self.renumber(o["session_id"])

    def replace_observations(self, session_id: str, rows: list[dict]) -> list[dict]:
        self.db.execute("DELETE FROM content_observations WHERE session_id = ?", (session_id,))
        for i, r in enumerate(rows, start=1):
            self.add_observation(session_id, {**r, "sequence_number": i})
        return self.list_observations(session_id=session_id)

    def apply_segment_plan(self, session_id: str, plan: list[tuple[str, dict]], delete_ids: list[str]) -> list[dict]:
        """Apply a boundary reconciliation in ONE transaction (all or nothing).

        plan: ordered (action, values) pairs; action "keep"/"update" carries observation_id, "new" inserts.
        delete_ids: observations absorbed by a merge.
        """
        s = self.get_session(session_id)
        now = utcnow()
        from app.storage.db import _encode

        with self.db.tx() as c:
            for oid in delete_ids:
                c.execute("DELETE FROM content_observations WHERE observation_id = ? AND session_id = ?",
                          (oid, session_id))
            for seq, (action, values) in enumerate(plan, start=1):
                values = dict(values)
                if action == "new":
                    row = {"observation_id": new_id("obs"), "experiment_id": s["experiment_id"],
                           "session_id": session_id, "platform": s["platform"], "surface": s["surface"],
                           "is_demo": s["is_demo"], "created_at": now, "updated_at": now,
                           **values, "sequence_number": seq}
                    cols = list(row)
                    c.execute(f"INSERT INTO content_observations ({', '.join(cols)}) VALUES "
                              f"({', '.join('?' * len(cols))})", [_encode(k, row[k]) for k in cols])
                else:
                    oid = values.pop("observation_id")
                    values.update({"sequence_number": seq, "updated_at": now})
                    cols = list(values)
                    cur = c.execute(
                        f"UPDATE content_observations SET {', '.join(f'{k} = ?' for k in cols)} "
                        "WHERE observation_id = ? AND session_id = ?",
                        [_encode(k, values[k]) for k in cols] + [oid, session_id])
                    if cur.rowcount != 1:
                        raise RuntimeError(f"observation {oid} changed during reconciliation")
            c.execute("UPDATE observation_sessions SET observation_count = "
                      "(SELECT COUNT(*) FROM content_observations WHERE session_id = ?) WHERE session_id = ?",
                      (session_id, session_id))
        return self.list_observations(session_id=session_id)

    def renumber(self, session_id: str) -> None:
        obs = self.list_observations(session_id=session_id)
        with self.db.tx() as c:
            for i, o in enumerate(obs, start=1):
                c.execute(
                    "UPDATE content_observations SET sequence_number = ? WHERE observation_id = ?",
                    (i, o["observation_id"]),
                )
        self._refresh_count(session_id)

    def _refresh_count(self, session_id: str) -> None:
        self.db.execute(
            "UPDATE observation_sessions SET observation_count = "
            "(SELECT COUNT(*) FROM content_observations WHERE session_id = ?) WHERE session_id = ?",
            (session_id, session_id),
        )

    # ---------------- interventions ----------------
    def add_intervention(self, experiment_id: str, values: dict[str, Any]) -> dict:
        exp = self.get_experiment(experiment_id)
        aid = new_id("act")
        row = {
            "action_id": aid,
            "experiment_id": experiment_id,
            "platform": exp["platform"],
            "planned_at": utcnow(),
            "is_demo": exp["is_demo"],
        }
        row.update(values)
        self.db.insert("intervention_actions", row)
        return self.get_intervention(aid)

    def get_intervention(self, action_id: str) -> dict:
        row = self.db.query_one("SELECT * FROM intervention_actions WHERE action_id = ?", (action_id,))
        if row is None:
            raise NotFound(f"intervention {action_id}")
        row["parameters"] = row.pop("parameters_json")
        return row

    def list_interventions(self, experiment_id: str) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM intervention_actions WHERE experiment_id = ? ORDER BY COALESCE(completed_at, planned_at)",
            (experiment_id,),
        )
        for r in rows:
            r["parameters"] = r.pop("parameters_json")
        return rows

    def update_intervention(self, action_id: str, values: dict[str, Any]) -> dict:
        self.db.update("intervention_actions", "action_id", action_id, values)
        return self.get_intervention(action_id)

    # ---------------- metrics ----------------
    def store_metrics(self, experiment_id: str, scope: str, metrics: dict, metric_version: str,
                      session_id: str | None = None) -> None:
        self.db.insert(
            "experiment_metrics",
            {
                "experiment_id": experiment_id,
                "session_id": session_id,
                "scope": scope,
                "metric_version": metric_version,
                "computed_at": utcnow(),
                "metrics_json": metrics,
            },
        )

    def latest_metrics(self, experiment_id: str) -> dict | None:
        return self.db.query_one(
            "SELECT * FROM experiment_metrics WHERE experiment_id = ? AND scope = 'experiment' "
            "ORDER BY metric_id DESC LIMIT 1",
            (experiment_id,),
        )


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)
