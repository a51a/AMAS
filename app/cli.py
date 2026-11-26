"""Command line: `python -m app.cli <command>` or `amas <command>` after `pip install -e .`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.storage.db import Database
from app.storage.repository import Repository
from app.taste_engine.profiles import ensure_exp001


def _repo() -> Repository:
    s = get_settings()
    r = Repository(Database(s.db_path), s.data_dir)
    ensure_exp001(r)
    return r


def cmd_serve(a):
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:create_app", factory=True, host=a.host or s.host, port=a.port or s.port, reload=a.reload)


def cmd_init(a):
    r = _repo()
    print(f"Database ready at {get_settings().db_path}. Experiments: {[e['experiment_id'] for e in r.list_experiments()]}")


def cmd_seed_demo(a):
    from app.demo import seed_demo

    exp = seed_demo(_repo(), seed=a.seed)
    print(f"Seeded {exp['experiment_id']} (SIMULATED demo data, is_demo=1).")


def cmd_new_session(a):
    r = _repo()
    s = r.create_session(a.experiment, checkpoint=a.checkpoint, capture_method="screen_recording", label=a.label or "")
    print(s["session_id"])


def cmd_import(a):
    from app.observer.pipeline import import_recording

    r = _repo()
    sid = a.session
    if not sid:
        sid = r.create_session(a.experiment, checkpoint=a.checkpoint, capture_method="screen_recording",
                               label=a.label or Path(a.path).name)["session_id"]
    s = import_recording(r, get_settings(), sid, Path(a.path).expanduser())
    print(json.dumps({"session_id": sid, "observations": s["observation_count"],
                      "duration_seconds": s["recording_duration_seconds"]}, indent=2))


def cmd_classify(a):
    from app.observer.pipeline import classify_session, get_classifier

    r, s = _repo(), get_settings()
    print(json.dumps(classify_session(r, s, a.session, get_classifier(a.classifier, s)), indent=2))


def cmd_summary(a):
    from app.services import compute_summary

    summ = compute_summary(_repo(), a.experiment, store=True)
    print(json.dumps({k: summ[k] for k in ("experiment_id", "is_demo", "baseline_session_count", "target_reached",
                                           "time_to_first_target", "persistence", "warnings")}, indent=2, default=str))


def cmd_export(a):
    from app.services import dumps, export_csv, export_json

    r = _repo()
    out = Path(a.out) if a.out else get_settings().exports_dir / f"{a.experiment}.{a.format}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(export_csv(r, a.experiment) if a.format == "csv" else dumps(export_json(r, a.experiment)),
                   encoding="utf-8")
    print(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="amas", description="AMAS local MVP")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("serve", help="Start the Control Center web app")
    sp.add_argument("--host"), sp.add_argument("--port", type=int), sp.add_argument("--reload", action="store_true")
    sp.set_defaults(fn=cmd_serve)

    sub.add_parser("init", help="Create the database and EXP-001").set_defaults(fn=cmd_init)

    sp = sub.add_parser("seed-demo", help="Create the SIMULATED DEMO-001 experiment")
    sp.add_argument("--seed", type=int, default=7)
    sp.set_defaults(fn=cmd_seed_demo)

    sp = sub.add_parser("new-session", help="Create an observation session")
    sp.add_argument("--experiment", default="EXP-001"), sp.add_argument("--checkpoint", default="T0")
    sp.add_argument("--label")
    sp.set_defaults(fn=cmd_new_session)

    sp = sub.add_parser("import", help="Import a screen recording (MP4/MOV) into a session")
    sp.add_argument("path")
    sp.add_argument("--session"), sp.add_argument("--experiment", default="EXP-001")
    sp.add_argument("--checkpoint", default="T0"), sp.add_argument("--label")
    sp.set_defaults(fn=cmd_import)

    sp = sub.add_parser("classify", help="Classify a session")
    sp.add_argument("session"), sp.add_argument("--classifier", default="mock")
    sp.set_defaults(fn=cmd_classify)

    sp = sub.add_parser("summary", help="Compute and store metrics")
    sp.add_argument("--experiment", default="EXP-001")
    sp.set_defaults(fn=cmd_summary)

    sp = sub.add_parser("export", help="Export observations (csv) or everything (json)")
    sp.add_argument("--experiment", default="EXP-001"), sp.add_argument("--format", choices=["csv", "json"], default="json")
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_export)

    a = p.parse_args(argv)
    a.fn(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
