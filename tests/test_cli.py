"""Tests for the ZwiadBrain CLI entrypoint.

The full command set is added per phase; for now we only pin that the app is
wired up and reports its version.
"""

import json
from pathlib import Path

import pytest
import respx
from typer.testing import CliRunner

from zwiadbrain import __version__
from zwiadbrain.cli import app
from zwiadbrain.models import Bill
from zwiadbrain.pipeline.render import write_page
from zwiadbrain.sources.congress import CONGRESS_API_BASE

runner = CliRunner()

_FIX = Path(__file__).parent / "fixtures" / "congress"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def _route_backfill(mock: respx.MockRouter) -> None:
    mock.get("/bill/118").respond(json=_fixture("list.json"))
    base = "/bill/118/hr/8818"
    mock.get(base).respond(json=_fixture("detail.json"))
    mock.get(f"{base}/actions").respond(json=_fixture("actions.json"))
    mock.get(f"{base}/amendments").respond(json=_fixture("amendments.json"))
    mock.get(f"{base}/text").respond(json=_fixture("text.json"))
    mock.get(f"{base}/summaries").respond(json=_fixture("summaries.json"))
    mock.get(f"{base}/relatedbills").respond(json=_fixture("relatedbills.json"))


def test_version_command_prints_package_version() -> None:
    """should print the package version"""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_reindex_command_reports_indexed_count(tmp_path: Path) -> None:
    """should rebuild the index from a wiki root and report how many pages it indexed"""
    wiki = tmp_path / "wiki"
    write_page(Bill(id="hr-1", jurisdiction="US", title="A bill", bill_number="HR 1"), wiki)
    result = runner.invoke(
        app, ["reindex", "--wiki", str(wiki), "--db", str(tmp_path / "i.sqlite")]
    )
    assert result.exit_code == 0
    assert "1" in result.stdout


def test_backfill_command_renders_federal_bill_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should enrich and render federal bills from Congress.gov under wiki/federal/bills/"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    wiki = tmp_path / "wiki"
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        _route_backfill(mock)
        result = runner.invoke(
            app, ["backfill", "--congress", "118", "--limit", "1", "--wiki", str(wiki)]
        )
    assert result.exit_code == 0, result.output
    page = wiki / "federal" / "bills" / "118-hr-8818.md"
    assert page.exists()
    assert "## Status & Timeline" in page.read_text(encoding="utf-8")


def test_backfill_command_errors_without_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exit non-zero with a clear error when CONGRESS_API_KEY is unset"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    result = runner.invoke(app, ["backfill", "--congress", "118", "--limit", "1"])
    assert result.exit_code == 1
    assert "CONGRESS_API_KEY" in result.output
