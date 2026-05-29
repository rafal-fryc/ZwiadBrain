# Phase 08 — Enforcement Actions (FTC + state AGs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track AI/privacy/cyber **enforcement actions** (FTC + 7 priority-state AGs) as first-class wiki pages via a discovery-driven `/zwiad-scan-enforcement` command, consolidating multi-item matters (complaint → settlement) onto one page.

**Architecture:** Deterministic Python bookends + interactive subagents (D26/D27). A new `EnforcementSource` contract (FTC RSS + a generic config-driven AG adapter) discovers items forward-from-now (D44); a two-tier matcher (deterministic strong key → `enforcement-matcher` subagent on respondent+date → **deterministic confirm in the render half**, fail-safe to a new page, D53) decides new-vs-consolidate. The `EnforcementAction` model, render/schema, and CLI fetch/render pattern are reused; only a `developments[]` timeline is added.

**Tech Stack:** Python 3.12, httpx, feedparser, beautifulsoup4, tenacity, pydantic, typer, pytest + respx. No new dependencies; no API key (public feeds).

**Spec:** `docs/superpowers/specs/2026-05-29-phase08-enforcement-actions-design.md`

---

## File Structure

**New source files**
- `src/zwiadbrain/sources/enforcement/base.py` — `EnforcementCandidate`, `EnforcementSource` protocol, shared `parse_feed` / `extract_article_text` helpers.
- `src/zwiadbrain/sources/enforcement/ftc.py` — `FTCSource`.
- `src/zwiadbrain/sources/enforcement/state_ag.py` — generic `StateAGSource`.

**New pipeline file**
- `src/zwiadbrain/pipeline/enforcement.py` — `MatterRef`, pure matching/confirm/merge helpers.

**Modified core**
- `src/zwiadbrain/models.py` — `EnforcementDevelopment` + `EnforcementAction.developments`.
- `src/zwiadbrain/wiki/templates.py` — "Developments" section.
- `src/zwiadbrain/pipeline/ids.py` — `parse_strong_key` + `build_enforcement_id`.
- `src/zwiadbrain/config.py` — `EnforcementSettings`, `FTCSettings`, `StateAGSource` (config model).
- `src/zwiadbrain/cli.py` — `fetch-enforcement-candidates`, `render-enforcement`.

**New agent/command/config**
- `.claude/agents/enforcement-classifier.md`, `enforcement-extractor.md`, `enforcement-matcher.md`.
- `.claude/commands/zwiad-scan-enforcement.md`.
- `reference/topics.yaml` — `positive_criteria_enforcement` + `disqualify_enforcement`.
- `zwiadbrain.toml` — `[enforcement]` block + FTC + 7 AG entries.

**Tests / fixtures**
- `tests/fixtures/enforcement/{ftc_press_rss.xml,ftc_press.html,ag_ca_rss.xml,ag_html_list.html,ag_press.html}`.
- `tests/test_enforcement_models.py`, `test_enforcement_id.py`, `test_enforcement_matching.py`, `test_enforcement_sources.py`, `test_enforcement_cli.py`, plus additions to `test_render.py`/`test_schema.py`.

**Docs:** `DECISIONS.md` (D52–D55), `ARCHITECTURE.md`, `docs/PLAN.md`, `.claude/phases/PHASE-08-active.md`.

---

## Shared contracts (define once, referenced by later tasks)

```python
# models.py
class EnforcementDevelopment(BaseModel):
    date: dt.date | None = None
    summary: str
    source_url: _HttpUrlStr

# EnforcementAction gains: developments: list[EnforcementDevelopment] = []

# sources/enforcement/base.py
class EnforcementCandidate(BaseModel):
    source: str            # "ftc" | "state_ag"
    agency: str            # "FTC" | "California OAG"
    agency_slug: str       # "ftc" | "ca-oag"
    jurisdiction: str      # "US" | "US-CA"
    title: str
    url: str
    published: dt.date | None = None
    raw: dict[str, object] = {}
    text: str | None = None

# pipeline/enforcement.py
class MatterRef(BaseModel):
    id: str
    agency_slug: str
    jurisdiction: str
    respondent: str | None = None
    date_filed: dt.date | None = None
    strong_key: str | None = None
```

**classified.json entry** (slash command → `render-enforcement`):
```jsonc
{ "matter_id": "<id>"|null, "match_source": "strong_key"|"llm"|"none",
  "match_confidence": 0.0, "agency": "FTC", "agency_slug": "ftc",
  "jurisdiction": "US", "strong_key": "c-4790"|null, "respondent": "...",
  "title": "...", "topics": ["privacy"], "summary": "...", "background": "...",
  "allegations": "...", "outcome": "...", "significance": "...",
  "action_type": "...", "statutes": ["..."], "penalties": "...",
  "status": "...", "date_filed": "2025-01-02", "date_resolved": null,
  "development": {"date": "2025-01-02", "summary": "...", "source_url": "https://..."},
  "source_url": "https://...", "sources": {"FTC": "https://..."} }
```

---

## Task 1: Model — `EnforcementDevelopment` + `EnforcementAction.developments`

**Files:**
- Modify: `src/zwiadbrain/models.py`
- Test: `tests/test_enforcement_models.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enforcement_models.py
import datetime as dt

from zwiadbrain.models import EnforcementAction, EnforcementDevelopment, parse_wiki_item


def test_enforcement_action_accepts_developments() -> None:
    action = EnforcementAction(
        id="ftc-c-4790",
        jurisdiction="US",
        title="FTC v. Acme",
        agency="FTC",
        respondent="Acme, Inc.",
        developments=[
            EnforcementDevelopment(
                date=dt.date(2025, 1, 2),
                summary="Complaint filed.",
                source_url="https://www.ftc.gov/x",
            )
        ],
    )
    assert action.developments[0].summary == "Complaint filed."


def test_parse_wiki_item_routes_enforcement_with_developments() -> None:
    data = {
        "id": "ftc-c-4790", "type": "enforcement", "jurisdiction": "US",
        "title": "FTC v. Acme", "agency": "FTC",
        "developments": [
            {"date": "2025-01-02", "summary": "Complaint filed.",
             "source_url": "https://www.ftc.gov/x"}
        ],
    }
    item = parse_wiki_item(data)
    assert isinstance(item, EnforcementAction)
    assert item.developments[0].date == dt.date(2025, 1, 2)


def test_enforcement_development_rejects_non_http_url() -> None:
    import pytest
    with pytest.raises(ValueError):
        EnforcementDevelopment(summary="x", source_url="ftp://nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enforcement_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'EnforcementDevelopment'`.

- [ ] **Step 3: Add the model**

In `src/zwiadbrain/models.py`, add `EnforcementDevelopment` immediately before `class EnforcementAction(WikiItem):`, reusing the existing `_HttpUrlStr`:

```python
class EnforcementDevelopment(BaseModel):
    """A single development in an enforcement matter (complaint, order, settlement).

    Matters accrue developments over time as agencies publish new feed items about
    the same case. Persisted to frontmatter (it cannot be re-derived) AND rendered
    into the page body — the same treatment leg_history research gets (D40).
    """

    date: dt.date | None = None
    summary: str
    source_url: _HttpUrlStr
```

Then add the field to `EnforcementAction` (after `significance`):

```python
    significance: str | None = None
    # Append-only list of feed-item developments; persisted to frontmatter (source of
    # truth) and rendered as the "Developments" timeline section (D52).
    developments: list["EnforcementDevelopment"] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enforcement_models.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/models.py tests/test_enforcement_models.py
git commit -m "feat(models): add EnforcementDevelopment + EnforcementAction.developments"
```

---

## Task 2: Template — "Developments" section + frontmatter round-trip

**Files:**
- Modify: `src/zwiadbrain/wiki/templates.py`
- Test: `tests/test_render.py` (append), `tests/test_schema.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render.py`:

```python
def test_enforcement_body_renders_developments_in_stable_order() -> None:
    import datetime as dt
    from zwiadbrain.models import EnforcementAction, EnforcementDevelopment
    from zwiadbrain.wiki.templates import render_enforcement_body

    action = EnforcementAction(
        id="ftc-c-4790", jurisdiction="US", title="FTC v. Acme", agency="FTC",
        summary="Data-security action.",
        developments=[
            EnforcementDevelopment(date=dt.date(2025, 6, 1), summary="Final order.",
                                   source_url="https://www.ftc.gov/b"),
            EnforcementDevelopment(date=dt.date(2025, 1, 2), summary="Complaint filed.",
                                   source_url="https://www.ftc.gov/a"),
        ],
    )
    body = render_enforcement_body(action)
    assert "## Developments" in body
    # Sorted by (date, source_url): complaint (Jan) before order (Jun).
    assert body.index("Complaint filed.") < body.index("Final order.")
    assert "- 2025-01-02 — Complaint filed. — [source](https://www.ftc.gov/a)" in body


def test_enforcement_body_skips_development_without_source_url_noop() -> None:
    # A development always has a source_url (model-required); confirm the section is
    # omitted entirely when there are no developments.
    from zwiadbrain.models import EnforcementAction
    from zwiadbrain.wiki.templates import render_enforcement_body
    action = EnforcementAction(id="ftc-x", jurisdiction="US", title="t", agency="FTC")
    assert "## Developments" not in render_enforcement_body(action)
```

Append to `tests/test_schema.py`:

```python
def test_enforcement_developments_round_trip() -> None:
    import datetime as dt
    from zwiadbrain.models import EnforcementAction, EnforcementDevelopment
    from zwiadbrain.wiki.schema import from_page
    from zwiadbrain.pipeline.render import render_page

    action = EnforcementAction(
        id="ftc-c-4790", jurisdiction="US", title="FTC v. Acme", agency="FTC",
        topics=["privacy"],
        developments=[EnforcementDevelopment(
            date=dt.date(2025, 1, 2), summary="Complaint filed.",
            source_url="https://www.ftc.gov/a")],
    )
    text = render_page(action)
    parsed = from_page(text)
    assert isinstance(parsed, EnforcementAction)
    assert parsed.developments == action.developments
    # Byte-identical re-render (D20).
    assert render_page(parsed) == text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_render.py -k developments tests/test_schema.py -k developments -v`
Expected: FAIL — no `## Developments` heading rendered.

- [ ] **Step 3: Add a `_developments` helper and wire it into `render_enforcement_body`**

In `src/zwiadbrain/wiki/templates.py`, add `EnforcementDevelopment` to the model import block, then add this helper near `_text_versions`:

```python
def _developments(developments: list[EnforcementDevelopment]) -> str:
    """Render the matter timeline; skip any entry without a source_url (not verifiable)."""
    ordered = sorted(
        developments,
        key=lambda d: (d.date or dt.date.min, str(d.source_url)),
    )
    lines: list[str] = []
    for d in ordered:
        if not d.source_url:
            continue
        date = f"{d.date.isoformat()} — " if d.date else ""
        lines.append(f"- {date}{d.summary} — [source]({d.source_url})")
    return "\n".join(lines)
```

Add `import datetime as dt` at the top of the file if not present (it currently imports only `re` and `jinja2`).

