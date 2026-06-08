# Backfill Scaling Gaps 1 + 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make backfill classification and summarization resumable by persisting verdicts and summaries to JSON and adding two CLIs (`apply-verdicts`, `apply-summaries`) that apply them, plus a batch-summarizer subagent.

**Architecture:** A new `pipeline/verdicts.py` holds a `Verdict` pydantic model and two pure functions (`split_by_verdict`, `apply_summaries`) operating on `Bill` objects. Two thin `cli.py` command wrappers parse staging JSON, call the pure functions, and write the standard run-dir files — mirroring how `pipeline/rejects.py` backs `record-rejects`. The existing `render-classified` / `record-rejects` commands are unchanged; this slots in before them. Gap 2's batched round-trip lives in a new `.claude/agents/batch-summarizer.md` plus edits to the two backfill slash commands.

**Tech Stack:** Python 3.12, pydantic, typer, pytest, pyright (strict), ruff. Spec: `docs/superpowers/specs/2026-06-08-backfill-scaling-gaps-design.md`.

---

## File Structure

- **Create** `src/zwiadbrain/pipeline/verdicts.py` — `Verdict` model + `split_by_verdict` + `apply_summaries` (pure logic only; no I/O).
- **Modify** `src/zwiadbrain/cli.py` — import from `verdicts.py`; add private read helpers `_read_json_list` / `_read_summaries`; add `apply-verdicts` and `apply-summaries` commands.
- **Create** `tests/test_verdicts.py` — unit tests for the two pure functions.
- **Modify** `tests/test_cli.py` — CLI tests for both new commands.
- **Create** `.claude/agents/batch-summarizer.md` — batch summarizer subagent (N bills → `{id: summary}`).
- **Modify** `.claude/commands/zwiad-scan-states.md` — rewrite steps 3–6 to the verdicts/summaries flow.
- **Modify** `.claude/commands/zwiad-backfill.md` — same rewrite, federal (`--scope federal`).
- **Modify** `DECISIONS.md` — log the verdict-persistence / two-CLI decision.

---

## Task 1: `Verdict` model + `split_by_verdict`

**Files:**
- Create: `src/zwiadbrain/pipeline/verdicts.py`
- Test: `tests/test_verdicts.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_verdicts.py`:

```python
"""Tests for resumable verdict + summary application (backfill scaling gaps 1+2)."""

import pytest

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.models import Bill
from zwiadbrain.pipeline.verdicts import Verdict, split_by_verdict


def _bill(bill_id: str, *, summary: str | None = None) -> Bill:
    """A minimal state Bill (state jurisdiction avoids the federal id-shape validator)."""
    return Bill(
        id=bill_id, jurisdiction="US-CA", title=f"Bill {bill_id}",
        bill_number=bill_id.upper(), summary=summary,
    )


def test_split_by_verdict_applies_topics_to_in_scope() -> None:
    """should return in-scope candidates with the verdict's topics applied"""
    cands = [_bill("ca-2025-ab-1")]
    verdicts = [Verdict(id="ca-2025-ab-1", in_scope=True, topics=["ai"])]
    classified, rejects, pending = split_by_verdict(cands, verdicts)
    assert [b.id for b in classified] == ["ca-2025-ab-1"]
    assert classified[0].topics == ["ai"]
    assert rejects == []
    assert pending == []


def test_split_by_verdict_routes_out_of_scope_to_rejects() -> None:
    """should route an out-of-scope verdict's candidate to rejects unchanged"""
    cands = [_bill("ca-2025-ab-2")]
    verdicts = [Verdict(id="ca-2025-ab-2", in_scope=False)]
    classified, rejects, pending = split_by_verdict(cands, verdicts)
    assert classified == []
    assert [b.id for b in rejects] == ["ca-2025-ab-2"]
    assert pending == []


def test_split_by_verdict_reports_unclassified_tail_as_pending() -> None:
    """should return a candidate with no verdict as pending (resumable tail), not emit it"""
    cands = [_bill("ca-2025-ab-1"), _bill("ca-2025-ab-2")]
    verdicts = [Verdict(id="ca-2025-ab-1", in_scope=True, topics=["privacy"])]
    classified, rejects, pending = split_by_verdict(cands, verdicts)
    assert [b.id for b in classified] == ["ca-2025-ab-1"]
    assert rejects == []
    assert pending == ["ca-2025-ab-2"]


def test_split_by_verdict_unknown_verdict_id_raises() -> None:
    """should fail loud on a verdict id that matches no candidate (stale/typo guard)"""
    cands = [_bill("ca-2025-ab-1")]
    verdicts = [Verdict(id="ca-2025-ab-99", in_scope=True, topics=["ai"])]
    with pytest.raises(ConfigError):
        split_by_verdict(cands, verdicts)


def test_split_by_verdict_in_scope_without_topics_raises() -> None:
    """should fail loud on an in-scope verdict that carries no topics"""
    cands = [_bill("ca-2025-ab-1")]
    verdicts = [Verdict(id="ca-2025-ab-1", in_scope=True, topics=[])]
    with pytest.raises(ConfigError):
        split_by_verdict(cands, verdicts)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_verdicts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'zwiadbrain.pipeline.verdicts'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/zwiadbrain/pipeline/verdicts.py`:

