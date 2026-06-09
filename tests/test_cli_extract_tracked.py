"""The ``extract-tracked`` CLI verb (PR-B): batch sidecar backfill over the committed wiki.

Walks ``wiki/**/*.md`` instead of a staged ``classified.json``. Bill pages do not
persist ``text_versions`` (body-only), so each due bill is re-fetched from its source
— stubbed here via fake Congress/LegiScan source classes patched into the cli
namespace. Enforcement pages extract straight from frontmatter (no re-fetch). The
Docling boundary and the enforcement HTML fetch are monkeypatched so tests never
touch torch or the network.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from zwiadbrain.cli import app
from zwiadbrain.models import Bill, EnforcementAction, EnforcementDevelopment, TextVersion
from zwiadbrain.pipeline.render import page_path, sidecar_path, write_page
from zwiadbrain.wiki.templates import EXTRACTED_TEXT_REGION_BEGIN

runner = CliRunner()


def _state_bill(bill_id: str = "ca-2025-sb-53", legiscan_id: int | None = 1898657) -> Bill:
    return Bill(
        id=bill_id,
        jurisdiction="US-CA",
        bill_number="SB 53",
        title="Frontier AI Act",
        summary="A summary.",
        legiscan_bill_id=legiscan_id,
        change_hash="h1",
    )


def _federal_bill(bill_id: str = "118-hr-1") -> Bill:
    return Bill(
        id=bill_id,
        jurisdiction="US",
        bill_number="HR 1",
        title="An Act",
        summary="A summary.",
    )


def _enforcement(action_id: str = "ftc-2026-acme") -> EnforcementAction:
    return EnforcementAction(
        id=action_id,
        jurisdiction="US",
        title="FTC v. Acme",
        agency="FTC",
        sources={"FTC": "https://ftc.example/press"},
        developments=[
            EnforcementDevelopment(
                date=None, summary="Complaint filed.", source_url="https://ftc.example/press"
            )
        ],
    )


def _with_text_versions(bill: Bill) -> Bill:
    """The fully-enriched shape a source re-fetch returns (text_versions are body-only)."""
    return bill.model_copy(
        update={"text_versions": [TextVersion(code="Enrolled", url=f"https://x.gov/{bill.id}.pdf")]}
    )


class _FetchRecorder:
    """Shared call log so tests can assert which sources actually fetched."""

    def __init__(self) -> None:
        self.constructed: list[str] = []
        self.fetched: list[str] = []


def _stub_sources(
    monkeypatch: pytest.MonkeyPatch,
    *,
    bills_by_ref: dict[str, Bill] | None = None,
    failing_refs: set[str] | None = None,
) -> _FetchRecorder:
    """Patch Congress/LegiScan source classes in the cli namespace with network-free fakes."""
    recorder = _FetchRecorder()
    refs = bills_by_ref or {}
    failing = failing_refs or set()

    class FakeCongress:
        def __init__(self, api_key: str) -> None:
            recorder.constructed.append("congress")

        def fetch(self, ref: str) -> Bill:
            recorder.fetched.append(ref)
            if ref in failing:
                raise RuntimeError(f"boom: {ref}")
            return refs[ref]

    class FakeLegiScan:
        def __init__(self, api_key: str, state: str) -> None:
            recorder.constructed.append(f"legiscan:{state}")

        def fetch(self, ref: str) -> Bill:
            recorder.fetched.append(ref)
            if ref in failing:
                raise RuntimeError(f"boom: {ref}")
            return refs[ref]

    monkeypatch.setattr("zwiadbrain.cli.CongressSource", FakeCongress)
    monkeypatch.setattr("zwiadbrain.cli.LegiScanSource", FakeLegiScan)
    monkeypatch.setenv("CONGRESS_API_KEY", "ck-test")
    monkeypatch.setenv("LEGISCAN_API_KEY", "lk-test")
    return recorder


def _stub_extractor(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_extract(source: object) -> str:
        return f"EXTRACTED::{source}"

    monkeypatch.setattr("zwiadbrain.pipeline.extract.extract_markdown", fake_extract)
    monkeypatch.setattr("zwiadbrain.cli.docling_available", lambda: True)


def test_extracts_state_bill_via_source_refetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should re-fetch a state bill by legiscan_bill_id and write its sidecar"""
    wiki = tmp_path / "wiki"
    bill = _state_bill()
    write_page(bill, wiki)
    _stub_extractor(monkeypatch)
    recorder = _stub_sources(
        monkeypatch, bills_by_ref={"1898657": _with_text_versions(bill)}
    )

    result = runner.invoke(app, ["extract-tracked", "--wiki", str(wiki)])

    assert result.exit_code == 0, result.output
    assert recorder.constructed == ["legiscan:ca"]
    assert recorder.fetched == ["1898657"]
    sidecar = sidecar_path(bill, wiki)
    assert sidecar.exists()
    assert "EXTRACTED::https://x.gov/ca-2025-sb-53.pdf" in sidecar.read_text(encoding="utf-8")
    assert EXTRACTED_TEXT_REGION_BEGIN in page_path(bill, wiki).read_text(encoding="utf-8")


