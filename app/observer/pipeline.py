"""Observer pipeline: import recording -> extract frames -> segment into Reels -> classify.

Every step writes raw data (frames, segment observations) that the user can
review and correct in the UI. Nothing here contacts Instagram.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.config import Settings
from app.models.schemas import RecommendationStatus, ReviewStatus, TargetMatch
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

def import_recording(repo: Repository, settings: Settings, session_id: str, source: Path,
                     *, original_name: str | None = None, move: bool = False) -> dict:
    """Copy a user-made screen recording into local storage, extract frames and auto-segment it."""
    source = Path(source)
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
    repo.update_session(session_id, {
        "recording_ref": str(dest),
        "recording_sha256": digest,
        "recording_duration_seconds": info["duration_seconds"],
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


def _write_segments(repo: Repository, session_id: str, segments, method: str) -> list[dict]:
    frames = repo.list_frames(session_id)
    rows = []
    for seg in segments:
        rep = frames[seg.representative_index]
        rows.append({
            "video_offset_seconds": round(seg.start_seconds, 3),
            "segment_end_seconds": round(seg.end_seconds, 3),
            "frame_count": len(seg.frame_indices),
            "representative_frame_id": rep["frame_id"],
            "content_fingerprint": f"ahash:{rep['ahash']}" if rep.get("ahash") else None,
            "target_match": TargetMatch.UNKNOWN.value,
            "recommendation_status": RecommendationStatus.UNDETERMINED.value,
            "review_status": ReviewStatus.PENDING.value,
            "segmentation_method": method,
        })
    return repo.replace_observations(session_id, rows)


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
            "classification_evidence": r.evidence + ([f"OCR text: {ocr_text[:200]}"] if ocr_text else []),
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
        if r.followed_indicator is True and o["recommendation_status"] == RecommendationStatus.UNDETERMINED:
            values["recommendation_status"] = RecommendationStatus.FOLLOWED_ACCOUNT.value
        repo.update_observation(o["observation_id"], values)
        counts["classified"] += 1
        counts["needs_review"] += review == ReviewStatus.NEEDS_REVIEW
    repo.update_session(session_id, {"status": "classified"})
    return counts


def apply_correction(repo: Repository, observation_id: str, patch: dict) -> dict:
    """Human review. Topic changes mark the row 'corrected'; a plain confirm marks it 'confirmed'."""
    o = repo.get_observation(observation_id)
    confirm = patch.pop("confirm", False)
    values = {k: v for k, v in patch.items() if v is not None}
    label_changed = any(k in values and values[k] != o.get(k) for k in ("target_match", "topic_label"))
    if label_changed:
        values["review_status"] = ReviewStatus.CORRECTED.value
        values["confidence"] = 1.0
        values["classification_evidence"] = (o.get("classification_evidence") or []) + ["Corrected by human reviewer."]
        if not o.get("classifier_version"):
            values["classifier_version"] = "human-manual"
    elif confirm:
        values["review_status"] = ReviewStatus.CONFIRMED.value
    return repo.update_observation(observation_id, values)
