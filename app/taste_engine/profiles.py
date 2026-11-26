"""Taste Engine (Sprint 1): stores user-defined interest profiles.

A profile describes the desired information environment: target topics, their
tier (direct/adjacent), polarity, desired share and keywords. Profiles are
versioned; every change creates a new version snapshot. Marketplace, Copy Taste,
Blend and Fork are future features and intentionally not implemented.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.models.schemas import ExperimentCreate, InterestProfile, ProfileTopic, TargetMatch
from app.storage.repository import Repository

REPO_ROOT = Path(__file__).resolve().parents[2]
EXP001_CONFIG = REPO_ROOT / "experiments" / "EXP-001-biathlon" / "config.json"


def load_experiment_config(path: Path = EXP001_CONFIG) -> tuple[ExperimentCreate, InterestProfile]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return ExperimentCreate(**raw["experiment"]), InterestProfile(**raw["profile"])


# Sprint 1 shipped these DIRECT keywords; several are ambiguous outside biathlon (R2, D-019).
LEGACY_V1_BIATHLON_KEYWORDS = frozenset({
    "biathlon", "biathlete", "ibu", "ibu world cup", "biathlonworld", "биатлон", "биатлонист",
    "biathlon world cup", "rifle range", "shooting range ski", "pursuit", "mass start", "relay biathlon",
})
# The complete topic list Sprint 1 shipped (commit e170928). Only a byte-for-byte unedited copy is upgraded.
LEGACY_V1_TOPICS_FILE = EXP001_CONFIG.parent / "profile-topics-v1.json"


def _normalized_topics(topics: list[dict]) -> list[dict]:
    return [ProfileTopic(**t).model_dump(mode="json") for t in topics]


def legacy_v1_topics() -> list[dict]:
    return _normalized_topics(json.loads(LEGACY_V1_TOPICS_FILE.read_text(encoding="utf-8")))


def is_unedited_legacy_profile(profile: dict) -> bool:
    """True only if every topic and every field equals what Sprint 1 shipped (C1, D-022)."""
    try:
        return _normalized_topics(profile.get("topics") or []) == legacy_v1_topics()
    except ValueError:
        return False


def upgrade_legacy_profile(repo: Repository, shipped: InterestProfile) -> dict:
    """Save the shipped topics as a new profile version only when the stored profile is a genuinely unedited
    Sprint 1 copy. Any user edit (any topic, field, weight, description, added topic) leaves the profile alone;
    the mock classifier still treats ambiguous legacy keywords as context only. Observations are not relabelled."""
    current = repo.get_profile(shipped.profile_id)
    if not is_unedited_legacy_profile(current):
        return current
    return repo.update_profile(shipped.profile_id, {"topics": [t.model_dump(mode="json") for t in shipped.topics]})


def ensure_exp001(repo: Repository) -> dict:
    """Create the real EXP-001 experiment and its default profile if missing (idempotent)."""
    exp, profile = load_experiment_config()
    repo.upsert_profile(profile)
    upgrade_legacy_profile(repo, profile)
    existing = repo.get_experiment(exp.experiment_id, missing_ok=True)
    return existing or repo.create_experiment(exp)


def target_topics(profile: dict, tier: TargetMatch) -> list[dict]:
    return [t for t in profile["topics"] if t.get("tier") == tier.value and t.get("polarity", "positive") == "positive"]


def negative_topics(profile: dict) -> list[dict]:
    return [t for t in profile["topics"] if t.get("polarity") == "negative"]
