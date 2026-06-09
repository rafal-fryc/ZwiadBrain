"""Tests for the relevance-taxonomy loader: keyword seeds and topic keys.

The loader feeds two consumers: the Python keyword recall filter (``seeds``) and
render-time validation (``topic_keys``). The classifier subagent reads
``topics.yaml`` directly for the rubric, so the loader stays minimal.
"""

from pathlib import Path

import pytest

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.reference.loader import load_reference

_YAML = """
topics:
  ai:
    label: "Artificial Intelligence"
    seeds: ["artificial intelligence", "automated decision", "facial recognition"]
  privacy:
    label: "Consumer Privacy"
    seeds: ["personal data", "data broker", "artificial intelligence"]
  cyber:
    label: "Cybersecurity"
    seeds: ["ransomware", "CISA"]
positive_criteria:
  - "Creates or amends obligations governing AI systems"
disqualify:
  - "Ceremonial or commemorative resolution"
policy_areas:
  - "Science, Technology, Communications"
  - "Commerce"
"""


def _write(tmp_path: Path, yaml: str = _YAML) -> Path:
    path = tmp_path / "topics.yaml"
    path.write_text(yaml, encoding="utf-8")
    return path


def test_load_reference_collects_flat_deduped_seeds(tmp_path: Path) -> None:
    """should flatten seeds across topics, de-duplicating while preserving order"""
    ref = load_reference(_write(tmp_path))
    assert ref.seeds == [
        "artificial intelligence",
        "automated decision",
        "facial recognition",
        "personal data",
        "data broker",
        "ransomware",
        "CISA",
    ]


def test_load_reference_exposes_topic_keys_in_file_order(tmp_path: Path) -> None:
    """should expose the taxonomy keys (valid topics[] values) in file order"""
    ref = load_reference(_write(tmp_path))
    assert ref.topic_keys == ["ai", "privacy", "cyber"]


def test_load_reference_exposes_policy_areas(tmp_path: Path) -> None:
    """should expose the policyArea allowlist used by the Stage-2 recall probe"""
    ref = load_reference(_write(tmp_path))
    assert ref.policy_areas == ["Science, Technology, Communications", "Commerce"]


def test_load_reference_policy_areas_default_to_empty(tmp_path: Path) -> None:
    """should default policy_areas to [] when the file omits them"""
    ref = load_reference(_write(tmp_path, yaml="topics:\n  ai:\n    seeds: [ai]\n"))
    assert ref.policy_areas == []


def test_load_reference_exposes_scope_version(tmp_path: Path) -> None:
    """should expose the taxonomy's scope-rule vintage (D96)"""
    ref = load_reference(_write(tmp_path, yaml=_YAML + 'scope_version: "D95"\n'))
    assert ref.scope_version == "D95"


def test_load_reference_scope_version_defaults_to_none(tmp_path: Path) -> None:
    """should default scope_version to None when the file omits it (pre-D96 shape)"""
    ref = load_reference(_write(tmp_path))
    assert ref.scope_version is None


def test_load_reference_raises_on_missing_file(tmp_path: Path) -> None:
    """should raise ConfigError when the topics file does not exist"""
    with pytest.raises(ConfigError):
        load_reference(tmp_path / "absent.yaml")


def test_load_reference_raises_when_topics_table_missing(tmp_path: Path) -> None:
    """should raise ConfigError when the file lacks a top-level 'topics' table"""
    with pytest.raises(ConfigError):
        load_reference(_write(tmp_path, yaml="positive_criteria: []\n"))


def test_loads_the_shipped_topics_yaml() -> None:
    """should load the committed reference/topics.yaml with the ai/privacy/cyber topics"""
    repo_root = Path(__file__).resolve().parents[1]
    ref = load_reference(repo_root / "reference" / "topics.yaml")
    assert ref.topic_keys == ["ai", "privacy", "cyber"]
    assert "artificial intelligence" in ref.seeds
    assert "security breach" in ref.seeds  # D94: recovers NY SHIELD-style phrasing
    assert len(ref.seeds) == len(set(ref.seeds))  # no duplicates survive
    assert ref.scope_version is not None  # D96: the shipped taxonomy must be versioned
