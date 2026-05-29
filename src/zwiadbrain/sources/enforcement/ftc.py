"""FTC enforcement source: press-release RSS discovery + article-text fetch."""

from __future__ import annotations

import datetime as dt

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from zwiadbrain.exceptions import SourceError, SourceFetchError
from zwiadbrain.sources.enforcement.base import (
    EnforcementCandidate,
    extract_article_text,
    parse_feed,
)

FTC_PRESS_RSS = "https://www.ftc.gov/feeds/press-release.xml"


class _Retryable(SourceError):
    """Transient HTTP status that should be retried."""


class FTCSource:
    """FTC press-release RSS source implementing :class:`EnforcementSource`."""

    name = "ftc"
    agency = "FTC"
    agency_slug = "ftc"
    jurisdiction = "US"

    def __init__(
        self,
        rss_url: str = FTC_PRESS_RSS,
        *,
        client: httpx.Client | None = None,
        max_attempts: int = 4,
        wait_initial: float = 1.0,
        wait_max: float = 30.0,
        timeout: float = 30.0,
    ) -> None:
        self.rss_url = rss_url
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._retrying = Retrying(
            retry=retry_if_exception_type((_Retryable, httpx.TransportError)),
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=wait_initial, max=wait_max),
            reraise=True,
        )

    def _get(self, url: str) -> httpx.Response:
        def _once() -> httpx.Response:
            resp = self.client.get(url)
            if resp.status_code >= 500:
                raise _Retryable(f"FTC returned {resp.status_code} for {url}")
            if resp.status_code >= 400:
                raise SourceFetchError(f"FTC returned {resp.status_code} for {url}")
            return resp

        try:
            return self._retrying(_once)
        except _Retryable as exc:
            raise SourceFetchError(f"FTC fetch failed after retries: {exc}") from exc

    def discover(
        self, *, since: dt.datetime | None = None, limit: int = 20
    ) -> list[EnforcementCandidate]:
        cutoff = since.date() if since is not None else None
        entries = parse_feed(self._get(self.rss_url).text)
        out: list[EnforcementCandidate] = []
        for entry in entries:
            raw_published = entry["published"]
            published: dt.date | None = (
                raw_published if isinstance(raw_published, dt.date) else None
            )
            if cutoff is not None and published is not None and published < cutoff:
                continue
            out.append(
                EnforcementCandidate(
                    source=self.name,
                    agency=self.agency,
                    agency_slug=self.agency_slug,
                    jurisdiction=self.jurisdiction,
                    title=str(entry["title"]),
                    url=str(entry["link"]),
                    published=published,
                    raw={"summary": entry["summary"]},
                )
            )
            if len(out) >= limit:
                break
        return out

    def fetch_text(self, candidate: EnforcementCandidate) -> str:
        return extract_article_text(self._get(candidate.url).text)
