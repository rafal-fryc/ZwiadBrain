"""Tests for the render-leg-history verifier-echo cross-check (PHASE-06.1)."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from zwiadbrain.cli import app
from zwiadbrain.sources.legiscan import LEGISCAN_API_BASE

runner = CliRunner()

_FIX = Path(__file__).parent / "fixtures" / "legiscan"

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


# --- Tier-2 related media (PHASE-14 / D72) ----------------------------------

# A non-YouTube media URL the fake resolves to 200 (routes through patched _fetch_url,
# not the live caption path).
_MEDIA_URL = "https://www.congress.gov/committee-video/markup"
_MEDIA_TITLE = "Full Committee Markup of H.R. 9020"


def _fake_fetch_media_ok(url: str) -> tuple[int, str]:
    """200 for the statement url and the media url; 404 otherwise."""
    if url in (_URL_TEST, _MEDIA_URL):
        return (200, f"Congressional Record: {_QUOTE} The speaker continued.")
    return (404, "Not Found")


def test_render_leg_history_keeps_related_media_when_url_200_and_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should render a related-media item whose url resolves 200 and verifier confirms it"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch_media_ok)

    staging = {
        "bill": _bill(),
        "spine": _spine(),
        "hearings": [],
        "statements": [],
        "related_media": [
            {"title": _MEDIA_TITLE, "url": _MEDIA_URL, "kind": "video", "relation": "on_bill"}
        ],
        "media_verdicts": [
            {"index": 0, "title_prefix": _MEDIA_TITLE[:30], "verified": True, "note": "ok"}
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
    assert "### Related Media" in rendered
    assert _MEDIA_TITLE in rendered


def test_render_leg_history_drops_related_media_when_verifier_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should drop a related-media item the verifier did not confirm (no Related Media section)"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch_media_ok)

    staging = {
        "bill": _bill(),
        "spine": _spine(),
        "hearings": [],
        "statements": [],
        "related_media": [
            {"title": _MEDIA_TITLE, "url": _MEDIA_URL, "kind": "video"}
        ],
        "media_verdicts": [
            {"index": 0, "title_prefix": _MEDIA_TITLE[:30], "verified": False, "note": "no"}
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
    assert "### Related Media" not in rendered
    assert _MEDIA_TITLE not in rendered


# --- fetch-state-leg-history (PHASE-16 / D75) -------------------------------


def _serve_getbill(mock: respx.MockRouter, payload: dict[str, object]) -> None:
    """Route every LegiScan GET to return *payload* (the getBill fixture)."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)
    mock.get(url=LEGISCAN_API_BASE).mock(side_effect=handler)


def test_fetch_state_leg_history_stages_state_spine_and_leads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should stage leghistory.json with the state spine (votes, enactment) and leads"""
    monkeypatch.setenv("LEGISCAN_API_KEY", "lk-test")
    payload = json.loads((_FIX / "getBill_leghistory.json").read_text(encoding="utf-8"))
    out = tmp_path / "run"
    with respx.mock(assert_all_called=False) as mock:
        _serve_getbill(mock, payload)
        result = runner.invoke(
            app,
            ["fetch-state-leg-history", "--bill", "1789012", "--state", "ca", "--out", str(out)],
        )
    assert result.exit_code == 0, result.output
    staged = json.loads((out / "leghistory.json").read_text(encoding="utf-8"))
    assert staged["bill"]["id"] == "ca-2023-sb-362"
    assert len(staged["spine"]["votes"]) == 2
    assert staged["spine"]["floor_consideration"] == []
    assert staged["spine"]["enactment"]["date_signed"] == "2023-10-08"
    assert staged["leads"]["state"] == "CA"
    # PHASE-21: the 'Analysis' supplement is promoted to a spine committee report; only the
    # fiscal note remains a Tier-2 lead (the third supplement is link-less and skipped).
    assert len(staged["leads"]["supplement_media"]) == 1
    assert [r["citation"] for r in staged["spine"]["committee_reports"]] == [
        "Assembly Floor Analysis"
    ]


def test_fetch_state_leg_history_rejects_unenacted_bill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exit non-zero with a 'not enacted' message for a bill that has not been chaptered"""
    monkeypatch.setenv("LEGISCAN_API_KEY", "lk-test")
    payload = json.loads((_FIX / "getBill_leghistory.json").read_text(encoding="utf-8"))
    # Demote the bill to in-progress: not Passed, no Chaptered progress event.
    payload["bill"]["status"] = 1
    payload["bill"]["progress"] = [{"date": "2023-02-08", "event": 1}]
    out = tmp_path / "run"
    with respx.mock(assert_all_called=False) as mock:
        _serve_getbill(mock, payload)
        result = runner.invoke(
            app,
            ["fetch-state-leg-history", "--bill", "1789012", "--state", "ca", "--out", str(out)],
        )
    assert result.exit_code == 1
    assert "not enacted" in result.output
    assert not (out / "leghistory.json").exists()


