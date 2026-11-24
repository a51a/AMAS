import math

from app.evaluator.metrics import experiment_summary, is_eligible, sample_metrics, unique_content_count
from app.evaluator.stats import newcombe_diff_interval, wilson_interval


def obs(tm, status="recommended", ad=None, seq=1, session="s1", fp=None, offset=None):
    return {"session_id": session, "target_match": tm, "recommendation_status": status, "is_ad": ad,
            "sequence_number": seq, "content_fingerprint": fp, "topic_label": tm, "review_status": "confirmed",
            "video_offset_seconds": offset}


def test_wilson_known_values():
    lo, hi = wilson_interval(10, 50)
    assert math.isclose(lo, 0.1124, abs_tol=1e-3) and math.isclose(hi, 0.3304, abs_tol=1e-3)
    assert wilson_interval(0, 0) is None
    lo0, hi0 = wilson_interval(0, 50)
    assert lo0 == 0.0 and 0.06 < hi0 < 0.08


def test_newcombe_contains_point_estimate():
    lo, hi = newcombe_diff_interval(10, 50, 1, 100)
    assert lo < 0.19 < hi and lo > 0


def test_eligibility_rules():
    assert is_eligible(obs("direct"))
    assert not is_eligible(obs("direct", ad=True))
    assert not is_eligible(obs("direct", status="followed_account"))
    assert not is_eligible(obs("direct", status="search_result"))
    assert not is_eligible(obs("direct", status="undetermined"))


def test_primary_metric_keeps_unknown_in_denominator_and_excludes_ineligible():
    rows = [obs("direct", seq=1), obs("unknown", seq=2), obs("unrelated", seq=3), obs("adjacent", seq=4),
            obs("direct", ad=True, seq=5), obs("direct", status="followed_account", seq=6),
            obs("direct", status="search_result", seq=7), obs("direct", status="undetermined", seq=8)]
    m = sample_metrics(rows)
    assert m["exposures_total"] == 8
    assert m["exposures_eligible"] == 4
    assert m["counts"]["direct"] == 1
    assert m["direct_share"] == 0.25
    assert m["unknown_rate"] == 0.25
    assert m["shares"]["adjacent"] == 0.25
    assert m["eligibility"]["undetermined"] == 1 and m["eligibility"]["flag_undetermined"]
    assert m["eligibility"]["identified_ads"] == 1
    # all-exposure metric includes everything
    assert m["all_exposure"]["direct_share"] == 5 / 8
    assert m["first_direct_sequence_number"] == 1


def test_empty_sample():
    m = sample_metrics([])
    assert m["direct_share"] is None and m["direct_share_ci95"] is None and m["exposures_total"] == 0


def test_unique_content_counts_near_duplicates_once():
    rows = [obs("direct", fp="ahash:ffff0000ffff0000"), obs("direct", fp="ahash:ffff0000ffff0001"),
            obs("direct", fp="ahash:0000ffff0000ffff"), obs("direct", fp="manual:a"), obs("direct", fp="manual:a"),
            obs("direct", fp=None)]
    assert unique_content_count(rows) == 4


def _session(sid, cp, when):
    return {"session_id": sid, "checkpoint": cp, "captured_at": when, "label": cp}


def test_experiment_summary_baseline_change_ttf_persistence():
    exp = {"experiment_id": "X", "target_topic": "biathlon", "target_share": 0.2, "is_demo": True}
    sessions = [_session("a", "T0", "2026-01-01T10:00:00+00:00"), _session("b", "T0", "2026-01-01T20:00:00+00:00"),
                _session("c", "T2", "2026-01-02T10:00:00+00:00"), _session("d", "T3", "2026-01-03T10:00:00+00:00")]
    rows = []
    rows += [obs("unrelated", seq=i, session="a") for i in range(1, 51)]
    rows += [obs("direct", seq=1, session="b")] + [obs("unrelated", seq=i, session="b") for i in range(2, 51)]
    rows += [obs("unrelated", seq=i, session="c", offset=i * 10.0) for i in range(1, 4)]
    rows += [obs("direct", seq=i, session="c", offset=i * 10.0) for i in range(4, 14)]
    rows += [obs("unrelated", seq=i, session="c") for i in range(14, 51)]
    rows += [obs("direct", seq=i, session="d") for i in range(1, 6)] + [obs("unrelated", seq=i, session="d") for i in range(6, 51)]
    acts = [{"status": "completed", "completed_at": "2026-01-02T09:00:00+00:00"}]
    s = experiment_summary(exp, sessions, rows, acts)
    assert s["baseline"]["exposures_eligible"] == 100
    assert s["baseline"]["direct_share"] == 0.01
    assert s["latest"]["checkpoint"] == "T3"
    assert s["latest"]["vs_baseline"]["change_pp"] == 9.0
    t2 = next(r for r in s["sessions"] if r["checkpoint"] == "T2")
    assert t2["vs_baseline"]["change_pp"] == 19.0
    ttf = s["time_to_first_target"]
    assert ttf["measurable"] and ttf["checkpoint"] == "T2" and ttf["sequence_number"] == 4
    assert ttf["eligible_exposures_before_first"] == 3
    assert ttf["hours_after_intervention"] == round((3600 + 40) / 3600, 2)
    p = {x["checkpoint"]: x for x in s["persistence"]}
    assert p["T3"]["measured"] and math.isclose(p["T3"]["retention_of_T2_lift"], 9 / 19, abs_tol=1e-3)
    assert not p["T4"]["measured"]
    assert s["target_reached"] is False


def test_summary_without_baseline_warns():
    exp = {"experiment_id": "X", "target_topic": "biathlon", "target_share": 0.2}
    s = experiment_summary(exp, [], [], [])
    assert s["baseline"] is None and "No T0 baseline sessions yet." in s["warnings"]
    assert s["time_to_first_target"]["measurable"] is False
