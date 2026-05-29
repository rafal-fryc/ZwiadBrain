"""Generic, config-driven state-AG enforcement source (rss | html).

One adapter serves every AG; a state is added by config, not code. Discovery failures
are isolated: a broken feed/selector logs and yields [] so one AG never aborts the
multi-agency scan (D54).
"""

from __future__ import annotations

import datetime as dt
import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from zwiadbrain.sources.enforcement.base import (
    EnforcementCandidate,
    extract_article_text,
    make_client,
    parse_feed,
)

_LOGGER = logging.getLogger(__name__)


def _as_date(value: object) -> dt.date | None:
    """Narrow an object from a parse_feed dict to dt.date, or None."""
    return value if isinstance(value, dt.date) else None


def _time_date(el: object) -> dt.date | None:
    """Find a nearby <time datetime=...> for a selected anchor and parse its date."""
    if not isinstance(el, Tag):
        return None
    time_el = el.find_next("time")
    if isinstance(time_el, Tag):
        raw = time_el.get("datetime")
        if isinstance(raw, str):
            try:
                return dt.date.fromisoformat(raw[:10])
            except ValueError:
                return None
    return None


class StateAGSource:
    """A single state Attorney General source, configured by a TOML entry."""

    name = "state_ag"

    def __init__(
        self,
        *,
        name: str,
        agency_slug: str,
        jurisdiction: str,
        url: str,
        kind: str,
        item_selector: str = "",
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.agency = name
        self.agency_slug = agency_slug
        self.jurisdiction = jurisdiction
        self.url = url
        self.kind = kind
        self.item_selector = item_selector
        self.client = client or make_client(timeout)

    def _candidate(
        self, title: str, link: str, published: dt.date | None
    ) -> EnforcementCandidate:
        return EnforcementCandidate(
            source=self.name,
            agency=self.agency,
            agency_slug=self.agency_slug,
            jurisdiction=self.jurisdiction,
            title=title.strip(),
            url=urljoin(self.url, link),
            published=published,
            raw={},
        )

    def _discover_rss(self) -> list[EnforcementCandidate]:
        text = self.client.get(self.url).raise_for_status().text
        return [
            self._candidate(str(e["title"]), str(e["link"]), _as_date(e["published"]))
            for e in parse_feed(text)
        ]

    def _discover_html(self) -> list[EnforcementCandidate]:
        if not self.item_selector:
            _LOGGER.warning(
                "state_ag %s kind=html with empty item_selector", self.agency_slug
            )
            return []
        html = self.client.get(self.url).raise_for_status().text
        soup = BeautifulSoup(html, "html.parser")
        out: list[EnforcementCandidate] = []
        for el in soup.select(self.item_selector):
            href = el.get("href")
            if not href:
                continue
            # el.get() can return str | list[str] | None; guard to str only
            if not isinstance(href, str):
                href = str(href)
            published = _time_date(el)
            out.append(self._candidate(el.get_text(strip=True), href, published))
        return out

    def discover(
        self, *, since: dt.datetime | None = None, limit: int = 20
    ) -> list[EnforcementCandidate]:
        cutoff = since.date() if since is not None else None
        try:
            cands = (
                self._discover_rss() if self.kind == "rss" else self._discover_html()
            )
        except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
            _LOGGER.warning(
                "state_ag %s discover failed (isolated): %s", self.agency_slug, exc
            )
            return []
        out: list[EnforcementCandidate] = []
        for cand in cands:
            if (
                cutoff is not None
                and cand.published is not None
                and cand.published < cutoff
            ):
                continue
            out.append(cand)
            if len(out) >= limit:
                break
        return out

    def fetch_text(self, candidate: EnforcementCandidate) -> str:
        return extract_article_text(
            self.client.get(candidate.url).raise_for_status().text
        )
