"""The enforcement-source abstraction + shared feed/HTML parsing.

An :class:`EnforcementSource` discovers lightweight :class:`EnforcementCandidate`
records from an agency feed (forward-from-now) and fetches the readable article text
behind each. Enforcement returns enforcement-shaped data, so it does NOT reuse the bill
``Source`` protocol (whose ``fetch`` returns a ``Bill``).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Protocol, runtime_checkable

import feedparser  # type: ignore[import-untyped]
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel

# A browser-like UA: public agency feeds (FTC, state AGs) sit behind bot filters that
# 403 the default httpx User-Agent. The feeds are published for consumption; a realistic
# UA is required to read them (UAT-confirmed: FTC returns 403 without it).
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def make_client(timeout: float = 30.0) -> httpx.Client:
    """An httpx client preconfigured for enforcement-feed fetching (browser UA, redirects)."""
    return httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": _USER_AGENT})


class EnforcementCandidate(BaseModel):
    """A discovered enforcement item before classification/extraction."""

    source: str
    agency: str
    agency_slug: str
    jurisdiction: str
    title: str
    url: str
    published: dt.date | None = None
    raw: dict[str, object] = {}
    text: str | None = None


@runtime_checkable
class EnforcementSource(Protocol):
    """Structural contract every enforcement source implements."""

    name: str

    def discover(
        self, *, since: dt.datetime | None = None, limit: int = 20
    ) -> list[EnforcementCandidate]:
        """Surface up to ``limit`` candidates published since ``since`` (newest first)."""
        ...

    def fetch_text(self, candidate: EnforcementCandidate) -> str:
        """Follow ``candidate.url`` and return the readable article body text."""
        ...


def _entry_date(entry: Any) -> dt.date | None:
    # ``entry`` is typed as Any because feedparser's entry objects are untyped
    # (feedparser ships no py.typed / stubs); using Any at the boundary is the
    # project's documented pattern for interfacing with untyped third-party libs.
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is not None:
        return dt.date(parsed.tm_year, parsed.tm_mon, parsed.tm_mday)
    return None


def parse_feed(content: str) -> list[dict[str, object]]:
    """Parse an RSS/Atom feed string into normalized entry dicts (newest first as given)."""
    feed: Any = feedparser.parse(content)  # type: ignore[reportUnknownMemberType]
    out: list[dict[str, object]] = []
    for entry in feed.entries:
        link = entry.get("link") or ""
        if not link:
            continue
        out.append(
            {
                "title": entry.get("title", "").strip(),
                "link": link,
                "summary": entry.get("summary", "") or entry.get("description", ""),
                "published": _entry_date(entry),
            }
        )
    return out


def extract_article_text(html: str) -> str:
    """Extract readable body text from a press-release page, dropping boilerplate."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "form", "aside"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return main.get_text(" ", strip=True)
