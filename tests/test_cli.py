"""Tests for the ZwiadBrain CLI entrypoint.

The full command set is added per phase; for now we only pin that the app is
wired up and reports its version.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import respx
from typer.testing import CliRunner

from zwiadbrain import __version__

# `_fetch_url` is imported by its internal name on purpose: the InvalidURL-handling
# unit test verifies that exact private helper's contract (returns (0, '') instead of
# raising), which is the whole point of the T10 hardening fix.
from zwiadbrain.cli import _fetch_url, app  # pyright: ignore[reportPrivateUsage]
from zwiadbrain.models import Bill, CommitteeReport, Enactment, Hearing, LegHistory, Statement
from zwiadbrain.pipeline.rejects import RejectEntry, write_reject_ledger
from zwiadbrain.pipeline.render import write_page
from zwiadbrain.sources.base import Candidate
from zwiadbrain.sources.congress import CONGRESS_API_BASE, CongressSource
from zwiadbrain.sources.govinfo import GovInfoSource
from zwiadbrain.sources.legiscan import LEGISCAN_API_BASE, LegiScanSource

runner = CliRunner()

_FIX = Path(__file__).parent / "fixtures" / "congress"
_TOPICS = Path(__file__).resolve().parents[1] / "reference" / "topics.yaml"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


_LEGISCAN_FIX = Path(__file__).parent / "fixtures" / "legiscan"


def _legiscan_fixture(name: str) -> dict[str, Any]:
    return json.loads((_LEGISCAN_FIX / name).read_text(encoding="utf-8"))


def _route_legiscan(mock: respx.MockRouter, mapping: dict[str, dict[str, Any]]) -> None:
    """Dispatch LegiScan ops (single base URL) to fixture payloads by the `op` query param."""
    def handler(request: httpx.Request) -> httpx.Response:
        op = request.url.params.get("op")
        return httpx.Response(200, json=mapping[op])
    mock.get(url=LEGISCAN_API_BASE).mock(side_effect=handler)


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
    write_page(Bill(id="118-hr-1", jurisdiction="US", title="A bill", bill_number="HR 1"), wiki)
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


def test_fetch_candidates_skip_existing_drops_already_tracked_bills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PHASE-22: --skip-existing drops candidates that already have a wiki page"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    wiki = tmp_path / "wiki"
    # Pre-track the only seed-matching bill so the sweep should skip it.
    write_page(
        Bill(id="118-hr-8818", jurisdiction="US", title="AI Act", bill_number="H.R. 8818"), wiki
    )
    out = tmp_path / "run"
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        _route_backfill(mock)
        result = runner.invoke(
            app,
            [
                "fetch-candidates",
                "--congress", "118",
                "--limit", "5",
                "--seed", "artificial intelligence",
                "--skip-existing",
                "--wiki", str(wiki),
                "--out", str(out),
            ],
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert data == []  # the only seed-matching bill was already tracked


def test_fetch_candidates_threads_max_pages_to_discover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PHASE-22: --max-pages is forwarded to CongressSource.discover (opt-in back-catalog)"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    captured: dict[str, int] = {}

    def _fake_discover(
        self: CongressSource,
        *,
        congress: int | None = None,
        since: object = None,
        limit: int = 20,
        max_pages: int = 1,
    ) -> list[object]:
        captured["max_pages"] = max_pages
        return []

    monkeypatch.setattr("zwiadbrain.cli.CongressSource.discover", _fake_discover)
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        [
            "fetch-candidates",
            "--congress", "118",
            "--seed", "ai",
            "--max-pages", "3",
            "--out", str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["max_pages"] == 3


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
    detail = {
        "bill": {
            "congress": 118, "type": "S", "number": "9999",
            "title": "Quarterly Filing Reform Act",
            "policyArea": {"name": "Commerce"},
        }
    }
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


def test_fetch_enacted_keeps_only_topical_enacted_laws(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should recall-filter /law/{congress}/pub and enrich only survivors (--no-classify-all)"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    out = tmp_path / "run"
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/law/118/pub").respond(json=_fixture("law_list.json"))
        # S.2073 has no title seed -> Stage-2 probe; reply with a policyArea NOT in the allowlist.
        mock.get("/bill/118/s/2073").respond(
            json={"bill": {"policyArea": {"name": "Transportation and Public Works"}}}
        )
        _route_backfill(mock)  # enrich routes for the survivor 118/hr/8818
        result = runner.invoke(
            app,
            ["fetch-enacted-candidates", "--congress", "118", "--no-classify-all",
             "--out", str(out), "--topics", str(_TOPICS)],
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert [b["id"] for b in data] == ["118-hr-8818"]
    bill = Bill.model_validate(data[0])
    assert bill.enacted is True
    assert bill.public_law is not None  # public_law populated from enacted laws array


def _fake_enrich(source: object, candidate: Candidate) -> Bill:
    """Stub enrich: build a Bill straight from the candidate (no HTTP)."""
    cong, btype, num = candidate.native_id.split("/")
    return Bill(
        id=f"{cong}-{btype}-{num}",
        jurisdiction="US",
        title=candidate.title or "x",
        bill_number=f"{btype.upper()} {num}",
        enacted=True,
    )


def test_fetch_enacted_classify_all_skips_recall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--classify-all stages every enacted law and makes no policyArea probe"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    monkeypatch.setattr("zwiadbrain.cli.enrich", _fake_enrich)
    out = tmp_path / "run"
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        law = mock.get("/law/118/pub").respond(json=_fixture("law_list.json"))
        probe = mock.get("/bill/118/s/2073").respond(json={"bill": {}})
        result = runner.invoke(
            app,
            ["fetch-enacted-candidates", "--congress", "118", "--classify-all", "--out", str(out)],
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert [b["id"] for b in data] == ["118-hr-8818", "118-s-2073"]
    assert law.called and not probe.called  # no Stage-2 probe under --classify-all


def test_fetch_enacted_defaults_to_classify_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should stage every enacted law with no recall probe when no flag is given (D87)"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    monkeypatch.setattr("zwiadbrain.cli.enrich", _fake_enrich)
    out = tmp_path / "run"
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/law/118/pub").respond(json=_fixture("law_list.json"))
        probe = mock.get("/bill/118/s/2073").respond(json={"bill": {}})
        result = runner.invoke(
            app, ["fetch-enacted-candidates", "--congress", "118", "--out", str(out)]
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert [b["id"] for b in data] == ["118-hr-8818", "118-s-2073"]
    assert not probe.called


def test_fetch_enacted_errors_when_candidates_exceed_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should fail loudly instead of silently dropping candidates beyond --limit"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    monkeypatch.setattr("zwiadbrain.cli.enrich", _fake_enrich)
    out = tmp_path / "run"
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/law/118/pub").respond(json=_fixture("law_list.json"))
        result = runner.invoke(
            app,
            ["fetch-enacted-candidates", "--congress", "118", "--limit", "1", "--out", str(out)],
        )
    assert result.exit_code == 1
    assert "--limit" in result.output
    assert not (out / "candidates.json").exists()


def test_fetch_enacted_skip_existing_drops_tracked_law(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--skip-existing drops an enacted law that already has a wiki page"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    monkeypatch.setattr("zwiadbrain.cli.enrich", _fake_enrich)
    wiki = tmp_path / "wiki"
    write_page(
        Bill(id="118-hr-8818", jurisdiction="US", title="AI Act", bill_number="H.R. 8818"), wiki
    )
    out = tmp_path / "run"
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        mock.get("/law/118/pub").respond(json=_fixture("law_list.json"))
        mock.get("/bill/118/s/2073").respond(
            json={"bill": {"policyArea": {"name": "Transportation and Public Works"}}}
        )
        result = runner.invoke(
            app,
            [
                "fetch-enacted-candidates", "--congress", "118", "--no-classify-all",
                "--skip-existing", "--wiki", str(wiki), "--out", str(out),
                "--topics", str(_TOPICS),
            ],
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert data == []  # the only topical enacted law was already tracked


def test_fetch_enacted_errors_without_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exit non-zero with a clear error when CONGRESS_API_KEY is unset"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    result = runner.invoke(app, ["fetch-enacted-candidates", "--congress", "118"])
    assert result.exit_code == 1
    assert "CONGRESS_API_KEY" in result.output


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


def test_render_classified_reports_clean_error_on_malformed_json(tmp_path: Path) -> None:
    """should exit 1 with an 'error:' message (no traceback) on invalid JSON"""
    bad = tmp_path / "classified.json"
    bad.write_text("{not valid json", encoding="utf-8")
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, _render_args(bad, wiki))
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output


def test_render_classified_reports_clean_error_on_missing_required_field(tmp_path: Path) -> None:
    """should exit 1 with an 'error:' message when a bill is missing a required field"""
    bad = tmp_path / "classified.json"
    # Missing required 'bill_number' (and 'jurisdiction'/'title') -> ValidationError.
    bad.write_text(json.dumps([{"id": "118-hr-1", "type": "bill"}]), encoding="utf-8")
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, _render_args(bad, wiki))
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output


def test_render_classified_reports_clean_error_when_top_level_not_list(tmp_path: Path) -> None:
    """should exit 1 with an 'error:' message when classified.json is not a JSON list"""
    bad = tmp_path / "classified.json"
    bad.write_text(json.dumps({"id": "118-hr-1"}), encoding="utf-8")
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, _render_args(bad, wiki))
    assert result.exit_code == 1
    assert "error:" in result.output


# ---------------------------------------------------------------------------
# fetch-leg-history
#
# Approach: monkeypatch CongressSource.fetch, assemble_spine, and collect_leads.
#
# Rationale: test_cli.py already monkeypatches for the non-API-key path (env
# manipulation), and the GovInfo base URL is different from Congress's.  Wiring
# two separate respx base-URL mocks inside a single CliRunner invocation is
# fiddly and produces no extra coverage beyond what test_govinfo.py and
# test_leg_history.py already deliver for the HTTP layer.  Monkeypatching the
# two pipeline calls keeps the tests readable and still genuinely exercises the
# enacted/non-enacted branch, the JSON shape, and the error paths.
# ---------------------------------------------------------------------------


def _make_enacted_bill() -> Bill:
    """Return a minimal enacted Bill for fetch-leg-history tests."""
    return Bill(
        id="118-hr-8818",
        jurisdiction="US",
        title="Artificial Intelligence Accountability Act",
        bill_number="H.R. 8818",
        congress="118",
        enacted=True,
        public_law="118-265",
        sponsors=["Rep. Lieu, Ted [D-CA-36]"],
    )


def _make_spine() -> LegHistory:
    """Return a minimal LegHistory spine for fetch-leg-history tests."""
    return LegHistory(
        committee_reports=[
            CommitteeReport(
                citation="H. Rept. 118-712 - ARTIFICIAL INTELLIGENCE ACCOUNTABILITY ACT",
                url="https://www.govinfo.gov/app/details/CRPT-118hrpt712",
            )
        ],
        enactment=Enactment(
            public_law="118-42",
            url="https://www.govinfo.gov/app/details/PLAW-118publ42",
        ),
    )


def _make_leads() -> dict[str, object]:
    """Return a minimal leads dict for fetch-leg-history tests."""
    return {
        "id": "118-hr-8818",
        "congress": "118",
        "citation": "H.R. 8818",
        "title": "Artificial Intelligence Accountability Act",
        "sponsors": ["Rep. Lieu, Ted [D-CA-36]"],
        "related_bills": [],
        "introduced_date": None,
        "latest_action_date": None,
        "hearings": [
            {
                "title": "Hearing on Artificial Intelligence Accountability",
                "committee": "House Committee on the Judiciary",
                "date": "2024-03-15",
                "citation": "CHRG-118hhrg54321",
                "url": "https://www.govinfo.gov/app/details/CHRG-118hhrg54321",
            }
        ],
    }


def test_fetch_leg_history_writes_staging_file_for_enacted_bill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should write leghistory.json with bill/spine/leads keys for an enacted bill"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    monkeypatch.setenv("GOVINFO_API_KEY", "test-govinfo-key")

    enacted = _make_enacted_bill()
    spine = _make_spine()
    leads = _make_leads()

    def _fake_fetch_enacted(self: object, native_id: str) -> Bill:  # noqa: ARG001
        return enacted

    monkeypatch.setattr("zwiadbrain.cli.CongressSource.fetch", _fake_fetch_enacted)
    mock_assemble = MagicMock(return_value=spine)
    mock_leads = MagicMock(return_value=leads)
    monkeypatch.setattr("zwiadbrain.cli.assemble_spine", mock_assemble)
    monkeypatch.setattr("zwiadbrain.cli.collect_leads", mock_leads)

    out = tmp_path / "run"
    result = runner.invoke(
        app,
        ["fetch-leg-history", "--bill", "118/hr/8818", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output

    staged = out / "leghistory.json"
    assert staged.exists()
    data = json.loads(staged.read_text(encoding="utf-8"))
    assert set(data.keys()) == {"bill", "spine", "leads"}

    # bill section round-trips back to a valid Bill
    bill_obj = Bill.model_validate(data["bill"])
    assert bill_obj.id == "118-hr-8818"
    assert bill_obj.enacted is True

    # spine carries committee_reports and enactment
    spine_data = data["spine"]
    assert len(spine_data["committee_reports"]) == 1
    assert spine_data["committee_reports"][0]["citation"].startswith("H. Rept.")
    assert spine_data["enactment"]["public_law"] == "118-42"

    # leads carries hearings
    assert len(data["leads"]["hearings"]) == 1
    assert "Artificial Intelligence" in data["leads"]["hearings"][0]["title"]

    # assemble_spine and collect_leads were called once with the correct args
    # (positional identity/type checks guard against an argument-order bug at the
    # call site, which assert_called_once alone could not catch).
    mock_assemble.assert_called_once()
    assert mock_assemble.call_args.args[0] is enacted
    assert isinstance(mock_assemble.call_args.args[1], CongressSource)
    assert isinstance(mock_assemble.call_args.args[2], GovInfoSource)

    mock_leads.assert_called_once()
    assert mock_leads.call_args.args[0] is enacted
    assert isinstance(mock_leads.call_args.args[1], GovInfoSource)

    # echo message present
    assert "118-hr-8818" in result.output


def test_fetch_leg_history_errors_for_non_enacted_bill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exit non-zero with 'not enacted' message and not write leghistory.json"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    monkeypatch.setenv("GOVINFO_API_KEY", "test-govinfo-key")

    non_enacted = Bill(
        id="118-hr-9999",
        jurisdiction="US",
        title="Some Non-Enacted Bill",
        bill_number="H.R. 9999",
        congress="118",
        enacted=False,
    )

    def _fake_fetch_non_enacted(self: object, native_id: str) -> Bill:  # noqa: ARG001
        return non_enacted

    monkeypatch.setattr("zwiadbrain.cli.CongressSource.fetch", _fake_fetch_non_enacted)

    out = tmp_path / "run"
    result = runner.invoke(
        app,
        ["fetch-leg-history", "--bill", "118/hr/9999", "--out", str(out)],
    )
    assert result.exit_code == 1
    assert "not enacted" in result.output
    assert not (out / "leghistory.json").exists()


def test_fetch_leg_history_errors_without_govinfo_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exit non-zero with a config error when GOVINFO_API_KEY is unset"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    monkeypatch.delenv("GOVINFO_API_KEY", raising=False)

    # GovInfoSource construction now happens after the enacted check; patch
    # CongressSource.fetch so the code reaches require_govinfo_api_key() cleanly.
    enacted = _make_enacted_bill()

    def _fake_fetch_enacted(self: object, native_id: str) -> Bill:  # noqa: ARG001
        return enacted

    monkeypatch.setattr("zwiadbrain.cli.CongressSource.fetch", _fake_fetch_enacted)

    result = runner.invoke(
        app,
        ["fetch-leg-history", "--bill", "118/hr/8818"],
    )
    assert result.exit_code == 1
    assert "GOVINFO_API_KEY" in result.output


# ---------------------------------------------------------------------------
# render-leg-history
#
# Approach: monkeypatch zwiadbrain.cli._fetch_url with a fake URL→(status,text)
# mapping.  No real network; all grounding logic exercised deterministically.
# ---------------------------------------------------------------------------

_QUOTE_A = (
    "This legislation will fundamentally transform how artificial intelligence"
    " is governed in our country."
)
_QUOTE_B = (
    "We must ensure that privacy protections keep pace with technological advancement"
    " and data collection practices."
)

_URL_HEARING_GOOD = "https://www.govinfo.gov/app/details/CHRG-118hhrg11111"
_URL_HEARING_BAD = "https://www.govinfo.gov/app/details/CHRG-118hhrg99999"
_URL_STMT_A = "https://www.congress.gov/congressional-record/stmt-a"
_URL_STMT_B = "https://www.congress.gov/congressional-record/stmt-b"
_URL_CRPT = "https://www.govinfo.gov/app/details/CRPT-118hrpt712"
_URL_PLAW = "https://www.govinfo.gov/app/details/PLAW-118publ42"

# Fake HTTP responses: url -> (status_code, body_text)
_FAKE_RESPONSES: dict[str, tuple[int, str]] = {
    _URL_HEARING_GOOD: (200, "Hearing on AI Accountability full transcript here."),
    _URL_HEARING_BAD: (404, "Not Found"),
    _URL_STMT_A: (200, f"Congressional Record statement: {_QUOTE_A} The speaker continued."),
    _URL_STMT_B: (200, "This page does not contain the expected quote."),
    _URL_CRPT: (200, "Committee Report content."),
    _URL_PLAW: (200, "Public Law full text."),
}


def _make_leg_history_staging(tmp_path: Path) -> Path:
    """Build a staging JSON that render-leg-history consumes and write it to tmp_path."""
    bill = Bill(
        id="118-hr-8818",
        jurisdiction="US",
        title="Artificial Intelligence Accountability Act",
        bill_number="H.R. 8818",
        congress="118",
        enacted=True,
        public_law="118-42",
    )
    spine = LegHistory(
        committee_reports=[
            CommitteeReport(
                citation="H. Rept. 118-712",
                url=_URL_CRPT,
            )
        ],
        enactment=Enactment(
            public_law="118-42",
            url=_URL_PLAW,
        ),
    )
    hearings = [
        Hearing(
            title="Hearing on AI Accountability",
            committee="House Committee on the Judiciary",
            url=_URL_HEARING_GOOD,
        ),
        Hearing(
            title="Hearing on AI and Data Governance",
            committee="House Committee on Energy and Commerce",
            url=_URL_HEARING_BAD,
        ),
    ]
    statements = [
        Statement(
            speaker="Rep. Lieu, Ted",
            role="sponsor",
            quote=_QUOTE_A,
            source_url=_URL_STMT_A,
            source_type="CREC",
            verified=False,
        ),
        Statement(
            speaker="Rep. Smith, Jane",
            role="member",
            quote=_QUOTE_B,
            source_url=_URL_STMT_B,
            source_type="CREC",
            verified=False,
        ),
    ]
    verdicts = [
        {
            "index": 0,
            "verified": True,
            "speaker": "Rep. Lieu, Ted",
            "quote_prefix": _QUOTE_A[:40],
            "note": "Quote confirmed in CR.",
        },
        {
            "index": 1,
            "verified": True,
            "speaker": "Rep. Smith, Jane",
            "quote_prefix": _QUOTE_B[:40],
            "note": "Quote confirmed in CR.",
        },
    ]
    narrative = (
        "This landmark bill establishes the first comprehensive federal framework"
        " for AI accountability."
    )
    payload: dict[str, object] = {
        "bill": bill.model_dump(mode="json"),
        "spine": spine.model_dump(mode="json"),
        "hearings": [h.model_dump(mode="json") for h in hearings],
        "statements": [s.model_dump(mode="json") for s in statements],
        "narrative": narrative,
        # D106: a narrative renders only with a pass verdict from the verifier.
        "narrative_verdict": {"checked": True, "verdict": "pass", "issues": []},
        "verdicts": verdicts,
    }
    path = tmp_path / "leghistory_staging.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _fake_fetch(url: str) -> tuple[int, str]:
    return _FAKE_RESPONSES.get(url, (404, "Not Found"))


def test_render_leg_history_renders_page_with_grounded_statement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should render a page that contains statement A (grounded) but not statement B (dropped)"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch)
    staging = _make_leg_history_staging(tmp_path)
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(staging), "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output

    page = wiki / "federal" / "bills" / "118-hr-8818.md"
    assert page.exists()
    content = page.read_text(encoding="utf-8")

    # Statement A: grounded, should appear with verified checkmark and source link
    assert _QUOTE_A in content
    assert _URL_STMT_A in content
    assert "✓" in content

    # Statement B: quote not found on page → dropped
    assert _QUOTE_B not in content

    # Narrative
    assert "landmark bill" in content

    # Spine committee report and enactment links
    assert _URL_CRPT in content
    assert _URL_PLAW in content


def test_render_leg_history_drops_404_hearing_keeps_good_hearing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should keep the 200-status hearing and drop the 404 hearing from the page"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch)
    staging = _make_leg_history_staging(tmp_path)
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(staging), "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output

    page = wiki / "federal" / "bills" / "118-hr-8818.md"
    content = page.read_text(encoding="utf-8")

    # Good hearing url should appear; bad hearing url should not
    assert _URL_HEARING_GOOD in content
    assert _URL_HEARING_BAD not in content


def test_render_leg_history_echo_reports_counts_and_drop_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should echo proposed/grounded/dropped counts and a drop line for each rejected item"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch)
    staging = _make_leg_history_staging(tmp_path)
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(staging), "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output

    out = result.output
    # Statement summary: 2 input / 1 grounded / 0 parse-drop / 1 ground-drop
    assert "statements: 2 input / 1 grounded / 0 parse-drop / 1 ground-drop" in out

    # Hearing summary: 2 input / 1 grounded / 0 parse-drop / 1 ground-drop
    assert "hearings: 2 input / 1 grounded / 0 parse-drop / 1 ground-drop" in out

    # Per-drop line for statement B
    assert "dropped statement" in out
    assert "Rep. Smith, Jane" in out

    # Per-drop line for bad hearing
    assert "dropped hearing" in out
    assert "AI and Data Governance" in out


def test_render_leg_history_collapses_grounded_near_duplicate_statements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should list a quote once when it grounds under two speaker honorific variants

    Regression guard for PHASE-18: dedup runs POST-grounding, so two statements that
    BOTH ground (same quote, "Gavin Newsom" vs "Gov. Gavin Newsom") collapse to one
    instead of double-listing — without dropping a groundable copy.
    """
    quote = "I am proud to sign this landmark AI transparency bill into law today."
    url_press = "https://www.congress.gov/congressional-record/newsom-press"
    url_signing = "https://www.congress.gov/congressional-record/newsom-signing"

    def _fetch(url: str) -> tuple[int, str]:
        # Both sources carry the SAME verbatim quote, so both pass the quote gate.
        if url in (url_press, url_signing):
            return (200, f"Statement: {quote} The speaker continued.")
        return (404, "Not Found")

    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fetch)

    bill = Bill(
        id="118-hr-9999",
        jurisdiction="US",
        title="AI Transparency Act",
        bill_number="H.R. 9999",
        congress="118",
    )
    spine = LegHistory()
    statements = [
        Statement(
            speaker="Gavin Newsom",
            role="other",
            quote=quote,
            source_url=url_press,
            source_type="press",
            verified=False,
        ),
        Statement(
            speaker="Gov. Gavin Newsom",
            role="other",
            quote=quote,
            source_url=url_signing,
            source_type="signing",
            verified=False,
        ),
    ]
    verdicts = [
        {"index": 0, "verified": True, "speaker": "Gavin Newsom", "quote_prefix": quote[:40]},
        {"index": 1, "verified": True, "speaker": "Gov. Gavin Newsom", "quote_prefix": quote[:40]},
    ]
    payload: dict[str, object] = {
        "bill": bill.model_dump(mode="json"),
        "spine": spine.model_dump(mode="json"),
        "hearings": [],
        "statements": [s.model_dump(mode="json") for s in statements],
        "narrative": None,
        "verdicts": verdicts,
    }
    staging = tmp_path / "neardup_staging.json"
    staging.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(staging), "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output

    # Both grounded, but the near-dup collapses: 1 final grounded, 1 near-dup, 0 ground-drop.
    assert "2 input / 1 grounded" in result.output
    assert "1 near-dup" in result.output

    page = wiki / "federal" / "bills" / "118-hr-9999.md"
    content = page.read_text(encoding="utf-8")
    # First-wins: the press-lane copy survives; the signing-lane near-dup's url is gone.
    assert url_press in content
    assert url_signing not in content


