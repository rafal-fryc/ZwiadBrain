"""Tests for the reject ledger (negative classification cache)."""

import json
from pathlib import Path

import pytest

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.pipeline.rejects import (
    RejectEntry,
    load_reject_ledger,
    write_reject_ledger,
)


def test_load_reject_ledger_missing_file_returns_empty(tmp_path: Path) -> None:
    """should treat a missing ledger as an empty cache (no-op)"""
    assert load_reject_ledger(tmp_path / "federal.json") == {}


def test_load_reject_ledger_malformed_json_raises(tmp_path: Path) -> None:
    """should fail loud on a malformed ledger file"""
    path = tmp_path / "federal.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_reject_ledger(path)


def test_load_reject_ledger_non_object_raises(tmp_path: Path) -> None:
    """should reject a ledger whose top level is not a JSON object"""
    path = tmp_path / "federal.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_reject_ledger(path)


def test_write_reject_ledger_is_byte_stable_and_sorted(tmp_path: Path) -> None:
    """should write sorted-key JSON so an unchanged re-write is byte-identical (D20)"""
    path = tmp_path / "rejects" / "federal.json"
    ledger = {"119-s-2": RejectEntry(cursor="b"), "119-hr-1": RejectEntry(cursor="a")}
    write_reject_ledger(path, ledger)
    first = path.read_bytes()
    write_reject_ledger(path, load_reject_ledger(path))
    assert path.read_bytes() == first
    text = first.decode("utf-8")
    assert text.index("119-hr-1") < text.index("119-s-2")  # sorted top-level keys


def test_write_reject_ledger_omits_none_id(tmp_path: Path) -> None:
    """should not serialize a null id (federal entries: key already is the slug)"""
    path = tmp_path / "federal.json"
    write_reject_ledger(path, {"119-hr-1": RejectEntry(cursor="a")})
    assert "id" not in json.loads(path.read_text(encoding="utf-8"))["119-hr-1"]


def test_write_reject_ledger_keeps_state_id(tmp_path: Path) -> None:
    """should serialize the page slug as a human anchor for state entries"""
    path = tmp_path / "state.json"
    write_reject_ledger(path, {"777": RejectEntry(cursor="h", id="ca-2025-ab-7")})
    assert json.loads(path.read_text(encoding="utf-8"))["777"]["id"] == "ca-2025-ab-7"
