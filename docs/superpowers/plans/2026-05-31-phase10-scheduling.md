# PHASE-10 Scheduling (`/zwiad-run` + run-log) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/zwiad-run`, one interactive scheduler-agnostic orchestration command that sequences all enabled source flows, auto-commits per source, and appends a grep-parseable `scan-log.md` audit block via a small tested `zwiadbrain run-log` helper.

**Architecture:** A thin runbook slash command composes the 6 existing (already-tested) commands; the only new Python is a pure `run_log` formatter + a `run-log` CLI verb that the runbook calls once at the end with a session-assembled JSON summary (mirrors the D27 "session assembles JSON → Python renders deterministically" seam). No changes to the 6 existing commands; no headless LLM (D26); the law brain stays read-only (D2).

**Tech Stack:** Python 3.12, typer (CLI), pydantic (`RunSummary` validation), pytest + typer `CliRunner` (tests); the runbook is Markdown.

**Spec:** `docs/superpowers/specs/2026-05-31-phase10-scheduling-design.md`

---

## File Structure

- Create `src/zwiadbrain/pipeline/run_log.py` — pure: `RunSummary`/`SourceResult` pydantic models, `format_run_log_entry(summary, at) -> str`, `append_run_log(log_path, entry) -> None`.
- Modify `src/zwiadbrain/cli.py` — add the `run-log` command (parse `--in` JSON → `RunSummary`, format, append).
- Create `tests/test_run_log.py` — unit + CLI tests.
- Create `.claude/commands/zwiad-run.md` — the orchestration runbook (prose; validated interactively, D26).
- Create `docs/scheduling.md` — scheduler-agnostic operating note.
- Modify `DECISIONS.md` — append the 4 PHASE-10 decisions.
- Rename `.claude/phases/PHASE-10-active.md` → `PHASE-10-done.md` at the end.

---

## Task 1: `run_log` pure formatter + models (TDD)

