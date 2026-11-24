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


def ensure_exp001(repo: Repository) -> dict:
    """Create the real EXP-001 experiment and its default profile if missing (idempotent)."""
    exp, profile = load_experiment_config()
    repo.upsert_profile(profile)
    existing = repo.get_experiment(exp.experiment_id, missing_ok=True)
    return existing or repo.create_experiment(exp)


def target_topics(profile: dict, tier: TargetMatch) -> list[dict]:
    return [t for t in profile["topics"] if t.get("tier") == tier.value and t.get("polarity", "positive") == "positive"]


def negative_topics(profile: dict) -> list[dict]:
    return [t for t in profile["topics"] if t.get("polarity") == "negative"]
