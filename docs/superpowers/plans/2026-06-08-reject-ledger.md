# Reject Ledger (negative classification cache) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist a committed, cursor-invalidated cache of classified-out (rejected) federal and state bills so `--skip-existing` sweeps skip them until the bill changes, eliminating the dominant re-classification cost of back-catalog backfills.

**Architecture:** A new `pipeline/rejects.py` module owns the ledger (a `RejectEntry` model, JSON load/write, a cursor-aware `filter_cached_rejects`, a plain `filter_by_key`, and per-source key/cursor adapters + Bill→entry derivation). A new `record-rejects` CLI command writes the ledger (mirrors `render-classified`); the federal `fetch-candidates` and state `fetch-state-candidates` commands consult it inside `--skip-existing` (mirrors `filter_unseen`). Two committed JSON files: `wiki/.rejects/federal.json` (keyed by bill-slug, cursor = Congress `updateDateIncludingText`) and `wiki/.rejects/state.json` (keyed by LegiScan `bill_id`, cursor = `change_hash`).

**Tech Stack:** Python 3.12, pydantic v2, typer, pytest + respx, pyright --strict, ruff. Run everything with `uv run`.

**Spec:** `docs/superpowers/specs/2026-06-08-reject-ledger-design.md`. **Branch:** `feature/reject-ledger` (already created off the D81 tip).

**Invariants for every task:** keep `uv run pyright` clean (--strict), `uv run ruff check` clean, and the full `uv run pytest` suite green (785 baseline). Use `uv run` for all commands. Line length ≤ 100 (ruff).

---

### Task 1: Reject ledger model + JSON load/write

**Files:**
- Create: `src/zwiadbrain/pipeline/rejects.py`
- Test: `tests/test_rejects.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rejects.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rejects.py -q`
Expected: FAIL (ModuleNotFoundError: zwiadbrain.pipeline.rejects).

- [ ] **Step 3: Create the module with the model + I/O**

Create `src/zwiadbrain/pipeline/rejects.py`:

```python
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

from pydantic import BaseModel, ValidationError

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.models import Bill
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
    entries: dict[str, object] = raw  # pyright: ignore[reportUnknownVariableType]
    ledger: RejectLedger = {}
    for key, value in entries.items():
        try:
            ledger[str(key)] = RejectEntry.model_validate(value)
        except ValidationError as exc:
            raise ConfigError(f"reject ledger {path} entry {key!r} invalid: {exc}") from exc
    return ledger


def write_reject_ledger(path: Path, ledger: RejectLedger) -> None:
    """Write the ledger as sorted-key JSON so an unchanged re-record is byte-identical (D20)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    obj = {key: ledger[key].model_dump(exclude_none=True) for key in sorted(ledger)}
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rejects.py -q`
Expected: PASS (6 tests). If pyright flags the `entries` assignment, keep the `# pyright: ignore[reportUnknownVariableType]` comment.

- [ ] **Step 5: Lint + type-check**

Run: `uv run ruff check src/zwiadbrain/pipeline/rejects.py tests/test_rejects.py` and `uv run pyright src/zwiadbrain/pipeline/rejects.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/zwiadbrain/pipeline/rejects.py tests/test_rejects.py
git commit -m "feat(rejects): reject-ledger model with byte-stable JSON load/write"
```

---

### Task 2: Cursor-aware filter + `filter_by_key` + source adapters

**Files:**
- Modify: `src/zwiadbrain/pipeline/rejects.py` (append)
- Test: `tests/test_rejects.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rejects.py` (add the imports to the existing `from zwiadbrain.pipeline.rejects import (...)` block: `federal_cursor, federal_key, filter_by_key, filter_cached_rejects, state_cursor, state_key`):

```python
from zwiadbrain.sources.base import Candidate


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rejects.py -q`
Expected: FAIL (ImportError: cannot import name 'filter_cached_rejects').

- [ ] **Step 3: Append the filters + adapters to `rejects.py`**

Append to `src/zwiadbrain/pipeline/rejects.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rejects.py -q`
Expected: PASS (14 tests total).

- [ ] **Step 5: Lint + type-check, then commit**

