"""Tests for the read-only law-brain reader (sources/lawbrain.py)."""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path
from typing import Any, cast

import pytest

from zwiadbrain.sources import lawbrain as lawbrain_module
from zwiadbrain.sources.lawbrain import (
    LawBrainPage,
    LawBrainReader,
    _coerce_str_list,  # pyright: ignore[reportPrivateUsage]
    _content_hash,  # pyright: ignore[reportPrivateUsage]
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "lawbrain"


@pytest.fixture
def reader() -> LawBrainReader:
    return LawBrainReader(FIXTURE_ROOT)


def _page_by_slug(reader: LawBrainReader, slug: str) -> LawBrainPage:
    pages = {page.slug: page for page in reader.pages()}
    assert slug in pages, f"{slug} not found; got {sorted(pages)}"
    return pages[slug]


def test_is_available_returns_true_when_wiki_dir_exists(reader: LawBrainReader) -> None:
    assert reader.is_available() is True


def test_is_available_returns_false_when_wiki_dir_missing(tmp_path: Path) -> None:
    assert LawBrainReader(tmp_path / "does-not-exist").is_available() is False


def test_pages_skips_non_type_prefixed_files(reader: LawBrainReader) -> None:
    slugs = {page.slug for page in reader.pages()}
    assert "index" not in slugs
    assert "regulation-fixture-sb53" in slugs
    assert "concept-fixture-ai-landscape" in slugs
    assert "regulation-fixture-crlf-eol" in slugs


def test_pages_preserves_list_jurisdiction(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "regulation-fixture-sb53")
    assert page.jurisdiction == ["US-CA"]


def test_pages_coerces_scalar_jurisdiction_to_list(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "concept-fixture-ai-landscape")
    assert page.jurisdiction == ["US-CA"]


def test_pages_parses_type_title_citation_and_updated(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "regulation-fixture-sb53")
    assert page.type == "regulation"
    assert page.title == "Fixture SB 53 — Transparency in Frontier AI Act (TFAIA)"
    assert page.citation == "California SB 53 (Ch. 138, Stats. 2025) — TFAIA"
    assert page.updated == dt.date(2026, 5, 6)


def test_pages_tolerates_missing_citation_and_updated(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "concept-fixture-ai-landscape")
    assert page.citation is None
    assert page.updated is None


def test_pages_captures_source_files_from_frontmatter(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "regulation-fixture-sb53")
    assert page.source_files == [
        "sources/zwiad/fixture-memo.md",
        "sources/zwiad/fixture-missing.md",
    ]


def test_pages_body_is_content_after_frontmatter(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "regulation-fixture-sb53")
    assert page.body.lstrip().startswith("## Summary")
    assert "[[regulation-fixture-ab-2013]]" in page.body
    assert "title: Fixture SB 53" not in page.body


def test_content_hash_matches_eol_normalized_sha256(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "regulation-fixture-sb53")
    raw = (FIXTURE_ROOT / "wiki" / "regulation-fixture-sb53.md").read_text(encoding="utf-8")
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    expected = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    assert page.content_hash == expected


def test_content_hash_is_crlf_invariant() -> None:
    crlf = "## Summary\r\nLine two.\r\n"
    lf = "## Summary\nLine two.\n"
    assert _content_hash(crlf) == _content_hash(lf)


def test_content_hash_is_bare_cr_invariant() -> None:
    assert _content_hash("## Summary\rLine two.\r") == _content_hash("## Summary\nLine two.\n")


def test_content_hash_of_crlf_fixture_equals_lf_equivalent(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "regulation-fixture-crlf-eol")
    raw_bytes = (FIXTURE_ROOT / "wiki" / "regulation-fixture-crlf-eol.md").read_bytes()
    lf_text = raw_bytes.decode("utf-8").replace("\r\n", "\n")
    expected = hashlib.sha256(lf_text.encode("utf-8")).hexdigest()
    assert page.content_hash == expected


def test_read_source_memo_returns_text_for_existing_md(reader: LawBrainReader) -> None:
    memo = reader.read_source_memo("sources/zwiad/fixture-memo.md")
    assert memo is not None
    assert "Crowell client alert" in memo


def test_read_source_memo_returns_none_for_missing_file(reader: LawBrainReader) -> None:
    assert reader.read_source_memo("sources/zwiad/fixture-missing.md") is None


def test_read_source_memo_returns_none_for_non_md_extension(reader: LawBrainReader) -> None:
    assert reader.read_source_memo("sources/zwiad/fixture-memo.pdf") is None


def test_read_source_memo_rejects_out_of_root_path(reader: LawBrainReader) -> None:
    # A traversal path must not escape the law-brain root, even if such a file exists.
    assert reader.read_source_memo("../../../../etc/passwd.md") is None


def test_pages_skips_page_with_malformed_frontmatter(reader: LawBrainReader) -> None:
    # The broken fixture has unparseable YAML; it must be skipped, not crash pages().
    slugs = {page.slug for page in reader.pages()}
    assert "regulation-fixture-broken" not in slugs
    # And the well-formed pages still come through — one bad page never sinks the run.
    assert "regulation-fixture-sb53" in slugs


def test_pages_isolates_construction_error(
    reader: LawBrainReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Even a failure *inside* LawBrainPage(...) construction must be isolated per-page
    # (the constructor is inside the try), so pages() still returns the other pages.
    # cast to Any: re-invoking the real __init__ with a **dict spread is untyped here.
    real_init = cast(Any, LawBrainPage.__init__)

    def exploding_init(self: LawBrainPage, **data: object) -> None:
        if data.get("slug") == "regulation-fixture-sb53":
            raise ValueError("boom during construction")
        real_init(self, **data)

    monkeypatch.setattr(lawbrain_module.LawBrainPage, "__init__", exploding_init)
    slugs = {page.slug for page in reader.pages()}
    assert "regulation-fixture-sb53" not in slugs  # the exploding page is skipped
    assert "concept-fixture-ai-landscape" in slugs  # others still parse


def test_coerce_str_list_drops_none_elements_without_stringifying() -> None:
    # tags: [null, ai] must drop the None, never produce the literal "None".
    result = _coerce_str_list([None, "ai", "  ", "tfaia"])
    assert result == ["ai", "tfaia"]
    assert "None" not in result