**Files:**
- Create: `src/zwiadbrain/pipeline/run_log.py`
- Test: `tests/test_run_log.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_log.py
"""Tests for the PHASE-10 scan run-log helper (deterministic, no I/O in the formatter)."""

import datetime as dt

from zwiadbrain.pipeline.run_log import (
    RunSummary,
    SourceResult,
    format_run_log_entry,
)

_AT = dt.datetime(2026, 5, 31, 22, 0, tzinfo=dt.timezone.utc)


def _summary() -> RunSummary:
    return RunSummary(
        run_id="a1b2c3",
        sources=[
            SourceResult(source="refresh-federal", summary="changed=1", commit="9f3a21c"),
            SourceResult(source="refresh-state", summary="changed=0", commit=None),
            SourceResult(source="discover-state", summary="new=2", commit="4c7e88a"),
            SourceResult(source="enforcement", summary="new=1", commit="b2d5f10"),
            SourceResult(source="lawbrain", summary="linked=0 review=1", commit="7e1aa90"),
        ],
        leg_history_flagged=["118-hr-2670"],
        errors=[],
    )


def test_format_run_log_entry_renders_expected_block() -> None:
    entry = format_run_log_entry(_summary(), _AT)
    assert entry == (
        "## 2026-05-31T22:00Z  (run a1b2c3)\n"
        "- refresh-federal : changed=1 → commit 9f3a21c\n"
        "- refresh-state   : changed=0 → no-op\n"
        "- discover-state  : new=2 → commit 4c7e88a\n"
        "- enforcement     : new=1 → commit b2d5f10\n"
        "- lawbrain        : linked=0 review=1 → commit 7e1aa90\n"
        "- leg-history     : 1 flagged (118-hr-2670) — run manually\n"
        "- errors          : none\n"
    )


def test_format_run_log_entry_no_flags_no_errors() -> None:
    summary = RunSummary(
        run_id="zzz999",
        sources=[SourceResult(source="lawbrain", summary="no changes", commit=None)],
    )
    entry = format_run_log_entry(summary, _AT)
    assert "- leg-history     : none\n" in entry
    assert "- errors          : none\n" in entry
    assert "- lawbrain        : no changes → no-op\n" in entry


def test_format_run_log_entry_joins_multiple_errors() -> None:
    summary = RunSummary(
        run_id="err001",
        sources=[],
        errors=["states: legiscan 429", "enforcement: ftc feed timeout"],
    )
    entry = format_run_log_entry(summary, _AT)
    assert "- errors          : states: legiscan 429; enforcement: ftc feed timeout\n" in entry
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_run_log.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'zwiadbrain.pipeline.run_log'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/zwiadbrain/pipeline/run_log.py
"""Deterministic scan run-log: format a session-assembled summary into a grep-parseable
``scan-log.md`` block, and append it. Mirrors the D27 seam (the interactive /zwiad-run
session assembles the JSON; Python renders it deterministically). No LLM, append-only."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from pydantic import BaseModel

_LABEL_WIDTH = 16
_LOG_HEADER = "# ZwiadBrain scan log\n"


class SourceResult(BaseModel):
    """One source's outcome in a /zwiad-run pass."""

    source: str  # short label, e.g. "refresh-federal", "discover-state", "enforcement"
    summary: str  # human-readable counts the runbook assembled, e.g. "changed=1", "new=2"
    commit: str | None = None  # short sha of this source's auto-commit, or None for a no-op


class RunSummary(BaseModel):
    """The whole /zwiad-run pass, assembled by the interactive session."""

    run_id: str
    sources: list[SourceResult] = []
    leg_history_flagged: list[str] = []  # enacted bill ids needing a manual leg-history
    errors: list[str] = []  # per-source failures, e.g. "states: legiscan 429"


def format_run_log_entry(summary: RunSummary, at: dt.datetime) -> str:
    """Render one append-only run-log block (ends with a single newline)."""
    lines = [f"## {at:%Y-%m-%dT%H:%M}Z  (run {summary.run_id})"]
    for s in summary.sources:
        commit_part = f" → commit {s.commit}" if s.commit else " → no-op"
        lines.append(f"- {s.source:<{_LABEL_WIDTH}}: {s.summary}{commit_part}")
    if summary.leg_history_flagged:
        flagged = ", ".join(summary.leg_history_flagged)
        body = f"{len(summary.leg_history_flagged)} flagged ({flagged}) — run manually"
    else:
        body = "none"
    lines.append(f"- {'leg-history':<{_LABEL_WIDTH}}: {body}")
    errors = "; ".join(summary.errors) if summary.errors else "none"
    lines.append(f"- {'errors':<{_LABEL_WIDTH}}: {errors}")
    return "\n".join(lines) + "\n"


def append_run_log(log_path: Path, entry: str) -> None:
    """Append a run-log block to ``log_path``, creating it with a header if absent.

    Append-only and time-varying (not idempotent): each run adds a new dated block,
    separated from the previous by one blank line. Always LF-terminated."""
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else _LOG_HEADER
    if not existing.endswith("\n"):
        existing += "\n"
    log_path.write_text(existing + "\n" + entry, encoding="utf-8", newline="\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_run_log.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/pipeline/run_log.py tests/test_run_log.py
git commit -m "feat(scan): add deterministic run-log formatter + models (PHASE-10)"
```

---

## Task 2: `run-log` CLI verb (TDD)

**Files:**
- Modify: `src/zwiadbrain/cli.py` (add a new `@app.command(name="run-log")`; reuse existing `json` and `import datetime as dt` imports — verify they are present near the top of the file before adding)
- Test: `tests/test_run_log.py` (append CLI tests)

- [ ] **Step 1: Write the failing test (append to `tests/test_run_log.py`)**

