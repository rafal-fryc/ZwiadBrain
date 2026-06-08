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
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.pipeline.staging import validate_model
from zwiadbrain.sources.base import Candidate


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
    raw_dict: dict[str, object] = raw  # pyright: ignore[reportUnknownVariableType]
    ledger: RejectLedger = {}
    for key, value in raw_dict.items():
        ledger[str(key)] = validate_model(
            RejectEntry, value, label=f"reject ledger {path} entry {key!r}"
        )
    return ledger


def write_reject_ledger(path: Path, ledger: RejectLedger) -> None:
    """Write ledger as sorted-key JSON so an unchanged re-record is byte-identical (D20)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    obj = {key: ledger[key].model_dump(exclude_none=True) for key in sorted(ledger)}
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Task 2: cursor-aware filter, filter_by_key, source adapters
# ---------------------------------------------------------------------------


def filter_cached_rejects(
    candidates: list[Candidate],
    ledger: RejectLedger,
    *,
    key_of: Callable[[Candidate], str],
    cursor_of: Callable[[Candidate], str | None],
) -> list[Candidate]:
    """Drop a candidate iff it is in *ledger* AND its cursor is unchanged.

    A cursor mismatch (the bill changed) or an absent key keeps the candidate so it is
    re-classified. Order preserved; empty/missing ledger is a no-op. Mirrors `filter_unseen`.
    """
    kept: list[Candidate] = []
    for candidate in candidates:
        entry = ledger.get(key_of(candidate))
        if entry is not None and entry.cursor == cursor_of(candidate):
            continue
        kept.append(candidate)
    return kept


def filter_by_key(
    candidates: list[Candidate], known: set[str], *, key_of: Callable[[Candidate], str]
) -> list[Candidate]:
    """Drop candidates whose `key_of(c)` is in *known* (state in-scope wiki dedup).

    The state analog of `filter_unseen`: state page ids are slugs unavailable at discovery,
    so the discovery key is the LegiScan bill_id and *known* is harvested from frontmatter.
    """
    return [c for c in candidates if key_of(c) not in known]


def federal_key(candidate: Candidate) -> str:
    """Congress native_id "119/hr/9076" -> bill-slug "119-hr-9076" (matches the page id)."""
    return candidate.native_id.replace("/", "-")


def federal_cursor(candidate: Candidate) -> str | None:
    """The federal change cursor (updateDateIncludingText-preferred; see congress.py:369)."""
    return candidate.update_date


def state_key(candidate: Candidate) -> str:
    """The LegiScan bill_id (the candidate's native_id) — the state ledger key."""
    return candidate.native_id


def state_cursor(candidate: Candidate) -> str | None:
    """The LegiScan change_hash carried on the search-result candidate (raw['change_hash'])."""
    value = candidate.raw.get("change_hash")
    return value if isinstance(value, str) else None
