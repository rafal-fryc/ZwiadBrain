# PHASE-06 Watchlist Refresh — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a self-updating federal-bill tracker — `/zwiad-refresh` detects bills whose Congress.gov cursors have advanced, dispatches classifier/summarizer/amendment-explainer subagents on real change, preserves PHASE-05's expensive cross-modal-verified leg-history (hearings + statements + narrative), and flips out-of-scope bills to `tracking: false` without deletion. Also closes PHASE-05's two known gaps: populate `Enactment.statutes_at_large` from GovInfo, and lift grounding-gate recall on JS-rendered pages via BeautifulSoup text extraction.

**Architecture:** Three-step Python→subagent→Python pattern, mirroring `/zwiad-backfill` and `/zwiad-leg-history`. Step 1 `fetch-refreshable` reads every tracked bill's frontmatter, re-fetches via Congress.gov, compares cursors, and writes `refreshable.json`. Step 2 (slash command) dispatches subagents only where triggers fired. Step 3 `render-refreshed` applies the D38 preservation rule, the IN→OUT flip, re-renders, and reindexes. No new API keys; runs on the user's regular Claude plan.

**Tech Stack:** Python 3.12, pydantic v2, httpx + tenacity (already in use), BeautifulSoup4 (already a dep), typer, pytest + respx, ruff, pyright (strict). Subagents via `.claude/agents/*.md`; slash command via `.claude/commands/zwiad-refresh.md`.

**Pre-existing facts discovered while planning** (impact the tasks below):
- `Bill.update_date` already exists, mapped as `updateDateIncludingText OR updateDate`. T1 splits it cleanly into `update_date` (bare) and `update_date_text` (text-including).
- `beautifulsoup4>=4.12` is already a runtime dep (used in `congress.py._strip_html`). L2 does not add a new dep.
- `Bill.change_hash` exists but is unused in this phase (PHASE-07 LegiScan).
- `Enactment.statutes_at_large` is currently `str | None`. L1 upgrades it to a typed `StatutesAtLarge(citation, url)` so the rendered citation can be a link, matching the project's "every leg-history item links to its source" rule.
- The deterministic grounding gate already lowercase-normalizes whitespace + curly quotes but matches against RAW HTML. L2 inserts a BeautifulSoup text extraction step before normalization.

---

## File structure

**Created**

| Path | Responsibility |
|---|---|
| `src/zwiadbrain/pipeline/refresh.py` | Pure functions: `detect_refreshable`, `summary_hash`, `_amendment_delta`, `preserve_leg_history`, `apply_classifier_flip`; `RefreshableBill` dataclass. |
| `tests/test_refresh.py` | Unit tests for every function above, all offline. |
| `.claude/commands/zwiad-refresh.md` | Slash command orchestrating fetch-refreshable → subagents → render-refreshed. |

**Modified**

| Path | Why |
|---|---|
| `src/zwiadbrain/models.py` | `Amendment` gains `latest_action_date`; `Bill` gains `update_date_text`, `summary_hash`, `amendments_count`, `flipped_out: FlipOutAudit \| None`; new `FlipOutAudit` and `StatutesAtLarge` models; `Enactment.statutes_at_large` becomes `StatutesAtLarge \| None`. |
| `src/zwiadbrain/sources/congress.py` | Map bare `updateDate` → `update_date`; bare `updateDateIncludingText` → `update_date_text`; map per-amendment `latestAction.actionDate` → `Amendment.latest_action_date`. |
| `src/zwiadbrain/pipeline/enrich.py` | Compute and set `summary_hash` + `amendments_count` after `source.fetch`. |
| `src/zwiadbrain/wiki/schema.py` | `to_frontmatter` emits new cursor fields, `flipped_out`, and `leg_history.narrative`; `from_page` round-trips them (the union model already handles new fields via pydantic). |
| `src/zwiadbrain/wiki/templates.py` | Render `flipped_out` as an HTML comment prepended to the body; render `StatutesAtLarge` as a link in `_enactment_block`. |
| `src/zwiadbrain/pipeline/leg_history.py` | `ground_items` extracts page text via BeautifulSoup before quote-presence check (L2); `assemble_spine` reads `enacted_law` and the new `fetch_statutes_at_large` result (L1). |
| `src/zwiadbrain/sources/govinfo.py` | New `fetch_statutes_at_large(plaw_package_id) -> StatutesAtLarge \| None` (L1). `enacted_law` calls it and populates the field. |
| `src/zwiadbrain/cli.py` | Two new commands: `fetch-refreshable` and `render-refreshed`. |
| `src/zwiadbrain/__init__.py` | `__version__ = "0.6.0"`. |
| `pyproject.toml` | `version = "0.6.0"`. |
| `DECISIONS.md` | Append D39 (re-classify on refresh, narrowly overrides D9) and D40 (`leg_history.narrative` persists to frontmatter, extends D37). |
| `.claude/phases/PHASE-06-active.md` | Phase tracking file (per Core Rules §1). Renamed to `-done.md` at T12 close. |
| `tests/test_models.py`, `tests/test_schema.py`, `tests/test_congress.py`, `tests/test_govinfo.py`, `tests/test_leg_history.py`, `tests/test_render.py`, `tests/test_cli.py`, `tests/test_agents.py` | New test cases for each change above. |

---

## Task 0: Create the active phase file

**Files:**
- Create: `.claude/phases/PHASE-06-active.md`

- [ ] **Step 1: Write the phase tracking file**

```markdown
# Phase 06 — Watchlist refresh (Pass A) + PHASE-05 leftovers
Status: ACTIVE

> Full design: `docs/superpowers/specs/2026-05-28-phase06-watchlist-refresh-design.md`.
> Full plan: `docs/superpowers/plans/2026-05-28-phase06-watchlist-refresh.md`.
> Decisions to log this phase: D39 (re-classify on refresh, narrowly overrides D9) and D40 (`leg_history.narrative` persists to frontmatter, extends D37).
> TDD throughout (test first, watch it fail, implement, watch it pass, commit). Atomic commits per task.

## Goal
Ship `/zwiad-refresh`: a deterministic-Python + subagent slash command that re-fetches every tracked federal bill, dispatches classifier/summarizer/amendment-explainer only on real change, preserves PHASE-05 leg-history (hearings/statements/narrative) across the refresh, and flips out-of-scope bills to `tracking: false` without deletion. Also closes PHASE-05's `Enactment.statutes_at_large` and grounding-gate-recall gaps.

## Tasks
- [ ] T1 — models: cursor fields + FlipOutAudit + StatutesAtLarge
- [ ] T2 — congress source: map bare update dates + per-amendment date
- [ ] T3 — enrich: compute summary_hash + amendments_count
- [ ] T4 — schema: round-trip new fields + leg_history.narrative
- [ ] T5 — templates: flipped-out audit marker + Statutes-at-Large link
- [ ] T6 — pipeline/refresh.py: pure functions
- [ ] T7 — cli `fetch-refreshable`
- [ ] T8 — cli `render-refreshed`
- [ ] T9 — slash command `/zwiad-refresh`
- [ ] L1 — GovInfo Statutes-at-Large fetch + spine wire-through
- [ ] L2 — grounding gate BeautifulSoup text-extract
- [ ] T10 — DECISIONS.md D39 + D40
- [ ] T11 — quality gate + version bump 0.6.0 + tag
- [ ] T12 — interactive UAT (Pass A + L1 + L2)

## Acceptance Criteria
- [ ] `/zwiad-refresh` on the existing 118-hr-2670 page reports `unchanged` and leaves `git status` clean.
- [ ] On a deliberately-stale fixture or live bill, `/zwiad-refresh` refreshes only the changed bill; subagents dispatch only where triggers fired; `leg_history.hearings/statements/narrative` survive byte-for-byte.
- [ ] IN→OUT classifier verdict sets `tracking: false`, prepends the flipped-out audit marker, keeps `topics` intact, never deletes the page.
- [ ] `Enactment.statutes_at_large` populates for 118-hr-2670 and renders as a clickable link.
- [ ] A JS-rendered `.senate.gov` press-release fixture previously rejected by the gate is now accepted; a genuinely-absent quote is still rejected.
- [ ] ruff + pyright (strict) + pytest all green.
- [ ] DECISIONS.md carries D39 + D40.
- [ ] v0.6.0 tagged.

## Decisions Made This Phase
(append as the phase runs)
- D39 — `/zwiad-refresh` re-classifies on every text-changed bill, narrowly overriding D9 for routine refresh. Justification + trade-offs in the spec §11.
- D40 — `LegHistory.narrative` persists to frontmatter alongside hearings/statements, extending D37's partial-persistence carve-out. Justification + trade-offs in the spec §11.
```

- [ ] **Step 2: Commit**

```bash
git add .claude/phases/PHASE-06-active.md
git commit -m "chore(phase-06): open active phase file

PHASE-06 watchlist refresh (Pass A) + PHASE-05 leftovers (L1 + L2).
References spec and plan; tasks T1-T12 + L1-L2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task T1: Models — cursor fields, FlipOutAudit, StatutesAtLarge upgrade

**Files:**
- Modify: `src/zwiadbrain/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for the new model shape**

Append to `tests/test_models.py`:

```python
def test_amendment_carries_latest_action_date() -> None:
    """should accept and round-trip a latest_action_date field"""
    from zwiadbrain.models import Amendment
    import datetime as dt
    a = Amendment(number="H.Amdt. 1", latest_action_date=dt.date(2026, 5, 1))
    assert a.latest_action_date == dt.date(2026, 5, 1)
    # default is None
    assert Amendment(number="H.Amdt. 2").latest_action_date is None


def test_bill_carries_split_cursors_and_amendments_count() -> None:
    """should carry update_date (bare), update_date_text (text-incl), summary_hash, amendments_count"""
    from zwiadbrain.models import Bill
    b = Bill(
        id="118-hr-1",
        jurisdiction="US",
        title="x",
        bill_number="H.R. 1",
        update_date="2026-05-01T00:00:00Z",
        update_date_text="2026-05-02T00:00:00Z",
        summary_hash="deadbeef",
        amendments_count=3,
    )
    assert b.update_date == "2026-05-01T00:00:00Z"
    assert b.update_date_text == "2026-05-02T00:00:00Z"
    assert b.summary_hash == "deadbeef"
    assert b.amendments_count == 3
    # defaults are None / 0
    b2 = Bill(id="118-hr-2", jurisdiction="US", title="y", bill_number="H.R. 2")
    assert b2.update_date_text is None
    assert b2.summary_hash is None
    assert b2.amendments_count == 0


def test_flipout_audit_model() -> None:
    """should record a date and reason for a classifier flip-out"""
    from zwiadbrain.models import FlipOutAudit
    import datetime as dt
    f = FlipOutAudit(date=dt.date(2026, 6, 4), reason="classifier: telehealth scope drift")
    assert f.date == dt.date(2026, 6, 4)
    assert f.reason == "classifier: telehealth scope drift"


def test_bill_carries_flipped_out_audit() -> None:
    """should accept a FlipOutAudit on Bill.flipped_out (default None)"""
    from zwiadbrain.models import Bill, FlipOutAudit
    import datetime as dt
    b = Bill(
        id="118-hr-3",
        jurisdiction="US",
        title="z",
        bill_number="H.R. 3",
        flipped_out=FlipOutAudit(date=dt.date(2026, 6, 4), reason="r"),
    )
    assert b.flipped_out is not None
    assert b.flipped_out.reason == "r"
    assert Bill(id="118-hr-4", jurisdiction="US", title="q", bill_number="H.R. 4").flipped_out is None


def test_statutes_at_large_is_a_typed_model() -> None:
    """should be a model with citation + url, not a bare string"""
    from zwiadbrain.models import StatutesAtLarge
    s = StatutesAtLarge(citation="138 Stat. 1234", url="https://www.govinfo.gov/app/details/STATUTE-138-Pg1234")
    assert s.citation == "138 Stat. 1234"
    assert str(s.url).startswith("https://")


def test_enactment_statutes_at_large_uses_new_model() -> None:
    """Enactment.statutes_at_large should accept StatutesAtLarge | None"""
    from zwiadbrain.models import Enactment, StatutesAtLarge
    e = Enactment(
        statutes_at_large=StatutesAtLarge(citation="138 Stat. 1234", url="https://example.test"),
    )
    assert e.statutes_at_large is not None
    assert e.statutes_at_large.citation == "138 Stat. 1234"
    assert Enactment().statutes_at_large is None
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/test_models.py -k "amendment_carries_latest or split_cursors or flipout or statutes_at_large or enactment_statutes" -v`