def test_extracts_federal_bill_via_congress_refetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should re-fetch a federal bill by its slash-form ref and write its sidecar"""
    wiki = tmp_path / "wiki"
    bill = _federal_bill()
    write_page(bill, wiki)
    _stub_extractor(monkeypatch)
    recorder = _stub_sources(
        monkeypatch, bills_by_ref={"118/hr/1": _with_text_versions(bill)}
    )

    result = runner.invoke(app, ["extract-tracked", "--wiki", str(wiki)])

    assert result.exit_code == 0, result.output
    assert recorder.constructed == ["congress"]
    assert recorder.fetched == ["118/hr/1"]
    assert sidecar_path(bill, wiki).exists()


def test_extracts_enforcement_from_page_model_without_refetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should extract an enforcement action straight from frontmatter (no source fetch)"""
    wiki = tmp_path / "wiki"
    action = _enforcement()
    write_page(action, wiki)
    _stub_extractor(monkeypatch)
    recorder = _stub_sources(monkeypatch)
    def fake_fetch(url: str) -> str:
        return '<a href="/cases/complaint.pdf">Complaint</a>'

    monkeypatch.setattr("zwiadbrain.pipeline.extract._fetch_html", fake_fetch)

    result = runner.invoke(app, ["extract-tracked", "--wiki", str(wiki)])

    assert result.exit_code == 0, result.output
    assert recorder.constructed == []  # frontmatter carries sources: no API source needed
    sidecar = sidecar_path(action, wiki).read_text(encoding="utf-8")
    assert "EXTRACTED::https://ftc.example/press" in sidecar
    assert "EXTRACTED::https://ftc.example/cases/complaint.pdf" in sidecar


def test_skips_page_with_existing_sidecar_unless_forced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should skip a sidecar-complete page by default and re-extract it under --force"""
    wiki = tmp_path / "wiki"
    bill = _state_bill()
    write_page(bill, wiki)
    sidecar_path(bill, wiki).write_text("old extraction", encoding="utf-8")
    _stub_extractor(monkeypatch)
    recorder = _stub_sources(
        monkeypatch, bills_by_ref={"1898657": _with_text_versions(bill)}
    )

    result = runner.invoke(app, ["extract-tracked", "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output
    assert recorder.fetched == []  # nothing due
    assert sidecar_path(bill, wiki).read_text(encoding="utf-8") == "old extraction"

    result = runner.invoke(app, ["extract-tracked", "--wiki", str(wiki), "--force"])
    assert result.exit_code == 0, result.output
    assert recorder.fetched == ["1898657"]
    assert "EXTRACTED::" in sidecar_path(bill, wiki).read_text(encoding="utf-8")


def test_skip_option_excludes_named_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exclude --skip ids (e.g. omnibus carriers) from extraction"""
    wiki = tmp_path / "wiki"
    omnibus, small = _federal_bill("117-hr-7776"), _federal_bill("118-hr-1")
    write_page(omnibus, wiki)
    write_page(small, wiki)
    _stub_extractor(monkeypatch)
    recorder = _stub_sources(
        monkeypatch, bills_by_ref={"118/hr/1": _with_text_versions(small)}
    )

    result = runner.invoke(
        app, ["extract-tracked", "--wiki", str(wiki), "--skip", "117-hr-7776"]
    )

    assert result.exit_code == 0, result.output
    assert recorder.fetched == ["118/hr/1"]
    assert not sidecar_path(omnibus, wiki).exists()
    assert sidecar_path(small, wiki).exists()
    assert "1 excluded via --skip" in result.output


