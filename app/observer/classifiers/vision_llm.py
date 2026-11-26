"""Pluggable vision LLM classifier.

`VisionLLMClassifier` holds the prompt, schema and safety rules; a
`VisionProvider` does the transport. Sprint 1 ships `AnthropicVisionProvider`
(official `anthropic` SDK, optional extra `pip install -e '.[llm]'`). Other
providers implement the same one-method interface.

Frames leave the machine, so callers MUST check the privacy gate
(`app.observer.pipeline.assert_external_allowed`) before using this classifier.
"""
from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.models.schemas import TargetMatch
from app.observer.classifiers.base import ClassificationInput, ClassificationResult, Classifier


class VisionLabel(BaseModel):
    target_match: Literal["direct", "adjacent", "unrelated", "unknown"]
    topic_label: str | None = Field(description="Short topic slug, e.g. biathlon, cross_country_skiing, cooking")
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(description="Concrete visual or textual cues seen in the frames")
    visible_caption_text: str | None = Field(description="Caption text exactly as visible, else null")
    visible_hashtags: list[str] = Field(default_factory=list)
    visible_creator_handle: str | None = Field(description="Handle only if clearly printed on screen, else null")
    sponsored_label_visible: bool | None = None
    following_indicator_visible: bool | None = None


class VisionProvider(ABC):
    name: str

    @abstractmethod
    def label(self, images: list[bytes], prompt: str) -> VisionLabel: ...


SYSTEM_PROMPT = """You classify short-form video frames (Instagram Reels, desktop web) for a personal research experiment.
Rules:
- Use only what is visible in the frames. Never guess or invent captions, hashtags, creator names or topics.
- If text is not legible, return null for it. If evidence is insufficient, use target_match "unknown".
- creator handle: only if clearly printed on screen.
- sponsored_label_visible: true only if a "Sponsored" / "Paid partnership" / "Ad" label is visible.
- Keep topic classification independent from whether the item is an ad or from a followed account."""


def build_prompt(profile: dict) -> str:
    lines = ["Taxonomy for this experiment:"]
    for t in profile.get("topics", []):
        lines.append(f"- {t['tier'].upper()} / {t['topic_id']}: {t.get('description', '')}")
    lines.append("- UNRELATED: any other identifiable topic.")
    lines.append("- UNKNOWN: insufficient evidence to classify.")
    lines.append("The frames below belong to ONE Reel, in time order. Classify it.")
    return "\n".join(lines)


class AnthropicVisionProvider(VisionProvider):
    name = "anthropic"

    def __init__(self, model: str, client=None):
        self.model = model
        if client is None:
            try:
                import anthropic
            except ImportError as e:  # pragma: no cover
                raise RuntimeError("Install the optional extra: pip install -e '.[llm]'") from e
            client = anthropic.Anthropic()
        self.client = client

    def label(self, images: list[bytes], prompt: str) -> VisionLabel:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.standard_b64encode(img).decode()}}
            for img in images
        ]
        content.append({"type": "text", "text": prompt})
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            output_format=VisionLabel,
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            return VisionLabel(target_match="unknown", topic_label=None, confidence=0.0,
                               evidence=[f"Provider returned no label (stop_reason={response.stop_reason})."],
                               visible_caption_text=None, visible_creator_handle=None)
        return response.parsed_output


class VisionLLMClassifier(Classifier):
    name = "vision-llm"
    version = "v1"
    external = True

    def __init__(self, provider: VisionProvider, max_frames: int = 3):
        self.provider = provider
        self.max_frames = max(1, max_frames)

    @property
    def classifier_version(self) -> str:
        model = getattr(self.provider, "model", "")
        return f"{self.name}-{self.version}:{self.provider.name}:{model}".rstrip(":")

    def _pick(self, frames: list[Path]) -> list[Path]:
        if len(frames) <= self.max_frames:
            return frames
        step = (len(frames) - 1) / (self.max_frames - 1) if self.max_frames > 1 else 0
        return [frames[round(i * step)] for i in range(self.max_frames)] if self.max_frames > 1 else [frames[len(frames) // 2]]

    def classify(self, item: ClassificationInput) -> ClassificationResult:
        frames = [p for p in self._pick(item.frame_paths) if Path(p).exists()]
        if not frames:
            return ClassificationResult(TargetMatch.UNKNOWN, None, 0.0, ["No frames available."], self.classifier_version)
        label = self.provider.label([Path(p).read_bytes() for p in frames], build_prompt(item.profile))
        return ClassificationResult(
            target_match=TargetMatch(label.target_match),
            topic_label=label.topic_label,
            confidence=float(label.confidence),
            evidence=label.evidence or ["(provider gave no evidence)"],
            classifier_version=self.classifier_version,
            caption_text=label.visible_caption_text,
            hashtags=label.visible_hashtags or None,
            creator_handle=label.visible_creator_handle,
            is_ad=label.sponsored_label_visible,
            followed_indicator=label.following_indicator_visible,
        )
