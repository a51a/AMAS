"""Application services: glue between repository and pure engines."""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from app.adapters.registry import adapter_for
from app.evaluator.metrics import METRIC_VERSION, experiment_summary, sample_readiness
from app.models.schemas import utcnow
from app.strategist.rules import build_plan
from app.storage.repository import Repository

EXPORT_COLUMNS = [
    "observation_id", "experiment_id", "session_id", "checkpoint", "platform", "surface", "sequence_number",
    "observed_at", "video_offset_seconds", "segment_end_seconds", "topic_label", "target_match", "confidence",
    "classification_evidence", "caption_text", "hashtags", "creator_handle", "recommendation_status", "is_ad",
    "content_fingerprint", "classifier_version", "review_status", "segmentation_method", "is_demo", "notes",
    "followed_signal", "eligibility_source", "eligibility_conflict", "sample_status", "deviation_note",
]


def compute_summary(repo: Repository, experiment_id: str, *, store: bool = False) -> dict:
    exp = repo.get_experiment(experiment_id)
    summary = experiment_summary(
        exp, repo.list_sessions(experiment_id), repo.list_observations(experiment_id=experiment_id),
        repo.list_interventions(experiment_id),
    )
    if store:
        repo.store_metrics(experiment_id, "experiment", summary, METRIC_VERSION)
        for row in summary["sessions"]:
            repo.store_metrics(experiment_id, "session", row["metrics"], METRIC_VERSION, session_id=row["session_id"])
    return summary


class ProtocolError(ValueError):
    def __init__(self, message: str, problems: list[str]):
        super().__init__(message)
        self.problems = problems


def accept_sample(repo: Repository, session_id: str, *, deviation_note: str | None = None) -> dict:
    """Explicitly accept a sample for the protocol (R4, D-021).

    A complete sample (enough Reels, every one human-reviewed, eligibility resolved) is accepted as is.
    An incomplete one is accepted only with a non-empty deviation note, which is stored and reported.
    """
    s = repo.get_session(session_id)
    exp = repo.get_experiment(s["experiment_id"])
    required = int((exp.get("config") or {}).get("reels_per_sample") or 50)
    check = sample_readiness(repo.list_observations(session_id=session_id), required)
    note = (deviation_note or "").strip() or None
    if check["observations"] == 0:
        raise ProtocolError("An empty sample cannot be accepted.", check["problems"])
    if not check["complete"] and note is None:
        raise ProtocolError("Sample does not meet the protocol. Fix it or accept it with a deviation_note that "
                            "explains the deviation.", check["problems"])
    return repo.update_session(session_id, {"sample_status": "accepted", "accepted_at": utcnow(),
                                            "deviation_note": None if check["complete"] else note})


def unaccept_sample(repo: Repository, session_id: str) -> dict:
    return repo.update_session(session_id, {"sample_status": "provisional", "accepted_at": None,
                                            "deviation_note": None})


def compute_plan(repo: Repository, experiment_id: str) -> dict:
    exp = repo.get_experiment(experiment_id)
    return build_plan(exp, compute_summary(repo, experiment_id), repo.list_interventions(experiment_id),
                      adapter_for(exp["platform"]))


def export_json(repo: Repository, experiment_id: str) -> dict[str, Any]:
    exp = repo.get_experiment(experiment_id)
    return {
        "export_format": "amas-export-v1",
        "is_demo": bool(exp["is_demo"]),
        "data_label": "SIMULATED DEMO DATA - not research findings" if exp["is_demo"] else "Real experiment data",
        "experiment": exp,
        "profile": repo.get_profile(exp["profile_id"]),
        "sessions": repo.list_sessions(experiment_id),
        "observations": repo.list_observations(experiment_id=experiment_id),
        "interventions": repo.list_interventions(experiment_id),
        "derived_metrics": compute_summary(repo, experiment_id),
    }


def export_csv(repo: Repository, experiment_id: str) -> str:
    sessions = {s["session_id"]: s for s in repo.list_sessions(experiment_id)}
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for o in repo.list_observations(experiment_id=experiment_id):
        row = dict(o)
        row["checkpoint"] = sessions[o["session_id"]]["checkpoint"]
        row["sample_status"] = sessions[o["session_id"]].get("sample_status")
        row["deviation_note"] = sessions[o["session_id"]].get("deviation_note")
        row["classification_evidence"] = " | ".join(o.get("classification_evidence") or [])
        row["hashtags"] = " ".join(o.get("hashtags") or [])
        w.writerow(row)
    return buf.getvalue()


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
