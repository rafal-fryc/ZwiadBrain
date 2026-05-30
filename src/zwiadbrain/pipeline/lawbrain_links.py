"""Deterministic, offline harvest of secondary-commentary reference links (D62).

The verbatim body-copy of a matched law-brain page (PHASE-09 §5.4) captures only the
links present in the page body. The richer law-firm / IAPP / natlawreview links live in
the ``sources/zwiad/*.md`` memos the page references. This module pulls ``[text](url)``
markdown links and bare ``https?://`` URLs out of the page body AND each referenced memo,
drops primary-source domains (ZwiadBrain already carries authoritative primary sources),
dedups by normalized URL, and stable-sorts by ``(host, url)`` so a re-render is
byte-identical (D20). No LLM, no network — pure text in, ``CommentaryLink`` list out.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from zwiadbrain.models import CommentaryLink

# [text](https://host/path) — non-greedy text, http(s) URL up to the closing paren.
# Known limitation: a URL with ) in its path (e.g. Wikipedia _(disambiguation)) is
# truncated at the paren. Acceptable: such hosts are denylisted, and law-firm/IAPP/NLR
# URLs don't use paren paths.
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
# A bare http(s) URL: run of non-whitespace after the scheme. Same paren limitation.
_BARE_URL = re.compile(r"https?://[^\s)\]]+")
# Sentence punctuation that commonly trails a bare URL and is not part of it.
_TRAILING_PUNCT = ".,;:)”\"'"


def _host(url: str) -> str:
    """Lowercase host of *url* (``urlsplit().hostname`` is already lowercased)."""
    return (urlsplit(url).hostname or "").lower()


def _normalized_url(url: str) -> str:
    """Dedup key: lowercase host spliced back in, one trailing ``/`` stripped."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    rest = url[url.lower().find(host) + len(host) :] if host else url
    rebuilt = f"{parts.scheme}://{host}{rest}"
    return rebuilt[:-1] if rebuilt.endswith("/") else rebuilt


def _is_primary_source(url: str, primary_source_domains: list[str]) -> bool:
    """True if the URL's host equals or ends with any configured denylist suffix."""
    host = _host(url)
    if not host:
        return False
    for suffix in primary_source_domains:
        bare = suffix.lstrip(".")
        if host == bare or host.endswith("." + bare):
            return True
    return False


def _strip_trailing_punct(url: str) -> str:
    """Remove trailing sentence punctuation that is not part of the URL."""
    return url.rstrip(_TRAILING_PUNCT)


def harvest_links(
    *,
    page_body: str,
    memo_texts: list[str],
    primary_source_domains: list[str],
) -> list[CommentaryLink]:
    """Extract secondary-commentary links from *page_body* and each memo (D62).

    Markdown ``[text](url)`` links keep their anchor text; bare ``https?://`` URLs use
    their host as the anchor. URLs whose host ends with a ``primary_source_domains``
    suffix are dropped. Results are deduped by normalized URL (lowercase host, one
    trailing ``/`` stripped) — first occurrence's anchor text wins — and stable-sorted
    by ``(host, normalized url)``.
    """
    # Ordered dict keyed by normalized URL preserves first-seen anchor text.
    seen: dict[str, CommentaryLink] = {}

    for text in (page_body, *memo_texts):
        consumed: set[str] = set()
        # Markdown links first; record their URL spans so the bare pass skips them.
        for match in _MARKDOWN_LINK.finditer(text):
            anchor, url = match.group(1).strip(), match.group(2)
            consumed.add(url)
            if _is_primary_source(url, primary_source_domains):
                continue
            key = _normalized_url(url)
            if key not in seen:
                seen[key] = CommentaryLink(text=anchor, url=url)
        # Bare URLs not already captured inside a markdown link.
        for match in _BARE_URL.finditer(text):
            url = _strip_trailing_punct(match.group(0))
            if url in consumed or match.group(0) in consumed:
                continue
            if _is_primary_source(url, primary_source_domains):
                continue
            key = _normalized_url(url)
            if key not in seen:
                seen[key] = CommentaryLink(text=_host(url), url=url)

    return sorted(seen.values(), key=lambda link: (_host(link.url), _normalized_url(link.url)))
