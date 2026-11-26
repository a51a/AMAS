"""Independent PR #3 edge-case probes. Synthetic data only; no images or APIs.

Run: .venv/bin/python -m scripts.research.pr3_review
Exit 0 means the probes ran, not that the observed behavior is correct.
"""
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.observer import pipeline
from app.observer.classifiers.mock import MockClassifier
from app.services import accept_sample, compute_plan, compute_summary
from app.storage.db import Database
from app.storage.repository import Repository
from app.taste_engine.profiles import LEGACY_V1_BIATHLON_KEYWORDS, ensure_exp001


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(prefix="amas-pr3-review-") as td:
        settings = Settings(data_dir=Path(td), _env_file=None,
                            allow_external_providers=False, ocr="off")
        repo = Repository(Database(settings.db_path), settings.data_dir)
        ensure_exp001(repo)
        try:
            yield repo, settings
        finally:
            repo.db.close()


def sample(repo, n, **extra):
    sid = repo.create_session("EXP-001", checkpoint="T0", capture_method="synthetic")["session_id"]
    for _ in range(n):
        repo.add_observation(sid, {"target_match": "unrelated", "review_status": "confirmed",
                                  "recommendation_status": "recommended", "is_ad": False, **extra})
    return sid


def main():
    out = {"data_kind": "SYNTHETIC REVIEW PROBES - NOT EXPERIMENT RESULTS"}
    with fixture() as (repo, _):
        pid = "PRF-EXP-001-biathlon"
        topics = repo.get_profile(pid)["topics"]
        topics[0].update(keywords=sorted(LEGACY_V1_BIATHLON_KEYWORDS),
                         description="User-authored description", target_weight=0.35,
                         context_keywords=["user-context"])
        topics[1]["keywords"].append("user-adjacent-keyword")
        topics.append({"topic_id": "user-topic", "label": "User topic", "tier": "adjacent",
                       "polarity": "positive", "keywords": ["custom sport"]})
        repo.update_profile(pid, {"topics": topics})
        before = repo.get_profile(pid)
        ensure_exp001(repo)
        after = repo.get_profile(pid)
        out["C1_profile_upgrade_overwrites_edits"] = {
            "before_version": before["version"], "after_version": after["version"],
            "custom_topic_survives": any(t["topic_id"] == "user-topic" for t in after["topics"]),
            "adjacent_edit_survives": "user-adjacent-keyword" in after["topics"][1]["keywords"],
            "description_survives": after["topics"][0]["description"] == "User-authored description",
            "target_weight_after": after["topics"][0]["target_weight"],
        }
    with fixture() as (repo, settings):
        a, b = sample(repo, 40), sample(repo, 50)
        accept_sample(repo, a, deviation_note="Recording stopped after 40 Reels; size deviation only.")
        accept_sample(repo, b)
        before_ready = compute_summary(repo, "EXP-001")["baseline_readiness"]["ready"]
        oid = repo.list_observations(session_id=a)[0]["observation_id"]
        repo.update_observation(oid, {"review_status": "needs_review", "eligibility_conflict": True})
        readiness = compute_summary(repo, "EXP-001")["baseline_readiness"]
        app = create_app(settings)
        try:
            with TestClient(app) as client:
                response = client.post("/api/experiments/EXP-001/interventions",
                    json={"action_type": "search_and_watch_target", "actuator": "manual"})
            out["C2_old_size_deviation_waives_new_review_conflict"] = {
                "before_ready": before_ready, "after_ready": readiness["ready"],
                "unreviewed": sum(s["unreviewed"] for s in readiness["sessions"]),
                "conflicts": sum(s["conflicts"] for s in readiness["sessions"]),
                "intervention_without_override_http": response.status_code,
                "action_has_override": "baseline_override" in response.json().get("parameters", {}),
                "strategist_status": compute_plan(repo, "EXP-001")["status"],
            }
        finally:
            app.state.repo.db.close()
    with fixture() as (repo, settings):
        sid = repo.create_session("EXP-001", checkpoint="T0", capture_method="synthetic")["session_id"]
        repo.add_frames(sid, [dict(frame_index=i, offset_seconds=float(i), path="synthetic.jpg")
                             for i in range(12)])
        rows = pipeline.set_manual_boundaries(repo, sid, [4.0, 8.0])
        for row in rows:
            repo.update_observation(row["observation_id"], {"target_match": "unrelated",
                "review_status": "confirmed", "recommendation_status": "recommended", "is_ad": False})
        first, absorbed = rows[0]["observation_id"], rows[1]["observation_id"]
        pipeline.merge_with_next(repo, first)
        evidence_before = repo.get_observation(first)["classification_evidence"]
        pipeline.classify_session(repo, settings, sid, MockClassifier())
        evidence_after = repo.get_observation(first)["classification_evidence"]
        out["C3_reclassification_erases_merge_history"] = {
            "absorbed_row_still_exists": repo.get_observation(absorbed, missing_ok=True) is not None,
            "absorbed_id_in_evidence_before": any(absorbed in e for e in evidence_before),
            "absorbed_id_in_evidence_after": any(absorbed in e for e in evidence_after),
            "boundary_history_survives": any("Boundaries changed" in e for e in evidence_after),
        }
    with fixture() as (repo, _):
        for _ in range(2):
            accept_sample(repo, sample(repo, 50, is_ad=True))
        summary = compute_summary(repo, "EXP-001")
        plan = compute_plan(repo, "EXP-001")
        out["C4_zero_eligible_baseline"] = {
            "ready": summary["baseline_readiness"]["ready"],
            "eligible": summary["baseline"]["exposures_eligible"],
            "direct_share": summary["baseline"]["direct_share"],
            "strategist_status": plan["status"],
            "recommended_actions": len(plan["recommended_actions"]),
        }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
