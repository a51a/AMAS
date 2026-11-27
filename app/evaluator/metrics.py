"""Evaluation Engine.

Pure functions over raw observation / session / intervention rows (dicts as
returned by the repository). Nothing here touches the database, so metrics are
reproducible and easy to unit test.

Primary metric:
    direct target recommendations / eligible recommendation exposures

Eligible exposure = recommendation_status == 'recommended' AND not an identified ad.
Unknown topic classifications stay in the denominator. Ads, search results and
followed-account content are excluded. Exposures whose eligibility is
'undetermined' are excluded from the primary metric, flagged, and covered by a
separate all-exposure metric. Exposures with an unresolved eligibility conflict
(e.g. marked recommended but a followed-account marker was detected, R3) are
treated the same way until a human resolves them.

Baseline readiness (R4) checks the T0 protocol (sessions x Reels, review state)
and explicit acceptance before the strategist may suggest a T1 intervention.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from app.models.schemas import CHECKPOINT_OFFSETS_HOURS, VERIFIED_CAPTURE_SOURCES, parse_stored_timestamp
from app.evaluator.stats import hamming_hex, newcombe_diff_interval, wilson_interval

METRIC_VERSION = "eval-v2"
AHASH_PREFIX = "ahash:"
AHASH_MAX_DISTANCE = 6
TARGET_LABELS = ("direct", "adjacent", "unrelated", "unknown")

CAVEATS = [
    "Confidence intervals assume independent exposures. Consecutive feed items are not independent, "
    "so intervals are optimistic; treat them as a rough guide, not a significance test.",
    "Samples come from a single account and a single surface; results do not generalise to other users.",
    "The platform's ranking changes for many reasons unrelated to the intervention (time of day, trends, "
    "seasonal sports calendar). Before/after differences are associations, not proof of causation.",
]


HUMAN_REVIEWED = ("confirmed", "corrected")


def is_eligible(o: dict) -> bool:
    return (o.get("recommendation_status") == "recommended" and not o.get("is_ad")
            and not o.get("eligibility_conflict"))


def sample_readiness(observations: list[dict], required_reels: int) -> dict[str, Any]:
    """Protocol completeness of one sample: size, human review and resolved eligibility."""
    n = len(observations)
    unreviewed = sum(1 for o in observations if o.get("review_status") not in HUMAN_REVIEWED)
    undetermined = sum(1 for o in observations if (o.get("recommendation_status") or "undetermined") == "undetermined")
    conflicts = sum(1 for o in observations if o.get("eligibility_conflict"))
    unknown_ad = sum(1 for o in observations if o.get("is_ad") is None)
    problems = []
    if n < required_reels:
        problems.append(f"{n} of {required_reels} Reels recorded")
    if unreviewed:
        problems.append(f"{unreviewed} observations not human-reviewed (confirm or correct each one)")
    if undetermined:
        problems.append(f"{undetermined} observations have undetermined eligibility")
    if conflicts:
        problems.append(f"{conflicts} observations have an unresolved eligibility conflict")
    return {"observations": n, "required_reels": required_reels, "unreviewed": unreviewed,
            "undetermined": undetermined, "conflicts": conflicts, "unknown_ad_status": unknown_ad,
            "complete": not problems, "problems": problems}


# Fields whose change after acceptance invalidates the accepted sample (C2, D-023).
REVISION_FIELDS = ("observation_id", "sequence_number", "video_offset_seconds", "segment_end_seconds",
                   "target_match", "topic_label", "recommendation_status", "is_ad", "review_status",
                   "eligibility_conflict", "followed_signal")


def sample_revision(observations: list[dict]) -> str:
    """Stable fingerprint of the reviewed content of a sample. Any boundary edit, relabel, reclassification,
    eligibility or conflict change, or added/deleted observation produces a different revision."""
    rows = [[o.get(k) for k in REVISION_FIELDS]
            for o in sorted(observations, key=lambda o: (o.get("sequence_number") or 0, o.get("observation_id")))]
    return "rev1:" + hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()[:24]


def baseline_readiness(experiment: dict, sessions: list[dict], observations: list[dict]) -> dict[str, Any]:
    """Is the T0 baseline good enough to plan a T1 intervention?

    A T0 session counts when it is explicitly accepted, its data is unchanged since acceptance (same revision),
    and it either meets the protocol or every current problem is covered by the deviation recorded at
    acceptance. Readiness also needs a measurable primary baseline: at least one eligible exposure across
    the counted samples (C4). Requirements come from the experiment config (defaults: 2 sessions x 50 Reels).
    """
    cfg = experiment.get("config") or {}
    required_sessions = int(cfg.get("baseline_sessions") or 2)
    required_reels = int(cfg.get("reels_per_sample") or 50)
    by_session: dict[str, list[dict]] = {}
    for o in observations:
        by_session.setdefault(o["session_id"], []).append(o)
    rows = []
    for s in sorted(sessions, key=session_order_key):
        if s.get("checkpoint") != "T0":
            continue
        obs = by_session.get(s["session_id"], [])
        r = sample_readiness(obs, required_reels)
        accepted = s.get("sample_status") == "accepted"
        deviation = (s.get("deviation_note") or "").strip() or None
        scope = list(s.get("deviation_scope") or [])
        revision = sample_revision(obs)
        unchanged = bool(s.get("accepted_revision")) and s.get("accepted_revision") == revision
        covered = r["complete"] or (deviation is not None and set(r["problems"]) <= set(scope))
        counts = accepted and r["observations"] > 0 and unchanged and covered
        rows.append({"session_id": s["session_id"], "label": s.get("label"), "accepted": accepted,
                     "accepted_at": s.get("accepted_at"), "deviation_note": deviation, "deviation_scope": scope,
                     "revision": revision, "unchanged_since_acceptance": unchanged,
                     "eligible_exposures": sum(1 for o in obs if is_eligible(o)), "counts": counts, **r})
    counted_rows = [r for r in rows if r["counts"]]
    counted = len(counted_rows)
    eligible = sum(r["eligible_exposures"] for r in counted_rows)
    problems = []
    if counted < required_sessions:
        problems.append(f"{counted} of {required_sessions} required T0 baseline sessions are accepted and complete.")
    elif eligible == 0:
        problems.append("The accepted T0 samples contain no eligible recommendation exposures (only ads, followed "
                        "accounts, search results or conflicts), so the primary baseline share is undefined. "
                        "Collect or review more baseline data.")
    for r in rows:
        if r["counts"]:
            continue
        name = r["label"] or r["session_id"]
        detail = "; ".join(r["problems"]) or "complete"
        if not r["accepted"]:
            problems.append(f"T0 {name}: not accepted yet ({detail}).")
        elif r["observations"] == 0:
            problems.append(f"T0 {name}: accepted but empty.")
        elif not r["unchanged_since_acceptance"]:
            problems.append(f"T0 {name}: data changed since acceptance (or accepted before revision tracking); "
                            f"review and accept it again ({detail}).")
        else:
            problems.append(f"T0 {name}: accepted but incomplete ({detail}); the recorded deviation does not cover "
                            "this. Fix the sample or accept it again with a deviation note.")
    return {
        "ready": counted >= required_sessions and eligible > 0,
        "required_sessions": required_sessions,
        "required_reels": required_reels,
        "counted_sessions": counted,
        "eligible_exposures": eligible,
        "sessions": rows,
        "deviations": [{"session_id": r["session_id"], "note": r["deviation_note"], "problems": r["problems"]}
                       for r in counted_rows if not r["complete"]],
        "problems": problems,
    }


def _parse_dt(value: str | None) -> datetime | None:
    """Aware UTC datetime for a stored value; legacy naive values are read as UTC (R6, D-027)."""
    return parse_stored_timestamp(value)[0]


_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def session_order_key(s: dict) -> tuple:
    """Chronological order by actual instant, not by string: mixed offsets and legacy naive values sort
    correctly and never raise. Unparseable capture times sort first, then by creation time; ties keep input order."""
    return (_parse_dt(s.get("captured_at")) or _EPOCH, _parse_dt(s.get("created_at")) or _EPOCH)


def capture_time_info(s: dict) -> dict[str, Any]:
    """Capture-time provenance for one session (D-027)."""
    source = s.get("captured_at_source")
    _, assumed = parse_stored_timestamp(s.get("captured_at"))
    return {"captured_at_source": source or "not_recorded",
            "capture_time_verified": source in VERIFIED_CAPTURE_SOURCES and not assumed,
            "timezone_assumed_utc": assumed}


def unique_content_count(observations: Iterable[dict]) -> int:
    """Count distinct content items. Observations without a fingerprint each count as unique.

    ahash fingerprints are clustered by Hamming distance (near-duplicate frames);
    other fingerprints must match exactly.
    """
    seen_hashes: list[str] = []
    seen_exact: set[str] = set()
    count = 0
    for o in observations:
        fp = o.get("content_fingerprint")
        if not fp:
            count += 1
            continue
        if fp.startswith(AHASH_PREFIX):
            h = fp[len(AHASH_PREFIX):]
            if any(hamming_hex(h, s) <= AHASH_MAX_DISTANCE for s in seen_hashes):
                continue
            seen_hashes.append(h)
            count += 1
        elif fp not in seen_exact:
            seen_exact.add(fp)
            count += 1
    return count


def _share(x: int, n: int) -> float | None:
    return x / n if n else None


def sample_metrics(observations: list[dict]) -> dict[str, Any]:
    """Metrics for one sample (a session or a pooled set of sessions)."""
    n_all = len(observations)
    eligible = [o for o in observations if is_eligible(o)]
    n = len(eligible)
    counts = Counter(o.get("target_match") or "unknown" for o in eligible)
    counts_all = Counter(o.get("target_match") or "unknown" for o in observations)
    status_counts = Counter(o.get("recommendation_status") or "undetermined" for o in observations)
    n_ads = sum(1 for o in observations if o.get("is_ad"))
    n_undetermined = status_counts.get("undetermined", 0)
    n_conflicts = sum(1 for o in observations if o.get("eligibility_conflict"))
    review_counts = Counter(o.get("review_status") or "pending" for o in observations)

    direct = counts.get("direct", 0)
    ci = wilson_interval(direct, n)
    direct_all = counts_all.get("direct", 0)
    ci_all = wilson_interval(direct_all, n_all)

    first_direct = next(
        (o.get("sequence_number") for o in sorted(eligible, key=lambda o: o.get("sequence_number") or 0)
         if o.get("target_match") == "direct"),
        None,
    )
    topic_distribution = Counter((o.get("topic_label") or "(unlabelled)") for o in eligible)

    return {
        "exposures_total": n_all,
        "exposures_eligible": n,
        "unique_content_eligible": unique_content_count(eligible),
        "unique_content_total": unique_content_count(observations),
        "counts": {k: counts.get(k, 0) for k in TARGET_LABELS},
        "shares": {k: _share(counts.get(k, 0), n) for k in TARGET_LABELS},
        "direct_share": _share(direct, n),
        "direct_share_ci95": list(ci) if ci else None,
        "unknown_rate": _share(counts.get("unknown", 0), n),
        "all_exposure": {
            "counts": {k: counts_all.get(k, 0) for k in TARGET_LABELS},
            "direct_share": _share(direct_all, n_all),
            "direct_share_ci95": list(ci_all) if ci_all else None,
            "unknown_rate": _share(counts_all.get("unknown", 0), n_all),
        },
        "eligibility": {
            "recommended": status_counts.get("recommended", 0),
            "followed_account": status_counts.get("followed_account", 0),
            "search_result": status_counts.get("search_result", 0),
            "undetermined": n_undetermined,
            "identified_ads": n_ads,
            "undetermined_rate": _share(n_undetermined, n_all),
            "flag_undetermined": n_undetermined > 0,
            "conflicts": n_conflicts,
        },
        "review": {
            "pending": review_counts.get("pending", 0),
            "needs_review": review_counts.get("needs_review", 0),
            "auto_accepted": review_counts.get("auto_accepted", 0),
            "human_checked": review_counts.get("confirmed", 0) + review_counts.get("corrected", 0),
        },
        "first_direct_sequence_number": first_direct,
        "topic_distribution": dict(topic_distribution.most_common()),
    }


def _first_intervention_time(interventions: list[dict]) -> datetime | None:
    times = [
        _parse_dt(a.get("completed_at"))
        for a in interventions
        if a.get("status") in ("completed", "simulated") and a.get("completed_at")
    ]
    times = [t for t in times if t]
    return min(times) if times else None


def _obs_time(session: dict, o: dict) -> datetime | None:
    if o.get("observed_at"):
        return _parse_dt(o["observed_at"])
    base = _parse_dt(session.get("captured_at"))
    if base and o.get("video_offset_seconds") is not None:
        return base + timedelta(seconds=float(o["video_offset_seconds"]))
    return base


def experiment_summary(
    experiment: dict,
    sessions: list[dict],
    observations: list[dict],
    interventions: list[dict],
) -> dict[str, Any]:
    """Experiment-level evaluation: baseline vs latest, trend, time-to-first, persistence."""
    by_session: dict[str, list[dict]] = {}
    for o in observations:
        by_session.setdefault(o["session_id"], []).append(o)

    ordered = sorted(sessions, key=session_order_key)
    anchor = _first_intervention_time(interventions)
    per_session = []
    for s in ordered:
        m = sample_metrics(by_session.get(s["session_id"], []))
        s_time = _parse_dt(s.get("captured_at"))
        elapsed = round((s_time - anchor).total_seconds() / 3600, 2) if (anchor and s_time) else None
        per_session.append({"session_id": s["session_id"], "checkpoint": s["checkpoint"], "label": s.get("label"),
                            "captured_at": s.get("captured_at"), **capture_time_info(s),
                            "hours_after_intervention": elapsed, "metrics": m})

    baseline_obs = [o for s in ordered if s["checkpoint"] == "T0" for o in by_session.get(s["session_id"], [])]
    baseline = sample_metrics(baseline_obs) if baseline_obs else None
    b_n = baseline["exposures_eligible"] if baseline else 0
    b_x = baseline["counts"]["direct"] if baseline else 0
    b_share = baseline["direct_share"] if baseline else None

    def change(m: dict) -> dict[str, Any]:
        if b_share is None or m["direct_share"] is None:
            return {"change_pp": None, "change_pp_ci95": None}
        ci = newcombe_diff_interval(m["counts"]["direct"], m["exposures_eligible"], b_x, b_n)
        return {
            "change_pp": round((m["direct_share"] - b_share) * 100, 2),
            "change_pp_ci95": [round(ci[0] * 100, 2), round(ci[1] * 100, 2)] if ci else None,
        }

    for row in per_session:
        row["vs_baseline"] = change(row["metrics"])

    post = [r for r in per_session if r["checkpoint"] not in ("T0",) and r["metrics"]["exposures_eligible"] > 0]
    latest = post[-1] if post else None

    # Time to first unsolicited target recommendation (post-intervention, eligible only).
    ttf: dict[str, Any] = {"measurable": False, "reason": None}
    if anchor is None:
        ttf["reason"] = "No completed intervention recorded yet."
    else:
        session_index = {s["session_id"]: s for s in ordered}
        exposures_before = 0
        found = None
        for s in ordered:
            s_time = _parse_dt(s.get("captured_at"))
            if s["checkpoint"] == "T0" or (s_time and s_time < anchor):
                continue
            for o in sorted(by_session.get(s["session_id"], []), key=lambda o: o.get("sequence_number") or 0):
                if not is_eligible(o):
                    continue
                if o.get("target_match") == "direct":
                    found = (s, o)
                    break
                exposures_before += 1
            if found:
                break
        if found:
            s, o = found
            t = _obs_time(session_index[s["session_id"]], o)
            ttf = {
                "measurable": True,
                "intervention_completed_at": anchor.isoformat(),
                "session_id": s["session_id"],
                "checkpoint": s["checkpoint"],
                "sequence_number": o.get("sequence_number"),
                "eligible_exposures_before_first": exposures_before,
                "hours_after_intervention": round((t - anchor).total_seconds() / 3600, 2) if t else None,
                "note": "Wall-clock time is bounded by when samples were taken; the first target item may "
                        "have appeared earlier between sessions.",
            }
        else:
            ttf["reason"] = "No eligible direct target recommendation observed after the intervention yet."

    # Persistence relative to the immediate post-intervention lift (T2).
    by_cp: dict[str, dict] = {}
    for r in per_session:
        if r["checkpoint"] in ("T2", "T3", "T4", "T5"):
            by_cp[r["checkpoint"]] = r  # latest session per checkpoint wins
    t2 = by_cp.get("T2")
    t2_lift = (t2["metrics"]["direct_share"] - b_share) if (t2 and b_share is not None and t2["metrics"]["direct_share"] is not None) else None
    persistence = []
    # The checkpoint name is a plan, not evidence (R6): report the actual elapsed time and its provenance.
    for cp, horizon in (("T3", "24h"), ("T4", "72h"), ("T5", "7d")):
        r = by_cp.get(cp)
        nominal = CHECKPOINT_OFFSETS_HOURS[cp]
        if not r or r["metrics"]["direct_share"] is None:
            persistence.append({"checkpoint": cp, "horizon": horizon, "nominal_hours": nominal, "measured": False})
            continue
        lift = (r["metrics"]["direct_share"] - b_share) if b_share is not None else None
        retention = (lift / t2_lift) if (lift is not None and t2_lift and t2_lift > 0) else None
        actual = r["hours_after_intervention"]
        persistence.append({
            "checkpoint": cp, "horizon": horizon, "nominal_hours": nominal, "measured": True,
            "session_id": r["session_id"],
            "actual_hours_after_intervention": actual,
            "hours_from_nominal": round(actual - nominal, 2) if actual is not None else None,
            "captured_before_intervention": actual is not None and actual < 0,
            "capture_time_verified": r["capture_time_verified"],
            "captured_at_source": r["captured_at_source"],
            "direct_share": r["metrics"]["direct_share"],
            "change_pp": r["vs_baseline"]["change_pp"],
            "retention_of_T2_lift": round(retention, 3) if retention is not None else None,
        })

    readiness = baseline_readiness(experiment, sessions, observations)
    target_share = experiment.get("target_share")
    latest_share = latest["metrics"]["direct_share"] if latest else None
    warnings = []
    if baseline is None:
        warnings.append("No T0 baseline sessions yet.")
    if not readiness["ready"]:
        warnings.append("Baseline not ready for an intervention: " + " ".join(readiness["problems"]))
    for d in readiness["deviations"]:
        warnings.append(f"Protocol deviation accepted for T0 {d['session_id']}: {d['note']}")
    assumed = [r["session_id"] for r in per_session if r["timezone_assumed_utc"]]
    assumed += [a.get("action_id") or "intervention" for a in interventions
                if parse_stored_timestamp(a.get("completed_at"))[1]]
    if assumed:
        warnings.append(f"{len(assumed)} stored timestamps have no timezone (legacy input) and were read as UTC: "
                        + ", ".join(assumed) + ".")
    for r in per_session:
        if r["checkpoint"] in ("T2", "T3", "T4", "T5"):
            if r["hours_after_intervention"] is None:
                warnings.append(f"{r['checkpoint']} {r['session_id']}: elapsed time since the intervention is unknown "
                                "(no completed intervention time or no parseable capture time).")
            elif r["hours_after_intervention"] < 0:
                warnings.append(f"{r['checkpoint']} {r['session_id']}: captured {-r['hours_after_intervention']:.1f} h "
                                "before the first completed intervention.")
            if not r["capture_time_verified"]:
                warnings.append(f"{r['checkpoint']} {r['session_id']}: capture time comes from "
                                f"'{r['captured_at_source']}', not from the owner or recording metadata; the "
                                "elapsed time since the intervention is not verified.")
    for r in per_session:
        m = r["metrics"]
        if m["eligibility"]["flag_undetermined"]:
            warnings.append(f"{r['checkpoint']} {r['session_id']}: {m['eligibility']['undetermined']} exposures have "
                            "undetermined eligibility and are excluded from the primary metric (see all-exposure metric).")
        if m["eligibility"]["conflicts"]:
            warnings.append(f"{r['checkpoint']} {r['session_id']}: {m['eligibility']['conflicts']} exposures have "
                            "conflicting eligibility evidence (e.g. followed-account marker on a 'recommended' row) "
                            "and are excluded from the primary metric until reviewed.")
        if m["unknown_rate"] and m["unknown_rate"] > 0.2:
            warnings.append(f"{r['checkpoint']} {r['session_id']}: unknown classification rate "
                            f"{m['unknown_rate']:.0%} is high; review observations.")

    return {
        "metric_version": METRIC_VERSION,
        "experiment_id": experiment["experiment_id"],
        "is_demo": bool(experiment.get("is_demo")),
        "target_topic": experiment.get("target_topic"),
        "target_share": target_share,
        "baseline": baseline,
        "baseline_session_count": sum(1 for s in ordered if s["checkpoint"] == "T0"),
        "baseline_readiness": readiness,
        "latest": {"session_id": latest["session_id"], "checkpoint": latest["checkpoint"],
                   "metrics": latest["metrics"], "vs_baseline": latest["vs_baseline"]} if latest else None,
        "target_reached": (latest_share >= target_share) if (latest_share is not None and target_share) else None,
        "trend": [
            {"session_id": r["session_id"], "checkpoint": r["checkpoint"], "captured_at": r["captured_at"],
             "hours_after_intervention": r["hours_after_intervention"],
             "capture_time_verified": r["capture_time_verified"],
             "direct_share": r["metrics"]["direct_share"], "direct_share_ci95": r["metrics"]["direct_share_ci95"],
             "shares": r["metrics"]["shares"], "exposures_eligible": r["metrics"]["exposures_eligible"],
             "exposures_total": r["metrics"]["exposures_total"], "change_pp": r["vs_baseline"]["change_pp"]}
            for r in per_session
        ],
        "sessions": per_session,
        "time_to_first_target": ttf,
        "persistence": persistence,
        "warnings": warnings,
        "caveats": CAVEATS,
    }
