"""Relevance-taxonomy loader.

Parses ``reference/topics.yaml`` into the two views the deterministic Python
pipeline needs: ``seeds`` (the flat keyword recall lexicon, fed to
``keyword_filter``) and ``topic_keys`` (the valid ``topics[]`` values, checked
at render). The classifier subagent reads ``topics.yaml`` directly for the full
rubric (positive criteria + DISQUALIFY lexicon), so nothing else is loaded here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from zwiadbrain.exceptions import ConfigError


class Reference(BaseModel):
    """The taxonomy views consumed by the deterministic Python pipeline."""

    model_config = ConfigDict(frozen=True)

    seeds: list[str]
    topic_keys: list[str]


class _Topic(BaseModel):
    """One taxonomy topic: ``label`` is for humans, ``seeds`` feed recall."""

    label: str | None = None
    seeds: list[str] = []


class _TopicsFile(BaseModel):
    """The parsed shape of ``topics.yaml`` — only the part Python consumes."""

    topics: dict[str, _Topic]


def load_reference(path: Path) -> Reference:
    """Load ``topics.yaml`` into a :class:`Reference`.

    Raises :class:`ConfigError` if the file is missing, unparseable, or lacks a
    well-formed top-level ``topics`` table.
    """
    if not path.exists():
        raise ConfigError(f"relevance taxonomy not found: {path}")
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        parsed = _TopicsFile.model_validate(raw)
    except yaml.YAMLError as exc:
        raise ConfigError(f"relevance taxonomy is not valid YAML: {path}") from exc
    except ValidationError as exc:
        raise ConfigError(f"relevance taxonomy is malformed: {path}\n{exc}") from exc

    seeds = [seed for topic in parsed.topics.values() for seed in topic.seeds]
    # De-duplicate, preserving first-seen order.
    return Reference(seeds=list(dict.fromkeys(seeds)), topic_keys=list(parsed.topics))
