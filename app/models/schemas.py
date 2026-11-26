"""Domain enums and Pydantic models shared by storage, engines and the API."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TargetMatch(StrEnum):
    """Topic classification relative to the experiment's target (EXP-001 taxonomy)."""

    DIRECT = "direct"
    ADJACENT = "adjacent"
    UNRELATED = "unrelated"
    UNKNOWN = "unknown"


class RecommendationStatus(StrEnum):
    """Content eligibility. Kept separate from topic classification.

    Only `recommended` (and not an identified ad) counts toward the primary metric.
    `undetermined` is flagged and reported through the all-exposure metric.
    """

    RECOMMENDED = "recommended"
    FOLLOWED_ACCOUNT = "followed_account"
    SEARCH_RESULT = "search_result"
    UNDETERMINED = "undetermined"


class ReviewStatus(StrEnum):
    PENDING = "pending"  # not classified yet
    NEEDS_REVIEW = "needs_review"  # classified, below confidence threshold
    AUTO_ACCEPTED = "auto_accepted"  # classified, above threshold, not human-checked
    CONFIRMED = "confirmed"  # human confirmed machine label
    CORRECTED = "corrected"  # human changed machine label


class Checkpoint(StrEnum):
    T0 = "T0"  # baseline
    T1 = "T1"  # intervention (no sample)
    T2 = "T2"  # immediate post-intervention
    T3 = "T3"  # +24h
    T4 = "T4"  # +72h
    T5 = "T5"  # +7d
    ADHOC = "ADHOC"


CHECKPOINT_OFFSETS_HOURS = {"T2": 0, "T3": 24, "T4": 72, "T5": 168}


class CaptureMethod(StrEnum):
    SCREEN_RECORDING = "screen_recording"
    SCREENSHOTS = "screenshots"
    MANUAL_ENTRY = "manual_entry"
    SYNTHETIC = "synthetic"


class ActionStatus(StrEnum):
    PLANNED = "planned"
    PENDING_USER = "pending_user"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    SIMULATED = "simulated"
    UNAVAILABLE = "unavailable"


class Authorization(StrEnum):
    USER_MANUAL = "user_manual"  # the account owner performed it by hand
    SIMULATED = "simulated"  # MockActuator, demo data only
    PLATFORM_AUTHORIZED = "platform_authorized"  # reserved; requires compliance review


# ---------- Profiles ----------


class ProfileTopic(BaseModel):
    topic_id: str
    label: str
    description: str = ""
    tier: TargetMatch = TargetMatch.DIRECT  # direct | adjacent
    polarity: str = "positive"  # positive | negative
    target_weight: float | None = None  # desired share 0..1
    keywords: list[str] = Field(default_factory=list)  # explicit evidence for this topic
    context_keywords: list[str] = Field(default_factory=list)  # ambiguous terms: context only, never sufficient


class InterestProfile(BaseModel):
    profile_id: str
    name: str
    description: str = ""
    topics: list[ProfileTopic]
    version: int = 1
    is_demo: bool = False
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)


class ProfileUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    topics: list[ProfileTopic] | None = None


# ---------- Experiments ----------


class ExperimentCreate(BaseModel):
    experiment_id: str
    name: str
    research_question: str = ""
    platform: str = "instagram"
    surface: str = "reels_desktop_web"
    profile_id: str
    target_topic: str
    target_share: float = 0.2
    is_demo: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class SessionCreate(BaseModel):
    checkpoint: Checkpoint
    label: str = ""
    capture_method: CaptureMethod = CaptureMethod.SCREEN_RECORDING
    captured_at: str | None = None
    notes: str = ""


class ManualObservation(BaseModel):
    topic_label: str | None = None
    target_match: TargetMatch = TargetMatch.UNKNOWN
    confidence: float | None = None
    classification_evidence: list[str] = Field(default_factory=list)
    recommendation_status: RecommendationStatus = RecommendationStatus.UNDETERMINED
    is_ad: bool | None = None
    caption_text: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    creator_handle: str | None = None
    content_fingerprint: str | None = None
    video_offset_seconds: float | None = None
    observed_at: str | None = None
    notes: str = ""


class ObservationPatch(BaseModel):
    topic_label: str | None = None
    target_match: TargetMatch | None = None
    recommendation_status: RecommendationStatus | None = None
    is_ad: bool | None = None
    caption_text: str | None = None
    hashtags: list[str] | None = None
    creator_handle: str | None = None
    notes: str | None = None
    confirm: bool = False  # confirm machine label without changes


class InterventionCreate(BaseModel):
    action_type: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    actuator: str = "manual"  # manual | mock | authorized
    # R4: planning before the baseline is ready requires an explicit, recorded protocol deviation.
    override_baseline_check: bool = False
    override_reason: str = ""


class InterventionComplete(BaseModel):
    completed_at: str | None = None
    evidence_notes: str = ""
    skipped: bool = False