```python
"""Resumable classification + summary application (backfill scaling gaps 1+2).

Classification verdicts (in/out + topics) and plain-language summaries are produced by
interactive-session subagents and persisted to JSON next to a run's candidates, so a plan
rate-limit or context cutoff only loses the unprocessed *tail*. ``split_by_verdict`` splits
candidates into in-scope (topics applied) + rejects from a verdict list; ``apply_summaries``
merges a ``{id: summary}`` map into the classified bills. The pure logic lives here; the CLI
wrappers (``apply-verdicts`` / ``apply-summaries``) live in ``cli.py`` — mirroring how
``rejects.py`` backs ``record-rejects``. See
docs/superpowers/specs/2026-06-08-backfill-scaling-gaps-design.md.
"""

from __future__ import annotations

from pydantic import BaseModel

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.models import Bill


class Verdict(BaseModel):
    """One classifier verdict for a candidate bill (a transient staging artifact).

    ``reason`` keeps the classifier's rationale for the audit trail; it is not persisted
    to the wiki page (only ``topics`` and, later, the summary land on the ``Bill``).
    """

    id: str
    in_scope: bool
    topics: list[str] = []
    reason: str = ""


def split_by_verdict(
    candidates: list[Bill], verdicts: list[Verdict]
) -> tuple[list[Bill], list[Bill], list[str]]:
    """Split *candidates* into ``(classified, rejects, pending_ids)`` by their verdict.

    An in-scope verdict yields the candidate with ``topics`` applied; an out-of-scope verdict
    yields it unchanged into ``rejects``; a candidate with no verdict has its id returned in
    ``pending_ids`` (the unclassified tail — not emitted, not an error, so a rerun resumes).
    A verdict whose id matches no candidate, or an in-scope verdict with no topics, is a
    :class:`ConfigError` (a stale/typo verdict, or a classified-in bill missing its topic).
    Order is preserved.
    """
    by_id = {bill.id: bill for bill in candidates}
    verdict_by_id: dict[str, Verdict] = {}
    for verdict in verdicts:
        if verdict.id not in by_id:
            raise ConfigError(f"verdict id {verdict.id!r} matches no candidate")
        if verdict.in_scope and not verdict.topics:
            raise ConfigError(f"in-scope verdict {verdict.id!r} has no topics")
        verdict_by_id[verdict.id] = verdict
    classified: list[Bill] = []
    rejects: list[Bill] = []
    pending: list[str] = []
    for bill in candidates:
        verdict = verdict_by_id.get(bill.id)
        if verdict is None:
            pending.append(bill.id)
        elif verdict.in_scope:
            classified.append(bill.model_copy(update={"topics": verdict.topics}))
        else:
            rejects.append(bill)
    return classified, rejects, pending
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_verdicts.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/pipeline/verdicts.py tests/test_verdicts.py
git commit -m "feat(backfill): Verdict model + split_by_verdict (resumable classification)"
```

---

## Task 2: `apply_summaries`

**Files:**
- Modify: `src/zwiadbrain/pipeline/verdicts.py`
- Test: `tests/test_verdicts.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_verdicts.py` (and add `apply_summaries` to the existing import line so it reads `from zwiadbrain.pipeline.verdicts import Verdict, apply_summaries, split_by_verdict`):