def _make_js_staging(tmp_path: Path, quote: str, url_js: str) -> Path:
    """Staging with a single statement whose quote is JS-injected (absent from static HTML)."""
    bill = Bill(
        id="118-hr-7777",
        jurisdiction="US",
        title="AI Disclosure Act",
        bill_number="H.R. 7777",
        congress="118",
    )
    spine = LegHistory()
    statements = [
        Statement(
            speaker="Jane Roe",
            role="other",
            quote=quote,
            source_url=url_js,
            source_type="news",
            verified=False,
        )
    ]
    verdicts = [{"index": 0, "verified": True, "speaker": "Jane Roe", "quote_prefix": quote[:40]}]
    payload: dict[str, object] = {
        "bill": bill.model_dump(mode="json"),
        "spine": spine.model_dump(mode="json"),
        "hearings": [],
        "statements": [s.model_dump(mode="json") for s in statements],
        "narrative": None,
        "verdicts": verdicts,
    }
    staging = tmp_path / "js_staging.json"
    staging.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return staging


def test_render_leg_history_recovers_js_rendered_statement_via_playwright(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PHASE-19: a quote-not-found statement re-grounds when the render pass shows the quote"""
    quote = "This statement is injected into the page by JavaScript after the load event."
    url_js = "https://news.test/js-article"

    def _static(url: str) -> tuple[int, str]:
        # Static HTML lacks the quote -> pass 1 drops it as "quote not found on source page".
        if url == url_js:
            return (200, "<body><div id='app'>Loading...</div></body>")
        return (404, "Not Found")

    def _render(url: str) -> str:
        return f"<body><p>{quote}</p></body>" if url == url_js else ""

    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _static)
    monkeypatch.setattr("zwiadbrain.cli.playwright_available", lambda: True)
    monkeypatch.setattr("zwiadbrain.cli.render_page_html", _render)

    staging = _make_js_staging(tmp_path, quote, url_js)
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(staging), "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output

    # The render pass recovered the JS-injected quote.
    assert "1 input / 1 grounded" in result.output
    assert "1 js-recovered" in result.output

    page = wiki / "federal" / "bills" / "118-hr-7777.md"
    assert url_js in page.read_text(encoding="utf-8")


def test_render_leg_history_drops_js_statement_when_playwright_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PHASE-19: with Playwright absent, the JS statement stays a fail-closed drop (unchanged)"""
    quote = "This statement is injected into the page by JavaScript after the load event."
    url_js = "https://news.test/js-article"

    def _static(url: str) -> tuple[int, str]:
        if url == url_js:
            return (200, "<body><div id='app'>Loading...</div></body>")
        return (404, "Not Found")

    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _static)
    monkeypatch.setattr("zwiadbrain.cli.playwright_available", lambda: False)

    staging = _make_js_staging(tmp_path, quote, url_js)
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(staging), "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output

    # No render pass: the statement drops exactly as it did before PHASE-19.
    assert "1 input / 0 grounded" in result.output
    assert "0 js-recovered" in result.output

    page = wiki / "federal" / "bills" / "118-hr-7777.md"
    assert url_js not in page.read_text(encoding="utf-8")