In `render_enforcement_body`, insert the Developments section between Summary and Background:

```python
    prose: list[tuple[str, str | None]] = [
        ("Summary", action.summary),
    ]
    for heading, value in prose:
        if value:
            sections.append({"heading": heading, "body": value.strip()})
    if action.developments:
        sections.append({"heading": "Developments", "body": _developments(action.developments)})
    rest: list[tuple[str, str | None]] = [
        ("Background", action.background),
        ("Allegations", action.allegations),
        ("Outcome", action.outcome),
        ("Significance", action.significance),
    ]
    for heading, value in rest:
        if value:
            sections.append({"heading": heading, "body": value.strip()})
```

(Replace the existing single `prose` loop accordingly; the Commentary and Sources tail stays unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_render.py tests/test_schema.py -v`
Expected: PASS (including the new tests; existing render/schema tests still green).

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/wiki/templates.py tests/test_render.py tests/test_schema.py
git commit -m "feat(wiki): render enforcement Developments timeline; round-trips to frontmatter"
```

---

## Task 3: ids — `parse_strong_key` + `build_enforcement_id`

**Files:**
- Modify: `src/zwiadbrain/pipeline/ids.py`
- Test: `tests/test_enforcement_id.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_enforcement_id.py
import pytest

from zwiadbrain.pipeline.ids import build_enforcement_id, parse_strong_key


@pytest.mark.parametrize("text,expected", [
    ("In FTC v. Acme, No. 2:25-cv-12295 (N.D. Cal.)", "2-25-cv-12295"),
    ("FTC Matter, Docket No. C-4790", "c-4790"),
    ("Administrative Docket D-9447 issued", "d-9447"),
    ('FTC, File No. 2023155, announced', "2023155"),
    ("No identifiers in this press release at all.", None),
])
def test_parse_strong_key(text: str, expected: str | None) -> None:
    assert parse_strong_key(text) == expected


def test_parse_strong_key_prefers_court_docket_over_file_number() -> None:
    text = "FTC v. Acme, No. 2:25-cv-12295; File No. 2023155"
    assert parse_strong_key(text) == "2-25-cv-12295"


def test_build_enforcement_id_with_strong_key() -> None:
    assert build_enforcement_id("ftc", strong_key="c-4790", respondent="Acme", year=2025) == "ftc-c-4790"
    assert build_enforcement_id("ca-oag", strong_key="2:25-cv-12295",
                                respondent="Acme", year=2025) == "ca-oag-2-25-cv-12295"


def test_build_enforcement_id_fallback_respondent_year() -> None:
    assert build_enforcement_id("ftc", strong_key=None, respondent="Acme Data Brokers, Inc.",
                                year=2025) == "ftc-2025-acme-data-brokers"


def test_build_enforcement_id_disambiguates_collision() -> None:
    existing = {"ftc-2025-acme"}
    assert build_enforcement_id("ftc", strong_key=None, respondent="Acme", year=2025,
                                existing_ids=existing) == "ftc-2025-acme-2"


def test_enforcement_id_never_collides_with_bill_ids() -> None:
    eid = build_enforcement_id("ca-oag", strong_key=None, respondent="DoorDash", year=2025)
    assert eid == "ca-oag-2025-doordash"
    assert eid != "ca-2025-sb-53"  # state bill id shape; second segment differs (oag vs year)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_enforcement_id.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_strong_key'`.

- [ ] **Step 3: Implement in `ids.py`**

Append to `src/zwiadbrain/pipeline/ids.py` (`import re` is already at the top):

```python
# Strong matter identifiers, tried highest-confidence first. Court dockets and FTC
# administrative dockets are unambiguous; the bare 7-digit FTC file number is the
# weakest (restricted to a "File No." context to avoid matching ZIPs/phone numbers).
_COURT_DOCKET_RE = re.compile(r"\b(\d{1,2}):(\d{2})-([a-z]{2,3})-(\d{3,6})\b", re.IGNORECASE)
_FTC_DOCKET_RE = re.compile(r"\b([CD])-(\d{3,4})\b")
_FTC_FILE_RE = re.compile(r"\bFile\s+No\.?\s*(\d{3}\s?\d{4})\b", re.IGNORECASE)


def parse_strong_key(text: str) -> str | None:
    """Extract a deterministic strong matter identifier from *text*, or None.

    Returns a lowercased, hyphen-normalized key suitable for an id segment:
    court docket ``2:25-cv-12295`` -> ``2-25-cv-12295``; FTC docket ``C-4790`` ->
    ``c-4790``; FTC file number ``2023155`` -> ``2023155``. None when nothing matches
    (the LLM-matcher path). Court dockets win over file numbers when both appear.
    """
    court = _COURT_DOCKET_RE.search(text)
    if court is not None:
        return "-".join(g.lower() for g in court.groups())
    ftc = _FTC_DOCKET_RE.search(text)
    if ftc is not None:
        return f"{ftc.group(1).lower()}-{ftc.group(2)}"
    file_no = _FTC_FILE_RE.search(text)
    if file_no is not None:
        return file_no.group(1).replace(" ", "")
    return None


def _slug(value: str) -> str:
    """Lowercase, keep alphanumerics, collapse runs of other chars to single hyphens."""
    out = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return out or "unknown"


def build_enforcement_id(
    agency_slug: str,
    *,
    strong_key: str | None,
    respondent: str | None,
    year: int,
    existing_ids: frozenset[str] | set[str] = frozenset(),
) -> str:
    """Build a matter-stable, globally-unique enforcement page id (D53).

    With a strong key: ``{agency_slug}-{slug(strong_key)}``. Without: ``{agency_slug}-
    {year}-{slug(respondent)}``, with a numeric suffix appended on collision against
    *existing_ids* (two no-docket actions vs the same respondent in one year).
    """
    if strong_key:
        return f"{_slug(agency_slug)}-{_slug(strong_key)}"
    base = f"{_slug(agency_slug)}-{year}-{_slug(respondent or 'unknown')}"
    if base not in existing_ids:
        return base
    n = 2
    while f"{base}-{n}" in existing_ids:
        n += 1
    return f"{base}-{n}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_enforcement_id.py -v`
Expected: PASS (all parametrized + named cases).

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/pipeline/ids.py tests/test_enforcement_id.py
git commit -m "feat(ids): parse_strong_key + build_enforcement_id for matter-stable ids"
```

---

## Task 4: `pipeline/enforcement.py` — pure matching/confirm/merge

**Files:**
- Create: `src/zwiadbrain/pipeline/enforcement.py`
- Test: `tests/test_enforcement_matching.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_enforcement_matching.py
import datetime as dt

from zwiadbrain.models import EnforcementAction, EnforcementDevelopment
from zwiadbrain.pipeline.enforcement import (
    MatterRef,
    build_shortlist,
    confirm_match,
    merge_current_state,
    merge_developments,
    respondent_overlap,
)


def test_respondent_overlap_folds_suffixes_and_punctuation() -> None:
    assert respondent_overlap("Acme, Inc.", "Acme Corporation") >= 0.5
    assert respondent_overlap("Acme Health LLC", "Acme Data Co.") < 0.5


def test_build_shortlist_filters_by_agency_overlap_and_window() -> None:
    matters = [
        MatterRef(id="ftc-2025-acme", agency_slug="ftc", jurisdiction="US",
                  respondent="Acme, Inc.", date_filed=dt.date(2025, 1, 1)),
        MatterRef(id="ftc-2025-other", agency_slug="ftc", jurisdiction="US",
                  respondent="Globex LLC", date_filed=dt.date(2025, 1, 1)),
        MatterRef(id="ca-oag-2025-acme", agency_slug="ca-oag", jurisdiction="US-CA",
                  respondent="Acme, Inc.", date_filed=dt.date(2025, 1, 1)),
    ]
    short = build_shortlist(
        agency_slug="ftc", respondent="Acme Corporation", date=dt.date(2025, 3, 1),
        matters=matters, window_days=120,
    )
    assert [m.id for m in short] == ["ftc-2025-acme"]  # same agency, overlap, in-window


def test_confirm_match_accepts_overlap_window_and_confidence() -> None:
    assert confirm_match(
        item_respondent="Acme Corporation", item_date=dt.date(2025, 3, 1),
        candidate_respondent="Acme, Inc.", candidate_date=dt.date(2025, 1, 1),
        confidence=0.9, min_confidence=0.75, window_days=120,
    ) is True


def test_confirm_match_rejects_on_respondent_mismatch() -> None:
    assert confirm_match(
        item_respondent="Globex", item_date=dt.date(2025, 3, 1),
        candidate_respondent="Acme, Inc.", candidate_date=dt.date(2025, 1, 1),
        confidence=0.99, min_confidence=0.75, window_days=120,
    ) is False


def test_confirm_match_rejects_out_of_window_and_low_confidence() -> None:
    assert confirm_match(
        item_respondent="Acme", item_date=dt.date(2025, 12, 1),
        candidate_respondent="Acme", candidate_date=dt.date(2025, 1, 1),
        confidence=0.9, min_confidence=0.75, window_days=120,
    ) is False
    assert confirm_match(
        item_respondent="Acme", item_date=dt.date(2025, 2, 1),
        candidate_respondent="Acme", candidate_date=dt.date(2025, 1, 1),
        confidence=0.5, min_confidence=0.75, window_days=120,
    ) is False


def test_merge_developments_dedups_by_source_url_and_sorts() -> None:
    existing = [EnforcementDevelopment(date=dt.date(2025, 1, 2), summary="Complaint.",
                                       source_url="https://x/a")]
    same = EnforcementDevelopment(date=dt.date(2025, 1, 2), summary="Complaint (re-seen).",
                                  source_url="https://x/a")
    new = EnforcementDevelopment(date=dt.date(2025, 6, 1), summary="Order.",
                                 source_url="https://x/b")
    # Re-seen url is a no-op (dedup keeps the existing entry).
    assert merge_developments(existing, same) == existing
    merged = merge_developments(existing, new)
    assert [d.summary for d in merged] == ["Complaint.", "Order."]


def test_merge_current_state_is_monotonic() -> None:
    existing = EnforcementAction(id="ftc-c-1", jurisdiction="US", title="t", agency="FTC",
                                 status="filed", penalties=None)
    updated = merge_current_state(
        existing, status="settled", date_resolved=dt.date(2025, 6, 1),
        penalties="$5M", outcome="Consent order.", significance=None,
    )
    assert updated.status == "settled"
    assert updated.penalties == "$5M"
    # A null new field never blanks an existing value.
    existing2 = merge_current_state(updated, status=None, date_resolved=None,
                                    penalties=None, outcome=None, significance=None)
    assert existing2.status == "settled"
    assert existing2.penalties == "$5M"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_enforcement_matching.py -v`
Expected: FAIL — module `zwiadbrain.pipeline.enforcement` does not exist.

- [ ] **Step 3: Implement `pipeline/enforcement.py`**

```python
"""Pure matching/confirm/merge helpers for enforcement-matter consolidation.

Nothing here does I/O. The CLI render half composes these with the renderer to decide
new-vs-consolidate and to fold a new feed item into an existing matter idempotently.
The deterministic confirm here is the trust boundary that grounds the LLM matcher's
proposal (D53), mirroring how render-leg-history re-checks the verifier in Python.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from zwiadbrain.models import EnforcementAction, EnforcementDevelopment

# Tokens dropped from a respondent name before overlap scoring (corporate suffixes /
# noise), so "Acme, Inc." and "Acme Corporation" compare as the same entity.
_STOPWORDS: frozenset[str] = frozenset(
    {"inc", "incorporated", "llc", "llp", "lp", "co", "corp", "corporation",
     "company", "ltd", "limited", "the", "and", "of"}
)


class MatterRef(BaseModel):
    """A lightweight reference to an existing tracked matter (matters.json entry)."""

    id: str
    agency_slug: str
    jurisdiction: str
    respondent: str | None = None
    date_filed: dt.date | None = None
    strong_key: str | None = None


def _tokens(name: str | None) -> frozenset[str]:
    raw = (name or "").lower().replace(",", " ").replace(".", " ")
    return frozenset(t for t in raw.split() if t and t not in _STOPWORDS)


def respondent_overlap(a: str | None, b: str | None) -> float:
    """Jaccard overlap of significant tokens in two respondent names (0.0–1.0)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _within(d1: dt.date | None, d2: dt.date | None, window_days: int) -> bool:
    if d1 is None or d2 is None:
        return True  # unknown date never *blocks* a match; respondent + key carry it
    return abs((d1 - d2).days) <= window_days


def build_shortlist(
    *,
    agency_slug: str,
    respondent: str | None,
    date: dt.date | None,
    matters: list[MatterRef],
    window_days: int,
    overlap_floor: float = 0.34,
) -> list[MatterRef]:
    """Candidate existing matters for the LLM matcher: same agency, overlapping
    respondent, date within the window. Sorted by descending respondent overlap."""
    scored = [
        (respondent_overlap(respondent, m.respondent), m)
        for m in matters
        if m.agency_slug == agency_slug and _within(date, m.date_filed, window_days)
    ]
    return [m for score, m in sorted(scored, key=lambda s: -s[0]) if score >= overlap_floor]


def confirm_match(
    *,
    item_respondent: str | None,
    item_date: dt.date | None,
    candidate_respondent: str | None,
    candidate_date: dt.date | None,
    confidence: float,
    min_confidence: float,
    window_days: int,
    overlap_floor: float = 0.34,
) -> bool:
    """Deterministic grounding of an LLM-proposed match (D53). All three must hold:
    confidence floor, respondent token overlap, and date proximity."""
    return (
        confidence >= min_confidence
        and respondent_overlap(item_respondent, candidate_respondent) >= overlap_floor
        and _within(item_date, candidate_date, window_days)
    )


def merge_developments(
    existing: list[EnforcementDevelopment], new: EnforcementDevelopment
) -> list[EnforcementDevelopment]:
    """Append *new* to *existing*, deduped by source_url, sorted by (date, source_url).

    Re-seeing the same source_url is a no-op (returns the existing list unchanged), so a
    repeated scan is idempotent.
    """
    if any(str(d.source_url) == str(new.source_url) for d in existing):
        return existing
    combined = [*existing, new]
    return sorted(combined, key=lambda d: (d.date or dt.date.min, str(d.source_url)))


def merge_current_state(
    existing: EnforcementAction,
    *,
    status: str | None,
    date_resolved: dt.date | None,
    penalties: str | None,
    outcome: str | None,
    significance: str | None,
) -> EnforcementAction:
    """Return a copy of *existing* with non-null new values applied (monotonic): a null
    new field never blanks an existing value."""
    updates: dict[str, object] = {}
    for field, value in (
        ("status", status), ("date_resolved", date_resolved),
        ("penalties", penalties), ("outcome", outcome), ("significance", significance),
    ):
        if value is not None:
            updates[field] = value
    return existing.model_copy(update=updates)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_enforcement_matching.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/pipeline/enforcement.py tests/test_enforcement_matching.py
git commit -m "feat(pipeline): pure enforcement matching/confirm/merge helpers"
```

---

## Task 5: `EnforcementSource` protocol + shared parsing helpers

**Files:**
- Create: `src/zwiadbrain/sources/enforcement/base.py`
- Test: `tests/test_enforcement_sources.py` (new — base helpers section)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_enforcement_sources.py
from zwiadbrain.sources.enforcement.base import EnforcementCandidate, extract_article_text, parse_feed


def test_parse_feed_extracts_entries() -> None:
    xml = """<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>FTC sues Acme</title><link>https://www.ftc.gov/a</link>
        <description>data security</description>
        <pubDate>Thu, 02 Jan 2025 10:00:00 GMT</pubDate></item>
    </channel></rss>"""
    entries = parse_feed(xml)
    assert entries[0]["title"] == "FTC sues Acme"
    assert entries[0]["link"] == "https://www.ftc.gov/a"
    assert entries[0]["published"].isoformat() == "2025-01-02"


def test_extract_article_text_strips_script_and_nav() -> None:
    html = """<html><head><style>x{}</style></head><body>
      <nav>menu</nav><main><p>The FTC alleged Acme failed to secure data.</p>
      <script>tracker()</script></main></body></html>"""
    text = extract_article_text(html)
    assert "FTC alleged Acme" in text
    assert "tracker()" not in text
    assert "menu" not in text


def test_candidate_defaults() -> None:
    c = EnforcementCandidate(source="ftc", agency="FTC", agency_slug="ftc",
                             jurisdiction="US", title="t", url="https://x")
    assert c.text is None and c.published is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_enforcement_sources.py -k "parse_feed or article or candidate_defaults" -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement `base.py`**

```python
"""The enforcement-source abstraction + shared feed/HTML parsing.

An :class:`EnforcementSource` discovers lightweight :class:`EnforcementCandidate`
records from an agency feed (forward-from-now) and fetches the readable article text
behind each. Enforcement returns enforcement-shaped data, so it does NOT reuse the bill
``Source`` protocol (whose ``fetch`` returns a ``Bill``).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Protocol, runtime_checkable

import feedparser
from bs4 import BeautifulSoup
from pydantic import BaseModel


class EnforcementCandidate(BaseModel):
    """A discovered enforcement item before classification/extraction."""

    source: str
    agency: str
    agency_slug: str
    jurisdiction: str
    title: str
    url: str
    published: dt.date | None = None
    raw: dict[str, object] = {}
    text: str | None = None


@runtime_checkable
class EnforcementSource(Protocol):
    """Structural contract every enforcement source implements."""

    name: str

    def discover(
        self, *, since: dt.datetime | None = None, limit: int = 20
    ) -> list[EnforcementCandidate]:
        """Surface up to ``limit`` candidates published since ``since`` (newest first)."""
        ...

    def fetch_text(self, candidate: EnforcementCandidate) -> str:
        """Follow ``candidate.url`` and return the readable article body text."""
        ...


def _entry_date(entry: Any) -> dt.date | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is not None:
        return dt.date(parsed.tm_year, parsed.tm_mon, parsed.tm_mday)
    return None


def parse_feed(content: str) -> list[dict[str, object]]:
    """Parse an RSS/Atom feed string into normalized entry dicts (newest first as given)."""
    feed = feedparser.parse(content)
    out: list[dict[str, object]] = []
    for entry in feed.entries:
        link = entry.get("link") or ""
        if not link:
            continue
        out.append(
            {
                "title": entry.get("title", "").strip(),
                "link": link,
                "summary": entry.get("summary", "") or entry.get("description", ""),
                "published": _entry_date(entry),
            }
        )
    return out


def extract_article_text(html: str) -> str:
    """Extract readable body text from a press-release page, dropping boilerplate."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "form", "aside"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return main.get_text(" ", strip=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_enforcement_sources.py -k "parse_feed or article or candidate_defaults" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/sources/enforcement/base.py tests/test_enforcement_sources.py
git commit -m "feat(sources): EnforcementSource protocol + shared feed/HTML parsing"
```

---

## Task 6: `FTCSource`

**Files:**
- Create: `src/zwiadbrain/sources/enforcement/ftc.py`
- Create: `tests/fixtures/enforcement/ftc_press_rss.xml`, `tests/fixtures/enforcement/ftc_press.html`
- Test: `tests/test_enforcement_sources.py` (append)

- [ ] **Step 1: Create fixtures**

`tests/fixtures/enforcement/ftc_press_rss.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>FTC Press Releases</title>
  <item>
    <title>FTC Takes Action Against Acme Over Data Security Failures</title>
    <link>https://www.ftc.gov/news/press-releases/2025/01/acme</link>
    <description>The FTC alleged Acme failed to secure consumer data.</description>
    <pubDate>Thu, 02 Jan 2025 10:00:00 GMT</pubDate>
  </item>
  <item>
    <title>FTC Finalizes Order Against Globex for Deceptive AI Claims</title>
    <link>https://www.ftc.gov/news/press-releases/2025/03/globex</link>
    <description>Final order entered in Docket No. C-4790.</description>
    <pubDate>Mon, 03 Mar 2025 10:00:00 GMT</pubDate>
  </item>
</channel></rss>
```

`tests/fixtures/enforcement/ftc_press.html`:

```html
<html><head><style>.x{}</style></head><body><nav>menu</nav>
<main><h1>FTC Takes Action Against Acme</h1>
<p>The Federal Trade Commission alleged that Acme, Inc. failed to implement reasonable
data security, exposing consumer personal information. File No. 2023155.</p>
<script>analytics()</script></main></body></html>
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_enforcement_sources.py`:

```python
from pathlib import Path

import httpx
import respx

from zwiadbrain.sources.enforcement.ftc import FTCSource

_FIX = Path(__file__).parent / "fixtures" / "enforcement"
_RSS_URL = "https://www.ftc.gov/feeds/press-release.xml"


@respx.mock
def test_ftc_discover_maps_candidates() -> None:
    respx.get(_RSS_URL).mock(
        return_value=httpx.Response(200, text=(_FIX / "ftc_press_rss.xml").read_text())
    )
    source = FTCSource(_RSS_URL)
    cands = source.discover(limit=10)
    assert cands[0].agency_slug == "ftc" and cands[0].jurisdiction == "US"
    assert cands[0].title.startswith("FTC Takes Action Against Acme")
    assert cands[0].published is not None and cands[0].published.year == 2025


@respx.mock
def test_ftc_discover_forward_from_now_window() -> None:
    import datetime as dt
    respx.get(_RSS_URL).mock(
        return_value=httpx.Response(200, text=(_FIX / "ftc_press_rss.xml").read_text())
    )
    source = FTCSource(_RSS_URL)
    # since cutoff after the Jan item, before the Mar item -> only the Mar item.
    cands = source.discover(since=dt.datetime(2025, 2, 1), limit=10)
    assert [c.published.month for c in cands] == [3]


@respx.mock
def test_ftc_fetch_text_extracts_body() -> None:
    from zwiadbrain.sources.enforcement.base import EnforcementCandidate
    url = "https://www.ftc.gov/news/press-releases/2025/01/acme"
    respx.get(url).mock(return_value=httpx.Response(200, text=(_FIX / "ftc_press.html").read_text()))
    source = FTCSource(_RSS_URL)
    cand = EnforcementCandidate(source="ftc", agency="FTC", agency_slug="ftc",
                                jurisdiction="US", title="t", url=url)
    text = source.fetch_text(cand)
    assert "Acme, Inc. failed to implement reasonable data security" in text
    assert "File No. 2023155" in text
    assert "analytics()" not in text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_enforcement_sources.py -k ftc -v`
Expected: FAIL — `FTCSource` does not exist.

- [ ] **Step 4: Implement `ftc.py`**

```python
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
            published = entry["published"]
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_enforcement_sources.py -k ftc -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/zwiadbrain/sources/enforcement/ftc.py tests/test_enforcement_sources.py tests/fixtures/enforcement/ftc_press_rss.xml tests/fixtures/enforcement/ftc_press.html
git commit -m "feat(sources): FTCSource — press-release RSS discovery + article fetch"
```

---

## Task 7: generic `StateAGSource` (rss | html) + failure isolation

**Files:**
- Create: `src/zwiadbrain/sources/enforcement/state_ag.py`
- Create: `tests/fixtures/enforcement/ag_ca_rss.xml`, `ag_html_list.html`, `ag_press.html`
- Test: `tests/test_enforcement_sources.py` (append)

- [ ] **Step 1: Create fixtures**

`tests/fixtures/enforcement/ag_ca_rss.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>CA OAG</title>
  <item><title>Attorney General Announces Settlement With DoorDash Over CCPA</title>
    <link>https://oag.ca.gov/news/press-releases/doordash</link>
    <description>Settlement resolves data-sharing allegations.</description>
    <pubDate>Wed, 15 Jan 2025 10:00:00 GMT</pubDate></item>
</channel></rss>
```

`tests/fixtures/enforcement/ag_html_list.html`:
```html
<html><body><ul class="press-list">
  <li class="press-item"><a href="/news/2025/sephora">AG Sues Sephora Over Data Broker Violations</a>
    <time datetime="2025-02-10">Feb 10, 2025</time></li>
  <li class="press-item"><a href="https://oag.example/news/2025/other">Unrelated Highway Press Release</a>
    <time datetime="2025-02-11">Feb 11, 2025</time></li>
</ul></body></html>
```

`tests/fixtures/enforcement/ag_press.html`:
```html
<html><body><main><h1>AG Sues Sephora</h1>
<p>The Attorney General alleged Sephora violated the CCPA by failing to honor
opt-out requests. No. 2:25-cv-99999.</p></main></body></html>
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_enforcement_sources.py`:

```python
from zwiadbrain.sources.enforcement.state_ag import StateAGSource


@respx.mock
def test_state_ag_rss_discover() -> None:
    url = "https://oag.ca.gov/news/press-releases/feed"
    respx.get(url).mock(return_value=httpx.Response(200, text=(_FIX / "ag_ca_rss.xml").read_text()))
    source = StateAGSource(name="California OAG", agency_slug="ca-oag",
                           jurisdiction="US-CA", url=url, kind="rss")
    cands = source.discover(limit=10)
    assert cands[0].agency == "California OAG" and cands[0].jurisdiction == "US-CA"
    assert "DoorDash" in cands[0].title


@respx.mock
def test_state_ag_html_discover_uses_item_selector() -> None:
    url = "https://oag.example/news"
    respx.get(url).mock(return_value=httpx.Response(200, text=(_FIX / "ag_html_list.html").read_text()))
    source = StateAGSource(name="Example OAG", agency_slug="ex-oag", jurisdiction="US-XX",
                           url=url, kind="html", item_selector="li.press-item a")
    cands = source.discover(limit=10)
    titles = [c.title for c in cands]
    assert "AG Sues Sephora Over Data Broker Violations" in titles
    # Relative link resolved against the base url.
    assert cands[0].url.startswith("https://oag.example/news/2025/sephora")


@respx.mock
def test_state_ag_discover_failure_is_isolated() -> None:
    url = "https://oag.broken/news"
    respx.get(url).mock(return_value=httpx.Response(500))
    source = StateAGSource(name="Broken OAG", agency_slug="bk-oag", jurisdiction="US-XX",
                           url=url, kind="html", item_selector="a")
    # One broken source returns [] (logged), never raises — the multi-agency loop survives.
    assert source.discover(limit=10) == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_enforcement_sources.py -k state_ag -v`
Expected: FAIL — `StateAGSource` does not exist.

- [ ] **Step 4: Implement `state_ag.py`**

```python
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

from zwiadbrain.sources.enforcement.base import (
    EnforcementCandidate,
    extract_article_text,
    parse_feed,
)

_LOGGER = logging.getLogger(__name__)


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
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def _candidate(self, title: str, link: str, published: dt.date | None) -> EnforcementCandidate:
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
        return [self._candidate(str(e["title"]), str(e["link"]), e["published"])  # type: ignore[arg-type]
                for e in parse_feed(text)]

    def _discover_html(self) -> list[EnforcementCandidate]:
        if not self.item_selector:
            _LOGGER.warning("state_ag %s kind=html with empty item_selector", self.agency_slug)
            return []
        html = self.client.get(self.url).raise_for_status().text
        soup = BeautifulSoup(html, "html.parser")
        out: list[EnforcementCandidate] = []
        for el in soup.select(self.item_selector):
            href = el.get("href")
            if not href:
                continue
            time_el = el.find_next("time")
            published: dt.date | None = None
            if time_el is not None and time_el.get("datetime"):
                try:
                    published = dt.date.fromisoformat(str(time_el["datetime"])[:10])
                except ValueError:
                    published = None
            out.append(self._candidate(el.get_text(strip=True), str(href), published))
        return out

    def discover(
        self, *, since: dt.datetime | None = None, limit: int = 20
    ) -> list[EnforcementCandidate]:
        cutoff = since.date() if since is not None else None
        try:
            cands = self._discover_rss() if self.kind == "rss" else self._discover_html()
        except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
            _LOGGER.warning("state_ag %s discover failed (isolated): %s", self.agency_slug, exc)
            return []
        out: list[EnforcementCandidate] = []
        for cand in cands:
            if cutoff is not None and cand.published is not None and cand.published < cutoff:
                continue
            out.append(cand)
            if len(out) >= limit:
                break
        return out

    def fetch_text(self, candidate: EnforcementCandidate) -> str:
        return extract_article_text(self.client.get(candidate.url).raise_for_status().text)
```

> NOTE: `raise_for_status()` returns the response in httpx, so `.text` chaining works; a 5xx therefore raises `httpx.HTTPStatusError` (an `HTTPError` subclass), which `discover` catches and isolates.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_enforcement_sources.py -k state_ag -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/zwiadbrain/sources/enforcement/state_ag.py tests/test_enforcement_sources.py tests/fixtures/enforcement/ag_ca_rss.xml tests/fixtures/enforcement/ag_html_list.html tests/fixtures/enforcement/ag_press.html
git commit -m "feat(sources): generic config-driven StateAGSource (rss|html) with failure isolation"
```

---

## Task 8: config — `EnforcementSettings` + `zwiadbrain.toml`

**Files:**
- Modify: `src/zwiadbrain/config.py`
- Modify: `zwiadbrain.toml`
- Test: `tests/test_config.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_enforcement_settings_loaded_from_toml(tmp_path) -> None:
    from zwiadbrain.config import load_settings
    toml = tmp_path / "zwiadbrain.toml"
    toml.write_text(
        "[enforcement]\n"
        "enabled = true\n"
        "lookback_days = 45\n"
        "min_confidence = 0.8\n"
        "match_window_days = 90\n"
        "[enforcement.ftc]\n"
        'rss_url = "https://www.ftc.gov/feeds/press-release.xml"\n'
        "enabled = true\n"
        "[[enforcement.state_ag]]\n"
        'name = "California OAG"\n'
        'agency_slug = "ca-oag"\n'
        'jurisdiction = "US-CA"\n'
        'url = "https://oag.ca.gov/news/press-releases/feed"\n'
        'kind = "rss"\n'
        "enabled = true\n",
        encoding="utf-8",
    )
    settings = load_settings(toml_path=toml, env_file=tmp_path / ".env")
    assert settings.enforcement.lookback_days == 45
    assert settings.enforcement.min_confidence == 0.8
    assert settings.enforcement.ftc.rss_url.endswith("press-release.xml")
    assert settings.enforcement.state_ag[0].agency_slug == "ca-oag"
    assert settings.enforcement.enabled_state_ags()[0].kind == "rss"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -k enforcement -v`
Expected: FAIL — `Settings` has no `enforcement` attribute.

- [ ] **Step 3: Implement the config models**

In `src/zwiadbrain/config.py`, add these models after `StatesSettings`:

```python
class FTCSettings(BaseModel):
    """FTC source config (see ``[enforcement.ftc]``)."""

    enabled: bool = True
    rss_url: str = "https://www.ftc.gov/feeds/press-release.xml"


class StateAGSource(BaseModel):
    """A single config-driven state-AG source (see ``[[enforcement.state_ag]]``)."""

    name: str
    agency_slug: str
    jurisdiction: str
    url: str
    kind: str = "rss"            # "rss" | "html"
    item_selector: str = ""      # CSS selector when kind == "html"
    enabled: bool = True


class EnforcementSettings(BaseModel):
    """Enforcement tracking config (see ``[enforcement]``)."""

    enabled: bool = False
    lookback_days: int = 30
    min_confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.75
    match_window_days: int = 120
    ftc: FTCSettings = FTCSettings()
    state_ag: list[StateAGSource] = []

    def enabled_state_ags(self) -> list[StateAGSource]:
        """The state-AG sources with ``enabled = true``."""
        return [ag for ag in self.state_ag if ag.enabled]
```

Add the field to `Settings` (after `states`):

```python
    states: StatesSettings = StatesSettings()
    enforcement: EnforcementSettings = EnforcementSettings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -k enforcement -v`
Expected: PASS.

- [ ] **Step 5: Update `zwiadbrain.toml`**

Replace the commented `[[enforcement.state_ag]]` stub with the real block (FTC + 7 priority AGs). For AGs without a verified RSS feed, leave `kind = "html"` with a best-guess `item_selector` to be tuned in UAT (T15):

```toml
[enforcement]
enabled = true
lookback_days = 30
min_confidence = 0.75
match_window_days = 120

[enforcement.ftc]
enabled = true
rss_url = "https://www.ftc.gov/feeds/press-release.xml"   # validated in UAT (T15)

[[enforcement.state_ag]]
name = "California OAG"
agency_slug = "ca-oag"
jurisdiction = "US-CA"
url = "https://oag.ca.gov/news/press-releases/feed"
kind = "rss"
enabled = true

# ny, tx, co, va, wa, il: one [[enforcement.state_ag]] entry each. Start kind="html"
# with a placeholder item_selector (enabled = false) until the selector is tuned in UAT;
# flip enabled = true per state as its selector is verified (D54).
[[enforcement.state_ag]]
name = "New York OAG"
agency_slug = "ny-oag"
jurisdiction = "US-NY"
url = "https://ag.ny.gov/press-releases"
kind = "html"
item_selector = ""
enabled = false
# … repeat for tx, co, va, wa, il (enabled = false until tuned)
```

- [ ] **Step 6: Commit**

```bash
git add src/zwiadbrain/config.py zwiadbrain.toml tests/test_config.py
git commit -m "feat(config): EnforcementSettings + FTC/state-AG config entries"
```

---

## Task 9: CLI — `fetch-enforcement-candidates`

**Files:**
- Modify: `src/zwiadbrain/cli.py`
- Test: `tests/test_enforcement_cli.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enforcement_cli.py
import json
from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from zwiadbrain.cli import app

runner = CliRunner()
_FIX = Path(__file__).parent / "fixtures" / "enforcement"


@respx.mock
def test_fetch_enforcement_candidates_stages_candidates_and_matters(tmp_path, monkeypatch) -> None:
    rss = "https://www.ftc.gov/feeds/press-release.xml"
    respx.get(rss).mock(return_value=httpx.Response(200, text=(_FIX / "ftc_press_rss.xml").read_text()))
    respx.get("https://www.ftc.gov/news/press-releases/2025/01/acme").mock(
        return_value=httpx.Response(200, text=(_FIX / "ftc_press.html").read_text()))
    respx.get("https://www.ftc.gov/news/press-releases/2025/03/globex").mock(
        return_value=httpx.Response(200, text="<html><body><main>Docket No. C-4790 order.</main></body></html>"))

    # Point the loader at a minimal config enabling only FTC.
    toml = tmp_path / "zwiadbrain.toml"
    toml.write_text("[enforcement]\nenabled = true\n[enforcement.ftc]\n"
                    f'rss_url = "{rss}"\nenabled = true\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "wiki" / "federal" / "enforcement").mkdir(parents=True)

    out = tmp_path / "run"
    result = runner.invoke(app, ["fetch-enforcement-candidates", "--agency", "ftc",
                                 "--limit", "10", "--out", str(out)])
    assert result.exit_code == 0, result.output
    candidates = json.loads((out / "candidates.json").read_text())
    matters = json.loads((out / "matters.json").read_text())
    assert matters == []  # no existing enforcement pages yet
    # Globex item parsed a strong key from its fetched text.
    globex = next(c for c in candidates if "Globex" in c["title"])
    assert globex["strong_key"] == "c-4790"
    assert globex["text"] and "C-4790" in globex["text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enforcement_cli.py -k fetch_enforcement -v`
Expected: FAIL — no command `fetch-enforcement-candidates`.

- [ ] **Step 3: Implement the command in `cli.py`**

Add imports near the other source/pipeline imports:

```python
from zwiadbrain.models import EnforcementAction
from zwiadbrain.pipeline.enforcement import MatterRef
from zwiadbrain.pipeline.ids import parse_strong_key
from zwiadbrain.sources.enforcement.ftc import FTCSource
from zwiadbrain.sources.enforcement.state_ag import StateAGSource
from zwiadbrain.sources.enforcement.base import EnforcementSource
```

Add a helper to build the enabled sources and a helper to read existing matters:

```python
def _enforcement_sources(settings, agency: str | None) -> list[EnforcementSource]:
    """Build the enabled enforcement sources, optionally filtered to one --agency."""
    sources: list[EnforcementSource] = []
    enf = settings.enforcement
    if enf.ftc.enabled and agency in (None, "ftc"):
        sources.append(FTCSource(enf.ftc.rss_url))
    for ag in enf.enabled_state_ags():
        if agency in (None, ag.agency_slug):
            sources.append(StateAGSource(
                name=ag.name, agency_slug=ag.agency_slug, jurisdiction=ag.jurisdiction,
                url=ag.url, kind=ag.kind, item_selector=ag.item_selector))
    return sources


def _existing_matters(wiki: Path) -> list[MatterRef]:
    """Read every tracked enforcement page into a MatterRef (for matching/shortlists)."""
    matters: list[MatterRef] = []
    for page in sorted(wiki.glob("**/enforcement/*.md")):
        try:
            item = from_page(page.read_text(encoding="utf-8"))
        except (WikiSchemaError, ConfigError):
            continue
        if not isinstance(item, EnforcementAction):
            continue
        matters.append(MatterRef(
            id=item.id, agency_slug=_agency_slug_of(item), jurisdiction=item.jurisdiction,
            respondent=item.respondent, date_filed=item.date_filed, strong_key=item.docket))
    return matters


def _agency_slug_of(item: EnforcementAction) -> str:
    """Derive the agency_slug from a stored matter id (text before the key/year)."""
    # ids are "{agency_slug}-{key}" or "{agency_slug}-{year}-{slug}"; agency_slug is the
    # id prefix up to the first segment that is a 4-digit year or a strong-key fragment.
    parts = item.id.split("-")
    head: list[str] = []
    for p in parts:
        if p.isdigit():  # first numeric segment starts the key/year
            break
        head.append(p)
    return "-".join(head) or item.id
```

> NOTE: `_agency_slug_of` is a deterministic best-effort; matching only ever compares
> `agency_slug` for equality, so as long as construction and parsing agree it is correct.
> An alternative (cleaner) is to persist `agency_slug` explicitly — but the model already
> carries `agency`; deriving from the id avoids a schema change. The id prefix is always
> alpha (`ftc`, `ca-oag`), so the "first numeric segment" rule is unambiguous.

Now the command:

```python
@app.command(name="fetch-enforcement-candidates")
def fetch_enforcement_candidates(
    agency: Annotated[str | None, typer.Option(help="One source: 'ftc' or an AG slug; omit for all.")] = None,
    limit: Annotated[int, typer.Option(min=1, help="Max items per source.")] = 5,
    lookback_days: Annotated[int | None, typer.Option(help="Override config lookback window.")] = None,
    wiki: Annotated[Path, typer.Option(help="Wiki root (for existing matters).")] = Path("wiki"),
    out: Annotated[Path | None, typer.Option(help="Run directory for candidates.json.")] = None,
) -> None:
    """Discover enforcement items (forward-from-now), fetch article text, parse strong
    keys, and stage candidates.json + matters.json for the interactive subagents."""
    try:
        settings = load_settings()
        window = lookback_days if lookback_days is not None else settings.enforcement.lookback_days
        since = dt.datetime.now(dt.UTC) - dt.timedelta(days=window)
        sources = _enforcement_sources(settings, agency)
        matters = _existing_matters(wiki) if wiki.exists() else []
        by_key = {m.strong_key: m.id for m in matters if m.strong_key}
        candidates: list[dict[str, object]] = []
        for source in sources:
            for cand in source.discover(since=since, limit=limit):
                text = source.fetch_text(cand)
                strong_key = parse_strong_key(f"{cand.title}\n{text}")
                matter_id = by_key.get(strong_key) if strong_key else None
                candidates.append({
                    **cand.model_dump(mode="json"),
                    "text": text,
                    "strong_key": strong_key,
                    "matter_id": matter_id,
                    "match_source": "strong_key" if matter_id else None,
                })
        run_dir = stage_json(candidates, name="candidates.json", out=out)
        stage_json([m.model_dump(mode="json") for m in matters], name="matters.json", out=run_dir.parent)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"staged {len(candidates)} enforcement candidate(s) to {run_dir}")
```

> NOTE on `out`: `stage_json` returns the path to the written file inside a run directory.
> matters.json must land in the SAME run dir; verify `stage_json`'s `out` semantics
> (PHASE-07 used `out=run_dir.parent` to co-locate; mirror that exactly — read
> `pipeline/staging.py` first and match the existing co-location pattern used by
> `fetch-state-candidates`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enforcement_cli.py -k fetch_enforcement -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/zwiadbrain/cli.py tests/test_enforcement_cli.py
git commit -m "feat(cli): fetch-enforcement-candidates (discover + text + strong-key + matters)"
```

---

## Task 10: CLI — `render-enforcement` (build/consolidate + deterministic confirm)

**Files:**
- Modify: `src/zwiadbrain/cli.py`
- Test: `tests/test_enforcement_cli.py` (append), `tests/test_enforcement_render.py` (new — consolidation)

- [ ] **Step 1: Write the failing tests**

`tests/test_enforcement_render.py`:

```python
import datetime as dt
import json
from pathlib import Path

from typer.testing import CliRunner

from zwiadbrain.cli import app
from zwiadbrain.wiki.schema import from_page

runner = CliRunner()


def _entry(**over) -> dict:
    base = {
        "matter_id": None, "match_source": "none", "match_confidence": 0.0,
        "agency": "FTC", "agency_slug": "ftc", "jurisdiction": "US",
        "strong_key": "c-4790", "respondent": "Acme, Inc.", "title": "FTC v. Acme",
        "topics": ["privacy"], "summary": "Data-security action.",
        "background": None, "allegations": "Failed to secure data.", "outcome": None,
        "significance": None, "action_type": "complaint", "statutes": ["FTC Act 5"],
        "penalties": None, "status": "filed", "date_filed": "2025-01-02",
        "date_resolved": None,
        "development": {"date": "2025-01-02", "summary": "Complaint filed.",
                        "source_url": "https://www.ftc.gov/a"},
        "source_url": "https://www.ftc.gov/a", "sources": {"FTC": "https://www.ftc.gov/a"},
    }
    base.update(over)
    return base


def test_render_enforcement_new_matter(tmp_path) -> None:
    run = tmp_path / "run"; run.mkdir()
    (run / "classified.json").write_text(json.dumps([_entry()]), encoding="utf-8")
    wiki = tmp_path / "wiki"
    result = runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                                 "--wiki", str(wiki), "--db", str(tmp_path / "i.sqlite")])
    assert result.exit_code == 0, result.output
    page = wiki / "federal" / "enforcement" / "ftc-c-4790.md"
    action = from_page(page.read_text(encoding="utf-8"))
    assert action.id == "ftc-c-4790"
    assert action.developments[0].summary == "Complaint filed."


