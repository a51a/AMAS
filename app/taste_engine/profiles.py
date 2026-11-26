"""Taste Engine (Sprint 1): stores user-defined interest profiles.

A profile describes the desired information environment: target topics, their
tier (direct/adjacent), polarity, desired share and keywords. Profiles are
versioned; every change creates a new version snapshot. Marketplace, Copy Taste,
Blend and Fork are future features and intentionally not implemented.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.models.schemas import ExperimentCreate, InterestProfile, TargetMatch
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


def upgrade_legacy_profile(repo: Repository, shipped: InterestProfile) -> dict:
    """If a stored profile still has the exact Sprint 1 biathlon keyword set, save the shipped topics as a
    new profile version. Profiles the user edited are left alone; existing observations are not relabelled."""
    current = repo.get_profile(shipped.profile_id)
    direct = next((t for t in current["topics"] if t.get("topic_id") == "biathlon"), None)
    if direct is None or set(direct.get("keywords") or []) != LEGACY_V1_BIATHLON_KEYWORDS:
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
