from app.taste_engine.profiles import load_experiment_config


def test_exp001_config_loads_and_matches_taxonomy():
    exp, profile = load_experiment_config()
    assert exp.experiment_id == "EXP-001" and exp.target_topic == "biathlon" and exp.target_share == 0.2
    assert not exp.is_demo
    tiers = {t.topic_id: t.tier.value for t in profile.topics}
    assert tiers == {"biathlon": "direct", "cross_country_skiing": "adjacent", "winter_sports": "adjacent"}


def test_exp001_available_immediately(repo):
    e = repo.get_experiment("EXP-001")
    assert e["is_demo"] is False and e["platform"] == "instagram"
    p = repo.get_profile(e["profile_id"])
    assert p["version"] == 1 and p["created_at"] and p["updated_at"]


def test_profile_update_bumps_version_and_keeps_history(repo):
    p = repo.get_profile("PRF-EXP-001-biathlon")
    topics = p["topics"] + [{"topic_id": "gambling", "label": "Gambling", "tier": "direct", "polarity": "negative",
                             "keywords": ["casino"]}]
    p2 = repo.update_profile(p["profile_id"], {"topics": topics})
    assert p2["version"] == 2
    versions = repo.profile_versions(p["profile_id"])
    assert [v["version"] for v in versions] == [2, 1]
    assert len(versions[1]["snapshot_json"]["topics"]) == 3


def test_ensure_exp001_is_idempotent(repo):
    from app.taste_engine.profiles import ensure_exp001

    ensure_exp001(repo)
    assert [e["experiment_id"] for e in repo.list_experiments()].count("EXP-001") == 1