Run: `uv run ruff check src/zwiadbrain/pipeline/rejects.py tests/test_rejects.py` and `uv run pyright src/zwiadbrain/pipeline/rejects.py`

```bash
git add src/zwiadbrain/pipeline/rejects.py tests/test_rejects.py
git commit -m "feat(rejects): cursor-aware filter, filter_by_key, source adapters"
```

---

### Task 3: Bill→entry derivation (record side)

**Files:**
- Modify: `src/zwiadbrain/pipeline/rejects.py` (append)
- Test: `tests/test_rejects.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rejects.py` (add `federal_bill_entry, state_bill_entry` to the rejects import block; add `from zwiadbrain.models import Bill`):

```python
def test_federal_bill_entry_prefers_text_inclusive_cursor() -> None:
    """should record update_date_text so the cursor matches the candidate's update_date"""
    bill = Bill(
        id="119-hr-1", jurisdiction="US", title="t", bill_number="H.R. 1",
        update_date="2026-01-01", update_date_text="2026-02-02",
    )
    key, entry = federal_bill_entry(bill)
    assert key == "119-hr-1"
    assert entry.cursor == "2026-02-02"
    assert entry.id is None


def test_federal_bill_entry_falls_back_to_bare_update_date() -> None:
    """should fall back to update_date when update_date_text is absent"""
    bill = Bill(
        id="119-hr-1", jurisdiction="US", title="t", bill_number="H.R. 1",
        update_date="2026-01-01",
    )
    _key, entry = federal_bill_entry(bill)
    assert entry.cursor == "2026-01-01"


def test_state_bill_entry_keys_by_legiscan_id_and_keeps_slug() -> None:
    """should key a state reject by LegiScan bill_id and keep the page slug as id"""
    bill = Bill(
        id="ca-2025-ab-7", jurisdiction="US-CA", title="t", bill_number="AB 7",
        legiscan_bill_id=999, change_hash="h9",
    )
    key, entry = state_bill_entry(bill)
    assert key == "999"
    assert entry.cursor == "h9"
    assert entry.id == "ca-2025-ab-7"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rejects.py -k bill_entry -q`
Expected: FAIL (ImportError: federal_bill_entry).

- [ ] **Step 3: Append the derivation helpers**

Append to `src/zwiadbrain/pipeline/rejects.py`:

```python
def federal_bill_entry(bill: Bill) -> tuple[str, RejectEntry]:
    """(slug, entry) for a federal reject; cursor matches `federal_cursor` (text-inclusive)."""
    cursor = bill.update_date_text or bill.update_date or ""
    return bill.id, RejectEntry(cursor=cursor)


def state_bill_entry(bill: Bill) -> tuple[str, RejectEntry]:
    """(bill_id, entry) for a state reject; keeps the page slug as a human anchor."""
    return str(bill.legiscan_bill_id), RejectEntry(cursor=bill.change_hash or "", id=bill.id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rejects.py -q`
Expected: PASS (17 tests total).

- [ ] **Step 5: Lint + type-check, then commit**

Run: `uv run ruff check src/zwiadbrain/pipeline/rejects.py tests/test_rejects.py` and `uv run pyright src/zwiadbrain/pipeline/rejects.py`

```bash
git add src/zwiadbrain/pipeline/rejects.py tests/test_rejects.py
git commit -m "feat(rejects): derive ledger entries from out-of-scope bills"
```

---

### Task 4: `record-rejects` CLI command

