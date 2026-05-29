# Phase 07 — State legislation via LegiScan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track AI/privacy/cyber state legislation via LegiScan — discover + classify + render state bills (backfill) and detect changes via `change_hash` incremental sync (refresh) — mirroring the federal flow, built for all 50 states but validated on the 7 priority states.

**Architecture:** A new `LegiScanSource` (httpx + tenacity, one instance per state) maps the LegiScan query API onto the existing `Bill` model. Two new deterministic CLI halves (`fetch-state-candidates`, `fetch-state-refreshable`) bracket the existing interactive subagents; the existing `render-classified` / `render-refreshed` halves are reused unchanged. Python makes zero LLM calls (D26).

**Tech Stack:** Python 3.12, httpx, tenacity, pydantic v2, typer, respx (test), pytest, ruff, pyright --strict.

**Spec:** `docs/superpowers/specs/2026-05-29-phase07-state-legislation-design.md`. Decisions logged this phase: D48 (state id + `legiscan_bill_id`), D49 (50-state scope), D50 (query API + `change_hash` cursor), D51 (error/redaction handling).

**Conventions for every task:** TDD (write test → watch fail → implement → watch pass → commit). Run the gate with `uv run pytest`, `uv run ruff check .`, `uv run pyright`. Atomic commit per task. All HTTP is mocked with respx — no live calls in tests.

---

## Phase file (create before Task 1)

