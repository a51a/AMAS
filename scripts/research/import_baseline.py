"""Import a real recording with source provenance; preserve original bytes.

Run: .venv/bin/python -m scripts.research.import_baseline /path/to/recording.mov
Local-only output: data/research/BASELINE-001/. Does not classify or contact a provider.
"""
import json
import subprocess
import sys
from pathlib import Path

from app.config import Settings
from app.observer.media import sha256_file
from app.observer.pipeline import import_recording
from app.services import export_json
from app.storage.db import Database
from app.storage.repository import Repository
from app.taste_engine.profiles import ensure_exp001


def main():
    source = Path(sys.argv[1]).resolve()
    out = Path("data/research/BASELINE-001")
    out.mkdir(parents=True, exist_ok=True)
    if (out / "manifest.json").exists():
        raise SystemExit("Manifest already exists; refusing to duplicate the baseline.")
    stat = source.stat()
    digest = sha256_file(source)
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source)]))
    capture = probe["format"].get("tags", {}).get("creation_time")
    if not capture:
        raise SystemExit("No capture timestamp metadata; supply a documented timestamp before importing.")
    settings = Settings(data_dir=Path("data"), _env_file=None, allow_external_providers=False, ocr="off")
    settings.ensure_dirs()
    repo = Repository(Database(settings.db_path), settings.data_dir)
    ensure_exp001(repo)
    if any(s["label"] == "BASELINE-001" for s in repo.list_sessions("EXP-001")):
        raise SystemExit("BASELINE-001 already exists; inspect state before resuming.")
    session = repo.create_session("EXP-001", checkpoint="T0", capture_method="screen_recording", label="BASELINE-001",
        captured_at=capture, notes="REAL DATA. Capture time from MOV creation_time (agrees with filename); not independently verified. Automated segmentation is provisional. All imagery stays on-device.")
    session = import_recording(repo, settings, session["session_id"], source)
    (out / "stock-import.json").write_text(json.dumps(export_json(repo, "EXP-001"), indent=2))
    after = source.stat()
    assert digest == session["recording_sha256"] == sha256_file(source)
    assert (stat.st_size, stat.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    manifest = dict(recording_id="BASELINE-001", experiment_id="EXP-001", checkpoint="T0", is_demo=False,
        source_path=str(source), source_bytes=stat.st_size, source_mtime_ns=stat.st_mtime_ns, source_sha256=digest,
        source_unchanged_verified=True, session_id=session["session_id"], captured_at=capture,
        capture_time_evidence="MOV creation_time; filename agrees; not independently verified",
        recording_duration_seconds=session["recording_duration_seconds"], original_probe=probe,
        stock_segmentation=session["segmentation_json"], stock_candidate_count=session["observation_count"],
        privacy="No images or video sent to external APIs, including the Codex conversation.")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    repo.db.close()
    print(json.dumps({k: manifest[k] for k in ("recording_id", "session_id", "captured_at", "recording_duration_seconds", "stock_candidate_count", "source_unchanged_verified", "stock_segmentation")}, indent=2))


if __name__ == "__main__":
    main()
