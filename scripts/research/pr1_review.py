"""Reproduce PR #1 review findings using synthetic inputs only; no external APIs.

Run from the checkout: .venv/bin/python -m scripts.research.pr1_review
This reports observed behavior, not a passing regression suite or experiment data.
"""
import json
import tempfile
from pathlib import Path

from app.config import Settings
from app.models.schemas import TargetMatch
from app.observer import pipeline
from app.observer.classifiers.base import ClassificationInput, ClassificationResult, Classifier
from app.observer.classifiers.mock import MockClassifier
from app.services import compute_plan, compute_summary
from app.storage.db import Database
from app.storage.repository import Repository
from app.taste_engine.profiles import ensure_exp001


class FollowedFixture(Classifier):
    def classify(self, item):
        return ClassificationResult(TargetMatch.DIRECT, "biathlon", 0.95,
                                    ["SYNTHETIC followed-account indicator"], "synthetic-review",
                                    followed_indicator=True)


def main():
    findings = {"data_kind": "SYNTHETIC REVIEW PROBES — NOT EXPERIMENT RESULTS"}
    with tempfile.TemporaryDirectory(prefix="amas-pr1-review-") as td:
        settings = Settings(data_dir=Path(td), _env_file=None, allow_external_providers=False, ocr="off")
        repo = Repository(Database(settings.db_path), settings.data_dir)
        ensure_exp001(repo)
        profile = repo.get_profile("PRF-EXP-001-biathlon")
        findings["keyword_false_positive"] = {
            text: MockClassifier().classify(ClassificationInput("synthetic", profile, caption_text=text)).__dict__
            for text in ("Police pursuit on the highway", "Follow", "Mass start in cycling")
        }

        sid = repo.create_session("EXP-001", checkpoint="T0", capture_method="synthetic")["session_id"]
        repo.add_frames(sid, [dict(frame_index=i, offset_seconds=float(i), path="synthetic.jpg") for i in range(12)])
        pipeline.set_manual_boundaries(repo, sid, [4.0, 8.0])
        rows = repo.list_observations(session_id=sid)
        for o in rows:
            repo.update_observation(o["observation_id"], dict(target_match="unrelated", topic_label="synthetic",
                review_status="confirmed", recommendation_status="recommended", is_ad=False))
        after = pipeline.merge_with_next(repo, rows[0]["observation_id"])
        findings["merge_discards_untouched_labels"] = {
            "before_count": len(rows), "after_count": len(after),
            "untouched_third_segment_after_merge": {k: after[-1][k] for k in
                ("observation_id", "video_offset_seconds", "target_match", "review_status", "recommendation_status", "is_ad")},
            "old_third_id_survives": any(o["observation_id"] == rows[-1]["observation_id"] for o in after),
        }
        first = after[0]
        repo.update_observation(first["observation_id"], {"recommendation_status": "recommended", "is_ad": True})
        pipeline.apply_correction(repo, first["observation_id"], {"is_ad": None})
        findings["explicit_null_cannot_clear_ad"] = repo.get_observation(first["observation_id"])["is_ad"]
        repo.update_observation(first["observation_id"], {"is_ad": False})
        pipeline.classify_session(repo, settings, sid, FollowedFixture())
        findings["following_ignored_after_bulk_recommended"] = repo.get_observation(first["observation_id"])["recommendation_status"]
        pipeline.apply_correction(repo, first["observation_id"], {"target_match": "unknown"})
        findings["unknown_correction_confidence"] = repo.get_observation(first["observation_id"])["confidence"]

        compute_summary(repo, "EXP-001", store=True)
        repo.delete_session(sid)
        findings["deleted_session_retained_in_experiment_snapshot"] = any(
            s["session_id"] == sid for s in repo.latest_metrics("EXP-001")["metrics_json"]["sessions"])

        for _ in range(2):
            s = repo.create_session("EXP-001", checkpoint="T0", capture_method="synthetic")
            repo.add_observation(s["session_id"], {"target_match": "unrelated", "review_status": "confirmed",
                                                   "recommendation_status": "recommended"})
        findings["two_single_item_baselines_plan"] = compute_plan(repo, "EXP-001")["status"]

        # Adapted in the R5/R6/N1 implementation PR: naive entry values are now refused, which used to
        # abort this probe before it printed. Record the refusal, then store the naive value directly to keep
        # probing the legacy-row path the original R6 reproduction exercised.
        try:
            s = repo.create_session("EXP-001", checkpoint="T2", capture_method="synthetic",
                                    captured_at="2026-11-26T12:00:00")
            findings["naive_capture_entry"] = "accepted"
        except ValueError as e:
            findings["naive_capture_entry"] = f"rejected: {e}"
            s = repo.create_session("EXP-001", checkpoint="T2", capture_method="synthetic")
            repo.update_session(s["session_id"], {"captured_at": "2026-11-26T12:00:00"})
        repo.add_intervention("EXP-001", dict(action_type="custom", actuator="manual", status="completed",
                                              completed_at="2026-11-26T11:00:00+00:00"))
        try:
            summ = compute_summary(repo, "EXP-001")
            row = next(r for r in summ["sessions"] if r["session_id"] == s["session_id"])
            findings["naive_capture_timestamp"] = {k: row.get(k) for k in (
                "captured_at", "hours_after_intervention", "timezone_assumed_utc", "capture_time_verified")}
        except Exception as e:
            findings["naive_capture_timestamp"] = f"{type(e).__name__}: {e}"
        repo.db.close()
    print(json.dumps(findings, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