```python
def test_apply_summaries_sets_summary_prose() -> None:
    """should replace each classified bill's summary from the {id: summary} map"""
    classified = [_bill("ca-2025-ab-1", summary="raw")]
    updated, pending = apply_summaries(classified, {"ca-2025-ab-1": "plain language"})
    assert updated[0].summary == "plain language"
    assert pending == []


def test_apply_summaries_reports_unsummarized_tail() -> None:
    """should return a classified bill with no summary entry as pending"""
    classified = [_bill("ca-2025-ab-1"), _bill("ca-2025-ab-2")]
    updated, pending = apply_summaries(classified, {"ca-2025-ab-1": "done"})
    assert updated[0].summary == "done"
    assert pending == ["ca-2025-ab-2"]


def test_apply_summaries_unknown_id_raises() -> None:
    """should fail loud on a summary id that matches no classified bill"""
    classified = [_bill("ca-2025-ab-1")]
    with pytest.raises(ConfigError):
        apply_summaries(classified, {"ca-2025-ab-99": "x"})


def test_apply_summaries_is_idempotent() -> None:
    """should be a stable no-op when re-applied with the same map (D20)"""
    classified = [_bill("ca-2025-ab-1")]
    once, _ = apply_summaries(classified, {"ca-2025-ab-1": "s"})
    twice, pending = apply_summaries(once, {"ca-2025-ab-1": "s"})
    assert twice[0].summary == "s"
    assert pending == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_verdicts.py -k apply_summaries -v`
Expected: FAIL with `ImportError: cannot import name 'apply_summaries'`.

- [ ] **Step 3: Add the implementation**

Append to `src/zwiadbrain/pipeline/verdicts.py`:

```python
def apply_summaries(
    classified: list[Bill], summaries: dict[str, str]
) -> tuple[list[Bill], list[str]]:
    """Set each classified bill's ``summary`` from *summaries*; report the un-summarized tail.

    A bill with an entry in *summaries* gets its ``summary`` replaced; a bill with no entry has
    its id returned in ``pending_ids``. A summary key matching no classified bill is a
    :class:`ConfigError` (stale/typo). Order is preserved; every bill is returned (summarized
    or not), so re-applying the same map is a stable no-op (D20).
    """
    by_id = {bill.id for bill in classified}
    for key in summaries:
        if key not in by_id:
            raise ConfigError(f"summary id {key!r} matches no classified bill")
    updated: list[Bill] = []
    pending: list[str] = []
    for bill in classified:
        summary = summaries.get(bill.id)
        if summary is None:
            pending.append(bill.id)
            updated.append(bill)
        else:
            updated.append(bill.model_copy(update={"summary": summary}))
    return updated, pending
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_verdicts.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/pipeline/verdicts.py tests/test_verdicts.py
git commit -m "feat(backfill): apply_summaries — merge {id: summary} map onto classified bills"
```

---

## Task 3: `apply-verdicts` CLI command

**Files:**
- Modify: `src/zwiadbrain/cli.py` (import block ~line 91–106; add helpers + command)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_cli.py` (`Bill`, `json`, `Path`, `runner`, `app` are already imported there):

```python
def _write_candidates(run: Path, bills: list[Bill]) -> Path:
    run.mkdir(parents=True, exist_ok=True)
    path = run / "candidates.json"
    path.write_text(
        json.dumps([b.model_dump(mode="json") for b in bills]), encoding="utf-8"
    )
    return path


def test_apply_verdicts_splits_candidates_into_classified_and_rejects(tmp_path: Path) -> None:
    """should write classified.json (topics applied) + rejects.json from verdicts.json"""
    run = tmp_path / "run"
    cands = _write_candidates(run, [
        Bill(id="ca-2025-ab-1", jurisdiction="US-CA", title="A", bill_number="AB 1"),
        Bill(id="ca-2025-ab-2", jurisdiction="US-CA", title="B", bill_number="AB 2"),
    ])
    (run / "verdicts.json").write_text(
        json.dumps([
            {"id": "ca-2025-ab-1", "in_scope": True, "topics": ["ai"], "reason": "r"},
            {"id": "ca-2025-ab-2", "in_scope": False, "topics": [], "reason": "out"},
        ]),
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["apply-verdicts", "--in", str(cands), "--verdicts", str(run / "verdicts.json")]
    )
    assert result.exit_code == 0, result.output
    classified = json.loads((run / "classified.json").read_text(encoding="utf-8"))
    rejects = json.loads((run / "rejects.json").read_text(encoding="utf-8"))
    assert [b["id"] for b in classified] == ["ca-2025-ab-1"]
    assert classified[0]["topics"] == ["ai"]
    assert [b["id"] for b in rejects] == ["ca-2025-ab-2"]