Create `.claude/phases/PHASE-07-active.md` (the user's one-active-phase rule):

```markdown
# Phase 07 — State legislation via LegiScan (backfill + refresh)
Status: ACTIVE

> Full design: docs/superpowers/specs/2026-05-29-phase07-state-legislation-design.md
> Full plan:   docs/superpowers/plans/2026-05-29-phase07-state-legislation.md
> Decisions:   D48 (state id + legiscan_bill_id), D49 (50-state scope),
>              D50 (query API + change_hash cursor), D51 (error/redaction).

## Goal
State bills become first-class tracked pages: LegiScan-backed discovery/classify/
render (the /zwiad-scan-states backfill) plus change_hash incremental refresh folded
into /zwiad-refresh. Built for 50 states, validated on the priority 7.

## Tasks
- [ ] T1  — _redact: mask key= as well as api_key=
- [ ] T2  — models: add Bill.legiscan_bill_id
- [ ] T3  — ids: build_state_bill_id + format_state_bill_number
- [ ] T4  — LegiScanSource transport + error/redaction
- [ ] T5  — LegiScanSource.fetch (getBill -> Bill mapping)
- [ ] T6  — LegiScanSource.discover (getSearchRaw)
- [ ] T7  — LegiScanSource.change_hashes (getMasterListRaw)
- [ ] T8  — config: require_legiscan_api_key
- [ ] T9  — refresh: detect_state_refreshable
- [ ] T10 — cli: fetch-state-candidates
- [ ] T11 — cli: fetch-state-refreshable
- [ ] T12 — slash commands: /zwiad-scan-states (new) + /zwiad-refresh (extend)
- [ ] T13 — DECISIONS.md D48-D51 + ARCHITECTURE/PLAN/toml updates
- [ ] T14 — quality gate + version bump 0.7.0 + PHASE-07 done
- [ ] T15 — live UAT (CA priority states)

## Acceptance Criteria
- A LegiScan getBill fixture maps to a Bill with id `ca-2023-sb-362`, jurisdiction
  `US-CA`, legiscan_bill_id set, byte-identical re-render (D20).
- getSearchRaw discovery yields relevance-ordered bill_id candidates; getMasterListRaw
  change_hash diffing re-fetches only changed bills.
- /zwiad-scan-states renders real CA pages; /zwiad-refresh covers federal + state in
  one run.
- ruff + pyright (strict) + pytest all green; v0.7.0 tagged.
- DECISIONS.md carries D48-D51.

## Decisions Made This Phase
(append as you go)
```

Then: `git add .claude/phases/PHASE-07-active.md && git commit -m "chore(phase07): open phase — state legislation via LegiScan"`

---

## Task 1: `_redact` masks `key=` as well as `api_key=`

LegiScan auth is `?key=` (D51). The single redactor must mask both param names.

**Files:**
- Modify: `src/zwiadbrain/sources/_redact.py`
- Test: `tests/test_redact.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_redact.py`:

```python
def test_redact_api_key_masks_bare_key_param() -> None:
    """should redact a LegiScan-style ?key= value while leaving other params intact"""
    url = "https://api.legiscan.com/?key=SECRET123&op=getBill&id=42"
    out = redact_api_key(url)
    assert "SECRET123" not in out
    assert "key=REDACTED" in out
    assert "op=getBill" in out


def test_redact_api_key_does_not_double_count_api_key_as_key() -> None:
    """should redact api_key= as a whole, not leave a stray 'key=' fragment"""
    out = redact_api_key("?api_key=SECRET")
    assert out == "?api_key=REDACTED"
    assert "key=REDACTED" not in out.replace("api_key=REDACTED", "")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_redact.py -v`
Expected: FAIL — `key=SECRET123` not redacted (current regex only matches `api_key=`).

- [ ] **Step 3: Implement**

Replace the regex and function body in `src/zwiadbrain/sources/_redact.py`:

```python
# Matches both `api_key=<value>` and a bare `key=<value>` (LegiScan). The \b before
# the alternation, plus listing api_key first, prevents the inner "key" of "api_key"
# from matching separately: "_key" has no word boundary, so \bkey= never fires there.
_SECRET_PARAM_RE = re.compile(r"\b(api_key|key)=[^&\s]+")


def redact_api_key(text: str) -> str:
    """Replace every ``api_key=``/``key=`` value in *text* with ``…=REDACTED``."""
    return _SECRET_PARAM_RE.sub(r"\1=REDACTED", text)
```

Update the module docstring's final line to: `This collapses any api_key= or key= query value to REDACTED.`

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_redact.py -v`
Expected: PASS (all four tests, including the two pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/sources/_redact.py tests/test_redact.py
git commit -m "feat(redact): mask LegiScan key= param as well as api_key="
```

---

## Task 2: `Bill.legiscan_bill_id` field

The stable native cursor key for refresh (the wiki id doesn't contain it). `None` for federal; round-trips via the existing `model_dump(exclude_none=True)`.

**Files:**
- Modify: `src/zwiadbrain/models.py` (the `Bill` class, near `change_hash`)
- Test: `tests/test_schema.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_schema.py` (imports `Bill`, `to_frontmatter`, `from_page` already present — add any missing):

```python
def test_state_bill_roundtrips_legiscan_bill_id() -> None:
    """should serialize legiscan_bill_id for a state bill and read it back unchanged"""
    bill = Bill(
        id="ca-2023-sb-362",
        jurisdiction="US-CA",
        title="Data broker registration.",
        bill_number="SB 362",
        session="2023-2024 Regular Session",
        legiscan_bill_id=1789012,
        change_hash="abc123",
    )
    fm = to_frontmatter(bill)
    assert fm["legiscan_bill_id"] == 1789012
    page = render_page(bill)
    parsed = from_page(page)
    assert isinstance(parsed, Bill)
    assert parsed.legiscan_bill_id == 1789012


def test_federal_bill_omits_legiscan_bill_id() -> None:
    """should drop legiscan_bill_id from frontmatter when it is None (federal)"""
    bill = Bill(id="118-hr-1", jurisdiction="US", title="X", bill_number="H.R. 1")
    assert "legiscan_bill_id" not in to_frontmatter(bill)
```

If `render_page` isn't imported in `test_schema.py`, add `from zwiadbrain.pipeline.render import render_page`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_schema.py -k legiscan -v`
Expected: FAIL — `Bill` has no field `legiscan_bill_id` (pydantic raises on the kwarg).

- [ ] **Step 3: Implement**

In `src/zwiadbrain/models.py`, in `class Bill`, add the field next to `change_hash` (around line 211):

```python
    change_hash: str | None = None
    # LegiScan internal bill_id (state bills only; None for federal). The stable native
    # cursor key used by refresh to match a page against a getMasterListRaw entry — the
    # wiki id does not contain it (D48).
    legiscan_bill_id: int | None = None
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_schema.py -k legiscan -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/models.py tests/test_schema.py
git commit -m "feat(models): add Bill.legiscan_bill_id state-native cursor key (D48)"
```

---

## Task 3: state id builder + display formatter

Pure functions in the shared id module. Split the verbatim `bill_number` into prefix + trailing-digit-run.

**Files:**
- Modify: `src/zwiadbrain/pipeline/ids.py`
- Test: `tests/test_ids.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_ids.py`:

```python
import pytest

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.pipeline.ids import build_state_bill_id, format_state_bill_number


@pytest.mark.parametrize(
    ("state", "year", "number", "expected"),
    [
        ("CA", 2023, "SB362", "ca-2023-sb-362"),
        ("CA", 2023, "AB1", "ca-2023-ab-1"),
        ("MD", 2019, "SB0181", "md-2019-sb-181"),   # leading zeros stripped
        ("CA", 2023, "SBX12", "ca-2023-sbx-12"),     # special session, trailing-digit split
        ("ny", 2023, "S1234", "ny-2023-s-1234"),
    ],
)
def test_build_state_bill_id(state: str, year: int, number: str, expected: str) -> None:
    """should build a globally-unique lowercased state id from state/year/bill_number"""
    assert build_state_bill_id(state, year, number) == expected


def test_build_state_bill_id_rejects_number_without_trailing_digits() -> None:
    """should raise ConfigError on a bill number with no trailing digit run"""
    with pytest.raises(ConfigError):
        build_state_bill_id("CA", 2023, "SBA")


def test_two_states_same_number_do_not_collide() -> None:
    """should produce distinct ids for the same bill number in two states (global key)"""
    assert build_state_bill_id("CA", 2023, "SB1") != build_state_bill_id("NY", 2023, "SB1")


@pytest.mark.parametrize(
    ("number", "expected"),
    [("SB362", "SB 362"), ("AB1", "AB 1"), ("SB0181", "SB 181"), ("SBX12", "SBX 12")],
)
def test_format_state_bill_number(number: str, expected: str) -> None:
    """should render a display bill number with a space and stripped leading zeros"""
    assert format_state_bill_number(number) == expected
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_ids.py -k "state" -v`
Expected: FAIL — `build_state_bill_id` / `format_state_bill_number` not defined.

- [ ] **Step 3: Implement**

Append to `src/zwiadbrain/pipeline/ids.py`:

```python
import re

# A bill number is a non-digit-run prefix followed by a trailing run of digits.
# Lazy prefix + anchored trailing \d+ partitions losslessly: prefix + digits == input.
# Special sessions (e.g. CA "SBX12") split to ("SBX", "12") — deterministic and unique
# within a (state, year) pair even though it does not segment the X-marker (D48).
_BILL_NUMBER_RE = re.compile(r"^(.*?)(\d+)$")


def _split_bill_number(raw: str) -> tuple[str, str]:
    """Split a LegiScan bill number into (prefix, number) with leading zeros stripped.

    Raises :class:`ConfigError` when *raw* has no trailing digit run (e.g. a letter
    suffix), so a malformed number is a surfaced data error rather than a bad id.
    """
    match = _BILL_NUMBER_RE.match(raw.strip())
    if match is None or not match.group(1):
        raise ConfigError(f"state bill number must be <prefix><digits>, got: {raw!r}")
    prefix = match.group(1)
    number = match.group(2).lstrip("0") or "0"
    return prefix, number


def build_state_bill_id(state: str, year_start: int, bill_number: str) -> str:
    """Build a state bill's wiki id: ``{state}-{year_start}-{type}-{number}`` (D48).

    Globally unique (the state prefix and integer-leading federal ids never collide);
    lowercased; the type/number come from splitting the verbatim *bill_number*.
    """
    prefix, number = _split_bill_number(bill_number)
    return f"{state.lower()}-{year_start}-{prefix.lower()}-{number}"


def format_state_bill_number(bill_number: str) -> str:
    """Render a display bill number: uppercased prefix, a space, stripped-zero number."""
    prefix, number = _split_bill_number(bill_number)
    return f"{prefix.upper()} {number}"
```

(Move the `import re` to the top of the file with the other imports if ruff prefers; keep `from __future__ import annotations` first.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_ids.py -v`
Expected: PASS (existing federal `parse_bill_id` tests still pass too).

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/pipeline/ids.py tests/test_ids.py
git commit -m "feat(ids): add build_state_bill_id + format_state_bill_number (D48)"
```

---

## Task 4: `LegiScanSource` transport + error/redaction

The httpx/tenacity skeleton, the `{status, …}` envelope handling, and `body.status == "ERROR"` branching (D51). Discovery/fetch mapping come in T5–T7.

**Files:**
- Create: `src/zwiadbrain/sources/legiscan.py`
- Create: `tests/fixtures/legiscan/error_quota.json`, `tests/fixtures/legiscan/error_other.json`
- Create: `tests/test_legiscan.py`

- [ ] **Step 1: Create the error fixtures**

`tests/fixtures/legiscan/error_quota.json`:
```json
{ "status": "ERROR", "alert": { "message": "Subscription query limit exceeded" } }
```

`tests/fixtures/legiscan/error_other.json`:
```json
{ "status": "ERROR", "alert": { "message": "Unknown bill id" } }
```

- [ ] **Step 2: Add failing tests**

Create `tests/test_legiscan.py`:

```python
"""Tests for the LegiScan source: transport, error/quota handling, redaction, mapping.

All HTTP is mocked with respx against committed fixture JSON — no live calls. Requests
are routed by the `op` query parameter via a side_effect handler.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from zwiadbrain.exceptions import RateLimitError, SourceFetchError
from zwiadbrain.sources.legiscan import LEGISCAN_API_BASE, LegiScanSource

_FIX = Path(__file__).parent / "fixtures" / "legiscan"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def _source(state: str = "ca", *, query: str | None = None) -> LegiScanSource:
    return LegiScanSource("test-key", state, query=query, max_attempts=3, wait_initial=0.0)


def _route_by_op(mock: respx.MockRouter, mapping: dict[str, dict[str, Any]]) -> None:
    """Route every GET to the base URL, returning the fixture for the request's `op`."""
    def handler(request: httpx.Request) -> httpx.Response:
        op = request.url.params.get("op", "")
        return httpx.Response(200, json=mapping[op])
    mock.get(url=LEGISCAN_API_BASE).mock(side_effect=handler)


def test_error_status_with_quota_message_raises_rate_limit() -> None:
    """should raise RateLimitError when the body status is ERROR with a quota message"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("error_quota.json")})
        with pytest.raises(RateLimitError):
            _source().fetch("42")


def test_error_status_other_message_raises_fetch_error() -> None:
    """should raise SourceFetchError on a non-quota ERROR body"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("error_other.json")})
        with pytest.raises(SourceFetchError):
            _source().fetch("42")


def test_http_429_raises_rate_limit() -> None:
    """should raise RateLimitError on an HTTP 429"""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=LEGISCAN_API_BASE).respond(status_code=429)
        with pytest.raises(RateLimitError):
            _source().fetch("42")


def test_http_500_retries_then_raises_fetch_error() -> None:
    """should retry a 5xx and surface SourceFetchError after attempts are exhausted"""
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(url=LEGISCAN_API_BASE).respond(status_code=503)
        with pytest.raises(SourceFetchError):
            _source().fetch("42")
        assert route.call_count == 3
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_legiscan.py -v`
Expected: FAIL — `zwiadbrain.sources.legiscan` does not exist.

- [ ] **Step 4: Implement the transport skeleton**

Create `src/zwiadbrain/sources/legiscan.py`:

```python
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


def _opt_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _items(value: Any) -> list[dict[str, Any]]:
    return value if isinstance(value, list) else []


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
            raise SourceFetchError(f"LegiScan op={exc.op} failed {exc.status} after retries") from exc
        data: dict[str, Any] = response.json()
        if data.get("status") == "ERROR":
            message = str(_obj(data.get("alert")).get("message") or "")
            if _is_quota(message):
                raise RateLimitError(f"LegiScan quota exhausted (op={op}): {redact_api_key(message)}")
            raise SourceFetchError(f"LegiScan op={op} returned ERROR: {redact_api_key(message)}")
        return data

    # --- enrichment (T5) ------------------------------------------------

    def fetch(self, native_id: str) -> Bill:
        """Fetch a single bill by LegiScan ``bill_id`` and map it to a :class:`Bill`."""
        bill = _obj(self._get("getBill", id=native_id).get("bill"))
        return self._to_bill(bill)

    def fetch_policy_area(self, native_id: str) -> str | None:
        """States need no policyArea probe — full-text search is the recall stage (D50)."""
        return None
```

(`_to_bill`, `discover`, `change_hashes` are added in T5–T7. This task leaves `fetch` referencing `_to_bill`, which T5 adds; the T4 tests only reach the error branches before `_to_bill` is called — the ERROR/HTTP paths raise inside `_get`, so `_to_bill` is never invoked. To keep T4 importable and green, add a minimal stub now and flesh it out in T5:)

Add a temporary stub at the end of the class so the module imports cleanly:

```python
    def _to_bill(self, detail: dict[str, Any]) -> Bill:  # fleshed out in T5
        raise NotImplementedError
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_legiscan.py -v`
Expected: PASS (all four T4 tests; the error/HTTP paths raise before `_to_bill`).

- [ ] **Step 6: Commit**

```bash
git add src/zwiadbrain/sources/legiscan.py tests/test_legiscan.py tests/fixtures/legiscan/
git commit -m "feat(legiscan): source transport + error/quota/redaction handling (D50/D51)"
```

---

## Task 5: `LegiScanSource.fetch` — `getBill` → `Bill` mapping

**Files:**
- Modify: `src/zwiadbrain/sources/legiscan.py` (replace the `_to_bill` stub)
- Create: `tests/fixtures/legiscan/getBill.json`
- Test: `tests/test_legiscan.py`

- [ ] **Step 1: Create the getBill fixture**

`tests/fixtures/legiscan/getBill.json` (CA SB 362, the Delete Act — verified schema shape):

```json
{
  "status": "OK",
  "bill": {
    "bill_id": 1789012,
    "change_hash": "abc123def4567890abc123def4567890",
    "session_id": 1995,
    "session": {
      "session_id": 1995,
      "state_id": 5,
      "year_start": 2023,
      "year_end": 2024,
      "prefile": 0,
      "sine_die": 1,
      "prior": 1,
      "special": 0,
      "session_tag": "Regular Session",
      "session_title": "2023-2024 Regular Session",
      "session_name": "2023-2024 Regular Session"
    },
    "url": "https://legiscan.com/CA/bill/SB362/2023",
    "state_link": "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202320240SB362",
    "completed": 1,
    "status": 4,
    "status_date": "2023-10-10",
    "progress": [
      { "date": "2023-02-08", "event": 1 },
      { "date": "2023-10-10", "event": 8 }
    ],
    "state": "CA",
    "state_id": 5,
    "bill_number": "SB362",
    "bill_type": "B",
    "bill_type_id": "1",
    "body": "S",
    "current_body": "S",
    "title": "Data broker registration: accessible deletion mechanism.",
    "description": "The California Delete Act requires data brokers to register and honor deletion requests.",
    "pending_committee_id": 0,
    "committee": {},
    "referrals": [],
    "history": [
      { "date": "2023-02-08", "action": "Introduced. Read first time.", "chamber": "S", "chamber_id": 35, "importance": 1 },
      { "date": "2023-10-10", "action": "Chaptered by Secretary of State. Chapter 709.", "chamber": "S", "chamber_id": 35, "importance": 1 }
    ],
    "sponsors": [
      { "people_id": 4718, "name": "Josh Becker", "first_name": "Josh", "last_name": "Becker", "party": "D", "role": "Sen", "role_id": 2, "sponsor_type_id": 1, "sponsor_order": 1, "committee_sponsor": 0, "committee_id": "0" },
      { "people_id": 5001, "name": "Bill Dodd", "first_name": "Bill", "last_name": "Dodd", "party": "D", "role": "Sen", "role_id": 2, "sponsor_type_id": 2, "sponsor_order": 2, "committee_sponsor": 0, "committee_id": "0" }
    ],
    "sasts": [
      { "type_id": 1, "type": "Same As", "sast_bill_number": "AB1194", "sast_bill_id": 1789500 }
    ],
    "subjects": [ { "subject_id": 3309, "subject_name": "Privacy" } ],
    "texts": [
      { "doc_id": 2700111, "date": "2023-02-08", "type": "Introduced", "type_id": 1, "mime": "application/pdf", "mime_id": 2, "url": "https://legiscan.com/CA/text/SB362/id/2700111", "state_link": "https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202320240SB362" },
      { "doc_id": 2900222, "date": "2023-10-10", "type": "Chaptered", "type_id": 6, "mime": "application/pdf", "mime_id": 2, "url": "https://legiscan.com/CA/text/SB362/id/2900222", "state_link": "https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202320240SB362&chap=1" }
    ],
    "votes": [],
    "amendments": [],
    "supplements": [],
    "calendar": []
  }
}
```

- [ ] **Step 2: Add failing tests**

Append to `tests/test_legiscan.py`:

```python
import datetime as dt  # noqa: E402  (add to the top import block if preferred)

from zwiadbrain.models import Bill  # noqa: E402


def test_fetch_maps_getbill_to_state_bill() -> None:
    """should map a getBill payload onto a Bill with the D48 id and US-CA jurisdiction"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("getBill.json")})
        bill = _source().fetch("1789012")
    assert isinstance(bill, Bill)
    assert bill.id == "ca-2023-sb-362"
    assert bill.jurisdiction == "US-CA"
    assert bill.legiscan_bill_id == 1789012
    assert bill.bill_number == "SB 362"
    assert bill.session == "2023-2024 Regular Session"
    assert bill.congress is None
    assert bill.change_hash == "abc123def4567890abc123def4567890"
    assert bill.sources["LegiScan"] == "https://legiscan.com/CA/bill/SB362/2023"


def test_fetch_marks_chaptered_bill_enacted() -> None:
    """should treat status==4 / a Chaptered progress event as enacted"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("getBill.json")})
        bill = _source().fetch("1789012")
    assert bill.enacted is True


def test_fetch_maps_sponsors_primary_first_and_timeline() -> None:
    """should order sponsors primary-first and map history into a dated timeline"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("getBill.json")})
        bill = _source().fetch("1789012")
    assert bill.sponsors[0] == "Josh Becker"
    assert bill.introduced_date == dt.date(2023, 2, 8)
    assert bill.actions[0].date == dt.date(2023, 2, 8)
    assert bill.actions[-1].text.startswith("Chaptered")
    assert [t.code for t in bill.text_versions] == ["Introduced", "Chaptered"]
    assert bill.related_bills == ["Same As: AB1194"]


def test_state_bill_renders_to_states_path_and_roundtrips() -> None:
    """should render a state bill under states/ca/bills and re-render byte-identically"""
    from zwiadbrain.pipeline.render import page_path, render_page
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getBill": _fixture("getBill.json")})
        bill = _source().fetch("1789012")
    assert page_path(bill, Path("wiki")).as_posix().endswith("wiki/states/ca/bills/ca-2023-sb-362.md")
    assert render_page(bill) == render_page(bill)
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_legiscan.py -k fetch_maps -v`
Expected: FAIL — `_to_bill` raises `NotImplementedError`.

- [ ] **Step 4: Implement `_to_bill`**

In `src/zwiadbrain/sources/legiscan.py`, add the imports and replace the `_to_bill` stub.

Add to the imports block:
```python
from zwiadbrain.models import Action, Amendment, Bill, TextVersion
from zwiadbrain.pipeline.ids import build_state_bill_id, format_state_bill_number
```
(Remove the now-duplicate bare `from zwiadbrain.models import Bill`.)

Add the status map near the top-level constants:
```python
_STATUS_TEXT: dict[int, str] = {
    0: "Prefiled", 1: "Introduced", 2: "Engrossed", 3: "Enrolled",
    4: "Passed", 5: "Vetoed", 6: "Failed",
}
_CHAPTERED_EVENT = 8  # progress[].event code for Chaptered (enactment signal)
_PASSED_STATUS = 4
```

Replace the `_to_bill` stub with:
```python
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
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_legiscan.py -v`
Expected: PASS (all T4 + T5 tests).

- [ ] **Step 6: Commit**

```bash
git add src/zwiadbrain/sources/legiscan.py tests/test_legiscan.py tests/fixtures/legiscan/getBill.json
git commit -m "feat(legiscan): map getBill onto Bill (id/status/sponsors/timeline) (D48)"
```

---

## Task 6: `LegiScanSource.discover` — `getSearchRaw`

**Files:**
- Modify: `src/zwiadbrain/sources/legiscan.py`
- Create: `tests/fixtures/legiscan/getSearchRaw.json`
- Test: `tests/test_legiscan.py`

- [ ] **Step 1: Create the fixture**

`tests/fixtures/legiscan/getSearchRaw.json`:
```json
{
  "status": "OK",
  "searchresult": {
    "summary": { "page": "1 of 1", "range": "1 - 3", "relevancy": "100% - 80%", "count": 3, "page_current": 1, "page_total": 1 },
    "results": [
      { "relevance": 100, "bill_id": 1789012, "change_hash": "abc123" },
      { "relevance": 92, "bill_id": 1789055, "change_hash": "def456" },
      { "relevance": 81, "bill_id": 1789099, "change_hash": "ghi789" }
    ]
  }
}
```

- [ ] **Step 2: Add failing tests**

Append to `tests/test_legiscan.py`:

```python
from zwiadbrain.exceptions import ConfigError  # noqa: E402


def test_discover_maps_search_results_to_candidates() -> None:
    """should yield relevance-ordered bill_id candidates with US-CA jurisdiction"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getSearchRaw": _fixture("getSearchRaw.json")})
        cands = _source(query="privacy").discover(limit=10)
    assert [c.native_id for c in cands] == ["1789012", "1789055", "1789099"]
    assert cands[0].jurisdiction == "US-CA"
    assert cands[0].source == "legiscan"
    assert cands[0].title == ""  # getSearchRaw returns no titles
    assert cands[0].raw["change_hash"] == "abc123"


def test_discover_respects_limit() -> None:
    """should return no more than `limit` candidates"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getSearchRaw": _fixture("getSearchRaw.json")})
        cands = _source(query="privacy").discover(limit=2)
    assert len(cands) == 2


def test_discover_without_query_raises() -> None:
    """should raise ConfigError when discover is called with no search query bound"""
    with pytest.raises(ConfigError):
        _source(query=None).discover(limit=5)
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_legiscan.py -k discover -v`
Expected: FAIL — `LegiScanSource` has no `discover`.

- [ ] **Step 4: Implement**

Add the import to the top of `legiscan.py`:
```python
from zwiadbrain.exceptions import ConfigError, RateLimitError, SourceError, SourceFetchError
```
(merge with the existing exceptions import line) and:
```python
from zwiadbrain.sources.base import Candidate
```

Add the method to the class (after `fetch_policy_area`):
```python
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
                    raw={"relevance": entry.get("relevance"), "change_hash": entry.get("change_hash")},
                )
            )
        total = _obj(_obj(payload.get("searchresult")).get("summary")).get("count")
        if isinstance(total, int) and total > len(candidates):
            _LOGGER.info("discovery kept %d of %d search results for state=%s",
                         len(candidates), total, self.state)
        return candidates
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_legiscan.py -k discover -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/zwiadbrain/sources/legiscan.py tests/test_legiscan.py tests/fixtures/legiscan/getSearchRaw.json
git commit -m "feat(legiscan): discover via getSearchRaw (full-text recall, D50)"
```

---

## Task 7: `LegiScanSource.change_hashes` — `getMasterListRaw`

**Files:**
- Modify: `src/zwiadbrain/sources/legiscan.py`
- Create: `tests/fixtures/legiscan/getMasterListRaw.json`
- Test: `tests/test_legiscan.py`

- [ ] **Step 1: Create the fixture**

`tests/fixtures/legiscan/getMasterListRaw.json` (numeric-keyed object; defensively includes a stray non-bill entry to prove it's skipped):
```json
{
  "status": "OK",
  "masterlist": {
    "session": { "session_id": 1995, "session_name": "2023-2024 Regular Session" },
    "0": { "bill_id": 1789012, "number": "SB362", "change_hash": "abc123-NEW" },
    "1": { "bill_id": 1789055, "number": "SB400", "change_hash": "def456" }
  }
}
```

- [ ] **Step 2: Add failing test**

Append to `tests/test_legiscan.py`:

```python
def test_change_hashes_maps_bill_id_to_hash_skipping_non_bill_entries() -> None:
    """should return {bill_id: change_hash}, skipping the masterlist 'session' sub-object"""
    with respx.mock(assert_all_called=False) as mock:
        _route_by_op(mock, {"getMasterListRaw": _fixture("getMasterListRaw.json")})
        hashes = _source().change_hashes()
    assert hashes == {1789012: "abc123-NEW", 1789055: "def456"}
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_legiscan.py -k change_hashes -v`
Expected: FAIL — no `change_hashes` method.

- [ ] **Step 4: Implement**

Add to the class:
```python
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
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_legiscan.py -v`
Expected: PASS (entire LegiScan suite).

- [ ] **Step 6: Commit**

```bash
git add src/zwiadbrain/sources/legiscan.py tests/test_legiscan.py tests/fixtures/legiscan/getMasterListRaw.json
git commit -m "feat(legiscan): change_hashes via getMasterListRaw (refresh cursor, D50)"
```

---

## Task 8: `config.require_legiscan_api_key`

**Files:**
- Modify: `src/zwiadbrain/config.py` (the `Settings` class)
- Test: `tests/test_config.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_config.py`:

```python
def test_require_legiscan_api_key_returns_value_when_set() -> None:
    """should return the LegiScan key when present"""
    settings = Settings(legiscan_api_key="lk-123")
    assert settings.require_legiscan_api_key() == "lk-123"


def test_require_legiscan_api_key_raises_when_unset() -> None:
    """should raise ConfigError when the LegiScan key is missing"""
    with pytest.raises(ConfigError):
        Settings(legiscan_api_key=None).require_legiscan_api_key()
```

(Ensure `from zwiadbrain.config import Settings` and `from zwiadbrain.exceptions import ConfigError` and `import pytest` are present in the file.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_config.py -k legiscan -v`
Expected: FAIL — no `require_legiscan_api_key`.

- [ ] **Step 3: Implement**

In `src/zwiadbrain/config.py`, after `require_govinfo_api_key`:
```python
    def require_legiscan_api_key(self) -> str:
        """Return the LegiScan API key, raising :class:`ConfigError` if it is unset."""
        if not self.legiscan_api_key:
            raise ConfigError(
                "LEGISCAN_API_KEY is not set — add it to .env (free key: https://legiscan.com/legiscan)"
            )
        return self.legiscan_api_key
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_config.py -k legiscan -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/config.py tests/test_config.py
git commit -m "feat(config): add require_legiscan_api_key accessor"
```

---

## Task 9: `detect_state_refreshable`

State refresh gates on `change_hash` (not `update_date`); reuses `_amendment_delta` + `summary_hash`.

**Files:**
- Modify: `src/zwiadbrain/pipeline/refresh.py`
- Test: `tests/test_refresh.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_refresh.py` (it already imports `Bill`; add `detect_state_refreshable`):

```python
from zwiadbrain.pipeline.refresh import detect_state_refreshable


def _state_bill(**over: object) -> Bill:
    base: dict[str, object] = dict(
        id="ca-2023-sb-362", jurisdiction="US-CA", title="T", bill_number="SB 362",
        session="2023-2024 Regular Session", legiscan_bill_id=1789012,
        change_hash="hash-A", summary="alpha", tracking=True,
    )
    base.update(over)
    return Bill(**base)


def test_detect_state_refreshable_none_when_hash_unchanged() -> None:
    """should return None when the change_hash matches (cheap gate)"""
    prev = _state_bill()
    fresh = _state_bill(summary="beta")  # other fields differ, but hash is the same
    assert detect_state_refreshable(prev, fresh) is None


def test_detect_state_refreshable_triggers_on_hash_change_and_summary() -> None:
    """should flag classifier+summarizer when the hash advanced and the summary changed"""
    prev = _state_bill(change_hash="hash-A", summary="alpha")
    fresh = _state_bill(change_hash="hash-B", summary="beta")
    result = detect_state_refreshable(prev, fresh)
    assert result is not None
    assert result.needs_classifier is True
    assert result.needs_summarizer is True


def test_detect_state_refreshable_none_for_untracked_prev() -> None:
    """should never refresh a bill that is already untracked"""
    prev = _state_bill(tracking=False, change_hash="hash-A")
    fresh = _state_bill(change_hash="hash-B")
    assert detect_state_refreshable(prev, fresh) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_refresh.py -k state_refreshable -v`
Expected: FAIL — no `detect_state_refreshable`.

- [ ] **Step 3: Implement**

In `src/zwiadbrain/pipeline/refresh.py`, after `detect_refreshable`:
```python
def detect_state_refreshable(prev: Bill, fresh: Bill) -> RefreshableBill | None:
    """State analog of :func:`detect_refreshable`, gated on LegiScan ``change_hash``.

    The cheap gate is the ``change_hash`` (the authoritative LegiScan cursor), not
    ``update_date``. When the hash advanced, ``needs_classifier``/``needs_summarizer``
    are True if the summary changed, and ``changed_amendment_numbers`` is the amendment
    delta — reusing the federal trigger logic. An already-untracked ``prev`` is never
    refreshable.
    """
    if not prev.tracking:
        return None
    if prev.change_hash == fresh.change_hash:
        return None
    text_changed = prev.summary_hash != fresh.summary_hash
    changed = _amendment_delta(prev.amendments, fresh.amendments)
    return RefreshableBill(
        prev=prev,
        fresh=fresh,
        needs_classifier=text_changed,
        needs_summarizer=text_changed,
        changed_amendment_numbers=changed,
    )
```

Note: the tests set `summary` but the trigger compares `summary_hash`. `_state_bill` does not set `summary_hash`, so both are `None` and `text_changed` would be False. Fix the second test to set the hashes explicitly so the trigger fires:

```python
def test_detect_state_refreshable_triggers_on_hash_change_and_summary() -> None:
    """should flag classifier+summarizer when the hash advanced and the summary_hash changed"""
    prev = _state_bill(change_hash="hash-A", summary_hash="sh-A")
    fresh = _state_bill(change_hash="hash-B", summary_hash="sh-B")
    result = detect_state_refreshable(prev, fresh)
    assert result is not None
    assert result.needs_classifier is True
    assert result.needs_summarizer is True
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_refresh.py -k state_refreshable -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/pipeline/refresh.py tests/test_refresh.py
git commit -m "feat(refresh): detect_state_refreshable gated on LegiScan change_hash (D50)"
```

---

## Task 10: CLI `fetch-state-candidates`

**Files:**
- Modify: `src/zwiadbrain/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_cli.py` (uses typer's `CliRunner` + respx; mirror existing CLI tests). Add at top if missing: `from zwiadbrain.sources.legiscan import LEGISCAN_API_BASE`, `import respx`, `import httpx`, `import json`.

```python
def test_fetch_state_candidates_stages_enriched_bills(tmp_path, monkeypatch) -> None:
    """should search a state, enrich the top results, and stage candidates.json"""
    monkeypatch.setenv("LEGISCAN_API_KEY", "lk-test")
    fix = Path(__file__).parent / "fixtures" / "legiscan"
    search = json.loads((fix / "getSearchRaw.json").read_text(encoding="utf-8"))
    bill = json.loads((fix / "getBill.json").read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        op = request.url.params.get("op", "")
        return httpx.Response(200, json={"getSearchRaw": search, "getBill": bill}[op])

    out = tmp_path / "run"
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=LEGISCAN_API_BASE).mock(side_effect=handler)
        result = runner.invoke(app, [
            "fetch-state-candidates", "--state", "ca", "--limit", "1",
            "--query", "privacy", "--out", str(out),
        ])
    assert result.exit_code == 0, result.output
    staged = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert len(staged) == 1
    assert staged[0]["id"] == "ca-2023-sb-362"
```

(Use the module's existing `runner` / `app` fixtures; if the file constructs `CliRunner()` inline per test, follow that pattern.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_cli.py -k fetch_state_candidates -v`
Expected: FAIL — no such command.

- [ ] **Step 3: Implement**

In `src/zwiadbrain/cli.py`, add the import:
```python
from zwiadbrain.sources.legiscan import LegiScanSource
```
and the command (after `render_classified`):
```python
@app.command(name="fetch-state-candidates")
def fetch_state_candidates(
    state: Annotated[str, typer.Option(help="Two-letter state, e.g. ca.")],
    limit: Annotated[int, typer.Option(min=1, help="Max candidates to fetch.")] = 5,
    query: Annotated[
        str | None,
        typer.Option(help="LegiScan full-text query; defaults to topics.yaml seeds."),
    ] = None,
    out: Annotated[Path | None, typer.Option(help="Run directory for candidates.json.")] = None,
    topics: Annotated[Path, typer.Option(help="Relevance taxonomy file.")] = _DEFAULT_TOPICS,
) -> None:
    """Search a state via LegiScan and stage enriched candidate bills for classification.

    The deterministic first half of ``/zwiad-scan-states``: getSearchRaw recall →
    getBill enrich → ``candidates.json`` for the interactive classifier/summarizer
    subagents. The search query is the recall stage (D50), so no title pre-filter runs.
    """
    try:
        if query:
            search_query = query
        else:
            seeds = load_reference(topics).seeds
            # Quote multi-word seeds as exact phrases; OR-join (D50 §8).
            terms = [f'"{s}"' if " " in s else s for s in seeds]
            search_query = " OR ".join(terms)
        api_key = load_settings().require_legiscan_api_key()
        source = LegiScanSource(api_key, state, query=search_query)
        candidates = source.discover(limit=limit)
        bills = [enrich(source, candidate) for candidate in candidates]
        payload = [bill.model_dump(mode="json") for bill in bills]
        path = stage_json(payload, name="candidates.json", out=out)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"fetched {len(bills)} {state} candidate(s) to {path}")
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_cli.py -k fetch_state_candidates -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/cli.py tests/test_cli.py
git commit -m "feat(cli): fetch-state-candidates (LegiScan search -> enrich -> stage)"
```

---

## Task 11: CLI `fetch-state-refreshable`

**Files:**
- Modify: `src/zwiadbrain/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_cli.py`:

```python
def test_fetch_state_refreshable_detects_changed_bill(tmp_path, monkeypatch) -> None:
    """should diff masterlist change_hash and stage only the changed tracked bill"""
    monkeypatch.setenv("LEGISCAN_API_KEY", "lk-test")
    fix = Path(__file__).parent / "fixtures" / "legiscan"
    masterlist = json.loads((fix / "getMasterListRaw.json").read_text(encoding="utf-8"))
    bill = json.loads((fix / "getBill.json").read_text(encoding="utf-8"))

    # Render a tracked CA page whose stored change_hash is STALE vs the masterlist.
    from zwiadbrain.pipeline.render import write_page
    from zwiadbrain.sources.legiscan import LegiScanSource
    src = LegiScanSource("lk-test", "ca")
    page_bill = src._to_bill(bill["bill"])  # noqa: SLF001 — building a fixture page
    page_bill = page_bill.model_copy(update={"change_hash": "abc123-OLD"})
    wiki = tmp_path / "wiki"
    write_page(page_bill, wiki)

    def handler(request: httpx.Request) -> httpx.Response:
        op = request.url.params.get("op", "")
        return httpx.Response(200, json={"getMasterListRaw": masterlist, "getBill": bill}[op])

    out = tmp_path / "run"
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url=LEGISCAN_API_BASE).mock(side_effect=handler)
        result = runner.invoke(app, [
            "fetch-state-refreshable", "--wiki", str(wiki), "--out", str(out),
        ])
    assert result.exit_code == 0, result.output
    staged = json.loads((out / "refreshable.json").read_text(encoding="utf-8"))
    assert len(staged) == 1
    assert staged[0]["bill_id"] == "ca-2023-sb-362"
    assert staged[0]["needs_summarizer"] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_cli.py -k fetch_state_refreshable -v`
Expected: FAIL — no such command.

- [ ] **Step 3: Implement**

Add the imports to `cli.py`:
```python
from zwiadbrain.pipeline.refresh import (
    apply_classifier_flip,
    clear_flip,
    detect_refreshable,
    detect_state_refreshable,
    preserve_leg_history,
    summary_hash,
)
```
(extend the existing refresh import). Add the command:
```python
@app.command(name="fetch-state-refreshable")
def fetch_state_refreshable(
    wiki: Annotated[Path, typer.Option(help="Wiki root to scan for tracked state bills.")] = Path("wiki"),
    out: Annotated[Path | None, typer.Option(help="Run directory for refreshable.json.")] = None,
) -> None:
    """Detect tracked state bills whose LegiScan change_hash advanced (incremental sync).

    One getMasterListRaw per state returns every current-session bill's change_hash;
    only bills whose stored hash differs are re-fetched via getBill. The staged entries
    share the shape `/zwiad-refresh` consumes, so render-refreshed is reused unchanged.
    """
    try:
        api_key = load_settings().require_legiscan_api_key()
        states_dir = wiki / "states"
        if not states_dir.exists():
            typer.echo(f"no states directory under {wiki}", err=True)
            raise typer.Exit(0)
        # Group tracked state bills by state code.
        by_state: dict[str, list[Bill]] = {}
        skipped = 0
        for page_path in sorted(states_dir.glob("*/bills/*.md")):
            try:
                item = from_page(page_path.read_text(encoding="utf-8"))
            except (WikiSchemaError, ConfigError) as exc:
                skipped += 1
                typer.echo(f"skipped {page_path}: {exc}", err=True)
                continue
            if not isinstance(item, Bill) or not item.tracking or item.legiscan_bill_id is None:
                continue
            state = item.jurisdiction.split("-", 1)[-1].lower()
            by_state.setdefault(state, []).append(item)
        entries: list[dict[str, object]] = []
        for state, bills in sorted(by_state.items()):
            source = LegiScanSource(api_key, state)
            hashes = source.change_hashes()
            for prev in bills:
                fresh_hash = hashes.get(prev.legiscan_bill_id or -1)
                if fresh_hash is None or fresh_hash == prev.change_hash:
                    continue  # absent from current session, or unchanged → no getBill
                fresh = source.fetch(str(prev.legiscan_bill_id))
                fresh.summary_hash = summary_hash(fresh.summary)
                fresh.amendments_count = len(fresh.amendments)
                refreshable = detect_state_refreshable(prev, fresh)
                if refreshable is None:
                    continue
                entries.append({
                    "bill_id": prev.id,
                    "prev": prev.model_dump(mode="json"),
                    "fresh": fresh.model_dump(mode="json"),
                    "needs_classifier": refreshable.needs_classifier,
                    "needs_summarizer": refreshable.needs_summarizer,
                    "changed_amendment_numbers": list(refreshable.changed_amendment_numbers),
                })
        path = stage_json(entries, name="refreshable.json", out=out)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"staged {len(entries)} refreshable state bill(s) to {path} ({skipped} skipped)")
```

Note: `prev.summary_hash` on a freshly-rendered page is `None` unless stamped. In the test, `page_bill` came from `_to_bill` without `summary_hash`; `detect_state_refreshable` compares `prev.summary_hash` (None) to `fresh.summary_hash` (set by `summary_hash(fresh.summary)`), so `text_changed` is True → `needs_summarizer True`, matching the assertion. (In production, `render-classified`/`render-refreshed` stamp `summary_hash`, so steady-state prev pages carry it.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_cli.py -k fetch_state_refreshable -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/cli.py tests/test_cli.py
git commit -m "feat(cli): fetch-state-refreshable (getMasterListRaw change_hash diff, D50)"
```

---

## Task 12: slash commands

`/zwiad-scan-states` (new) and `/zwiad-refresh` (extended to add the state pass). These are Markdown command files — no pytest; validated by UAT (T15). Mirror the structure of the existing `.claude/commands/zwiad-backfill.md` and `zwiad-refresh.md`.

**Files:**
- Create: `.claude/commands/zwiad-scan-states.md`
- Modify: `.claude/commands/zwiad-refresh.md`

- [ ] **Step 1: Read the existing command files to match structure**

Run: open `.claude/commands/zwiad-backfill.md` and `.claude/commands/zwiad-refresh.md` and reuse their frontmatter (`allowed-tools`, `description`), step layout, and subagent-dispatch wording verbatim where it applies.

- [ ] **Step 2: Write `/zwiad-scan-states`**

Create `.claude/commands/zwiad-scan-states.md` modeled on `zwiad-backfill.md`, changing only the fetch half. The body must instruct the session to:
1. For each state in `[states].enabled` (or the `--state` arg), run
   `uv run zwiadbrain fetch-state-candidates --state <st> --limit <N> --out data/runs/<id>`.
2. Dispatch the **classifier** subagent on each candidate's `title` + `summary`
   (the LegiScan `description`), applying the disqualify rubric (D17) — identical to
   `/zwiad-backfill`.
3. For in-scope bills, dispatch **summarizer** + **amendment-explainer**; assemble
   `classified.json` (in-scope bills with `topics`/`summary`/`what_changed`).
4. Run `uv run zwiadbrain render-classified --in data/runs/<id>/classified.json`.
5. Run `uv run zwiadbrain reindex`.

Keep the per-state `--limit` prominent (it bounds classifier plan usage, D49). Copy the
exact subagent-invocation phrasing from `zwiad-backfill.md` so the agents are driven
identically.

- [ ] **Step 3: Extend `/zwiad-refresh`**

In `.claude/commands/zwiad-refresh.md`, after the existing `fetch-refreshable` step, add
a parallel step:
- Run `uv run zwiadbrain fetch-state-refreshable --out data/runs/<id>`.
- Merge its `refreshable.json` entries with the federal ones (same schema) into the set
  the classifier/summarizer/amendment-explainer subagents process.
- Feed the merged, subagent-updated entries to the existing single
  `render-refreshed --in data/runs/<id>/refreshed.json` step (unchanged).

State the invariant explicitly in the doc: the union is rendered by one
`render-refreshed` call; state bills carry their new `change_hash`/`legiscan_bill_id`
through unchanged so the next refresh diffs correctly.

- [ ] **Step 4: Verify the CLI commands the docs reference exist**

Run: `uv run zwiadbrain --help`
Expected: `fetch-state-candidates` and `fetch-state-refreshable` both listed.

- [ ] **Step 5: Commit**

```bash
git add .claude/commands/zwiad-scan-states.md .claude/commands/zwiad-refresh.md
git commit -m "feat(commands): /zwiad-scan-states + state pass in /zwiad-refresh"
```

---

## Task 13: decisions + docs

**Files:**
- Modify: `DECISIONS.md`, `ARCHITECTURE.md`, `docs/PLAN.md`, `zwiadbrain.toml`

- [ ] **Step 1: Append D48–D51 to `DECISIONS.md`**

Add four entries in the existing format (date `2026-05-29`). Content per spec §12:
- **D48** — state id `{state}-{year_start}-{type}-{number}` (verbatim bill_number split,
  special sessions self-disambiguate, zeros stripped); adds `Bill.legiscan_bill_id`;
  extends D21.
- **D49** — target = all 50 states, phased rollout (priority-7 first); supersedes D12;
  binding constraint is classifier plan usage (D26), not LegiScan's 30k/mo quota.
- **D50** — LegiScan query API (getSearchRaw/getMasterListRaw/getBill), not the dataset
  API; `change_hash` is the state refresh cursor; full-text search replaces the federal
  title `keyword_filter`.
- **D51** — LegiScan signals failure as HTTP 200 + `{"status":"ERROR", alert?}`; branch
  on `body.status` first (quota-message → RateLimitError, else SourceFetchError); never
  rely on a 429/Retry-After; `_redact` masks `key=` too (extends D46/D47).

- [ ] **Step 2: Update `ARCHITECTURE.md`**

In "Source layout", add `legiscan.py` to `sources/`. In "Slash commands", add
`/zwiad-scan-states` and note `/zwiad-refresh` now covers federal + state. In "Status",
move PHASE-07 from "Not yet implemented" to shipped; bump the version line to v0.7.0
after T14.

- [ ] **Step 3: Update `docs/PLAN.md`**

Change the PHASE-07 bullet from "*Unimplemented.*" to a one-line "shipped as
`/zwiad-scan-states` + state pass in `/zwiad-refresh`; LegiScan query API (D50)."

- [ ] **Step 4: Update `zwiadbrain.toml` comment**

Update the `[states]` comment from "v1 priority states (tracked via LegiScan)." to note
the 50-state goal with a phased rollout (D49) and that the list is the active set.

- [ ] **Step 5: Commit**

```bash
git add DECISIONS.md ARCHITECTURE.md docs/PLAN.md zwiadbrain.toml
git commit -m "docs(phase07): log D48-D51 and update architecture/plan/config"
```

---

## Task 14: quality gate + version bump

**Files:**
- Modify: `pyproject.toml` (or wherever `__version__` is sourced), `src/zwiadbrain/__init__.py`
- Rename: `.claude/phases/PHASE-07-active.md` → `PHASE-07-done.md`

- [ ] **Step 1: Run the full gate**

Run:
```bash
uv run ruff check .
uv run pyright
uv run pytest
```
Expected: ruff clean, pyright 0 errors (the 4 pre-existing `frontmatter` stub warnings are acceptable, unchanged), all tests green. Fix anything that fails before proceeding.

- [ ] **Step 2: Bump the version to 0.7.0**

Update `__version__` (check `src/zwiadbrain/__init__.py`) and `pyproject.toml` `version` to `0.7.0`.

Run: `uv run pytest tests/test_cli.py -k version -v`
Expected: PASS (the `version` command test, if present, asserts the new value — update its expectation if it pins a literal).

- [ ] **Step 3: Mark the phase done**

Tick all task boxes in `.claude/phases/PHASE-07-active.md`, append the outcome notes and any decisions, then rename:
```bash
git mv .claude/phases/PHASE-07-active.md .claude/phases/PHASE-07-done.md
```

- [ ] **Step 4: Commit + annotated tag**

```bash
git add -A
git commit -m "chore(phase07): close phase — state legislation via LegiScan (v0.7.0)"
git tag -a v0.7.0 -m "Phase 7 complete: LegiScan state bills (backfill + change_hash refresh)"
```

(Do not push or open the PR until after UAT — T15.)

---

## Task 15: live UAT (key is in `.env`)

Interactive validation against the real LegiScan API. Not pytest; record results in the
phase file before pushing.

- [ ] **Step 1: Validate the query syntax (the one MEDIUM-confidence risk)**

Run: `uv run zwiadbrain fetch-state-candidates --state ca --limit 5 --query '"facial recognition" OR biometric OR "data broker"'`
Expected: a `candidates.json` with real, relevance-ranked CA bills, fully enriched.
If it errors or returns nothing, inspect the LegiScan response and adjust the query
builder (operators only — not the architecture); re-run.

- [ ] **Step 2: Default-seed discovery**

Run: `uv run zwiadbrain fetch-state-candidates --state ca --limit 5`
Expected: the topics.yaml-seed query returns CA candidates.

- [ ] **Step 3: End-to-end backfill**

Run `/zwiad-scan-states --state ca --limit 5` interactively → classifier verdicts →
in-scope bills rendered under `wiki/states/ca/bills/`. Open a page (target CA SB 362,
the Delete Act) and confirm: correct id, `US-CA` jurisdiction, session, timeline,
sources, `legiscan_bill_id` in frontmatter.

- [ ] **Step 4: Refresh idempotency**

Run: `uv run zwiadbrain fetch-state-refreshable`
Expected: `[]` (no changes → clean no-op).

- [ ] **Step 5: Stale detection**

Edit one tracked page's `change_hash` to a stale value, re-run `fetch-state-refreshable`.
Expected: exactly that bill detected with the right triggers; `getBill` spent only on it.
Restore the page (`git checkout`).

- [ ] **Step 6: Unified refresh**

Run `/zwiad-refresh` and confirm it runs both the federal and state passes and reports a
combined count.

- [ ] **Step 7: Record + finish**

Append UAT results to `PHASE-07-done.md`. Then use the
`superpowers:finishing-a-development-branch` skill to push and open the PR.

---

## Self-review notes (author)

- **Spec coverage:** §4 id → T3; §5 transport/errors → T4; §6 mapping → T5; discovery
  (§8) → T6; refresh (§9) → T7/T9/T11; model field (§7) → T2; config (§11) → T8;
  commands (§10) → T12; decisions (§12) → T13; tests (§14) → T1–T11; UAT (§15) → T15.
  All spec sections map to a task.
- **Type consistency:** `LegiScanSource(api_key, state, *, query=…)`, `discover(limit=)`,
  `fetch(native_id)`, `change_hashes() -> dict[int, str]`, `detect_state_refreshable`,
  `build_state_bill_id`, `format_state_bill_number`, `LEGISCAN_API_BASE` are used
  identically across T4–T11 and the tests.
- **Known follow-up:** state leg-history / votes, getSearchRaw pagination, dataset API,
  session_id pinning — all deferred per spec §16 (not in this plan).
```