def test_render_leg_history_fetches_each_url_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PHASE-20: a url shared by multiple items is fetched once per render (memoized)"""
    url = "https://www.congress.gov/congressional-record/shared"
    q1 = "The first distinct quote that appears verbatim on the shared source page here."
    q2 = "A second distinct quote that also appears verbatim on the same shared page now."
    page_body = f"<body>{q1} ... {q2}</body>"

    fetch_calls: list[str] = []

    def _counting(u: str) -> tuple[int, str]:
        fetch_calls.append(u)
        return (200, page_body) if u == url else (404, "Not Found")

    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _counting)
    monkeypatch.setattr("zwiadbrain.cli.playwright_available", lambda: False)

    bill = Bill(
        id="118-hr-8888",
        jurisdiction="US",
        title="Shared Source Act",
        bill_number="H.R. 8888",
        congress="118",
    )
    spine = LegHistory()
    statements = [
        Statement(
            speaker="A One", role="member", quote=q1, source_url=url, source_type="CREC"
        ),
        Statement(
            speaker="B Two", role="member", quote=q2, source_url=url, source_type="CREC"
        ),
    ]
    verdicts = [
        {"index": 0, "verified": True, "speaker": "A One", "quote_prefix": q1[:40]},
        {"index": 1, "verified": True, "speaker": "B Two", "quote_prefix": q2[:40]},
    ]
    payload: dict[str, object] = {
        "bill": bill.model_dump(mode="json"),
        "spine": spine.model_dump(mode="json"),
        "hearings": [],
        "statements": [s.model_dump(mode="json") for s in statements],
        "narrative": None,
        "verdicts": verdicts,
    }
    staging = tmp_path / "shared_staging.json"
    staging.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(staging), "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output

    assert "2 input / 2 grounded" in result.output
    assert fetch_calls.count(url) == 1  # fetched once despite two statements sharing the url


def test_render_leg_history_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should produce byte-identical page content on second run (write_page returns False)"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch)
    staging = _make_leg_history_staging(tmp_path)
    wiki = tmp_path / "wiki"
    args = ["render-leg-history", "--in", str(staging), "--wiki", str(wiki)]

    result1 = runner.invoke(app, args)
    assert result1.exit_code == 0, result1.output

    page = wiki / "federal" / "bills" / "118-hr-8818.md"
    first_content = page.read_text(encoding="utf-8")

    result2 = runner.invoke(app, args)
    assert result2.exit_code == 0, result2.output
    assert page.read_text(encoding="utf-8") == first_content

    # Second run should report "unchanged"
    assert "unchanged" in result2.output


def test_render_leg_history_exits_nonzero_when_bill_key_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exit non-zero with a clear error when the staging file is missing 'bill'"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"spine": {}, "hearings": [], "statements": []}), encoding="utf-8")
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(bad), "--wiki", str(wiki)])
    assert result.exit_code == 1
    # Should mention what went wrong, not raw traceback
    assert "bill" in result.output


def test_render_leg_history_exits_nonzero_when_spine_key_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exit non-zero with a clear error when the staging file is missing 'spine'"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch)
    bill = Bill(id="118-hr-1", jurisdiction="US", title="t", bill_number="H.R. 1")
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"bill": bill.model_dump(mode="json"), "statements": []}), encoding="utf-8"
    )
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(bad), "--wiki", str(wiki)])
    assert result.exit_code == 1
    assert "spine" in result.output


def test_render_leg_history_survives_invalid_url_in_statement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should drop a statement whose url makes the fetcher raise InvalidURL, exit 0, no traceback"""

    def _fetch_raises_invalid_url(url: str) -> tuple[int, str]:
        # Statement A's url triggers a real httpx.InvalidURL escaping HTTPError.
        if url == _URL_STMT_A:
            # _fetch_url must catch this and return (0, ""); this fake stands in for
            # the production fetcher confronting a malformed researcher URL.
            return _fetch_url(":://not a url")
        return _fake_fetch(url)

    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fetch_raises_invalid_url)
    staging = _make_leg_history_staging(tmp_path)
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(staging), "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output
    assert "Traceback" not in result.output

    page = wiki / "federal" / "bills" / "118-hr-8818.md"
    content = page.read_text(encoding="utf-8")
    # Statement A is dropped because its url returned status 0 (InvalidURL → (0, "")).
    assert _QUOTE_A not in content
    assert "dropped statement" in result.output