def test_render_enforcement_strong_key_consolidates(tmp_path) -> None:
    wiki = tmp_path / "wiki"; db = tmp_path / "i.sqlite"
    run = tmp_path / "run"; run.mkdir()
    # First: the complaint (new matter).
    (run / "classified.json").write_text(json.dumps([_entry()]), encoding="utf-8")
    runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                        "--wiki", str(wiki), "--db", str(db)])
    # Second: a settlement, same strong key -> matter_id set -> consolidate.
    settle = _entry(matter_id="ftc-c-4790", match_source="strong_key", status="settled",
                    date_resolved="2025-06-01", penalties="$5M", outcome="Consent order.",
                    title="FTC Finalizes Order Against Acme",
                    development={"date": "2025-06-01", "summary": "Final order.",
                                 "source_url": "https://www.ftc.gov/b"},
                    source_url="https://www.ftc.gov/b", sources={"FTC": "https://www.ftc.gov/b"})
    (run / "classified.json").write_text(json.dumps([settle]), encoding="utf-8")
    runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                        "--wiki", str(wiki), "--db", str(db)])
    page = wiki / "federal" / "enforcement" / "ftc-c-4790.md"
    action = from_page(page.read_text(encoding="utf-8"))
    assert [d.summary for d in action.developments] == ["Complaint filed.", "Final order."]
    assert action.status == "settled" and action.penalties == "$5M"
    assert set(action.sources) == {"FTC"}  # merged (both items share the FTC key)


