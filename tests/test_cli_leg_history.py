"""Tests for the render-leg-history verifier-echo cross-check (PHASE-06.1)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zwiadbrain.cli import app

runner = CliRunner()

# A URL the fake fetch will resolve to 200 with the test quote.
_URL_TEST = "https://www.congress.gov/congressional-record/test-stmt"

# The quote used in both tests — long enough to pass the min-length gate.
_QUOTE = "We must protect consumers from harmful automated systems and their misuse today."


def _fake_fetch_ok(url: str) -> tuple[int, str]:
    """Returns 200 with the quote body for _URL_TEST, 404 otherwise."""
    if url == _URL_TEST:
        return (200, f"Congressional Record: {_QUOTE} The speaker continued.")
    return (404, "Not Found")


def _spine() -> dict[str, object]:
    return {
        "versions": [],
        "committee_reports": [],
        "votes": [],
        "floor_consideration": [],
        "hearings": [],
        "statements": [],
        "enactment": None,
        "narrative": None,
    }


def _bill() -> dict[str, object]:
    return {
        "type": "bill",
        "id": "118-hr-9020",
        "jurisdiction": "US",
        "title": "Test Act",
        "bill_number": "H.R. 9020",
        "summary": "A test bill.",
        "status": "enacted",
        "topics": ["ai"],
        "sponsors": [],
        "actions": [],
        "amendments": [],
    }


def test_render_leg_history_drops_statement_when_verifier_echo_speaker_mismatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should drop a statement whose verifier verdict echoes a different speaker than the input"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch_ok)

    staging = {
        "bill": _bill(),
        "spine": _spine(),
        "hearings": [],
        "statements": [
            {
                "speaker": "Rep. Jane Doe",
                "role": "sponsor",
                "quote": _QUOTE,
                "source_url": _URL_TEST,
                "source_type": "CREC",
                "verified": False,
            }
        ],
        # Verifier claims verified:true but echoes the WRONG speaker → fail-closed drop.
        "verdicts": [
            {
                "index": 0,
                "speaker": "Sen. Someone Else",
                "quote_prefix": _QUOTE[:40],
                "verified": True,
                "note": "ok",
            }
        ],
        "narrative": "Journey.",
    }
    staging_file = tmp_path / "staging.json"
    staging_file.write_text(json.dumps(staging), encoding="utf-8")
    wiki = tmp_path / "wiki"

    result = runner.invoke(
        app, ["render-leg-history", "--in", str(staging_file), "--wiki", str(wiki)]
    )
    assert result.exit_code == 0, result.output

    rendered = next(wiki.rglob("*.md")).read_text(encoding="utf-8")
    assert "We must protect consumers from" not in rendered


def test_render_leg_history_keeps_statement_when_verifier_echo_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should keep a verified statement whose verdict echo matches speaker and quote_prefix"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch_ok)

    staging = {
        "bill": _bill(),
        "spine": _spine(),
        "hearings": [],
        "statements": [
            {
                "speaker": "Rep. Jane Doe",
                "role": "sponsor",
                "quote": _QUOTE,
                "source_url": _URL_TEST,
                "source_type": "CREC",
                "verified": False,
            }
        ],
        "verdicts": [
            {
                "index": 0,
                "speaker": "Rep. Jane Doe",
                "quote_prefix": _QUOTE[:40],
                "verified": True,
                "note": "ok",
            }
        ],
        "narrative": "Journey.",
    }
    staging_file = tmp_path / "staging.json"
    staging_file.write_text(json.dumps(staging), encoding="utf-8")
    wiki = tmp_path / "wiki"

    result = runner.invoke(
        app, ["render-leg-history", "--in", str(staging_file), "--wiki", str(wiki)]
    )
    assert result.exit_code == 0, result.output

    rendered = next(wiki.rglob("*.md")).read_text(encoding="utf-8")
    assert "We must protect consumers from" in rendered
