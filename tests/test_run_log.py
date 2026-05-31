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