def test_apply_verdicts_reports_pending_tail(tmp_path: Path) -> None:
    """should report candidates with no verdict as pending and still exit 0"""
    run = tmp_path / "run"
    cands = _write_candidates(run, [
        Bill(id="ca-2025-ab-1", jurisdiction="US-CA", title="A", bill_number="AB 1"),
        Bill(id="ca-2025-ab-2", jurisdiction="US-CA", title="B", bill_number="AB 2"),
    ])
    (run / "verdicts.json").write_text(
        json.dumps([{"id": "ca-2025-ab-1", "in_scope": True, "topics": ["ai"]}]),
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["apply-verdicts", "--in", str(cands), "--verdicts", str(run / "verdicts.json")]
    )
    assert result.exit_code == 0, result.output
    assert "1 pending" in result.output
    assert "ca-2025-ab-2" in result.output


def test_apply_verdicts_unknown_verdict_id_errors(tmp_path: Path) -> None:
    """should exit non-zero when a verdict id matches no candidate"""
    run = tmp_path / "run"
    cands = _write_candidates(
        run, [Bill(id="ca-2025-ab-1", jurisdiction="US-CA", title="A", bill_number="AB 1")]
    )
    (run / "verdicts.json").write_text(
        json.dumps([{"id": "ca-2025-zz-9", "in_scope": True, "topics": ["ai"]}]),
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["apply-verdicts", "--in", str(cands), "--verdicts", str(run / "verdicts.json")]
    )
    assert result.exit_code == 1
    assert "error" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k apply_verdicts -v`
Expected: FAIL — typer exits 2 ("No such command 'apply-verdicts'"), so the `exit_code == 0` assertions fail.

- [ ] **Step 3: Add the import**

In `src/zwiadbrain/cli.py`, add this import next to the other `zwiadbrain.pipeline.*` imports (immediately after the `from zwiadbrain.pipeline.staging import stage_json, validate_model` line):

```python
from zwiadbrain.pipeline.verdicts import Verdict, apply_summaries, split_by_verdict
```

- [ ] **Step 4: Add the shared read helpers**

In `src/zwiadbrain/cli.py`, add these module-level helpers just above the `@app.command(name="apply-verdicts")` you will add in Step 5 (place the whole block right after the existing `record-rejects` command, before `fetch-state-candidates`):

```python
def _read_json_list(path: Path, *, label: str) -> list[object]:
    """Read a JSON-list staging file (candidates/verdicts) or raise a labelled ConfigError."""
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"could not read {label} {path}: {exc}") from exc
    if not isinstance(raw, list):
        raise ConfigError(f"{label} must be a JSON list, got {type(raw).__name__}")
    return list(raw)  # pyright: ignore[reportUnknownArgumentType]


def _read_summaries(path: Path) -> dict[str, str]:
    """Read a summaries.json ``{id: summary}`` object; non-object/non-str-value -> ConfigError."""
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"could not read summaries file {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"summaries file must be a JSON object, got {type(raw).__name__}")
    raw_dict: dict[str, object] = raw  # pyright: ignore[reportUnknownVariableType]
    result: dict[str, str] = {}
    for key, value in raw_dict.items():  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(value, str):
            raise ConfigError(
                f"summary for {str(key)!r} must be a string, got {type(value).__name__}"
            )
        result[str(key)] = value
    return result