def test_render_leg_history_routes_state_bill_to_states_path(tmp_path: Path) -> None:
    """should write a rendered state-bill leg history under wiki/states/ca/bills (Task 5)"""
    staging: dict[str, object] = {
        "bill": {
            "type": "bill",
            "id": "ca-2023-sb-362",
            "jurisdiction": "US-CA",
            "title": "Data broker registration.",
            "bill_number": "SB 362",
            "summary": "A state test bill.",
            "sponsors": [],
            "actions": [],
            "amendments": [],
        },
        "spine": {
            "versions": [],
            "committee_reports": [],
            "votes": [
                {
                    "date": "2023-05-31",
                    "chamber": "S",
                    "result": "Senate Third Reading — Passed 30-8",
                    "roll_call_url": "https://legiscan.com/CA/rollcall/SB362/id/555001",
                }
            ],
            "floor_consideration": [],
            "enactment": {
                "date_signed": "2023-10-08",
                "url": "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?id=SB362",
            },
            "hearings": [],
            "statements": [],
            "narrative": None,
        },
        "hearings": [],
        "statements": [],
        "narrative": "State journey.",
    }
    staging_file = tmp_path / "staging.json"
    staging_file.write_text(json.dumps(staging), encoding="utf-8")
    wiki = tmp_path / "wiki"

    result = runner.invoke(
        app, ["render-leg-history", "--in", str(staging_file), "--wiki", str(wiki)]
    )
    assert result.exit_code == 0, result.output
    page = wiki / "states" / "ca" / "bills" / "ca-2023-sb-362.md"
    assert page.exists()
    assert "Senate Third Reading" in page.read_text(encoding="utf-8")


# --- narrative render gate (D106) --------------------------------------------


def _narrative_staging(narrative_verdict: object) -> dict[str, object]:
    staging: dict[str, object] = {
        "bill": _bill(),
        "spine": _spine(),
        "hearings": [],
        "statements": [],
        "verdicts": [],
        "narrative": "The bill passed both chambers unanimously.",
    }
    if narrative_verdict is not None:
        staging["narrative_verdict"] = narrative_verdict
    return staging


def test_render_leg_history_keeps_narrative_with_pass_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should render the Legislative Journey when the narrative verdict is pass"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch_ok)
    staging = _narrative_staging({"checked": True, "verdict": "pass", "issues": []})
    staging_file = tmp_path / "staging.json"
    staging_file.write_text(json.dumps(staging), encoding="utf-8")
    wiki = tmp_path / "wiki"

    result = runner.invoke(
        app, ["render-leg-history", "--in", str(staging_file), "--wiki", str(wiki)]
    )
    assert result.exit_code == 0, result.output
    assert "narrative=yes" in result.output

    rendered = next(wiki.rglob("*.md")).read_text(encoding="utf-8")
    assert "The bill passed both chambers unanimously." in rendered


def test_render_leg_history_drops_narrative_on_fail_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should drop the narrative and report the drop when the verdict is fail"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch_ok)
    staging = _narrative_staging(
        {
            "checked": True,
            "verdict": "fail",
            "issues": [{"claim": "unanimously", "problem": "60-1 vote", "evidence": "spine"}],
        }
    )
    staging_file = tmp_path / "staging.json"
    staging_file.write_text(json.dumps(staging), encoding="utf-8")
    wiki = tmp_path / "wiki"

    result = runner.invoke(
        app, ["render-leg-history", "--in", str(staging_file), "--wiki", str(wiki)]
    )
    assert result.exit_code == 0, result.output
    assert "narrative=dropped" in result.output
    assert "dropped narrative:" in result.output

    rendered = next(wiki.rglob("*.md")).read_text(encoding="utf-8")
    assert "The bill passed both chambers unanimously." not in rendered


def test_render_leg_history_drops_narrative_when_staging_has_no_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should fail-closed drop the narrative from a pre-D106 staging file with no verdict"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch_ok)
    staging = _narrative_staging(None)
    staging_file = tmp_path / "staging.json"
    staging_file.write_text(json.dumps(staging), encoding="utf-8")
    wiki = tmp_path / "wiki"

    result = runner.invoke(
        app, ["render-leg-history", "--in", str(staging_file), "--wiki", str(wiki)]
    )
    assert result.exit_code == 0, result.output
    assert "narrative=dropped" in result.output

    rendered = next(wiki.rglob("*.md")).read_text(encoding="utf-8")
    assert "The bill passed both chambers unanimously." not in rendered
