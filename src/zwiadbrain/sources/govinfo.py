"""GovInfo API client: legislative-history enricher for federal bills.

Maps GovInfo's REST API onto the project's leg-history domain models
(:class:`~zwiadbrain.models.CommitteeReport`, :class:`~zwiadbrain.models.Enactment`,
:class:`~zwiadbrain.models.Hearing`, :class:`~zwiadbrain.models.FloorAction`).

This is a *leg-history enricher*, not a discover/fetch Source — it does not
implement the ``Source`` protocol and has no ``discover`` / ``fetch`` methods.
Transport mirrors :class:`~zwiadbrain.sources.congress.CongressSource`:
an httpx.Client with tenacity retry on 5xx / network errors; 429 surfaces as
:class:`~zwiadbrain.exceptions.RateLimitError`.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import re
from typing import Any, cast

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.wait import wait_base

from zwiadbrain.exceptions import RateLimitError, SourceError, SourceFetchError
from zwiadbrain.models import CommitteeReport, Enactment, FloorAction, Hearing, StatutesAtLarge
from zwiadbrain.sources._redact import redact_api_key

GOVINFO_API_BASE = "https://api.govinfo.gov"

_PLAW_RE = re.compile(r"^PLAW-(\d+)publ(\d+)$")


# ---------------------------------------------------------------------------
# Pure module-level helpers (pinned public surface for T7)
# ---------------------------------------------------------------------------


def enrolled_bill_package_id(congress: int, bill_type: str, number: int | str) -> str:
    """Return the GovInfo packageId for an enrolled bill.

    Example: ``enrolled_bill_package_id(118, "HR", 8818)`` → ``"BILLS-118hr8818enr"``.
    """
    return f"BILLS-{congress}{bill_type.lower()}{number}enr"


def details_url(package_id: str, granule_id: str | None = None) -> str:
    """Return the human-clickable GovInfo details URL for a package.

    If *granule_id* is provided it is appended as a path segment.
    """
    base = f"https://www.govinfo.gov/app/details/{package_id}"
    return f"{base}/{granule_id}" if granule_id else base


def _parse_public_law(package_id: str) -> str | None:
    """Parse a PLAW packageId to a ``"{congress}-{number}"`` public law string.

    Returns ``None`` if *package_id* does not match the ``PLAW-NNNpublNN`` pattern.
    """
    match = _PLAW_RE.search(package_id)
    return f"{match.group(1)}-{match.group(2)}" if match else None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_date(value: Any) -> dt.date | None:
    """Tolerant date parser: ``YYYY-MM-DD`` prefix or full ISO string → date."""
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _flatten_str(value: Any) -> str | None:
    """Coerce a GovInfo search-result field to ``str | None``, tolerating lists.

    GovInfo's ``/search`` API (currently in public preview) returns fields like
    ``governmentAuthor`` as either a string (e.g. ``"House Committee on …"``) or a
    list (e.g. ``["Congress", "House of Representatives", "Committee on …"]``).
    For list values we return the LAST non-empty string element (the most-specific
    name); ``None`` / empty / unexpected types collapse to ``None``.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, list):
        # Pyright narrows isinstance(list) to list[Unknown]; cast restores Any so the
        # iteration item is typed (genuinely untyped JSON — matches the dict[str, Any]
        # discipline used throughout this module).
        items = cast(list[Any], value)
        for item in reversed(items):
            if isinstance(item, str) and item:
                return item
        return None
    return None


