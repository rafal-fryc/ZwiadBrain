# Phase 07 — State legislation via LegiScan (backfill + refresh)

> Design spec. Authored 2026-05-29. Grounds the implementation plan that
> `writing-plans` will produce. Verified against the **LegiScan API v1.91 User
> Manual (Rev. 20250317)** and the current codebase (v0.6.1).
>
> Supersedes the pre-pivot PHASE-07 sketch in `docs/PLAN.md` ("`sources/legiscan.py`
> with `change_hash` incremental sync") by restating it in the post-pivot
> subagent architecture (D26/D27) and expanding scope to all 50 states (D49).

---

## 1. Goal

State bills become first-class tracked wiki pages, mirroring the federal flow:

- **Backfill** — discover relevant state bills via LegiScan full-text search,
  classify (disqualify rubric, D17), summarize + explain amendments for in-scope
  bills, render to `wiki/states/<st>/bills/`. The `/zwiad-backfill` analog,
  exposed as a new **`/zwiad-scan-states`** slash command.
- **Refresh** — the literal "`change_hash` incremental sync" the PLAN names:
  one cheap `getMasterListRaw` call per state detects changed bills; only changed
  bills are re-fetched and re-dispatched. Folded into the existing
  **`/zwiad-refresh`** so the operator keeps one "refresh everything I track"
  entry point.

Built **state-count-agnostic** for the all-50 goal (D49); **validated against the
7 priority states first** (CA, NY, TX, CO, VA, WA, IL), expanded by editing config.

## 2. Why this is mostly additive

The wiki/render layer is already jurisdiction-agnostic, so Phase 07 adds a source
and two CLI halves rather than reworking the core:

- `render.py:_jurisdiction_parts` already routes `US-CA` → `wiki/states/ca/bills/`.
- `Bill` already carries `session` (state bills) and `change_hash` (the LegiScan
  cursor); the federal-id validator (`Bill._check_federal_id_shape`) deliberately
  runs only for `jurisdiction == "US"`, so state ids are unconstrained by it.
- `render-classified` and `render-refreshed` are source-agnostic (they validate
  `Bill` models and write pages) — **reused unchanged** for state bills.
- `store.reindex` already indexes any jurisdiction; `items.id` is a global primary
  key, which is why state ids must be globally unique (§4).

The genuinely new pieces: `sources/legiscan.py`, `fetch-state-candidates`,
`fetch-state-refreshable`, a state branch in refresh detection, one new `Bill`
field, the `/zwiad-scan-states` command, and the `/zwiad-refresh` extension.

## 3. Architecture fit

```
/zwiad-scan-states (NEW slash command)         /zwiad-refresh (EXTENDED)
  │                                               │
  ├ fetch-state-candidates  (getSearchRaw →        ├ fetch-refreshable        (federal, unchanged)
  │   top-N bill_id → getBill → enrich →           ├ fetch-state-refreshable  (NEW: getMasterListRaw
  │   candidates.json)                             │    change_hash diff → getBill on change)
  ├ classifier / summarizer / amendment-explainer  ├ classifier / summarizer / amendment-explainer
  │   subagents (D26, reused)                      │   subagents (reused)
  └ render-classified  (REUSED, source-agnostic)   └ render-refreshed  (REUSED, source-agnostic)
```

Python makes zero LLM calls (D26); LegiScan calls are deterministic, rate-limited,
and `change_hash`-gated.

## 4. State bill identity (D48)

A state bill's `id` is the filename slug **and** the global `items.id` primary key,
so it must be globally unique across federal + all states.

**Shape:** `{state}-{year_start}-{type}-{number}` — e.g. `ca-2023-sb-362`.

Construction from a `getBill` payload:
- `state` = `bill.state` lowercased (e.g. `"CA"` → `ca`).
- `year_start` = `bill.session.year_start` (an integer; constant across a 2-year
  session, so all 2023–2024 bills share `…-2023-…`).
- `type` + `number` = the **verbatim `bill.bill_number`** split into its leading
  non-trailing-digit prefix and its trailing run of digits, both lowercased, with
  leading zeros stripped from the number:
  - `"SB362"` → `sb` + `362` → `ca-2023-sb-362`
  - `"AB1"` → `ab` + `1` → `ca-2023-ab-1`
  - `"SB0181"` → `sb` + `181` (zeros stripped) → `md-2019-sb-181`
  - `"SBX12"` (1st extraordinary session, bill 2) → `sbx1` + `2` → `ca-2023-sbx1-2`

**Special sessions are self-disambiguating.** LegiScan reflects the state's special-
session numbering directly in `bill_number` (California: `SBX1…`, `ABX2…`), and
`session.special == 1` flags it. Because the split is a lossless partition of the
verbatim `bill_number` (prefix + trailing digits == original), distinct bill numbers
yield distinct ids within a `(state, year_start)` pair. No separate special-session
suffix is needed (this supersedes the "append session_id" idea floated during
brainstorming — the bill number already carries the marker).

**Collision argument:** within one state-session, LegiScan `bill_number`s are unique;
`year_start` is constant per session; a same-year special session uses an `X<n>`
marker absent from regular numbers. Federal ids begin with an integer congress
(`118-…`); state ids begin with an alpha state code (`ca-…`) — the two never collide.

**Display:** the `Bill.bill_number` field gets a space inserted between prefix and
number for readability — `"SB362"` → `"SB 362"`, `"SBX12"` → `"SBX1 2"`.

## 5. `sources/legiscan.py` — `LegiScanSource`

Same shape as `CongressSource`: an httpx client, a tenacity `Retrying` on transient
failures, `Retry-After` honored via the existing `_wait_retry_after` pattern, and
URL redaction before logging. One instance per state, with the search query bound at
construction (a `LegiScanSource` *is* "the California source searching the AI/privacy/
cyber query"):

```python
LegiScanSource(api_key, state, *, query=None, client=None,
               base_url="https://api.legiscan.com/", max_attempts=5,
               wait_initial=1.0, wait_max=30.0, timeout=30.0)
```

**Transport.** All operations are `GET https://api.legiscan.com/?key=KEY&op=OP&…`.
The key is query-param auth only (no header auth), so the `_redact` helper is
extended to mask `key=` in addition to `api_key=` (D51 / extends D47). The response
envelope is `{"status": "OK"|"ERROR", "<container>": …}`:

- HTTP 5xx → retryable (tenacity), as in `CongressSource`.
- HTTP 429 (if it occurs) → `RateLimitError`.
- **`body.status == "ERROR"` (on an HTTP 200)** → branch on the body first: if the
  optional `alert.message` indicates quota/limit exhaustion → `RateLimitError`;
  otherwise → `SourceFetchError(alert.message or "<op> returned ERROR")`. The manual
  does not document quota-exhaustion HTTP semantics, so the client treats
  `body.status` as authoritative and never relies on a 429 or `Retry-After`
  existing (D51).

**Protocol conformance.** Implements the `Source` protocol so the shared
`enrich(source, candidate)` (which calls only `source.fetch`) type-checks:

| Method | LegiScan op | Returns | Notes |
|---|---|---|---|
| `discover(*, congress=None, since=None, limit=20)` | `getSearchRaw` | `list[Candidate]` | Ignores `congress` (per the protocol's "a source with no congress concept ignores it"); uses the construction-bound `state` + `query`. Raises `ConfigError` if `query` is unset. |
| `fetch(native_id)` | `getBill?id=<bill_id>` | `Bill` | `native_id` is the LegiScan integer `bill_id` as a string. |
| `fetch_policy_area(native_id)` | — | `None` | States need no policyArea probe — full-text search already gives recall (D50). |
| `change_hashes()` | `getMasterListRaw?state=<st>` | `dict[int, str]` | `{bill_id: change_hash}` for the state's **current** session — the refresh primitive. Not part of the `Source` protocol; an extra method. |

**`discover` mapping (`getSearchRaw`).** Response is `{status, searchresult:{summary,
results:[…]}}` where each `results[]` entry has **only** `relevance`, `bill_id`,
`change_hash` (verified — no titles/URLs). So a Candidate from discovery carries:
`source="legiscan"`, `native_id=str(bill_id)`, `jurisdiction=f"US-{STATE}"`,
`title=""` (unknown until `getBill`), `raw={"relevance":…, "change_hash":…}`. Results
are relevance-ranked; the CLI takes the top `limit`. **The federal title-based
`keyword_filter` is not used** — the search query is the recall stage.

**Pagination.** `getSearchRaw` returns up to 2000 results/page; v1 reads page 1 only
(the relevance-ranked head is what we cap to `limit`), logging `summary.count` when it
exceeds what we kept — mirroring the federal single-request-with-warning discipline
(D33). Deeper pagination is a deferred follow-up.

## 6. `getBill` → `Bill` mapping

Per-field mapping lives in `LegiScanSource._to_bill` (per D22, the source owns its
mapping). Verified field paths:

| `Bill` field | LegiScan source | Mapping notes |
|---|---|---|
| `id` | `state` + `session.year_start` + `bill_number` | §4 construction. |
| `jurisdiction` | `state` | `f"US-{state.upper()}"`. |
| `legiscan_bill_id` | `bill_id` | **New field (§7)** — the stable native cursor key for refresh. |
| `bill_number` | `bill_number` | Reformatted for display (space inserted). |
| `title` | `title` | |
| `session` | `session.session_name` | e.g. `"2023-2024 Regular Session"`. |
| `congress` | — | `None` (state bills have no congress). |
| `chamber` | `body` | Origin chamber text (`"S"`/`"H"`/`"A"`). |
| `status` | `status` (int) → text | Code map: 0=Prefiled, 1=Introduced, 2=Engrossed, 3=Enrolled, 4=Passed, 5=Vetoed, 6=Failed. |
| `enacted` | `status == 4` OR a `progress[].event == 8` (Chaptered) | There is **no distinct "Enacted" code** — enactment = Passed and/or the Chaptered progress event (verified). |
| `public_law` | chapter, if surfaced | Most states don't expose a public-law number via the API; left `None` when absent (no fabrication). |
| `sponsors` | `sponsors[].name` | Primary first by `sponsor_type_id == 1`, then `sponsor_order`. |
| `introduced_date` | first `history[]` date / `status_date` | |
| `actions` | `history[]` → `Action` | `date`, `text=action`, `chamber`. Already oldest→newest? LegiScan `history` is chronological; sort defensively like the federal timeline. |
| `amendments` | `amendments[]` → `Amendment` | `number=title`, `chamber`, `status` from `adopted`, `latest_action_date=date` (guarding the `"0000-00-00"` placeholder → `None`). `what_changed` filled by the amendment-explainer subagent. |
| `text_versions` | `texts[]` → `TextVersion` | `code=type`, `date` (guard `"0000-00-00"`), `url` (prefer `state_link`, fall back to `url`). |
| `change_hash` | `change_hash` | The authoritative state refresh cursor. |
| `update_date` | `status_date` | Secondary/display; **not** the cursor for state (change_hash is). |
| `related_bills` | `sasts[]` | `f"{type}: {sast_bill_number}"` (e.g. `"Same As: SB10"`). |
| `sources` | `url` | `{"LegiScan": bill.url}` (+ `state_link` as `{"State source": …}` when present). |
| `summary` | `description` | Provisional, like the federal CRS summary (D23); the summarizer subagent overwrites it. |

`votes[]` (roll calls) are available but **not mapped in v1** — state legislative
history (the GovInfo/CREC-backed `LegHistory`) is federal-only this phase; mapping
state votes into a timeline/leg-history section is a deferred follow-up (§16).

Defensive parsing matches `CongressSource`: every untyped JSON scalar is coerced, the
`"0000-00-00"` placeholder date → `None`, and string-typed integers (`bill_type_id`,
`committee_id`) are tolerated.

## 7. Model & schema changes

- **`Bill.legiscan_bill_id: int | None = None`** — the stable LegiScan `bill_id`,
  stored so refresh can match a wiki page against a `getMasterListRaw` entry (the
  wiki id does not contain it). `None` for federal bills. Round-trips automatically:
  `to_frontmatter` uses `model_dump(exclude_none=True)`, so it serializes only when
  set; `from_page`/`parse_wiki_item` reads it back. No change to `to_frontmatter`/
  `from_page` code is required.
- **No new body-only field, no leg_history change.** `session` already exists.
- **Optional store column (deferred):** `legiscan_bill_id` need not be indexed in
  SQLite for v1 (refresh reads frontmatter, not the index). Adding an indexed column
  is a follow-up only if a query needs it.

D20 (byte-identical render) holds: the new field is metadata, serialized
deterministically, dropped when `None`.

## 8. Backfill flow — `fetch-state-candidates`

New CLI command (the deterministic discovery half):

```
fetch-state-candidates --state ca [--limit N] [--query "…"] [--out DIR] [--topics PATH]
```

1. Build the search query: explicit `--query` if given, else an OR-join of the
   `topics.yaml` seeds (`reference/loader.load_reference(topics).seeds`) into a single
   LegiScan full-text query string (URL-encoded by httpx). Multi-word seeds are
   double-quoted as exact phrases (`"facial recognition"`); single-word seeds are bare
   (stemming applies). The exact operator syntax (uppercase `OR`, quoted phrases,
   stemming) is MEDIUM-confidence from research (§17) and is validated live in UAT
   step 1 before relying on it.
2. `LegiScanSource(api_key, state, query=…)` → `discover(limit=N)` → top-N Candidates
   (relevance-ranked `bill_id`s).
3. `enrich(source, candidate)` for each → full `Bill` (this is the `getBill` spend;
   bounded by `--limit` to cap both quota and downstream classifier plan usage).
4. `stage_json([bill.model_dump(mode="json") for bill in bills], "candidates.json")`.

The interactive `/zwiad-scan-states` command then runs the classifier (on title +
`description` summary, D28), and for in-scope bills the summarizer + amendment-
explainer, exactly as `/zwiad-backfill` does — then `render-classified` (reused)
validates `topics` and writes the pages, and `reindex` runs.

**Per-state limit** bounds classifier plan usage — the real 50-state constraint (D49),
not LegiScan quota. `/zwiad-scan-states` loops the configured states, each capped.

## 9. Refresh flow — `fetch-state-refreshable` + state detection

New CLI command (the deterministic refresh-detection half):

```
fetch-state-refreshable [--wiki wiki] [--out DIR]
```

1. Scan `wiki/states/**/bills/*.md`; parse each via `from_page`; keep tracked `Bill`s
   that have a `legiscan_bill_id`. Group by `state` (derived from `jurisdiction`).
   Per-page errors are isolated and counted (matching `fetch-refreshable`).
2. For each state: one `getMasterListRaw?state=<st>` → `{bill_id: change_hash}` for the
   **current** session (the manual's "current session" shortcut — appropriate because
   we track forward-from-now, D44; prior-session bills fall out of the current list and
   are simply not polled, which is correct for archived sessions).
3. For each tracked bill: if its `legiscan_bill_id` is in the map **and** the map's
   `change_hash` differs from the stored `change_hash` → it changed. Only then
   `getBill` to fetch fresh. Bills whose hash matches → skipped (no `getBill`). Bills
   absent from the current masterlist → skipped (archived).
4. For each changed bill, compute the subagent triggers and stage an entry shaped like
   `fetch-refreshable`'s (`bill_id`, `prev`, `fresh`, `needs_classifier`,
   `needs_summarizer`, `changed_amendment_numbers`).

**State refresh detection (`pipeline/refresh.py`).** `detect_refreshable` gates on
`prev.update_date == fresh.update_date` (federal cursor) — wrong for state, where the
authoritative cursor is `change_hash`. Add a sibling that gates on `change_hash` and
reuses the existing trigger logic:

```python
def detect_state_refreshable(prev: Bill, fresh: Bill) -> RefreshableBill | None:
    if not prev.tracking:
        return None
    if prev.change_hash == fresh.change_hash:   # cheap gate: LegiScan change_hash
        return None
    text_changed = prev.summary_hash != fresh.summary_hash
    changed = _amendment_delta(prev.amendments, fresh.amendments)
    return RefreshableBill(prev=prev, fresh=fresh,
                           needs_classifier=text_changed,
                           needs_summarizer=text_changed,
                           changed_amendment_numbers=changed)
```

This reuses `_amendment_delta`, `summary_hash`, and `RefreshableBill` unchanged;
`_amendment_delta` stays private but is called from within the same module. (In
practice the `getMasterListRaw` diff in step 3 already established change, so this
mainly computes triggers; the gate is kept for symmetry and for direct unit testing.)

**Render half — reused.** `render-refreshed` already validates `prev`+`bill`,
preserves `leg_history` (a no-op for state bills, which have none this phase),
applies the classifier flip, re-stamps `summary_hash`/`amendments_count`, writes, and
reindexes. The fresh state bill carries the **new** `change_hash` and
`legiscan_bill_id` (echoed through by the subagent step), so the next refresh diffs
correctly. No change to `render-refreshed` is required.

## 10. Slash commands

- **`/zwiad-scan-states` (new)** — `.claude/commands/zwiad-scan-states.md`. The state
  analog of `/zwiad-backfill`: for each configured state (capped by `--limit`), run
  `fetch-state-candidates`, dispatch the classifier subagent, then summarizer +
  amendment-explainer for in-scope bills, hand back `classified.json`, run
  `render-classified`. Restricted subagent toolset is unchanged (the existing
  classifier/summarizer/amendment-explainer agents are source-agnostic — they read a
  `Bill`'s title/summary/amendments, which look the same for state bills).
- **`/zwiad-refresh` (extended)** — `.claude/commands/zwiad-refresh.md`. After the
  existing federal `fetch-refreshable` step, also run `fetch-state-refreshable`; union
  the two `refreshable.json` sets; dispatch subagents on the union; run
  `render-refreshed` once over all entries. One operator command refreshes the whole
  watchlist.

## 11. Config & scope (D49)

- `[states].enabled` stays the explicit active list. Ship with the 7 priority states;
  **expand coverage by editing the list** (the phased rollout). `LegiScanSource`
  accepts any LegiScan-valid 2-letter abbreviation.
- Add `Settings.require_legiscan_api_key()` (mirrors `require_congress_api_key` /
  `require_govinfo_api_key`) raising `ConfigError` with the signup hint when unset.
- `getSessionList` is **not** required for v1: discovery uses `year=2` (current) and id
  construction reads `session.year_start` straight off `getBill`; refresh uses the
  `getMasterListRaw?state=` current-session shortcut. (`getSessionList` is noted as the
  upgrade path if pinning a specific `session_id` ever becomes necessary.)

## 12. Decisions to log (`DECISIONS.md`)

- **D48** — State bill id = `{state}-{year_start}-{type}-{number}`, `type`+`number`
  from splitting the verbatim `bill_number`; special sessions self-disambiguate via
  the state's `X<n>` marker in `bill_number`; leading zeros stripped from `number`.
  Extends D21. Adds `Bill.legiscan_bill_id` as the stable native cursor key.
- **D49** — Target coverage = all 50 states, phased rollout (priority-7 first);
  supersedes D12's 7-state scope. Code is state-count-agnostic; rollout is staged via
  `[states].enabled`. The binding constraint at scale is classifier/summarizer plan
  usage (D26), not LegiScan's 30k/month quota (steady-state ≈ 4k/month at 50 states).
- **D50** — LegiScan **query API** (`getSearchRaw` discovery + `getMasterListRaw`
  `change_hash` refresh + `getBill` enrich), not the bulk dataset API. `change_hash`
  is the state refresh cursor (the `updateDate` analog). `getSearchRaw`'s server-side
  full-text query is the state recall stage, replacing the federal title
  `keyword_filter` (which can't apply — `getSearchRaw` returns no titles).
- **D51** — LegiScan signals failure as HTTP 200 + `{"status":"ERROR", alert?}`; the
  client branches on `body.status` first (quota-message ERROR → `RateLimitError`, other
  ERROR → `SourceFetchError`) and never relies on a 429 or `Retry-After` existing. The
  `_redact` helper masks `key=` as well as `api_key=` (extends D46/D47).

## 13. File map

**New**
- `src/zwiadbrain/sources/legiscan.py` — `LegiScanSource`.
- `.claude/commands/zwiad-scan-states.md` — backfill slash command.
- `tests/fixtures/legiscan/` — `getSearchRaw.json`, `getMasterListRaw.json`,
  `getBill.json` (CA SB 362 — the Delete Act), plus a special-session and an
  error-envelope fixture.
- `tests/test_legiscan.py` — source unit tests.
- `tests/test_state_id.py` — id-construction unit tests (or a section in test_legiscan).

**Changed**
- `src/zwiadbrain/models.py` — add `Bill.legiscan_bill_id`.
- `src/zwiadbrain/sources/_redact.py` — mask `key=` too.
- `src/zwiadbrain/pipeline/refresh.py` — add `detect_state_refreshable`.
- `src/zwiadbrain/cli.py` — add `fetch-state-candidates`, `fetch-state-refreshable`.
- `src/zwiadbrain/config.py` — add `require_legiscan_api_key()`.
- `.claude/commands/zwiad-refresh.md` — add the state pass.
- `DECISIONS.md` — D48–D51.
- `ARCHITECTURE.md`, `docs/PLAN.md` status notes, `zwiadbrain.toml` comments.
- `tests/test_refresh.py`, `tests/test_render.py`, `tests/test_schema.py` — state
  cases (round-trip a state Bill, reindex jurisdiction `US-CA`, state refresh detection).

**Unchanged (reused)** — `pipeline/render.py`, `wiki/templates.py`, `wiki/schema.py`,
`store.py`, `pipeline/enrich.py`, `render-classified`, `render-refreshed`, the three
existing subagents.

## 14. Test plan (offline, `respx` + fixtures — how `CongressSource` is tested)

- **Source mapping:** `getBill.json` (CA SB 362) → `Bill` with `id == "ca-2023-sb-362"`,
  `jurisdiction == "US-CA"`, `legiscan_bill_id` set, `bill_number == "SB 362"`,
  `session` populated, `congress is None`, sponsors/actions/amendments/text_versions
  mapped, `sources["LegiScan"]` set, `change_hash` set.
- **Status/enacted:** `status==4` → `enacted True`; a Chaptered progress event →
  `enacted True`; `status==1` → `enacted False`.
- **id construction:** `SB362`→`sb-362`, `AB1`→`ab-1`, `SB0181`→`sb-181`,
  `SBX12`→`sbx1-2`; full ids across two states don't collide; a federal `118-hr-1`
  and a state `ca-2023-…` coexist in `reindex` without primary-key conflict.
- **Discovery:** `getSearchRaw.json` → top-N Candidates with `native_id`=bill_id,
  empty title, `change_hash` in `raw`; `limit` respected; relevance order preserved.
- **Errors/redaction:** `{"status":"ERROR","alert":{"message":"…limit…"}}` →
  `RateLimitError`; a non-quota ERROR → `SourceFetchError`; HTTP 5xx retried then
  `SourceFetchError`; a logged URL has the key masked (`key=REDACTED`).
- **Refresh detection:** `detect_state_refreshable` returns `None` when `change_hash`
  matches; returns triggers when it differs (summary change → classifier+summarizer;
  amendment delta → explainer); untracked `prev` → `None`.
- **Round-trip:** render a state `Bill` → path `wiki/states/ca/bills/ca-2023-sb-362.md`;
  `from_page` re-parses with `legiscan_bill_id` intact; `to_frontmatter` drops it for a
  federal bill; re-render is byte-identical (D20).

## 15. Live UAT (key is in `.env`)

1. `fetch-state-candidates --state ca --limit 5` → inspect `candidates.json`: real CA
   bills, relevance-ranked, fully enriched.
2. `/zwiad-scan-states --state ca --limit 5` end-to-end → classifier verdicts →
   in-scope bills rendered under `wiki/states/ca/bills/` → inspect a page (CA SB 362,
   the Delete Act, is the canonical target — it appears in the law brain).
3. `fetch-state-refreshable` on the fresh pages → `[]` (clean idempotent no-op).
4. Mutate a tracked state bill's `change_hash` to a stale value → `fetch-state-refreshable`
   detects exactly that bill with the right triggers; `getBill` spent only on it.
5. Confirm `/zwiad-refresh` runs both federal and state passes and reports a unified
   count.
6. Spot-check LegiScan quota usage stayed negligible (a handful of queries).

## 16. Out of scope / deferred (named, not silent)

- **State legislative history** (votes/roll-calls → a `LegHistory`-style section).
  `getBill` exposes `votes[]`, but the GovInfo/CREC research pipeline is federal-only;
  state leg-history is a separate future phase.
- **`getSearchRaw` pagination beyond page 1** — v1 caps to the relevance head; deeper
  recall is a follow-up (the D33/D44 forward-from-now posture).
- **Bulk dataset API** (`getDataset`) — rejected for v1 (D50): whole-session base64 ZIP,
  coarse `dataset_hash` granularity, no per-bill change cursor.
- **Pinning `session_id` via `getSessionList`** — v1 uses the current-session shortcut;
  pin if session-boundary rollover ever causes a missed refresh.
- **Indexing `legiscan_bill_id` in SQLite** — added only if a query needs it.
- **Enforcement / state AGs** — that is PHASE-08.

## 17. Risks & open questions

- **`getMasterListRaw` "current session" rollover** (manual: "use with caution"). At a
  session boundary the current list flips to the new session; prior-session tracked
  bills stop being polled. Acceptable for forward-from-now tracking (D44); the
  `getSessionList` pin is the escape hatch if it bites.
- **Quota-exhaustion HTTP semantics are undocumented.** Mitigated by branching on
  `body.status` (D51); validated in UAT only indirectly (we won't deliberately exhaust
  the quota).
- **Special-session `bill_number` formatting is a per-state convention**, not an API
  guarantee (verified for CA). The id rule (split verbatim `bill_number`) is robust to
  formatting differences because it never interprets the marker — it only partitions
  the string. Other states' special-session formats will be checked during the 50-state
  rollout, not v1.
- **`status` value type varies** (string vs int across operations). Parse defensively.
- **Full-text query operator syntax is MEDIUM-confidence.** LegiScan's
  `legiscan.com/fulltext-search` (the authoritative operator reference) sits behind a
  Cloudflare challenge that blocked verbatim fetch; the operators (default-AND,
  explicit `OR`, quoted exact phrases, automatic stemming) come from search snippets.
  The query builder (§8) is validated against the live API in UAT step 1 before the
  full discovery run; if the syntax differs, the only fix is the query-builder string
  (not the architecture).
- **`bill_number` with no trailing digits** (rare letter-suffixed numbering in some
  states) would split to an empty `number`. The id builder guards this defensively
  (logs and falls back rather than emitting a malformed id); the 7 priority states use
  `type`+digits numbering, so this is a 50-state-rollout edge, not a v1 blocker.
- **Classifier plan usage at 50-state scale** is the real cost. Mitigated by per-state
  `--limit` and the phased rollout (D49); revisit cadence/limits after the 7-state UAT.
```