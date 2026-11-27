"""Observer pipeline: import recording -> extract frames -> segment into Reels -> classify.

Every step writes raw data (frames, segment observations) that the user can
review and correct in the UI. Nothing here contacts Instagram.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.config import Settings
from app.models.schemas import (PATCH_NULLABLE_FIELDS, CaptureTimeSource, RecommendationStatus, ReviewStatus,
                                TargetMatch, normalize_timestamp, utcnow)
from app.observer import media
from app.observer.classifiers.base import ClassificationInput, Classifier
from app.observer.classifiers.mock import MockClassifier
from app.observer.classifiers.ocr import ocr_available, ocr_image
from app.observer.segmentation import ahash, boundaries_from_offsets, segment, segments_from_boundaries
from app.storage.repository import Repository

ALLOWED_SUFFIXES = {".mp4", ".mov", ".m4v"}


class PrivacyGateError(PermissionError):
    pass


PRIVACY_NOTICE = (
    "External classification sends extracted video frames (images from your screen recording) to a third-party "
    "model provider over the internet. Frames may show other people's content, usernames and anything else that "
    "was on screen. The provider processes them under its own terms and retention policy. AMAS never sends your "
    "recording file, passwords, cookies or tokens. You can keep using the local mock/manual classifier instead."
)


def assert_external_allowed(settings: Settings, experiment: dict) -> None:
    if not settings.allow_external_providers:
        raise PrivacyGateError("External providers are disabled (set AMAS_ALLOW_EXTERNAL_PROVIDERS=true in .env).")
    if not experiment.get("external_provider_consent"):
        raise PrivacyGateError("Accept the privacy notice for this experiment before sending frames to a provider.")


def get_classifier(name: str, settings: Settings) -> Classifier:
    if name == "mock":
        return MockClassifier()
    if name == "anthropic":
        from app.observer.classifiers.vision_llm import AnthropicVisionProvider, VisionLLMClassifier

        return VisionLLMClassifier(AnthropicVisionProvider(settings.anthropic_model),
                                   max_frames=settings.llm_max_frames_per_reel)
    raise ValueError(f"Unknown classifier '{name}'. Use 'mock' or 'anthropic'.")


# ---------------------------------------------------------------- import

def resolve_capture_time(session: dict, recording_created_at: str | None,
                         captured_at: str | None = None) -> dict:
    """Decide a session's capture time at import (R6, D-027). Import time is never capture time.

    Precedence: an explicit `captured_at` from the owner, then a capture time the owner entered earlier,
    then the recording's container creation time, then the existing fallback (session creation time), which
    stays flagged as unverified. Legacy rows without a recorded source keep their value; only an explicit
    `captured_at` replaces it (the recording metadata is still stored in `recording_created_at`).
    """
    explicit = normalize_timestamp(captured_at, field="captured_at")
    if explicit:
        return {"captured_at": explicit, "captured_at_source": CaptureTimeSource.USER.value}
    current = session.get("captured_at_source")
    if current is None or current == CaptureTimeSource.USER.value:
        return {}  # owner-entered, or a legacy row (pre-v4) whose origin is unknown: never rewritten silently
    if recording_created_at:
        return {"captured_at": recording_created_at, "captured_at_source": CaptureTimeSource.RECORDING_METADATA.value}
    if current == CaptureTimeSource.RECORDING_METADATA.value:
        # A replacement recording without metadata must not inherit the previous file's capture time.
        return {"captured_at": session.get("created_at") or utcnow(),
                "captured_at_source": CaptureTimeSource.SESSION_CREATED.value}
    return {}


def import_recording(repo: Repository, settings: Settings, session_id: str, source: Path,
                     *, original_name: str | None = None, move: bool = False,
                     captured_at: str | None = None) -> dict:
    """Copy a user-made screen recording into local storage, extract frames and auto-segment it.

    `captured_at` (timezone-aware) overrides the recording metadata; see `resolve_capture_time`.
    """
    source = Path(source)
    explicit = normalize_timestamp(captured_at, field="captured_at")  # reject bad input before copying
    suffix = Path(original_name or source.name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"Unsupported file type '{suffix}'. Use MP4 or MOV.")
    info = media.probe(source)
    sdir = repo.session_dir(session_id)
    sdir.mkdir(parents=True, exist_ok=True)
    dest = sdir / f"recording{suffix}"
    if source.resolve() != dest.resolve():
        (shutil.move if move else shutil.copy2)(str(source), str(dest))
    digest = media.sha256_file(dest)
    created = (info.get("creation_time") or {}).get("value")
    repo.update_session(session_id, {
        "recording_ref": str(dest),
        "recording_sha256": digest,
        "recording_duration_seconds": info["duration_seconds"],
        "recording_created_at": created,
        "imported_at": utcnow(),
        **resolve_capture_time(repo.get_session(session_id), created, explicit),
        "status": "imported",
    })
    extract_and_segment(repo, settings, session_id)
    return repo.get_session(session_id)


def extract_and_segment(repo: Repository, settings: Settings, session_id: str) -> dict:
    s = repo.get_session(session_id)
    rec = Path(s["recording_ref"])
    fps = settings.frame_fps
    frame_paths = media.extract_frames(rec, repo.session_dir(session_id) / "frames", fps, settings.frame_width)
    thumbs = media.extract_thumbnails(rec, fps, settings.segment_crop_width)
    n = min(len(frame_paths), len(thumbs))
    frame_paths, thumbs = frame_paths[:n], thumbs[:n]
    result = segment(thumbs, fps, abs_threshold=settings.segment_diff_threshold,
                     min_segment_seconds=settings.segment_min_seconds)
    repo.add_frames(session_id, [
        {"frame_index": i, "offset_seconds": round(i / fps, 3), "path": str(p),
         "diff_score": round(result.diffs[i], 3), "ahash": ahash(thumbs[i])}
        for i, p in enumerate(frame_paths)
    ])
    repo.update_session(session_id, {"segmentation_json": {**result.params, "frames": n}})
    _write_segments(repo, session_id, result.segments, method="auto")
    return repo.update_session(session_id, {"status": "segmented"})


BOUNDARY_TOLERANCE = 1e-3


def _same(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= BOUNDARY_TOLERANCE


def _label_summary(o: dict) -> str:
    return (f"{o['observation_id']} [{o['video_offset_seconds']:.2f}-{(o.get('segment_end_seconds') or 0):.2f}s] "
            f"{o.get('target_match')}/{o.get('recommendation_status')}/{o.get('review_status')}")


_LABEL_FIELDS = ("observation_id", "target_match", "topic_label", "recommendation_status", "is_ad",
                 "review_status", "classifier_version", "eligibility_source", "eligibility_conflict")


# Evidence written by boundary edits, human review or eligibility checks is provenance, not machine output:
# a new classification keeps it (C3, D-024). The structured record lives in boundary_history.
PRESERVED_EVIDENCE_PREFIXES = ("Boundaries changed", "Corrected by human reviewer", "Eligibility conflict")


def _preserved_evidence(o: dict) -> list[str]:
    return [e for e in (o.get("classification_evidence") or []) if e.startswith(PRESERVED_EVIDENCE_PREFIXES)]


def _label_record(o: dict) -> dict:
    return {k: o.get(k) for k in _LABEL_FIELDS}


def _write_segments(repo: Repository, session_id: str, segments, method: str) -> list[dict]:
    """Reconcile new segment boundaries with existing observations (R1, D-018).

    - Same start and end: the observation keeps its ID, labels, eligibility, ad state, review status and
      provenance; only frame-derived fields are refreshed.
    - Same start, different end (merge or split of this Reel): keeps its ID and labels as evidence but is
      sent back to review (`needs_review`).
    - Anything else is a new, pending observation. Old rows that no longer start a segment are removed.
    Everything is applied in one transaction.
    """
    frames = repo.list_frames(session_id)
    existing = repo.list_observations(session_id=session_id)
    timed = [o for o in existing if o.get("video_offset_seconds") is not None]
    untimed = [o for o in existing if o.get("video_offset_seconds") is None]
    used: set[str] = set()
    plan: list[tuple[str, dict]] = []
    for seg in segments:
        rep = frames[seg.representative_index]
        start, end = round(seg.start_seconds, 3), round(seg.end_seconds, 3)
        frame_values = {
            "frame_count": len(seg.frame_indices),
            "representative_frame_id": rep["frame_id"],
            "content_fingerprint": f"ahash:{rep['ahash']}" if rep.get("ahash") else None,
        }
        match = next((o for o in timed if o["observation_id"] not in used
                      and _same(o["video_offset_seconds"], start)), None)
        if match is None:
            plan.append(("new", {
                "video_offset_seconds": start,
                "segment_end_seconds": end,
                **frame_values,
                "target_match": TargetMatch.UNKNOWN.value,
                "recommendation_status": RecommendationStatus.UNDETERMINED.value,
                "review_status": ReviewStatus.PENDING.value,
                "segmentation_method": method,
            }))
            continue
        used.add(match["observation_id"])
        if _same(match.get("segment_end_seconds"), end):
            plan.append(("keep", {"observation_id": match["observation_id"], **frame_values}))
            continue
        absorbed = [o for o in timed if o["observation_id"] != match["observation_id"]
                    and start - BOUNDARY_TOLERANCE <= o["video_offset_seconds"] < end - BOUNDARY_TOLERANCE]
        note = (f"Boundaries changed ({method}) from {match['video_offset_seconds']:.2f}-"
                f"{(match.get('segment_end_seconds') or 0):.2f}s to {start:.2f}-{end:.2f}s; re-review required.")
        if absorbed:
            note += " Absorbed: " + "; ".join(_label_summary(o) for o in absorbed) + "."
        # Durable audit trail, kept apart from replaceable machine evidence (C3, D-024).
        entry = {"at": utcnow(), "method": method,
                 "old": [match["video_offset_seconds"], match.get("segment_end_seconds")], "new": [start, end],
                 "previous_labels": _label_record(match),
                 "absorbed": [{**_label_record(o), "interval": [o["video_offset_seconds"], o.get("segment_end_seconds")],
                               "boundary_history": o.get("boundary_history") or []} for o in absorbed]}
        values = {"observation_id": match["observation_id"], "segment_end_seconds": end, **frame_values,
                  "segmentation_method": method,
                  "boundary_history": (match.get("boundary_history") or []) + [entry],
                  "classification_evidence": (match.get("classification_evidence") or []) + [note]}
        if match["review_status"] != ReviewStatus.PENDING.value:
            values["review_status"] = ReviewStatus.NEEDS_REVIEW.value
        plan.append(("update", values))
    plan += [("keep", {"observation_id": o["observation_id"]}) for o in untimed]
    delete_ids = [o["observation_id"] for o in timed if o["observation_id"] not in used]
    return repo.apply_segment_plan(session_id, plan, delete_ids)


def _current_boundaries(repo: Repository, session_id: str) -> tuple[list[dict], list[float]]:
    frames = repo.list_frames(session_id)
    starts = [o["video_offset_seconds"] for o in repo.list_observations(session_id=session_id)
              if o.get("video_offset_seconds") is not None]
    return frames, starts


def _interval(repo: Repository, session_id: str) -> float:
    seg = repo.get_session(session_id).get("segmentation_json") or {}
    return 1.0 / float(seg.get("fps") or 1.0)


def set_manual_boundaries(repo: Repository, session_id: str, boundary_seconds: list[float]) -> list[dict]:
    """Manual segmentation fallback: the user lists Reel start times in seconds."""
    frames = repo.list_frames(session_id)
    if not frames:
        raise ValueError("No extracted frames for this session.")
    offsets = [f["offset_seconds"] for f in frames]
    b = boundaries_from_offsets(offsets, boundary_seconds)
    segs = segments_from_boundaries(len(frames), offsets, b, _interval(repo, session_id))
    return _write_segments(repo, session_id, segs, method="manual")


def merge_with_next(repo: Repository, observation_id: str) -> list[dict]:
    o = repo.get_observation(observation_id)
    sid = o["session_id"]
    frames, starts = _current_boundaries(repo, sid)
    nxt = [s for s in starts if s > o["video_offset_seconds"]]
    if not nxt:
        raise ValueError("Last segment has no next segment to merge with.")
    keep = [s for s in starts if s != nxt[0]]
    return set_manual_boundaries(repo, sid, [s for s in keep if s > 0])


def split_at(repo: Repository, observation_id: str, at_seconds: float) -> list[dict]:
    o = repo.get_observation(observation_id)
    if not (o["video_offset_seconds"] < at_seconds < (o["segment_end_seconds"] or 1e9)):
        raise ValueError("Split point must be inside the segment.")
    _, starts = _current_boundaries(repo, o["session_id"])
    return set_manual_boundaries(repo, o["session_id"], [s for s in starts if s > 0] + [at_seconds])


# ---------------------------------------------------------------- classify

def segment_frame_paths(repo: Repository, o: dict) -> list[Path]:
    frames = repo.list_frames(o["session_id"])
    start, end = o.get("video_offset_seconds"), o.get("segment_end_seconds")
    if start is None or end is None:
        return []
    return [Path(f["path"]) for f in frames if start - 1e-6 <= f["offset_seconds"] < end - 1e-6]


def classify_session(repo: Repository, settings: Settings, session_id: str, classifier: Classifier,
                     *, include_reviewed: bool = False) -> dict:
    s = repo.get_session(session_id)
    exp = repo.get_experiment(s["experiment_id"])
    if classifier.external:
        assert_external_allowed(settings, exp)
    profile = repo.get_profile(exp["profile_id"])
    use_ocr = settings.ocr == "auto" and ocr_available()
    counts = {"classified": 0, "skipped_human_reviewed": 0, "needs_review": 0}
    for o in repo.list_observations(session_id=session_id):
        if o["review_status"] in (ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED) and not include_reviewed:
            counts["skipped_human_reviewed"] += 1
            continue
        frames = segment_frame_paths(repo, o)
        ocr_text = None
        if use_ocr and frames:
            ocr_text = ocr_image(frames[len(frames) // 2])
        item = ClassificationInput(o["observation_id"], profile, frames, o.get("caption_text"),
                                   o.get("hashtags") or [], ocr_text)
        r = classifier.classify(item)
        review = (ReviewStatus.AUTO_ACCEPTED if r.confidence >= settings.review_confidence_threshold
                  and r.target_match != TargetMatch.UNKNOWN else ReviewStatus.NEEDS_REVIEW)
        values = {
            "target_match": r.target_match.value,
            "topic_label": r.topic_label,
            "confidence": r.confidence,
            "classification_evidence": r.evidence + ([f"OCR text: {ocr_text[:200]}"] if ocr_text else [])
            + _preserved_evidence(o),
            "classifier_version": r.classifier_version,
            "review_status": review.value,
            "machine_label_json": {"target_match": r.target_match.value, "topic_label": r.topic_label,
                                   "confidence": r.confidence, "classifier_version": r.classifier_version},
        }
        if r.caption_text and not o.get("caption_text"):
            values["caption_text"] = r.caption_text
        if r.hashtags and not o.get("hashtags"):
            values["hashtags"] = r.hashtags
        if r.creator_handle and not o.get("creator_handle"):
            values["creator_handle"] = r.creator_handle
        if r.is_ad is True:
            values["is_ad"] = True
        if r.followed_indicator is True:
            values.update(_followed_signal_values(o, values["classification_evidence"]))
        values["classification_evidence"] = list(dict.fromkeys(values["classification_evidence"]))
        repo.update_observation(o["observation_id"], values)
        counts["classified"] += 1
        counts["needs_review"] += review == ReviewStatus.NEEDS_REVIEW
    repo.update_session(session_id, {"status": "classified"})
    return counts


ELIGIBILITY_CLASSIFIER = "classifier"
ELIGIBILITY_BULK = "bulk_assumption"
ELIGIBILITY_HUMAN = "human_review"


def _followed_signal_values(o: dict, evidence: list[str]) -> dict:
    """A followed-account marker was detected (R3). Never silently keep the row eligible and never silently
    overwrite an explicit status: undetermined rows become followed_account; recommended rows get a conflict."""
    values: dict = {"followed_signal": True}
    status = o.get("recommendation_status")
    if status == RecommendationStatus.UNDETERMINED:
        values["recommendation_status"] = RecommendationStatus.FOLLOWED_ACCOUNT.value
        values["eligibility_source"] = ELIGIBILITY_CLASSIFIER
    elif status == RecommendationStatus.RECOMMENDED:
        values["eligibility_conflict"] = True
        values["classification_evidence"] = evidence + [
            f"Eligibility conflict: followed-account marker detected but status is 'recommended' "
            f"(source: {o.get('eligibility_source') or 'unrecorded'}). Excluded from the primary metric until a "
            "human sets the status for this Reel."]
    return values


def bulk_set_eligibility(repo: Repository, session_id: str, status: str, *, only_undetermined: bool = True) -> dict:
    """Session-wide eligibility assumption (e.g. 'everything I scrolled was recommended').

    Rows with a detected followed-account marker are flagged as conflicts instead of silently becoming eligible.
    """
    updated = conflicts = 0
    for o in repo.list_observations(session_id=session_id):
        if only_undetermined and o["recommendation_status"] != RecommendationStatus.UNDETERMINED:
            continue
        conflict = bool(o.get("followed_signal")) and status == RecommendationStatus.RECOMMENDED
        values = {"recommendation_status": status, "eligibility_source": ELIGIBILITY_BULK,
                  "eligibility_conflict": conflict}
        if conflict:
            values["classification_evidence"] = (o.get("classification_evidence") or []) + [
                "Eligibility conflict: bulk 'recommended' applied to a Reel with a detected followed-account marker."]
            conflicts += 1
        repo.update_observation(o["observation_id"], values)
        updated += 1
    return {"updated": updated, "conflicts": conflicts}


def apply_correction(repo: Repository, observation_id: str, patch: dict) -> dict:
    """Human review (R5, D-026).

    `patch` holds only the fields the client sent (exclude_unset): an omitted field is unchanged, an explicit
    None clears a nullable field (`is_ad` back to "not identified", caption/topic/creator to null).
    Topic changes mark the row 'corrected'; a plain confirm marks it 'confirmed'. Review status is human
    provenance and is independent of confidence: a correction does not invent certainty. The new confidence
    is the reviewer's explicit value if given, otherwise null; an UNKNOWN label never carries a confidence.
    The machine's own confidence stays in `machine_label_json`.
    """
    o = repo.get_observation(observation_id)
    patch = dict(patch)
    confirm = patch.pop("confirm", False)
    bad = [k for k, v in patch.items() if v is None and k not in PATCH_NULLABLE_FIELDS]
    if bad:
        raise ValueError(f"These fields cannot be cleared: {', '.join(sorted(bad))}")
    explicit_confidence = "confidence" in patch
    confidence = patch.pop("confidence", None)
    values = {k: v for k, v in patch.items() if v != o.get(k)}
    label_changed = any(k in values for k in ("target_match", "topic_label"))
    resulting_match = values.get("target_match", o.get("target_match"))
    if explicit_confidence and confidence is not None and resulting_match == TargetMatch.UNKNOWN:
        raise ValueError("An UNKNOWN label cannot carry a confidence; omit confidence or send null.")
    if "recommendation_status" in patch:
        # An explicit per-Reel human ruling is authoritative and resolves any eligibility conflict.
        values["recommendation_status"] = patch["recommendation_status"]
        values["eligibility_source"] = ELIGIBILITY_HUMAN
        values["eligibility_conflict"] = False
    if label_changed:
        values["review_status"] = ReviewStatus.CORRECTED.value
        values["confidence"] = None if resulting_match == TargetMatch.UNKNOWN else confidence
        values["classification_evidence"] = (o.get("classification_evidence") or []) + ["Corrected by human reviewer."]
        if not o.get("classifier_version"):
            values["classifier_version"] = "human-manual"
    else:
        if explicit_confidence:
            values["confidence"] = None if resulting_match == TargetMatch.UNKNOWN else confidence
        if confirm:
            values["review_status"] = ReviewStatus.CONFIRMED.value
    return repo.update_observation(observation_id, values)