class _Retryable(SourceError):
    """Internal marker for a transient HTTP status that should be retried."""

    def __init__(self, status: int, path: str, *, retry_after: float | None = None) -> None:
        super().__init__(f"transient GovInfo error {status} for {path}")
        self.status = status
        self.path = path
        self.retry_after = retry_after


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Parse a ``Retry-After`` header to non-negative seconds, or ``None`` if absent/invalid.

    Accepts the two RFC 7231 forms: an integer delta-seconds, or an HTTP-date (in which
    case the wait is the date minus now, floored at 0). Anything unparseable → ``None``.
    """
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return float(raw)
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    delta = (parsed - dt.datetime.now(dt.UTC)).total_seconds()
    return max(delta, 0.0)


class _wait_retry_after(wait_base):
    """Wait the exception's ``Retry-After`` seconds if present, else fall back to exponential."""

    def __init__(self, fallback: wait_base) -> None:
        self._fallback = fallback

    def __call__(self, retry_state: Any) -> float:
        outcome = retry_state.outcome
        if outcome is not None and outcome.failed:
            exc = outcome.exception()
            if isinstance(exc, _Retryable) and exc.retry_after is not None:
                return exc.retry_after
        return self._fallback(retry_state)


# ---------------------------------------------------------------------------
# GovInfoSource
# ---------------------------------------------------------------------------