**Files:**
- Modify: `src/zwiadbrain/cli.py` (add import + new command)
- Test: `tests/test_cli.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_record_rejects_federal_writes_ledger(tmp_path: Path) -> None:
    """should derive the federal cursor and upsert the bill into federal.json"""
    rejects = tmp_path / "rejects.json"
    rejects.write_text(
        json.dumps([
            {
                "id": "119-hr-9", "jurisdiction": "US", "title": "Boring",
                "bill_number": "H.R. 9", "update_date": "2026-01-01",
                "update_date_text": "2026-02-02",
            }
        ]),
        encoding="utf-8",
    )
    cache = tmp_path / ".rejects"
    result = runner.invoke(
        app,
        ["record-rejects", "--in", str(rejects), "--scope", "federal",
         "--cache-dir", str(cache)],
    )
    assert result.exit_code == 0, result.output
    led = json.loads((cache / "federal.json").read_text(encoding="utf-8"))
    assert led == {"119-hr-9": {"cursor": "2026-02-02"}}


def test_record_rejects_is_idempotent_byte_identical(tmp_path: Path) -> None:
    """should produce a byte-identical ledger when the same reject is recorded twice"""
    rejects = tmp_path / "rejects.json"
    rejects.write_text(
        json.dumps([
            {"id": "119-hr-9", "jurisdiction": "US", "title": "B",
             "bill_number": "H.R. 9", "update_date": "2026-01-01"}
        ]),
        encoding="utf-8",
    )
    cache = tmp_path / ".rejects"
    args = ["record-rejects", "--in", str(rejects), "--scope", "federal",
            "--cache-dir", str(cache)]
    runner.invoke(app, args)
    first = (cache / "federal.json").read_bytes()
    runner.invoke(app, args)
    assert (cache / "federal.json").read_bytes() == first


def test_record_rejects_rejects_unknown_scope(tmp_path: Path) -> None:
    """should exit non-zero on an invalid --scope"""
    rejects = tmp_path / "r.json"
    rejects.write_text("[]", encoding="utf-8")
    result = runner.invoke(
        app,
        ["record-rejects", "--in", str(rejects), "--scope", "county",
         "--cache-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "scope" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k record_rejects -q`
Expected: FAIL (no such command 'record-rejects' → non-zero / usage error).

- [ ] **Step 3: Add the import and the command to `cli.py`**

Add to the imports of `src/zwiadbrain/cli.py` (alphabetical within the pipeline group, after the `lawbrain_*` imports and before `render`):

```python
from zwiadbrain.pipeline.rejects import (
    federal_bill_entry,
    federal_cursor,
    federal_key,
    filter_by_key,
    filter_cached_rejects,
    load_reject_ledger,
    state_bill_entry,
    state_cursor,
    state_key,
    write_reject_ledger,
)
```

Add the command (place it directly after `render_classified`, around line 319):

