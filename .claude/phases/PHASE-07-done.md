# Phase 07 — State legislation via LegiScan (backfill + refresh)
Status: DONE

> Full design: docs/superpowers/specs/2026-05-29-phase07-state-legislation-design.md
> Full plan:   docs/superpowers/plans/2026-05-29-phase07-state-legislation.md
> Decisions:   D48 (state id + legiscan_bill_id), D49 (50-state scope),
>              D50 (query API + change_hash cursor), D51 (error/redaction).

## Outcome (2026-05-29)
PHASE-07 shipped on `feature/phase-07-state-legislation` (v0.7.0, 22 commits, 413 tests
+ ruff + pyright strict all green). State bills are now first-class tracked pages via a
new `LegiScanSource` (query API: `getSearchRaw` discovery + `getMasterListRaw` change_hash
refresh + `getBill` enrich), two deterministic CLI halves (`fetch-state-candidates`,
`fetch-state-refreshable`), a new `/zwiad-scan-states` slash command, and a state pass
folded into `/zwiad-refresh`. The wiki/render layer needed no changes (already
jurisdiction-agnostic); `render-classified`/`render-refreshed` were reused unchanged.

Built state-count-agnostic for the 50-state goal (D49); validated against CA first.

**Executed via subagent-driven development** — a fresh implementer subagent per task with
controller spec/quality review between tasks. Two review-caught fixes: the `/zwiad-refresh`
state pass would have overwritten the federal `refreshable.json` (fixed to a two-file
merge), and a structural test asserting the old 6-step `/zwiad-refresh` layout was updated
for the new 7-step federal+state flow. An independent opus spec-review of the getBill
mapping (T5) confirmed compliance and prompted added amendment/`0000-00-00`-date coverage.

**Live UAT (real LegiScan API, CA):**
- `fetch-state-candidates --state ca` returned 3 genuinely on-topic bills via the
  seed-OR full-text query — resolving the one MEDIUM-confidence risk (query operator
  syntax) against the real API.
- `getBill` mapping verified on real data: `ca-2025-sb-53` (Transparency in Frontier AI
  Act, status Passed → enacted=True ✓), `ca-2025-ab-1064` (LEAD for Kids, Vetoed →
  enacted=False ✓), `ca-2025-ab-1337` (Information Practices Act, Engrossed). Correct id
  shape, `US-CA` jurisdiction, session, `congress=None`, sponsors, dual sources.
- Full interactive pipeline run end-to-end: classifier (all 3 in-scope: ai/ai/privacy),
  summarizer (plain-language prose), `render-classified` → 3 committed CA pages with full
  status timeline + text-version links + `legiscan_bill_id`/`change_hash`/`summary_hash`.
- `fetch-state-refreshable` idempotency: 0 refreshable on fresh pages (change_hash matches).
- `fetch-state-refreshable` stale detection: mutating one page's change_hash → exactly 1
  detected, `getBill` spent only on it; restored.

## Tasks
- [x] T1  — _redact: mask key= as well as api_key=
- [x] T2  — models: add Bill.legiscan_bill_id
- [x] T3  — ids: build_state_bill_id + format_state_bill_number
- [x] T4  — LegiScanSource transport + error/redaction
- [x] T5  — LegiScanSource.fetch (getBill -> Bill mapping)
- [x] T6  — LegiScanSource.discover (getSearchRaw)
- [x] T7  — LegiScanSource.change_hashes (getMasterListRaw)
- [x] T8  — config: require_legiscan_api_key
- [x] T9  — refresh: detect_state_refreshable
- [x] T10 — cli: fetch-state-candidates
- [x] T11 — cli: fetch-state-refreshable
- [x] T12 — slash commands: /zwiad-scan-states (new) + /zwiad-refresh (extend)
- [x] T13 — DECISIONS.md D48-D51 + ARCHITECTURE/PLAN/toml updates
- [x] T14 — quality gate + version bump 0.7.0 + PHASE-07 done
- [x] T15 — live UAT (CA priority states)

## Acceptance Criteria
- [x] A LegiScan getBill fixture (and real CA data) maps to a Bill with id `ca-2025-sb-53`,
  jurisdiction `US-CA`, legiscan_bill_id set, byte-identical re-render (D20).
- [x] getSearchRaw discovery yields relevance-ordered bill_id candidates; getMasterListRaw
  change_hash diffing re-fetches only changed bills (idempotency + stale both validated).
- [x] /zwiad-scan-states renders real CA pages; /zwiad-refresh covers federal + state.
- [x] ruff + pyright (strict) + pytest all green (413 passing); v0.7.0 tagged.
- [x] DECISIONS.md carries D48-D51.

## Decisions Made This Phase
- D48 — state bill id `{state}-{year_start}-{type}-{number}` + `Bill.legiscan_bill_id`; extends D21.
- D49 — target = all 50 states, phased rollout (priority-7 first); supersedes D12.
- D50 — LegiScan query API; change_hash is the state refresh cursor; getSearchRaw is the recall stage.
- D51 — body-status-first error handling (HTTP 200 + {"status":"ERROR"}); `_redact` masks `key=`.

## Follow-ups (named, deferred — not blocking)
- State legislative history / roll-call votes (getBill exposes votes[]; GovInfo pipeline is federal-only).
- getSearchRaw pagination beyond page 1 (v1 caps to the relevance head, forward-from-now per D44).
- session_id pinning via getSessionList (v1 uses the current-session shortcut).
- Expand `[states].enabled` beyond the priority 7 toward all 50 (D49 rollout).
