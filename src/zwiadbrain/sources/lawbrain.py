"""Read-only reader for the sibling law brain — NOT a :class:`Source`.

The law brain (``LAW_BRAIN_PATH/wiki/<type>-<slug>.md``) is a local Markdown
corpus, so this reader does no transport: it enumerates pages, parses their YAML
frontmatter tolerantly, and computes an EOL-normalized content hash used as the
commentary staleness cursor (D5). It also resolves a page's ``sources:`` memo
paths for the Further-Reading link harvester. Strictly read-only — this module
never writes to the law brain (D2).

Tolerance is deliberate: a single malformed page must not sink a whole sync run,
and the two wikis disagree on small shapes (``jurisdiction`` may be a scalar or a
list; ``citation``/``updated`` may be absent). One bad page is logged and skipped.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
from pathlib import Path
from typing import Any, cast

import frontmatter
from pydantic import BaseModel, Field

_LOGGER = logging.getLogger(__name__)


def _content_hash(text: str) -> str:
    """SHA-256 of ``text`` with line endings normalized to ``\\n`` (D5).

    Normalizing CRLF and bare CR to LF before hashing makes the cursor
    insensitive to the EOL style the law brain happens to be saved with, so a
    pure line-ending change never reads as a stale-content diff.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _coerce_str_list(value: Any) -> list[str]:
    """Coerce a scalar-or-list YAML value into a ``list[str]`` (drop None/blanks).

    A ``None`` element (``tags: [null, ai]``) is dropped rather than stringified —
    a literal ``"None"`` would otherwise leak into downstream key extraction.
    """
    if value is None:
        return []
    if isinstance(value, list):
        # Pyright narrows isinstance(list) to list[Unknown]; cast restores Any so the
        # iteration item is typed (genuinely untyped YAML — matches the dict[str, Any]
        # discipline used throughout this module).
        items = cast(list[Any], value)
        out: list[str] = []
        for item in items:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def _opt_str(value: Any) -> str | None:
    """Return a stripped string, or None for missing/blank values."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_date(value: Any) -> dt.date | None:
    """Parse a ``YYYY-MM-DD`` date for display/attribution only (never diffing).

    ``python-frontmatter`` may already have parsed the YAML scalar into a
    ``datetime.date``; accept that directly, otherwise parse the ISO prefix.
    Any unparseable value yields ``None`` — the date is non-load-bearing.
    """
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = _opt_str(value)
    if text is None:
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


class LawBrainPage(BaseModel):
    """One parsed law-brain wiki page (read-only view).

    ``body`` is the verbatim Markdown after the frontmatter; ``content_hash`` is
    the EOL-normalized hash of the whole file and is the staleness cursor.
    ``updated`` is display/attribution only — never trusted for diffing (D5).
    """

    slug: str
    type: str
    jurisdiction: list[str]
    tags: list[str]
    title: str
    citation: str | None = None
    updated: dt.date | None = None
    body: str
    content_hash: str
    source_files: list[str] = Field(default_factory=list)


class LawBrainReader:
    """Enumerate and parse law-brain wiki pages from a root directory (read-only)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.wiki_dir = root / "wiki"

    def is_available(self) -> bool:
        """True iff ``<root>/wiki`` is a directory — a missing path is a clean no-op."""
        return self.wiki_dir.is_dir()

    def pages(self) -> list[LawBrainPage]:
        """Parse every ``wiki/<type>-*.md`` page; skip non-pages and malformed files.

        A file is a page only if its stem carries a ``<type>-`` prefix (so
        ``index.md``/``log.md``/``CLAUDE.md`` are skipped). Per-page parse errors
        are logged and skipped — one bad page never sinks a sync run.
        """
        if not self.is_available():
            return []
        results: list[LawBrainPage] = []
        for path in sorted(self.wiki_dir.glob("*.md")):
            page_type, sep, _ = path.stem.partition("-")
            if not sep or not page_type:
                continue
            page = self._parse_page(path, page_type)
            if page is not None:
                results.append(page)
        return results

    def _parse_page(self, path: Path, page_type: str) -> LawBrainPage | None:
        try:
            text = path.read_text(encoding="utf-8")
            parsed = frontmatter.loads(text)
            metadata: dict[str, Any] = parsed.metadata
            return LawBrainPage(
                slug=path.stem,
                type=str(metadata.get("type") or page_type),
                jurisdiction=_coerce_str_list(metadata.get("jurisdiction")),
                tags=_coerce_str_list(metadata.get("tags")),
                title=str(metadata.get("title") or path.stem),
                citation=_opt_str(metadata.get("citation")),
                updated=_parse_date(metadata.get("updated")),
                body=parsed.content,
                content_hash=_content_hash(text),
                source_files=_coerce_str_list(metadata.get("sources")),
            )
        except (OSError, UnicodeDecodeError) as exc:
            _LOGGER.warning("skipping unreadable law-brain page %s: %s", path.name, exc)
            return None
        except Exception as exc:  # noqa: BLE001 — tolerant parse boundary (D5); malformed YAML or construction error must not sink the run
            _LOGGER.warning("skipping malformed law-brain page %s: %s", path.name, exc)
            return None

    def read_source_memo(self, rel_path: str) -> str | None:
        """Return the text of a ``sources:`` memo, or None if missing or non-``.md``.

        Only ``.md`` memos are readable (a ``source_files`` entry may be a PDF or
        other binary). The path is resolved against the law-brain root and read
        read-only; a missing file yields ``None`` rather than raising. A
        ``rel_path`` that escapes the root (``../../x.md``) is rejected — the law
        brain is read-only and an attacker-controlled frontmatter path must not
        be able to read arbitrary files.
        """
        candidate = self.root / rel_path
        if candidate.suffix.lower() != ".md":
            return None
        try:
            candidate.resolve().relative_to(self.root.resolve())
        except ValueError:
            _LOGGER.warning("skipping out-of-root memo path: %s", rel_path)
            return None
        if not candidate.is_file():
            return None
        try:
            return candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            _LOGGER.warning("skipping unreadable law-brain memo %s: %s", rel_path, exc)
            return None