```python
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zwiadbrain.cli import app

_RUNNER = CliRunner()


def _write_summary(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "run_id": "a1b2c3",
                "sources": [
                    {"source": "enforcement", "summary": "new=1", "commit": "b2d5f10"}
                ],
                "leg_history_flagged": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )


def test_run_log_cli_creates_and_appends(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    _write_summary(summary)
    log = tmp_path / "scan-log.md"

    result = _RUNNER.invoke(
        app,
        ["run-log", "--in", str(summary), "--log-file", str(log),
         "--at", "2026-05-31T22:00:00+00:00"],
    )
    assert result.exit_code == 0, result.output
    text = log.read_text(encoding="utf-8")
    assert text.startswith("# ZwiadBrain scan log\n")
    assert "## 2026-05-31T22:00Z  (run a1b2c3)" in text
    assert "- enforcement     : new=1 → commit b2d5f10" in text


def test_run_log_cli_second_run_appends_in_order(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    _write_summary(summary)
    log = tmp_path / "scan-log.md"
    args = ["run-log", "--in", str(summary), "--log-file", str(log)]
    _RUNNER.invoke(app, [*args, "--at", "2026-05-31T22:00:00+00:00"])
    _RUNNER.invoke(app, [*args, "--at", "2026-06-01T09:30:00+00:00"])
    text = log.read_text(encoding="utf-8")
    assert text.index("2026-05-31T22:00Z") < text.index("2026-06-01T09:30Z")
    assert text.count("# ZwiadBrain scan log") == 1  # header written once


def test_run_log_cli_rejects_malformed_summary(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"sources": []}', encoding="utf-8")  # missing required run_id
    log = tmp_path / "scan-log.md"
    result = _RUNNER.invoke(app, ["run-log", "--in", str(bad), "--log-file", str(log)])
    assert result.exit_code != 0
    assert not log.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_run_log.py -k cli -q`
Expected: FAIL (no `run-log` command; `CliRunner` reports usage error / exit code 2)

- [ ] **Step 3: Add the CLI command in `src/zwiadbrain/cli.py`**

Place near the other render/log commands. First confirm `import json` and `import datetime as dt` already exist at the top of `cli.py` (they do — used by `render-lawbrain-commentary`); add `from zwiadbrain.pipeline.run_log import RunSummary, append_run_log, format_run_log_entry` to the imports.

```python
@app.command(name="run-log")
def run_log(
    input_file: Annotated[
        Path, typer.Option("--in", help="run-summary JSON assembled by /zwiad-run.")
    ],
    log_file: Annotated[
        Path, typer.Option(help="Committed append-only scan log.")
    ] = Path("scan-log.md"),
    at: Annotated[
        str | None,
        typer.Option(help="ISO timestamp override (tests); defaults to now (UTC)."),
    ] = None,
) -> None:
    """Append one grep-parseable block to scan-log.md — the audit half of /zwiad-run."""
    try:
        raw = json.loads(input_file.read_text(encoding="utf-8"))
        summary = RunSummary.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ConfigError(f"invalid run-summary {input_file}: {exc}") from exc
    when = dt.datetime.fromisoformat(at) if at else dt.datetime.now(dt.timezone.utc)
    append_run_log(log_file, format_run_log_entry(summary, when))
    typer.echo(f"run-log: appended {summary.run_id} ({len(summary.sources)} sources)")
```

Note: `ValidationError` (pydantic) and `ConfigError` are already imported in `cli.py` (used by other commands). If `ValidationError` is not imported, add `from pydantic import ValidationError`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_run_log.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Run the full suite + type-check + lint**

Run: `uv run pytest -q && uv run pyright && uv run ruff check .`
Expected: all green (existing count + 6 new), `0 errors`, `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/zwiadbrain/cli.py tests/test_run_log.py
git commit -m "feat(scan): add run-log CLI verb appending to scan-log.md (PHASE-10)"
```

---

## Task 3: `/zwiad-run` orchestration runbook

**Files:**
- Create: `.claude/commands/zwiad-run.md`

No unit test — the runbook is prose, validated by an interactive dry-run (D26), like the other 6 commands.

- [ ] **Step 1: Create `.claude/commands/zwiad-run.md`**

````markdown
---
description: Run the whole ZwiadBrain pipeline in one interactive session — refresh + discover + enforcement + law-brain — auto-committing per source and writing a scan-log entry. Built to be triggered by an external interactive-session runner (D26).
argument-hint: "[--dry-run]"
allowed-tools: Bash, Read, Write, Task
---

# ZwiadBrain full run

Orchestrate every enabled source flow in ONE interactive session. This command does not
re-implement the sources — it sequences the existing commands, auto-commits each source's
changes, and records a grep-parseable run-log. Designed so an external runner that opens an
interactive Claude Code session can trigger ZwiadBrain on a schedule (D26: LLM work stays
interactive; no `claude -p`).

**Arguments:** `--dry-run` lists the intended steps and per-source commit messages without
running subagents or writing/committing anything.

## Principles
- **Per-source isolation (D54):** if a step fails, record the error, commit whatever already
  succeeded, and continue to the next source. Never abort the whole run on one failure.