def test_fetch_url_returns_zero_on_invalid_url() -> None:
    """should return (0, '') for a malformed url instead of raising httpx.InvalidURL"""
    status, text = _fetch_url(":://not a url")
    assert status == 0
    assert text == ""


def test_render_leg_history_handles_null_statements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should treat a null 'statements' field as empty and exit cleanly, not crash"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch)
    bill = Bill(id="118-hr-1", jurisdiction="US", title="t", bill_number="H.R. 1", enacted=True)
    spine = LegHistory()
    staging = tmp_path / "null_statements.json"
    staging.write_text(
        json.dumps(
            {
                "bill": bill.model_dump(mode="json"),
                "spine": spine.model_dump(mode="json"),
                "hearings": [],
                "statements": None,
                "narrative": None,
                "verdicts": [],
            }
        ),
        encoding="utf-8",
    )
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(staging), "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output
    assert "statements: 0 input" in result.output


def test_render_leg_history_handles_null_verdicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should treat a null 'verdicts' field as empty (every statement ground-dropped), exit clean"""
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch)
    bill = Bill(id="118-hr-1", jurisdiction="US", title="t", bill_number="H.R. 1", enacted=True)
    spine = LegHistory()
    stmt = Statement(
        speaker="Rep. Lieu, Ted",
        role="sponsor",
        quote=_QUOTE_A,
        source_url=_URL_STMT_A,
        source_type="CREC",
    )
    staging = tmp_path / "null_verdicts.json"
    staging.write_text(
        json.dumps(
            {
                "bill": bill.model_dump(mode="json"),
                "spine": spine.model_dump(mode="json"),
                "hearings": [],
                "statements": [stmt.model_dump(mode="json")],
                "narrative": None,
                "verdicts": None,
            }
        ),
        encoding="utf-8",
    )
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(staging), "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output
    # No verdict means the verifier gate fails → statement ground-dropped.
    assert "1 input / 0 grounded" in result.output


def test_render_leg_history_verdict_aligned_to_surviving_statements_after_parse_drop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should apply verdicts by ORIGINAL index even when an earlier statement parse-drops

    Regression test for C1 (trust-boundary bug): when statement[0] parse-drops (e.g.
    unknown role), the surviving list shifts so that original index 1 is now at position 0
    and original index 2 is at position 1.  Before the fix, ground_items received:
        verifier_verdicts = {0: True, 1: False, 2: True}
    keyed by ORIGINAL index — but it keys by POSITION in the list it receives.  So the
    surviving statements at positions 0 and 1 would receive verdicts[0]=True and verdicts[1]=False,
    but those originated from original indices 1 and 2 respectively.  The statement that
    the verifier REJECTED (original index 1, verified=False) would be published as verified —
    a critical trust-boundary violation.

    After the fix, the CLI remaps verdicts to surviving positions before calling ground_items,
    so original-index-1 (verified=False) is correctly dropped and original-index-2 (verified=True)
    is kept.
    """
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch)

    bill = Bill(
        id="118-hr-8818", jurisdiction="US", title="t", bill_number="H.R. 8818", enacted=True
    )
    spine = LegHistory()

    # statement[0]: INVALID role — will parse-drop (unknown_role is not a valid Literal)
    # statement[1]: original index 1 — verifier says verified=FALSE → must be DROPPED
    # statement[2]: original index 2 — verifier says verified=TRUE → must be KEPT
    stmts_raw: list[object] = [
        {
            "speaker": "Rep. A",
            "role": "INVALID_ROLE_THAT_DOES_NOT_EXIST",  # causes parse-drop
            "quote": _QUOTE_A,
            "source_url": _URL_STMT_A,
            "source_type": "CREC",
            "verified": False,
        },
        {
            "speaker": "Rep. B",
            "role": "member",
            "quote": _QUOTE_A,  # quote IS present at the URL (200 response)
            "source_url": _URL_STMT_A,
            "source_type": "CREC",
            "verified": False,
        },
        {
            "speaker": "Rep. C",
            "role": "sponsor",
            "quote": _QUOTE_A,  # quote IS present at the URL (200 response)
            "source_url": _URL_STMT_A,
            "source_type": "CREC",
            "verified": False,
        },
    ]
    verdicts: list[object] = [
        # original index 0 — parse-dropped, verdict unused
        {"index": 0, "verified": True, "speaker": "Rep. A", "quote_prefix": _QUOTE_A[:40]},
        # original index 1 — verifier REJECTED
        {"index": 1, "verified": False},
        # original index 2 — verifier CONFIRMED
        {"index": 2, "verified": True, "speaker": "Rep. C", "quote_prefix": _QUOTE_A[:40]},
    ]
    staging = tmp_path / "c1_regression.json"
    staging.write_text(
        json.dumps(
            {
                "bill": bill.model_dump(mode="json"),
                "spine": spine.model_dump(mode="json"),
                "hearings": [],
                "statements": stmts_raw,
                "narrative": None,
                "verdicts": verdicts,
            }
        ),
        encoding="utf-8",
    )

    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(staging), "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output

    page = wiki / "federal" / "bills" / "118-hr-8818.md"
    content = page.read_text(encoding="utf-8") if page.exists() else ""

    # Rep. B (original index 1, verified=False) must NOT appear — verifier rejected it.
    # Before the fix this would be published because the shifted position-0 receives
    # verdicts[0]=True (belonging to the parse-dropped statement, not to Rep. B).
    assert "Rep. B" not in content, (
        "Rep. B (original index 1, verified=False) was published — "
        "verdict was applied to wrong surviving statement (C1 trust-boundary bug)"
    )

    # Rep. C (original index 2, verified=True) MUST appear — verifier confirmed it.
    assert "Rep. C" in content, (
        "Rep. C (original index 2, verified=True) was not published — "
        "correct verdict was not applied after parse-drop remapping"
    )

    # Summary: 3 input / 1 parse-drop / 1 ground-drop (Rep. B rejected) / 1 grounded (Rep. C)
    assert "statements: 3 input / 1 grounded / 1 parse-drop / 1 ground-drop" in result.output


def test_render_leg_history_input_verified_flag_does_not_bypass_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should drop a statement marked verified=true in the input when verdicts are empty

    This documents the command's central invariant: the verifier gate, not the
    researcher-supplied ``verified`` flag, decides whether a quote is grounded.
    A trusted-looking input flag must NEVER bypass independent verification.
    """
    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch)
    bill = Bill(id="118-hr-1", jurisdiction="US", title="t", bill_number="H.R. 1", enacted=True)
    spine = LegHistory()
    # Quote IS present at the (200) source url, so only the verifier gate stands
    # between this statement and the page — and verdicts is empty.
    stmt = Statement(
        speaker="Rep. Lieu, Ted",
        role="sponsor",
        quote=_QUOTE_A,
        source_url=_URL_STMT_A,
        source_type="CREC",
        verified=True,  # input claims verified — must NOT be trusted
    )
    staging = tmp_path / "verified_input.json"
    staging.write_text(
        json.dumps(
            {
                "bill": bill.model_dump(mode="json"),
                "spine": spine.model_dump(mode="json"),
                "hearings": [],
                "statements": [stmt.model_dump(mode="json")],
                "narrative": None,
                "verdicts": [],  # no independent verdict
            }
        ),
        encoding="utf-8",
    )
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(staging), "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output

    page = wiki / "federal" / "bills" / "118-hr-1.md"
    content = page.read_text(encoding="utf-8") if page.exists() else ""
    # The statement must NOT appear: input verified=true does not bypass the gate.
    assert _QUOTE_A not in content
    assert "1 input / 0 grounded" in result.output


def test_fetch_refreshable_writes_json_for_changed_bills_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should re-fetch tracked bills, write refreshable.json for those whose update_date moved"""
    import json

    import respx
    from typer.testing import CliRunner

    from zwiadbrain.cli import app
    from zwiadbrain.sources.congress import CONGRESS_API_BASE

    # Wiki with two tracked bills committed to disk.
    wiki = tmp_path / "wiki"
    (wiki / "federal" / "bills").mkdir(parents=True)
    (wiki / "federal" / "bills" / "118-hr-1.md").write_text(
        "---\n"
        "id: 118-hr-1\n"
        "jurisdiction: US\n"
        "title: Bill One\n"
        "bill_number: H.R. 1\n"
        "type: bill\n"
        "tracking: true\n"
        "update_date: '2026-05-01T00:00:00Z'\n"
        "update_date_text: '2026-05-01T00:00:00Z'\n"
        "summary_hash: hash-1\n"
        "amendments_count: 0\n"
        "---\n\n## Summary\n\nx\n",
        encoding="utf-8",
    )
    (wiki / "federal" / "bills" / "118-hr-2.md").write_text(
        "---\n"
        "id: 118-hr-2\n"
        "jurisdiction: US\n"
        "title: Bill Two\n"
        "bill_number: H.R. 2\n"
        "type: bill\n"
        "tracking: true\n"
        "update_date: '2026-05-01T00:00:00Z'\n"
        "update_date_text: '2026-05-01T00:00:00Z'\n"
        "summary_hash: hash-2\n"
        "amendments_count: 0\n"
        "---\n\n## Summary\n\ny\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONGRESS_API_KEY", "test")
    monkeypatch.setenv("GOVINFO_API_KEY", "test")

    # Bill 1 fresh: update_date unchanged → skipped.
    bill1_detail = {"bill": {"congress": 118, "type": "HR", "number": 1, "title": "Bill One",
                              "updateDate": "2026-05-01T00:00:00Z",
                              "updateDateIncludingText": "2026-05-01T00:00:00Z"}}
    # Bill 2 fresh: update_date_text advanced → refreshable, text-changed.
    bill2_detail = {"bill": {"congress": 118, "type": "HR", "number": 2, "title": "Bill Two",
                              "updateDate": "2026-05-05T00:00:00Z",
                              "updateDateIncludingText": "2026-05-05T00:00:00Z"}}
    empty_subs: dict[str, list[object]] = {"actions": [], "amendments": [], "textVersions": [],
                                           "summaries": [], "relatedBills": []}

    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        for n, payload in [(1, bill1_detail), (2, bill2_detail)]:
            mock.get(f"/bill/118/hr/{n}").respond(json=payload)
            mock.get(f"/bill/118/hr/{n}/actions").respond(json={"actions": empty_subs["actions"]})
            mock.get(f"/bill/118/hr/{n}/amendments").respond(
                json={"amendments": empty_subs["amendments"]}
            )
            mock.get(f"/bill/118/hr/{n}/text").respond(
                json={"textVersions": empty_subs["textVersions"]}
            )
            mock.get(f"/bill/118/hr/{n}/summaries").respond(
                json={"summaries": empty_subs["summaries"]}
            )
            mock.get(f"/bill/118/hr/{n}/relatedbills").respond(
                json={"relatedBills": empty_subs["relatedBills"]}
            )

        out_dir = tmp_path / "run"
        result = CliRunner().invoke(app, [
            "fetch-refreshable", "--wiki", str(wiki), "--out", str(out_dir),
        ])
    assert result.exit_code == 0, result.output
    refreshable = json.loads((out_dir / "refreshable.json").read_text(encoding="utf-8"))
    ids = [r["bill_id"] for r in refreshable]
    assert ids == ["118-hr-2"]
    entry = refreshable[0]
    assert entry["needs_classifier"] is True
    assert entry["needs_summarizer"] is True
    assert entry["changed_amendment_numbers"] == []


