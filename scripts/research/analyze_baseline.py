"""Provisional, on-device-only analysis of BASELINE-001; not a production detector.

Input: import_baseline.py manifest + local_vision.swift JSONL at 2 fps / 1128 px.
Creator-overlay geometry is specific to this cropped recording. All evidence,
recording-derived identifiers, labels, and exports remain in ignored data/.
Run: .venv/bin/python -m scripts.research.analyze_baseline
"""
import collections
import difflib
import hashlib
import html
import json
import platform
import re
from datetime import datetime, timedelta
from pathlib import Path

from app.evaluator.metrics import sample_metrics
from app.observer.media import extract_thumbnails, sha256_file
from app.observer.segmentation import ahash
from app.services import compute_summary, export_csv, export_json
from app.storage.db import Database
from app.storage.repository import Repository

ROOT = Path("data/research/BASELINE-001")
VERSION = "local-vision-evidence-v1-provisional"


def save(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False))


def normalize(text):
    return re.sub(r"[^a-zа-я0-9_.]", "", re.split(r"\bfollow\b", text.lower())[0])


def write_review_page(evidence):
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">',
             '<title>BASELINE-001 local review</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:20px;background:#111;color:#eee}article{border-top:1px solid #666;padding:20px 0}img{max-width:32%;height:auto}small{color:#ccc}a{color:#aaf}</style>',
             '<h1>BASELINE-001 · T0 · PROVISIONAL</h1><p>On-device evidence only. Candidate intervals and labels require human review. All images are local files; no scripts, external fonts or network resources.</p>',
             '<p>Review boundaries, topics, ads and follow status in AMAS before accepting this baseline. Generic people/clothing/outdoor labels are insufficient topic evidence. Sampling is 2 fps; timing uncertainty includes sampling and scroll transitions. The original is preserved.</p>']
    for r in evidence:
        parts.append(f'<article><h2>E{r["sequence_number"]:03d} · {r["start"]:.2f}–{r["end"]:.2f}s · {html.escape(r["taxonomy_match"].upper())}</h2>')
        parts.append('<p>'+html.escape(' '.join(r['classification_evidence']))+'</p>')
        parts.append(f'<small>Follow-marker frames: {r["follow_ocr_frames"]}; ad-marker frames: {r["ad_ocr_frames"]}. Boundary brackets: {r["boundary_before_bracket"]} → {r["boundary_after_bracket"]}. Duplicate state: unverified.</small><p>')
        for index in dict.fromkeys([r['stable_indices'][0], r['representative_index'], r['stable_indices'][-1]]):
            file = f'frames-2fps/frame_{index+1:05d}.jpg'
            parts.append(f'<a href="{file}"><img loading="lazy" src="{file}" alt="Local frame at {index/2:.1f} seconds" title="{index/2:.1f}s"></a> ')
        parts.append('</p></article>')
    parts.append('</html>')
    (ROOT / 'review.html').write_text('\n'.join(parts))


def classify(rows):
    # Broad tags such as people, clothing, outdoor, or document do not identify a topic.
    hits = collections.Counter(v["label"] for row in rows for v in row["labels"] if v["confidence"] >= .65)
    cues = []
    topic = None
    if hits["skateboarding"] >= 2:
        topic, cues = "skateboarding", ["skateboarding"]
    elif hits["food"] >= 2 and max(hits["tableware"], hits["plate"], hits["bowl"] ) >= 2:
        topic, cues = "food", ["food", "tableware/plate/bowl"]
    elif hits["pot_cooking"] >= 2 and hits["stove"] >= 2:
        topic, cues = "cooking", ["pot_cooking", "stove"]
    # These are suggestions; absence of a keyword is never evidence of UNRELATED.
    text = " ".join(v["text"].lower() for row in rows for v in row["ocr"] if v["confidence"] >= .8)
    direct = bool(re.search(r"\bbiathlon\b|\bbiathlete\b|биатлон", text))
    adjacent = bool(re.search(r"\bcross[- ]country skiing\b|\bwinter sports\b|\bsnowboard(?:ing)?\b|лыжные гонки", text))
    if direct or adjacent:
        # A keyword can occur in a handle, overlay or unrelated context. Require review.
        return "unknown", None, ["Explicit topic keyword candidate requires contextual review."], dict(hits)
    if topic:
        return "unrelated", topic, ["On-device Vision: repeated content cues " + ", ".join(cues) + " (score >=0.65 in >=2 sampled frames); provisional, not human-confirmed."], dict(hits)
    return "unknown", None, ["On-device evidence does not reliably identify the topic. No image was inspected by a remote model or human reviewer in this analysis."], dict(hits)


