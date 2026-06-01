"""Tests for the PHASE-10 scan run-log helper (deterministic, no I/O in the formatter)
and the ``run-log`` CLI verb that appends to ``scan-log.md``."""

import datetime as dt
import json
from pathlib import Path

from typer.testing import CliRunner

from zwiadbrain.cli import app
from zwiadbrain.pipeline.run_log import (
    RunSummary,
    SourceResult,
    format_run_log_entry,
)

_AT = dt.datetime(2026, 5, 31, 22, 0, tzinfo=dt.UTC)
_RUNNER = CliRunner()


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
