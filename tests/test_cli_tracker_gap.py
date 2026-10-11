"""Tests for the tracker cross-check CLI commands (PHASE-29).

``tracker-gap`` is pure file IO over a snapshot; ``fetch-tracker-candidates`` talks to
LegiScan, mocked here with respx and routed by the request's ``op`` parameter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
import yaml
from typer.testing import CliRunner

from zwiadbrain.cli import app
from zwiadbrain.sources.legiscan import LEGISCAN_API_BASE

runner = CliRunner()

_LEGISCAN_FIX = Path(__file__).parent / "fixtures" / "legiscan"


def _route_legiscan(mock: respx.MockRouter, mapping: dict[str, dict[str, Any]]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        op = request.url.params.get("op", "")
        return httpx.Response(200, json=mapping[op])

    mock.get(url=LEGISCAN_API_BASE).mock(side_effect=handler)


def _snapshot(path: Path) -> Path:
    path.write_text(
        yaml.safe_dump(
            {
                "laws": [
                    {
                        "jurisdiction": "US-CA",
                        "state": "California",
                        "orrick_topic": "AI Calling",
                        "name": "AI Call Disclosures Law",
                        "bill_number": "AB 2905",
                        "citation": None,
                        "bill_key": "ca-ab-2905",
                        "law_link": "https://example.test/ab2905",
                    },
                    {
                        "jurisdiction": "US-CA",
                        "state": "California",
                        "orrick_topic": "AI Transparency",
                        "name": "California AI Transparency Act",
                        "bill_number": None,
                        "citation": "Cal. Bus. & Prof. Code 22757",
                        "bill_key": None,
                        "law_link": None,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _wiki(root: Path) -> Path:
    (root / "states" / "ca" / "bills").mkdir(parents=True)
    return root


# --- tracker-gap ------------------------------------------------------------


def test_tracker_gap_writes_the_gap_and_citation_rows(tmp_path: Path) -> None:
    """should bucket the snapshot against the wiki and write a reviewable report"""
    snapshot = _snapshot(tmp_path / "snap.yaml")
    wiki = _wiki(tmp_path / "wiki")
    out = tmp_path / "gap.json"

    result = runner.invoke(
        app,
        ["tracker-gap", "--snapshot", str(snapshot), "--wiki", str(wiki), "--out", str(out),
         "--corrections", str(tmp_path / "none.yaml")],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(out.read_text(encoding="utf-8"))
    assert [e["bill_number"] for e in report["gap"]] == ["AB 2905"]
    assert report["tracked"] == []
    assert len(report["citation_only"]) == 1


def test_tracker_gap_counts_an_existing_page_as_tracked(tmp_path: Path) -> None:
    """should not report a law as a gap when a wiki page already covers it"""
    snapshot = _snapshot(tmp_path / "snap.yaml")
    wiki = _wiki(tmp_path / "wiki")
    (wiki / "states" / "ca" / "bills" / "ca-2023-ab-2905.md").write_text("x", encoding="utf-8")
    out = tmp_path / "gap.json"

    result = runner.invoke(
        app,
        ["tracker-gap", "--snapshot", str(snapshot), "--wiki", str(wiki), "--out", str(out),
         "--corrections", str(tmp_path / "none.yaml")],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["gap"] == []
    assert [e["bill_number"] for e in report["tracked"]] == ["AB 2905"]


def test_tracker_gap_counts_a_ledger_entry_as_already_rejected(tmp_path: Path) -> None:
    """should bucket a law already decided out-of-scope as rejected, not as a gap"""
    snapshot = _snapshot(tmp_path / "snap.yaml")
    wiki = _wiki(tmp_path / "wiki")
    (wiki / ".rejects").mkdir()
    (wiki / ".rejects" / "state.json").write_text(
        json.dumps({"1848433": {"id": "ca-2023-ab-2905", "cursor": "h", "scope_version": "D95"}}),
        encoding="utf-8",
    )
    out = tmp_path / "gap.json"

    result = runner.invoke(
        app,
        ["tracker-gap", "--snapshot", str(snapshot), "--wiki", str(wiki), "--out", str(out),
         "--corrections", str(tmp_path / "none.yaml")],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["gap"] == []
    assert [e["bill_number"] for e in report["rejected"]] == ["AB 2905"]


def test_tracker_gap_applies_a_correction_to_a_tracker_bill_number(tmp_path: Path) -> None:
    """should cross-check under the corrected number, not the tracker's wrong one"""
    snapshot = _snapshot(tmp_path / "snap.yaml")
    wiki = _wiki(tmp_path / "wiki")
    (wiki / "states" / "ca" / "bills" / "ca-2023-ab-9999.md").write_text("x", encoding="utf-8")
    fixes = tmp_path / "fixes.yaml"
    fixes.write_text(
        yaml.safe_dump(
            {"corrections": [
                {"state": "ca", "bill_number": "AB 2905", "correct_number": "AB 9999",
                 "why": "test"}
            ]}
        ),
        encoding="utf-8",
    )
    out = tmp_path / "gap.json"

    result = runner.invoke(
        app,
        ["tracker-gap", "--snapshot", str(snapshot), "--wiki", str(wiki), "--out", str(out),
         "--corrections", str(fixes)],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["gap"] == []
    assert [e["bill_number"] for e in report["tracked"]] == ["AB 9999"]


def test_tracker_gap_errors_on_a_correction_that_matches_nothing(tmp_path: Path) -> None:
    """should fail loudly when the snapshot has moved out from under a correction"""
    snapshot = _snapshot(tmp_path / "snap.yaml")
    wiki = _wiki(tmp_path / "wiki")
    fixes = tmp_path / "fixes.yaml"
    fixes.write_text(
        yaml.safe_dump(
            {"corrections": [{"state": "ca", "bill_number": "AB 1", "year": 2020, "why": "stale"}]}
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["tracker-gap", "--snapshot", str(snapshot), "--wiki", str(wiki),
         "--out", str(tmp_path / "gap.json"), "--corrections", str(fixes)],
    )

    assert result.exit_code == 1
    assert "matches no tracker law" in result.output


# --- fetch-tracker-candidates -----------------------------------------------


_SESSIONS = {
    "status": "OK",
    "sessions": [
        {"session_id": 2016, "year_start": 2023, "year_end": 2024,
         "special": 0, "session_name": "2023-2024 Session"},
    ],
}
_MASTERLIST = {
    "status": "OK",
    "masterlist": {
        "session": {"session_id": 2016},
        "0": {"bill_id": 1848000, "number": "AB2905", "change_hash": "h1", "status": 4,
              "title": "Automated calls: artificial intelligence", "description": "d"},
        "1": {"bill_id": 1848001, "number": "AB9999", "change_hash": "h2", "status": 4,
              "title": "Unrelated", "description": "d"},
    },
}


def _gap_file(path: Path, *, bill_number: str = "AB 2905") -> Path:
    path.write_text(
        json.dumps(
            {
                "gap": [
                    {
                        "key": ["ca", "H", bill_number.split()[-1].lstrip("0")],
                        "state": "ca",
                        "jurisdiction": "US-CA",
                        "bill_number": bill_number,
                        "names": ["AI Call Disclosures Law"],
                        "topics": ["AI Calling"],
                        "sources": ["orrick"],
                        "year_hint": None,
                        "urls": [],
                        "wiki_ids": [],
                        "reject_ids": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_fetch_tracker_candidates_resolves_a_number_and_stages_the_bill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should resolve the tracker's bill number to a LegiScan bill and stage it"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LEGISCAN_API_KEY", "test-key")
    gap = _gap_file(tmp_path / "gap.json")
    detail = json.loads((_LEGISCAN_FIX / "getBill.json").read_text(encoding="utf-8"))

    with respx.mock(assert_all_called=False) as mock:
        _route_legiscan(
            mock,
            {"getSessionList": _SESSIONS, "getMasterList": _MASTERLIST, "getBill": detail},
        )
        result = runner.invoke(
            app,
            ["fetch-tracker-candidates", "--gap", str(gap), "--state", "ca",
             "--out", str(tmp_path / "run")],
        )

    assert result.exit_code == 0, result.output
    staged = json.loads((tmp_path / "run" / "candidates.json").read_text(encoding="utf-8"))
    assert len(staged) == 1
    assert "resolved 1" in result.output


def test_fetch_tracker_candidates_reports_a_number_it_cannot_find(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should report an unresolved target instead of silently staging nothing"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LEGISCAN_API_KEY", "test-key")
    gap = _gap_file(tmp_path / "gap.json", bill_number="AB 1234")

    with respx.mock(assert_all_called=False) as mock:
        _route_legiscan(mock, {"getSessionList": _SESSIONS, "getMasterList": _MASTERLIST})
        result = runner.invoke(
            app,
            ["fetch-tracker-candidates", "--gap", str(gap), "--state", "ca",
             "--out", str(tmp_path / "run")],
        )

    assert result.exit_code == 0, result.output
    assert "not-found" in result.output
    unresolved = json.loads((tmp_path / "run" / "unresolved.json").read_text(encoding="utf-8"))
    assert [u["bill_number"] for u in unresolved] == ["AB 1234"]


def test_fetch_tracker_candidates_errors_without_an_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exit non-zero with a clear message when the LegiScan key is unset"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LEGISCAN_API_KEY", raising=False)
    gap = _gap_file(tmp_path / "gap.json")

    result = runner.invoke(
        app, ["fetch-tracker-candidates", "--gap", str(gap), "--state", "ca"]
    )

    assert result.exit_code == 1
    assert "error:" in result.output