Expected: **FAIL** — `Amendment` has no `latest_action_date`, `Bill` has no `update_date_text`/`summary_hash`/`amendments_count`/`flipped_out`, `FlipOutAudit`/`StatutesAtLarge` not defined, `Enactment.statutes_at_large` is a string.

- [ ] **Step 3: Implement the models**

Edit `src/zwiadbrain/models.py`:

a. **Add `latest_action_date` to `Amendment`** (insert before `what_changed`):

```python
class Amendment(BaseModel):
    """An amendment to a bill, with a plain-language explanation of its effect."""

    number: str
    sponsor: str | None = None
    chamber: str | None = None
    status: str | None = None
    latest_action_date: dt.date | None = None
    what_changed: str | None = None
```

b. **Insert new `StatutesAtLarge` and `FlipOutAudit` models** (place `StatutesAtLarge` right before `Enactment`; `FlipOutAudit` right before `WikiItem`):

```python
class StatutesAtLarge(BaseModel):
    """Statutes-at-Large citation for an enacted public law.

    Carries the canonical citation (e.g. ``"138 Stat. 1234"``) and a clickable
    GovInfo ``app/details`` URL.  ``url`` is required: the project's leg-history
    rule is "no link, no render" (matching ``Hearing``, ``CommitteeReport``, etc.).
    """

    citation: str
    url: str


class FlipOutAudit(BaseModel):
    """Audit record for a bill whose classifier verdict flipped IN→OUT during refresh.

    Persisted to frontmatter so a future ``reindex`` re-reads it; the renderer
    emits an ``<!-- zwiadbrain:flipped-out … -->`` comment in the body from it.
    Survives a fresh clone via committed wiki history.
    """

    date: dt.date
    reason: str
```

c. **Update `Enactment.statutes_at_large` to use the new model:**

```python
class Enactment(BaseModel):
    """Enactment details recorded when a bill becomes law."""

    date_signed: dt.date | None = None
    public_law: str | None = None
    statutes_at_large: StatutesAtLarge | None = None
    url: str | None = None
```

d. **Add cursor and flip fields to `Bill`** (place new fields after `update_date`):

```python
class Bill(WikiItem):
    """A tracked piece of legislation (federal or state)."""

    type: Literal["bill"] = "bill"
    bill_number: str
    chamber: str | None = None
    congress: str | None = None
    session: str | None = None
    status: str | None = None
    policy_area: str | None = None
    sponsors: list[str] = []
    introduced_date: dt.date | None = None
    latest_action_date: dt.date | None = None
    latest_action: str | None = None
    enacted: bool = False
    public_law: str | None = None
    actions: list[Action] = []
    amendments: list[Amendment] = []
    text_versions: list[TextVersion] = []
    leg_history: LegHistory | None = None
    related_bills: list[str] = []
    change_hash: str | None = None
    update_date: str | None = None
    update_date_text: str | None = None
    summary_hash: str | None = None
    amendments_count: int = 0
    flipped_out: FlipOutAudit | None = None
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `uv run pytest tests/test_models.py -v`

Expected: **PASS** — all new tests green; pre-existing tests still green.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/models.py tests/test_models.py
git commit -m "feat(models): add refresh cursors, flip audit, StatutesAtLarge

- Amendment.latest_action_date (per-amendment cursor for explainer trigger)
- Bill.update_date_text (bare updateDateIncludingText, splits old update_date)
- Bill.summary_hash, Bill.amendments_count (refresh-detection cursors)
- Bill.flipped_out: FlipOutAudit | None (IN→OUT classifier audit)
- Enactment.statutes_at_large becomes StatutesAtLarge | None (was str | None)
- New FlipOutAudit and StatutesAtLarge models

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task T2: Congress source — split cursors, map per-amendment date

**Files:**
- Modify: `src/zwiadbrain/sources/congress.py`
- Test: `tests/test_congress.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_congress.py`:

```python
def test_fetch_maps_bare_update_date_and_update_date_text_separately() -> None:
    """should set update_date from bare updateDate, update_date_text from bare updateDateIncludingText"""
    import respx
    from zwiadbrain.sources.congress import CONGRESS_API_BASE, CongressSource

    detail_payload = {
        "bill": {
            "congress": 118,
            "type": "HR",
            "number": 2670,
            "title": "Test bill",
            "updateDate": "2026-05-01T00:00:00Z",
            "updateDateIncludingText": "2026-05-02T00:00:00Z",
        }
    }
    empty_list_payloads = {
        "actions": {"actions": []},
        "amendments": {"amendments": []},
        "text": {"textVersions": []},
        "summaries": {"summaries": []},
        "relatedbills": {"relatedBills": []},
    }
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        mock.get("/bill/118/hr/2670").respond(json=detail_payload)
        for sub, body in empty_list_payloads.items():
            mock.get(f"/bill/118/hr/2670/{sub}").respond(json=body)
        bill = CongressSource(api_key="k").fetch("118/hr/2670")
    assert bill.update_date == "2026-05-01T00:00:00Z"
    assert bill.update_date_text == "2026-05-02T00:00:00Z"


def test_fetch_maps_per_amendment_latest_action_date() -> None:
    """should map each amendment's latestAction.actionDate to Amendment.latest_action_date"""
    import datetime as dt
    import respx
    from zwiadbrain.sources.congress import CONGRESS_API_BASE, CongressSource

    detail_payload = {
        "bill": {"congress": 118, "type": "HR", "number": 2670, "title": "x"}
    }
    amendments_payload = {
        "amendments": [
            {
                "type": "HAMDT",
                "number": "5",
                "purpose": "Adds AI clause",
                "latestAction": {"text": "Agreed to", "actionDate": "2026-04-15"},
            },
            {
                "type": "HAMDT",
                "number": "7",
                "purpose": "Strikes section 3",
                "latestAction": {"text": "Failed", "actionDate": "2026-04-20"},
            },
        ]
    }
    empty = {"actions": [], "textVersions": [], "summaries": [], "relatedBills": []}
    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        mock.get("/bill/118/hr/2670").respond(json=detail_payload)
        mock.get("/bill/118/hr/2670/actions").respond(json={"actions": empty["actions"]})
        mock.get("/bill/118/hr/2670/amendments").respond(json=amendments_payload)
        mock.get("/bill/118/hr/2670/text").respond(json={"textVersions": empty["textVersions"]})
        mock.get("/bill/118/hr/2670/summaries").respond(json={"summaries": empty["summaries"]})
        mock.get("/bill/118/hr/2670/relatedbills").respond(json={"relatedBills": empty["relatedBills"]})
        bill = CongressSource(api_key="k").fetch("118/hr/2670")
    assert len(bill.amendments) == 2
    assert bill.amendments[0].latest_action_date == dt.date(2026, 4, 15)
    assert bill.amendments[1].latest_action_date == dt.date(2026, 4, 20)
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/test_congress.py -k "split or per_amendment" -v`

Expected: **FAIL** — current code stores `updateDateIncludingText OR updateDate` in `update_date` (a single field); `Amendment.latest_action_date` is not mapped.

- [ ] **Step 3: Implement the changes**

Edit `src/zwiadbrain/sources/congress.py`:

a. **Update `_to_amendment` to map the date:**

```python
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
```

b. **Update `_to_bill` to split the cursors** (find the existing `update_date=...` line and replace with the two-field mapping):

```python
            update_date=_opt_str(detail.get("updateDate")),
            update_date_text=_opt_str(detail.get("updateDateIncludingText")),
```

c. **Update the module docstring's cursor sentence** (the old "stored on the bill as ``update_date``" line is now wrong):

```python
"""…

The Congress.gov change cursor is split across two fields on the bill:
``update_date`` (bare ``updateDate`` — bumps on any change) and
``update_date_text`` (``updateDateIncludingText`` — bumps when text/summary
changes).  Pass A compares both to decide what to refresh.
"""
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `uv run pytest tests/test_congress.py -v`

Expected: **PASS** — new tests green; verify the pre-existing congress tests still pass too (the existing fixture data may use one or the other date — adjust pre-existing test assertions only if a date assertion regresses, and only on `update_date` semantics).

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/sources/congress.py tests/test_congress.py
git commit -m "feat(congress): split update_date cursors; map amendment date

- update_date is now bare updateDate (bumps on any change)
- update_date_text is bare updateDateIncludingText (text/summary change)
- Amendment.latest_action_date mapped from latestAction.actionDate

PHASE-06 trigger logic needs both cursors separately.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task T3: Enrich — compute summary_hash and amendments_count

**Files:**
- Modify: `src/zwiadbrain/pipeline/enrich.py`
- Test: `tests/test_enrich.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_enrich.py`:

```python
def test_enrich_sets_summary_hash_when_summary_present() -> None:
    """should set summary_hash to sha256 of whitespace-normalized summary"""
    import hashlib
    from zwiadbrain.models import Bill
    from zwiadbrain.pipeline.enrich import enrich
    from zwiadbrain.sources.base import Candidate

    summary_text = "  This  bill\n establishes\tan AI advisory board.  "
    normalized = " ".join(summary_text.split())
    expected = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    class _StubSource:
        name = "stub"
        def fetch(self, native_id: str) -> Bill:
            return Bill(
                id="118-hr-99", jurisdiction="US", title="x",
                bill_number="H.R. 99", summary=summary_text, amendments=[],
            )
    bill = enrich(_StubSource(), Candidate(source="stub", native_id="118/hr/99",
                  jurisdiction="US", title="x", update_date=None, raw={}))
    assert bill.summary_hash == expected


def test_enrich_leaves_summary_hash_none_when_no_summary() -> None:
    """should leave summary_hash as None when bill has no summary"""
    from zwiadbrain.models import Bill
    from zwiadbrain.pipeline.enrich import enrich
    from zwiadbrain.sources.base import Candidate

    class _StubSource:
        name = "stub"
        def fetch(self, native_id: str) -> Bill:
            return Bill(id="118-hr-1", jurisdiction="US", title="x",
                        bill_number="H.R. 1", summary=None)
    bill = enrich(_StubSource(), Candidate(source="stub", native_id="118/hr/1",
                  jurisdiction="US", title="x", update_date=None, raw={}))
    assert bill.summary_hash is None


def test_enrich_sets_amendments_count_from_amendments_list() -> None:
    """should set amendments_count = len(bill.amendments) after fetch"""
    from zwiadbrain.models import Amendment, Bill
    from zwiadbrain.pipeline.enrich import enrich
    from zwiadbrain.sources.base import Candidate

    class _StubSource:
        name = "stub"
        def fetch(self, native_id: str) -> Bill:
            return Bill(
                id="118-hr-2", jurisdiction="US", title="x", bill_number="H.R. 2",
                amendments=[Amendment(number="H.Amdt. 1"), Amendment(number="H.Amdt. 2")],
            )
    bill = enrich(_StubSource(), Candidate(source="stub", native_id="118/hr/2",
                  jurisdiction="US", title="x", update_date=None, raw={}))
    assert bill.amendments_count == 2
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/test_enrich.py -k "summary_hash or amendments_count" -v`

Expected: **FAIL** — `enrich` does not compute `summary_hash` or `amendments_count`.

- [ ] **Step 3: Implement**

Replace `src/zwiadbrain/pipeline/enrich.py` body with:

```python
"""Enrichment: turn a discovered candidate into a fully-populated ``Bill``.

The per-field mapping from a source's API onto :class:`~zwiadbrain.models.Bill`
lives in each source (so the pipeline stays source-agnostic). This module is the
source-agnostic seam that owns the cross-source post-processing: stamping
``last_synced``, deriving ``summary_hash`` from the CRS summary text, and
caching the amendments count so PHASE-06's refresh can detect amendment growth
without re-comparing the full list.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from zwiadbrain.models import Bill
from zwiadbrain.sources.base import Candidate, Source


def _summary_hash(summary: str | None) -> str | None:
    """sha256 hex of whitespace-collapsed summary, or ``None`` when no summary.

    Whitespace normalization mirrors the deterministic-render contract used
    elsewhere in the codebase so a Congress-side reformatting that only changes
    whitespace does not spuriously dirty the cursor.
    """
    if not summary:
        return None
    normalized = " ".join(summary.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def enrich(source: Source, candidate: Candidate) -> Bill:
    """Fetch the full bill for ``candidate`` and stamp the cross-source cursors."""
    bill = source.fetch(candidate.native_id)
    if bill.last_synced is None:
        bill.last_synced = dt.datetime.now(dt.UTC)
    bill.summary_hash = _summary_hash(bill.summary)
    bill.amendments_count = len(bill.amendments)
    return bill
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `uv run pytest tests/test_enrich.py -v`

Expected: **PASS** — all new tests; pre-existing tests still green.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/pipeline/enrich.py tests/test_enrich.py
git commit -m "feat(enrich): compute summary_hash and amendments_count

Cursor stamping for PHASE-06 refresh detection — summary_hash is sha256
of whitespace-normalized CRS summary text; amendments_count caches
len(amendments) so the per-amendment delta is computed only on growth.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task T4: Schema — round-trip new fields and leg_history.narrative

**Files:**
- Modify: `src/zwiadbrain/wiki/schema.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_schema.py`:

```python
def test_to_frontmatter_emits_new_cursor_fields_on_bill() -> None:
    """should emit update_date_text, summary_hash, amendments_count when set"""
    from zwiadbrain.models import Bill
    from zwiadbrain.wiki.schema import to_frontmatter
    b = Bill(
        id="118-hr-1", jurisdiction="US", title="x", bill_number="H.R. 1",
        update_date="2026-05-01T00:00:00Z",
        update_date_text="2026-05-02T00:00:00Z",
        summary_hash="dead",
        amendments_count=3,
    )
    fm = to_frontmatter(b)
    assert fm["update_date_text"] == "2026-05-02T00:00:00Z"
    assert fm["summary_hash"] == "dead"
    assert fm["amendments_count"] == 3


def test_to_frontmatter_drops_amendments_count_zero() -> None:
    """should not emit amendments_count when it's the default 0"""
    from zwiadbrain.models import Bill
    from zwiadbrain.wiki.schema import to_frontmatter
    b = Bill(id="118-hr-1", jurisdiction="US", title="x", bill_number="H.R. 1")
    assert "amendments_count" not in to_frontmatter(b)


def test_to_frontmatter_emits_flipped_out_audit() -> None:
    """should serialize flipped_out as a dict in frontmatter"""
    import datetime as dt
    from zwiadbrain.models import Bill, FlipOutAudit
    from zwiadbrain.wiki.schema import to_frontmatter
    b = Bill(
        id="118-hr-1", jurisdiction="US", title="x", bill_number="H.R. 1",
        flipped_out=FlipOutAudit(date=dt.date(2026, 6, 4), reason="r"),
    )
    fm = to_frontmatter(b)
    assert fm["flipped_out"] == {"date": "2026-06-04", "reason": "r"}


def test_to_frontmatter_persists_leg_history_narrative() -> None:
    """should include leg_history.narrative in frontmatter (extends D37)"""
    from zwiadbrain.models import Bill, LegHistory
    from zwiadbrain.wiki.schema import to_frontmatter
    b = Bill(
        id="118-hr-1", jurisdiction="US", title="x", bill_number="H.R. 1",
        leg_history=LegHistory(narrative="A long arc of NDAA debates..."),
    )
    fm = to_frontmatter(b)
    assert "leg_history" in fm
    lh = fm["leg_history"]
    assert isinstance(lh, dict)
    assert lh["narrative"] == "A long arc of NDAA debates..."


def test_from_page_round_trips_narrative_and_cursors() -> None:
    """should reconstruct narrative + new cursor fields from frontmatter"""
    from zwiadbrain.models import Bill, FlipOutAudit, Hearing, LegHistory
    from zwiadbrain.pipeline.render import render_page
    from zwiadbrain.wiki.schema import from_page
    import datetime as dt
    original = Bill(
        id="118-hr-1", jurisdiction="US", title="x", bill_number="H.R. 1",
        update_date="2026-05-01T00:00:00Z",
        update_date_text="2026-05-02T00:00:00Z",
        summary_hash="dead",
        amendments_count=2,
        flipped_out=FlipOutAudit(date=dt.date(2026, 6, 4), reason="r"),
        leg_history=LegHistory(
            narrative="The arc of the debate.",
            hearings=[Hearing(title="H1", url="https://example.test/h1")],
        ),
    )
    text = render_page(original)
    reparsed = from_page(text)
    assert isinstance(reparsed, Bill)
    assert reparsed.update_date_text == "2026-05-02T00:00:00Z"
    assert reparsed.summary_hash == "dead"
    assert reparsed.amendments_count == 2
    assert reparsed.flipped_out is not None
    assert reparsed.flipped_out.reason == "r"
    assert reparsed.leg_history is not None
    assert reparsed.leg_history.narrative == "The arc of the debate."
    assert len(reparsed.leg_history.hearings) == 1
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/test_schema.py -k "cursor or flipped_out or narrative" -v`

Expected: **FAIL** — `to_frontmatter` does not persist `narrative` (D37 dropped it); doesn't emit `flipped_out`; `amendments_count` may be emitted as 0 instead of dropped.

- [ ] **Step 3: Implement schema changes**

Edit `src/zwiadbrain/wiki/schema.py`:

a. **Extend the leg-history persistence block** to include `narrative`:

```python
    # Persist the researched leg_history sub-fields plus the narrative (D40).
    # The deterministic spine (versions, committee_reports, floor_consideration,
    # votes, conference, enactment) remains body-only / re-derived per D37.
    if isinstance(item, Bill) and item.leg_history is not None:
        lh_fm: dict[str, object] = {}
        if item.leg_history.hearings:
            lh_fm["hearings"] = [
                h.model_dump(mode="json", exclude_none=True)
                for h in item.leg_history.hearings
            ]
        if item.leg_history.statements:
            lh_fm["statements"] = [
                s.model_dump(mode="json", exclude_none=True)
                for s in item.leg_history.statements
            ]
        if item.leg_history.narrative:
            lh_fm["narrative"] = item.leg_history.narrative
        if lh_fm:
            fm["leg_history"] = lh_fm
    return fm
```

b. **Update the module docstring** (the existing "narrative remain body-only" line is now wrong):

Replace the leg_history paragraph in the docstring with:

```
**leg_history partial persistence:** ``leg_history.hearings``,
``leg_history.statements``, and ``leg_history.narrative`` are expensive,
non-deterministic outputs and persist to frontmatter (D40 extends D37 to add
narrative).  The deterministic spine fields (``versions``,
``committee_reports``, ``floor_consideration``, ``votes``, ``conference``,
``enactment``) remain body-only and are re-derived from the API on each
render.
```

c. **Verify `amendments_count=0` is dropped:** the existing `value in ([], {})` filter does NOT drop `0`. Update it to also drop the integer default for `amendments_count` only — but a general-purpose `if value == 0` would wrongly drop legitimate zero fields elsewhere. The narrow fix: add `amendments_count` to the explicit drop check.

Find the existing loop:

```python
    for key, value in raw.items():
        if key == "commentary_sources" or key in _BODY_ONLY_FIELDS or value in ([], {}):
            continue
        fm[key] = value
```

Replace with:

```python
    for key, value in raw.items():
        if key == "commentary_sources" or key in _BODY_ONLY_FIELDS or value in ([], {}):
            continue
        if key == "amendments_count" and value == 0:
            continue
        fm[key] = value
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `uv run pytest tests/test_schema.py -v`

Expected: **PASS** — all new tests green; pre-existing schema tests still green.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/wiki/schema.py tests/test_schema.py
git commit -m "feat(schema): persist narrative, flipped_out, refresh cursors

- leg_history.narrative now round-trips through frontmatter (D40 extends D37)
- Bill.flipped_out audit serializes to frontmatter for re-render survival
- Bill.update_date_text and summary_hash emit/parse normally
- Bill.amendments_count is dropped from frontmatter when it equals the default 0

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task T5: Templates — flipped-out audit marker + Statutes-at-Large link

**Files:**
- Modify: `src/zwiadbrain/wiki/templates.py`
- Test: `tests/test_render.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_render.py`:

```python
def test_render_emits_flipped_out_marker_when_set() -> None:
    """should prepend an HTML comment marker to the body when bill.flipped_out is set"""
    import datetime as dt
    from zwiadbrain.models import Bill, FlipOutAudit
    from zwiadbrain.wiki.templates import render_bill_body
    bill = Bill(
        id="118-hr-1", jurisdiction="US", title="x", bill_number="H.R. 1",
        summary="A short summary.",
        flipped_out=FlipOutAudit(date=dt.date(2026, 6, 4), reason="classifier: drift"),
    )
    body = render_bill_body(bill)
    first_line = body.split("\n", 1)[0]
    assert first_line.startswith("<!-- zwiadbrain:flipped-out ")
    assert 'date="2026-06-04"' in first_line
    assert 'reason="classifier: drift"' in first_line


def test_render_omits_marker_when_not_flipped() -> None:
    """should not emit the marker for a normally-tracked bill"""
    from zwiadbrain.models import Bill
    from zwiadbrain.wiki.templates import render_bill_body
    bill = Bill(id="118-hr-1", jurisdiction="US", title="x", bill_number="H.R. 1",
                summary="A short summary.")
    body = render_bill_body(bill)
    assert "<!-- zwiadbrain:flipped-out" not in body


def test_render_escapes_quote_in_flip_reason() -> None:
    """should escape a double-quote inside the reason so the HTML comment stays valid"""
    import datetime as dt
    from zwiadbrain.models import Bill, FlipOutAudit
    from zwiadbrain.wiki.templates import render_bill_body
    bill = Bill(
        id="118-hr-1", jurisdiction="US", title="x", bill_number="H.R. 1",
        flipped_out=FlipOutAudit(date=dt.date(2026, 6, 4), reason='he said "AI" out of scope'),
    )
    body = render_bill_body(bill)
    first_line = body.split("\n", 1)[0]
    # backslash-escape inside double-quoted attribute
    assert 'reason="he said \\"AI\\" out of scope"' in first_line


def test_render_emits_statutes_at_large_link() -> None:
    """should render the StatutesAtLarge as a markdown link in the Enactment block"""
    from zwiadbrain.models import Bill, Enactment, LegHistory, StatutesAtLarge
    from zwiadbrain.wiki.templates import render_bill_body
    bill = Bill(
        id="118-hr-1", jurisdiction="US", title="x", bill_number="H.R. 1",
        leg_history=LegHistory(
            enactment=Enactment(
                public_law="118-31",
                url="https://www.govinfo.gov/app/details/PLAW-118publ31",
                statutes_at_large=StatutesAtLarge(
                    citation="138 Stat. 1234",
                    url="https://www.govinfo.gov/app/details/STATUTE-138-Pg1234",
                ),
            ),
        ),
    )
    body = render_bill_body(bill)
    assert (
        "Statutes at Large: [138 Stat. 1234]"
        "(https://www.govinfo.gov/app/details/STATUTE-138-Pg1234)"
    ) in body
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/test_render.py -k "flipped_out or statutes_at_large" -v`

Expected: **FAIL** — `render_bill_body` doesn't know about `flipped_out`; `_enactment_block` renders the now-removed string `statutes_at_large`.

- [ ] **Step 3: Implement template changes**

Edit `src/zwiadbrain/wiki/templates.py`:

a. **Update `_enactment_block` to render the structured citation as a link:**

```python
def _enactment_block(enactment: Enactment) -> str:
    """Render the enactment bullet list, linking the public law when url is present."""
    rows: list[str] = []
    if enactment.date_signed:
        rows.append(f"Signed: {enactment.date_signed.isoformat()}")
    if enactment.url:
        if enactment.public_law:
            rows.append(f"Public Law: [{enactment.public_law}]({enactment.url})")
        else:
            rows.append(f"[Public law document]({enactment.url})")
    elif enactment.public_law:
        rows.append(f"Public Law: {enactment.public_law}")
    if enactment.statutes_at_large:
        s = enactment.statutes_at_large
        rows.append(f"Statutes at Large: [{s.citation}]({s.url})")
    return "\n".join(f"- {row}" for row in rows)
```

