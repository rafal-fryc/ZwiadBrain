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

from zwiadbrain.exceptions import ConfigError, RateLimitError, SourceError, SourceFetchError
from zwiadbrain.models import Action, Amendment, Bill, TextVersion
from zwiadbrain.pipeline.ids import build_state_bill_id, format_state_bill_number
from zwiadbrain.sources._redact import redact_api_key
from zwiadbrain.sources.base import Candidate

LEGISCAN_API_BASE = "https://api.legiscan.com/"
_LOGGER = logging.getLogger(__name__)
# Substrings that mark a body-level ERROR as a quota exhaustion (D51 — undocumented, so
# matched leniently; any other ERROR is a plain fetch failure).
_QUOTA_MARKERS: tuple[str, ...] = ("limit", "quota", "exceeded")
_STATUS_TEXT: dict[int, str] = {
    0: "Prefiled", 1: "Introduced", 2: "Engrossed", 3: "Enrolled",
    4: "Passed", 5: "Vetoed", 6: "Failed",
}
_CHAPTERED_EVENT = 8  # progress[].event code for Chaptered (enactment signal)
_PASSED_STATUS = 4


class _Retryable(SourceError):
    """Internal marker for a transient HTTP status that should be retried."""

    def __init__(self, status: int, op: str) -> None:
        super().__init__(f"transient LegiScan error {status} for op={op}")
        self.status = status
        self.op = op


def _is_quota(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _QUOTA_MARKERS)


def _opt_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _items(value: Any) -> list[dict[str, Any]]:
    return value if value is not None else []


def _obj(value: Any) -> dict[str, Any]:
    return value if value is not None else {}


def _parse_date(value: Any) -> dt.date | None:
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

    def discover(
        self,
        *,
        congress: int | None = None,  # noqa: ARG002  — federal-only; LegiScan ignores it
        since: dt.datetime | None = None,  # noqa: ARG002 — v1 uses year=2 (current)
        limit: int = 20,
    ) -> list[Candidate]:
        """Search the state's current session for ``self.query`` → relevance-ranked candidates.

        ``getSearchRaw`` returns only ``relevance``/``bill_id``/``change_hash`` per result
        (no titles), because the full-text query is the recall stage (D50). The federal
        title ``keyword_filter`` therefore does not apply here.
        """
        if not self.query:
            raise ConfigError("LegiScanSource.discover requires a search query")
        payload = self._get("getSearchRaw", state=self.state, query=self.query, year=2)
        results = _items(_obj(payload.get("searchresult")).get("results"))
        candidates: list[Candidate] = []
        for entry in results[:limit]:
            bill_id = entry.get("bill_id")
            if bill_id is None:
                continue
            candidates.append(
                Candidate(
                    source=self.name,
                    native_id=str(bill_id),
                    jurisdiction=f"US-{self.state.upper()}",
                    title="",
                    raw={
                        "relevance": entry.get("relevance"),
                        "change_hash": entry.get("change_hash"),
                    },
                )
            )
        total = _obj(_obj(payload.get("searchresult")).get("summary")).get("count")
        if isinstance(total, int) and total > len(candidates):
            _LOGGER.info(
                "discovery kept %d of %d search results for state=%s",
                len(candidates), total, self.state,
            )
        return candidates

    def change_hashes(self) -> dict[int, str]:
        """Return ``{bill_id: change_hash}`` for the state's current session (refresh cursor).

        One ``getMasterListRaw?state=`` call covers the whole session. The ``masterlist``
        container is a numeric-keyed object whose values are bill entries; a non-bill
        member (e.g. a ``session`` sub-object) is skipped by requiring a ``bill_id``.
        """
        masterlist = _obj(self._get("getMasterListRaw", state=self.state).get("masterlist"))
        out: dict[int, str] = {}
        for entry in masterlist.values():
            row = _obj(entry)
            bill_id = row.get("bill_id")
            change_hash = row.get("change_hash")
            if bill_id is None or change_hash is None:
                continue
            out[int(bill_id)] = str(change_hash)
        return out

    def _to_bill(self, detail: dict[str, Any]) -> Bill:
        session = _obj(detail.get("session"))
        year_start = int(session.get("year_start") or 0)
        state = str(detail.get("state") or self.state).upper()
        raw_number = str(detail.get("bill_number") or "")
        status_int = int(detail.get("status") or 0)
        events = {int(p.get("event") or 0) for p in _items(detail.get("progress"))}
        enacted = status_int == _PASSED_STATUS or _CHAPTERED_EVENT in events
        sponsors = sorted(
            _items(detail.get("sponsors")),
            key=lambda s: (int(s.get("sponsor_type_id") or 9), int(s.get("sponsor_order") or 99)),
        )
        sponsor_names = [str(s.get("name")) for s in sponsors if s.get("name")]
        history = _items(detail.get("history"))
        actions = [
            Action(
                date=_parse_date(h.get("date")),
                text=str(h.get("action") or ""),
                chamber=_opt_str(h.get("chamber")),
            )
            for h in history
        ]
        actions.sort(key=lambda a: (a.date is None, a.date or dt.date.min))
        introduced = actions[0].date if actions else None
        text_versions = [
            TextVersion(
                code=str(t.get("type") or ""),
                date=_parse_date(t.get("date")),
                url=_opt_str(t.get("state_link") or t.get("url")),
            )
            for t in _items(detail.get("texts"))
        ]
        amendments = [
            Amendment(
                number=str(a.get("title") or a.get("amendment_id") or ""),
                chamber=_opt_str(a.get("chamber")),
                status="adopted" if a.get("adopted") else None,
                latest_action_date=_parse_date(a.get("date")),
            )
            for a in _items(detail.get("amendments"))
        ]
        related = [
            f"{s.get('type')}: {s.get('sast_bill_number')}"
            for s in _items(detail.get("sasts"))
            if s.get("sast_bill_number")
        ]
        sources: dict[str, str] = {}
        if detail.get("url"):
            sources["LegiScan"] = str(detail["url"])
        if detail.get("state_link"):
            sources["State source"] = str(detail["state_link"])
        return Bill(
            id=build_state_bill_id(state, year_start, raw_number),
            jurisdiction=f"US-{state}",
            title=str(detail.get("title") or ""),
            bill_number=format_state_bill_number(raw_number),
            chamber=_opt_str(detail.get("body")),
            session=_opt_str(session.get("session_name")),
            status=_STATUS_TEXT.get(status_int),
            sponsors=sponsor_names,
            introduced_date=introduced,
            latest_action=actions[-1].text if actions else None,
            latest_action_date=actions[-1].date if actions else None,
            enacted=enacted,
            summary=_opt_str(detail.get("description")),
            actions=actions,
            amendments=amendments,
            text_versions=text_versions,
            related_bills=related,
            change_hash=_opt_str(detail.get("change_hash")),
            update_date=_opt_str(detail.get("status_date")),
            legiscan_bill_id=int(detail["bill_id"]) if detail.get("bill_id") is not None else None,
            sources=sources,
        )