def main():
    if (ROOT / "analysis.json").exists():
        raise SystemExit("Analysis already exists; preserve reviewed observations and inspect before rerunning.")
    manifest = json.loads((ROOT / "manifest.json").read_text())
    rows = [json.loads(x) for x in (ROOT / "local-vision.jsonl").read_text().splitlines()]
    assert len(rows) == 423 and not any("error" in r for r in rows), "Incomplete local Vision evidence"
    canons, runs = [], []
    for r in rows:
        candidates = [x for x in r["ocr"] if .09 < x["box"][0] < .13 and .05 < x["box"][1] < .23 and x["confidence"] >= .5]
        candidate = max(candidates, key=lambda x: x["box"][1]) if candidates else None
        key = normalize(candidate["text"]) if candidate else ""
        alias = None
        if key:
            match = next((i for i, s in enumerate(canons) if difflib.SequenceMatcher(None, key, s).ratio() >= .75), None)
            if match is None:
                canons.append(key)
                match = len(canons) - 1
            alias = match
        if runs and runs[-1]["alias"] == alias:
            runs[-1]["indices"].append(r["index"])
        else:
            runs.append(dict(alias=alias, indices=[r["index"]]))
    stable = []
    for run in runs:
        if run["alias"] is None or len(run["indices"]) < 2:
            continue
        if stable and stable[-1]["alias"] == run["alias"]:
            stable[-1]["indices"] += run["indices"]
        else:
            stable.append(dict(alias=run["alias"], indices=run["indices"].copy()))
    # Midpoint between last stable old anchor and first stable new anchor.
    brackets = [[a["indices"][-1]/2, b["indices"][0]/2] for a, b in zip(stable, stable[1:])]
    boundaries = [0.0] + [sum(pair)/2 for pair in brackets] + [manifest["recording_duration_seconds"]]
    repo = Repository(Database(Path("data/amas.sqlite")), Path("data"))
    sid = manifest["session_id"]
    original = repo.list_observations(session_id=sid)
    assert len(original) == manifest["stock_candidate_count"] and all(o["review_status"] == "pending" for o in original), "Refusing to replace reviewed state"
    save("stock-frames.json", repo.list_frames(sid))
    session = repo.get_session(sid)
    thumbs = extract_thumbnails(Path(session["recording_ref"]), 2.0, .4)
    assert len(thumbs) == len(rows)
    frame_data = [dict(frame_index=i, offset_seconds=i/2,
                       path=str(ROOT / "frames-2fps" / r["file"]), ahash=ahash(thumbs[i])) for i, r in enumerate(rows)]
    repo.add_frames(sid, frame_data)
    frames = repo.list_frames(sid)
    capture = datetime.fromisoformat(manifest["captured_at"].replace("Z", "+00:00"))
    observations, evidence = [], []
    for i, run in enumerate(stable):
        samples = [rows[k] for k in run["indices"]]
        match, topic, cues, tags = classify(samples)
        rep_index = run["indices"][len(run["indices"])//2]
        follow_frames = sum(any(re.search(r"\bfollow\b", x["text"], re.I) and x["box"][1] < .25 for x in r["ocr"]) for r in samples)
        ad_frames = sum(any(re.search(r"\b(?:sponsored|paid partnership)\b|реклама", x["text"], re.I) for x in r["ocr"]) for r in samples)
        # User identifies this recording as the Reels feed. Visible Follow corroborates non-followed origin.
        status = "recommended" if follow_frames >= 2 else "undetermined"
        detail = dict(sequence_number=i+1, start=boundaries[i], end=boundaries[i+1],
            stable_indices=run["indices"], representative_index=rep_index,
            creator_anchor_sha256=hashlib.sha256(canons[run["alias"]].encode()).hexdigest(),
            boundary_before_bracket=brackets[i-1] if i else [0,0],
            boundary_after_bracket=brackets[i] if i < len(stable)-1 else [boundaries[-1],boundaries[-1]],
            edge_censored=i in (0, len(stable)-1), boundary_review="provisional; no human review",
            follow_ocr_frames=follow_frames, ad_ocr_frames=ad_frames,
            ad_state="identified_ad" if ad_frames else "unknown; no ad marker detected, absence is not proof",
            eligibility_evidence="Founder-reported Reels surface plus repeated Follow OCR" if status == "recommended" else "Follow state not established",
            visual_tag_frame_counts=tags, taxonomy_match=match, classification_evidence=cues,
            confidence_semantics="Uncalibrated local model; classification confidence null for suggested labels, zero for UNKNOWN",
            duplicate_state="unverified; aHash candidates are not established content identities")
        evidence.append(detail)
        observations.append(dict(observation_id=f"BASELINE-001-E{i+1:03d}",
            observed_at=(capture+timedelta(seconds=boundaries[i])).isoformat(),
            video_offset_seconds=boundaries[i], segment_end_seconds=boundaries[i+1],
            frame_count=sum(boundaries[i] <= f["offset_seconds"] < boundaries[i+1] for f in frames),
            representative_frame_id=frames[rep_index]["frame_id"], content_fingerprint="ahash:"+frames[rep_index]["ahash"],
            target_match=match, topic_label=topic, confidence=0.0 if match == "unknown" else None,
            classification_evidence=cues+[f"Local evidence: data/research/BASELINE-001/evidence.json, row {i+1}; representative t={rep_index/2:.1f}s"],
            recommendation_status=status, is_ad=True if ad_frames else None,
            classifier_version=VERSION, review_status="needs_review", segmentation_method="ocr-anchor-v1-provisional",
            machine_label_json=dict(target_match=match, topic_label=topic, confidence=None,
                classifier_version=VERSION, profile_version=1, evidence=cues),
            notes=json.dumps(detail)))
    repo.replace_observations(sid, observations)
    repo.update_session(sid, dict(status="needs_review", segmentation_json=dict(method="ocr-anchor-v1-provisional", fps=2,
        frames=len(frames), frame_width=1128, creator_roi=[.09,.05,.13,.23], anchor_similarity=.75,
        minimum_stable_samples=2, boundaries=boundaries, boundary_brackets=brackets,
        source_stock_candidate_count=len(original), human_verified=False)))
    save("evidence.json", evidence)
    save("anchor-runs.json", {"runs":runs, "discarded_singletons":[r for r in runs if r["alias"] is not None and len(r["indices"])==1]})
    summary = compute_summary(repo, "EXP-001", store=True)
    metrics = sample_metrics(repo.list_observations(session_id=sid))
    n, direct, unknown = metrics["exposures_eligible"], metrics["counts"]["direct"], metrics["counts"]["unknown"]
    # No primary exposures are removed on aHash similarity; report candidate pairs separately.
    pairs = []
    for i, a in enumerate(observations):
        for j, b in enumerate(observations[i+1:], i+1):
            distance = (int(a["content_fingerprint"][6:],16)^int(b["content_fingerprint"][6:],16)).bit_count()
            if distance <= 6:
                pairs.append({"exposures":[i+1,j+1],"ahash_distance":distance,"status":"candidate_only"})
    source = Path(manifest["source_path"])
    assert sha256_file(source) == manifest["source_sha256"]
    assert source.stat().st_mtime_ns == manifest["source_mtime_ns"]
    report = dict(recording_id="BASELINE-001", is_demo=False, result_status="PROVISIONAL — NOT AN ACCEPTED BASELINE",
        metrics=metrics, classification_unknown_bounds=[direct/n,(direct+unknown)/n] if n else None,
        bounds_note="Conditional on proposed boundaries and provisional eligibility; not a confidence interval. Does not cover classifier error or unknown ad status.",
        unknown_ad_status_count=sum(o["is_ad"] is None for o in observations),
        verified_non_ad_sensitivity=sample_metrics([o for o in observations if o["is_ad"] is False]),
        duplicate_candidates=pairs, duplicate_exposure_policy="Count every exposure; do not deduplicate the primary denominator.",
        original_unchanged_verified=True, privacy="All images processed on-device; no external image classification",
        environment=dict(macos=platform.mac_ver()[0], python=platform.python_version()),
        evidence_sha256=sha256_file(ROOT / "local-vision.jsonl"),
        acceptance_gaps=["27 provisional exposure intervals require on-device human boundary review",
                         "Topic labels are uncalibrated suggestions; all rows need review",
                         "One exposure has undetermined follow status and an OCR-detected ad marker; remaining ad states are unknown",
                         "Only one T0 session, fewer than protocol's 50 exposures; second T0 absent",
                         "No intervention or post-intervention evidence exists; feasibility remains untested"],
        source_stock_candidate_count=len(original), stable_creator_runs=len(stable))
    save("analysis.json", report)
    write_review_page(evidence)
    save("amas-export.json", export_json(repo, "EXP-001"))
    (ROOT / "observations.csv").write_text(export_csv(repo, "EXP-001"))
    repo.db.close()
    print(json.dumps({k:report[k] for k in ("result_status","stable_creator_runs","source_stock_candidate_count","classification_unknown_bounds","unknown_ad_status_count","duplicate_candidates")}, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