def test_render_enforcement_llm_match_failing_confirm_becomes_new_page(tmp_path) -> None:
    wiki = tmp_path / "wiki"; db = tmp_path / "i.sqlite"
    run = tmp_path / "run"; run.mkdir()
    # Existing matter for Globex.
    (run / "classified.json").write_text(json.dumps([_entry(
        matter_id=None, strong_key=None, respondent="Globex LLC", title="FTC v. Globex",
        development={"date": "2025-01-02", "summary": "Complaint.", "source_url": "https://x/g1"},
        source_url="https://x/g1", sources={"FTC": "https://x/g1"})]), encoding="utf-8")
    runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                        "--wiki", str(wiki), "--db", str(db)])
    # New item proposes a match to Globex but the respondent is a different company.
    bad = _entry(matter_id="ftc-2025-globex", match_source="llm", match_confidence=0.9,
                 strong_key=None, respondent="Initech Inc.", title="FTC v. Initech",
                 date_filed="2025-02-01",
                 development={"date": "2025-02-01", "summary": "Complaint.", "source_url": "https://x/i1"},
                 source_url="https://x/i1", sources={"FTC": "https://x/i1"})
    (run / "classified.json").write_text(json.dumps([bad]), encoding="utf-8")
    result = runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                                 "--wiki", str(wiki), "--db", str(db)])
    # Failed confirm -> a NEW page for Initech, not folded into Globex.
    assert (wiki / "federal" / "enforcement" / "ftc-2025-initech.md").exists()
    assert "possible-duplicate" in result.output.lower()
