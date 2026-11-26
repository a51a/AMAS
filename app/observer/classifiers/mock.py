"""MockClassifier: deterministic keyword matcher over *available text only*.

It does not look at pixels. With no caption/hashtag/OCR text it returns
`unknown` (confidence 0). It is intended for tests, demos and as a fast
pre-labeller for manually entered captions.
"""
from __future__ import annotations

import re

from app.models.schemas import TargetMatch
from app.observer.classifiers.base import ClassificationInput, ClassificationResult, Classifier

AD_PATTERN = re.compile(r"\b(sponsored|paid partnership|реклама)\b", re.I)


def _norm(text: str) -> str:
    return re.sub(r"[#_]", " ", text.lower())


class MockClassifier(Classifier):
    name = "mock-keyword"
    version = "v1"

    def classify(self, item: ClassificationInput) -> ClassificationResult:
        parts = [p for p in [item.caption_text, " ".join(item.hashtags or []), item.ocr_text] if p]
        if not parts:
            return ClassificationResult(
                TargetMatch.UNKNOWN, None, 0.0,
                ["No caption, hashtag or OCR text available; the mock classifier does not inspect images."],
                self.classifier_version,
            )
        text = _norm(" ".join(parts))
        is_ad = True if AD_PATTERN.search(text) else None
        for tier, conf in ((TargetMatch.DIRECT, 0.9), (TargetMatch.ADJACENT, 0.75)):
            for topic in item.profile.get("topics", []):
                if topic.get("tier") != tier.value:
                    continue
                for kw in topic.get("keywords", []):
                    if re.search(rf"(?<!\w){re.escape(_norm(kw))}(?!\w)", text):
                        return ClassificationResult(
                            tier, topic["topic_id"], conf,
                            [f"Keyword '{kw}' (topic {topic['topic_id']}) found in available text."],
                            self.classifier_version, is_ad=is_ad,
                        )
        return ClassificationResult(
            TargetMatch.UNRELATED, "other", 0.5,
            ["Text available but no target or adjacent keyword matched. Low confidence: text may be incomplete."],
            self.classifier_version, is_ad=is_ad,
        )
