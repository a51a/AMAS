"""Application services: glue between repository and pure engines."""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from app.adapters.registry import adapter_for
from app.evaluator.metrics import METRIC_VERSION, experiment_summary
from app.strategist.rules import build_plan
from app.storage.repository import Repository

EXPORT_COLUMNS = [
    "observation_id", "experiment_id", "session_id", "checkpoint", "platform", "surface", "sequence_number",
    "observed_at", "video_offset_seconds", "segment_end_seconds", "topic_label", "target_match", "confidence",
    "classification_evidence", "caption_text", "hashtags", "creator_handle", "recommendation_status", "is_ad",
    "content_fingerprint", "classifier_version", "review_status", "segmentation_method", "is_demo", "notes",
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
        row["classification_evidence"] = " | ".join(o.get("classification_evidence") or [])
        row["hashtags"] = " ".join(o.get("hashtags") or [])
        w.writerow(row)
    return buf.getvalue()


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
