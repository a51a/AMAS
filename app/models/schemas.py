"""Domain enums and Pydantic models shared by storage, engines and the API."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- Timestamps (R6, D-027) ----------


def normalize_timestamp(value: str | None, *, field: str = "timestamp") -> str | None:
    """Validate an ISO 8601 entry timestamp and normalise it to UTC (`...+00:00`).

    New input must carry an explicit timezone (`Z` or `+01:00`). Naive values are rejected because their
    wall-clock zone is unknowable later; malformed values are rejected. None/"" stays None.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO 8601 string")
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        raise ValueError(f"{field} is not a valid ISO 8601 timestamp: {value!r}") from None
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset (e.g. 2026-11-27T13:00:00Z or +01:00): {value!r}")
    return dt.astimezone(timezone.utc).isoformat()


def parse_stored_timestamp(value: str | None) -> tuple[datetime | None, bool]:
    """Read a timestamp that is already stored (possibly legacy). Returns (aware UTC datetime, assumed_utc).

    Stored values written before D-027 may be naive. They are interpreted as UTC so that chronology never crashes,
    and `assumed_utc=True` lets callers report that the zone was assumed. Unparseable values return (None, False).
    """
    if not value or not isinstance(value, str):
        return None, False
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None, False
    if dt.tzinfo is None or dt.utcoffset() is None:
        return dt.replace(tzinfo=timezone.utc), True
    return dt.astimezone(timezone.utc), False


class CaptureTimeSource(StrEnum):
    """Where a session's `captured_at` came from. Only the first two are evidence of when the feed was seen."""

    USER = "user"  # entered by the account owner (API, UI or CLI --captured-at)
    RECORDING_METADATA = "recording_metadata"  # container creation time from the recording itself
    SESSION_CREATED = "session_created"  # fallback: when the session row was created (not capture evidence)
    IMPORT_TIME = "import_time"  # fallback: when the recording was imported (not capture evidence)


VERIFIED_CAPTURE_SOURCES = {CaptureTimeSource.USER.value, CaptureTimeSource.RECORDING_METADATA.value}


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

    @field_validator("captured_at")
    @classmethod
    def _tz_captured(cls, v):
        return normalize_timestamp(v, field="captured_at")


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

    @field_validator("observed_at")
    @classmethod
    def _tz_observed(cls, v):
        return normalize_timestamp(v, field="observed_at")

    @field_validator("confidence")
    @classmethod
    def _confidence_range(cls, v):
        if v is not None and not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return v


# R5 (D-026): in a PATCH an omitted field means "unchanged" and an explicit null means "clear".
# Only these fields may be cleared; the others have a required value (hashtags clear with []).
PATCH_NULLABLE_FIELDS = ("topic_label", "is_ad", "caption_text", "creator_handle", "confidence")


class ObservationPatch(BaseModel):
    topic_label: str | None = None
    target_match: TargetMatch | None = None
    recommendation_status: RecommendationStatus | None = None
    is_ad: bool | None = None
    caption_text: str | None = None
    hashtags: list[str] | None = None
    creator_handle: str | None = None
    notes: str | None = None
    # Optional reviewer-stated certainty for a non-UNKNOWN label. A human edit never implies 1.0.
    confidence: float | None = None
    confirm: bool = False  # confirm machine label without changes

    @model_validator(mode="after")
    def _explicit_nulls(self):
        for name in self.model_fields_set:
            if getattr(self, name) is None and name not in PATCH_NULLABLE_FIELDS:
                raise ValueError(f"{name} cannot be null; omit it to keep the current value")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return self


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

    @field_validator("completed_at")
    @classmethod
    def _tz_completed(cls, v):
        return normalize_timestamp(v, field="completed_at")
