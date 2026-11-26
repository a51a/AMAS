"""MockClassifier: deterministic keyword matcher over *available text only*.

It does not look at pixels. With no caption/hashtag/OCR text it returns
`unknown` (confidence 0). It is intended for tests, demos and as a fast
pre-labeller for manually entered captions.

v2 (R2, D-019): DIRECT needs an explicit target term (for EXP-001: "biathlon", "биатлон", ...).
Ambiguous sport words such as "pursuit", "mass start", "relay" or "IBU" are context only: on their
own they leave the item UNKNOWN. Instagram UI words ("Follow", "Like", "Reels") are not evidence.
The mock never returns UNRELATED, because the absence of target keywords does not identify other
content; a human (or a richer classifier) must decide that.
"""
from __future__ import annotations

import re

from app.models.schemas import TargetMatch
from app.observer.classifiers.base import ClassificationInput, ClassificationResult, Classifier

AD_PATTERN = re.compile(r"\b(sponsored|paid partnership|реклама)\b", re.I)

# Terms that are shared with other sports or with non-sport content. Even when an older profile lists
# them as DIRECT keywords they only count as context, never as explicit target evidence.
AMBIGUOUS_TERMS = {
    "pursuit", "mass start", "relay", "sprint", "individual", "ibu", "rifle", "shooting", "shooting range",
    "rifle range", "shooting range ski", "prone", "standing", "penalty loop", "world cup", "relay biathlon",
}

# Words that come from the Instagram interface rather than from the content itself.
UI_WORDS = {
    "follow", "following", "followed", "like", "likes", "liked", "share", "send", "save", "saved", "comment",
    "comments", "reply", "reels", "reel", "more", "less", "audio", "original", "remix", "view", "views",
    "sponsored", "paid", "partnership", "ad", "home", "search", "explore", "profile", "message", "messages",
    "подписаться", "подписки", "нравится", "реклама", "ещё", "еще",
}

MIN_INFORMATIVE_WORDS = 3


def _norm(text: str) -> str:
    return re.sub(r"[#_@]", " ", text.lower())


def _has(term: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(_norm(term).strip())}(?!\w)", text) is not None


def _informative_words(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", text) if w not in UI_WORDS and not w.isdigit()]


class MockClassifier(Classifier):
    name = "mock-keyword"
    version = "v2"

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
        topics = item.profile.get("topics", [])
        context_hits: list[str] = []
        for tier, conf in ((TargetMatch.DIRECT, 0.9), (TargetMatch.ADJACENT, 0.75)):
            for topic in topics:
                if topic.get("tier") != tier.value or topic.get("polarity", "positive") != "positive":
                    continue
                for kw in topic.get("keywords", []):
                    if _norm(kw).strip() in AMBIGUOUS_TERMS:
                        continue
                    if _has(kw, text):
                        return ClassificationResult(
                            tier, topic["topic_id"], conf,
                            [f"Explicit keyword '{kw}' (topic {topic['topic_id']}) found in available text."],
                            self.classifier_version, is_ad=is_ad,
                        )
        for topic in topics:
            ambiguous = [k for k in topic.get("keywords", []) if _norm(k).strip() in AMBIGUOUS_TERMS]
            for kw in list(topic.get("context_keywords", [])) + ambiguous:
                if _has(kw, text) and kw not in context_hits:
                    context_hits.append(kw)
        if len(_informative_words(text)) < MIN_INFORMATIVE_WORDS:
            return ClassificationResult(
                TargetMatch.UNKNOWN, None, 0.0,
                ["Available text is interface-only or too short to identify the content."],
                self.classifier_version, is_ad=is_ad,
            )
        if context_hits:
            return ClassificationResult(
                TargetMatch.UNKNOWN, None, 0.3,
                [f"Only ambiguous context terms found ({', '.join(context_hits)}); no explicit target term. "
                 "Needs human review."],
                self.classifier_version, is_ad=is_ad,
            )
        return ClassificationResult(
            TargetMatch.UNKNOWN, None, 0.2,
            ["Text available but no explicit target or adjacent keyword matched. The mock cannot identify other "
             "content from missing keywords; review manually."],
            self.classifier_version, is_ad=is_ad,
        )