```python
@app.command(name="record-rejects")
def record_rejects(
    input_file: Annotated[Path, typer.Option("--in", help="Out-of-scope bills JSON (Bill list).")],
    scope: Annotated[str, typer.Option(help="federal or state.")],
    cache_dir: Annotated[
        Path, typer.Option(help="Reject-ledger directory.")
    ] = Path("wiki/.rejects"),
) -> None:
    """Record classified-out bills into the committed reject ledger (the negative cache).

    The write half that pairs with ``--skip-existing``: the interactive session hands back the
    OUT-of-scope ``Bill``s; this derives each one's change cursor and upserts it into
    ``<cache_dir>/<scope>.json`` so a future sweep skips it until the bill changes (D82).
    """
    try:
        if scope not in {"federal", "state"}:
            raise ConfigError(f"--scope must be 'federal' or 'state', got {scope!r}")
        try:
            raw: object = json.loads(input_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"could not read rejects file {input_file}: {exc}") from exc
        if not isinstance(raw, list):
            raise ConfigError(f"rejects file must be a JSON list, got {type(raw).__name__}")
        items: list[object] = list(raw)  # pyright: ignore[reportUnknownArgumentType]
        bills = [validate_model(Bill, item, label="reject bill") for item in items]
        entry_of = federal_bill_entry if scope == "federal" else state_bill_entry
        path = cache_dir / f"{scope}.json"
        ledger = load_reject_ledger(path)
        new = updated = 0
        for bill in bills:
            key, entry = entry_of(bill)
            if key in ledger:
                updated += 1
            else:
                new += 1
            ledger[key] = entry
        write_reject_ledger(path, ledger)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"recorded {new} new, {updated} updated reject(s) to {path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k record_rejects -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + type-check, then commit**

Run: `uv run ruff check src/zwiadbrain/cli.py tests/test_cli.py` and `uv run pyright src/zwiadbrain/cli.py`

```bash
git add src/zwiadbrain/cli.py tests/test_cli.py
git commit -m "feat(cli): record-rejects command writes the reject ledger"
```

---

### Task 5: Wire the federal `fetch-candidates --skip-existing` to consult the ledger

**Files:**
- Modify: `src/zwiadbrain/cli.py` (the `skip_existing` branch of `fetch_candidates`, ~lines 259-266)
- Test: `tests/test_cli.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py` (ensure `from zwiadbrain.sources.base import Candidate` and `from zwiadbrain.pipeline.rejects import RejectEntry, write_reject_ledger` are imported at the top; add them if missing):

```python
def test_fetch_candidates_skip_existing_drops_cached_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should drop a federal candidate cached as a reject whose cursor is unchanged (D82)"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    wiki = tmp_path / "wiki"
    write_reject_ledger(
        wiki / ".rejects" / "federal.json",
        {"119-hr-9": RejectEntry(cursor="2026-01-01")},
    )

    def _fake_discover(
        self: CongressSource, *, congress: int | None = None,
        since: object = None, limit: int = 20, max_pages: int = 1,
    ) -> list[Candidate]:
        return [
            Candidate(
                source="congress", native_id="119/hr/9", jurisdiction="US",
                title="Boring Act", update_date="2026-01-01",
            )
        ]

    monkeypatch.setattr(CongressSource, "discover", _fake_discover)
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        ["fetch-candidates", "--congress", "119", "--limit", "5", "--seed", "boring",
         "--skip-existing", "--wiki", str(wiki), "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert json.loads((out / "candidates.json").read_text(encoding="utf-8")) == []
    assert "cached-reject" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_fetch_candidates_skip_existing_drops_cached_rejects -q`
Expected: FAIL — the candidate is staged (not dropped) and "cached-reject" is absent from output.

- [ ] **Step 3: Update the `skip_existing` branch**

In `src/zwiadbrain/cli.py`, replace the existing `if skip_existing:` block inside `fetch_candidates` (currently filters only `filter_unseen`) with:

```python
        if skip_existing:
            known = _existing_federal_bill_ids(wiki)
            ledger = load_reject_ledger(wiki / ".rejects" / "federal.json")
            before = len(scanned)
            scanned = filter_unseen(scanned, known)
            after_unseen = len(scanned)
            scanned = filter_cached_rejects(
                scanned, ledger, key_of=federal_key, cursor_of=federal_cursor
            )
            typer.echo(
                f"skip-existing: dropped {before - after_unseen} already-tracked"
                f" + {after_unseen - len(scanned)} cached-reject of {before} scanned"
                f" ({len(known)} on wiki, {len(ledger)} rejects)"
            )
```

- [ ] **Step 4: Run the test (and the existing skip-existing test) to verify they pass**

Run: `uv run pytest tests/test_cli.py -k "skip_existing" -q`
Expected: PASS (both `_drops_already_tracked_bills` and `_drops_cached_rejects`).

- [ ] **Step 5: Lint + type-check, then commit**

Run: `uv run ruff check src/zwiadbrain/cli.py tests/test_cli.py` and `uv run pyright src/zwiadbrain/cli.py`

```bash
git add src/zwiadbrain/cli.py tests/test_cli.py
git commit -m "feat(cli): federal fetch --skip-existing skips cached rejects"
```

---

### Task 6: Add `--skip-existing` to state `fetch-state-candidates`

**Files:**
- Modify: `src/zwiadbrain/cli.py` (`fetch_state_candidates` + new `_existing_state_bill_ids` helper + a `_STATE_OVERSAMPLE` constant + `from_page` import)
- Test: `tests/test_cli.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py` (ensure `from zwiadbrain.sources.legiscan import LegiScanSource` is imported; the module already imports `LEGISCAN_API_BASE`):

```python
def test_existing_state_bill_ids_reads_legiscan_id_from_frontmatter(tmp_path: Path) -> None:
    """should harvest tracked state bills' LegiScan ids from frontmatter, skipping sidecars"""
    from zwiadbrain.cli import _existing_state_bill_ids

    wiki = tmp_path / "wiki"
    write_page(
        Bill(
            id="ca-2025-ab-7", jurisdiction="US-CA", title="t",
            bill_number="AB 7", legiscan_bill_id=777,
        ),
        wiki,
    )
    (wiki / "states" / "ca" / "bills" / "ca-2025-ab-7.text.md").write_text(
        "sidecar", encoding="utf-8"
    )
    assert _existing_state_bill_ids(wiki, "ca") == {"777"}


def test_existing_state_bill_ids_missing_dir_is_empty(tmp_path: Path) -> None:
    """should return an empty set when the state has no bills directory yet"""
    from zwiadbrain.cli import _existing_state_bill_ids

    assert _existing_state_bill_ids(tmp_path / "wiki", "ny") == set()


def test_fetch_state_candidates_skip_existing_drops_cached_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should drop a state candidate whose LegiScan change_hash is cached as a reject (D82)"""
    monkeypatch.setenv("LEGISCAN_API_KEY", "lk-test")
    wiki = tmp_path / "wiki"
    write_reject_ledger(
        wiki / ".rejects" / "state.json",
        {"777": RejectEntry(cursor="hash-1", id="ca-2025-ab-7")},
    )

    def _fake_discover(
        self: LegiScanSource, *, congress: int | None = None,
        since: object = None, limit: int = 20, max_pages: int = 1,
    ) -> list[Candidate]:
        return [
            Candidate(
                source="legiscan", native_id="777", jurisdiction="US-CA",
                title="", raw={"change_hash": "hash-1"},
            )
        ]

    monkeypatch.setattr(LegiScanSource, "discover", _fake_discover)
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        ["fetch-state-candidates", "--state", "ca", "--limit", "5", "--query", "privacy",
         "--skip-existing", "--wiki", str(wiki), "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert json.loads((out / "candidates.json").read_text(encoding="utf-8")) == []
    assert "cached-reject" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "state_bill_ids or state_candidates_skip_existing" -q`
Expected: FAIL (`_existing_state_bill_ids` missing; `--skip-existing` is an unknown option for the state command).

- [ ] **Step 3: Add the `from_page` import and the constant**

In `src/zwiadbrain/cli.py`, add the import near the other `zwiadbrain.wiki` imports (or after `from zwiadbrain.store import Store`):

```python
from zwiadbrain.wiki.schema import from_page
```

Add a module constant next to `_SCAN_LIMIT` / `_MAX_PROBE`:

```python
_STATE_OVERSAMPLE = 5  # over-fetch factor so --skip-existing still yields up to `limit` fresh bills
```

- [ ] **Step 4: Add the `_existing_state_bill_ids` helper**

Add directly below `_existing_federal_bill_ids` in `src/zwiadbrain/cli.py`:

```python
def _existing_state_bill_ids(wiki: Path, state: str) -> set[str]:
    """LegiScan bill ids already tracked under ``wiki/states/<st>/bills`` (--skip-existing).

    State page filenames are slugs (``ca-2025-ab-1064``), not LegiScan ids, so the
    discovery-time key (the LegiScan ``bill_id``) is read from each page's frontmatter via
    :func:`from_page`. ``.text.md`` sidecars are skipped; a missing directory -> empty set.
    """
    bills_dir = wiki / "states" / state / "bills"
    if not bills_dir.exists():
        return set()
    known: set[str] = set()
    for page in bills_dir.glob("*.md"):
        if page.name.endswith(".text.md"):
            continue
        item = from_page(page.read_text(encoding="utf-8"))
        if isinstance(item, Bill) and item.legiscan_bill_id is not None:
            known.add(str(item.legiscan_bill_id))
    return known
```

- [ ] **Step 5: Add the flags + filtering to `fetch_state_candidates`**

Add two options to the `fetch_state_candidates` signature (after `topics`):

```python
    skip_existing: Annotated[
        bool,
        typer.Option(
            "--skip-existing/--no-skip-existing",
            help="Drop already-tracked and cached-reject bills (idempotent re-runs).",
        ),
    ] = False,
    wiki: Annotated[Path, typer.Option(help="Wiki root, for --skip-existing.")] = Path("wiki"),
```

Replace the discover+enrich body (currently `candidates = source.discover(limit=limit)` then the `bills = [...]` line) with:

```python
        api_key = load_settings().require_legiscan_api_key()
        source = LegiScanSource(api_key, state, query=search_query)
        fetch_limit = limit * _STATE_OVERSAMPLE if skip_existing else limit
        candidates = source.discover(limit=fetch_limit)
        if skip_existing:
            known = _existing_state_bill_ids(wiki, state)
            ledger = load_reject_ledger(wiki / ".rejects" / "state.json")
            before = len(candidates)
            candidates = filter_by_key(candidates, known, key_of=state_key)
            after_unseen = len(candidates)
            candidates = filter_cached_rejects(
                candidates, ledger, key_of=state_key, cursor_of=state_cursor
            )
            typer.echo(
                f"skip-existing: dropped {before - after_unseen} already-tracked"
                f" + {after_unseen - len(candidates)} cached-reject of {before} scanned"
                f" ({len(known)} on wiki, {len(ledger)} rejects)"
            )
        candidates = candidates[:limit]
        bills = [enrich(source, candidate) for candidate in candidates]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k "state_bill_ids or state_candidates" -q`
Expected: PASS (the two new helper tests, the new skip-existing test, and the existing `test_fetch_state_candidates_stages_enriched_bills` — which still uses no `--skip-existing`, so `fetch_limit == limit`).

- [ ] **Step 7: Lint + type-check, then commit**

Run: `uv run ruff check src/zwiadbrain/cli.py tests/test_cli.py` and `uv run pyright src/zwiadbrain/cli.py`

```bash
git add src/zwiadbrain/cli.py tests/test_cli.py
git commit -m "feat(cli): state fetch --skip-existing dedups wiki + cached rejects"
```

---

### Task 7: Skill docs + DECISIONS.md (D82)

**Files:**
- Modify: `.claude/commands/zwiad-backfill.md`
- Modify: `.claude/commands/zwiad-scan-states.md`
- Modify: `DECISIONS.md`

- [ ] **Step 1: Update the federal backfill skill**

In `.claude/commands/zwiad-backfill.md`, after step 3 (Classify), insert a new step (renumber the rest):

```markdown
### 3a. Record the rejects (reject ledger — the negative cache)
Collect the OUT-of-scope bills (the ones the classifier dropped). `Write` them — the
**full `Bill` JSON objects**, same shape as `candidates.json` — to a `rejects.json` in the
run directory, then run:
```
uv run zwiadbrain record-rejects --in data/runs/<id>/rejects.json --scope federal
```
This upserts each rejected bill into `wiki/.rejects/federal.json` keyed by bill id and its
Congress `updateDateIncludingText` cursor, so a future `--skip-existing` sweep skips it
until the bill changes (D82). Commit `wiki/.rejects/` alongside the rendered pages.
```

In step 1, append to the note about `--skip-existing`: "`--skip-existing` now also drops
bills already in `wiki/.rejects/federal.json` whose change cursor is unchanged."

- [ ] **Step 2: Update the state scan skill**

In `.claude/commands/zwiad-scan-states.md`, after step 3 (Classify), insert the analogous
step:

```markdown
### 3a. Record the rejects (reject ledger — the negative cache)
`Write` the OUT-of-scope bills (full `Bill` JSON objects) to `rejects.json`, then run:
```
uv run zwiadbrain record-rejects --in data/runs/<id>/rejects.json --scope state
```
This upserts each into `wiki/.rejects/state.json` keyed by LegiScan `bill_id` and its
`change_hash` cursor. Pass `--skip-existing --wiki wiki` to `fetch-state-candidates` on
later runs to skip already-tracked and cached-reject bills (D82). Commit `wiki/.rejects/`.
```

- [ ] **Step 3: Append D82 to DECISIONS.md**

Append to `DECISIONS.md`:

```markdown
## 2026-06-08 — D82: Reject ledger (committed negative classification cache)
**Chosen:** Persist classified-out federal and state bills to committed JSON ledgers
(`wiki/.rejects/federal.json` keyed by bill-slug + Congress `updateDateIncludingText`;
`wiki/.rejects/state.json` keyed by LegiScan `bill_id` + `change_hash`). A new
`record-rejects` CLI writes them; `filter_cached_rejects` (folded into `--skip-existing`)
reads them, dropping a candidate only while its change cursor is unchanged.
**Alternatives:** (B) one unified ledger keyed by `jurisdiction:native_id` — rejected,
buys little once key/cursor extraction stays source-specific. (C) SQLite negative cache —
rejected, gitignored/local contradicts the durability requirement.
**Why:** Back-catalog sweeps (`--max-pages`) re-classified every out-of-scope bill (~13k
plan tokens each); the Stage-0 backfill pilot re-classified 9 rejects on one re-sweep.
Cursor invalidation reuses the refresh "any-change gate", so a bill that later changes is
re-classified rather than hidden forever. Also adds the missing state wiki-dedup.
**Trade-offs:** The ledger grows with rejects (small: ~100 bytes/entry) and must be
committed per batch for `--skip-existing` to see it. No `reason`/timestamp field, to keep
writes byte-stable.
**Revisit if:** ledger size becomes unwieldy, or a source needs a non-cursor invalidation.
```

- [ ] **Step 4: Commit**

```bash
git add .claude/commands/zwiad-backfill.md .claude/commands/zwiad-scan-states.md DECISIONS.md
git commit -m "docs(rejects): document reject ledger in skills + DECISIONS (D82)"
```

---

### Task 8: Full gate + final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS — 785 baseline + the new tests (≈ 785 + 25), 0 failures.

- [ ] **Step 2: Type-check the whole package**

Run: `uv run pyright`
Expected: no new errors versus baseline.

- [ ] **Step 3: Lint the whole tree**

Run: `uv run ruff check`
Expected: no errors.

- [ ] **Step 4: Smoke-test the new command end to end**

Run:
```bash
uv run zwiadbrain record-rejects --in /dev/null --scope federal --cache-dir /tmp/x 2>&1 || true
```
(That should error cleanly on the empty input — confirms the command is wired.) Then confirm
`record-rejects` and the new `--skip-existing` flag appear in help:
```bash
uv run zwiadbrain --help
uv run zwiadbrain fetch-state-candidates --help
```
Expected: `record-rejects` listed; `--skip-existing` shown for the state command.

- [ ] **Step 5: Final confirmation (no extra commit needed if all green)**

If steps 1-3 surfaced any fixes, commit them:
```bash
git add -A
git commit -m "test(rejects): gate fixes after full-suite run"
```

---

## Self-Review

**Spec coverage:**
- Storage (§1) → Tasks 1, 4 (write path), and `wiki/.rejects/<scope>.json` location used in Tasks 5-6. ✓
- Filter read side (§2) → Task 2 (`filter_cached_rejects`, adapters). ✓
- Record write side (§3) → Tasks 3-4 (`record-rejects`, Bill→entry). ✓
- Wiring (§4): federal → Task 5; state `--skip-existing` + over-fetch + `_existing_state_bill_ids` → Task 6. ✓
- Skill + doc updates (§5) → Task 7. ✓
- Testing (§Testing) → unit in Tasks 1-3 (and 6 for the helper), CLI integration in Tasks 4-6, full gate in Task 8. ✓
- Open implementation details resolved: (1) federal cursor = `update_date_text or update_date` to match `Candidate.update_date` (congress.py:369) — Task 3; (2) state over-fetch via `_STATE_OVERSAMPLE` — Task 6; (3) `native_id == str(bill_id)` (legiscan.py:338) — used in Task 2 adapters. ✓

**Placeholder scan:** No TBD/TODO; every code/test step shows complete code and exact commands. ✓

**Type consistency:** `filter_cached_rejects(candidates, ledger, *, key_of, cursor_of)`, `filter_by_key(candidates, known, *, key_of)`, `federal_key`/`federal_cursor`/`state_key`/`state_cursor`, `federal_bill_entry`/`state_bill_entry -> tuple[str, RejectEntry]`, `RejectEntry(cursor, id=None)`, `load_reject_ledger`/`write_reject_ledger` — names and signatures match across Tasks 1-6 and the CLI imports in Task 4. ✓

**Note (Open detail #2 nuance):** `getSearchRaw` is single-page (≤ ~50 results), so `_STATE_OVERSAMPLE` saturates at the page size for very large `--limit`; this is acceptable best-effort and matches the federal `_OVERSAMPLE` philosophy. If deeper state recall is ever needed, paginate `getSearchRaw` in a later change.
