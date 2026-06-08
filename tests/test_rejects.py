"""Tests for the reject ledger (negative classification cache)."""

import json
from pathlib import Path

import pytest

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.pipeline.rejects import (
    RejectEntry,
    federal_cursor,
    federal_key,
    filter_by_key,
    filter_cached_rejects,
    load_reject_ledger,
    state_cursor,
    state_key,
    write_reject_ledger,
)
from zwiadbrain.sources.base import Candidate


def test_load_reject_ledger_missing_file_returns_empty(tmp_path: Path) -> None:
    """should treat a missing ledger as an empty cache (no-op)"""
    assert load_reject_ledger(tmp_path / "federal.json") == {}


def test_load_reject_ledger_round_trips_field_values(tmp_path: Path) -> None:
    """should load each entry's cursor and id back to their written values"""
    path = tmp_path / "state.json"
    write_reject_ledger(
        path,
        {"119-hr-1": RejectEntry(cursor="c1"), "777": RejectEntry(cursor="h", id="ca-2025-ab-7")},
    )
    loaded = load_reject_ledger(path)
    assert loaded["119-hr-1"].cursor == "c1"
    assert loaded["119-hr-1"].id is None
    assert loaded["777"].cursor == "h"
    assert loaded["777"].id == "ca-2025-ab-7"


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


# ---------------------------------------------------------------------------
# Task 2: cursor-aware filter, filter_by_key, source adapters
# ---------------------------------------------------------------------------


def _fed(native_id: str, update_date: str | None = None) -> Candidate:
    return Candidate(
        source="congress", native_id=native_id, jurisdiction="US",
        title=native_id, update_date=update_date,
    )


def _state(bill_id: str, change_hash: str | None = None) -> Candidate:
    return Candidate(
        source="legiscan", native_id=bill_id, jurisdiction="US-CA",
        title="", raw={"change_hash": change_hash},
    )


def test_federal_key_maps_native_id_to_slug() -> None:
    """should map a Congress native_id to its bill-slug form"""
    assert federal_key(_fed("119/hr/9076")) == "119-hr-9076"


def test_federal_cursor_reads_candidate_update_date() -> None:
    """should read the federal change cursor off the candidate's update_date"""
    assert federal_cursor(_fed("119/hr/1", "2026-01-01")) == "2026-01-01"


def test_state_key_and_cursor_read_legiscan_fields() -> None:
    """should key state candidates by bill_id and read change_hash from raw"""
    assert state_key(_state("777", "h")) == "777"
    assert state_cursor(_state("777", "hash-abc")) == "hash-abc"
    assert state_cursor(_state("777", None)) is None


def test_filter_cached_rejects_drops_unchanged_cursor() -> None:
    """should drop a candidate whose key is cached and cursor matches"""
    cands = [_fed("119/hr/1", "2026-01-01"), _fed("119/hr/2", "2026-01-02")]
    ledger = {"119-hr-1": RejectEntry(cursor="2026-01-01")}
    kept = filter_cached_rejects(cands, ledger, key_of=federal_key, cursor_of=federal_cursor)
    assert [c.native_id for c in kept] == ["119/hr/2"]


def test_filter_cached_rejects_keeps_advanced_cursor() -> None:
    """should keep (re-classify) a cached bill whose cursor advanced"""
    cands = [_fed("119/hr/1", "2026-02-01")]
    ledger = {"119-hr-1": RejectEntry(cursor="2026-01-01")}
    kept = filter_cached_rejects(cands, ledger, key_of=federal_key, cursor_of=federal_cursor)
    assert [c.native_id for c in kept] == ["119/hr/1"]


def test_filter_cached_rejects_empty_ledger_is_noop() -> None:
    """should pass everything through when the ledger is empty"""
    cands = [_fed("119/hr/1", "x")]
    assert filter_cached_rejects(cands, {}, key_of=federal_key, cursor_of=federal_cursor) == cands


def test_filter_cached_rejects_state_drops_unchanged_hash() -> None:
    """should drop a state candidate whose change_hash is unchanged"""
    cands = [_state("777", "h1"), _state("888", "h2")]
    ledger = {"777": RejectEntry(cursor="h1", id="ca-2025-ab-7")}
    kept = filter_cached_rejects(cands, ledger, key_of=state_key, cursor_of=state_cursor)
    assert [c.native_id for c in kept] == ["888"]


def test_filter_by_key_drops_known_keys_preserving_order() -> None:
    """should drop candidates whose key is already known (state wiki dedup)"""
    cands = [_state("777"), _state("888"), _state("999")]
    kept = filter_by_key(cands, {"888"}, key_of=state_key)
    assert [c.native_id for c in kept] == ["777", "999"]