- **Auto-commit per source (PHASE-10):** after a source produces changes, commit the touched
  paths (`wiki/**`, plus `wiki/links.yaml` / `wiki/review-queue.md` for the law-brain step)
  with a conventional message. No changes → no commit.
- **Law brain is read-only (D2).** Never write under `LAW_BRAIN_PATH`.
- Pick a `RUN_ID`: the short basename of the newest `data/runs/<id>/` directory created this
  pass (timestamp form), used in the run-log header.

## Steps

Run each in order. For each, follow that command's own procedure (read its `.claude/commands/<name>.md`).
Track a per-source result `{source, summary, commit|null}` for the run-log.

1. **Refresh tracked items** — follow `/zwiad-refresh`. Record `refresh-federal` and
   `refresh-state` results. Commit changed pages: `chore(scan): refresh tracked bills (<n> changed)`.
2. **Discover new federal** — follow `/zwiad-backfill` (since-window). Commit:
   `chore(scan): discover federal bills (<n> new)`.
3. **Discover new state** — follow `/zwiad-scan-states`. Commit:
   `chore(scan): discover state bills (<n> new)`.
4. **Enforcement** — follow `/zwiad-scan-enforcement` (FTC + enabled AGs). Commit:
   `chore(scan): enforcement actions (<n> new/updated)`.
5. **Law-brain sync** — follow `/zwiad-sync-lawbrain`. Commit `wiki/**` + `wiki/links.yaml`
   + `wiki/review-queue.md`: `chore(scan): law-brain commentary (<n> linked, <m> review)`.
6. **Reindex + log:**
   - `uv run zwiadbrain reindex` (rebuilds the gitignored index — nothing to commit).
   - Identify newly-enacted bills with no `leg_history` (flag only — do NOT run
     `/zwiad-leg-history`; list them in the summary).
   - `Write` the assembled run-summary JSON to `data/runs/<RUN_ID>/run-summary.json`
     (fields: `run_id`, `sources[]` with `{source, summary, commit|null}`,
     `leg_history_flagged[]`, `errors[]`).
   - `uv run zwiadbrain run-log --in data/runs/<RUN_ID>/run-summary.json`
   - `git add scan-log.md && git commit -m "chore(scan): log run <RUN_ID>"`

## Report
Print the consolidated summary: per-source counts + commit shas, any errors, and the
leg-history TODO list. For `--dry-run`, print the intended steps and commit messages only.
````

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/zwiad-run.md
git commit -m "feat(scan): add /zwiad-run orchestration runbook (PHASE-10)"
```

---

## Task 4: `docs/scheduling.md`

**Files:**
- Create: `docs/scheduling.md`

- [ ] **Step 1: Create `docs/scheduling.md`**

```markdown
# Scheduling ZwiadBrain

ZwiadBrain has no built-in scheduler. All LLM work runs as interactive Claude Code subagents
on the regular plan (D26) — headless `claude -p` / the Agent SDK are forbidden — so a session
must be open and triggered.

## The entrypoint

`/zwiad-run` runs the whole pipeline (refresh → discover federal/state → enforcement →
law-brain → reindex) in one interactive session, auto-commits per source, and appends a block
to `scan-log.md`.

## Triggering it on a schedule

Point any runner that can **open an interactive Claude Code session** at `/zwiad-run` on your
desired cadence (a few times/week is the design target). ZwiadBrain is deliberately
**scheduler-agnostic** — it does not ship Task Scheduler / cron wiring. The runner is the only
thing that needs scheduling; ZwiadBrain just exposes the one command.

Why not a plain cron job running shell? Because the LLM dispatch (classifier / summarizer /
enforcement / law-brain subagents) must run in an interactive session to stay on the regular
plan (D26). A runner that drives an interactive session satisfies this; a headless shell does
not.

## Auditing runs

