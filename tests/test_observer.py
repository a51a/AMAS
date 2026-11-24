from pathlib import Path

import pytest

from app.observer.classifiers.base import ClassificationInput
from app.observer.classifiers.mock import MockClassifier
from app.observer.classifiers.vision_llm import VisionLabel, VisionLLMClassifier, VisionProvider
from app.observer import pipeline
from app.observer.segmentation import ahash, boundaries_from_offsets, detect_boundaries, segment
from tests.conftest import needs_ffmpeg
from tests.fixtures.synthetic_video import make_reels_video

DURATIONS = [6, 8, 5, 7, 6, 9]


def flat(v):
    return bytes([v] * 256)


def test_segmentation_groups_frames_and_ignores_small_motion():
    thumbs = [flat(10)] * 5 + [flat(12)] * 3 + [flat(200)] * 6 + [flat(90)] * 4
    r = segment(thumbs, 1.0, abs_threshold=28, min_segment_seconds=3)
    assert [(s.start_index, s.end_index) for s in r.segments] == [(0, 7), (8, 13), (14, 17)]


def test_min_segment_length_suppresses_in_reel_cuts():
    diffs = [0, 2, 90, 2, 90, 2, 2, 2, 90, 2]
    offsets = [float(i) for i in range(10)]
    b, _ = detect_boundaries(diffs, offsets, abs_threshold=28, min_segment_seconds=3)
    assert b == [4, 8]


def test_multi_frame_scroll_is_one_boundary():
    diffs = [0, 1, 1, 1, 60, 70, 1, 1, 1, 1]
    b, _ = detect_boundaries(diffs, [float(i) for i in range(10)], abs_threshold=28, min_segment_seconds=3)
    assert b == [6]


def test_manual_boundaries_map_to_frames():
    assert boundaries_from_offsets([0, 1, 2, 3, 4], [0, 2.2, 3.9]) == [2, 4]


def test_ahash_is_stable():
    assert ahash(flat(5)) == ahash(flat(5))
    half = bytes([0] * 128 + [255] * 128)
    assert ahash(half) != ahash(flat(5))


def _profile(repo):
    return repo.get_profile("PRF-EXP-001-biathlon")


def test_mock_classifier_never_fabricates(repo):
    clf = MockClassifier()
    r = clf.classify(ClassificationInput("o", _profile(repo)))
    assert r.target_match.value == "unknown" and r.confidence == 0 and r.caption_text is None
    r = clf.classify(ClassificationInput("o", _profile(repo), caption_text="Mass start finish! #biathlon"))
    assert r.target_match.value == "direct" and r.topic_label == "biathlon"
    r = clf.classify(ClassificationInput("o", _profile(repo), caption_text="Morning xc ski in Lillehammer"))
    assert r.target_match.value == "adjacent"
    r = clf.classify(ClassificationInput("o", _profile(repo), caption_text="Pasta carbonara recipe"))
    assert r.target_match.value == "unrelated" and r.confidence < 0.7
    r = clf.classify(ClassificationInput("o", _profile(repo), caption_text="Sponsored · new phone"))
    assert r.is_ad is True


class FakeProvider(VisionProvider):
    name = "fake"
    model = "fake-1"

    def __init__(self):
        self.calls = 0

    def label(self, images, prompt):
        self.calls += 1
        assert images and "biathlon" in prompt
        return VisionLabel(target_match="direct", topic_label="biathlon", confidence=0.93,
                           evidence=["rifle range visible"], visible_caption_text=None, visible_creator_handle=None)


@needs_ffmpeg
def test_pipeline_import_segment_classify(repo, settings, tmp_path):
    video = make_reels_video(tmp_path / "rec.mp4", DURATIONS)
    s = repo.create_session("EXP-001", checkpoint="T0", capture_method="screen_recording", label="t")
    s = pipeline.import_recording(repo, settings, s["session_id"], video)
    assert s["status"] == "segmented" and s["recording_sha256"]
    assert abs(s["recording_duration_seconds"] - sum(DURATIONS)) < 0.5
    obs = repo.list_observations(session_id=s["session_id"])
    # grouping: 6 Reels, not one observation per frame
    assert len(obs) == len(DURATIONS)
    starts = [o["video_offset_seconds"] for o in obs]
    expected = [sum(DURATIONS[:i]) for i in range(len(DURATIONS))]
    assert all(abs(a - b) <= 1.0 for a, b in zip(starts, expected))
    assert len(repo.list_frames(s["session_id"])) >= sum(DURATIONS) - 1
    assert all(o["content_fingerprint"].startswith("ahash:") for o in obs)

    # mock classification of pixels-only data -> unknown, flagged for review
    counts = pipeline.classify_session(repo, settings, s["session_id"], MockClassifier())
    assert counts["classified"] == 6 and counts["needs_review"] == 6

    # merge/split/manual fallback
    first = repo.list_observations(session_id=s["session_id"])[0]
    assert len(pipeline.merge_with_next(repo, first["observation_id"])) == 5
    first = repo.list_observations(session_id=s["session_id"])[0]
    assert len(pipeline.split_at(repo, first["observation_id"], 6.0)) == 6
    assert len(pipeline.set_manual_boundaries(repo, s["session_id"], [10, 20, 30])) == 4

    # external classifier is blocked by the privacy gate until enabled + consented
    clf = VisionLLMClassifier(FakeProvider())
    with pytest.raises(pipeline.PrivacyGateError):
        pipeline.classify_session(repo, settings, s["session_id"], clf)
    settings.allow_external_providers = True
    with pytest.raises(pipeline.PrivacyGateError):
        pipeline.classify_session(repo, settings, s["session_id"], clf)
    repo.set_external_consent("EXP-001", True)
    counts = pipeline.classify_session(repo, settings, s["session_id"], clf)
    assert counts["classified"] == 4 and clf.provider.calls == 4
    o = repo.list_observations(session_id=s["session_id"])[0]
    assert o["target_match"] == "direct" and o["review_status"] == "auto_accepted"
    assert o["classifier_version"] == "vision-llm-v1:fake:fake-1"

    # human correction is preserved on re-classification
    pipeline.apply_correction(repo, o["observation_id"], {"target_match": "adjacent"})
    pipeline.classify_session(repo, settings, s["session_id"], clf)
    o = repo.get_observation(o["observation_id"])
    assert o["target_match"] == "adjacent" and o["review_status"] == "corrected"
    assert o["machine_label_json"]["target_match"] == "direct"

    # deletion of recording + derived frames
    rec = Path(repo.get_session(s["session_id"])["recording_ref"])
    repo.delete_recording(s["session_id"])
    assert not rec.exists() and repo.list_frames(s["session_id"]) == []
    assert len(repo.list_observations(session_id=s["session_id"])) == 4


def test_import_rejects_unsupported_type(repo, settings, tmp_path):
    f = tmp_path / "x.gif"
    f.write_bytes(b"GIF89a")
    s = repo.create_session("EXP-001", checkpoint="T0", capture_method="screen_recording")
    with pytest.raises(ValueError):
        pipeline.import_recording(repo, settings, s["session_id"], f)