b. **Add the flipped-out marker to `render_bill_body`** — prepend it before the section render. Update the function:

```python
def render_bill_body(bill: Bill) -> str:
    """Render the Markdown body for a bill page (no frontmatter).

    When ``bill.flipped_out`` is set, an HTML comment marker is prepended to the
    body for audit visibility in ``git log -p``.  The comment's ``reason``
    attribute is rendered inside double quotes; any literal double-quote in the
    reason is backslash-escaped so the attribute stays well-formed.
    """
    sections: list[dict[str, str]] = []
    if bill.summary:
        sections.append({"heading": "Summary", "body": bill.summary.strip()})
    if bill.actions:
        sections.append({"heading": "Status & Timeline", "body": _timeline(bill.actions)})
    if bill.amendments:
        sections.append({"heading": "Amendments", "body": _amendments(bill.amendments)})
    if bill.leg_history:
        sections.append({"heading": "Legislative History", "body": _leg_history(bill.leg_history)})
    if bill.text_versions:
        sections.append({"heading": "Full Text", "body": _text_versions(bill.text_versions)})
    if bill.related_bills:
        sections.append({"heading": "Related Bills", "body": _bullets(bill.related_bills)})
    if bill.commentary_sources:
        sections.append(
            {"heading": "Commentary & Analysis", "body": _commentary(bill.commentary_sources)}
        )
    if bill.sources:
        sections.append({"heading": "Sources", "body": _sources(bill.sources)})
    body = _BODY.render(sections=sections)
    if bill.flipped_out:
        reason = bill.flipped_out.reason.replace('"', '\\"')
        marker = (
            f'<!-- zwiadbrain:flipped-out date="{bill.flipped_out.date.isoformat()}"'
            f' reason="{reason}" -->\n\n'
        )
        body = marker + body
    return body
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `uv run pytest tests/test_render.py -v`

Expected: **PASS** — new tests green; pre-existing render tests still green.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/wiki/templates.py tests/test_render.py
git commit -m "feat(templates): flip-out audit marker + Statutes-at-Large link

- render_bill_body prepends <!-- zwiadbrain:flipped-out date=… reason=… -->
  when bill.flipped_out is set (escapes double-quotes in reason)
- _enactment_block renders Statutes-at-Large as a Markdown link
  ([citation](url)) now that StatutesAtLarge is a structured model

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task T6: pipeline/refresh.py — pure functions

**Files:**
- Create: `src/zwiadbrain/pipeline/refresh.py`
- Create: `tests/test_refresh.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_refresh.py`:

```python
"""Tests for the pure refresh-detection functions in pipeline/refresh.py."""

from __future__ import annotations

import datetime as dt
import hashlib

import pytest

from zwiadbrain.models import (
    Amendment,
    Bill,
    FlipOutAudit,
    Hearing,
    LegHistory,
    Statement,
)
from zwiadbrain.pipeline.refresh import (
    RefreshableBill,
    apply_classifier_flip,
    detect_refreshable,
    preserve_leg_history,
    summary_hash,
)


def _bill(**overrides: object) -> Bill:
    """Construct a minimal Bill for tests, accepting field overrides."""
    base: dict[str, object] = dict(
        id="118-hr-1", jurisdiction="US", title="x", bill_number="H.R. 1",
        update_date="2026-05-01T00:00:00Z",
        update_date_text="2026-05-02T00:00:00Z",
        summary_hash="hash-prev",
        amendments_count=0,
        amendments=[],
    )
    base.update(overrides)
    return Bill(**base)  # type: ignore[arg-type]


# --- summary_hash -----------------------------------------------------------


def test_summary_hash_normalizes_whitespace() -> None:
    """should produce identical hashes for strings that differ only in whitespace"""
    a = summary_hash("This  bill\n establishes\tan AI board.")
    b = summary_hash("This bill establishes an AI board.")
    assert a == b


def test_summary_hash_differs_on_single_char_change() -> None:
    """should change when any non-whitespace character changes"""
    a = summary_hash("This bill establishes an AI board.")
    b = summary_hash("This bill establishes an AI panel.")
    assert a != b


def test_summary_hash_returns_none_for_empty() -> None:
    """should return None for None and empty/whitespace-only inputs"""
    assert summary_hash(None) is None
    assert summary_hash("") is None
    assert summary_hash("   \n\t  ") is None


def test_summary_hash_matches_expected_sha256() -> None:
    """should be a hex sha256 of the whitespace-collapsed normalized text"""
    text = "  A B C  "
    expected = hashlib.sha256(b"A B C").hexdigest()
    assert summary_hash(text) == expected


# --- detect_refreshable -----------------------------------------------------


def test_detect_refreshable_returns_none_when_update_date_unchanged() -> None:
    """should return None when prev and fresh have the same update_date"""
    prev = _bill()
    fresh = _bill()
    assert detect_refreshable(prev, fresh) is None


def test_detect_refreshable_flags_text_change_for_classifier_and_summarizer() -> None:
    """should set needs_classifier and needs_summarizer when text-date OR summary_hash differs"""
    prev = _bill()
    fresh = _bill(
        update_date="2026-05-03T00:00:00Z",
        update_date_text="2026-05-03T00:00:00Z",
        summary_hash="hash-new",
    )
    result = detect_refreshable(prev, fresh)
    assert result is not None
    assert result.needs_classifier is True
    assert result.needs_summarizer is True
    assert result.changed_amendment_numbers == ()


def test_detect_refreshable_skips_classifier_when_only_status_changed() -> None:
    """should leave needs_classifier=False when only update_date moved (not text/hash)"""
    prev = _bill()
    fresh = _bill(update_date="2026-05-03T00:00:00Z")
    result = detect_refreshable(prev, fresh)
    assert result is not None
    assert result.needs_classifier is False
    assert result.needs_summarizer is False


def test_detect_refreshable_flags_new_and_advanced_amendments() -> None:
    """should return numbers for new amendments and amendments whose date advanced"""
    prev = _bill(
        amendments=[
            Amendment(number="H.Amdt. 1", latest_action_date=dt.date(2026, 4, 1)),
            Amendment(number="H.Amdt. 2", latest_action_date=dt.date(2026, 4, 5)),
        ],
        amendments_count=2,
    )
    fresh = _bill(
        update_date="2026-05-03T00:00:00Z",
        amendments=[
            Amendment(number="H.Amdt. 1", latest_action_date=dt.date(2026, 4, 1)),  # unchanged
            Amendment(number="H.Amdt. 2", latest_action_date=dt.date(2026, 5, 1)),  # advanced
            Amendment(number="H.Amdt. 3", latest_action_date=dt.date(2026, 5, 2)),  # new
        ],
        amendments_count=3,
    )
    result = detect_refreshable(prev, fresh)
    assert result is not None
    assert set(result.changed_amendment_numbers) == {"H.Amdt. 2", "H.Amdt. 3"}
    assert result.needs_explainer is True


def test_refreshable_bill_carries_prev_and_fresh() -> None:
    """RefreshableBill should expose both bills"""
    prev = _bill()
    fresh = _bill(update_date="2026-05-03T00:00:00Z")
    result = detect_refreshable(prev, fresh)
    assert result is not None
    assert isinstance(result, RefreshableBill)
    assert result.prev.update_date == "2026-05-01T00:00:00Z"
    assert result.fresh.update_date == "2026-05-03T00:00:00Z"


# --- preserve_leg_history ---------------------------------------------------


def test_preserve_leg_history_returns_spine_unchanged_when_prev_is_none() -> None:
    """should return the fresh spine as-is when prev leg_history is None"""
    fresh_spine = LegHistory(narrative=None, hearings=[], statements=[])
    out = preserve_leg_history(None, fresh_spine)
    assert out is fresh_spine or out == fresh_spine


def test_preserve_leg_history_reattaches_hearings_statements_narrative() -> None:
    """should copy hearings/statements/narrative from prev onto fresh spine"""
    from zwiadbrain.models import CommitteeReport, TextVersion
    prev = LegHistory(
        hearings=[Hearing(title="H1", url="https://example.test/h1")],
        statements=[Statement(
            speaker="Sen. Reed", role="member", quote="x" * 30,
            source_url="https://example.test/s", source_type="CREC",
        )],
        narrative="The old narrative.",
    )
    fresh = LegHistory(
        versions=[TextVersion(code="enr", date=dt.date(2026, 5, 1))],
        committee_reports=[CommitteeReport(citation="H. Rept. 1", url="https://example.test/c")],
    )
    out = preserve_leg_history(prev, fresh)
    # research carried from prev
    assert out.hearings == prev.hearings
    assert out.statements == prev.statements
    assert out.narrative == "The old narrative."
    # spine taken from fresh (not prev)
    assert out.versions == fresh.versions
    assert out.committee_reports == fresh.committee_reports


# --- apply_classifier_flip --------------------------------------------------


def test_apply_classifier_flip_in_scope_returns_bill_unchanged() -> None:
    """should be a no-op when classifier verdict is in_scope"""
    bill = _bill()
    out = apply_classifier_flip(bill, in_scope=True, rationale="ok", date=dt.date(2026, 6, 4))
    assert out is bill or out == bill
    assert out.tracking is True
    assert out.flipped_out is None


def test_apply_classifier_flip_out_of_scope_sets_tracking_false_and_audit() -> None:
    """should set tracking=False and populate flipped_out with date+reason"""
    bill = _bill()
    out = apply_classifier_flip(
        bill, in_scope=False, rationale="telehealth scope drift", date=dt.date(2026, 6, 4),
    )
    assert out.tracking is False
    assert out.flipped_out == FlipOutAudit(date=dt.date(2026, 6, 4), reason="telehealth scope drift")