def test_fetch_refreshable_writes_empty_list_when_nothing_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should write refreshable.json with [] when no tracked bill moved"""
    import json

    import respx
    from typer.testing import CliRunner

    from zwiadbrain.cli import app
    from zwiadbrain.sources.congress import CONGRESS_API_BASE

    wiki = tmp_path / "wiki"
    (wiki / "federal" / "bills").mkdir(parents=True)
    (wiki / "federal" / "bills" / "118-hr-1.md").write_text(
        "---\n"
        "id: 118-hr-1\njurisdiction: US\ntitle: Bill One\nbill_number: H.R. 1\n"
        "type: bill\ntracking: true\nupdate_date: '2026-05-01T00:00:00Z'\n---\n\nx\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONGRESS_API_KEY", "test")
    monkeypatch.setenv("GOVINFO_API_KEY", "test")

    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        mock.get("/bill/118/hr/1").respond(
            json={"bill": {"congress": 118, "type": "HR", "number": 1, "title": "Bill One",
                            "updateDate": "2026-05-01T00:00:00Z"}}
        )
        for sub in ("actions", "amendments", "text", "summaries", "relatedbills"):
            key = {"actions": "actions", "amendments": "amendments", "text": "textVersions",
                   "summaries": "summaries", "relatedbills": "relatedBills"}[sub]
            mock.get(f"/bill/118/hr/1/{sub}").respond(json={key: []})
        out_dir = tmp_path / "run"
        result = CliRunner().invoke(app, [
            "fetch-refreshable", "--wiki", str(wiki), "--out", str(out_dir),
        ])
    assert result.exit_code == 0, result.output
    refreshable = json.loads((out_dir / "refreshable.json").read_text(encoding="utf-8"))
    assert refreshable == []


def test_render_refreshed_applies_preservation_and_renders(tmp_path: Path) -> None:
    """should re-attach prev leg_history, write the page, and report counts"""
    import json

    from typer.testing import CliRunner

    from zwiadbrain.cli import app

    # Fresh bill (from fetch-refreshable) — enacted, with re-derived spine, no hearings.
    fresh = {
        "id": "118-hr-1", "jurisdiction": "US", "title": "Bill One",
        "bill_number": "H.R. 1", "type": "bill", "tracking": True, "enacted": True,
        "leg_history": {
            "versions": [],
            "committee_reports": [
                {"citation": "H. Rept. 1", "url": "https://example.test/c"}
            ],
            "floor_consideration": [], "votes": [], "hearings": [], "statements": [],
            "narrative": None, "conference": None, "enactment": None,
        },
        "topics": ["ai"],
        "summary": "Refreshed summary.",
    }
    # Prev (committed page) — has a hearing + narrative that must survive.
    prev = {
        **fresh,
        "summary": "Old summary.",
        "leg_history": {
            "versions": [], "committee_reports": [],
            "floor_consideration": [], "votes": [],
            "hearings": [{"title": "Hearing X", "url": "https://example.test/h"}],
            "statements": [],
            "narrative": "The arc of the debate.",
            "conference": None, "enactment": None,
        },
    }
    refreshed = [{
        "bill_id": "118-hr-1",
        "prev": prev,
        "bill": fresh,                  # fresh + subagent outputs merged by the slash command
        "classifier_in_scope": True,
        "classifier_rationale": "still about AI",
    }]
    run = tmp_path / "run"
    run.mkdir()
    (run / "refreshed.json").write_text(json.dumps(refreshed), encoding="utf-8")
    wiki = tmp_path / "wiki"

    result = CliRunner().invoke(app, [
        "render-refreshed", "--in", str(run / "refreshed.json"), "--wiki", str(wiki),
        "--db", str(tmp_path / "idx.sqlite"),
    ])
    assert result.exit_code == 0, result.output

    page = (wiki / "federal" / "bills" / "118-hr-1.md").read_text(encoding="utf-8")
    # research carried from prev
    assert "Hearing X" in page
    assert "The arc of the debate." in page
    # spine taken from fresh
    assert "H. Rept. 1" in page
    # summary refreshed
    assert "Refreshed summary." in page
    # report mentions the count
    assert "refreshed 1" in result.output


def test_render_refreshed_flips_out_when_classifier_out_of_scope(tmp_path: Path) -> None:
    """should set tracking=False and emit the audit marker on IN→OUT flip"""
    import json

    from typer.testing import CliRunner

    from zwiadbrain.cli import app

    refreshed = [{
        "bill_id": "118-hr-9",
        "prev": {
            "id": "118-hr-9", "jurisdiction": "US", "title": "Old Title",
            "bill_number": "H.R. 9", "type": "bill", "tracking": True, "topics": ["ai"],
        },
        "bill": {
            "id": "118-hr-9", "jurisdiction": "US", "title": "Old Title",
            "bill_number": "H.R. 9", "type": "bill", "tracking": True, "topics": ["ai"],
            "summary": "Updated",
        },
        "classifier_in_scope": False,
        "classifier_rationale": "telehealth scope drift",
    }]
    run = tmp_path / "run"
    run.mkdir()
    (run / "refreshed.json").write_text(json.dumps(refreshed), encoding="utf-8")
    wiki = tmp_path / "wiki"

    result = CliRunner().invoke(app, [
        "render-refreshed", "--in", str(run / "refreshed.json"), "--wiki", str(wiki),
        "--db", str(tmp_path / "idx.sqlite"),
    ])
    assert result.exit_code == 0, result.output

    page = (wiki / "federal" / "bills" / "118-hr-9.md").read_text(encoding="utf-8")
    assert "tracking: false" in page
    assert "<!-- zwiadbrain:flipped-out " in page
    assert "telehealth scope drift" in page
    # topics preserved (the prior classification's record stands)
    assert "ai" in page
    assert "1 flipped-out" in result.output


def test_render_refreshed_carries_prev_leg_history_when_bill_has_none(tmp_path: Path) -> None:
    """should carry prev.leg_history through unchanged when fresh bill has none

    Defensive case: a non-enacted fresh bill has no spine, but prev had
    research that must not be lost on refresh.
    """
    import json

    from typer.testing import CliRunner

    from zwiadbrain.cli import app

    fresh = {
        "id": "118-hr-5", "jurisdiction": "US", "title": "Bill Five",
        "bill_number": "H.R. 5", "type": "bill", "tracking": True, "enacted": False,
        "topics": ["ai"],
        "summary": "Refreshed.",
        # leg_history intentionally omitted — fresh non-enacted bill has no spine
    }
    prev = {
        **fresh,
        "summary": "Old.",
        "leg_history": {
            "versions": [], "committee_reports": [],
            "floor_consideration": [], "votes": [],
            "hearings": [{"title": "Old Hearing", "url": "https://example.test/h"}],
            "statements": [],
            "narrative": "Old narrative we must keep.",
            "conference": None, "enactment": None,
        },
    }
    refreshed = [{
        "bill_id": "118-hr-5",
        "prev": prev,
        "bill": fresh,
        "classifier_in_scope": True,
        "classifier_rationale": "",
    }]
    run = tmp_path / "run"
    run.mkdir()
    (run / "refreshed.json").write_text(json.dumps(refreshed), encoding="utf-8")
    wiki = tmp_path / "wiki"

    result = CliRunner().invoke(app, [
        "render-refreshed", "--in", str(run / "refreshed.json"), "--wiki", str(wiki),
        "--db", str(tmp_path / "idx.sqlite"),
    ])
    assert result.exit_code == 0, result.output

    page = (wiki / "federal" / "bills" / "118-hr-5.md").read_text(encoding="utf-8")
    # prev's research carried through onto the fresh bill
    assert "Old Hearing" in page
    assert "Old narrative we must keep." in page


def test_render_refreshed_reports_clean_error_on_missing_key(tmp_path: Path) -> None:
    """should exit with code 1 and a clean message when entry lacks 'bill' or 'prev'"""
    import json

    from typer.testing import CliRunner

    from zwiadbrain.cli import app

    # Entry missing 'bill'
    refreshed = [{"bill_id": "118-hr-1", "prev": {"id": "118-hr-1", "jurisdiction": "US",
                  "title": "x", "bill_number": "H.R. 1", "type": "bill"}}]
    run = tmp_path / "run"
    run.mkdir()
    (run / "refreshed.json").write_text(json.dumps(refreshed), encoding="utf-8")

    result = CliRunner().invoke(app, [
        "render-refreshed", "--in", str(run / "refreshed.json"), "--wiki", str(tmp_path / "wiki"),
        "--db", str(tmp_path / "idx.sqlite"),
    ])
    assert result.exit_code == 1
    assert "missing required key 'bill'" in result.output


def test_fetch_refreshable_rejects_malformed_bill_id(tmp_path: Path) -> None:
    """should raise ConfigError (not a bare unpacking ValueError) on a non-three-segment id"""
    from zwiadbrain.exceptions import ConfigError
    from zwiadbrain.pipeline.ids import parse_bill_id

    # The cli path delegates id parsing to parse_bill_id; a 4-segment state id
    # must surface as ConfigError, the type fetch_refreshable's AppError handler catches.
    with pytest.raises(ConfigError):
        parse_bill_id("us-ca-sb-362")


def test_fetch_state_candidates_stages_enriched_bills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should search a state, enrich the top results, and stage candidates.json"""
    monkeypatch.setenv("LEGISCAN_API_KEY", "lk-test")
    fix = Path(__file__).parent / "fixtures" / "legiscan"
    search = json.loads((fix / "getSearchRaw.json").read_text(encoding="utf-8"))
    bill = json.loads((fix / "getBill.json").read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        op = request.url.params.get("op", "")
        return httpx.Response(200, json={"getSearchRaw": search, "getBill": bill}[op])

    out = tmp_path / "run"
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=LEGISCAN_API_BASE).mock(side_effect=handler)
        result = runner.invoke(app, [
            "fetch-state-candidates", "--state", "ca", "--limit", "1",
            "--query", "privacy", "--out", str(out),
        ])
    assert result.exit_code == 0, result.output
    staged = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert len(staged) == 1
    assert staged[0]["id"] == "ca-2023-sb-362"


