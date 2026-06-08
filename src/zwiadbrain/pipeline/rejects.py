"""The reject ledger: a committed, cursor-invalidated negative classification cache.

`fetch-candidates --skip-existing` already drops in-scope bills that have a wiki page;
the reject ledger extends "don't redo work" to OUT-of-scope bills so a re-sweep does not
re-classify them (~13k plan tokens each) — until the bill's change cursor advances, at
which point it is re-classified. Federal keys by bill-slug + Congress updateDate; state
keys by LegiScan bill_id + change_hash. Mirrors `filter_unseen` (read) and
`render-classified` (write). See docs/superpowers/specs/2026-06-08-reject-ledger-design.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from zwiadbrain.exceptions import ConfigError


class RejectEntry(BaseModel):
    """One classified-out bill: its change cursor plus an optional human-readable id."""

    cursor: str
    id: str | None = None


RejectLedger = dict[str, RejectEntry]


def load_reject_ledger(path: Path) -> RejectLedger:
    """Load a reject ledger; missing file -> {} (no-op), malformed -> ConfigError."""
    if not path.exists():
        return {}
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"could not read reject ledger {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"reject ledger {path} must be a JSON object")
    entries: dict[str, object] = raw  # pyright: ignore[reportUnknownVariableType]
    ledger: RejectLedger = {}
    for key, value in entries.items():
        try:
            ledger[str(key)] = RejectEntry.model_validate(value)
        except ValidationError as exc:
            raise ConfigError(f"reject ledger {path} entry {key!r} invalid: {exc}") from exc
    return ledger


def write_reject_ledger(path: Path, ledger: RejectLedger) -> None:
    """Write ledger as sorted-key JSON so an unchanged re-record is byte-identical (D20)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    obj = {key: ledger[key].model_dump(exclude_none=True) for key in sorted(ledger)}
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