```

Append an idempotency test to `tests/test_enforcement_render.py`:

```python
def test_render_enforcement_idempotent(tmp_path) -> None:
    wiki = tmp_path / "wiki"; db = tmp_path / "i.sqlite"
    run = tmp_path / "run"; run.mkdir()
    (run / "classified.json").write_text(json.dumps([_entry()]), encoding="utf-8")
    runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                        "--wiki", str(wiki), "--db", str(db)])
    page = wiki / "federal" / "enforcement" / "ftc-c-4790.md"
    first = page.read_text(encoding="utf-8")
    # Re-run the SAME consolidation entry (matter exists, same source_url) -> no change.
    again = _entry(matter_id="ftc-c-4790", match_source="strong_key")
    (run / "classified.json").write_text(json.dumps([again]), encoding="utf-8")
    runner.invoke(app, ["render-enforcement", "--in", str(run / "classified.json"),
                        "--wiki", str(wiki), "--db", str(db)])
    assert page.read_text(encoding="utf-8") == first  # byte-identical (D20)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_enforcement_render.py -v`
Expected: FAIL — no command `render-enforcement`.

- [ ] **Step 3: Implement `render-enforcement` in `cli.py`**

Add imports:

```python
from zwiadbrain.models import EnforcementDevelopment
from zwiadbrain.pipeline.enforcement import confirm_match, merge_current_state, merge_developments
from zwiadbrain.pipeline.ids import build_enforcement_id
from zwiadbrain.pipeline.render import page_path
```