def _fake_state_enrich(source: object, candidate: Candidate) -> Bill:
    """Stub enrich: build a state Bill from the candidate (no HTTP)."""
    return Bill(
        id=f"ca-2019-{candidate.native_id}",
        jurisdiction=candidate.jurisdiction,
        title=candidate.title or "x",
        bill_number=candidate.native_id,
        enacted=True,
        legiscan_bill_id=int(candidate.native_id),
    )


def test_fetch_state_enacted_keeps_topical_enacted_laws(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should resolve --year to a session, keep enacted+topical bills, stage them"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LEGISCAN_API_KEY", "test-key")
    monkeypatch.setattr("zwiadbrain.cli.enrich", _fake_state_enrich)
    out = tmp_path / "run"
    with respx.mock(assert_all_called=False) as mock:
        _route_legiscan(mock, {
            "getSessionList": _legiscan_fixture("getSessionList.json"),
            "getMasterList": _legiscan_fixture("getMasterList.json"),
        })
        result = runner.invoke(
            app,
            ["fetch-state-enacted-candidates", "--state", "ca", "--year", "2019",
             "--topics", str(_TOPICS), "--out", str(out)],
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    # AB1 (status4, AI) kept; AB99 (status4, off-topic) dropped by recall; SB200 (status6) excluded.
    assert [b["legiscan_bill_id"] for b in data] == [1132030]


def test_fetch_state_enacted_classify_all_stages_all_enacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--classify-all stages every enacted (status==4) bill, skipping recall"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LEGISCAN_API_KEY", "test-key")
    monkeypatch.setattr("zwiadbrain.cli.enrich", _fake_state_enrich)
    out = tmp_path / "run"
    with respx.mock(assert_all_called=False) as mock:
        _route_legiscan(mock, {
            "getSessionList": _legiscan_fixture("getSessionList.json"),
            "getMasterList": _legiscan_fixture("getMasterList.json"),
        })
        result = runner.invoke(
            app,
            ["fetch-state-enacted-candidates", "--state", "ca", "--year", "2019",
             "--classify-all", "--out", str(out)],
        )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert [b["legiscan_bill_id"] for b in data] == [1132030, 1132099]  # both enacted, no recall


def test_fetch_state_enacted_errors_when_candidates_exceed_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should fail loudly instead of silently dropping enacted bills beyond --limit"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LEGISCAN_API_KEY", "test-key")
    monkeypatch.setattr("zwiadbrain.cli.enrich", _fake_state_enrich)
    out = tmp_path / "run"
    with respx.mock(assert_all_called=False) as mock:
        _route_legiscan(mock, {
            "getSessionList": _legiscan_fixture("getSessionList.json"),
            "getMasterList": _legiscan_fixture("getMasterList.json"),
        })
        result = runner.invoke(
            app,
            ["fetch-state-enacted-candidates", "--state", "ca", "--year", "2019",
             "--classify-all", "--limit", "1", "--out", str(out)],
        )
    assert result.exit_code == 1
    assert "--limit" in result.output
    assert not (out / "candidates.json").exists()


def test_fetch_state_enacted_errors_without_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exit non-zero with a clear error when LEGISCAN_API_KEY is unset"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LEGISCAN_API_KEY", raising=False)
    result = runner.invoke(
        app, ["fetch-state-enacted-candidates", "--state", "ca", "--year", "2019"]
    )
    assert result.exit_code == 1
    assert "LEGISCAN_API_KEY" in result.output


def test_fetch_state_enacted_skip_existing_drops_cached_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--skip-existing drops a recall-kept enacted bill cached as a reject (D82)"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LEGISCAN_API_KEY", "test-key")
    monkeypatch.setattr("zwiadbrain.cli.enrich", _fake_state_enrich)
    wiki = tmp_path / "wiki"
    # AB1 (bill_id 1132030, change_hash hashA) is the only recall survivor; cache it
    # as a reject with its unchanged cursor so skip-existing drops it.
    write_reject_ledger(
        wiki / ".rejects" / "state.json",
        {"1132030": RejectEntry(cursor="hashA", id="ca-2019-1132030")},
    )
    out = tmp_path / "run"
    with respx.mock(assert_all_called=False) as mock:
        _route_legiscan(mock, {
            "getSessionList": _legiscan_fixture("getSessionList.json"),
            "getMasterList": _legiscan_fixture("getMasterList.json"),
        })
        result = runner.invoke(
            app,
            ["fetch-state-enacted-candidates", "--state", "ca", "--year", "2019",
             "--skip-existing", "--wiki", str(wiki), "--topics", str(_TOPICS), "--out", str(out)],
        )
    assert result.exit_code == 0, result.output
    assert json.loads((out / "candidates.json").read_text(encoding="utf-8")) == []
    assert "cached-reject" in result.output


def test_fetch_state_enacted_errors_when_no_session_covers_year(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exit non-zero when no session covers the requested year"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LEGISCAN_API_KEY", "test-key")
    with respx.mock(assert_all_called=False) as mock:
        _route_legiscan(mock, {"getSessionList": _legiscan_fixture("getSessionList.json")})
        result = runner.invoke(
            app, ["fetch-state-enacted-candidates", "--state", "ca", "--year", "1990"]
        )
    assert result.exit_code == 1
    assert "no ca session" in result.output


def test_fetch_bill_stages_federal_bill_when_no_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should fetch one federal bill from Congress.gov into a one-item classified.json"""
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    out = tmp_path / "run"
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        _route_backfill(mock)
        result = runner.invoke(app, ["fetch-bill", "--bill", "118/hr/8818", "--out", str(out)])
    assert result.exit_code == 0, result.output
    staged = json.loads((out / "classified.json").read_text(encoding="utf-8"))
    assert len(staged) == 1
    assert Bill.model_validate(staged[0]).id == "118-hr-8818"


def test_fetch_bill_stages_state_bill_when_state_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should fetch one state bill via LegiScan when --state is given"""
    monkeypatch.setenv("LEGISCAN_API_KEY", "lk-test")
    fix = Path(__file__).parent / "fixtures" / "legiscan"
    bill = json.loads((fix / "getBill.json").read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        op = request.url.params.get("op", "")
        return httpx.Response(200, json={"getBill": bill}[op])

    out = tmp_path / "run"
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=LEGISCAN_API_BASE).mock(side_effect=handler)
        result = runner.invoke(
            app, ["fetch-bill", "--bill", "1904800", "--state", "ca", "--out", str(out)]
        )
    assert result.exit_code == 0, result.output
    staged = json.loads((out / "classified.json").read_text(encoding="utf-8"))
    assert len(staged) == 1
    assert Bill.model_validate(staged[0]).id == "ca-2023-sb-362"


def test_reindex_skips_corrupt_page_and_indexes_the_rest(tmp_path: Path) -> None:
    """should index the valid page and skip a page whose frontmatter YAML is malformed"""
    wiki = tmp_path / "wiki"
    write_page(Bill(id="118-hr-1", jurisdiction="US", title="Good", bill_number="H.R. 1"), wiki)
    (wiki / "federal" / "bills" / "corrupt.md").write_text(
        "---\nid: 118-hr-2\njurisdiction: {US\n---\nbody", encoding="utf-8"
    )
    result = runner.invoke(
        app, ["reindex", "--wiki", str(wiki), "--db", str(tmp_path / "i.sqlite")]
    )
    assert result.exit_code == 0, result.output
    assert "reindexed 1 pages" in result.stdout


def test_render_leg_history_stamps_summary_hash_on_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should write a summary_hash into frontmatter for a leg-history page with a summary"""
    from zwiadbrain.pipeline.refresh import summary_hash
    from zwiadbrain.wiki.schema import from_page

    monkeypatch.setattr("zwiadbrain.cli._fetch_url", _fake_fetch)
    bill = Bill(
        id="118-hr-8818", jurisdiction="US", title="t", bill_number="H.R. 8818",
        congress="118", enacted=True, summary="A Claude-written summary of the Act.",
    )
    spine = LegHistory()
    staging = tmp_path / "lh_hash.json"
    staging.write_text(
        json.dumps({
            "bill": bill.model_dump(mode="json"),
            "spine": spine.model_dump(mode="json"),
            "hearings": [], "statements": [], "narrative": None, "verdicts": [],
        }),
        encoding="utf-8",
    )
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-leg-history", "--in", str(staging), "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output
    page = (wiki / "federal" / "bills" / "118-hr-8818.md").read_text(encoding="utf-8")
    parsed = from_page(page)
    assert isinstance(parsed, Bill)
    assert parsed.summary_hash == summary_hash("A Claude-written summary of the Act.")
    assert parsed.summary_hash is not None


def test_render_refreshed_recomputes_cursors_deterministically(tmp_path: Path) -> None:
    """should re-stamp summary_hash/amendments_count from the merged bill, ignoring stale input"""
    import json

    from typer.testing import CliRunner

    from zwiadbrain.cli import app
    from zwiadbrain.pipeline.refresh import summary_hash
    from zwiadbrain.wiki.schema import from_page

    fresh = {
        "id": "118-hr-1", "jurisdiction": "US", "title": "Bill One",
        "bill_number": "H.R. 1", "type": "bill", "tracking": True,
        "topics": ["ai"], "summary": "Refreshed summary text.",
        "summary_hash": "STALE-HASH-FROM-SUBAGENT", "amendments_count": 99, "amendments": [],
    }
    prev = {**fresh, "summary": "Old summary.", "summary_hash": "old", "amendments_count": 0}
    refreshed = [{
        "bill_id": "118-hr-1", "prev": prev, "bill": fresh,
        "classifier_in_scope": True, "classifier_rationale": "still about AI",
    }]
    run = tmp_path / "run"
    run.mkdir()
    (run / "refreshed.json").write_text(json.dumps(refreshed), encoding="utf-8")
    wiki = tmp_path / "wiki"
    result = CliRunner().invoke(app, [
        "render-refreshed", "--in", str(run / "refreshed.json"), "--wiki", str(wiki),
        "--db", str(tmp_path / "idx.sqlite"),
    ])
    assert result.exit_code == 0, result.output
    parsed = from_page((wiki / "federal" / "bills" / "118-hr-1.md").read_text(encoding="utf-8"))
    assert isinstance(parsed, Bill)
    assert parsed.summary_hash == summary_hash("Refreshed summary text.")
    assert parsed.summary_hash != "STALE-HASH-FROM-SUBAGENT"
    assert parsed.amendments_count == 0


def test_fetch_refreshable_skips_bad_page_and_processes_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should skip a page with a malformed id, log it to stderr, and still process valid bills"""
    import respx

    from zwiadbrain.sources.congress import CONGRESS_API_BASE

    wiki = tmp_path / "wiki"
    (wiki / "federal" / "bills").mkdir(parents=True)
    # Malformed id: "118-hr" has only two segments -> parse_bill_id raises ConfigError.
    (wiki / "federal" / "bills" / "bad.md").write_text(
        "---\nid: 118-hr\njurisdiction: US\ntitle: Bad\nbill_number: H.R.\n"
        "type: bill\ntracking: true\nupdate_date: '2026-05-01T00:00:00Z'\n---\n\nx\n",
        encoding="utf-8",
    )
    # Valid, changed bill.
    (wiki / "federal" / "bills" / "118-hr-2.md").write_text(
        "---\nid: 118-hr-2\njurisdiction: US\ntitle: Bill Two\nbill_number: H.R. 2\n"
        "type: bill\ntracking: true\nupdate_date: '2026-05-01T00:00:00Z'\n"
        "update_date_text: '2026-05-01T00:00:00Z'\nsummary_hash: hash-2\n---\n\ny\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONGRESS_API_KEY", "test")
    monkeypatch.setenv("GOVINFO_API_KEY", "test")
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        mock.get("/bill/118/hr/2").respond(
            json={"bill": {"congress": 118, "type": "HR", "number": 2, "title": "Bill Two",
                           "updateDate": "2026-05-05T00:00:00Z",
                           "updateDateIncludingText": "2026-05-05T00:00:00Z"}}
        )
        for sub, key in [("actions", "actions"), ("amendments", "amendments"),
                         ("text", "textVersions"), ("summaries", "summaries"),
                         ("relatedbills", "relatedBills")]:
            mock.get(f"/bill/118/hr/2/{sub}").respond(json={key: []})
        out_dir = tmp_path / "run"
        result = runner.invoke(
            app, ["fetch-refreshable", "--wiki", str(wiki), "--out", str(out_dir)]
        )
    assert result.exit_code == 0, result.output
    refreshable = json.loads((out_dir / "refreshable.json").read_text(encoding="utf-8"))
    assert [r["bill_id"] for r in refreshable] == ["118-hr-2"]
    assert "skipped" in result.output
    assert "bad.md" in result.output
    assert "1 skipped" in result.output


