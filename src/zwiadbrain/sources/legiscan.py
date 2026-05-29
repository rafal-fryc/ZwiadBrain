"""LegiScan query-API source: discover, refresh-detect, and enrich state bills.

Discovery uses ``getSearchRaw`` (server-side full-text search → relevance-ranked
``bill_id`` candidates); refresh detection uses ``getMasterListRaw`` (one call per
state returns every bill's ``change_hash``); enrichment uses ``getBill``. Transport is
httpx with a tenacity retry on transient (5xx / network) failures; HTTP 429 and a body
``status == "ERROR"`` are surfaced as typed errors. The key is ``?key=`` query-param
auth and is redacted before any string reaches a log or message (D47/D51).
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from zwiadbrain.exceptions import RateLimitError, SourceError, SourceFetchError
from zwiadbrain.models import Bill
from zwiadbrain.sources._redact import redact_api_key

LEGISCAN_API_BASE = "https://api.legiscan.com/"
_LOGGER = logging.getLogger(__name__)
# Substrings that mark a body-level ERROR as a quota exhaustion (D51 — undocumented, so
# matched leniently; any other ERROR is a plain fetch failure).
_QUOTA_MARKERS: tuple[str, ...] = ("limit", "quota", "exceeded")


class _Retryable(SourceError):
    """Internal marker for a transient HTTP status that should be retried."""

    def __init__(self, status: int, op: str) -> None:
        super().__init__(f"transient LegiScan error {status} for op={op}")
        self.status = status
        self.op = op


def _is_quota(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _QUOTA_MARKERS)


def _opt_str(value: Any) -> str | None:  # pyright: ignore[reportUnusedFunction]  # used in T5
    return str(value) if value is not None else None


def _items(value: Any) -> list[dict[str, Any]]:  # pyright: ignore[reportUnusedFunction]  # used in T5
    return value if value is not None else []


def _obj(value: Any) -> dict[str, Any]:
    return value if value is not None else {}


def _parse_date(value: Any) -> dt.date | None:  # pyright: ignore[reportUnusedFunction]  # used in T5
    """Parse a LegiScan ``YYYY-MM-DD`` date, treating the ``0000-00-00`` placeholder as None."""
    text = str(value or "")
    if not text or text.startswith("0000"):
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


class LegiScanSource:
    """LegiScan query-API client implementing the :class:`Source` protocol for one state."""

    name = "legiscan"

    def __init__(
        self,
        api_key: str,
        state: str,
        *,
        query: str | None = None,
        client: httpx.Client | None = None,
        base_url: str = LEGISCAN_API_BASE,
        max_attempts: int = 5,
        wait_initial: float = 1.0,
        wait_max: float = 30.0,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.state = state.lower()
        self.query = query
        self.base_url = base_url
        self.client = client or httpx.Client(timeout=timeout)
        self._retrying = Retrying(
            retry=retry_if_exception_type((_Retryable, httpx.TransportError)),
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=wait_initial, max=wait_max),
            reraise=True,
        )

    # --- transport ------------------------------------------------------

    def _request(self, op: str, params: dict[str, str | int]) -> httpx.Response:
        full: dict[str, str | int] = {"key": self.api_key, "op": op, **params}
        response = self.client.get(self.base_url, params=full)
        if response.status_code == 429:
            raise RateLimitError(f"LegiScan rate limit hit for op={op}")
        if response.status_code >= 500:
            raise _Retryable(response.status_code, op)
        if response.status_code >= 400:
            raise SourceFetchError(f"LegiScan returned {response.status_code} for op={op}")
        return response

    def _get(self, op: str, **params: str | int) -> dict[str, Any]:
        try:
            response = self._retrying(self._request, op, params)
        except _Retryable as exc:
            raise SourceFetchError(
                f"LegiScan op={exc.op} failed {exc.status} after retries"
            ) from exc
        data: dict[str, Any] = response.json()
        if data.get("status") == "ERROR":
            message = str(_obj(data.get("alert")).get("message") or "")
            if _is_quota(message):
                raise RateLimitError(
                    f"LegiScan quota exhausted (op={op}): {redact_api_key(message)}"
                )
            raise SourceFetchError(
                f"LegiScan op={op} returned ERROR: {redact_api_key(message)}"
            )
        return data

    # --- enrichment (T5) ------------------------------------------------

    def fetch(self, native_id: str) -> Bill:
        """Fetch a single bill by LegiScan ``bill_id`` and map it to a :class:`Bill`."""
        bill = _obj(self._get("getBill", id=native_id).get("bill"))
        return self._to_bill(bill)

    def fetch_policy_area(self, native_id: str) -> str | None:
        """States need no policyArea probe — full-text search is the recall stage (D50)."""
        return None

    def _to_bill(self, detail: dict[str, Any]) -> Bill:  # fleshed out in T5
        raise NotImplementedError
