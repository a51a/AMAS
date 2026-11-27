"""Strategist v1: deterministic rules that compare the observed distribution with the
target profile and produce a human-readable intervention plan. It never executes
anything; actions go through an Actuator after the user decides."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.adapters.base import PlatformAdapter
from app.models.schemas import CHECKPOINT_OFFSETS_HOURS, parse_stored_timestamp

STRATEGIST_VERSION = "rules-v2"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _rec(adapter: PlatformAdapter, action_type: str, priority: str, rationale: str, **params) -> dict:
    spec = adapter.get_action(action_type)
    return {
        "action_type": action_type,
        "title": spec.title,
        "priority": priority,
        "rationale": rationale,
        "parameters": {**spec.default_parameters, **params},
        "instructions": adapter.render_instructions(action_type, params),
        "confound_note": spec.confound_note,
    }


def _readiness(summary: dict) -> dict:
    return summary.get("baseline_readiness") or {"ready": False, "required_sessions": 2, "required_reels": 50,
                                                 "problems": ["Baseline readiness was not computed."]}


def _data_quality_findings(summary: dict) -> list[str]:
    findings = []
    for row in summary["sessions"]:
        m = row["metrics"]
        if m["review"]["pending"] or m["review"]["needs_review"]:
            findings.append(f"{row['checkpoint']}: {m['review']['pending'] + m['review']['needs_review']} observations "
                            "still need classification review.")
        if m["eligibility"]["undetermined"]:
            findings.append(f"{row['checkpoint']}: {m['eligibility']['undetermined']} observations have undetermined "
                            "eligibility (mark as recommended / followed / search).")
        if m["eligibility"].get("conflicts"):
            findings.append(f"{row['checkpoint']}: {m['eligibility']['conflicts']} observations have conflicting "
                            "eligibility evidence (followed-account marker vs. 'recommended').")
    return findings


def intervention_gate(summary: dict, interventions: list[dict]) -> dict:
    """Single source of truth for 'may a T1 intervention be planned without an override?' (C2, D-023).

    Used by both the strategist and the intervention API so they cannot disagree. Before the first completed
    intervention, any open review item blocks planning; afterwards only baseline readiness is re-checked.
    """
    problems = list(_readiness(summary)["problems"]) if not _readiness(summary)["ready"] else []
    if not any(a["status"] in ("completed", "simulated") for a in interventions):
        problems += _data_quality_findings(summary)
    return {"open": not problems, "problems": problems}


def next_checkpoint(summary: dict, interventions: list[dict]) -> dict | None:
    done = {t["checkpoint"] for t in summary["trend"]}
    completed = [a for a in interventions if a["status"] in ("completed", "simulated") and a.get("completed_at")]
    ready = _readiness(summary)
    if not completed and not ready["ready"]:
        return {"checkpoint": "T0", "due_at": None,
                "note": f"Record, review and accept the baseline ({ready['required_sessions']} x "
                        f"{ready['required_reels']} Reels)."}
    if not completed:
        return {"checkpoint": "T1", "due_at": None, "note": "Perform and log the intervention."}
    times = [t for t in (parse_stored_timestamp(a["completed_at"])[0] for a in completed) if t]
    if not times:
        return {"checkpoint": "T2", "due_at": None, "note": "Intervention completion time is not parseable; fix it."}
    anchor = min(times)
    for cp, hours in CHECKPOINT_OFFSETS_HOURS.items():
        if cp not in done:
            return {"checkpoint": cp, "due_at": (anchor + timedelta(hours=hours)).isoformat(timespec="minutes"),
                    "note": f"Sample 50 Reels {'immediately' if hours == 0 else f'{hours}h after the intervention'}."}
    return None


def build_plan(experiment: dict, summary: dict, interventions: list[dict], adapter: PlatformAdapter) -> dict:
    target = experiment.get("target_share") or 0.2
    topic = experiment.get("target_topic")
    findings: list[str] = []
    recs: list[dict] = []
    status = "on_track"

    baseline = summary.get("baseline")
    latest = summary.get("latest")
    nxt = next_checkpoint(summary, interventions)

    readiness = _readiness(summary)
    completed_any = any(a["status"] in ("completed", "simulated") for a in interventions)
    if baseline is None or (not readiness["ready"] and not completed_any):
        status = "collect_baseline"
        findings.append(f"Baseline not ready. The protocol needs {readiness['required_sessions']} accepted T0 "
                        f"sessions of {readiness['required_reels']} human-reviewed Reels before any intervention.")
        findings.extend(readiness["problems"])
        return _plan(experiment, status, findings, recs, nxt, summary)
    if not readiness["ready"]:
        findings.append("Baseline was not ready when the intervention was logged; results are a protocol deviation.")

    findings.append(f"Baseline direct {topic} share: {_pct(baseline['direct_share'])} "
                    f"over {baseline['exposures_eligible']} eligible exposures.")

    quality = _data_quality_findings(summary)
    findings.extend(quality)
    if quality:
        status = "review_data"

    current = latest["metrics"]["direct_share"] if latest else baseline["direct_share"]
    gap = target - (current or 0)
    adjacent = (latest or {"metrics": baseline})["metrics"]["shares"].get("adjacent") or 0
    completed = [a for a in interventions if a["status"] in ("completed", "simulated")]

    if not completed and status == "review_data":
        findings.append("Resolve the review items above before planning an intervention.")
        nxt = {"checkpoint": "REVIEW", "due_at": None, "note": "Review flagged observations, then re-check the plan."}
    elif not completed:
        status = "intervene"
        findings.append(f"No intervention yet. Gap to the {_pct(target)} target: {gap * 100:.1f} pp.")
        recs.append(_rec(adapter, "search_and_watch_target", "high",
                         "Strongest documented signal you can create yourself: deliberate search and full watches.",
                         query=topic, count=10, topic=topic) if _has(adapter, "search_and_watch_target") else None)
        recs.append(_rec(adapter, "engage_target", "medium", "Adds explicit positive feedback on watched items.",
                         topic=topic, count=5) if _has(adapter, "engage_target") else None)
        recs.append(_rec(adapter, "follow_target_accounts", "low",
                         "Follows add a strong signal but their content is excluded from the primary metric.",
                         topic=topic, count=3) if _has(adapter, "follow_target_accounts") else None)
    elif current is not None and current >= target:
        findings.append(f"Latest share {_pct(current)} meets the {_pct(target)} target. Measure persistence; "
                        "avoid new interventions so T3-T5 remain interpretable.")
        status = "measure_persistence" if status != "review_data" else status
    else:
        findings.append(f"Latest share {_pct(current)} is {gap * 100:.1f} pp below target.")
        decaying = [p for p in summary["persistence"] if p.get("measured") and p.get("retention_of_T2_lift") is not None
                    and p["retention_of_T2_lift"] < 0.5]
        if decaying:
            findings.append("Effect is decaying (less than half of the T2 lift retained).")
        if adjacent and current is not None and adjacent > current:
            findings.append(f"Adjacent content ({_pct(adjacent)}) exceeds direct; the system may generalise to "
                            "winter sports instead of biathlon. Prefer biathlon-specific signals.")
        pending_checkpoints = nxt and nxt["checkpoint"] in ("T3", "T4", "T5")
        if pending_checkpoints:
            findings.append("A second intervention now would confound the scheduled persistence checkpoints. "
                            "Recommended: finish T3-T5 first, then plan a follow-up experiment phase.")
            status = "measure_persistence" if status != "review_data" else status
        else:
            status = "intervene" if status != "review_data" else status
            if _has(adapter, "search_and_watch_target"):
                recs.append(_rec(adapter, "search_and_watch_target", "high", "Reinforce with a second round.",
                                 query=topic, count=10, topic=topic))
            if _has(adapter, "feed_dwell_target"):
                recs.append(_rec(adapter, "feed_dwell_target", "medium",
                                 "Reward target items surfaced by the feed itself.", topic=topic))

    return _plan(experiment, status, findings, [r for r in recs if r], nxt, summary)


def _has(adapter: PlatformAdapter, action_type: str) -> bool:
    return any(a.action_type == action_type for a in adapter.action_catalog())


def _plan(experiment, status, findings, recs, nxt, summary) -> dict:
    headline = {
        "collect_baseline": "Collect the T0 baseline first.",
        "review_data": "Review observations before drawing conclusions.",
        "intervene": "Plan and log a documented intervention.",
        "measure_persistence": "Keep measuring; do not intervene during persistence checkpoints.",
        "on_track": "On track.",
    }[status]
    return {
        "strategist_version": STRATEGIST_VERSION,
        "experiment_id": experiment["experiment_id"],
        "is_demo": bool(experiment.get("is_demo")),
        "status": status,
        "headline": headline,
        "findings": findings,
        "recommended_actions": recs,
        "next_checkpoint": nxt,
        "disclaimer": "Recommendations are rules-based suggestions. You decide and perform every action yourself.",
    }