class GovInfoSource:
    """GovInfo API client that maps API responses to leg-history domain models."""

    name = "govinfo"

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        base_url: str = GOVINFO_API_BASE,
        max_attempts: int = 5,
        wait_initial: float = 1.0,
        wait_max: float = 30.0,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=timeout)
        self._retrying = Retrying(
            retry=retry_if_exception_type((_Retryable, httpx.TransportError)),
            stop=stop_after_attempt(max_attempts),
            wait=_wait_retry_after(wait_exponential(multiplier=wait_initial, max=wait_max)),
            reraise=True,
        )

    # --- transport ----------------------------------------------------------

    def _handle_response(self, response: httpx.Response, path: str) -> httpx.Response:
        """Raise the appropriate error class based on HTTP status."""
        if response.status_code == 429:
            raise RateLimitError(f"GovInfo rate limit hit for {path}")
        if response.status_code >= 500:
            raise _Retryable(
                response.status_code, path, retry_after=_retry_after_seconds(response)
            )
        if response.status_code >= 400:
            raise SourceFetchError(f"GovInfo returned {response.status_code} for {path}")
        return response

    def _request_get(self, path: str, params: dict[str, str | int]) -> httpx.Response:
        full: dict[str, str | int] = {"api_key": self.api_key, **params}
        response = self.client.get(f"{self.base_url}{path}", params=full)
        return self._handle_response(response, path)

    def _request_post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        response = self.client.post(
            f"{self.base_url}{path}",
            json=body,
            params={"api_key": self.api_key},
        )
        return self._handle_response(response, path)

    def _get_json(self, path: str, **params: str | int) -> dict[str, Any]:
        """GET *path* with query params, retry on transient errors, return parsed JSON."""
        try:
            response = self._retrying(self._request_get, path, params)
        except _Retryable as exc:
            raise SourceFetchError(
                f"GovInfo returned {exc.status} for {redact_api_key(exc.path)} after retries"
            ) from exc
        data: dict[str, Any] = response.json()
        return data

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST *path* with JSON *body*, retry on transient errors, return parsed JSON."""
        try:
            response = self._retrying(self._request_post, path, body)
        except _Retryable as exc:
            raise SourceFetchError(
                f"GovInfo returned {exc.status} for {redact_api_key(exc.path)} after retries"
            ) from exc
        data: dict[str, Any] = response.json()
        return data

    # --- primitives ---------------------------------------------------------

    def related(self, access_id: str, collection: str) -> list[dict[str, Any]]:
        """Return the ``results`` list from ``GET /related/{accessId}/{collection}``."""
        path = f"/related/{access_id}/{collection}"
        payload = self._get_json(path)
        results: list[dict[str, Any]] = payload.get("results") or []
        return results

    def package_summary(self, package_id: str) -> dict[str, Any]:
        """Return the summary metadata dict from ``GET /packages/{packageId}/summary``."""
        path = f"/packages/{package_id}/summary"
        data: dict[str, Any] = self._get_json(path)
        return data

    def search(
        self,
        query: str,
        *,
        page_size: int = 50,
        result_level: str = "default",
        historical: bool = False,
    ) -> list[dict[str, Any]]:
        """POST ``/search`` and return the ``results`` list (single page).

        GovInfo search is a "public preview" endpoint — results are parsed
        tolerantly (``dict.get`` only; never key-access that can raise KeyError).
        """
        body: dict[str, Any] = {
            "query": query,
            "pageSize": str(page_size),
            "offsetMark": "*",
            "resultLevel": result_level,
            "historical": historical,
            "sorts": [{"field": "publishdate", "sortOrder": "ASC"}],
        }
        payload = self._post_json("/search", body)
        results: list[dict[str, Any]] = payload.get("results") or []
        return results

    # --- typed leg-history fragments ----------------------------------------

    def committee_reports(
        self, congress: int, bill_type: str, number: int | str
    ) -> list[CommitteeReport]:
        """Return committee reports for a bill as :class:`CommitteeReport` objects."""
        pkg_id = enrolled_bill_package_id(congress, bill_type, number)
        results = self.related(pkg_id, "CRPT")
        return [
            CommitteeReport(
                citation=_flatten_str(r.get("title")) or "",
                url=details_url(str(r.get("packageId") or "")),
            )
            for r in results
            if r.get("packageId")
        ]

    def fetch_statutes_at_large(self, plaw_package_id: str) -> StatutesAtLarge | None:
        """Resolve a PLAW package's Statutes-at-Large citation, or ``None`` if absent.

        Calls ``GET /related/{plawPackageId}/STATUTE``.  Some PLAW packages do
        not yet have a published STATUTE row (the volume hasn't been printed),
        in which case the related list is empty and this returns ``None``
        (fail-quiet, matching the project's "no link, no render" rule).
        """
        results = self.related(plaw_package_id, "STATUTE")
        if not results:
            return None
        first = results[0]
        package_id = str(first.get("packageId") or "")
        if not package_id:
            return None
        title = _flatten_str(first.get("title")) or package_id
        return StatutesAtLarge(citation=title, url=details_url(package_id))

    def enacted_law(
        self, congress: int, bill_type: str, number: int | str
    ) -> Enactment | None:
        """Return enactment metadata for a bill, or ``None`` if no PLAW record exists."""
        pkg_id = enrolled_bill_package_id(congress, bill_type, number)
        results = self.related(pkg_id, "PLAW")
        if not results:
            return None
        first = results[0]
        package_id = str(first.get("packageId") or "")
        return Enactment(
            public_law=_parse_public_law(package_id),
            statutes_at_large=self.fetch_statutes_at_large(package_id) if package_id else None,
            url=details_url(package_id) if package_id else None,
            date_signed=None,
        )

    def hearings(self, congress: int, citation: str) -> list[Hearing]:
        """Return congressional hearings related to *citation* as :class:`Hearing` objects."""
        safe = citation.replace('"', '\\"')
        query = f'collection:CHRG AND congress:{congress} AND "{safe}"'
        results = self.search(query)
        hearings: list[Hearing] = []
        for r in results:
            package_id = str(r.get("packageId") or "")
            granule_id = _flatten_str(r.get("granuleId"))
            hearings.append(
                Hearing(
                    title=_flatten_str(r.get("title")) or "",
                    committee=_flatten_str(r.get("governmentAuthor")),
                    chamber=None,
                    date=_parse_date(r.get("dateIssued")),
                    citation=package_id or None,
                    url=details_url(package_id, granule_id) if package_id else None,
                )
            )
        return hearings

    def record_references(self, congress: int, citation: str) -> list[FloorAction]:
        """Return Congressional Record references for *citation* as :class:`FloorAction` objects."""
        safe = citation.replace('"', '\\"')
        query = f'collection:CREC AND congress:{congress} AND "{safe}"'
        results = self.search(query)
        actions: list[FloorAction] = []
        for r in results:
            package_id = str(r.get("packageId") or "")
            granule_id = _flatten_str(r.get("granuleId"))
            actions.append(
                FloorAction(
                    date=_parse_date(r.get("dateIssued")),
                    chamber=None,
                    congressional_record=_flatten_str(r.get("title")),
                    url=details_url(package_id, granule_id) if package_id else None,
                )
            )
        return actions
