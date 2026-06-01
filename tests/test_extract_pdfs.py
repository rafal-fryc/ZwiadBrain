"""Enforcement filing-PDF discovery for text extraction (PHASE-12).

``discover_enforcement_pdfs`` scans a press-release page for links to the
underlying legal filings (complaint, order, settlement, consent decree, ...),
resolving relative URLs and ignoring navigation/boilerplate and unrelated PDFs.
"""

from zwiadbrain.pipeline.extract import discover_enforcement_pdfs

_BASE = "https://www.ftc.gov/news-events/news/press-releases/2026/05/foo"

_HTML = """
<html><body>
  <nav><a href="/home">Home</a></nav>
  <main>
    <p>The FTC filed a
       <a href="/system/files/documents/cases/complaint.pdf">complaint</a>.</p>
    <p>See the
       <a href="https://www.ftc.gov/orders/consent_order.pdf">proposed consent order</a>.</p>
    <p>An unrelated <a href="/files/annual_report.pdf">annual report</a>.</p>
    <p>Read the <a href="https://example.com/news">news coverage</a>.</p>
    <p>Duplicate
       <a href="/system/files/documents/cases/complaint.pdf">complaint again</a>.</p>
  </main>
</body></html>
"""


def test_finds_filing_pdfs_and_resolves_relative_urls() -> None:
    found = discover_enforcement_pdfs(_HTML, _BASE)
    assert "https://www.ftc.gov/system/files/documents/cases/complaint.pdf" in found
    assert "https://www.ftc.gov/orders/consent_order.pdf" in found


def test_excludes_non_pdf_and_unrelated_pdf() -> None:
    found = discover_enforcement_pdfs(_HTML, _BASE)
    assert "https://example.com/news" not in found
    assert all("annual_report.pdf" not in url for url in found)


def test_dedups_repeated_urls() -> None:
    found = discover_enforcement_pdfs(_HTML, _BASE)
    complaint = "https://www.ftc.gov/system/files/documents/cases/complaint.pdf"
    assert found.count(complaint) == 1


def test_matches_on_anchor_text_when_href_is_opaque() -> None:
    html = (
        '<a href="/system/files/cases/2026/05/d0c-1.pdf">Complaint and Proposed Order</a>'
    )
    found = discover_enforcement_pdfs(html, _BASE)
    assert found == ["https://www.ftc.gov/system/files/cases/2026/05/d0c-1.pdf"]


def test_returns_empty_when_no_filings() -> None:
    html = '<main><p>No documents here, just <a href="/about">about</a>.</p></main>'
    assert discover_enforcement_pdfs(html, _BASE) == []
