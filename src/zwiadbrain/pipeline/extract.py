"""Document text extraction (PHASE-12).

Deterministic helpers that pick which source document(s) to extract for a tracked
item. The actual PDF/HTML → Markdown conversion lives behind the lazy Docling
boundary in :mod:`zwiadbrain.pipeline.docling_text`; this module never imports it
at module load, so the rest of the CLI/tests stay free of the heavy ML stack.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from zwiadbrain.models import Bill, EnforcementAction, TextVersion
from zwiadbrain.pipeline.docling_text import extract_markdown
from zwiadbrain.pipeline.render import page_path, sidecar_path, write_extracted_text_region

# Substrings that mark a linked PDF as one of the underlying legal filings worth
# extracting (rather than an unrelated report/newsletter on the press-release page).
_FILING_KEYWORDS: tuple[str, ...] = (
    "complaint",
    "order",
    "settlement",
    "consent",
    "stipulat",
    "decree",
    "judgment",
    "judgement",
    "petition",
)

# Final/enacted text — the most authoritative version to extract when present.
_OPERATIVE_KEYWORDS: tuple[str, ...] = ("enrolled", "chaptered", "public law", "enacted")
# Passed-one-chamber text — preferred over introduced/amended drafts.
_SECONDARY_KEYWORDS: tuple[str, ...] = ("engrossed",)


def _latest(versions: list[TextVersion]) -> TextVersion:
    """Pick the latest version by date; fall back to the last one when undated."""
    dated = [v for v in versions if v.date is not None]
    if dated:
        return max(dated, key=lambda v: v.date or dt.date.min)
    return versions[-1]


def select_bill_document(bill: Bill) -> TextVersion | None:
    """Choose the single operative text version to extract, or ``None``.

    Preference: enacted/final text (enrolled, chaptered, public law) → engrossed →
    latest dated version → first available. Only versions carrying a ``url`` are
    considered, since a version without one cannot be fetched.
    """
    candidates = [v for v in bill.text_versions if v.url]
    if not candidates:
        return None
    for keywords in (_OPERATIVE_KEYWORDS, _SECONDARY_KEYWORDS):
        matches = [v for v in candidates if any(k in v.code.lower() for k in keywords)]
        if matches:
            return _latest(matches)
    return _latest(candidates)


def discover_enforcement_pdfs(press_html: str, base_url: str) -> list[str]:
    """Return absolute URLs of the legal-filing PDFs linked from a press release.

    Keeps only ``.pdf`` links whose href or anchor text names a filing
    (complaint, order, settlement, ...), resolves relative URLs against
    ``base_url``, and dedups while preserving first-seen order.
    """
    soup = BeautifulSoup(press_html, "html.parser")
    found: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not isinstance(href, str):
            continue
        absolute = urljoin(base_url, href)
        if not urlparse(absolute).path.lower().endswith(".pdf"):
            continue
        haystack = f"{href} {anchor.get_text(' ', strip=True)}".lower()
        if not any(keyword in haystack for keyword in _FILING_KEYWORDS):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        found.append(absolute)
    return found


def _fetch_html(url: str) -> str:
    """Fetch a press-release page's raw HTML (for filing-PDF discovery)."""
    from zwiadbrain.sources.enforcement.base import make_client

    with make_client() as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def _enforcement_doc_urls(action: EnforcementAction) -> list[str]:
    """Ordered, de-duped press-release URLs from an action's sources/developments."""
    urls: list[str] = []
    seen: set[str] = set()
    for url in (*action.sources.values(), *(str(d.source_url) for d in action.developments)):
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _collect_sections(
    item: Bill | EnforcementAction,
    extractor: Callable[[str], str],
    html_fetcher: Callable[[str], str],
) -> list[tuple[str, str]]:
    """Extract each operative document into ``(label, markdown)`` sections."""
    if isinstance(item, Bill):
        version = select_bill_document(item)
        if version is None or not version.url:
            return []
        return [(version.code or "Text", extractor(version.url))]
    sections: list[tuple[str, str]] = []
    for url in _enforcement_doc_urls(item):
        sections.append((url, extractor(url)))
        try:
            html = html_fetcher(url)
        except httpx.HTTPError:
            # Press page unreachable for PDF discovery — keep the page text, skip filings.
            html = ""
        for pdf_url in discover_enforcement_pdfs(html, url):
            sections.append((pdf_url, extractor(pdf_url)))
    return sections


def _render_sidecar(item: Bill | EnforcementAction, sections: list[tuple[str, str]]) -> str:
    """Render the ``<id>.text.md`` sidecar: a provenance note plus each document."""
    parts = [
        f"# Extracted text — {item.title}",
        "> Extracted with Docling from official sources for full-text reference; "
        "the sources linked on the page remain authoritative.",
    ]
    parts.extend(f"## {label}\n\n{markdown.strip()}" for label, markdown in sections)
    return "\n\n".join(parts) + "\n"


def extract_item(
    item: Bill | EnforcementAction,
    wiki_root: Path,
    *,
    extractor: Callable[[str], str] | None = None,
    html_fetcher: Callable[[str], str] | None = None,
) -> Path | None:
    """Extract an item's operative document(s) to its sidecar and link the page.

    Returns the sidecar path, or ``None`` when the page does not exist yet or
    there is nothing fetchable to extract. ``extractor``/``html_fetcher`` are
    injectable for tests; by default they call the lazy Docling boundary and an
    httpx fetch. Idempotent: rewrites the sidecar and re-applies the page region.
    """
    page = page_path(item, wiki_root)
    if not page.exists():
        return None
    extract = extractor or extract_markdown
    fetch = html_fetcher or _fetch_html
    sections = _collect_sections(item, extract, fetch)
    if not sections:
        return None
    sidecar = sidecar_path(item, wiki_root)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(_render_sidecar(item, sections), encoding="utf-8", newline="\n")
    write_extracted_text_region(item, wiki_root)
    return sidecar


def plan_extraction(
    item: Bill | EnforcementAction, wiki_root: Path
) -> tuple[Path, list[str]] | None:
    """Dry-run plan: the target sidecar and the source URLs known without fetching.

    For enforcement, linked filing PDFs are discovered at run time (they need an
    HTTP fetch), so only the press-release URLs are listed here.
    """
    if not page_path(item, wiki_root).exists():
        return None
    if isinstance(item, Bill):
        version = select_bill_document(item)
        if version is None or not version.url:
            return None
        return sidecar_path(item, wiki_root), [version.url]
    urls = _enforcement_doc_urls(item)
    if not urls:
        return None
    return sidecar_path(item, wiki_root), urls