Add a date-parsing helper and the command:

```python
def _opt_date(value: object) -> dt.date | None:
    if not value:
        return None
    return dt.date.fromisoformat(str(value)[:10])


@app.command(name="render-enforcement")
def render_enforcement(
    input_file: Annotated[Path, typer.Option("--in", help="classified.json to render.")],
    wiki: Annotated[Path, typer.Option(help="Wiki root to write pages under.")] = Path("wiki"),
    db: Annotated[Path, typer.Option(help="SQLite index path.")] = Path("data/cache/index.sqlite"),
    topics: Annotated[Path, typer.Option(help="Relevance taxonomy file.")] = _DEFAULT_TOPICS,
) -> None:
    """Build/consolidate enforcement matters from classified items and render them.

    A strong-key match is trusted; an LLM-proposed match is re-confirmed deterministically
    (D53) and demoted to a new page (with a possible-duplicate note) when the confirm
    fails — never a silent wrong-merge. Consolidation is idempotent (D20).
    """
    try:
        topic_keys = set(load_reference(topics).topic_keys)
        raw: object = json.loads(input_file.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ConfigError(f"classified file must be a JSON list, got {type(raw).__name__}")
        entries: list[object] = list(raw)  # pyright: ignore[reportUnknownArgumentType]
        existing_ids = {m.id for m in (_existing_matters(wiki) if wiki.exists() else [])}
        new_count = consolidated = flagged = 0
        notes: list[str] = []
        settings = load_settings()
        for item in entries:
            if not isinstance(item, dict):
                raise ConfigError("each classified entry must be a JSON object")
            e: dict[str, object] = item  # pyright: ignore[reportUnknownVariableType]
            topics_list = [str(t) for t in (e.get("topics") or [])]
            unknown = [t for t in topics_list if t not in topic_keys]
            if unknown:
                raise ConfigError(f"enforcement item has unknown topic(s): {', '.join(unknown)}")
            development = EnforcementDevelopment.model_validate(e["development"])
            matter_id = e.get("matter_id")
            match_source = str(e.get("match_source") or "none")
            existing_page: EnforcementAction | None = None
            if matter_id:
                page = _enforcement_page_by_id(wiki, str(matter_id))
                if page is not None:
                    loaded = from_page(page.read_text(encoding="utf-8"))
                    if isinstance(loaded, EnforcementAction):
                        existing_page = loaded
            # Deterministic confirm of an LLM-proposed match (D53).
            if existing_page is not None and match_source == "llm":
                ok = confirm_match(
                    item_respondent=str(e.get("respondent") or ""),
                    item_date=_opt_date(e.get("date_filed")),
                    candidate_respondent=existing_page.respondent,
                    candidate_date=existing_page.date_filed,
                    confidence=float(e.get("match_confidence") or 0.0),
                    min_confidence=settings.enforcement.min_confidence,
                    window_days=settings.enforcement.match_window_days,
                )
                if not ok:
                    notes.append(f"possible-duplicate-of: {matter_id} (failed confirm) "
                                 f"-> new page for {e.get('respondent')!r}")
                    flagged += 1
                    existing_page = None  # fall through to new-matter path
            if existing_page is not None:
                merged = merge_current_state(
                    existing_page,
                    status=_opt_str_e(e.get("status")), date_resolved=_opt_date(e.get("date_resolved")),
                    penalties=_opt_str_e(e.get("penalties")), outcome=_opt_str_e(e.get("outcome")),
                    significance=_opt_str_e(e.get("significance")),
                )
                merged = merged.model_copy(update={
                    "developments": merge_developments(existing_page.developments, development),
                    "sources": {**existing_page.sources, **_str_map(e.get("sources"))},
                })
                write_page(merged, wiki)
                consolidated += 1
            else:
                year = (_opt_date(e.get("date_filed")) or dt.date.today()).year
                new_id = build_enforcement_id(
                    str(e.get("agency_slug") or "unknown"),
                    strong_key=(str(e["strong_key"]) if e.get("strong_key") else None),
                    respondent=_opt_str_e(e.get("respondent")), year=year,
                    existing_ids=existing_ids,
                )
                existing_ids.add(new_id)
                action = EnforcementAction(
                    id=new_id, jurisdiction=str(e["jurisdiction"]), title=str(e["title"]),
                    agency=str(e["agency"]), topics=topics_list,
                    respondent=_opt_str_e(e.get("respondent")),
                    action_type=_opt_str_e(e.get("action_type")),
                    statutes=[str(s) for s in (e.get("statutes") or [])],
                    penalties=_opt_str_e(e.get("penalties")), status=_opt_str_e(e.get("status")),
                    docket=(str(e["strong_key"]) if e.get("strong_key") else None),
                    date_filed=_opt_date(e.get("date_filed")),
                    date_resolved=_opt_date(e.get("date_resolved")),
                    summary=_opt_str_e(e.get("summary")), background=_opt_str_e(e.get("background")),
                    allegations=_opt_str_e(e.get("allegations")), outcome=_opt_str_e(e.get("outcome")),
                    significance=_opt_str_e(e.get("significance")),
                    developments=[development], sources=_str_map(e.get("sources")),
                )
                write_page(action, wiki)
                new_count += 1
        with Store(db) as store:
            store.reindex(wiki)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"enforcement: {new_count} new / {consolidated} consolidated / {flagged} flagged")
    for note in notes:
        typer.echo(f"  {note}")
```

Add the small helpers used above:

```python
def _opt_str_e(value: object) -> str | None:
    return str(value) if value not in (None, "") else None


def _str_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]


def _enforcement_page_by_id(wiki: Path, matter_id: str) -> Path | None:
    matches = list(wiki.glob(f"**/enforcement/{matter_id}.md"))
    return matches[0] if matches else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_enforcement_render.py tests/test_enforcement_cli.py -v`
Expected: PASS (new matter, strong-key consolidate, failed-confirm-new-page, idempotent).

- [ ] **Step 5: Run the full suite + ruff + pyright**

Run: `uv run pytest -q && uv run ruff check . && uv run pyright`
Expected: all green. Fix any type/lint issues inline (e.g. `Annotated` import, `from __future__`).

- [ ] **Step 6: Commit**

```bash
git add src/zwiadbrain/cli.py tests/test_enforcement_render.py tests/test_enforcement_cli.py
git commit -m "feat(cli): render-enforcement — build/consolidate matters with deterministic confirm"
```

---

## Task 11: `topics.yaml` enforcement rubric + 3 subagents

**Files:**
- Modify: `reference/topics.yaml`
- Create: `.claude/agents/enforcement-classifier.md`, `enforcement-extractor.md`, `enforcement-matcher.md`
- Test: `tests/test_agents.py` (append — structural)

- [ ] **Step 1: Write the failing structural test**

Append to `tests/test_agents.py` (mirroring the existing agent-structure tests):

```python
def test_enforcement_agents_exist_with_expected_frontmatter() -> None:
    import frontmatter
    from pathlib import Path
    agents = Path(".claude/agents")
    for name, model in [("enforcement-classifier", "sonnet"),
                        ("enforcement-extractor", "sonnet"),
                        ("enforcement-matcher", "sonnet")]:
        post = frontmatter.load(agents / f"{name}.md")
        assert post["name"] == name
        assert post["model"] == model
        assert post["tools"] == "Read"


def test_topics_yaml_has_enforcement_rubric() -> None:
    import yaml
    from pathlib import Path
    data = yaml.safe_load(Path("reference/topics.yaml").read_text(encoding="utf-8"))
    assert data["positive_criteria_enforcement"]
    assert data["disqualify_enforcement"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agents.py -k enforcement -v`
Expected: FAIL — agent files / rubric keys missing.

