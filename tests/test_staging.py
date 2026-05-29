"""Tests for the shared staging/validation helpers in pipeline/staging.py."""

import json
from pathlib import Path

import pytest

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.models import Bill
from zwiadbrain.pipeline.staging import stage_json, validate_model


def test_stage_json_writes_named_file_under_run_dir(tmp_path: Path) -> None:
    """should create the run dir and write indented JSON to <out>/<name>"""
    out = tmp_path / "run"
    path = stage_json([{"a": 1}], name="candidates.json", out=out)
    assert path == out / "candidates.json"
    assert json.loads(path.read_text(encoding="utf-8")) == [{"a": 1}]


def test_stage_json_defaults_to_timestamped_run_dir_when_out_none(tmp_path: Path) -> None:
    """should create data/runs/<timestamp>/<name> when out is None"""
    monkey = tmp_path
    import os

    os.chdir(monkey)
    path = stage_json({"k": "v"}, name="leghistory.json", out=None)
    assert path.name == "leghistory.json"
    assert path.parent.parent.name == "runs"
    assert path.exists()


def test_validate_model_raises_config_error_on_invalid(tmp_path: Path) -> None:
    """should wrap a ValidationError as ConfigError naming the label"""
    with pytest.raises(ConfigError, match="prev"):
        validate_model(Bill, {"id": "x", "type": "bill"}, label="prev")


def test_validate_model_returns_parsed_model_on_valid() -> None:
    """should return the parsed model on valid input"""
    out = validate_model(
        Bill,
        {"id": "118-hr-1", "jurisdiction": "US", "title": "t", "bill_number": "H.R. 1"},
        label="bill",
    )
    assert isinstance(out, Bill)
    assert out.id == "118-hr-1"