def test_apply_classifier_flip_raises_on_already_untracked() -> None:
    """should raise ValueError when the bill is already tracking=False"""
    bill = _bill(tracking=False)
    with pytest.raises(ValueError, match="already-untracked"):
        apply_classifier_flip(bill, in_scope=False, rationale="x", date=dt.date(2026, 6, 4))
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/test_refresh.py -v`

Expected: **FAIL** — module does not exist.

- [ ] **Step 3: Implement `pipeline/refresh.py`**

Create `src/zwiadbrain/pipeline/refresh.py`:

```python
"""Pure functions and the dataclass that drive the PHASE-06 watchlist refresh.

Nothing here does I/O.  The CLI commands (``fetch-refreshable``,
``render-refreshed``) compose these helpers with the source clients and the
renderer.

The trust boundary this module enforces:

* :func:`detect_refreshable` decides whether a bill is refreshable at all and,
  if so, which subagents the slash command needs to dispatch.  A bill whose
  Congress.gov ``updateDate`` is unchanged is NEVER refreshable, even if the
  other cursors look different (this is the cheap "any change" gate).

* :func:`preserve_leg_history` carries PHASE-05's expensive cross-modal-verified
  hearings + statements + narrative across a spine re-derive, per D38 + D40.

* :func:`apply_classifier_flip` is the only place that flips
  ``Bill.tracking`` to ``False`` and records the audit.  It refuses to operate
  on an already-untracked bill so the slash command can't double-flip.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field

from zwiadbrain.models import Amendment, Bill, FlipOutAudit, LegHistory


def summary_hash(summary: str | None) -> str | None:
    """sha256 hex of whitespace-collapsed *summary*, or ``None`` when no summary.

    Whitespace normalization matches :mod:`zwiadbrain.pipeline.enrich` so the
    two places that compute the cursor agree byte-for-byte on input.
    """
    if not summary or not summary.strip():
        return None
    normalized = " ".join(summary.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RefreshableBill:
    """A bill detected as refreshable, with the slash-command triggers computed.

    *changed_amendment_numbers* lists amendments whose ``number`` is new in
    *fresh* OR whose ``latest_action_date`` advanced since *prev*.  An unchanged
    amendment (same number + same date) is NOT included — the explainer is
    dispatched only on real change, not on every amendment for the whole bill.
    """

    prev: Bill
    fresh: Bill
    needs_classifier: bool
    needs_summarizer: bool
    changed_amendment_numbers: tuple[str, ...] = field(default_factory=tuple)

    @property
    def needs_explainer(self) -> bool:
        """True when there is at least one new or date-advanced amendment."""
        return bool(self.changed_amendment_numbers)


def _amendment_delta(prev: list[Amendment], fresh: list[Amendment]) -> tuple[str, ...]:
    """Return the amendment numbers that need re-explaining.

    An amendment is in the delta when its number is not in *prev*, OR when its
    ``latest_action_date`` differs from the prev entry's date (including a None
    → date transition).  Order matches *fresh*'s order, deduped.
    """
    prev_by_number: dict[str, Amendment] = {a.number: a for a in prev}
    out: list[str] = []
    seen: set[str] = set()
    for a in fresh:
        if a.number in seen:
            continue
        old = prev_by_number.get(a.number)
        if old is None or old.latest_action_date != a.latest_action_date:
            out.append(a.number)
            seen.add(a.number)
    return tuple(out)


def detect_refreshable(prev: Bill, fresh: Bill) -> RefreshableBill | None:
    """Return a :class:`RefreshableBill` when *fresh* differs from *prev*, else ``None``.

    Trigger logic (matches the PHASE-06 spec §3 matrix):

    * If ``prev.update_date == fresh.update_date`` → ``None`` (any-change gate
      failed; the cheap path).
    * Otherwise the bill is refreshable.  ``needs_classifier`` and
      ``needs_summarizer`` are True when EITHER ``update_date_text`` advanced
      OR ``summary_hash`` differs.  ``changed_amendment_numbers`` is the result
      of :func:`_amendment_delta`.

    A previously-untracked bill (``prev.tracking is False``) is treated as not
    refreshable — the caller must not have included it in
    ``refreshable.json``.  Defensive: we return ``None`` rather than raise so a
    rogue input cannot abort a bulk refresh.
    """
    if not prev.tracking:
        return None
    if prev.update_date == fresh.update_date:
        return None
    text_changed = (
        prev.update_date_text != fresh.update_date_text
        or prev.summary_hash != fresh.summary_hash
    )
    changed = _amendment_delta(prev.amendments, fresh.amendments)
    return RefreshableBill(
        prev=prev,
        fresh=fresh,
        needs_classifier=text_changed,
        needs_summarizer=text_changed,
        changed_amendment_numbers=changed,
    )


def preserve_leg_history(prev: LegHistory | None, fresh_spine: LegHistory) -> LegHistory:
    """Re-attach *prev*'s hearings/statements/narrative onto a freshly assembled spine.

    Implements the D38 + D40 preservation rule: the spine fields (``versions``,
    ``committee_reports``, ``votes``, ``floor_consideration``, ``conference``,
    ``enactment``) come from *fresh_spine* (re-derived from the API); the
    expensive cross-modal-verified research (``hearings``, ``statements``) and
    the narrative come from *prev*.  Returns *fresh_spine* unchanged when *prev*
    is ``None`` (e.g. a non-enacted bill or a bill that never had leg-history
    assembled).
    """
    if prev is None:
        return fresh_spine
    return fresh_spine.model_copy(
        update={
            "hearings": prev.hearings,
            "statements": prev.statements,
            "narrative": prev.narrative,
        }
    )


def apply_classifier_flip(
    bill: Bill,
    *,
    in_scope: bool,
    rationale: str,
    date: dt.date,
) -> Bill:
    """Return a copy of *bill* reflecting the classifier's verdict.

    * ``in_scope=True`` → returns *bill* unchanged.
    * ``in_scope=False`` → returns a copy with ``tracking=False`` and
      ``flipped_out`` populated.  The existing ``topics`` are NOT cleared (the
      record of the prior classification stands).

    Raises :class:`ValueError` when called on an already-``tracking=False`` bill
    — that case never reaches the refresh pipeline because untracked bills are
    excluded from ``refreshable.json`` by ``fetch-refreshable``.
    """
    if not bill.tracking:
        raise ValueError(f"apply_classifier_flip on already-untracked bill: {bill.id}")
    if in_scope:
        return bill
    return bill.model_copy(
        update={
            "tracking": False,
            "flipped_out": FlipOutAudit(date=date, reason=rationale),
        }
    )
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `uv run pytest tests/test_refresh.py -v`

Expected: **PASS** — all tests green.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/pipeline/refresh.py tests/test_refresh.py
git commit -m "feat(refresh): pure detection, preservation, and flip helpers

New pipeline/refresh.py:
- summary_hash: whitespace-normalized sha256 (parity with enrich)
- detect_refreshable: cursor diff → RefreshableBill | None with subagent triggers
- _amendment_delta: per-amendment change set keyed on number + latest_action_date
- preserve_leg_history: D38 + D40 — keeps hearings/statements/narrative across spine re-derive
- apply_classifier_flip: only place that sets tracking=False; refuses double-flip

No I/O. Composed by fetch-refreshable / render-refreshed in T7/T8.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task T7: CLI — `fetch-refreshable` command

**Files:**
- Modify: `src/zwiadbrain/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_cli.py` (assume a `_runner()` helper similar to existing CLI tests; if not, use `typer.testing.CliRunner` directly):

```python
def test_fetch_refreshable_writes_json_for_changed_bills_only(tmp_path, monkeypatch) -> None:
    """should re-fetch tracked bills, write refreshable.json for those whose update_date moved"""
    import json
    import respx
    from typer.testing import CliRunner
    from zwiadbrain.cli import app
    from zwiadbrain.sources.congress import CONGRESS_API_BASE

    # Wiki with two tracked bills committed to disk.
    wiki = tmp_path / "wiki"
    (wiki / "federal" / "bills").mkdir(parents=True)
    (wiki / "federal" / "bills" / "118-hr-1.md").write_text(
        "---\n"
        "id: 118-hr-1\n"
        "jurisdiction: US\n"
        "title: Bill One\n"
        "bill_number: H.R. 1\n"
        "type: bill\n"
        "tracking: true\n"
        "update_date: '2026-05-01T00:00:00Z'\n"
        "update_date_text: '2026-05-01T00:00:00Z'\n"
        "summary_hash: hash-1\n"
        "amendments_count: 0\n"
        "---\n\n## Summary\n\nx\n",
        encoding="utf-8",
    )
    (wiki / "federal" / "bills" / "118-hr-2.md").write_text(
        "---\n"
        "id: 118-hr-2\n"
        "jurisdiction: US\n"
        "title: Bill Two\n"
        "bill_number: H.R. 2\n"
        "type: bill\n"
        "tracking: true\n"
        "update_date: '2026-05-01T00:00:00Z'\n"
        "update_date_text: '2026-05-01T00:00:00Z'\n"
        "summary_hash: hash-2\n"
        "amendments_count: 0\n"
        "---\n\n## Summary\n\ny\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONGRESS_API_KEY", "test")
    monkeypatch.setenv("GOVINFO_API_KEY", "test")

    # Bill 1 fresh: update_date unchanged → skipped.
    bill1_detail = {"bill": {"congress": 118, "type": "HR", "number": 1, "title": "Bill One",
                              "updateDate": "2026-05-01T00:00:00Z",
                              "updateDateIncludingText": "2026-05-01T00:00:00Z"}}
    # Bill 2 fresh: update_date_text advanced → refreshable, text-changed.
    bill2_detail = {"bill": {"congress": 118, "type": "HR", "number": 2, "title": "Bill Two",
                              "updateDate": "2026-05-05T00:00:00Z",
                              "updateDateIncludingText": "2026-05-05T00:00:00Z"}}
    empty_subs = {"actions": [], "amendments": [], "textVersions": [],
                  "summaries": [], "relatedBills": []}

    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        for n, payload in [(1, bill1_detail), (2, bill2_detail)]:
            mock.get(f"/bill/118/hr/{n}").respond(json=payload)
            mock.get(f"/bill/118/hr/{n}/actions").respond(json={"actions": empty_subs["actions"]})
            mock.get(f"/bill/118/hr/{n}/amendments").respond(json={"amendments": empty_subs["amendments"]})
            mock.get(f"/bill/118/hr/{n}/text").respond(json={"textVersions": empty_subs["textVersions"]})
            mock.get(f"/bill/118/hr/{n}/summaries").respond(json={"summaries": empty_subs["summaries"]})
            mock.get(f"/bill/118/hr/{n}/relatedbills").respond(json={"relatedBills": empty_subs["relatedBills"]})

        out_dir = tmp_path / "run"
        result = CliRunner().invoke(app, [
            "fetch-refreshable", "--wiki", str(wiki), "--out", str(out_dir),
        ])
    assert result.exit_code == 0, result.output
    refreshable = json.loads((out_dir / "refreshable.json").read_text(encoding="utf-8"))
    ids = [r["bill_id"] for r in refreshable]
    assert ids == ["118-hr-2"]
    entry = refreshable[0]
    assert entry["needs_classifier"] is True
    assert entry["needs_summarizer"] is True
    assert entry["changed_amendment_numbers"] == []


def test_fetch_refreshable_writes_empty_list_when_nothing_changed(tmp_path, monkeypatch) -> None:
    """should write refreshable.json with [] when no tracked bill moved"""
    import json
    import respx
    from typer.testing import CliRunner
    from zwiadbrain.cli import app
    from zwiadbrain.sources.congress import CONGRESS_API_BASE

    wiki = tmp_path / "wiki"
    (wiki / "federal" / "bills").mkdir(parents=True)
    (wiki / "federal" / "bills" / "118-hr-1.md").write_text(
        "---\n"
        "id: 118-hr-1\njurisdiction: US\ntitle: Bill One\nbill_number: H.R. 1\n"
        "type: bill\ntracking: true\nupdate_date: '2026-05-01T00:00:00Z'\n---\n\nx\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONGRESS_API_KEY", "test")
    monkeypatch.setenv("GOVINFO_API_KEY", "test")

    with respx.mock(base_url=CONGRESS_API_BASE) as mock:
        mock.get("/bill/118/hr/1").respond(
            json={"bill": {"congress": 118, "type": "HR", "number": 1, "title": "Bill One",
                            "updateDate": "2026-05-01T00:00:00Z"}}
        )
        for sub in ("actions", "amendments", "text", "summaries", "relatedbills"):
            key = {"actions": "actions", "amendments": "amendments", "text": "textVersions",
                   "summaries": "summaries", "relatedbills": "relatedBills"}[sub]
            mock.get(f"/bill/118/hr/1/{sub}").respond(json={key: []})
        out_dir = tmp_path / "run"
        result = CliRunner().invoke(app, [
            "fetch-refreshable", "--wiki", str(wiki), "--out", str(out_dir),
        ])
    assert result.exit_code == 0, result.output
    refreshable = json.loads((out_dir / "refreshable.json").read_text(encoding="utf-8"))
    assert refreshable == []
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/test_cli.py -k "fetch_refreshable" -v`

Expected: **FAIL** — command does not exist.

- [ ] **Step 3: Implement `fetch-refreshable`**

Add to `src/zwiadbrain/cli.py` (place imports + command after the existing `fetch-leg-history` block):

a. **Add imports at the top:**

```python
from zwiadbrain.models import Bill, EnforcementAction, Hearing, LegHistory, Statement
from zwiadbrain.pipeline.leg_history import assemble_spine, collect_leads, ground_items
from zwiadbrain.pipeline.refresh import detect_refreshable, preserve_leg_history
from zwiadbrain.wiki.schema import from_page
```

(merge the new imports into the existing import block; do not duplicate `Bill`.)

b. **Add the command:**

```python
@app.command(name="fetch-refreshable")
def fetch_refreshable(
    wiki: Annotated[Path, typer.Option(help="Wiki root to scan for tracked bills.")] = Path("wiki"),
    out: Annotated[
        Path | None, typer.Option(help="Run directory for refreshable.json.")
    ] = None,
) -> None:
    """Detect tracked federal bills whose Congress.gov cursors have advanced.

    Reads every ``wiki/federal/bills/*.md`` page, re-fetches each tracked bill
    via Congress.gov, compares update-date cursors, and stages the changed
    bills + their subagent triggers to ``refreshable.json`` for the
    ``/zwiad-refresh`` slash command.
    """
    try:
        settings = load_settings()
        congress_source = CongressSource(settings.require_congress_api_key())
        govinfo_source = GovInfoSource(settings.require_govinfo_api_key())
        bills_dir = wiki / "federal" / "bills"
        if not bills_dir.exists():
            typer.echo(f"no federal bills directory under {wiki}", err=True)
            raise typer.Exit(0)
        entries: list[dict[str, object]] = []
        for page_path in sorted(bills_dir.glob("*.md")):
            text = page_path.read_text(encoding="utf-8")
            item = from_page(text)
            if not isinstance(item, Bill) or not item.tracking:
                continue
            congress, bill_type, number = item.id.split("-")
            native_id = f"{congress}/{bill_type}/{number}"
            fresh = congress_source.fetch(native_id)
            # Cross-source enrich seam: compute the cursors that source.fetch
            # cannot (they straddle the source/pipeline boundary by design).
            from zwiadbrain.pipeline.enrich import _summary_hash  # noqa: PLC0415
            fresh.summary_hash = _summary_hash(fresh.summary)
            fresh.amendments_count = len(fresh.amendments)
            # For enacted bills, also re-derive the leg-history spine so
            # render-refreshed can reattach prev's hearings/statements/narrative.
            if fresh.enacted:
                fresh.leg_history = assemble_spine(fresh, congress_source, govinfo_source)
            refreshable = detect_refreshable(item, fresh)
            if refreshable is None:
                continue
            entries.append({
                "bill_id": item.id,
                "prev": item.model_dump(mode="json"),
                "fresh": fresh.model_dump(mode="json"),
                "needs_classifier": refreshable.needs_classifier,
                "needs_summarizer": refreshable.needs_summarizer,
                "changed_amendment_numbers": list(refreshable.changed_amendment_numbers),
            })
        run_dir = out or Path("data/runs") / dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "refreshable.json"
        path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"staged {len(entries)} refreshable bill(s) to {path}")
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `uv run pytest tests/test_cli.py -k "fetch_refreshable" -v`

Expected: **PASS**.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/cli.py tests/test_cli.py
git commit -m "feat(cli): fetch-refreshable command

Scans wiki/federal/bills/ for tracking=true pages, re-fetches each via
Congress.gov, compares update-date cursors, and writes refreshable.json
with the changed bills plus the slash command's per-bill triggers
(needs_classifier, needs_summarizer, changed_amendment_numbers).
Enacted bills also get their leg-history spine re-derived so
render-refreshed can reattach prev's hearings/statements/narrative.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task T8: CLI — `render-refreshed` command

**Files:**
- Modify: `src/zwiadbrain/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_cli.py`:

```python
def test_render_refreshed_applies_preservation_and_renders(tmp_path) -> None:
    """should re-attach prev leg_history, write the page, and report counts"""
    import json
    from typer.testing import CliRunner
    from zwiadbrain.cli import app

    # Fresh bill (from fetch-refreshable) — enacted, with re-derived spine, no hearings.
    fresh = {
        "id": "118-hr-1", "jurisdiction": "US", "title": "Bill One",
        "bill_number": "H.R. 1", "type": "bill", "tracking": True, "enacted": True,
        "leg_history": {
            "versions": [],
            "committee_reports": [
                {"citation": "H. Rept. 1", "url": "https://example.test/c"}
            ],
            "floor_consideration": [], "votes": [], "hearings": [], "statements": [],
            "narrative": None, "conference": None, "enactment": None,
        },
        "topics": ["ai"],
        "summary": "Refreshed summary.",
    }
    # Prev (committed page) — has a hearing + narrative that must survive.
    prev = {
        **fresh,
        "summary": "Old summary.",
        "leg_history": {
            "versions": [], "committee_reports": [],
            "floor_consideration": [], "votes": [],
            "hearings": [{"title": "Hearing X", "url": "https://example.test/h"}],
            "statements": [],
            "narrative": "The arc of the debate.",
            "conference": None, "enactment": None,
        },
    }
    refreshed = [{
        "bill_id": "118-hr-1",
        "prev": prev,
        "bill": fresh,                  # fresh + subagent outputs merged by the slash command
        "classifier_in_scope": True,
        "classifier_rationale": "still about AI",
    }]
    run = tmp_path / "run"
    run.mkdir()
    (run / "refreshed.json").write_text(json.dumps(refreshed), encoding="utf-8")
    wiki = tmp_path / "wiki"

    result = CliRunner().invoke(app, [
        "render-refreshed", "--in", str(run / "refreshed.json"), "--wiki", str(wiki),
        "--db", str(tmp_path / "idx.sqlite"),
    ])
    assert result.exit_code == 0, result.output

    page = (wiki / "federal" / "bills" / "118-hr-1.md").read_text(encoding="utf-8")
    # research carried from prev
    assert "Hearing X" in page
    assert "The arc of the debate." in page
    # spine taken from fresh
    assert "H. Rept. 1" in page
    # summary refreshed
    assert "Refreshed summary." in page
    # report mentions the count
    assert "refreshed 1" in result.output


def test_render_refreshed_flips_out_when_classifier_out_of_scope(tmp_path) -> None:
    """should set tracking=False and emit the audit marker on IN→OUT flip"""
    import json
    from typer.testing import CliRunner
    from zwiadbrain.cli import app

    refreshed = [{
        "bill_id": "118-hr-9",
        "prev": {
            "id": "118-hr-9", "jurisdiction": "US", "title": "Old Title",
            "bill_number": "H.R. 9", "type": "bill", "tracking": True, "topics": ["ai"],
        },
        "bill": {
            "id": "118-hr-9", "jurisdiction": "US", "title": "Old Title",
            "bill_number": "H.R. 9", "type": "bill", "tracking": True, "topics": ["ai"],
            "summary": "Updated",
        },
        "classifier_in_scope": False,
        "classifier_rationale": "telehealth scope drift",
    }]
    run = tmp_path / "run"
    run.mkdir()
    (run / "refreshed.json").write_text(json.dumps(refreshed), encoding="utf-8")
    wiki = tmp_path / "wiki"

    result = CliRunner().invoke(app, [
        "render-refreshed", "--in", str(run / "refreshed.json"), "--wiki", str(wiki),
        "--db", str(tmp_path / "idx.sqlite"),
    ])
    assert result.exit_code == 0, result.output

    page = (wiki / "federal" / "bills" / "118-hr-9.md").read_text(encoding="utf-8")
    assert "tracking: false" in page
    assert "<!-- zwiadbrain:flipped-out " in page
    assert "telehealth scope drift" in page
    # topics preserved (the prior classification's record stands)
    assert "ai" in page
    assert "1 flipped-out" in result.output
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/test_cli.py -k "render_refreshed" -v`

Expected: **FAIL** — command does not exist.

- [ ] **Step 3: Implement `render-refreshed`**

Add to `src/zwiadbrain/cli.py` (place after `fetch-refreshable`):

a. **Add imports** (merge into the top import block; the `apply_classifier_flip` import is new):

```python
from zwiadbrain.pipeline.refresh import apply_classifier_flip, detect_refreshable, preserve_leg_history
```

b. **Add the command:**

```python
@app.command(name="render-refreshed")
def render_refreshed(
    input_file: Annotated[
        Path, typer.Option("--in", help="refreshed.json staged by /zwiad-refresh."),
    ],
    wiki: Annotated[Path, typer.Option(help="Wiki root to write pages under.")] = Path("wiki"),
    db: Annotated[Path, typer.Option(help="SQLite index path.")] = Path("data/cache/index.sqlite"),
) -> None:
    """Apply subagent outputs, the D38 preservation rule, and the IN→OUT flip; render + reindex."""
    try:
        raw = json.loads(input_file.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ConfigError(
                f"refreshed.json must be a JSON list, got {type(raw).__name__}"
            )
        refreshed_count = 0
        flipped_out: list[tuple[str, str]] = []
        for entry in raw:
            if not isinstance(entry, dict):
                raise ConfigError("each entry in refreshed.json must be a JSON object")
            prev = Bill.model_validate(entry["prev"])
            bill = Bill.model_validate(entry["bill"])
            in_scope = bool(entry.get("classifier_in_scope", True))
            rationale = str(entry.get("classifier_rationale") or "")
            # Preserve leg-history research onto fresh spine.
            if prev.leg_history is not None and bill.leg_history is not None:
                bill = bill.model_copy(update={
                    "leg_history": preserve_leg_history(prev.leg_history, bill.leg_history),
                })
            elif prev.leg_history is not None and bill.leg_history is None:
                # Defensive: a fresh non-enacted bill has no spine, but prev had research.
                # Carry prev.leg_history through unchanged so the research is not lost.
                bill = bill.model_copy(update={"leg_history": prev.leg_history})
            # Apply classifier verdict (no-op when in_scope=True, flip when False).
            bill = apply_classifier_flip(
                bill,
                in_scope=in_scope,
                rationale=rationale,
                date=dt.datetime.now(dt.UTC).date(),
            )
            write_page(bill, wiki)
            refreshed_count += 1
            if not bill.tracking and bill.flipped_out is not None:
                flipped_out.append((bill.id, bill.flipped_out.reason))
        # Reindex after all writes.
        with Store(db) as store:
            store.reindex(wiki)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    flipped_count = len(flipped_out)
    typer.echo(
        f"refresh complete: refreshed {refreshed_count} / {flipped_count} flipped-out"
    )
    for bill_id, reason in flipped_out:
        typer.echo(f"  flipped-out: {bill_id} — \"{reason}\"")
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `uv run pytest tests/test_cli.py -k "render_refreshed" -v`

Expected: **PASS**.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/cli.py tests/test_cli.py
git commit -m "feat(cli): render-refreshed command

Reads refreshed.json (slash command output), applies the D38 + D40
preservation rule (leg_history.hearings/statements/narrative carried
from prev onto fresh's spine), applies the classifier flip via
apply_classifier_flip (IN-scope no-op, OUT-of-scope sets tracking=false
with audit marker), writes pages, and reindexes. Reports refreshed and
flipped-out counts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task T9: Slash command `/zwiad-refresh`

**Files:**
- Create: `.claude/commands/zwiad-refresh.md`
- Modify: `tests/test_agents.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_agents.py`:

```python
def test_zwiad_refresh_command_frontmatter_parses() -> None:
    """should declare description, argument-hint, and allow Bash/Read/Write/Task"""
    import frontmatter
    from pathlib import Path
    text = Path(".claude/commands/zwiad-refresh.md").read_text(encoding="utf-8")
    post = frontmatter.loads(text)
    assert post.metadata["description"]
    assert "Bash" in post.metadata["allowed-tools"]
    assert "Read" in post.metadata["allowed-tools"]
    assert "Write" in post.metadata["allowed-tools"]
    assert "Task" in post.metadata["allowed-tools"]


def test_zwiad_refresh_references_existing_subagents() -> None:
    """should reference the classifier, summarizer, amendment-explainer subagents"""
    from pathlib import Path
    text = Path(".claude/commands/zwiad-refresh.md").read_text(encoding="utf-8")
    assert "classifier" in text
    assert "summarizer" in text
    assert "amendment-explainer" in text
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/test_agents.py -k "zwiad_refresh" -v`

Expected: **FAIL** — file does not exist.

- [ ] **Step 3: Create the slash command**

Create `.claude/commands/zwiad-refresh.md`:

````markdown
---
description: Refresh tracked federal bills — detect changed cursors, dispatch classifier/summarizer/amendment-explainer subagents only where triggers fired, preserve PHASE-05 leg-history, flip out-of-scope bills (runs on your regular Claude plan usage).
argument-hint: "[--bill <id>]"
allowed-tools: Bash, Read, Write, Task
---

# ZwiadBrain watchlist refresh (Pass A)

Re-fetch every tracked federal bill, dispatch subagents only on real change,
preserve PHASE-05's expensive cross-modal-verified leg-history (hearings +
statements + narrative), and flip IN→OUT bills to `tracking: false`. Python
does the deterministic fetch + render; you (this interactive session) do the
LLM steps so the work runs on the regular Claude plan, **not** the API or the
Agent SDK credit.

Optional argument: `$1` may be `--bill <id>` to refresh a single bill (rare;
default is all tracking=true federal bills).

## Steps

### 1. Fetch refreshable (Python, deterministic)
Run:
```
uv run zwiadbrain fetch-refreshable
```
Scans `wiki/federal/bills/*.md` frontmatter for tracking=true bills,
re-fetches each via Congress.gov, compares cursors, and writes
`refreshable.json` to `data/runs/<id>/`. **Note the exact path it prints.**

If the file is `[]`, every tracked bill is up to date — report `no
refreshable bills` and STOP. Do not run the subagents in this case.

### 2. Read the refreshable list
`Read` the `refreshable.json`. Each entry is:
```json
{
  "bill_id": "...",
  "prev": {full prev Bill},
  "fresh": {full fresh Bill, with leg_history.spine re-derived if enacted},
  "needs_classifier": true|false,
  "needs_summarizer": true|false,
  "changed_amendment_numbers": ["H.Amdt. 1", ...]
}
```

### 3. Per-bill subagent dispatch
For each entry, build a `bill` object starting from a copy of `fresh`, then:

a. **Classifier** (only if `needs_classifier`): dispatch the **classifier**
   subagent with `fresh.title` and `fresh.summary`. Capture
   `{in_scope, topics, rationale, criterion}`. Save as `classifier_in_scope`,
   `classifier_rationale`, and set `bill.topics = classifier.topics` (only
   when in-scope; leave `bill.topics = prev.topics` on out-of-scope to
   preserve the prior record).

b. **Summarizer** (only if `needs_summarizer` AND classifier returned in-scope
   — out-of-scope bills do not get a fresh summary): dispatch the
   **summarizer** subagent with `fresh` → set `bill.summary` to the returned
   prose.

c. **Amendment-explainer** (only if `changed_amendment_numbers` is non-empty
   AND classifier in-scope): dispatch the **amendment-explainer** with the
   amendments whose `number` is in `changed_amendment_numbers`, and set each
   matching `bill.amendments[i].what_changed`. Carry forward existing
   `what_changed` for amendments NOT in `changed_amendment_numbers`.

When classifier returned out-of-scope, do NOT dispatch summarizer or
amendment-explainer — the bill is being flipped out and re-running the
expensive subagents is wasted plan usage.

### 4. Stage refreshed
`Write` a `refreshed.json` array in the same run directory. Each entry:
```json
{
  "bill_id": "...",
  "prev": {prev Bill verbatim},
  "bill": {bill with all subagent outputs merged},
  "classifier_in_scope": true|false,
  "classifier_rationale": "..."
}
```
When `needs_classifier` was false, set `classifier_in_scope: true` and
`classifier_rationale: ""` so the Python step sees a consistent shape.

### 5. Render + index (Python, deterministic)
Run:
```
uv run zwiadbrain render-refreshed --in data/runs/<id>/refreshed.json
```
This applies the D38 + D40 leg-history preservation rule, the IN→OUT flip,
re-renders pages, and reindexes the FTS5 store. It prints
`refresh complete: refreshed N / K flipped-out`.

### 6. Report
Summarize: number of refreshable bills detected, subagent dispatch counts
(classifier / summarizer / explainer calls), bills refreshed, bills flipped
out (with reasons). Do not commit — leave the wiki changes for review.

## Notes
- Keep `ANTHROPIC_API_KEY` unset so subagents use your plan session, not the API.
- The D38 + D40 rule is enforced by `render-refreshed`: prev's
  `leg_history.hearings/statements/narrative` always survive a refresh.
- A bill whose classifier verdict flips IN→OUT is re-rendered with
  `tracking: false` and an audit marker; its page stays at the same path and
  its committed history is preserved (a future `/zwiad-backfill --force <id>`,
  not yet implemented, could re-track it).
````

- [ ] **Step 4: Run tests — verify they pass**

Run: `uv run pytest tests/test_agents.py -k "zwiad_refresh" -v`

Expected: **PASS**.

- [ ] **Step 5: Commit**

```bash
git add .claude/commands/zwiad-refresh.md tests/test_agents.py
git commit -m "feat(commands): /zwiad-refresh slash command

Orchestrates fetch-refreshable → per-bill subagent dispatch (classifier,
summarizer, amendment-explainer; only on triggered changes) → write
refreshed.json → render-refreshed. Mirrors zwiad-backfill / zwiad-leg-history
patterns; runs on the user's regular Claude plan.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task L1: GovInfo Statutes-at-Large — fetch + wire through

**Files:**
- Modify: `src/zwiadbrain/sources/govinfo.py`
- Modify: `tests/test_govinfo.py`
- Modify: `tests/fixtures/govinfo/related_statute.json` (new)
- Modify: `tests/fixtures/govinfo/related_statute_empty.json` (new)

- [ ] **Step 1: Add fixture files**

Create `tests/fixtures/govinfo/related_statute.json`:

```json
{
  "results": [
    {
      "packageId": "STATUTE-138-Pg1234",
      "granuleId": null,
      "title": "Statutes at Large Volume 138, Page 1234"
    }
  ]
}
```

Create `tests/fixtures/govinfo/related_statute_empty.json`:

```json
{ "results": [] }
```

- [ ] **Step 2: Write failing tests**

Append to `tests/test_govinfo.py`:

```python
def test_fetch_statutes_at_large_maps_first_row_to_statutes_at_large() -> None:
    """should map STATUTE related row to StatutesAtLarge(citation, url)"""
    import respx
    from zwiadbrain.models import StatutesAtLarge
    from zwiadbrain.sources.govinfo import GOVINFO_API_BASE, GovInfoSource

    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get("/related/PLAW-118publ31/STATUTE").respond(json=_fixture("related_statute.json"))
        result = GovInfoSource(api_key="k").fetch_statutes_at_large("PLAW-118publ31")
    assert isinstance(result, StatutesAtLarge)
    assert result.citation == "Statutes at Large Volume 138, Page 1234"
    assert result.url == "https://www.govinfo.gov/app/details/STATUTE-138-Pg1234"


def test_fetch_statutes_at_large_returns_none_on_empty_related() -> None:
    """should return None when /related/{plaw}/STATUTE has no results (fail-quiet)"""
    import respx
    from zwiadbrain.sources.govinfo import GOVINFO_API_BASE, GovInfoSource

    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get("/related/PLAW-118publ99/STATUTE").respond(json=_fixture("related_statute_empty.json"))
        result = GovInfoSource(api_key="k").fetch_statutes_at_large("PLAW-118publ99")
    assert result is None


def test_enacted_law_now_populates_statutes_at_large() -> None:
    """should call fetch_statutes_at_large and attach the result to Enactment"""
    import respx
    from zwiadbrain.sources.govinfo import GOVINFO_API_BASE, GovInfoSource, enrolled_bill_package_id

    pkg_id = enrolled_bill_package_id(118, "HR", 8818)
    plaw_results = {"results": [{"packageId": "PLAW-118publ42"}]}
    with respx.mock(base_url=GOVINFO_API_BASE) as mock:
        mock.get(f"/related/{pkg_id}/PLAW").respond(json=plaw_results)
        mock.get("/related/PLAW-118publ42/STATUTE").respond(json=_fixture("related_statute.json"))
        result = GovInfoSource(api_key="k").enacted_law(118, "HR", 8818)
    assert result is not None
    assert result.statutes_at_large is not None
    assert result.statutes_at_large.citation == "Statutes at Large Volume 138, Page 1234"
```

- [ ] **Step 3: Run tests — verify they fail**

Run: `uv run pytest tests/test_govinfo.py -k "statutes_at_large" -v`

Expected: **FAIL** — `fetch_statutes_at_large` does not exist; `enacted_law` does not populate the field.

- [ ] **Step 4: Implement**

Edit `src/zwiadbrain/sources/govinfo.py`:

a. **Add `StatutesAtLarge` to imports:**

```python
from zwiadbrain.models import CommitteeReport, Enactment, FloorAction, Hearing, StatutesAtLarge
```

b. **Add the new method to `GovInfoSource` (place after `enacted_law`):**

```python
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
```

c. **Update `enacted_law` to populate the field:**

```python
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
```

- [ ] **Step 5: Run tests — verify they pass**

Run: `uv run pytest tests/test_govinfo.py -v`

Expected: **PASS** — new tests green; the rest of the govinfo test file still passes.

- [ ] **Step 6: Commit**

```bash
git add src/zwiadbrain/sources/govinfo.py tests/test_govinfo.py tests/fixtures/govinfo/related_statute.json tests/fixtures/govinfo/related_statute_empty.json
git commit -m "feat(govinfo): populate Enactment.statutes_at_large from /related/STATUTE

Closes PHASE-05 M1 (deferred). fetch_statutes_at_large resolves a PLAW
package's STATUTE related row to a StatutesAtLarge(citation, url); empty
result list returns None (fail-quiet — some PLAW packages don't yet
have a published STATUTE volume). enacted_law now wires it through to
the returned Enactment.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task L2: Grounding gate — BeautifulSoup text extract

**Files:**
- Modify: `src/zwiadbrain/pipeline/leg_history.py`
- Modify: `tests/test_leg_history.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_leg_history.py`:

```python
def test_ground_items_accepts_quote_inside_html_when_text_extracted() -> None:
    """should ground a quote present in extracted text but not in raw HTML byte-match"""
    from zwiadbrain.models import Statement
    from zwiadbrain.pipeline.leg_history import ground_items

    # Mimics a press-release page where the quote text is split by <br/> tags +
    # nbsp + a leading <span class="js-only"> wrapper that current raw-HTML
    # substring match rejects.
    html_page = (
        '<html><body><div class="release">'
        '<p><span class="js-only">Senator X said:</span>&nbsp;</p>'
        '<p>"This is a very important and notable<br/>quote about AI."</p>'
        "</body></html>"
    )
    statements = [
        Statement(
            speaker="Senator X", role="member",
            quote='This is a very important and notable quote about AI.',
            source_url="https://example.test/pr", source_type="press",
        )
    ]
    result = ground_items(
        statements, hearings=[],
        fetch=lambda url: (200, html_page),
        verifier_verdicts={0: True},
    )
    assert len(result.statements) == 1
    assert result.statements[0].verified is True


def test_ground_items_still_rejects_genuinely_absent_quote() -> None:
    """should drop a quote that is not on the extracted-text page (precision held)"""
    from zwiadbrain.models import Statement
    from zwiadbrain.pipeline.leg_history import ground_items

    html_page = "<html><body><p>An entirely unrelated discussion of fiscal policy.</p></body></html>"
    statements = [
        Statement(
            speaker="Senator Y", role="member",
            quote="This quote does not appear anywhere on the page at all.",
            source_url="https://example.test/x", source_type="press",
        )
    ]
    result = ground_items(
        statements, hearings=[],
        fetch=lambda url: (200, html_page),
        verifier_verdicts={0: True},
    )
    assert len(result.statements) == 0
    assert any(d.reason == "quote not found on source page" for d in result.dropped)
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/test_leg_history.py -k "ground_items_accepts_quote_inside_html or rejects_genuinely_absent" -v`

Expected: The "accepts" test FAILS (current code can't see the quote across the `<br/>` split + leading nbsp); the "rejects" test may already pass — verify both behaviors.

- [ ] **Step 3: Implement the extraction step**

Edit `src/zwiadbrain/pipeline/leg_history.py`:

a. **Add the BeautifulSoup import at the top:**

```python
from bs4 import BeautifulSoup
```

b. **Add a module-private text extractor and update `_quote_present` to use it:**

Add this helper after `_normalize_text`:

```python
def _page_text(page: str) -> str:
    """Extract human-visible text from an HTML page for quote-presence comparison.

    HTML byte-substring matching over-rejects on JS-rendered press-release pages
    and CREC pages where the quote sits across tag boundaries (e.g. a ``<br/>``
    split, a ``<span>`` wrapper, or an inline ``&nbsp;``).  BeautifulSoup's
    ``get_text(separator=' ')`` walks the parsed DOM and returns a single string
    with tag boundaries replaced by spaces; downstream
    :func:`_normalize_text` then collapses runs of whitespace, so a quote
    fragmented across markup matches as long as its WORDS appear in order.

    NOTE on the trust boundary: this raises recall (more true-positives) without
    lowering precision — the deterministic gate still requires the exact
    normalized quote to appear in the extracted text, and the cross-modal
    verifier subagent independently checks speaker attribution.  A
    misattributed-but-present quote is therefore kept by this gate and dropped
    by the verifier, by design.
    """
    return BeautifulSoup(page, "html.parser").get_text(separator=" ")
```

Update `_quote_present`:

```python
def _quote_present(quote: str, page_text: str) -> bool:
    """Return True when *quote* appears (after normalization) inside *page_text*.

    *page_text* is treated as HTML and extracted to plain text before
    normalization; see :func:`_page_text`.  An empty or blank-only *quote*
    always returns False — an empty string must not be treated as matching.
    The comparison is case-sensitive: attributed quotes must match the source
    verbatim.
    """
    normalized_quote = _normalize_text(quote)
    if not normalized_quote:
        return False
    return normalized_quote in _normalize_text(_page_text(page_text))
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `uv run pytest tests/test_leg_history.py -v`

Expected: **PASS** — both new tests; pre-existing PHASE-05 leg-history tests still green.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/pipeline/leg_history.py tests/test_leg_history.py
git commit -m "fix(grounding): extract page text via BeautifulSoup before quote match

Closes PHASE-05 grounding-gate recall gap. The deterministic gate now
extracts visible text with BeautifulSoup get_text(separator=' ') before
applying the existing whitespace/curly-quote normalization. Quotes that
straddle <br/>, <span>, &nbsp; on JS-rendered press releases and CREC
pages now ground correctly. Precision unchanged — a genuinely-absent
quote still fails the substring check; speaker attribution remains the
verifier subagent's job (a misattributed-but-present quote is still
dropped by the verifier).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task T10: DECISIONS.md — D39 and D40

**Files:**
- Modify: `DECISIONS.md`

- [ ] **Step 1: Append the two decisions**

Append to `DECISIONS.md`:

```markdown

## 2026-05-28 — 39. `/zwiad-refresh` re-classifies on text change, overriding D9 for routine refresh
**Chosen:** `/zwiad-refresh` dispatches the classifier on every bill whose `updateDateIncludingText` advanced or whose `summary_hash` changed, even if the bill was previously classified IN-scope and its identifiers haven't changed. Overrides D9 ("decided pages trusted until their identifiers change") narrowly — for the routine-refresh path only. Initial classification (`/zwiad-backfill`) still follows D9.
**Alternatives:** (a) Trust the prior classification; re-run only summarizer + amendment-explainer on refresh; (b) Hold proposed flips in a review queue (requires the PHASE-09 review-queue machinery, which is not yet built).
**Why:** User decision — wants prose freshness (summary + amendments) AND scope freshness (topics) to track together. Avoids the failure mode where a bill silently drifts out of scope (e.g. an AI clause struck in markup) while the wiki keeps tracking + summarizing it as if it were still in scope.
**Trade-offs:** One extra classifier call per text-changed bill (plan usage). Possible flap if the classifier is noisy on borderline bills. Mitigated by the OUT→stay-with-`tracking=false` rule (the page is never deleted; flipping back IN requires explicit `/zwiad-backfill --force` — a follow-up, not built in this phase).
**Revisit if:** Flap is observed (a bill toggles IN/OUT across runs without substantive change) — then narrow to summarizer + explainer per alternative (a), or add the review-queue gate.

## 2026-05-28 — 40. `LegHistory.narrative` persists to frontmatter alongside hearings/statements
**Chosen:** Extend D37's partial-persistence carve-out: page frontmatter's `leg_history` block now carries `{hearings, statements, narrative}` (D37 was `{hearings, statements}` only). Spine fields (versions, committee_reports, votes, floor_consideration, enactment) remain body-only / re-derived per D37.
**Alternatives:** Leave D37 as-is; a routine refresh strips the narrative; user re-runs `/zwiad-leg-history` to regenerate.
**Why:** The narrative is the same kind of expensive, non-deterministic, model-generated output as the verified statements — losing it on routine refresh would silently degrade the most-read part of the leg-history section. Surviving in frontmatter is the same property `hearings`/`statements` already have.
**Trade-offs:** Slightly longer YAML (the narrative is prose, not a structured list). Splits `LegHistory` persistence further: structured research + narrative in frontmatter; spine body-only.
**Revisit if:** Narrative prose in YAML proves unwieldy — then encode it as a path reference to a sidecar file and keep the frontmatter slim.
```

- [ ] **Step 2: Commit**

```bash
git add DECISIONS.md
git commit -m "docs(decisions): log D39 (refresh re-classifies) and D40 (narrative persists)

D39 narrowly overrides D9 for the routine-refresh path so a bill that
silently drifts out of scope mid-cycle is caught. D40 extends D37 so
LegHistory.narrative persists to frontmatter alongside hearings and
statements, surviving a routine refresh.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task T11: Quality gate + version bump + tag

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/zwiadbrain/__init__.py`

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`

Expected: All tests pass. If any pre-existing test breaks, investigate and fix the regression before continuing — do not bump version on a red build.

- [ ] **Step 2: Run ruff**

Run: `uv run ruff check .`

Expected: clean. Fix any new lint issues before continuing.

- [ ] **Step 3: Run pyright (strict)**

Run: `uv run pyright`

Expected: 0 errors. Fix any new type errors before continuing.

- [ ] **Step 4: Bump version**

Edit `pyproject.toml`:

```toml
version = "0.6.0"
```

Edit `src/zwiadbrain/__init__.py`:

```python
__version__ = "0.6.0"
```

- [ ] **Step 5: Verify version**

Run: `uv run zwiadbrain version`

Expected: prints `0.6.0`.

- [ ] **Step 6: Commit + tag (do not push)**

```bash
git add pyproject.toml src/zwiadbrain/__init__.py
git commit -m "chore(release): bump version to 0.6.0 (PHASE-06)

PHASE-06 ships:
- Watchlist refresh (/zwiad-refresh) with cursor-based detection,
  per-bill subagent triggers, D38+D40 leg-history preservation,
  and IN→OUT classifier flip
- L1: Enactment.statutes_at_large populated from GovInfo
- L2: Grounding gate uses BeautifulSoup text-extract (recall lift)
- D39 + D40 logged

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git tag -a v0.6.0 -m "PHASE-06 — watchlist refresh + PHASE-05 leftovers"
```

DO NOT push or merge yet — T12 UAT must pass first.

---

## Task T12: Interactive UAT (Pass A + L1 + L2)

This task is run by the user in an interactive Claude Code session on their regular plan. It is NOT executed by an agent — the agent's job ends after T11 commits clean.

**Files:**
- `wiki/federal/bills/118-hr-2670.md` (existing — re-rendered as part of UAT)
- `.claude/phases/PHASE-06-active.md` → `PHASE-06-done.md` (renamed only on success)

- [ ] **Step 1: Re-run `/zwiad-leg-history 118/hr/2670`**

In an interactive session:

```
/zwiad-leg-history 118/hr/2670
```

Why: the existing 118-hr-2670 frontmatter does not have `leg_history.narrative` (D37 stored it body-only). PHASE-06 starts persisting narrative to frontmatter (D40); if `/zwiad-refresh` runs before this regeneration, the body-only narrative will be silently stripped on the next render. Running `/zwiad-leg-history` here regenerates the narrative and lands it in frontmatter via the new path.

Expected:
- Page renders cleanly.
- Frontmatter now contains `leg_history.narrative`.
- `Enactment.statutes_at_large` appears in the rendered page as `Statutes at Large: [Statutes at Large Volume X, Page Y](https://www.govinfo.gov/app/details/STATUTE-…)` (L1 UAT).
- Re-running once more should produce a byte-identical page (`git diff` empty on the second run).

- [ ] **Step 2: Verify `/zwiad-refresh` reports unchanged on a fresh page**

```
/zwiad-refresh
```

Expected:
- `fetch-refreshable` writes `refreshable.json` containing `[]` (118-hr-2670 was just refreshed and Congress hasn't moved its cursor since).
- The slash command STOPs after step 1 with `no refreshable bills`.
- `git status` is clean.

- [ ] **Step 3: Pick a deliberately-stale bill and verify a real refresh**

Pick one of: (a) backfill a new federal bill via `/zwiad-backfill 118 5` and then mutate its frontmatter `update_date` field locally to an older value, or (b) use a live bill whose Congress.gov `updateDate` you know has advanced since the local copy was rendered.

```
/zwiad-refresh
```

Expected:
- `refreshable.json` contains the one bill.
- The slash command dispatches the appropriate subagents (classifier + summarizer if text changed; explainer if amendments grew).
- `render-refreshed` reports `refresh complete: refreshed 1 / 0 flipped-out`.
- The rendered page shows fresh subagent outputs (new summary prose, etc.) AND preserves the prior `leg_history.hearings/statements/narrative` byte-for-byte if the bill was enacted.

- [ ] **Step 4: L2 UAT — grounding gate recall**

Re-run `/zwiad-leg-history` on a bill whose `.senate.gov` press-release statement was dropped in PHASE-05 (audit the PHASE-05 commit transcripts for the specific bill and statement). Confirm the previously-dropped statement now grounds + verifies.

Expected:
- The PHASE-05 audit log entry "dropped statement: <speaker>: <quote> — quote not found on source page" no longer appears for that specific statement.
- The statement is now rendered with ✓.
- Other statements behave as before.

- [ ] **Step 5: Update DECISIONS.md if any UAT finding changes a documented assumption**

If a UAT finding contradicts the spec (e.g. the deterministic-gate text extract still over-rejects on a different page shape), record it as an appended finding under PHASE-06 in `.claude/phases/PHASE-06-active.md` and decide whether to fold a fix into T11's quality gate (re-open commit) or carry it as a known follow-up.

- [ ] **Step 6: Rename phase file and push**

```bash
git mv .claude/phases/PHASE-06-active.md .claude/phases/PHASE-06-done.md
```

Append a `## Outcome (YYYY-MM-DD)` section to the renamed file summarizing the UAT findings (mirroring the PHASE-05 outcome paragraph).

```bash
git add .claude/phases/PHASE-06-done.md
git commit -m "chore(phase-06): close phase — UAT passed

UAT outcomes:
- /zwiad-refresh: no-op on fresh 118-hr-2670 (clean git status)
- Real refresh of <bill_id>: subagents dispatched only on triggered changes;
  leg_history.hearings/statements/narrative survived
- L1: Statutes at Large link renders for 118-hr-2670
- L2: previously-dropped <speaker>:<quote> now grounds + verifies

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
git push --tags
```

PHASE-06 closes here.

---

## Plan self-review

Per the writing-plans skill, a fresh-eyes check before handoff.

**Spec coverage:** Walked Sections 1–12 of the spec.

| Spec section | Covered by |
|---|---|
| §1 Outcome | T6–T9 (Pass A path); L1 + L2 (leftovers); T11 release |
| §2 Architecture (Python → subagent → Python) | T7 (fetch-refreshable), T9 (slash command), T8 (render-refreshed) |
| §3 Trigger logic + cursors | T1 (model fields), T2 (congress mapping), T3 (hash/count), T6 (detect_refreshable) |
| §4 D38 preservation rule | T4 (schema persists narrative), T6 (preserve_leg_history), T8 (applied in render-refreshed) |
| §5 Out-of-scope flip | T1 (FlipOutAudit), T5 (renderer marker), T6 (apply_classifier_flip), T8 (applied) |
| §6 L1 (Statutes-at-Large) | L1 |
| §6 L2 (grounding gate text-extract) | L2 |
| §7 File map | every task references its exact paths |
| §8 Test plan | each task has its own failing-test step |
| §9 UAT | T12 |
| §10 Tasks list | T0–T12 + L1, L2 |
| §11 D39 + D40 | T10 |
| §12 Open follow-ups | left as documented in the spec; not implemented this phase |

No gaps detected.

**Placeholder scan:** No `TBD`, `TODO`, `implement later`, or "Add appropriate error handling" anywhere. Every step shows the actual code. Every test step shows the actual test body.

**Type consistency:** Method/property names cross-checked:
- `RefreshableBill.needs_classifier` / `needs_summarizer` / `needs_explainer` (property) / `changed_amendment_numbers` — used identically across T6, T7, T9.
- `Bill.update_date` (bare) and `Bill.update_date_text` (text-including) — used identically across T1, T2, T6.
- `FlipOutAudit(date, reason)` — used identically across T1, T5, T6, T8.
- `StatutesAtLarge(citation, url)` — used identically across T1, T5, L1.
- `summary_hash` lives in both `enrich.py` (private `_summary_hash`) and `refresh.py` (public `summary_hash`) — intentional duplication of a 3-line helper to keep enrich and refresh decoupled (refresh has no business depending on enrich); both apply the same whitespace-collapse + sha256.

No inconsistencies detected.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-28-phase06-watchlist-refresh.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