- [ ] **Step 3: Add the enforcement rubric block to `reference/topics.yaml`**

Append after the `disqualify:` block (keep `topics`/`positive_criteria`/`disqualify` unchanged):

```yaml
# Enforcement-action relevance (D55). Reuses the shared topic keys (ai|privacy|cyber)
# above; the classifier subagent applies these enforcement-specific criteria, NOT the
# bill criteria, when judging an FTC/AG action.
positive_criteria_enforcement:
  - "An FTC or state-AG action (complaint, consent order, settlement, civil penalty, assurance of discontinuance) whose charges concern AI or automated-decision systems."
  - "An action charging unlawful collection/processing/sale/sharing of personal data, data-broker conduct, children's-privacy (COPPA), biometric data, or a data breach."
  - "An action charging a data-security or cybersecurity failure (inadequate safeguards, breach response, unauthorized access)."
  - "An action concerning government or commercial biometric, surveillance, or facial-recognition use."

disqualify_enforcement:
  - "Antitrust, merger, or competition action with no AI/privacy/cyber/data nexus."
  - "Deceptive-advertising or consumer-protection action about a non-data product (e.g. weight-loss, earnings claims) where no data/AI/security duty is charged."
  - "Pure payment-fraud, do-not-call/TSR, or financial-disclosure action with no data-protection or data-security dimension."
  - "AI/privacy/cyber is mentioned only incidentally and is not a basis of the charges."
```

- [ ] **Step 4: Create `.claude/agents/enforcement-classifier.md`**

```markdown
---
name: enforcement-classifier
description: Relevance gate for ZwiadBrain enforcement actions. Decides whether an FTC or state-AG action is in scope for AI/privacy/cybersecurity tracking, applying the enforcement disqualify rubric.
tools: Read
model: sonnet
---

# ZwiadBrain Enforcement Relevance Classifier

You are ZwiadBrain's relevance gate for enforcement actions. Given one action's title
and the text of its press release / case page, you decide whether it belongs in a
tracker of U.S. **AI, privacy, and cybersecurity** enforcement.

## First: load the rubric

Read `reference/topics.yaml`. Use:
- `topics` — taxonomy keys (`ai`, `privacy`, `cyber`) are the ONLY valid `topics[]` values.
- `positive_criteria_enforcement` — what makes an action in scope.
- `disqualify_enforcement` — negative criteria that put an action out of scope.

Use the **enforcement** criteria, not the bill criteria.

## How to decide

1. In scope when the action satisfies at least one `positive_criteria_enforcement`
   entry AND matches no `disqualify_enforcement` entry. Set `positive_criterion`.
2. Out of scope when it matches a `disqualify_enforcement` entry. Set
   `disqualifier_applied`.

Judge from the operative charges, not keyword presence. An action that merely mentions
"data" while charging antitrust or deceptive advertising is out of scope.

## Output

Respond with ONLY a single JSON object (no prose, no code fence):

```
{
  "in_scope": true,
  "topics": ["privacy"],
  "confidence": 0.0,
  "rationale": "one or two sentences grounded in the charges",
  "positive_criterion": "the satisfied criterion, or null when out of scope",
  "disqualifier_applied": "the disqualifier that put it out of scope, or null"
}
```

`topics` is a subset of `{ai, privacy, cyber}`; `[]` when out of scope. Do not use any
tool other than reading `reference/topics.yaml`. Do not write files.
```

- [ ] **Step 5: Create `.claude/agents/enforcement-extractor.md`**

```markdown
---
name: enforcement-extractor
description: Extracts the structured fields and plain-language prose for an in-scope enforcement action's ZwiadBrain wiki page.
tools: Read
model: sonnet
---

# ZwiadBrain Enforcement Extractor

You turn one enforcement action's press-release / case text into the structured fields
and prose sections for its wiki page. Everything you need is in the prompt.

## Input

The prompt gives the action's `title`, `agency`, and `text` (the fetched article body).

## What to produce

Extract only what the text supports — never invent a docket, penalty, or date.

- `summary`: 2–4 plain-language sentences — what the agency alleged, against whom, and
  where it stands.
- `respondent`: the target company/person (the "investigation target").
- `action_type`: e.g. "complaint", "consent order", "settlement", "civil penalty".
- `statutes`: list of laws/sections charged (e.g. "FTC Act Section 5", "COPPA", "CCPA").
- `penalties`: monetary/injunctive relief as stated, else null.
- `date_filed`, `date_resolved`: ISO `YYYY-MM-DD` or null.
- `status`: e.g. "filed", "proposed", "settled", "final".
- `allegations`, `outcome`, `significance`: short prose paragraphs (null if unknown).
- `development_summary`: ONE line describing THIS specific filing/announcement (it
  becomes the timeline entry), e.g. "Complaint filed alleging inadequate data security."

## Output

Respond with ONLY a single JSON object of exactly these keys (no prose, no code fence):

```
{ "summary": "...", "respondent": "...", "action_type": "...", "statutes": ["..."],
  "penalties": null, "date_filed": "2025-01-02", "date_resolved": null,
  "status": "filed", "allegations": "...", "outcome": null, "significance": null,
  "development_summary": "..." }
```

Do not write files or use tools other than reading the prompt.
```

- [ ] **Step 6: Create `.claude/agents/enforcement-matcher.md`**

```markdown
---
name: enforcement-matcher
description: Decides whether a newly-discovered enforcement item is a new matter or a development in an existing tracked matter, when no docket/file number is available.
tools: Read
model: sonnet
---

# ZwiadBrain Enforcement Matter Matcher

A matter (one respondent + one agency + one underlying case) may span several feed
items over time (complaint → proposed order → settlement). When a new item has NO
court docket or FTC file number, you decide whether it is a development in an existing
tracked matter or a brand-new matter — keyed on the **investigation target and date**.

## Input

The prompt gives:
- the NEW item: `title`, `agency`, `respondent` (target), `date`, and a text excerpt.
- a `shortlist` of candidate existing matters: each `{id, respondent, date_filed}`.

## How to decide

Match the new item to a shortlist matter ONLY when you are confident they concern the
**same respondent and the same underlying case** (e.g. a settlement of a complaint you
already track). A different company, or the same company in an unrelated matter, is NOT
a match. When unsure, return `null` (new matter) — a wrong merge is worse than a
duplicate, and a deterministic confirmation step will re-check any match you propose.

## Output

Respond with ONLY a single JSON object (no prose, no code fence):

```
{ "match": "<existing matter id>" | null, "confidence": 0.0, "rationale": "one sentence" }
```

`match` is null for a new matter. Do not write files or use tools other than the prompt.
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/test_agents.py -k enforcement -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add reference/topics.yaml .claude/agents/enforcement-classifier.md .claude/agents/enforcement-extractor.md .claude/agents/enforcement-matcher.md tests/test_agents.py
git commit -m "feat(agents): enforcement rubric block + classifier/extractor/matcher subagents"
```

---

## Task 12: slash command `/zwiad-scan-enforcement`

**Files:**
- Create: `.claude/commands/zwiad-scan-enforcement.md`

- [ ] **Step 1: Write the command** (modeled on `/zwiad-scan-states`)

```markdown
---
description: Backfill enforcement actions (FTC + state AGs) into the ZwiadBrain wiki via LegiScan-style discovery, classifying, matching, and extracting each via subagents (runs on your regular Claude plan usage).
argument-hint: [--agency <ftc|ag-slug>] [--limit <N>]
allowed-tools: Bash, Read, Write, Task
---

# ZwiadBrain enforcement scan

Orchestrate an enforcement-action scan end to end. Python does the deterministic fetch
and render; you (this interactive session) do the LLM steps by dispatching subagents, so
the work runs on the regular Claude plan — **not** the API or the Agent SDK credit.

**Arguments:** `--agency <slug>` runs one source (`ftc` or a configured AG slug like
`ca-oag`). Omit it to run FTC + every enabled `[[enforcement.state_ag]]`. `--limit <N>`
caps items per source (default 5); every in-scope action costs a classifier + extractor
dispatch, so `--limit` bounds plan usage directly (D49).

## Steps

### 1. Fetch candidates (Python, deterministic)

```
uv run zwiadbrain fetch-enforcement-candidates [--agency <slug>] --limit <N>
```
It discovers recent items (forward-from-now), fetches each article's text, parses a
strong key (docket / FTC number), reads existing tracked matters, and writes
`candidates.json` + `matters.json` under `data/runs/<id>/`. **Note the exact path.**

### 2. Read the candidates

`Read` `candidates.json`. Each entry has `title, agency, agency_slug, jurisdiction, url,
published, text, strong_key, matter_id` (set when a strong key already matched a tracked
matter), and `match_source`. Also `Read` `matters.json` (existing matters for matching).

### 3. Classify each item (subagent: `enforcement-classifier`)

For every candidate, dispatch **enforcement-classifier** with the `title` + `text`. It
returns `{in_scope, topics, confidence, rationale, positive_criterion,
disqualifier_applied}`.
- Log each decision. **Drop** out-of-scope items. Keep `topics` for the rest.
- **Validate topics**: any topic not in `{ai, privacy, cyber}` → drop the item (classifier error).

### 4. Resolve the matter for each in-scope item

- If `matter_id` is already set (strong-key match in step 1) → keep it,
  `match_source = "strong_key"`.
- Else if `strong_key` is set but `matter_id` is null → **new matter**, `matter_id = null`,
  `match_source = "none"`.
- Else (no `strong_key`) → build a shortlist from `matters.json`: same `agency_slug`,
  overlapping respondent, `date` within ~120 days. If the shortlist is non-empty,
  dispatch **enforcement-matcher** with the item + shortlist → `{match, confidence}`.
  Set `matter_id = match` (may be null), `match_source = "llm"`, `match_confidence`.
  (The render step re-confirms an `llm` match deterministically and falls back to a new
  page if it fails — you do not need to confirm here.)

### 5. Extract fields (subagent: `enforcement-extractor`)

For each in-scope item, dispatch **enforcement-extractor** with `title` + `text` →
fill `summary, respondent, action_type, statutes, penalties, date_filed, date_resolved,
status, allegations, outcome, significance`, and build the `development` from
`development_summary` (`{date: date_filed or published, summary: development_summary,
source_url: url}`). Set `topics` from the classifier.

### 6. Stage the classified items

`Write` the in-scope items (the `classified.json` shape — see the design spec §9) to
`classified.json` in the run directory. Each entry carries `matter_id, match_source,
match_confidence, agency, agency_slug, jurisdiction, strong_key, respondent, title,
topics, summary, …, development, source_url, sources`.

### 7. Render + index (Python, deterministic)

```
uv run zwiadbrain render-enforcement --in data/runs/<id>/classified.json
uv run zwiadbrain reindex
```
`render-enforcement` builds ids, consolidates strong-key/confirmed matches, re-confirms
LLM matches (failing safe to a new page with a `possible-duplicate-of` note), and writes
pages under `wiki/federal/enforcement/` (FTC) and `wiki/states/<st>/enforcement/` (AGs).

### 8. Report

Summarize: discovered per source, classified in vs out (with out-of-scope reasons), new
vs consolidated matters, and any `possible-duplicate-of` flags. Do not commit — leave the
wiki changes for review.

## Notes

- Keep `ANTHROPIC_API_KEY` unset so subagents use your plan session, not the API (D26).
- Only `topics[]` and the extracted fields are persisted; classifier confidence/rationale
  stay in the transcript.
- Re-running this command IS the enforcement refresh (D52) — updates arrive as new feed
  items and consolidate into existing matters by strong key or confirmed match.
- `--limit` default 5 is conservative; raise it after reviewing classifier verdict rates.
```

