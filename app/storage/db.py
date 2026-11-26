"""SQLite storage. Plain sqlite3 + SQL, no ORM (see docs/DECISIONS.md D-003).

Raw observations live in `content_observations`; derived numbers live in
`experiment_metrics` and are always recomputable from raw rows.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS interest_profiles (
    profile_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    topics_json  TEXT NOT NULL,
    version      INTEGER NOT NULL DEFAULT 1,
    is_demo      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interest_profile_versions (
    profile_id    TEXT NOT NULL REFERENCES interest_profiles(profile_id) ON DELETE CASCADE,
    version       INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (profile_id, version)
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id     TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    research_question TEXT NOT NULL DEFAULT '',
    platform          TEXT NOT NULL,
    surface           TEXT NOT NULL,
    profile_id        TEXT NOT NULL REFERENCES interest_profiles(profile_id),
    target_topic      TEXT NOT NULL,
    target_share      REAL NOT NULL DEFAULT 0.2,
    status            TEXT NOT NULL DEFAULT 'active',
    is_demo           INTEGER NOT NULL DEFAULT 0,
    external_provider_consent    INTEGER NOT NULL DEFAULT 0,
    external_provider_consent_at TEXT,
    config_json       TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_sessions (
    session_id         TEXT PRIMARY KEY,
    experiment_id      TEXT NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    checkpoint         TEXT NOT NULL,
    label              TEXT NOT NULL DEFAULT '',
    capture_method     TEXT NOT NULL,
    captured_at        TEXT NOT NULL,
    platform           TEXT NOT NULL,
    surface            TEXT NOT NULL,
    recording_ref      TEXT,
    recording_sha256   TEXT,
    recording_duration_seconds REAL,
    observation_count  INTEGER NOT NULL DEFAULT 0,
    status             TEXT NOT NULL DEFAULT 'created',
    segmentation_json  TEXT,
    sample_status      TEXT NOT NULL DEFAULT 'provisional',
    accepted_at        TEXT,
    deviation_note     TEXT,
    notes              TEXT NOT NULL DEFAULT '',
    is_demo            INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recording_frames (
    frame_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL REFERENCES observation_sessions(session_id) ON DELETE CASCADE,
    frame_index    INTEGER NOT NULL,
    offset_seconds REAL NOT NULL,
    path           TEXT NOT NULL,
    diff_score     REAL,
    ahash          TEXT
);
CREATE INDEX IF NOT EXISTS idx_frames_session ON recording_frames(session_id, frame_index);

CREATE TABLE IF NOT EXISTS content_observations (
    observation_id          TEXT PRIMARY KEY,
    experiment_id           TEXT NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    session_id              TEXT NOT NULL REFERENCES observation_sessions(session_id) ON DELETE CASCADE,
    platform                TEXT NOT NULL,
    surface                 TEXT NOT NULL,
    sequence_number         INTEGER NOT NULL,
    observed_at             TEXT,
    video_offset_seconds    REAL,
    segment_end_seconds     REAL,
    frame_count             INTEGER,
    representative_frame_id INTEGER,
    topic_label             TEXT,
    target_match            TEXT NOT NULL DEFAULT 'unknown',
    confidence              REAL,
    classification_evidence TEXT NOT NULL DEFAULT '[]',
    caption_text            TEXT,
    hashtags                TEXT NOT NULL DEFAULT '[]',
    creator_handle          TEXT,
    recommendation_status   TEXT NOT NULL DEFAULT 'undetermined',
    is_ad                   INTEGER,
    followed_signal         INTEGER,
    eligibility_source      TEXT,
    eligibility_conflict    INTEGER NOT NULL DEFAULT 0,
    content_fingerprint     TEXT,
    classifier_version      TEXT,
    machine_label_json      TEXT,
    review_status           TEXT NOT NULL DEFAULT 'pending',
    segmentation_method     TEXT,
    notes                   TEXT NOT NULL DEFAULT '',
    is_demo                 INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_obs_session ON content_observations(session_id, sequence_number);

CREATE TABLE IF NOT EXISTS intervention_actions (
    action_id        TEXT PRIMARY KEY,
    experiment_id    TEXT NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    checkpoint       TEXT NOT NULL DEFAULT 'T1',
    action_type      TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    parameters_json  TEXT NOT NULL DEFAULT '{}',
    instructions     TEXT NOT NULL DEFAULT '',
    platform         TEXT NOT NULL,
    actuator         TEXT NOT NULL,
    status           TEXT NOT NULL,
    authorization    TEXT,
    planned_at       TEXT NOT NULL,
    completed_at     TEXT,
    evidence_notes   TEXT NOT NULL DEFAULT '',
    is_demo          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS experiment_metrics (
    metric_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id  TEXT NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    session_id     TEXT REFERENCES observation_sessions(session_id) ON DELETE CASCADE,
    scope          TEXT NOT NULL,
    metric_version TEXT NOT NULL,
    computed_at    TEXT NOT NULL,
    metrics_json   TEXT NOT NULL
);
"""