def test_limit_counts_only_due_items(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """should apply --limit after the skip filters so chunked runs make progress"""
    wiki = tmp_path / "wiki"
    done_bill, due_a, due_b = (
        _state_bill("ca-2025-sb-1", 111),
        _state_bill("ca-2025-sb-2", 222),
        _state_bill("ca-2025-sb-3", 333),
    )
    for bill in (done_bill, due_a, due_b):
        write_page(bill, wiki)
    sidecar_path(done_bill, wiki).write_text("already extracted", encoding="utf-8")
    _stub_extractor(monkeypatch)
    recorder = _stub_sources(
        monkeypatch,
        bills_by_ref={"222": _with_text_versions(due_a), "333": _with_text_versions(due_b)},
    )

    result = runner.invoke(app, ["extract-tracked", "--wiki", str(wiki), "--limit", "1"])

    assert result.exit_code == 0, result.output
    # the sidecar-complete page does not consume the limit; exactly one due item ran
    assert recorder.fetched == ["222"]
    assert sidecar_path(due_a, wiki).exists()
    assert not sidecar_path(due_b, wiki).exists()


def test_dry_run_is_network_free_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should list planned work without Docling, fetches, or writes under --dry-run"""
    wiki = tmp_path / "wiki"
    bill, action = _state_bill(), _enforcement()
    write_page(bill, wiki)
    write_page(action, wiki)
    recorder = _stub_sources(monkeypatch)  # no bills_by_ref: any fetch would KeyError
    monkeypatch.setattr("zwiadbrain.cli.docling_available", lambda: False)

    result = runner.invoke(app, ["extract-tracked", "--wiki", str(wiki), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert recorder.constructed == []
    assert recorder.fetched == []
    assert "would fetch+extract ca-2025-sb-53" in result.output
    assert "would extract ftc-2026-acme" in result.output
    assert not sidecar_path(bill, wiki).exists()
    assert not sidecar_path(action, wiki).exists()


def test_fails_fast_without_docling_on_real_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should exit non-zero with the install hint when Docling is absent (real run)"""
    wiki = tmp_path / "wiki"
    bill = _state_bill()
    write_page(bill, wiki)
    monkeypatch.setattr("zwiadbrain.cli.docling_available", lambda: False)

    result = runner.invoke(app, ["extract-tracked", "--wiki", str(wiki)])

    assert result.exit_code == 1
    assert "Docling is not installed" in result.output
    assert not sidecar_path(bill, wiki).exists()


def test_per_item_isolation_one_failing_fetch_does_not_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should record a failing item as skipped and still extract the next one"""
    wiki = tmp_path / "wiki"
    bad, good = _state_bill("ca-2025-sb-1", 111), _state_bill("ca-2025-sb-2", 222)
    write_page(bad, wiki)
    write_page(good, wiki)
    _stub_extractor(monkeypatch)
    _stub_sources(
        monkeypatch,
        bills_by_ref={"222": _with_text_versions(good)},
        failing_refs={"111"},
    )

    result = runner.invoke(app, ["extract-tracked", "--wiki", str(wiki)])

    assert result.exit_code == 0, result.output
    assert not sidecar_path(bad, wiki).exists()
    assert sidecar_path(good, wiki).exists()
    assert "skipped ca-2025-sb-1" in result.output


def test_untracked_pages_are_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """should never extract a tracking=false page"""
    wiki = tmp_path / "wiki"
    flipped = _state_bill().model_copy(update={"tracking": False})
    write_page(flipped, wiki)
    _stub_extractor(monkeypatch)
    recorder = _stub_sources(monkeypatch)

    result = runner.invoke(app, ["extract-tracked", "--wiki", str(wiki)])

    assert result.exit_code == 0, result.output
    assert recorder.fetched == []
    assert not sidecar_path(flipped, wiki).exists()


def test_state_bill_without_legiscan_id_is_reported_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should report a state bill lacking legiscan_bill_id as skipped with a reason"""
    wiki = tmp_path / "wiki"
    orphan = _state_bill("ca-2025-sb-9", legiscan_id=None)
    write_page(orphan, wiki)
    _stub_extractor(monkeypatch)
    recorder = _stub_sources(monkeypatch)

    result = runner.invoke(app, ["extract-tracked", "--wiki", str(wiki)])

    assert result.exit_code == 0, result.output
    assert recorder.constructed == []
    assert "skipped ca-2025-sb-9" in result.output
    assert "legiscan_bill_id" in result.output


def test_summary_line_reports_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """should report extracted / already-present / excluded counts in the summary line"""
    wiki = tmp_path / "wiki"
    done_bill, due = _state_bill("ca-2025-sb-1", 111), _state_bill("ca-2025-sb-2", 222)
    write_page(done_bill, wiki)
    write_page(due, wiki)
    sidecar_path(done_bill, wiki).write_text("already", encoding="utf-8")
    _stub_extractor(monkeypatch)
    _stub_sources(monkeypatch, bills_by_ref={"222": _with_text_versions(due)})

    result = runner.invoke(app, ["extract-tracked", "--wiki", str(wiki)])

    assert result.exit_code == 0, result.output
    assert "extracted 1 item(s)" in result.output
    assert "1 sidecar already present" in result.output