```

- [ ] **Step 5: Add the `apply-verdicts` command**

In `src/zwiadbrain/cli.py`, add this command immediately after the helpers from Step 4:

```python
@app.command(name="apply-verdicts")
def apply_verdicts(
    input_file: Annotated[Path, typer.Option("--in", help="candidates.json to split.")],
    verdicts_file: Annotated[
        Path, typer.Option("--verdicts", help="verdicts.json from the classifier.")
    ],
    out: Annotated[
        Path | None,
        typer.Option(help="Output dir for classified.json + rejects.json (default: --in's dir)."),
    ] = None,
) -> None:
    """Split staged candidates into classified (in-scope, topics applied) + rejects.

    The resumable classification step (backfill gap 1): the classifier subagent writes
    verdicts.json (``[{id, in_scope, topics, reason}]``); this applies them so a rate-limit or
    context cutoff only loses the unclassified tail (reported as 'pending'). Replaces the
    ad-hoc ``data/runs/build_*.py`` scripts.
    """
    try:
        candidates = [
            validate_model(Bill, item, label="candidate bill")
            for item in _read_json_list(input_file, label="candidates file")
        ]
        verdicts = [
            validate_model(Verdict, item, label="verdict")
            for item in _read_json_list(verdicts_file, label="verdicts file")
        ]
        classified, rejects, pending = split_by_verdict(candidates, verdicts)
        out_dir = out or input_file.parent
        classified_path = stage_json(
            [b.model_dump(mode="json") for b in classified],
            name="classified.json",
            out=out_dir,
        )
        stage_json(
            [b.model_dump(mode="json") for b in rejects], name="rejects.json", out=out_dir
        )
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"applied {len(verdicts)} verdict(s): {len(classified)} in-scope,"
        f" {len(rejects)} reject(s), {len(pending)} pending -> {classified_path.parent}"
    )
    if pending:
        typer.echo(f"  pending (unclassified): {', '.join(pending)}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k apply_verdicts -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add src/zwiadbrain/cli.py tests/test_cli.py
git commit -m "feat(backfill): apply-verdicts CLI — split candidates by classifier verdict"
```

---

## Task 4: `apply-summaries` CLI command

**Files:**
- Modify: `src/zwiadbrain/cli.py` (add command after `apply-verdicts`)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_cli.py`:

```python
def test_apply_summaries_merges_map_in_place(tmp_path: Path) -> None:
    """should set each classified bill's summary from summaries.json, rewriting it in place"""
    run = tmp_path / "run"
    run.mkdir()
    cpath = run / "classified.json"
    cpath.write_text(
        json.dumps([
            Bill(
                id="ca-2025-ab-1", jurisdiction="US-CA", title="A",
                bill_number="AB 1", topics=["ai"],
            ).model_dump(mode="json")
        ]),
        encoding="utf-8",
    )
    (run / "summaries.json").write_text(
        json.dumps({"ca-2025-ab-1": "Plain-language summary."}), encoding="utf-8"
    )
    result = runner.invoke(
        app, ["apply-summaries", "--in", str(cpath), "--summaries", str(run / "summaries.json")]
    )
    assert result.exit_code == 0, result.output
    out = json.loads(cpath.read_text(encoding="utf-8"))
    assert out[0]["summary"] == "Plain-language summary."


def test_apply_summaries_reports_pending(tmp_path: Path) -> None:
    """should report classified bills with no summary entry as pending"""
    run = tmp_path / "run"
    run.mkdir()
    cpath = run / "classified.json"
    cpath.write_text(
        json.dumps([
            Bill(id="ca-2025-ab-1", jurisdiction="US-CA", title="A",
                 bill_number="AB 1", topics=["ai"]).model_dump(mode="json"),
            Bill(id="ca-2025-ab-2", jurisdiction="US-CA", title="B",
                 bill_number="AB 2", topics=["ai"]).model_dump(mode="json"),
        ]),
        encoding="utf-8",
    )
    (run / "summaries.json").write_text(json.dumps({"ca-2025-ab-1": "Done."}), encoding="utf-8")
    result = runner.invoke(
        app, ["apply-summaries", "--in", str(cpath), "--summaries", str(run / "summaries.json")]
    )
    assert result.exit_code == 0, result.output
    assert "1 pending" in result.output
    assert "ca-2025-ab-2" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k apply_summaries -v`
Expected: FAIL — typer exits 2 ("No such command 'apply-summaries'").

- [ ] **Step 3: Add the `apply-summaries` command**

In `src/zwiadbrain/cli.py`, add this command immediately after `apply-verdicts`. Note the function is named `apply_summaries_cmd` to avoid shadowing the imported `apply_summaries` pure function:

```python
@app.command(name="apply-summaries")
def apply_summaries_cmd(
    input_file: Annotated[Path, typer.Option("--in", help="classified.json to enrich in place.")],
    summaries_file: Annotated[
        Path, typer.Option("--summaries", help="summaries.json {id: summary} map.")
    ],
) -> None:
    """Merge a ``{id: summary}`` map into the classified bills, in place (backfill gap 2).

    The leaner summary handoff: a batch-summarizer subagent writes summaries.json; this sets
    each in-scope bill's plain-language summary, so a cutoff only loses the un-summarized tail
    (reported as 'pending'). render-classified then renders unchanged.
    """
    try:
        classified = [
            validate_model(Bill, item, label="classified bill")
            for item in _read_json_list(input_file, label="classified file")
        ]
        summaries = _read_summaries(summaries_file)
        updated, pending = apply_summaries(classified, summaries)
        stage_json(
            [b.model_dump(mode="json") for b in updated],
            name=input_file.name,
            out=input_file.parent,
        )
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"applied {len(summaries)} summary(ies): {len(updated) - len(pending)} set,"
        f" {len(pending)} pending"
    )
    if pending:
        typer.echo(f"  pending (un-summarized): {', '.join(pending)}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k apply_summaries -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/cli.py tests/test_cli.py
git commit -m "feat(backfill): apply-summaries CLI — merge batch summaries into classified.json"
```

---

## Task 5: Full gate — tests, pyright, ruff

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest`
Expected: PASS — all prior tests plus the 9 in `test_verdicts.py` and the 5 new in `test_cli.py`. No failures.

- [ ] **Step 2: Run the type checker**

Run: `uv run pyright`
Expected: 0 errors, 0 warnings. If a JSON-traversal `reportUnknown*` surfaces in `_read_summaries`, confirm the inline `# pyright: ignore[...]` comments from Task 3 Step 4 are present and correctly placed.

- [ ] **Step 3: Run the linter**

Run: `uv run ruff check .`
Expected: "All checks passed!". Fix any line-length (E501) or import-order issues ruff reports, then re-run.

- [ ] **Step 4: Commit any gate fixes**

Only if Steps 2–3 required edits:

```bash
git add -A
git commit -m "chore(backfill): pyright/ruff clean-up for verdict + summary CLIs"
```

---

## Task 6: Batch-summarizer subagent + slash-command rewrites

**Files:**
- Create: `.claude/agents/batch-summarizer.md`
- Modify: `.claude/commands/zwiad-scan-states.md` (steps 3–6 + the D49 intro note)
- Modify: `.claude/commands/zwiad-backfill.md` (steps 3–6)

- [ ] **Step 1: Create the batch-summarizer subagent**

Create `.claude/agents/batch-summarizer.md`:

```markdown
---
name: batch-summarizer
description: Writes plain-language summaries for a batch of in-scope U.S. bills in one pass, returning an {id: summary} JSON map. Use for dense backfill runs to cut per-bill round-trips.
tools: Read
model: sonnet
---

# ZwiadBrain Batch Bill Summarizer

You write the plain-language **Summary** prose for SEVERAL tracked bills at once, returning
one JSON object mapping each bill's id to its summary. This is the batched form of the
single-bill `summarizer`, used by dense backfill runs (state batches run ~90% in-scope) to
cut N per-bill round-trips down to one.

## Input

The prompt gives you a JSON list of bills, each with `id`, `title`, official `summary`
(CRS/LegiScan-style), `status`, sponsor(s), and latest action. Everything you need is in the
prompt; you do not fetch anything.

## What to write — for each bill

A tight summary — **2 to 4 sentences** — that answers:
- What does this bill actually do (its operative mechanism)?
- Who/what does it regulate or affect?
- Where does it stand (only if notable, e.g. enacted or passed a chamber)?

Be specific and neutral. Name the obligation, prohibition, agency, or right the bill creates.
Avoid hedging, boilerplate ("This bill would..."), and editorializing. Do not invent details
unsupported by the input. Summarize every bill in the input; do not skip any.

## Output

Respond with ONLY a single JSON object mapping each bill's `id` to its summary string, e.g.:

    {"ca-2025-sb-354": "California's SB 354 overhauls ...", "ca-2025-ab-979": "AB 979 amends ..."}

No preamble, no surrounding code fence, no extra keys, no per-bill headings. The keys must
exactly match the input ids. Do not write files or use tools.
```

- [ ] **Step 2: Rewrite `zwiad-scan-states.md` steps 3–6**

In `.claude/commands/zwiad-scan-states.md`, replace the entire block from the start of `### 3. Classify each bill` through the end of `### 6. Render + index` with:

```markdown
### 3. Classify each bill (subagent: `classifier`) → `verdicts.json`

For every candidate, dispatch the **classifier** subagent with the bill's `title` and
`summary`. It reads `reference/topics.yaml` and returns
`{in_scope, topics, confidence, rationale, positive_criterion, disqualifier_survived, disqualifier_applied}`.
- Log each decision (id, in_scope, confidence, positive_criterion/disqualifier) to the transcript.
- **Validate topics**: if the classifier returns any topic not in `{ai, privacy, cyber}`,
  treat it as a classifier error — record the bill as out-of-scope in the transcript and set
  `in_scope: false` in its verdict (do not enrich it).
- Collect one entry per classified bill into `verdicts.json` —
  `[{ "id", "in_scope", "topics", "reason" }]`, where `reason` is the classifier's rationale —
  and `Write` it to the run directory.

`verdicts.json` is the resumable classification record (backfill gap 1): if a plan rate-limit
or context cutoff interrupts classification, only the *unclassified tail* is lost. Re-run the
classifier on the remaining ids, append their verdicts, and continue.

### 4. Apply verdicts (Python, deterministic)

Run:
```
uv run zwiadbrain apply-verdicts --in data/runs/<id>/candidates.json --verdicts data/runs/<id>/verdicts.json
```
It splits candidates into `classified.json` (in-scope, with `topics` applied) and
`rejects.json` (out-of-scope), and reports any **pending** candidates that have no verdict
yet. If pending > 0, classify those, append to `verdicts.json`, and re-run before continuing.

### 4a. Record the rejects (reject ledger — the negative cache)

Run:
```
uv run zwiadbrain record-rejects --in data/runs/<id>/rejects.json --scope state
```
This upserts each into `wiki/.rejects/state.json` keyed by LegiScan `bill_id` and its
`change_hash` cursor. Pass `--skip-existing --wiki wiki` to `fetch-state-candidates` on later
runs to skip already-tracked and cached-reject bills (D82). Commit `wiki/.rejects/`.

### 5. Summarize the in-scope bills (subagent: `batch-summarizer`) → `summaries.json`

`Read` `classified.json`. Dispatch the **batch-summarizer** subagent ONCE with the full list
of in-scope bills (each bill's `id`, `title`, `summary`, `status`, sponsors, latest action).
It returns a single `{id: summary}` JSON map. `Write` it to `summaries.json`, then run:
```
uv run zwiadbrain apply-summaries --in data/runs/<id>/classified.json --summaries data/runs/<id>/summaries.json
```
This sets each bill's plain-language summary in place, reporting any **pending**
(un-summarized) bills. The single batch dispatch replaces the old one-summarizer-per-bill
round-trip (backfill gap 2); a cutoff loses only the un-summarized tail.

If an in-scope bill has amendments, dispatch the **amendment-explainer** subagent for that
bill and set each amendment's `what_changed` by editing `classified.json` directly. This
touches only the `amendments`, leaving the applied `summary` and `topics` intact (order
relative to `apply-summaries` does not matter — they update disjoint fields).

### 6. Render + index (Python, deterministic)

Run:
```
uv run zwiadbrain render-classified --in data/runs/<id>/classified.json
uv run zwiadbrain reindex
```
`render-classified` validates each bill's `topics` against the taxonomy and writes wiki pages
under `wiki/states/<st>/bills/`; `reindex` rebuilds the FTS5 index from the committed wiki.
```

Then update the intro paragraph's cost note: replace the sentence
"**every in-scope bill costs one classifier + one summarizer dispatch**, so limit bounds plan usage directly (D49)."
with
"**every candidate costs one classifier dispatch, and each run's in-scope bills share a single batch-summarizer dispatch**, so limit bounds plan usage directly (D49)."

- [ ] **Step 3: Rewrite `zwiad-backfill.md` steps 3–6**

In `.claude/commands/zwiad-backfill.md`, apply the identical rewrite as Step 2 with these federal differences:
- Step 4a uses `--scope federal`: `uv run zwiadbrain record-rejects --in data/runs/<id>/rejects.json --scope federal`, and the ledger sentence reads "upserts each rejected bill into `wiki/.rejects/federal.json` keyed by bill id and its Congress `updateDateIncludingText` cursor (D82)."
- Step 5 renders to `wiki/federal/bills/` (drop the `states/<st>/` path note; `render-classified` writes the federal path itself).
- Keep the existing `--force` handling described in the intro unchanged.

Concretely, replace the block from `### 3. Classify each bill` through the end of `### 6. Render + index` with the same text as Step 2, substituting `--scope federal` in 4a and the federal ledger sentence above, and removing the `wiki/states/<st>/bills/` clause from step 6 (federal pages render under `wiki/federal/bills/`).

- [ ] **Step 4: Verify both commands are registered and the agent frontmatter parses**

Run: `uv run zwiadbrain --help`
Expected: the command list now includes `apply-verdicts` and `apply-summaries`.

Run: `uv run zwiadbrain apply-verdicts --help` and `uv run zwiadbrain apply-summaries --help`
Expected: each prints its options (`--in`, `--verdicts`/`--summaries`, and for apply-verdicts `--out`).

Manually confirm `.claude/agents/batch-summarizer.md` has valid YAML frontmatter (name, description, tools, model) matching the shape of `.claude/agents/summarizer.md`.

- [ ] **Step 5: Commit**

```bash
git add .claude/agents/batch-summarizer.md .claude/commands/zwiad-scan-states.md .claude/commands/zwiad-backfill.md
git commit -m "feat(backfill): batch-summarizer subagent + verdicts/summaries flow in slash commands"
```

---

## Task 7: Decision log + plan close-out

**Files:**
- Modify: `DECISIONS.md`

- [ ] **Step 1: Append the decision entry**

Read the last decision number in `DECISIONS.md` (the latest is D82, the reject ledger). Append a new entry with the next number (e.g. D83), matching the file's existing format:

```markdown
## 2026-06-08 — Verdict persistence + two apply-CLIs for resumable backfill
**Chosen:** Persist classifier verdicts (`verdicts.json`) and summaries (`summaries.json`) to the run directory, applied by two symmetric CLIs (`apply-verdicts`, `apply-summaries`) backed by pure functions in `pipeline/verdicts.py`. `apply-verdicts` writes `classified.json` (topics applied) + `rejects.json`; `apply-summaries` merges the `{id: summary}` map into `classified.json` in place. A batch-summarizer subagent produces the summary map in one dispatch.
**Alternatives:** (a) Fold the summary into `verdicts.json` so one apply step does everything. (b) A `render-classified --summaries` flag that merges at render time. (c) Keep the ad-hoc `data/runs/build_*.py` scripts.
**Why:** Separate persisted files keep the classifier and summarizer subagents decoupled — a classifier rerun does not require summaries to already exist, and each step's cutoff loses only its own unprocessed tail. Two small CLIs mirror the existing fetch/render symmetry and the `rejects.py`/`record-rejects` split, and are unit-testable. Implements gaps 1 and 2 of `docs/backfill-scaling.md`.
**Trade-offs:** Two more pipeline files and two more run-dir artifacts per backfill. The batch-summarizer prompt is markdown, not unit-tested, so summary quality at batch scale relies on review. Gap 3 (push/merge cadence) stays convention-only; gap 4 (LegiScan quota) is unaddressed (no clean API hook).
**Revisit if:** Summary quality degrades at large batch sizes (consider chunking the batch-summarizer), or a third persisted-then-applied stage appears (factor a shared apply harness).
```

- [ ] **Step 2: Commit**

```bash
git add DECISIONS.md
git commit -m "docs(backfill): log D83 — verdict persistence + apply-verdicts/apply-summaries"
```

- [ ] **Step 3: Final full-suite confirmation**

Run: `uv run pytest && uv run pyright && uv run ruff check .`
Expected: all green. The feature is complete on `feature/initial-backfill`.

---

## Self-Review Notes

- **Spec coverage:** Verdict model (Task 1) ✓; `split_by_verdict` (Task 1) ✓; `apply_summaries` (Task 2) ✓; `apply-verdicts` CLI (Task 3) ✓; `apply-summaries` CLI (Task 4) ✓; fail-loud errors + pending tolerance (Tasks 1–4 tests) ✓; taxonomy validation left to `render-classified` (not duplicated) ✓; batch-summarizer + skill edits (Task 6) ✓; DECISIONS entry (Task 7) ✓; one-off `build_*.py` scripts left in place (no deletion task — intentional per spec) ✓.
- **Type consistency:** `split_by_verdict(list[Bill], list[Verdict]) -> (list[Bill], list[Bill], list[str])` and `apply_summaries(list[Bill], dict[str,str]) -> (list[Bill], list[str])` are used with those exact signatures in cli.py. Command fn `apply_summaries_cmd` deliberately differs from the imported `apply_summaries` to avoid shadowing.
- **Out of scope (confirmed):** gap 3 (convention), gap 4 (no API hook), amendment-explainer stays per-bill (unchanged), no deletion of throwaway run scripts.
```
