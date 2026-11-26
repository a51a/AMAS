"""InstagramManualAdapter: every action is performed by the account owner by hand.

AMAS never logs in, never stores credentials, cookies or tokens, never
automates playback, likes, follows, comments or saves, and never scrapes.
"""
from __future__ import annotations

from app.adapters.base import ActionSpec, PlatformAdapter


class InstagramManualAdapter(PlatformAdapter):
    platform = "instagram"
    surfaces = ("reels_desktop_web",)
    capture_methods = ("screen_recording", "screenshots", "manual_entry")
    supports_automation = False

    def action_catalog(self) -> list[ActionSpec]:
        return [
            ActionSpec(
                "search_and_watch_target",
                "Search and watch target Reels",
                "In Instagram on the web, search for '{query}'. Open {count} Reels from the results that are clearly "
                "about {topic} and watch each one to the end. Do this yourself; do not use any automation. "
                "These views are part of the intervention and are NOT recorded as observations.",
                "Search-originated views are the intervention signal. Never count them as recommendation exposures.",
                {"query": "biathlon", "count": 10, "topic": "biathlon"},
            ),
            ActionSpec(
                "engage_target",
                "Genuinely engage with target Reels",
                "While watching {topic} Reels, like or save the ones you would genuinely engage with (up to {count}). "
                "Record how many you liked and saved in the evidence notes.",
                "Engagement strength confounds watch time; record counts so later analysis can separate them.",
                {"topic": "biathlon", "count": 5},
            ),
            ActionSpec(
                "follow_target_accounts",
                "Follow target accounts",
                "Follow up to {count} accounts that publish {topic} content, e.g. an official federation account "
                "you have verified yourself. List the handles in the evidence notes.",
                "Content from followed accounts is excluded from the primary metric afterwards; mark it in review.",
                {"topic": "biathlon", "count": 3},
            ),
            ActionSpec(
                "feed_dwell_target",
                "Dwell on target Reels in the feed",
                "When a {topic} Reel appears in the Reels feed, watch it fully; skip unrelated Reels promptly. "
                "Apply this only during the stated intervention window.",
                "Changes observer behaviour during sampling; only use outside observation sessions or document it.",
                {"topic": "biathlon"},
            ),
            ActionSpec(
                "native_preference_control",
                "Use Instagram's native preference controls",
                "Use Instagram's own 'Interested' / 'Not interested' or content preference settings for {topic}.",
                "Reserved for a separate native-controls experiment; mixing it into EXP-001 confounds the result.",
                {"topic": "biathlon"},
                reserved_for="EXP-002 (native controls comparison)",
            ),
            ActionSpec(
                "custom",
                "Custom documented action",
                "{description}",
                "Describe exactly what was done so the experiment stays reproducible.",
                {"description": "Describe the action."},
            ),
        ]
