# Phase 08 — Enforcement actions (FTC + state AGs)

> Design spec. Authored 2026-05-29. Grounds the implementation plan that
> `writing-plans` will produce. Verified against the current codebase (v0.7.0).
>
> Supersedes the pre-pivot PHASE-08 sketch in `docs/PLAN.md`
> ("`sources/enforcement/ftc.py` + `state_ag.py` (config-driven); relevance/
> extraction via an enforcement subagent") by restating it in the post-pivot
> subagent architecture (D26/D27) and pinning the matter-identity model that the
> sketch left unspecified.

---

## 1. Goal

Enforcement actions become first-class tracked wiki pages alongside bills:

- **Discover** AI/privacy/cyber enforcement actions from the **FTC** and the **7
  priority-state Attorneys General** (CA, NY, TX, CO, VA, WA, IL — jurisdiction
  parity with the legislation we already track).
- **Classify** relevance with an enforcement-specific disqualify rubric, **extract**
  structured fields + prose, **consolidate** a matter that spans several feed items
  (complaint → proposed order → settlement) onto one page, and **render** under
  `wiki/federal/enforcement/` (FTC) and `wiki/states/<st>/enforcement/` (AGs).
- Exposed as a new **`/zwiad-scan-enforcement`** slash command.

**Discovery-driven, forward-from-now (D44).** No historical back-catalog: each scan
reads a recent window of agency feeds. **Re-running `/zwiad-scan-enforcement` *is* the
refresh** — there is deliberately no enforcement leg in `/zwiad-refresh`, because
enforcement updates arrive as *new feed items about the same matter*, not as edits to
an existing page (the key domain fact this design is built around).

Built **agency-count-agnostic**; validated against FTC + the 7 priority AGs first,
expanded by editing config.

## 2. What is already pre-wired vs genuinely new

The model and render layers already anticipate enforcement, so this phase adds sources,
matching, subagents, and CLI halves rather than reworking the core:

**Already present (reused):**
- `models.EnforcementAction` (`type="enforcement"`, `agency, respondent, action_type,
  statutes[], date_filed, date_resolved, penalties, status, docket` + body-prose
  `background/allegations/outcome/significance`) and `parse_wiki_item`'s discriminated
  union route on `type`.
- `templates.render_enforcement_body`, `schema.to_frontmatter`/`from_page` (handle
  `EnforcementAction`; body-prose fields already excluded from frontmatter).
- `render.page_path` already routes `EnforcementAction` → `wiki/{federal|states/<st>}/
  enforcement/{id}.md`; `render_page`/`write_page` are kind-agnostic and idempotent.
- `[sources].enabled` already lists `"ftc"`, `"state_ag"`; `feedparser` + `beautifulsoup4`
  are already dependencies. **No new runtime dependency is added.**

**Genuinely new:**
- A separate **`EnforcementSource`** contract (the bill `Source.fetch` returns `Bill`;
  enforcement returns `EnforcementAction`-shaped data, so it cannot reuse that protocol).
- `sources/enforcement/{base,ftc,state_ag}.py`.
- A **matter-identity + two-tier matching** subsystem (`pipeline/enforcement.py`,
  `ids.build_enforcement_id` + `ids.parse_strong_key`).
- One model addition: `EnforcementDevelopment` + `EnforcementAction.developments[]`,
  plus a "Developments" render section.
- Three subagents (`enforcement-classifier`, `enforcement-extractor`,
  `enforcement-matcher`) and an enforcement rubric block in `reference/topics.yaml`.
- CLI `fetch-enforcement-candidates` + `render-enforcement`; the
  `/zwiad-scan-enforcement` command; `EnforcementSettings` config.

## 3. Architecture fit

```
/zwiad-scan-enforcement (NEW slash command)        (re-run = refresh; NO /zwiad-refresh leg)
  │
  ├ fetch-enforcement-candidates  (deterministic Python)
  │    FTC RSS + AG rss|html  ── discover (forward-from-now) ─→ fetch article text (bs4)
  │    parse strong key (docket / FTC number)
  │    build matters.json (existing tracked matters, for the matcher shortlist)
  │    → candidates.json + matters.json
  │
  ├ enforcement-classifier   subagent  (relevance, enforcement rubric)         ┐ D26
  ├ enforcement-matcher      subagent  (sonnet 4.6; only when NO strong key)   │ interactive
  ├ enforcement-extractor    subagent  (summary + structured fields)           ┘
  │
  └ render-enforcement  (deterministic Python)
       build id / consolidate; re-run match confirm DETERMINISTICALLY (D16-style);
       merge developments + current-state fields idempotently → wiki/**/enforcement/ → reindex
```

Python makes zero LLM calls (D26); the fetch/render halves exchange gitignored JSON
under `data/runs/<id>/` (D27); `render_page` is byte-identical on unchanged input (D20).

## 4. Enforcement matter identity & id scheme

A page = one **matter** (one respondent + one agency + one underlying case), which may
accrue several feed items over time. The page `id` is the filename slug **and** the
global `items.id` primary key, so it must be **globally unique** across bills + all
enforcement, and **matter-stable** (a later development maps back to the same page).

**`ids.parse_strong_key(text) -> str | None`** — extract a deterministic strong
identifier from an item's title/text, trying in order:
- Federal court docket: `\d{1,2}:\d{2}-[a-z]{2,3}-\d{3,6}` → `2:25-cv-12295`.
- FTC administrative docket: `\bC-\d{3,4}\b` or `\bD-\d{3,4}\b` → `c-4790`.
- FTC file/matter number: `\b\d{7}\b` (e.g. `2023155`) or `\b\d{3}\s?\d{4}\b`.
- `None` when none match (→ the LLM-matcher path).

**`ids.build_enforcement_id(agency_slug, *, strong_key, respondent, year) -> str`:**
- With a strong key: `{agency_slug}-{slug(strong_key)}` — e.g. `ftc-c-4790`,
  `ftc-2-25-cv-12295`, `ca-oag-2-25-cv-12295`.
- Without: `{agency_slug}-{year}-{slug(respondent)}` — e.g. `ftc-2025-acme-data-brokers`,
  `ca-oag-2025-doordash`. A collision within `(agency, year, respondent)` (two
  no-docket actions against the same respondent the same year) appends `-2`, `-3`…
  (the renderer disambiguates against existing ids; logged).

`agency_slug` is `ftc` for the FTC and `{state}-oag` (or the config entry's slugified
short name) for an AG. **Collision argument:** enforcement ids are always alpha-led
(`ftc-…`, `ca-oag-…`); federal bill ids are integer-led (`118-…`) and state bill ids
are `{state}-{year}-…` (second segment numeric) — `ca-oag-…` (second segment `oag`)
never collides with `ca-2025-…`. The agency-slug prefix guarantees global uniqueness;
`page_path` additionally separates `bills/` from `enforcement/` directories.

## 5. Matter matching & consolidation (the core)

Per discovered, **in-scope** item, resolve identity in three deterministic-first tiers
(this is the law-brain D16 pattern — deterministic key → LLM fallback → deterministic
grounding confirm → fail-safe — applied to enforcement matters):

1. **Strong-key match (deterministic, in the fetch half).** If `parse_strong_key`
   yields a key and an existing tracked matter stores that key → `matter_id = <that
   id>`, `match_source = "strong_key"`. If a key is present but matches nothing → new
   matter, id derived from the key.
2. **LLM matcher (`enforcement-matcher`, sonnet 4.6) — only when no strong key.** The
   subagent receives the new item (title, agency, candidate respondent, date, a text
   excerpt) + a **deterministically-built shortlist** of existing matters in the same
   agency whose respondent fuzzily overlaps and whose date is within a window. It
   returns `{match: "<id>"|null, confidence, rationale}` (null = new matter),
   `match_source = "llm"`.
3. **Deterministic confirm in the render half (grounds the LLM gate).** Mirroring how
   `render-leg-history` re-checks the verifier's claim in Python rather than trusting
   it, `render-enforcement` re-runs `pipeline.enforcement.confirm_match(item,
   candidate)` for any `match_source == "llm"` proposal:
   - require **normalized respondent overlap** (case/punctuation/suffix-folded token
     overlap ≥ threshold) **AND** `|item.date − candidate.date| ≤ window_days`
     **AND** `confidence ≥ min_confidence` (config, default 0.75).
   - pass → consolidate; **fail → NEW matter** (never wrong-merge) + a
     `possible-duplicate-of: <id>` line in the run report (transcript only; no
     persistent queue in v1 — a named follow-up).

**Consolidation (deterministic, idempotent — D20):**
- **New matter** → build `EnforcementAction` (id from §4, extracted fields,
  `developments = [the one development]`), `write_page`.
- **Existing matter** → load the page via `from_page`, then:
  - append the new `EnforcementDevelopment`, **deduped by `source_url`** (re-scanning
    the same feed finds the development already present → no change); sort developments
    by `(date, source_url)` for stable bytes.
  - update current-state fields **monotonically**: a new non-null `status /
    date_resolved / penalties / outcome / significance` overwrites; a null from the new
    item never blanks an existing value.
  - merge `sources` (add the new item's URL).
  - `write_page` (skips the write when bytes are unchanged).

Re-running an identical scan is therefore a clean no-op (source_url dedup + monotonic
merge + byte-compare write).

## 6. `EnforcementSource` contract + FTC + state-AG adapter

`sources/enforcement/base.py`:

```python
class EnforcementCandidate(BaseModel):
    source: str            # "ftc" | "state_ag"
    agency: str            # "FTC" | the AG config name, e.g. "California OAG"
    agency_slug: str       # "ftc" | "ca-oag"
    jurisdiction: str      # "US" (FTC) | "US-CA" … (AG)
    title: str
    url: str
    published: dt.date | None = None
    raw: dict[str, object] = {}
    text: str | None = None     # filled by fetch_text

@runtime_checkable
class EnforcementSource(Protocol):
    name: str
    def discover(self, *, since: dt.datetime | None = None, limit: int = 20
                 ) -> list[EnforcementCandidate]: ...
    def fetch_text(self, candidate: EnforcementCandidate) -> str: ...
```

- **`ftc.py` — `FTCSource`.** `discover` reads the FTC press-release / Cases &
  Proceedings RSS via `feedparser` (title, link, published, summary → Candidates,
  `jurisdiction="US"`, `agency="FTC"`, `agency_slug="ftc"`). `fetch_text` GETs the link
  and extracts readable body text via BeautifulSoup. httpx + tenacity transport mirrors
  `LegiScanSource` (5xx retried, network retried). No API key (RSS is public).
- **`state_ag.py` — `StateAGSource`.** One **generic, config-driven** adapter
  constructed from a `StateAGSource` config entry (`name, jurisdiction, url, kind,
  item_selector, enabled`). `kind="rss"` → `feedparser`. `kind="html"` → httpx GET +
  `BeautifulSoup.select(item_selector)` to enumerate release links/titles/dates.
  `fetch_text` GETs each release and extracts body text. **Adding/fixing a state is
  config-only, never new code.**
- **Per-source failure isolation.** `discover` wraps network/parse errors per source,
  logs, and returns `[]` so one broken AG selector never aborts the multi-agency run.
- **Forward-from-now (D44).** `discover` filters to a recent window (`since` =
  `now − lookback_days`, config default 30) and caps to `limit`. No back-catalog crawl.

## 7. Model & schema changes (small, contained)

```python
class EnforcementDevelopment(BaseModel):
    date: dt.date | None = None
    summary: str                       # one-line description of this development
    source_url: _HttpUrlStr            # reuses the existing http-validated str type

class EnforcementAction(WikiItem):
    ...                                # unchanged existing fields
    developments: list[EnforcementDevelopment] = []
```

- `developments` is **persisted to frontmatter** (NOT body-only): each entry came from a
  transient feed item and cannot be re-derived, so it is the source of truth — the same
  treatment `leg_history.{hearings,statements,narrative}` already gets (D40). It is
  *also* rendered into the body (the body is derived from the persisted model, so D20
  holds). It must therefore **not** be added to `schema._BODY_ONLY_FIELDS`; the existing
  `to_frontmatter` (`model_dump(exclude_none=True)`, drops empty collections) serializes
  it automatically — same zero-code round-trip that `legiscan_bill_id` got in PHASE-07.
- `templates.render_enforcement_body` gains a **"Developments"** timeline section
  (placed after `Summary`, before `Background`): `- {date} — {summary} — [source](url)`,
  skipping any entry without a `source_url` (matches the hearings/statements "no link,
  no render" rule).
- `templates.py` will import the new `EnforcementDevelopment` (it already imports
  `EnforcementAction`).

D20 holds: stable `(date, source_url)` sort + deterministic template + compare-then-write.

## 8. Subagents + `topics.yaml` enforcement rubric

**Compartmentalize the judgment, share the plumbing.** The `ai/privacy/cyber` taxonomy
keys and seed lexicon stay shared (single-source in `topics.yaml`); a new **enforcement
rubric block** is added to the *same* file so the two cannot drift:

```yaml
positive_criteria_enforcement:
  - "An FTC or state-AG action (complaint, consent order, settlement, civil penalty,
     assurance of discontinuance) whose charges concern AI / automated-decision systems."
  - "... the unlawful collection/processing/sale/sharing of personal data, data-broker
     conduct, children's-privacy (COPPA), biometric data, or a data breach."
  - "... a data-security / cybersecurity failure (inadequate safeguards, breach response,
     unauthorized access)."
  - "... government or commercial biometric / surveillance / facial-recognition use."
disqualify_enforcement:
  - "Antitrust / merger / competition action with no AI/privacy/cyber/data nexus."
  - "Deceptive-advertising or consumer-protection action about a non-data product
     (e.g. weight-loss, earnings claims) where no data/AI/security duty is charged."
  - "Pure payment-fraud, do-not-call/TSR, or financial-disclosure action with no
     data-protection or data-security dimension."
  - "AI/privacy/cyber is mentioned only incidentally and is not a basis of the charges."
```

Three new prompts in `.claude/agents/` (restricted `tools: Read`, like the bill agents):

- **`enforcement-classifier`** (`model: sonnet`) — reads the enforcement rubric block;
  input = action `title` + extracted `text`; output the same JSON shape as the bill
  classifier (`{in_scope, topics, confidence, rationale, positive_criterion,
  disqualifier_applied}`), `topics[] ⊆ {ai, privacy, cyber}`.
- **`enforcement-extractor`** (`model: sonnet`) — one dispatch; input = `title` + `text`;
  output JSON `{summary, respondent, action_type, statutes[], penalties, date_filed,
  date_resolved, status, allegations, outcome, significance, development_summary}`.
  Extracts structured fields AND the prose sections AND the one-line development summary.
- **`enforcement-matcher`** (`model: sonnet` — claude-sonnet-4-6, the user-specified
  matcher) — input = the new item + a candidate shortlist; output `{match: "<id>"|null,
  confidence, rationale}`. Only dispatched for in-scope items with **no** strong key.

Per-item dispatch (bounds plan usage, D49): **classify → drop out-of-scope → match
(only no-strong-key items) → extract.** `--limit` caps items per agency; feed volume is
low (dozens/run), so steady-state plan usage is modest.

## 9. Scan flow — `fetch-enforcement-candidates` + `render-enforcement`

**`fetch-enforcement-candidates [--agency ftc|<name>|all] [--limit N] [--lookback-days D]
[--out DIR]`** (deterministic discovery half):
1. Build the enabled `EnforcementSource`s from config (FTC + each enabled AG).
2. For each source (failure-isolated): `discover(since=now−D, limit=N)` → `fetch_text`
   per candidate → `parse_strong_key`.
3. Stage `candidates.json` = list of `{candidate fields, text, strong_key}` and
   `matters.json` = every existing tracked matter `{id, agency_slug, jurisdiction,
   respondent, date_filed, strong_key}` (read from `wiki/**/enforcement/*.md` via
   `from_page`) for the matcher's shortlist + the deterministic strong-key match.
4. Resolve strong-key matches deterministically here (no LLM needed): annotate each
   candidate with `matter_id`/`match_source="strong_key"` when its key hits a matter.

**`/zwiad-scan-enforcement`** then runs the subagents (classifier → matcher for
no-key in-scope items → extractor) and writes `classified.json`, where each entry is:

```jsonc
{
  "matter_id": "<existing id>" | null,     // null = new matter
  "match_source": "strong_key" | "llm" | "none",
  "match_confidence": 0.0,                  // for llm; render re-confirms
  "agency": "FTC", "agency_slug": "ftc", "jurisdiction": "US",
  "strong_key": "C-4790" | null,
  "respondent": "...", "title": "...", "topics": ["privacy"],
  "summary": "...", "background": "...", "allegations": "...",
  "outcome": "...", "significance": "...",
  "action_type": "...", "statutes": ["..."], "penalties": "...",
  "status": "...", "date_filed": "2025-..", "date_resolved": null,
  "development": {"date": "2025-..", "summary": "...", "source_url": "https://..."},
  "source_url": "https://...", "sources": {"FTC": "https://..."}
}
```

**`render-enforcement --in classified.json [--wiki wiki] [--db …]`** (deterministic
render half):
1. Validate each entry; validate `topics` against the taxonomy (reuse the
   `render-classified` topic-validation discipline).
2. Resolve identity: `strong_key` → trust; `llm` → **re-run `confirm_match`
   deterministically** (§5) → pass = consolidate, fail = new matter + log; `none` = new.
3. New → `build_enforcement_id` + construct `EnforcementAction` (developments=[the dev]);
   Existing → load + merge developments (source_url dedup) + monotonic current-state
   update + merge sources.
4. `write_page` (idempotent), then `reindex`.
5. Report: per-agency discovered, classified in/out (with disqualifier reasons), new vs
   consolidated, and any `possible-duplicate-of` flags. Do not commit.

## 10. Slash command — `/zwiad-scan-enforcement` (no `/zwiad-refresh` leg)

`.claude/commands/zwiad-scan-enforcement.md`, modeled on `/zwiad-scan-states`:
`--agency` runs one source (FTC or a named AG); omitted runs all enabled. `--limit`
caps per agency. Steps: fetch → read candidates → classify (drop out-of-scope, validate
topics) → resolve matter (strong-key already annotated; dispatch `enforcement-matcher`
for no-key in-scope items) → extract → write `classified.json` → `render-enforcement` →
`reindex` → report. Keep `ANTHROPIC_API_KEY` unset (D26).

**`/zwiad-refresh` is deliberately NOT extended.** Enforcement currency comes from
re-running `/zwiad-scan-enforcement` (updates arrive as new feed items, §1). This is
recorded as D52 so the asymmetry with bills is explicit, not an omission.

## 11. Config & scope

```toml
[enforcement]
enabled = true
lookback_days = 30
min_confidence = 0.75      # LLM-match confirm threshold (D53)
match_window_days = 120    # date proximity for confirm (D53)

[enforcement.ftc]
enabled = true
rss_url = "https://www.ftc.gov/feeds/press-release.xml"   # validated in UAT

[[enforcement.state_ag]]
name = "California OAG"
agency_slug = "ca-oag"
jurisdiction = "US-CA"
url = "https://oag.ca.gov/news/press-releases/feed"
kind = "rss"
item_selector = ""
enabled = true
# … one entry per priority state: ny, tx, co, va, wa, il (rss where available, else html)
```

- `EnforcementSettings` (pydantic `BaseModel`) added to `config.Settings`:
  `enabled, lookback_days, min_confidence, match_window_days, ftc: FTCSettings,
  state_ag: list[StateAGSource]`. Loaded from the `[enforcement]` TOML table exactly as
  `[lawbrain]`/`[states]` are (no `.env` overlap — no secret; FTC/AG feeds are public).
- **No new API key.** Unlike Congress/LegiScan, enforcement sources are public RSS/HTML,
  so there is no `require_enforcement_api_key`.
- Scope rollout: ship FTC + 7 priority AGs; expand by adding `[[enforcement.state_ag]]`
  entries. Agency-count-agnostic (D54).

## 12. Decisions to log (`DECISIONS.md`)

- **D52** — Enforcement is **discovery-driven**; re-running `/zwiad-scan-enforcement`
  *is* the refresh; there is no enforcement leg in `/zwiad-refresh`. *Why:* updates
  arrive as new feed items about the same matter, not edits to the original page, so a
  bill-style change-cursor re-fetch of a stored URL is the wrong mechanism.
- **D53** — **Two-tier matter matching:** deterministic strong key (court docket / FTC
  docket or file number) when present; else an LLM matcher (`enforcement-matcher`,
  sonnet 4.6) keyed on investigation target + date over a deterministic shortlist; an
  LLM match auto-applies only after a **deterministic confirm** (normalized respondent
  overlap + date window + confidence ≥ threshold). Failed confirm → new page, never a
  silent wrong-merge (extends the D16 grounding discipline to enforcement). Uncertain
  matches surface as a run-report `possible-duplicate-of` note; a persistent review
  queue is a named follow-up.
- **D54** — **One generic config-driven state-AG adapter** (`kind = rss | html`,
  `item_selector`), with **per-source failure isolation**; adding a state is config-only.
  *Trade-off:* HTML selectors are layout-fragile and may need UAT tuning — isolation
  keeps one broken scraper from aborting the run.
- **D55** — Enforcement gets a **separate rubric block + separate subagents**
  (classifier/extractor/matcher), while **sharing** the `ai/privacy/cyber` taxonomy,
  the `EnforcementAction` model, and the render/schema/CLI plumbing. *Why:* the relevance
  judgment differs from bills (different positive criteria + disqualifiers), but the
  taxonomy keys and page machinery are mechanically identical; one prompt judging both
  kinds would erode the stated-negative-criteria precision D17 protects.

## 13. File map

**New**
- `src/zwiadbrain/sources/enforcement/base.py` — `EnforcementSource` + `EnforcementCandidate`.
- `src/zwiadbrain/sources/enforcement/ftc.py` — `FTCSource`.
- `src/zwiadbrain/sources/enforcement/state_ag.py` — generic `StateAGSource`.
- `src/zwiadbrain/pipeline/enforcement.py` — pure matching/confirm/consolidate helpers
  (`normalize_respondent`, `build_shortlist`, `confirm_match`, `merge_developments`,
  `merge_current_state`).
- `.claude/agents/enforcement-classifier.md`, `enforcement-extractor.md`,
  `enforcement-matcher.md`.
- `.claude/commands/zwiad-scan-enforcement.md`.
- `tests/fixtures/enforcement/` — `ftc_press_rss.xml`, `ftc_press.html`,
  `ag_ca_rss.xml`, `ag_html_list.html`, `ag_press.html`.
- `tests/test_enforcement_sources.py`, `tests/test_enforcement_matching.py`,
  `tests/test_enforcement_id.py`, `tests/test_enforcement_render.py`,
  `tests/test_enforcement_cli.py`.

**Changed**
- `src/zwiadbrain/models.py` — `EnforcementDevelopment` + `EnforcementAction.developments`.
- `src/zwiadbrain/wiki/templates.py` — "Developments" section in `render_enforcement_body`.
- `src/zwiadbrain/pipeline/ids.py` — `parse_strong_key` + `build_enforcement_id`.
- `src/zwiadbrain/cli.py` — `fetch-enforcement-candidates`, `render-enforcement`.
- `src/zwiadbrain/config.py` — `EnforcementSettings`, `FTCSettings`, `StateAGSource`.
- `zwiadbrain.toml` — `[enforcement]` block + FTC + 7 AG entries (replaces the stub comment).
- `reference/topics.yaml` — `positive_criteria_enforcement` + `disqualify_enforcement`.
- `DECISIONS.md` — D52–D55.
- `ARCHITECTURE.md`, `docs/PLAN.md` status notes.
- `tests/test_schema.py`, `tests/test_render.py` — enforcement round-trip + developments.

**Unchanged (reused / verify)** — `pipeline/render.py` (`page_path`/`write_page` already
route enforcement), `wiki/schema.py` (`to_frontmatter`/`from_page` already handle the
union; the new field round-trips via `model_dump`), `pipeline/staging.py`. **Verify
`store.reindex` globs `wiki/**/enforcement/*.md`** (it walks `wiki/**`; confirm in the
plan and add an enforcement reindex test).

## 14. Test plan (offline, `respx` + fixtures)

- **Sources:** `ftc_press_rss.xml` → `FTCSource.discover` yields Candidates with the
  right `jurisdiction="US"`, `agency_slug="ftc"`, `published`, `url`; `fetch_text` on
  `ftc_press.html` returns clean body text. `StateAGSource` with `kind="rss"` and
  `kind="html"` (+`item_selector`) both enumerate releases; a malformed feed → `[]` +
  logged (failure isolation), not an exception.
- **Strong-key parse:** `2:25-cv-12295`, `C-4790`, `2023155` parse; a release with none
  → `None`. `build_enforcement_id`: strong-key form, respondent-fallback form,
  same-respondent-same-year disambiguation suffix; global-uniqueness vs a federal
  `118-hr-1` and a state `ca-2025-sb-53` (no collision).
- **Matching/confirm:** `confirm_match` accepts (respondent overlap + in-window date +
  conf≥0.75), rejects on respondent mismatch, on out-of-window date, on low confidence;
  `build_shortlist` filters by agency + respondent overlap + window.
- **Consolidation/idempotency:** new matter → page with one development; a second item
  with the same strong key folds in (2 developments, monotonic status update, merged
  sources); **re-running the identical item → byte-identical page, zero writes** (D20);
  a null new field never blanks an existing value.
- **Render:** `render_enforcement_body` emits the Developments section in stable order;
  an entry without `source_url` is skipped; round-trip a full `EnforcementAction`
  through `to_frontmatter`/`from_page` with `developments` intact; `reindex` indexes an
  enforcement page.
- **CLI:** `fetch-enforcement-candidates` stages `candidates.json` + `matters.json`
  (mocked sources); `render-enforcement` validates topics, builds ids, consolidates,
  re-confirms an `llm` match and **demotes a failed confirm to a new page**.

## 15. Live UAT (no API key needed; needs egress to ftc.gov + AG sites)

1. `fetch-enforcement-candidates --agency ftc --limit 5 --lookback-days 60` → inspect
   `candidates.json`: real recent FTC items, article text populated, strong keys parsed.
2. `/zwiad-scan-enforcement --agency ftc --limit 5` end-to-end → classifier verdicts
   (precision: privacy/data-security actions in, antitrust/ad-claims out) → in-scope
   actions rendered under `wiki/federal/enforcement/` → inspect a page.
3. **Strong-key consolidation:** find a real FTC matter with a complaint + a later order
   sharing a docket; confirm both fold onto one page with two developments.
4. **LLM match:** a no-docket AG item that updates an earlier action → matcher proposes,
   render confirms (or fails to a new page) — inspect the decision in the report.
5. **Idempotency:** re-run the same scan → clean `git status` (byte-identical).
6. One AG with `kind="html"` (e.g. tune CA OAG's `item_selector` live) to validate the
   generic adapter + the failure-isolation path on a deliberately-broken selector.

## 16. Out of scope / deferred (named, not silent)

- **Enforcement leg in `/zwiad-refresh`** — re-running the scan is the refresh (D52).
- **Persistent review queue** for uncertain LLM merges — v1 emits a run-report note;
  a committed `enforcement-review.md` (the `links.yaml` analog) is a follow-up.
- **Respondent-name fuzzy *discovery*** (clustering unrelated agencies' items about one
  company across jurisdictions) — out of scope; matching is within one agency.
- **Historical back-catalog** — forward-from-now only (D44).
- **SEC / HHS-OCR / CFPB and non-priority-state AGs** — config/source additions later.
- **PDF complaint parsing** — v1 extracts from the HTML press release / case page; PDF
  text extraction is a follow-up if HTML text proves too thin.
- **Cross-linking enforcement ↔ bills/law-brain** — entity propagation is deferred
  (D15); law-brain commentary on enforcement pages is PHASE-09.

## 17. Risks & open questions

- **HTML AG selectors are layout-fragile.** Mitigated by the config-driven adapter +
  per-source failure isolation (D54); expect to tune a few `item_selector`s in UAT.
  Some AGs may offer no usable RSS and an awkward HTML structure — those states may ship
  later in the rollout rather than block the phase.
- **LLM wrong-merge.** Mitigated by the deterministic confirm (respondent + date +
  confidence) and fail-safe new-page (D53); the cost of a miss is a duplicate page (a
  later manual merge), never a corrupted/fused matter.
- **Strong-key formats vary** (FTC file number `2023155` vs docket `C-4790` vs court
  `2:25-cv-12295`); the parser handles the known set and returns `None` otherwise (→ LLM
  path). A `\d{7}` file-number regex risks false positives (e.g. a phone or ZIP in body
  text) — restrict it to the title / a labeled "File No." context, validated in UAT.
- **Forward-from-now window.** If `lookback_days` is shorter than the gap between scans,
  items can be missed. Config default 30; the operator widens it for infrequent runs.
- **FTC RSS URL / field shape** is assumed from the public feed and **validated in UAT
  step 1** before relying on it (mirrors PHASE-07's MEDIUM-confidence query caveat).
- **Respondent normalization threshold** (token overlap) needs tuning so "Acme, Inc."
  matches "Acme Corporation" but not "Acme Health"; tuned against real AG data in UAT.
- **Plan usage:** classifier + extractor per in-scope item, matcher per no-key item.
  Bounded by `--limit` and low feed volume; revisit if a high-volume AG is added.
