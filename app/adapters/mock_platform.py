"""MockPlatformAdapter: synthetic platform for tests and clearly-labelled demo data."""
from __future__ import annotations

import random

from app.adapters.base import ActionSpec, PlatformAdapter

TOPICS_UNRELATED = ["comedy", "cooking", "music", "travel", "pets", "tech", "football", "fitness", "fashion"]


class MockPlatformAdapter(PlatformAdapter):
    platform = "mock"
    surfaces = ("mock_feed",)
    capture_methods = ("synthetic",)

    def action_catalog(self) -> list[ActionSpec]:
        return [
            ActionSpec("simulated_boost", "Simulated interest boost",
                       "Simulate stronger interest in {topic} (no real platform involved).",
                       "Simulation only.", {"topic": "biathlon"}),
        ]

    @staticmethod
    def simulate_feed(rng: random.Random, n: int, *, direct_rate: float, adjacent_rate: float,
                      unknown_rate: float = 0.04, ad_rate: float = 0.06, followed_rate: float = 0.04) -> list[dict]:
        """Generate synthetic observation rows. Every row is tagged as simulated."""
        rows = []
        for i in range(n):
            r = rng.random()
            if r < direct_rate:
                tm, topic = "direct", "biathlon"
            elif r < direct_rate + adjacent_rate:
                tm, topic = "adjacent", rng.choice(["cross_country_skiing", "winter_sports"])
            elif r < direct_rate + adjacent_rate + unknown_rate:
                tm, topic = "unknown", None
            else:
                tm, topic = "unrelated", rng.choice(TOPICS_UNRELATED)
            is_ad = rng.random() < ad_rate
            status = "followed_account" if rng.random() < followed_rate else "recommended"
            rows.append({
                "sequence_number": i + 1,
                "video_offset_seconds": float(i * 12),
                "segment_end_seconds": float(i * 12 + 11),
                "topic_label": topic,
                "target_match": tm,
                "confidence": round(rng.uniform(0.6, 0.98), 2) if tm != "unknown" else 0.0,
                "classification_evidence": ["SIMULATED demo observation - not real data."],
                "recommendation_status": status,
                "is_ad": is_ad,
                "content_fingerprint": f"sim:{rng.getrandbits(40):010x}",
                "classifier_version": "synthetic-v1",
                "review_status": "auto_accepted",
                "segmentation_method": "synthetic",
            })
        return rows
