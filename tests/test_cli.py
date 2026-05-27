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
_TOPICS = Path(__file__).resolve().parents[1] / "reference" / "topics.yaml"


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


def test_fetch_candidates_writes_enriched_bills_to_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should fetch keyword-matched candidates and write enriched Bills to candidates.json"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    out = tmp_path / "run"
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        _route_backfill(mock)
        result = runner.invoke(
            app,
            [
                "fetch-candidates",
                "--congress", "118",
                "--limit", "1",
                "--seed", "artificial intelligence",
                "--out", str(out),
            ],
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert len(data) == 1
    bill = Bill.model_validate(data[0])
    assert bill.id == "118-hr-8818"
    assert bill.title == "Artificial Intelligence Accountability Act"
    assert bill.last_synced is not None  # enrichment stamped sync time


def test_fetch_candidates_defaults_seeds_from_topics_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should use the topics.yaml seed lexicon for recall when no --seed is given"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    out = tmp_path / "run"
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        _route_backfill(mock)
        result = runner.invoke(
            app,
            [
                "fetch-candidates",
                "--congress", "118",
                "--limit", "1",
                "--out", str(out),
                "--topics", str(_TOPICS),
            ],
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert Bill.model_validate(data[0]).id == "118-hr-8818"


def test_fetch_candidates_recovers_title_miss_via_policy_area(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should recover a topical bill that lacks a title seed via its allowlisted policyArea"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    out = tmp_path / "run"
    bill_list = {
        "bills": [
            {
                "congress": 118, "type": "S", "number": "9999",
                "title": "Quarterly Filing Reform Act",  # no AI/privacy/cyber seed in the title
                "updateDate": "2024-01-01T00:00:00Z",
            }
        ]
    }
    base = "/bill/118/s/9999"
    detail = {"bill": {"title": "Quarterly Filing Reform Act", "policyArea": {"name": "Commerce"}}}
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/bill/118").respond(json=bill_list)
        mock.get(base).respond(json=detail)
        mock.get(f"{base}/actions").respond(json={"actions": []})
        mock.get(f"{base}/amendments").respond(json={"amendments": []})
        mock.get(f"{base}/text").respond(json={"textVersions": []})
        mock.get(f"{base}/summaries").respond(json={"summaries": []})
        mock.get(f"{base}/relatedbills").respond(json={"relatedBills": []})
        result = runner.invoke(
            app,
            [
                "fetch-candidates",
                "--congress", "118",
                "--limit", "5",
                "--out", str(out),
                "--topics", str(_TOPICS),
            ],
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert len(data) == 1
    assert Bill.model_validate(data[0]).title == "Quarterly Filing Reform Act"


def _classified(tmp_path: Path, bills: list[Bill]) -> Path:
    path = tmp_path / "classified.json"
    path.write_text(
        json.dumps([b.model_dump(mode="json") for b in bills]), encoding="utf-8"
    )
    return path


def _render_args(infile: Path, wiki: Path) -> list[str]:
    return ["render-classified", "--in", str(infile), "--wiki", str(wiki), "--topics", str(_TOPICS)]


def test_render_classified_renders_in_scope_bills(tmp_path: Path) -> None:
    """should render the provided in-scope bills into the wiki"""
    bill = Bill(
        id="118-hr-8818",
        jurisdiction="US",
        title="Artificial Intelligence Accountability Act",
        bill_number="H.R. 8818",
        topics=["ai"],
        summary="A Claude-written summary.",
    )
    infile = _classified(tmp_path, [bill])
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, _render_args(infile, wiki))
    assert result.exit_code == 0, result.output
    page = wiki / "federal" / "bills" / "118-hr-8818.md"
    assert page.exists()
    assert "A Claude-written summary." in page.read_text(encoding="utf-8")


def test_render_classified_rejects_unknown_topic(tmp_path: Path) -> None:
    """should exit non-zero naming a topic that is not in the taxonomy"""
    bill = Bill(
        id="118-hr-1", jurisdiction="US", title="t", bill_number="H.R. 1", topics=["bogus"]
    )
    infile = _classified(tmp_path, [bill])
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, _render_args(infile, wiki))
    assert result.exit_code == 1
    assert "bogus" in result.output


def test_render_classified_is_idempotent(tmp_path: Path) -> None:
    """should produce a byte-identical page when re-run with identical input"""
    bill = Bill(
        id="118-hr-8818",
        jurisdiction="US",
        title="Artificial Intelligence Accountability Act",
        bill_number="H.R. 8818",
        topics=["ai"],
        summary="A Claude-written summary.",
    )
    infile = _classified(tmp_path, [bill])
    wiki = tmp_path / "wiki"
    page = wiki / "federal" / "bills" / "118-hr-8818.md"
    args = _render_args(infile, wiki)
    runner.invoke(app, args)
    first = page.read_text(encoding="utf-8")
    runner.invoke(app, args)
    assert page.read_text(encoding="utf-8") == first
