"""Link-rot detection over the committed wiki (D111 / B9 of the 2026-07 hardening).

The 2026-07-01 accuracy audit found an entire URL family dead at once: ILGA's site
redesign retired ``BillStatus.asp``, ``/legislation/votehistory/*``, and the old
bill-text paths, 404ing most links on every Illinois page. This module turns that
class of failure from an audit finding into a routine report: harvest every http(s)
URL from the tracked pages, probe each unique URL once through an injected fetcher,
and group the failures by URL *family* (host + first path segment) so a site
redesign shows up as one loud cluster instead of a hundred scattered lines.

Pure logic — the fetcher is injected, so tests run with a fake and the CLI passes a
real HEAD/GET prober.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

# A pragmatic URL matcher for Markdown/YAML page text: an http(s) run ended by
# whitespace or the delimiters Markdown/YAML wrap links in. Trailing punctuation
# that belongs to the prose (a sentence's final ``.`` or ``,``) is stripped after
# the match.
_URL_RE = re.compile(r"https?://[^\s<>()\[\]\"']+")
_TRAILING_PUNCT = ".,;:!?"


def harvest_urls(text: str) -> list[str]:
    """Extract the unique http(s) URLs from a page's raw text, in first-seen order."""
    seen: set[str] = set()
    urls: list[str] = []
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(_TRAILING_PUNCT)
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def url_family(url: str) -> str:
    """Group key for a URL: lowercased host + first path segment.

    ``https://www.ilga.gov/legislation/BillStatus.asp?x=1`` -> ``www.ilga.gov/legislation``
    — coarse enough that a retired URL scheme clusters into one family, fine enough
    that unrelated paths on a big host do not.
    """
    match = re.match(r"^https?://([^/]+)(?:/([^/?#]+))?", url)
    if not match:
        return url
    host, segment = match.groups()
    return f"{host.lower()}/{segment}" if segment else host.lower()


@dataclass(frozen=True)
class DeadLink:
    """One non-OK URL and the page(s) it appears on."""

    url: str
    status: int
    pages: tuple[str, ...]


def check_pages(
    pages: Sequence[tuple[str, str]], fetch: Callable[[str], int]
) -> list[DeadLink]:
    """Probe every unique URL across *pages* once; return the non-OK ones.

    *pages* is ``(page_id, raw_text)`` pairs; *fetch* maps a URL to an HTTP status
    (0 for a network failure). Any 2xx/3xx status counts as alive — redirects are
    fine (several states 301 old hosts to working mirrors). Results are ordered by
    first appearance so the report is stable.
    """
    pages_by_url: dict[str, list[str]] = {}
    for page_id, text in pages:
        for url in harvest_urls(text):
            pages_by_url.setdefault(url, []).append(page_id)

    dead: list[DeadLink] = []
    for url, page_ids in pages_by_url.items():
        status = fetch(url)
        if not (200 <= status < 400):
            dead.append(DeadLink(url=url, status=status, pages=tuple(page_ids)))
    return dead


def group_by_family(dead: Sequence[DeadLink]) -> dict[str, list[DeadLink]]:
    """Cluster dead links by URL family, families ordered by descending size.

    A retired URL scheme (the ILGA case) surfaces as one large family at the top of
    the report; isolated 404s trail as single-entry families.
    """
    families: dict[str, list[DeadLink]] = {}
    for link in dead:
        families.setdefault(url_family(link.url), []).append(link)
    return dict(
        sorted(families.items(), key=lambda item: (-len(item[1]), item[0]))
    )
