"""The ``extract-text`` CLI verb (PHASE-12).

Reads a classified.json of model dumps (Bill / EnforcementAction), extracts the
operative document(s) via the Docling boundary (stubbed here), writes a
``<id>.text.md`` sidecar, and links it from the page. Docling and the HTML fetch
are monkeypatched so the test never touches torch or the network.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zwiadbrain.cli import app
from zwiadbrain.models import Bill, EnforcementAction, EnforcementDevelopment, TextVersion
from zwiadbrain.pipeline.render import page_path, sidecar_path, write_page
from zwiadbrain.wiki.templates import EXTRACTED_TEXT_REGION_BEGIN

runner = CliRunner()


def _bill(bill_id: str = "119-hr-1") -> Bill:
    return Bill(
        id=bill_id,
        jurisdiction="US",
        bill_number="HR 1",
        title="An Act",
        summary="A summary.",
        sources={"Congress.gov": "https://www.congress.gov/bill/119/hr/1"},
        text_versions=[TextVersion(code="Enrolled Bill", url="https://x.gov/enr.pdf")],
    )


def _stub_extractor(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_extract(source: object) -> str:
        return f"EXTRACTED::{source}"

    monkeypatch.setattr("zwiadbrain.pipeline.extract.extract_markdown", fake_extract)
    monkeypatch.setattr("zwiadbrain.cli.docling_available", lambda: True)


def _write_classified(tmp_path: Path, items: list[object]) -> Path:
    path = tmp_path / "classified.json"
    path.write_text(json.dumps(items), encoding="utf-8")
    return path


def test_extracts_bill_writes_sidecar_and_links_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wiki = tmp_path / "wiki"
    bill = _bill()
    write_page(bill, wiki)
    classified = _write_classified(tmp_path, [bill.model_dump(mode="json")])
    _stub_extractor(monkeypatch)

    result = runner.invoke(app, ["extract-text", "--in", str(classified), "--wiki", str(wiki)])

    assert result.exit_code == 0, result.output
    sidecar = sidecar_path(bill, wiki)
    assert sidecar.exists()
    assert "EXTRACTED::https://x.gov/enr.pdf" in sidecar.read_text(encoding="utf-8")
    page = page_path(bill, wiki).read_text(encoding="utf-8")
    assert EXTRACTED_TEXT_REGION_BEGIN in page
    assert "(119-hr-1.text.md)" in page


def test_dry_run_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wiki = tmp_path / "wiki"
    bill = _bill()
    write_page(bill, wiki)
    classified = _write_classified(tmp_path, [bill.model_dump(mode="json")])
    _stub_extractor(monkeypatch)

    result = runner.invoke(
        app, ["extract-text", "--in", str(classified), "--wiki", str(wiki), "--dry-run"]
    )

    assert result.exit_code == 0, result.output
    assert not sidecar_path(bill, wiki).exists()
    assert EXTRACTED_TEXT_REGION_BEGIN not in page_path(bill, wiki).read_text(encoding="utf-8")


def test_limit_caps_items_extracted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wiki = tmp_path / "wiki"
    first, second = _bill("119-hr-1"), _bill("119-hr-2")
    write_page(first, wiki)
    write_page(second, wiki)
    classified = _write_classified(
        tmp_path, [first.model_dump(mode="json"), second.model_dump(mode="json")]
    )
    _stub_extractor(monkeypatch)

    result = runner.invoke(
        app, ["extract-text", "--in", str(classified), "--wiki", str(wiki), "--limit", "1"]
    )

    assert result.exit_code == 0, result.output
    assert sidecar_path(first, wiki).exists()
    assert not sidecar_path(second, wiki).exists()


def test_extracts_enforcement_press_release_and_linked_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wiki = tmp_path / "wiki"
    action = EnforcementAction(
        id="ftc-2026-acme",
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
    write_page(action, wiki)
    classified = _write_classified(tmp_path, [action.model_dump(mode="json")])
    _stub_extractor(monkeypatch)

    def fake_fetch(url: str) -> str:
        return '<a href="/cases/complaint.pdf">Complaint</a>'

    monkeypatch.setattr("zwiadbrain.pipeline.extract._fetch_html", fake_fetch)

    result = runner.invoke(app, ["extract-text", "--in", str(classified), "--wiki", str(wiki)])

    assert result.exit_code == 0, result.output
    sidecar = sidecar_path(action, wiki).read_text(encoding="utf-8")
    assert "EXTRACTED::https://ftc.example/press" in sidecar
    assert "EXTRACTED::https://ftc.example/cases/complaint.pdf" in sidecar


def test_skips_item_with_no_committed_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    bill = _bill()  # no page written
    classified = _write_classified(tmp_path, [bill.model_dump(mode="json")])
    _stub_extractor(monkeypatch)

    result = runner.invoke(app, ["extract-text", "--in", str(classified), "--wiki", str(wiki)])

    assert result.exit_code == 0, result.output
    assert not sidecar_path(bill, wiki).exists()


def test_fails_fast_when_docling_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wiki = tmp_path / "wiki"
    bill = _bill()
    write_page(bill, wiki)
    classified = _write_classified(tmp_path, [bill.model_dump(mode="json")])
    monkeypatch.setattr("zwiadbrain.cli.docling_available", lambda: False)

    result = runner.invoke(app, ["extract-text", "--in", str(classified), "--wiki", str(wiki)])

    assert result.exit_code == 1
    assert "Docling is not installed" in result.output
    assert not sidecar_path(bill, wiki).exists()


def test_dry_run_works_without_docling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --dry-run must preview even when Docling is absent (it never invokes it).
    wiki = tmp_path / "wiki"
    bill = _bill()
    write_page(bill, wiki)
    classified = _write_classified(tmp_path, [bill.model_dump(mode="json")])
    monkeypatch.setattr("zwiadbrain.cli.docling_available", lambda: False)

    result = runner.invoke(
        app, ["extract-text", "--in", str(classified), "--wiki", str(wiki), "--dry-run"]
    )

    assert result.exit_code == 0, result.output
    assert not sidecar_path(bill, wiki).exists()
