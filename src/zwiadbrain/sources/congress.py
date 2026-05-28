"""Congress.gov v3 source: discover federal bills and enrich them into ``Bill``s.

Discovery lists a congress's bills (newest-updated first) as lightweight
candidates; enrichment fans out to the per-bill sub-resources (actions,
amendments, text, summaries, related bills) and maps everything onto the common
:class:`~zwiadbrain.models.Bill`. Transport is httpx with a tenacity retry on
transient (5xx / network) failures; 429 surfaces as :class:`RateLimitError`.

The Congress.gov change cursor is split across two fields on the bill:
``update_date`` (bare ``updateDate`` — bumps on any change) and
``update_date_text`` (``updateDateIncludingText`` — bumps when text/summary
changes).  Pass A compares both to decide what to refresh.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from zwiadbrain.exceptions import RateLimitError, SourceError, SourceFetchError
from zwiadbrain.models import Action, Amendment, Bill, TextVersion, Vote
from zwiadbrain.sources.base import Candidate

CONGRESS_API_BASE = "https://api.congress.gov/v3"

_TYPE_DISPLAY: dict[str, str] = {
    "HR": "H.R.",
    "S": "S.",
    "HJRES": "H.J.Res.",
    "SJRES": "S.J.Res.",
    "HCONRES": "H.Con.Res.",
    "SCONRES": "S.Con.Res.",
    "HRES": "H.Res.",
    "SRES": "S.Res.",
}
_TYPE_URL_SEGMENT: dict[str, str] = {
    "HR": "house-bill",
    "S": "senate-bill",
    "HJRES": "house-joint-resolution",
    "SJRES": "senate-joint-resolution",
    "HCONRES": "house-concurrent-resolution",
    "SCONRES": "senate-concurrent-resolution",
    "HRES": "house-resolution",
    "SRES": "senate-resolution",
}
_AMENDMENT_DISPLAY: dict[str, str] = {"HAMDT": "H.Amdt.", "SAMDT": "S.Amdt."}
_AMENDMENT_CHAMBER: dict[str, str] = {"HAMDT": "House", "SAMDT": "Senate"}
_PUBLIC_LAW_RE = re.compile(r"Public Law No:?\s*(\d+-\d+)")


class _Retryable(SourceError):
    """Internal marker for a transient HTTP status that should be retried."""

    def __init__(self, status: int, path: str) -> None:
        super().__init__(f"transient Congress.gov error {status} for {path}")
        self.status = status
        self.path = path


def _opt_str(value: Any) -> str | None:
    """Coerce an optional JSON scalar to ``str | None``."""
    return str(value) if value is not None else None


def _parse_date(value: Any) -> dt.date | None:
    """Parse a Congress.gov date or datetime (``YYYY-MM-DD`` / ISO ``...Z``)."""
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _obj(value: Any) -> dict[str, Any]:
    """Coerce an optional JSON value to a dict (Congress.gov payloads are untyped)."""
    return value if value is not None else {}


def _items(value: Any) -> list[dict[str, Any]]:
    """Coerce an optional JSON value to a list of dicts."""
    return value if value is not None else []


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _format_bill_number(bill_type: str, number: Any) -> str:
    return f"{_TYPE_DISPLAY.get(bill_type.upper(), bill_type.upper())} {number}"


def _public_url(congress: int, bill_type: str, number: Any) -> str:
    segment = _TYPE_URL_SEGMENT.get(bill_type.upper(), "bill")
    return f"https://www.congress.gov/bill/{_ordinal(congress)}-congress/{segment}/{number}"


def _extract_public_law(text: str | None) -> str | None:
    if not text:
        return None
    match = _PUBLIC_LAW_RE.search(text)
    return match.group(1) if match else None


def _strip_html(html: str) -> str:
    return " ".join(BeautifulSoup(html, "html.parser").get_text(separator=" ").split())


def _latest_summary(summaries: list[dict[str, Any]]) -> str | None:
    """Return the most recent official summary as plain text, or None."""
    if not summaries:
        return None
    latest = max(summaries, key=lambda s: str(s.get("actionDate") or ""))
    text = _strip_html(str(latest.get("text") or ""))
    return text or None


def _to_action(raw: dict[str, Any]) -> Action:
    return Action(
        date=_parse_date(raw.get("actionDate")),
        text=str(raw.get("text") or ""),
        action_type=_opt_str(raw.get("type")),
    )


def _build_timeline(actions: list[dict[str, Any]]) -> list[Action]:
    """Map a bill's actions into a deduplicated, oldest-first status timeline.

    Congress returns actions newest-first, so reverse before the stable date-sort:
    same-date actions then read chronologically (introduced before referred) rather
    than in reverse. Congress also repeats some actions across source systems
    (identical date + text); collapse those to one row, keeping first occurrence.
    """
    timeline = [_to_action(a) for a in reversed(actions)]
    timeline.sort(key=lambda a: (a.date is None, a.date or dt.date.min))
    deduped: list[Action] = []
    seen: set[tuple[dt.date | None, str]] = set()
    for action in timeline:
        key = (action.date, action.text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return deduped


def _to_amendment(raw: dict[str, Any]) -> Amendment:
    amdt_type = str(raw.get("type") or "").upper()
    number = str(raw.get("number") or "")
    if amdt_type in _AMENDMENT_DISPLAY:
        designation = f"{_AMENDMENT_DISPLAY[amdt_type]} {number}"
    else:
        designation = number
    latest = _obj(raw.get("latestAction"))
    return Amendment(
        number=designation,
        chamber=_AMENDMENT_CHAMBER.get(amdt_type),
        status=_opt_str(latest.get("text")),
        latest_action_date=_parse_date(latest.get("actionDate")),
        what_changed=_opt_str(raw.get("purpose") or raw.get("description")),
    )


def _to_text_version(raw: dict[str, Any]) -> TextVersion:
    formats = _items(raw.get("formats"))
    url: str | None = None
    for fmt in formats:
        if str(fmt.get("type")) == "Formatted Text":
            url = _opt_str(fmt.get("url"))
            break
    if url is None and formats:
        url = _opt_str(formats[0].get("url"))
    return TextVersion(code=str(raw.get("type") or ""), date=_parse_date(raw.get("date")), url=url)


def _to_related(raw: dict[str, Any]) -> str:
    number = raw.get("number")
    label = _format_bill_number(str(raw.get("type") or ""), number)
    congress = raw.get("congress")
    return f"{label} ({_ordinal(int(congress))})" if congress is not None else label


class CongressSource:
    """Congress.gov v3 client implementing the :class:`Source` protocol."""

    name = "congress"

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        base_url: str = CONGRESS_API_BASE,
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
            wait=wait_exponential(multiplier=wait_initial, max=wait_max),
            reraise=True,
        )

    # --- transport ------------------------------------------------------

    def _request(self, path: str, params: dict[str, str | int]) -> httpx.Response:
        full: dict[str, str | int] = {"api_key": self.api_key, "format": "json", **params}
        response = self.client.get(f"{self.base_url}{path}", params=full)
        if response.status_code == 429:
            raise RateLimitError(f"Congress.gov rate limit hit for {path}")
        if response.status_code >= 500:
            raise _Retryable(response.status_code, path)
        if response.status_code >= 400:
            raise SourceFetchError(f"Congress.gov returned {response.status_code} for {path}")
        return response

    def _get_json(self, path: str, **params: str | int) -> dict[str, Any]:
        try:
            response = self._retrying(self._request, path, params)
        except _Retryable as exc:
            raise SourceFetchError(
                f"Congress.gov returned {exc.status} for {exc.path} after retries"
            ) from exc
        data: dict[str, Any] = response.json()
        return data

    # --- discovery ------------------------------------------------------

    def discover(
        self,
        *,
        congress: int | None = None,
        since: dt.datetime | None = None,
        limit: int = 20,
    ) -> list[Candidate]:
        """List bills (newest-updated first) as candidates.

        With ``congress`` set, lists that congress; otherwise lists across
        congresses. ``limit`` ≤ 250 maps to a single request (pagination-following
        for larger windows is added with the scheduled scan phase).
        """
        path = f"/bill/{congress}" if congress is not None else "/bill"
        params: dict[str, str | int] = {"sort": "updateDate desc", "limit": min(max(limit, 1), 250)}
        if since is not None:
            params["fromDateTime"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = self._get_json(path, **params)
        bills = _items(payload.get("bills"))
        return [self._to_candidate(bill) for bill in bills][:limit]

    def _to_candidate(self, raw: dict[str, Any]) -> Candidate:
        bill_type = str(raw.get("type") or "")
        return Candidate(
            source=self.name,
            native_id=f"{raw.get('congress')}/{bill_type.lower()}/{raw.get('number')}",
            jurisdiction="US",
            title=str(raw.get("title") or ""),
            update_date=_opt_str(raw.get("updateDateIncludingText") or raw.get("updateDate")),
            raw=raw,
        )

    def fetch_policy_area(self, native_id: str) -> str | None:
        """Fetch only a bill's ``policyArea`` name via one core-detail request.

        The Stage-2 recall probe: cheap (no sub-resources) so a wide scan can be
        re-checked by topic when a bill's title carries no keyword seed.
        """
        congress, bill_type, number = native_id.split("/")
        detail = _obj(self._get_json(f"/bill/{congress}/{bill_type}/{number}").get("bill"))
        return _opt_str(_obj(detail.get("policyArea")).get("name"))

    # --- enrichment -----------------------------------------------------

    def fetch(self, native_id: str) -> Bill:
        """Fetch a bill and its sub-resources and map them to a :class:`Bill`."""
        congress, bill_type, number = native_id.split("/")
        base = f"/bill/{congress}/{bill_type}/{number}"
        detail = _obj(self._get_json(base).get("bill"))
        actions = _items(self._get_json(f"{base}/actions").get("actions"))
        amendments = _items(self._get_json(f"{base}/amendments").get("amendments"))
        texts = _items(self._get_json(f"{base}/text").get("textVersions"))
        summaries = _items(self._get_json(f"{base}/summaries").get("summaries"))
        related = _items(self._get_json(f"{base}/relatedbills").get("relatedBills"))
        return self._to_bill(detail, actions, amendments, texts, summaries, related)

    def _to_bill(
        self,
        detail: dict[str, Any],
        actions: list[dict[str, Any]],
        amendments: list[dict[str, Any]],
        texts: list[dict[str, Any]],
        summaries: list[dict[str, Any]],
        related: list[dict[str, Any]],
    ) -> Bill:
        congress = int(detail.get("congress") or 0)
        bill_type = str(detail.get("type") or "")
        number = detail.get("number")
        latest = _obj(detail.get("latestAction"))
        latest_text = _opt_str(latest.get("text"))
        laws = _items(detail.get("laws"))
        public_law = _opt_str(laws[0].get("number")) if laws else _extract_public_law(latest_text)
        enacted = bool(laws) or bool(latest_text and "Became Public Law" in latest_text)
        sponsors = [
            str(s.get("fullName")) for s in _items(detail.get("sponsors")) if s.get("fullName")
        ]
        policy_area = _obj(detail.get("policyArea"))

        return Bill(
            id=f"{congress}-{bill_type.lower()}-{number}",
            jurisdiction="US",
            title=str(detail.get("title") or ""),
            bill_number=_format_bill_number(bill_type, number),
            chamber=_opt_str(detail.get("originChamber")),
            congress=str(congress),
            status=latest_text,
            policy_area=_opt_str(policy_area.get("name")),
            sponsors=sponsors,
            introduced_date=_parse_date(detail.get("introducedDate")),
            latest_action=latest_text,
            latest_action_date=_parse_date(latest.get("actionDate")),
            enacted=enacted,
            public_law=public_law,
            summary=_latest_summary(summaries),
            actions=_build_timeline(actions),
            amendments=[_to_amendment(a) for a in amendments],
            text_versions=[_to_text_version(t) for t in texts],
            related_bills=[_to_related(r) for r in related],
            update_date=_opt_str(detail.get("updateDate")),
            update_date_text=_opt_str(detail.get("updateDateIncludingText")),
            sources={"Congress.gov": _public_url(congress, bill_type, number)},
        )

    # --- recorded votes -------------------------------------------------------

    def recorded_votes(self, native_id: str) -> list[Vote]:
        """Return recorded votes for a bill from its actions sub-resource.

        This makes its own independent ``GET /bill/{congress}/{type}/{number}/actions``
        request — even if the caller has already fetched the bill (and thus its
        actions) elsewhere, this does not reuse that payload. One extra GET on an
        on-demand single-bill command is acceptable; the orchestration phase may
        thread a shared actions payload through later if it matters.

        Each Congress.gov action may carry a ``recordedVotes`` list.  For each
        item in that list one :class:`Vote` is emitted, using the recorded vote's
        own ``date`` if present, falling back to the parent action's
        ``actionDate``.  ``result`` is left ``None`` — the roll-call URL is the
        verifiable link for downstream grounding.
        """
        congress, bill_type, number = native_id.split("/")
        path = f"/bill/{congress}/{bill_type}/{number}/actions"
        actions = _items(self._get_json(path).get("actions"))
        votes: list[Vote] = []
        for action in actions:
            for rv in _items(action.get("recordedVotes")):
                date_val = rv.get("date") or action.get("actionDate")
                votes.append(
                    Vote(
                        date=_parse_date(date_val),
                        chamber=_opt_str(rv.get("chamber")),
                        result=None,
                        roll_call_url=_opt_str(rv.get("url")),
                    )
                )
        return votes
