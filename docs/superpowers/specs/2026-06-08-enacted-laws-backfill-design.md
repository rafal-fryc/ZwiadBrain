# Enacted-laws backfill campaign (federal 116–118 + 7 states, 2019–2024)

> Design spec. A deliberate, per-unit backfill of **enacted** AI/privacy/cybersecurity
> laws from prior years. Builds new *enacted-first discovery* on top of the existing
> resumable classify→summarize→render pipeline (PR #13); adds no new processing code.
> For reasoning conventions see `DECISIONS.md` (append-only, authoritative).

## 1. Goal

Cover **all** relevant enacted laws from prior years — never bills that died.

- **Subject scope:** AI, privacy, cybersecurity (the existing classifier rubric, D17).
- **Status scope:** *enacted only* — became law. Excludes pending, failed, vetoed,
  and the current in-progress period (119th Congress / 2025–26 state sessions stay
  with the routine `/zwiad-backfill` + `/zwiad-scan-states`).
- **Jurisdiction × period matrix:**
  - Federal: 116th (2019–20), 117th (2021–22), 118th (2023–24).
  - States: CA, NY, TX, CO, VA, WA, IL — every session covering 2019–2024.
- **Depth:** full bill page per enacted law (summary, status timeline, amendments).
  Significant laws are *flagged* for a later, per-law-approved `/zwiad-leg-history`
  pass — leg-history is **not** part of this campaign.

**Definition of done:** every enacted AI/privacy/cyber law in the matrix has either a
reviewed wiki page or a logged reject reason; zero non-enacted bills ingested; each
(jurisdiction × period) unit reviewed and committed independently.

## 2. Why this needs new code (the gap)

"Cover all relevant enacted laws" is a **completeness** goal over the enacted set.
Current discovery optimizes the opposite:

- **Federal** `CongressSource.discover(congress=N)` lists *all* bills newest-updated
  first (no status filter); `enacted` is computed only later, during enrichment
  (`congress.py:432`). Sweeping a full Congress means ~10–15k bills across 40+ pages,
  enriching mostly non-enacted bills.
- **State** `LegiScanSource.discover()` hard-codes `getSearchRaw?...&year=2` — the
  **current session only** (`legiscan.py:328`). No prior-session path; full-text search
  is recall-limited (can miss an enacted law whose text lacks a seed) and enriches
  non-enacted hits before status is known.

So "enacted-only from prior years" is not a flag — it requires deliberate discovery.

## 3. Chosen approach — enacted-first discovery (Approach A)

Filter to the **complete enacted universe before** spending any enrichment/classifier
budget. The only new code is discovery; everything downstream is reused verbatim.

- **Federal:** discover via Congress.gov `/law/{congress}` — lists *only* enacted public
  laws (~300–500/Congress). Far smaller, precise, complete.
- **State:** `getSessionList` → `getMasterListRaw(id=session_id)` per prior session →
  keep `status == 4 (Passed)`. The masterlist already carries `status` + title +
  description, so the **complete** enacted set is filtered with **one call per session
  and zero per-bill fetches**.

**Rejected alternatives** (logged in DECISIONS):
- *B — enrich-then-filter:* reuse existing discovery, drop non-enacted after enrichment.
  Lightest code, but federal sweeps thousands of discarded bills and state stays
  recall-limited. Compromises the completeness goal.
- *C — hybrid:* federal `/law`, state full-text + year + post-filter. Front-loads the
  federal win but keeps the state recall gap.

## 4. New discovery components

### 4.1 Federal — `congress.py`
```
discover_laws(congress: int, *, limit: int = 250, max_pages: int = 1) -> list[Candidate]
```
- `GET /law/{congress}` (and/or `/law/{congress}/pub`), paginated like `discover`
  (offset sweep, de-dupe by `native_id`, truncation logged — same discipline).
- Emits `Candidate`s in the existing `congress/type/number` `native_id` format, so
  `fetch()` / `enrich` / id-mapping work unchanged.
- **Live-validation task (PHASE-A first step):** confirm the exact `/law/{congress}`
  JSON shape (field names for billType/number, pagination `count`).

### 4.2 State — `legiscan.py`
```
list_sessions() -> list[Session]                       # getSessionList for self.state
list_session_enacted(session_id: int, *, limit) -> list[Candidate]   # getMasterListRaw(id=)
```
- `Session` = `{session_id, year_start, year_end, special, session_name}` (small frozen
  dataclass, like `StateLegHistoryInputs`).
- `list_session_enacted` reads the numeric-keyed `masterlist` (same container shape as
  `change_hashes()`), keeps rows with `status == 4`, and returns `Candidate`s carrying
  `bill_id`, `change_hash`, `title`, `description` from the masterlist row.
- **Live-validation task (PHASE-B first step):** confirm `getMasterListRaw?id=<session_id>`
  returns a per-row `status` field and that `id=` selects a *prior* session.

### 4.3 New CLI fetch halves — `cli.py` (mirror `fetch-candidates`)
```
fetch-enacted-candidates       --congress N [--limit] [--max-pages] [--skip-existing]
                               [--recall-prefilter] [--out] [--wiki]
fetch-state-enacted-candidates --state <st> --year <YYYY> [--limit] [--skip-existing]
                               [--recall-prefilter] [--out] [--wiki]
```
- Each: discover (enacted-first) → optional recall pre-filter → `enrich` → write
  `candidates.json` under `data/runs/<id>/`. Identical staging contract to
  `fetch-candidates`, so the downstream steps are byte-for-byte the same.
- `fetch-state-enacted-candidates` resolves `--year` → the session(s) covering that year
  via `list_sessions()`, then unions their enacted candidates.

### 4.4 Recall decision — classifier is the sole topic gate by default
The enacted universe is already tiny, so we **classify every enacted law** rather than
keyword-pre-filter — maximizing completeness so no relevant law is dropped for lacking a
title seed. `--recall-prefilter` is an opt-in cost control (applies `recall_filter` on
title+description) for unusually large sessions. Cost envelope: federal ≈ 300–500 haiku
classifier dispatches/Congress × 3; state smaller per session — acceptable under per-unit
batching (D26 plan-usage model).

## 5. Reused unchanged (no new code)

`classifier` subagent → `verdicts.json` → `apply-verdicts` → `record-rejects` (reject
ledger, D82/D83) → `batch-summarizer` → `summaries.json` → `apply-summaries` →
`amendment-explainer` → `render-classified` → `reindex`. Resumable verdict/summary tails
(D83) and the negative-cache reject ledger carry over directly.

**State `--skip-existing` parity:** add the state-side equivalent of the federal
`--skip-existing` (existing-wiki + reject-ledger drop) keyed by state bill id, so
re-running a unit re-stages nothing already tracked or cached-rejected.

## 6. The unit model & orchestration

**A unit = one (jurisdiction × period)** — the atom reviewed and committed.
- Federal: `116`, `117`, `118` (3 units).
- State: `(state, session)` resolved from `getSessionList` for sessions overlapping
  2019–2024 (~2–3 sessions × 7 states ≈ 14–21 units). Total campaign ≈ 17–24 gates.

**Two thin new slash commands** (routine commands untouched — separate concerns):
- `/zwiad-backfill-enacted <congress>`
- `/zwiad-backfill-enacted-state <st> <year>`

Each runs the resumable 7-step flow against enacted discovery and **stops before commit**
for review. One unit = one `data/runs/<id>/` = one commit.

**Per-unit review gate (before commit):** enacted candidates found, classified in vs out
*with reject reasons*, pages rendered, leg-history flags raised. Commit or send back, then
the next unit starts.

**Campaign tracker:** `docs/backfill/enacted-campaign.md` — checklist of all units with
status (pending / in-review / done) + counts. Source of truth for campaign progress;
resumable across sessions. Distinct from the `.claude/phases/` build files.

## 7. Inclusion / "enacted" rules

- **Federal:** returned by `/law/{congress}` (became public law) → `bill.enacted == True`,
  carries `public_law`. Includes HR/S/HJRES/SJRES that became law; non-law resolutions are
  not returned by the endpoint.
- **State:** masterlist `status == 4 (Passed)`, confirmed at enrich by the existing
  `enacted` flag (status==4 **or** Chaptered event 8, `legiscan.py:380`). Vetoed (5) /
  Failed (6) excluded. A post-enrich guard drops obvious non-law resolutions
  (ceremonial/memorial) by bill-number/type signal.

## 8. Leg-history flagging (follow-up, not this campaign)

After each unit renders, append significant laws to `docs/backfill/leg-history-queue.md`:
heuristic = has `public_law`/chaptered **and** a named act or high-salience title signal.
Human-reviewable list. The actual `/zwiad-leg-history` runs are a **separate, per-law-
approved** pass (matches the chosen depth: "bill page now, leg-history for a flagged
subset").

## 9. Error handling & idempotency

- Discovery failures surface as the existing typed errors (`SourceFetchError`,
  `RateLimitError`); per-unit isolation means one unit failing never poisons another.
- `--skip-existing` (wiki + reject ledger) makes unit re-runs idempotent; resumable
  verdict/summary tails (D83) handle mid-unit interruption.
- `stage_json` run-dir convention reused; no change to the D20 byte-identical render
  invariant (only `topics`/`summary`/`what_changed` are set by subagents, as today).

## 10. Test plan (offline, mocked transport — `respx`/httpx mock + fixtures)

- `discover_laws`: mocked `/law/{congress}` payload → expected `Candidate`s + id format;
  pagination + truncation-log path.
- `list_sessions`: mocked `getSessionList` → `Session` list.
- `list_session_enacted`: mocked `getMasterListRaw(id=)` with mixed `status` → keeps only
  `status == 4`; skips non-bill masterlist members (parity with `change_hashes`).
- enacted-filter + post-enrich resolution guard unit tests.
- Both CLI commands via `CliRunner` (mock source) — happy path + `--skip-existing` +
  malformed-input/`--out` override, mirroring `test_cli.py`.
- One end-to-end fixture per source (a known prior enacted law) validating mapping.
- All existing 79 tests stay green; new code does not reduce coverage.

## 11. Phasing (`.claude/phases/`, one active at a time, approval between)

- **PHASE-A — Federal enacted discovery:** `discover_laws` + `fetch-enacted-candidates` +
  tests; validate `/law` live on one Congress.
- **PHASE-B — State enacted discovery:** `list_sessions` + `list_session_enacted` +
  `fetch-state-enacted-candidates` + state `--skip-existing` parity + tests; validate
  `getSessionList`/masterlist `status` live.
- **PHASE-C — Orchestration & tracking:** the two slash commands, `enacted-campaign.md`
  tracker, `leg-history-queue.md`, README/ARCHITECTURE notes, DECISIONS entry.
- **PHASE-D — Execute the campaign:** run units, per-unit review + commit, paced per
  review appetite.

PHASE-A→C are build (~2–3 focused sessions); PHASE-D is the backfill run itself.

## 12. Decisions to log (`DECISIONS.md`, next is D84)

- **D84 — Enacted-first discovery for the prior-years backfill.** New `/law/{congress}`
  (federal) + session-masterlist `status==4` (state) discovery; classifier is the sole
  topic gate by default (completeness over the small enacted set). Alternatives B/C
  (enrich-then-filter, hybrid) rejected for compromising the completeness goal.
- **D85 — Per-(jurisdiction × period) unit batching with review gates.** Dedicated
  `/zwiad-backfill-enacted[-state]` commands separate from routine scan; campaign tracked
  in `docs/backfill/enacted-campaign.md`; leg-history deferred to a flagged per-law pass.

## 13. File map

```
src/zwiadbrain/sources/congress.py    + discover_laws()
src/zwiadbrain/sources/legiscan.py    + list_sessions(), list_session_enacted(), Session
src/zwiadbrain/cli.py                 + fetch-enacted-candidates, fetch-state-enacted-candidates
.claude/commands/zwiad-backfill-enacted.md         (new)
.claude/commands/zwiad-backfill-enacted-state.md   (new)
docs/backfill/enacted-campaign.md     (new — campaign tracker)
docs/backfill/leg-history-queue.md    (new — flagged follow-ups)
tests/test_sources_congress.py        + discover_laws cases
tests/test_sources_legiscan.py        + sessions / enacted-masterlist cases
tests/test_cli.py                     + two new fetch commands
DECISIONS.md                          + D84, D85
```

## 14. Out of scope / deferred (named, not silent)

- Legislative history for enacted laws (separate, per-law-approved `/zwiad-leg-history`).
- The current in-progress period (119th / 2025–26) — routine scan commands own it.
- Enforcement actions, law-brain commentary — unchanged by this campaign.
- All 50 states — only the 7 already-enabled states; widening is a config/`enabled` change later.

## 15. Risks & open questions

- **`/law/{congress}` response shape** — validated live in PHASE-A before relying on it.
- **`getMasterListRaw?id=` status reliability** — validated live in PHASE-B; if `status`
  is ever absent/stale for a session, fall back to a bounded post-enrich `enacted` filter
  for that session (logged, never silent).
- **Classifier volume** — if a Congress's enacted set is larger than expected, enable
  `--recall-prefilter` for that unit (logged as a cost decision).
- **State session granularity** — `getSessionList` may expose special sessions; include
  any session whose year range overlaps 2019–2024.
