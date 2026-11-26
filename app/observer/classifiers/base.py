"""Classifier interface. Implementations must never invent captions, creators or labels:
when evidence is missing they return `unknown` with confidence 0 and say why."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from app.models.schemas import TargetMatch


@dataclass
class ClassificationInput:
    observation_id: str
    profile: dict
    frame_paths: list[Path] = field(default_factory=list)
    caption_text: str | None = None
    hashtags: list[str] = field(default_factory=list)
    ocr_text: str | None = None


@dataclass
class ClassificationResult:
    target_match: TargetMatch
    topic_label: str | None
    confidence: float
    evidence: list[str]
    classifier_version: str
    caption_text: str | None = None  # only if actually read from the frames
    hashtags: list[str] | None = None
    creator_handle: str | None = None  # only if visibly shown
    is_ad: bool | None = None  # only if a visible "Sponsored"/"Ad" label
    followed_indicator: bool | None = None


class Classifier(ABC):
    name: str = "base"
    version: str = "0"
    external: bool = False  # True if frames leave the machine

    @abstractmethod
    def classify(self, item: ClassificationInput) -> ClassificationResult: ...

    @property
    def classifier_version(self) -> str:
        return f"{self.name}-{self.version}"