def test_fetch_leg_history_rejects_malformed_bill_arg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exit 1 with a clean ConfigError when --bill is not congress/type/number"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    monkeypatch.setenv("GOVINFO_API_KEY", "test-govinfo-key")
    result = runner.invoke(
        app, ["fetch-leg-history", "--bill", "foo", "--out", str(tmp_path / "r")]
    )
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output
    assert not (tmp_path / "r" / "leghistory.json").exists()


def test_reindex_command_reports_store_error_without_traceback(tmp_path: Path) -> None:
    """should exit 1 with a clean message when the index path is an unwritable directory"""
    runner = CliRunner()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    # Point --db at a directory: sqlite cannot open it as a file, surfacing StoreError.
    bad_db = tmp_path / "adir"
    bad_db.mkdir()
    result = runner.invoke(app, ["reindex", "--wiki", str(wiki), "--db", str(bad_db)])
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback" not in result.output


def test_backfill_force_retracks_single_flipped_out_bill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should re-fetch a single bill and write it re-tracked (tracking=true, no flip audit)"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    wiki = tmp_path / "wiki"
    with respx.mock(base_url=CONGRESS_API_BASE, assert_all_called=False) as mock:
        base = "/bill/118/hr/8818"
        mock.get(base).respond(json=_fixture("detail.json"))
        mock.get(f"{base}/actions").respond(json=_fixture("actions.json"))
        mock.get(f"{base}/amendments").respond(json=_fixture("amendments.json"))
        mock.get(f"{base}/text").respond(json=_fixture("text.json"))
        mock.get(f"{base}/summaries").respond(json=_fixture("summaries.json"))
        mock.get(f"{base}/relatedbills").respond(json=_fixture("relatedbills.json"))
        result = runner.invoke(
            app, ["backfill", "--congress", "118", "--force", "118/hr/8818", "--wiki", str(wiki)]
        )
    assert result.exit_code == 0, result.output
    page = (wiki / "federal" / "bills" / "118-hr-8818.md").read_text(encoding="utf-8")
    assert "tracking: true" in page or "tracking:" not in page  # default True is omitted
    assert "flipped-out" not in page


def test_backfill_rejects_nonpositive_limit() -> None:
    """should exit 2 when --limit is below 1"""
    result = runner.invoke(app, ["backfill", "--congress", "118", "--limit", "0"])
    assert result.exit_code == 2


def test_fetch_candidates_rejects_nonpositive_congress() -> None:
    """should exit 2 when --congress is below 1"""
    result = runner.invoke(app, ["fetch-candidates", "--congress", "0", "--limit", "1"])
    assert result.exit_code == 2


