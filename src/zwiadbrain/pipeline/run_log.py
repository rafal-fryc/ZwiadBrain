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