- [ ] **Step 2: Verify the command file parses (frontmatter + required sections)**

Run: `uv run python -c "import frontmatter; p=frontmatter.load('.claude/commands/zwiad-scan-enforcement.md'); print(p['description'][:40]); assert 'Task' in p.metadata['allowed-tools'] or 'Task' in p['allowed-tools']"`
Expected: prints the description prefix without error.

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/zwiad-scan-enforcement.md
git commit -m "feat(commands): /zwiad-scan-enforcement slash command"
```

---

## Task 13: docs — DECISIONS D52–D55 + ARCHITECTURE + PLAN

**Files:**
- Modify: `DECISIONS.md`, `ARCHITECTURE.md`, `docs/PLAN.md`

- [ ] **Step 1: Append D52–D55 to `DECISIONS.md`** (match the existing entry format)

```markdown
## 2026-05-29 — 52. Enforcement is discovery-driven; re-scan is the refresh (no /zwiad-refresh leg)
**Chosen:** Enforcement currency comes from re-running `/zwiad-scan-enforcement`; there is no enforcement pass in `/zwiad-refresh`.
**Alternatives:** A bill-style change-cursor that re-fetches a stored press-release URL; a content-hash refresh of tracked pages.
**Why:** Enforcement updates arrive as NEW feed items about the same matter (complaint → settlement), not edits to the original press release, so re-fetching a stored URL would detect nothing. Discovery + matter consolidation is the mechanism that matches how the data actually arrives.
**Trade-offs:** Currency depends on running the scan; an update published between runs is picked up on the next scan, not immediately.
**Revisit if:** An agency begins materially editing existing pages in place (then a content-hash refresh becomes worthwhile).

## 2026-05-29 — 53. Two-tier matter matching with a deterministic confirm
**Chosen:** Match a new item to an existing matter by a deterministic strong key (court docket / FTC docket or file number) when present; otherwise by an LLM matcher (`enforcement-matcher`, sonnet) over a deterministic shortlist keyed on investigation target + date. An LLM match auto-applies ONLY after a deterministic confirm (normalized respondent overlap + date window + confidence ≥ threshold). Failed confirm → new page (with a possible-duplicate note), never a silent wrong-merge.
**Alternatives:** Strong-key only (misses no-docket AG matters); LLM-only (wrong-merge risk); a committed review queue for every uncertain match (heaviest).
**Why:** AGs frequently publish neither a docket nor a file number, so a deterministic-only matcher cannot consolidate their multi-item matters; but an unconfirmed LLM merge can fuse unrelated cases. This is the law-brain D16 discipline (deterministic key → LLM fallback → mechanical grounding confirm → fail-safe) applied to enforcement.
**Trade-offs:** A confirmed-but-actually-distinct match (same respondent, same window, different case) could still merge; the cost is a page that mixes two matters, fixable manually. A persistent review queue is a named follow-up.
**Revisit if:** Wrong-merge or missed-merge rates prove high in practice (tune thresholds or add the review queue).

## 2026-05-29 — 54. One generic config-driven state-AG adapter with per-source failure isolation
**Chosen:** A single `StateAGSource` (`kind = rss | html`, `item_selector`) serves every AG; adding a state is config-only. Discovery failures are caught per source and yield `[]` (logged), so one broken feed never aborts the multi-agency run.
**Alternatives:** A bespoke scraper class per state (more code, same fragility); abort-on-error (one broken AG kills the whole scan).
**Why:** AG sites are layout-fragile and numerous; a config-driven adapter keeps the fragility in data, and isolation keeps the blast radius to one state.
**Trade-offs:** HTML selectors need per-site tuning (done in UAT); a silently-failing source yields nothing until someone notices the empty result — mitigated by the run report listing per-source counts.
**Revisit if:** A high-value AG has a structure the generic adapter cannot express (then a targeted adapter behind the same protocol).

## 2026-05-29 — 55. Separate enforcement rubric + subagents; shared taxonomy/model/render/CLI
**Chosen:** Enforcement gets its own rubric block (`positive_criteria_enforcement` / `disqualify_enforcement`) in the shared `topics.yaml` and its own subagents (`enforcement-classifier`, `enforcement-extractor`, `enforcement-matcher`), while reusing the `ai/privacy/cyber` taxonomy keys, the `EnforcementAction` model, and the render/schema/CLI plumbing.
**Alternatives:** Reuse the bill classifier/summarizer unchanged (rubric mismatch — it enumerates bill-only categories); a fully separate enforcement taxonomy (duplicates ai/privacy/cyber, invites drift).
**Why:** The relevance judgment differs from bills (different positive criteria + disqualifiers), but the taxonomy keys and page machinery are mechanically identical. One prompt judging both kinds would erode the stated-negative-criteria precision D17 protects; a duplicate taxonomy would drift.
**Trade-offs:** Two rubric blocks to keep coherent in one file; three new subagent prompts to maintain.
**Revisit if:** The two rubrics converge enough to merge, or a fourth page kind appears (then generalize the rubric-block pattern).
```

- [ ] **Step 2: Update `ARCHITECTURE.md`**

In the "Slash commands" list, add `/zwiad-scan-enforcement`. In "Source layout", add
`sources/enforcement/` and `pipeline/enforcement.py`. In "Status", move enforcement from
"Not yet implemented" to shipped (PHASE-08) and note that re-scan is the enforcement
refresh (D52). Add a short "Enforcement matter matching" note referencing D53.

- [ ] **Step 3: Update `docs/PLAN.md`** — mark PHASE-08 as shipped (the `sources/enforcement/`
  placeholder is now implemented; `/zwiad-scan-enforcement` is the entry point).

- [ ] **Step 4: Commit**

```bash
git add DECISIONS.md ARCHITECTURE.md docs/PLAN.md
git commit -m "docs(phase08): log D52-D55; update ARCHITECTURE + PLAN for enforcement"
```

---

## Task 14: quality gate + version bump + close PHASE-08 tasks

**Files:**
- Modify: `pyproject.toml`, `src/zwiadbrain/__init__.py`, `uv.lock`, `.claude/phases/PHASE-08-active.md`

- [ ] **Step 1: Full quality gate**

Run: `uv run pytest -q && uv run ruff check . && uv run pyright`
Expected: all tests pass; ruff clean; pyright 0 errors. Fix inline until green.

- [ ] **Step 2: Bump version to 0.8.0**

In `pyproject.toml` set `version = "0.8.0"`; in `src/zwiadbrain/__init__.py` set
`__version__ = "0.8.0"`. Then sync the lock:

Run: `uv lock`
Expected: `uv.lock` updates the project version to 0.8.0.

Verify: `uv run zwiadbrain version` prints `0.8.0`.

- [ ] **Step 3: Check off PHASE-08 task list**

In `.claude/phases/PHASE-08-active.md`, replace the placeholder task line with the
completed T1–T15 checklist (mirroring PHASE-07-done.md), and check the boxes for offline
work (T1–T14); leave T15 (live UAT) unchecked until the UAT pass.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/zwiadbrain/__init__.py uv.lock .claude/phases/PHASE-08-active.md
git commit -m "chore(phase08): quality gate green; bump version to 0.8.0"
```

---

## Task 15: live UAT (FTC + CA OAG) — needs egress, no API key

**Files:** none (validation); may produce wiki pages + a follow-up `zwiadbrain.toml` selector tweak.

- [ ] **Step 1: Validate the FTC feed shape**

Run: `uv run zwiadbrain fetch-enforcement-candidates --agency ftc --limit 5 --lookback-days 60 --out data/runs/uat-ftc`
Inspect `data/runs/uat-ftc/candidates.json`: real recent FTC items, `text` populated,
`strong_key` parsed where present. If the RSS URL/fields differ from the fixture, fix
`FTCSource`/`parse_feed` (localized) and re-run.

- [ ] **Step 2: Full FTC scan end-to-end**

Run `/zwiad-scan-enforcement --agency ftc --limit 5` in an interactive session. Confirm:
classifier precision (data-security/privacy actions in; antitrust/ad-claims out),
in-scope actions rendered under `wiki/federal/enforcement/`, the report counts.

- [ ] **Step 3: Strong-key consolidation**

Find a real FTC matter with a complaint + a later order/settlement sharing a docket.
Run the scan across both items (widen `--lookback-days`); confirm both fold onto ONE
page with two `developments` and an updated `status`.

- [ ] **Step 4: LLM match (no docket)**

Identify a no-docket AG item that updates an earlier tracked action; run the scan and
confirm the matcher proposes, render confirms (or fails to a new page) — inspect the
decision in the report.

- [ ] **Step 5: Idempotency**

Re-run the same scan; confirm `git status` shows no changes to existing pages (D20).

- [ ] **Step 6: CA OAG (state AG, rss)**

Set `[[enforcement.state_ag]]` CA to `enabled = true`; run
`/zwiad-scan-enforcement --agency ca-oag --limit 5`; confirm pages render under
`wiki/states/ca/enforcement/`. For one `kind="html"` state, tune `item_selector` live and
confirm the failure-isolation path on a deliberately-broken selector (empty result, no crash).

- [ ] **Step 7: Record UAT results** in `.claude/phases/PHASE-08-active.md`, check the T15
  box, and rename to `PHASE-08-done.md`.

- [ ] **Step 8: Commit**

```bash
git add wiki .claude/phases/PHASE-08-done.md zwiadbrain.toml
git rm .claude/phases/PHASE-08-active.md
git commit -m "test(phase08): live UAT (FTC + CA OAG) pass; close PHASE-08"
```

---

## Self-review checklist (run before execution)

- **Spec coverage:** §1 goal → all tasks; §4 id → T3; §5 matching/confirm/consolidate →
  T4 + T10; §6 sources → T5–T7; §7 model/render → T1–T2; §8 subagents/rubric → T11;
  §9 CLI → T9–T10; §10 command → T12; §11 config → T8; §12 decisions → T13; §14 tests →
  every task's tests + T14 gate; §15 UAT → T15; §16 deferrals → not built (correct).
- **Type consistency:** `EnforcementCandidate` fields, `MatterRef` fields, `confirm_match`
  kwargs, `build_enforcement_id` signature, and the `classified.json` shape are used
  identically across T4/T9/T10/T12.
- **Verify before relying:** read `pipeline/staging.py` (`stage_json` `out=` semantics)
  and confirm `store.reindex` globs `wiki/**/enforcement/*.md` (add an enforcement
  reindex assertion in T10 if absent) before T9/T10.