JSON_COLUMNS = {
    "topics_json",
    "config_json",
    "classification_evidence",
    "hashtags",
    "parameters_json",
    "metrics_json",
    "snapshot_json",
    "machine_label_json",
    "segmentation_json",
}
BOOL_COLUMNS = {"is_demo", "is_ad", "external_provider_consent", "followed_signal", "eligibility_conflict"}

# Columns added after schema v1 (D-017). Older databases receive them through additive
# ALTER TABLE statements on open; existing rows and values are never rewritten.
MIGRATION_COLUMNS = {
    "observation_sessions": {
        "sample_status": "TEXT NOT NULL DEFAULT 'provisional'",
        "accepted_at": "TEXT",
        "deviation_note": "TEXT",
    },
    "content_observations": {
        "followed_signal": "INTEGER",
        "eligibility_source": "TEXT",
        "eligibility_conflict": "INTEGER NOT NULL DEFAULT 0",
    },
}


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in row.keys():
        val = row[key]
        if key in JSON_COLUMNS and isinstance(val, str):
            val = json.loads(val)
        elif key in BOOL_COLUMNS and val is not None:
            val = bool(val)
        out[key] = val
    return out


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # One shared connection; FastAPI runs sync endpoints in a thread pool, so serialise access.
        self._lock = threading.RLock()
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL") if self.path != ":memory:" else None
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        for table, cols in MIGRATION_COLUMNS.items():
            existing = {r[1] for r in self._conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for col, ddl in cols.items():
                if col not in existing:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(SCHEMA_VERSION),))

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def query(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [_row_to_dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def query_one(self, sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return _row_to_dict(row) if row else None

    def insert(self, table: str, values: dict[str, Any]) -> int:
        cols = list(values)
        vals = [_encode(c, values[c]) for c in cols]
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
        with self.tx() as c:
            cur = c.execute(sql, vals)
            return cur.lastrowid or 0

    def update(self, table: str, key_col: str, key: Any, values: dict[str, Any]) -> None:
        if not values:
            return
        cols = list(values)
        sets = ", ".join(f"{c} = ?" for c in cols)
        with self.tx() as c:
            c.execute(
                f"UPDATE {table} SET {sets} WHERE {key_col} = ?",
                [_encode(col, values[col]) for col in cols] + [key],
            )

    def execute(self, sql: str, params: tuple | list = ()) -> None:
        with self.tx() as c:
            c.execute(sql, params)

    def close(self) -> None:
        self._conn.close()


def _encode(col: str, val: Any) -> Any:
    if col in JSON_COLUMNS and not isinstance(val, str) and val is not None:
        return json.dumps(val, ensure_ascii=False)
    if isinstance(val, bool):
        return int(val)
    return val
