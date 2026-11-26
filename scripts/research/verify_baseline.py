"""Read-only, independent consistency checks of local BASELINE-001 artifacts."""
import csv
import hashlib
import json
import sqlite3
from pathlib import Path


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    root = Path("data/research/BASELINE-001")
    manifest = json.loads((root / "manifest.json").read_text())
    report = json.loads((root / "analysis.json").read_text())
    exported = json.loads((root / "amas-export.json").read_text())
    with sqlite3.connect("file:data/amas.sqlite?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        sid = manifest["session_id"]
        session = dict(db.execute("SELECT * FROM observation_sessions WHERE session_id=?", (sid,)).fetchone())
        observations = [dict(x) for x in db.execute("SELECT * FROM content_observations WHERE session_id=? ORDER BY sequence_number", (sid,))]
        frames = [dict(x) for x in db.execute("SELECT * FROM recording_frames WHERE session_id=? ORDER BY frame_index", (sid,))]
        assert db.execute("SELECT external_provider_consent FROM experiments WHERE experiment_id='EXP-001'").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM intervention_actions WHERE experiment_id='EXP-001'").fetchone()[0] == 0
    assert session["checkpoint"] == "T0" and session["label"] == "BASELINE-001" and not session["is_demo"]
    assert session["observation_count"] == len(observations) == len(exported["observations"])
    assert len(list(csv.DictReader((root / "observations.csv").open()))) == len(observations)
    assert observations[0]["video_offset_seconds"] == 0
    assert observations[-1]["segment_end_seconds"] == manifest["recording_duration_seconds"]
    assert sum(o["frame_count"] for o in observations) == len(frames)
    frame_by_id = {f["frame_id"]: f for f in frames}
    for i, o in enumerate(observations):
        assert not o["is_demo"] and o["review_status"] == "needs_review"
        assert o["sequence_number"] == i+1
        if i:
            assert o["video_offset_seconds"] == observations[i-1]["segment_end_seconds"]
        rep = frame_by_id[o["representative_frame_id"]]
        assert o["video_offset_seconds"] <= rep["offset_seconds"] < o["segment_end_seconds"]
        assert Path(rep["path"]).is_file()
    eligible = [o for o in observations if o["recommendation_status"] == "recommended" and not o["is_ad"]]
    m = report["metrics"]
    assert m["exposures_eligible"] == len(eligible)
    for label in ("direct", "adjacent", "unrelated", "unknown"):
        assert m["counts"][label] == sum(o["target_match"] == label for o in eligible)
        assert m["all_exposure"]["counts"][label] == sum(o["target_match"] == label for o in observations)
    assert m["direct_share"] == sum(o["target_match"] == "direct" for o in eligible)/len(eligible)
    assert all(Path(f["path"]).is_file() for f in frames)
    assert report["evidence_sha256"] == digest(root / "local-vision.jsonl")
    assert digest(manifest["source_path"]) == manifest["source_sha256"] == digest(session["recording_ref"])
    assert Path(manifest["source_path"]).stat().st_mtime_ns == manifest["source_mtime_ns"]
    assert not exported["is_demo"] and exported["export_format"] == "amas-export-v1"
    assert not any(x in (root / "review.html").read_text().lower() for x in ("<script", 'src="http', 'href="http'))
    print(json.dumps(dict(verified=True, observations=len(observations), frames=len(frames), eligible=len(eligible),
        source_unchanged=True, exports_consistent=True, external_consent=False, human_reviewed=0), indent=2))


if __name__ == "__main__":
    main()