def test_fetch_state_refreshable_detects_changed_bill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should diff masterlist change_hash and stage only the changed tracked bill"""
    monkeypatch.setenv("LEGISCAN_API_KEY", "lk-test")
    fix = Path(__file__).parent / "fixtures" / "legiscan"
    masterlist = json.loads((fix / "getMasterListRaw.json").read_text(encoding="utf-8"))
    bill = json.loads((fix / "getBill.json").read_text(encoding="utf-8"))

    # Render a tracked CA page whose stored change_hash is STALE vs the masterlist.
    from zwiadbrain.pipeline.render import write_page
    from zwiadbrain.sources.legiscan import LegiScanSource
    src = LegiScanSource("lk-test", "ca")
    page_bill = src._to_bill(bill["bill"])  # noqa: SLF001 — building a fixture page  # pyright: ignore[reportPrivateUsage]
    page_bill = page_bill.model_copy(update={"change_hash": "abc123-OLD"})
    wiki = tmp_path / "wiki"
    write_page(page_bill, wiki)

    def handler(request: httpx.Request) -> httpx.Response:
        op = request.url.params.get("op", "")
        return httpx.Response(200, json={"getMasterListRaw": masterlist, "getBill": bill}[op])

    out = tmp_path / "run"
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=LEGISCAN_API_BASE).mock(side_effect=handler)
        result = runner.invoke(app, [
            "fetch-state-refreshable", "--wiki", str(wiki), "--out", str(out),
        ])
    assert result.exit_code == 0, result.output
    staged = json.loads((out / "refreshable.json").read_text(encoding="utf-8"))
    assert len(staged) == 1
    assert staged[0]["bill_id"] == "ca-2023-sb-362"
    assert staged[0]["needs_summarizer"] is True


def _tmp_topics(tmp_path: Path, *, scope_version: str | None = "D-TEST") -> Path:
    """A minimal valid topics.yaml; scope_version=None omits the key (pre-D96 shape)."""
    version_line = f'scope_version: "{scope_version}"\n' if scope_version else ""
    path = tmp_path / "topics.yaml"
    path.write_text(f"topics:\n  ai:\n    seeds: [ai]\n{version_line}", encoding="utf-8")
    return path


def test_record_rejects_federal_writes_ledger(tmp_path: Path) -> None:
    """should derive the federal cursor and stamp the scope_version into federal.json"""
    rejects = tmp_path / "rejects.json"
    rejects.write_text(
        json.dumps([
            {
                "id": "119-hr-9", "jurisdiction": "US", "title": "Boring",
                "bill_number": "H.R. 9", "update_date": "2026-01-01",
                "update_date_text": "2026-02-02",
            }
        ]),
        encoding="utf-8",
    )
    cache = tmp_path / ".rejects"
    result = runner.invoke(
        app,
        ["record-rejects", "--in", str(rejects), "--scope", "federal",
         "--cache-dir", str(cache), "--topics", str(_tmp_topics(tmp_path))],
    )
    assert result.exit_code == 0, result.output
    led = json.loads((cache / "federal.json").read_text(encoding="utf-8"))
    assert led == {"119-hr-9": {"cursor": "2026-02-02", "scope_version": "D-TEST"}}


def test_record_rejects_omits_stamp_when_taxonomy_unversioned(tmp_path: Path) -> None:
    """should serialize no scope_version key when the taxonomy has none (pre-D96 shape)"""
    rejects = tmp_path / "rejects.json"
    rejects.write_text(
        json.dumps([
            {"id": "119-hr-9", "jurisdiction": "US", "title": "B",
             "bill_number": "H.R. 9", "update_date": "2026-01-01"}
        ]),
        encoding="utf-8",
    )
    cache = tmp_path / ".rejects"
    result = runner.invoke(
        app,
        ["record-rejects", "--in", str(rejects), "--scope", "federal",
         "--cache-dir", str(cache),
         "--topics", str(_tmp_topics(tmp_path, scope_version=None))],
    )
    assert result.exit_code == 0, result.output
    led = json.loads((cache / "federal.json").read_text(encoding="utf-8"))
    assert "scope_version" not in led["119-hr-9"]


def test_record_rejects_is_idempotent_byte_identical(tmp_path: Path) -> None:
    """should produce a byte-identical ledger when the same reject is recorded twice"""
    rejects = tmp_path / "rejects.json"
    rejects.write_text(
        json.dumps([
            {"id": "119-hr-9", "jurisdiction": "US", "title": "B",
             "bill_number": "H.R. 9", "update_date": "2026-01-01"}
        ]),
        encoding="utf-8",
    )
    cache = tmp_path / ".rejects"
    args = ["record-rejects", "--in", str(rejects), "--scope", "federal",
            "--cache-dir", str(cache), "--topics", str(_tmp_topics(tmp_path))]
    runner.invoke(app, args)
    first = (cache / "federal.json").read_bytes()
    runner.invoke(app, args)
    assert (cache / "federal.json").read_bytes() == first


def test_record_rejects_rejects_unknown_scope(tmp_path: Path) -> None:
    """should exit non-zero on an invalid --scope"""
    rejects = tmp_path / "r.json"
    rejects.write_text("[]", encoding="utf-8")
    result = runner.invoke(
        app,
        ["record-rejects", "--in", str(rejects), "--scope", "county",
         "--cache-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "scope" in result.output


# ---------------------------------------------------------------------------
# stale-rejects (D96): surface/clear rejects recorded under superseded scope rules
# ---------------------------------------------------------------------------


def _stale_ledger(tmp_path: Path) -> Path:
    """A state ledger with one current, one stale, and one pre-versioning entry."""
    cache = tmp_path / ".rejects"
    cache.mkdir()
    (cache / "state.json").write_text(
        json.dumps({
            "111": {"cursor": "h1", "id": "ny-2021-a-1", "scope_version": "D-TEST"},
            "222": {"cursor": "h2", "id": "ny-2021-a-2", "scope_version": "D-OLD"},
            "333": {"cursor": "h3", "id": "ny-2021-a-3"},
        }),
        encoding="utf-8",
    )
    return cache


def test_stale_rejects_reports_stale_and_unknown_counts(tmp_path: Path) -> None:
    """should report stale (version mismatch) and unknown (pre-versioning) buckets"""
    cache = _stale_ledger(tmp_path)
    result = runner.invoke(
        app,
        ["stale-rejects", "--scope", "state", "--cache-dir", str(cache),
         "--topics", str(_tmp_topics(tmp_path))],
    )
    assert result.exit_code == 0, result.output
    assert "1 stale" in result.output
    assert "1 unknown" in result.output
    assert "222" in result.output  # the stale entry is listed
    assert "--clear" in result.output  # hints at the removal flag


def test_stale_rejects_clear_removes_only_stale(tmp_path: Path) -> None:
    """should clear version-mismatched entries but leave current and unknown intact"""
    cache = _stale_ledger(tmp_path)
    result = runner.invoke(
        app,
        ["stale-rejects", "--scope", "state", "--cache-dir", str(cache),
         "--topics", str(_tmp_topics(tmp_path)), "--clear"],
    )
    assert result.exit_code == 0, result.output
    led = json.loads((cache / "state.json").read_text(encoding="utf-8"))
    assert set(led) == {"111", "333"}  # stale 222 gone; unknown 333 guarded


def test_stale_rejects_include_unknown_clears_preversioning(tmp_path: Path) -> None:
    """should clear pre-versioning entries only under the explicit --include-unknown flag"""
    cache = _stale_ledger(tmp_path)
    result = runner.invoke(
        app,
        ["stale-rejects", "--scope", "state", "--cache-dir", str(cache),
         "--topics", str(_tmp_topics(tmp_path)), "--clear", "--include-unknown"],
    )
    assert result.exit_code == 0, result.output
    led = json.loads((cache / "state.json").read_text(encoding="utf-8"))
    assert set(led) == {"111"}  # only the current-version entry survives


def test_stale_rejects_key_selects_explicit_entries(tmp_path: Path) -> None:
    """should clear exactly the named keys regardless of their stamp"""
    cache = _stale_ledger(tmp_path)
    result = runner.invoke(
        app,
        ["stale-rejects", "--scope", "state", "--cache-dir", str(cache),
         "--topics", str(_tmp_topics(tmp_path)), "--key", "333", "--clear"],
    )
    assert result.exit_code == 0, result.output
    led = json.loads((cache / "state.json").read_text(encoding="utf-8"))
    assert set(led) == {"111", "222"}  # only the named pre-versioning key removed


def test_stale_rejects_unknown_key_exits_nonzero(tmp_path: Path) -> None:
    """should fail loud when a named --key is not in the ledger"""
    cache = _stale_ledger(tmp_path)
    result = runner.invoke(
        app,
        ["stale-rejects", "--scope", "state", "--cache-dir", str(cache),
         "--topics", str(_tmp_topics(tmp_path)), "--key", "999"],
    )
    assert result.exit_code == 1
    assert "999" in result.output


def test_stale_rejects_without_clear_is_readonly(tmp_path: Path) -> None:
    """should not modify the ledger when --clear is absent"""
    cache = _stale_ledger(tmp_path)
    before = (cache / "state.json").read_bytes()
    runner.invoke(
        app,
        ["stale-rejects", "--scope", "state", "--cache-dir", str(cache),
         "--topics", str(_tmp_topics(tmp_path))],
    )
    assert (cache / "state.json").read_bytes() == before


def test_stale_rejects_rejects_unknown_scope(tmp_path: Path) -> None:
    """should exit non-zero on an invalid --scope"""
    result = runner.invoke(
        app,
        ["stale-rejects", "--scope", "county", "--cache-dir", str(tmp_path),
         "--topics", str(_tmp_topics(tmp_path))],
    )
    assert result.exit_code == 1
    assert "scope" in result.output


def test_fetch_candidates_skip_existing_drops_cached_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should drop a federal candidate cached as a reject whose cursor is unchanged (D82)"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONGRESS_API_KEY", "test-key")
    wiki = tmp_path / "wiki"
    write_reject_ledger(
        wiki / ".rejects" / "federal.json",
        {"119-hr-9": RejectEntry(cursor="2026-01-01")},
    )

    def _fake_discover(
        self: CongressSource, *, congress: int | None = None,
        since: object = None, limit: int = 20, max_pages: int = 1,
    ) -> list[Candidate]:
        return [
            Candidate(
                source="congress", native_id="119/hr/9", jurisdiction="US",
                title="Boring Act", update_date="2026-01-01",
            )
        ]

    monkeypatch.setattr(CongressSource, "discover", _fake_discover)
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        ["fetch-candidates", "--congress", "119", "--limit", "5", "--seed", "boring",
         "--skip-existing", "--wiki", str(wiki), "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert json.loads((out / "candidates.json").read_text(encoding="utf-8")) == []
    assert "cached-reject" in result.output


def test_existing_state_bill_ids_reads_legiscan_id_from_frontmatter(tmp_path: Path) -> None:
    """should harvest tracked state bills' LegiScan ids from frontmatter, skipping sidecars"""
    from zwiadbrain.cli import _existing_state_bill_ids  # pyright: ignore[reportPrivateUsage]

    wiki = tmp_path / "wiki"
    write_page(
        Bill(
            id="ca-2025-ab-7", jurisdiction="US-CA", title="t",
            bill_number="AB 7", legiscan_bill_id=777,
        ),
        wiki,
    )
    (wiki / "states" / "ca" / "bills" / "ca-2025-ab-7.text.md").write_text(
        "sidecar", encoding="utf-8"
    )
    assert _existing_state_bill_ids(wiki, "ca") == {"777"}


def test_existing_state_bill_ids_missing_dir_is_empty(tmp_path: Path) -> None:
    """should return an empty set when the state has no bills directory yet"""
    from zwiadbrain.cli import _existing_state_bill_ids  # pyright: ignore[reportPrivateUsage]

    assert _existing_state_bill_ids(tmp_path / "wiki", "ny") == set()


def test_existing_state_bill_ids_skips_unreadable_pages(tmp_path: Path) -> None:
    """should skip a malformed page rather than crash the whole sweep"""
    from zwiadbrain.cli import _existing_state_bill_ids  # pyright: ignore[reportPrivateUsage]

    wiki = tmp_path / "wiki"
    write_page(
        Bill(id="ca-2025-ab-7", jurisdiction="US-CA", title="t",
             bill_number="AB 7", legiscan_bill_id=777),
        wiki,
    )
    # Malformed frontmatter YAML (unclosed flow mapping) -> from_page raises
    # WikiSchemaError; the sweep must skip this page, not abort the whole state.
    bad = wiki / "states" / "ca" / "bills" / "ca-2025-ab-bad.md"
    bad.write_text(
        "---\nid: ca-2025-ab-bad\njurisdiction: {US-CA\ntype: bill\n---\nbody\n",
        encoding="utf-8",
    )
    assert _existing_state_bill_ids(wiki, "ca") == {"777"}


def test_fetch_state_candidates_skip_existing_drops_cached_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should drop a state candidate whose LegiScan change_hash is cached as a reject (D82)"""
    monkeypatch.setenv("LEGISCAN_API_KEY", "lk-test")
    wiki = tmp_path / "wiki"
    write_reject_ledger(
        wiki / ".rejects" / "state.json",
        {"777": RejectEntry(cursor="hash-1", id="ca-2025-ab-7")},
    )

    def _fake_discover(
        self: LegiScanSource, *, congress: int | None = None,
        since: object = None, limit: int = 20, max_pages: int = 1,
    ) -> list[Candidate]:
        return [
            Candidate(
                source="legiscan", native_id="777", jurisdiction="US-CA",
                title="", raw={"change_hash": "hash-1"},
            )
        ]

    monkeypatch.setattr(LegiScanSource, "discover", _fake_discover)
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        ["fetch-state-candidates", "--state", "ca", "--limit", "5", "--query", "privacy",
         "--skip-existing", "--wiki", str(wiki), "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert json.loads((out / "candidates.json").read_text(encoding="utf-8")) == []
    assert "cached-reject" in result.output


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


def test_apply_verdicts_honors_out_override(tmp_path: Path) -> None:
    """should write classified.json + rejects.json to --out, not the candidates' dir"""
    run = tmp_path / "run"
    out = tmp_path / "elsewhere"
    cands = _write_candidates(
        run, [Bill(id="ca-2025-ab-1", jurisdiction="US-CA", title="A", bill_number="AB 1")]
    )
    (run / "verdicts.json").write_text(
        json.dumps([{"id": "ca-2025-ab-1", "in_scope": True, "topics": ["ai"]}]),
        encoding="utf-8",
    )
    result = runner.invoke(app, [
        "apply-verdicts", "--in", str(cands),
        "--verdicts", str(run / "verdicts.json"), "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert (out / "classified.json").exists()
    assert (out / "rejects.json").exists()
    assert not (run / "classified.json").exists()


def test_apply_verdicts_non_list_candidates_errors(tmp_path: Path) -> None:
    """should exit non-zero when candidates.json is not a JSON list"""
    run = tmp_path / "run"
    run.mkdir()
    (run / "candidates.json").write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    (run / "verdicts.json").write_text(json.dumps([]), encoding="utf-8")
    result = runner.invoke(app, [
        "apply-verdicts", "--in", str(run / "candidates.json"),
        "--verdicts", str(run / "verdicts.json"),
    ])
    assert result.exit_code == 1
    assert "error" in result.output.lower()


def test_apply_summaries_non_string_value_errors(tmp_path: Path) -> None:
    """should exit non-zero when a summaries value is not a string"""
    run = tmp_path / "run"
    run.mkdir()
    cpath = run / "classified.json"
    cpath.write_text(
        json.dumps([Bill(id="ca-2025-ab-1", jurisdiction="US-CA", title="A",
                         bill_number="AB 1", topics=["ai"]).model_dump(mode="json")]),
        encoding="utf-8",
    )
    (run / "summaries.json").write_text(json.dumps({"ca-2025-ab-1": 123}), encoding="utf-8")
    result = runner.invoke(app, [
        "apply-summaries", "--in", str(cpath), "--summaries", str(run / "summaries.json"),
    ])
    assert result.exit_code == 1
    assert "error" in result.output.lower()