`scan-log.md` (committed) carries one grep-parseable block per run — per-source counts, the
commit shas, flagged-for-manual-leg-history bills, and any per-source errors.
```

- [ ] **Step 2: Commit**

```bash
git add docs/scheduling.md
git commit -m "docs(scan): scheduler-agnostic operating note (PHASE-10)"
```

---

## Task 5: DECISIONS entries + close the phase

**Files:**
- Modify: `DECISIONS.md`
- Rename: `.claude/phases/PHASE-10-active.md` → `.claude/phases/PHASE-10-done.md`

- [ ] **Step 1: Append the PHASE-10 decisions to `DECISIONS.md`**

Number them sequentially after the highest existing entry **at execution time** (note: PR #5
adds D64 and may merge first — check `DECISIONS.md` for the current max and continue from
there). Add:

```markdown
## 2026-05-31 — N. PHASE-10 scheduling = one interactive `/zwiad-run`, externally triggered
**Chosen:** A single interactive orchestration command (`/zwiad-run`) sequences all enabled source flows and auto-commits per source; an external runner that opens an interactive Claude Code session triggers it on a schedule. ZwiadBrain ships no OS-scheduler wiring.
**Alternatives:** D41's split hybrid (OS cron for headless detection + separate interactive dispatch); pure `/loop`; headless `claude -p` (D26-forbidden).
**Why:** The user will drive scheduling via an external interactive-session runner, which can do BOTH detection and dispatch in one session — collapsing D41's hybrid to a single entrypoint and keeping every LLM call on the regular plan (D26). Scheduler-agnostic so the trigger can be anything.
**Trade-offs:** Nothing runs unless the runner opens a session; a long single-session run dispatches many subagents.
**Revisit if:** A headless path is ever adopted (see D26), or single-session runs grow too large to complete reliably (then split per-source).

## 2026-05-31 — N+1. `/zwiad-run` auto-commits per source; run-log is the audit trail
**Chosen:** Each source's changes are auto-committed as the run proceeds (conventional messages); a committed append-only `scan-log.md` records one grep-parseable block per run via the deterministic `zwiadbrain run-log` verb. Leg-history is flagged, never auto-run. Law brain stays read-only.
**Alternatives:** Stage-only (review-before-commit, the other 6 commands' convention); auto-commit to a per-run branch + PR.
**Why:** Unattended/runner-driven operation needs the changes committed without a human in the loop each run; git history + `scan-log.md` are the after-the-fact review surface. Leg-history is the heaviest, rarest flow, so it is surfaced for a deliberate manual run.
**Trade-offs:** Commits land without per-run human review (mitigated by diffs + the run-log); a bad scrape could commit noise (mitigated by the existing classifiers + idempotent renders).
**Revisit if:** Auto-committed noise becomes a problem — switch to the dated-branch-+-PR variant.
```

- [ ] **Step 2: Run the full suite once more**

Run: `uv run pytest -q && uv run pyright && uv run ruff check .`
Expected: all green.

- [ ] **Step 3: Mark the phase done and commit**

```bash
git mv .claude/phases/PHASE-10-active.md .claude/phases/PHASE-10-done.md
# edit the Status line in the file from ACTIVE to DONE, and tick the task checkboxes
git add DECISIONS.md .claude/phases/PHASE-10-done.md
git commit -m "docs(phase10): record decisions; mark PHASE-10 done"
```

---

## Task 6: Interactive dry-run validation (acceptance — not a code change)

- [ ] **Step 1:** With the law brain reachable and API keys present, run `/zwiad-run --dry-run`; confirm it lists all 6 steps + the intended per-source commit messages and writes nothing.
- [ ] **Step 2:** Run `/zwiad-run`; confirm: each changed source committed with a conventional message; unchanged sources committed nothing; a `scan-log.md` block appended + committed; the law brain `git status` / fingerprint unchanged; newly-enacted bills (if any) appear in the summary as a manual leg-history TODO.
- [ ] **Step 3:** Re-run `/zwiad-run`; confirm a no-change pass commits only the new `scan-log.md` block (sources are clean no-ops, D20).

---

## Self-Review notes (author)
- **Spec coverage:** `/zwiad-run` (Task 3), run-log helper + `scan-log.md` (Tasks 1–2), `docs/scheduling.md` (Task 4), decisions (Task 5), interactive acceptance (Task 6), leg-history-flag (Tasks 3/6), per-source auto-commit + isolation (Task 3), law-brain read-only (Task 3) — all covered.
- **Placeholders:** none — code shown in every code step; the only deliberate execution-time choice is the DECISIONS numbers (cross-branch with PR #5's D64), called out explicitly.
- **Type consistency:** `RunSummary`/`SourceResult` fields (`run_id`, `sources`, `summary`, `commit`, `leg_history_flagged`, `errors`) are identical across Tasks 1–2 and the runbook JSON in Task 3.
