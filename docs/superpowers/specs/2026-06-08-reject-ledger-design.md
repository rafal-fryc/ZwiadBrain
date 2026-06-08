# Reject Ledger (negative classification cache) — design

**Date:** 2026-06-08
**Status:** Approved (design), pending implementation plan
**Decision log:** to be recorded as D82

## Problem

`fetch-candidates --skip-existing` (federal) only drops candidates that already have an
**in-scope** committed wiki page. Out-of-scope (rejected) bills leave no trace, so every
re-sweep re-fetches and **re-classifies** them — ~13k plan tokens per reject. The pilot
(Stage 0) re-classified the same 9 out-of-scope bills on a second `--skip-existing` fetch.
For a federal back-catalog sweep (`--max-pages > 1`) this is the dominant cost. State
discovery (`fetch-state-candidates`) is worse: it has **no** skip-existing at all, so it
re-stages even already-tracked in-scope bills.

## Goal

Persist a **reject ledger** of classified-out bills so future fetches skip them — until the
bill actually changes, at which point it is re-classified. Cover **federal and state**.

## Non-goals

- Enforcement actions (forward-from-now + matter-consolidation model, D52 — a reject cache
  fits poorly; explicitly out of scope).
- Changing classifier behavior, the recall filter, or any rendering.
- Caching anything other than the classify decision (no summary caching, etc.).

## Key facts grounding the design

- `Candidate` already carries `update_date` (the Congress `updateDate` change cursor) and,
  for LegiScan, the `change_hash` in `candidate.raw["change_hash"]` (`getSearchRaw` returns
  `relevance`/`bill_id`/`change_hash` per result). So **both sources expose their
  invalidation cursor at discovery time, before enrichment** — no extra API call.
- The refresh pipeline already defines the "any-change gate": federal compares
  `prev.update_date == fresh.update_date`; state compares `prev.change_hash ==
  fresh.change_hash`. The ledger reuses these exact comparisons.
- Discovery-time identifiers differ by source:
  - **Federal:** `native_id` `"119/hr/9076"` → bill-slug `"119-hr-9076"` (`/`→`-`), which
    matches the wiki page filename and what `filter_unseen` already keys on.
  - **State:** the page id `"ca-2025-ab-1064"` is computed during *enrich* and is NOT
    available at discovery; the LegiScan `bill_id` (the candidate's `native_id`) **is**.
  → The two ledgers key by whatever is cheap at discovery: federal by **bill-slug**, state by
    **LegiScan bill_id**.

## Approach (chosen: A)

Two committed JSON ledgers + a `record-rejects` CLI + a cursor-aware filter folded into
`--skip-existing`. Mirrors the existing `filter_unseen` + `render-classified` patterns and
reuses the refresh cursor gates. (Rejected: B — one unified ledger keyed by
`jurisdiction:native_id`, buys little once cursor/key extraction stays source-specific;
C — SQLite negative cache, contradicts the committed-storage decision.)

## 1. Storage

Two byte-stable JSON files, committed alongside the wiki:

- `wiki/.rejects/federal.json`, keyed by bill-slug:
  ```json
  { "119-hr-8800": { "cursor": "2026-06-06T08:06:29Z", "reason": "seed term in title only" } }
  ```
- `wiki/.rejects/state.json`, keyed by LegiScan bill_id (string):
  ```json
  { "1789234": { "cursor": "<change_hash>", "id": "ca-2025-ab-1064", "reason": "incidental data mention" } }
  ```

Entry schema: `cursor` (required, the source change cursor), `reason` (optional, audit-only
— the classifier's `disqualifier_applied`/rationale, never read by the filter), and for
state `id` (optional, the eventual page slug, audit-only). **No timestamp field** — keeps
writes deterministic so an unchanged re-record produces a byte-identical file (D20
discipline). The dot-directory is never mistaken for a wiki page and never matches `*.md`.

## 2. Filter (read side) — `pipeline/discover.py`

```
filter_cached_rejects(candidates, ledger, *, key_of, cursor_of) -> list[Candidate]
```
Drop a candidate iff `key_of(c)` is in `ledger` **and** `cursor_of(c) == ledger[key].cursor`.
If the cursor advanced (or the key is absent), keep it → it gets re-classified. Order
preserved. Empty/missing ledger → no-op (every candidate passes), mirroring `filter_unseen`.

Source adapters (small, pure, individually tested):
- federal: `key_of = lambda c: c.native_id.replace("/", "-")`, `cursor_of = lambda c: c.update_date`
- state:   `key_of = lambda c: c.native_id`, `cursor_of = lambda c: c.raw.get("change_hash")`

Loader `load_reject_ledger(path) -> dict[str, dict]`: missing file → `{}`; malformed →
`ConfigError` (fail loud, consistent with `render-classified`).

## 3. Record (write side) — new CLI `record-rejects`

```
uv run zwiadbrain record-rejects --in <rejects.json> --scope <federal|state> \
    [--cache-dir wiki/.rejects]
```
`rejects.json` is a JSON list of `{ "key": <slug|bill_id>, "cursor": <str>, "reason": <str?>,
"id": <str?> }`. The command loads the existing `<scope>.json` (or `{}`), upserts each item
(a newer cursor overwrites the prior entry), and writes **sorted-key** JSON. Echoes counts
(new vs updated). Mirrors the `render-classified` validate-then-write shape. Validation:
`--scope` ∈ {federal, state}; each item must have non-empty `key` and `cursor`.

## 4. Wiring

- **Federal `fetch-candidates`:** inside the existing `--skip-existing` branch, after
  `filter_unseen`, load `federal.json` and apply `filter_cached_rejects` on `scanned` (before
  the Stage-2 recall probe, so cached rejects are never re-probed). Echo a dropped-rejects
  count line.
- **State `fetch-state-candidates`:** add `--skip-existing/--no-skip-existing` (default
  False) and `--wiki` (default `Path("wiki")`). When set, apply `filter_unseen` against a new
  `_existing_state_bill_ids(wiki, state)` helper **and** `filter_cached_rejects` against
  `state.json`, then cap to `limit`. This also closes the pre-existing gap that state never
  deduped against its own wiki pages.
  - `_existing_state_bill_ids(wiki, state)`: stems of `wiki/states/<st>/bills/*.md`,
    **excluding `*.text.md` sidecars**.
  - **Over-fetch to preserve `limit`:** because reject/seen filtering happens after
    `getSearchRaw`, state discovery must over-fetch (oversample, mirroring federal
    `_OVERSAMPLE`) before filtering so it still returns up to `limit` *fresh* candidates when
    more exist. Exact mechanism (search page size / requesting more than `limit`) resolved in
    research/planning.

## 5. Skill + doc updates

- `.claude/commands/zwiad-backfill.md`: after step 3 (classify), add a step — stage the
  out-of-scope bills' `{key: <slug>, cursor: <bill.update_date>, reason}` to `rejects.json`
  and run `record-rejects --scope federal`. Note `--skip-existing` now also skips cached
  rejects.
- `.claude/commands/zwiad-scan-states.md`: analogous step with
  `{key: <legiscan_bill_id>, cursor: <change_hash>, id: <bill.id>, reason}` and
  `record-rejects --scope state`; document the new `--skip-existing`.
- `DECISIONS.md`: append D82 (reject ledger: committed, cursor-invalidated, federal+state).

## Error handling

- Missing ledger → empty cache (no-op read).
- Malformed ledger or `rejects.json` → `ConfigError` → non-zero exit (no silent swallow).
- `--scope` outside {federal, state} → `ConfigError`.
- Writes are atomic-enough for a single-writer interactive session; sorted-key dump keeps
  re-commits clean.

## Testing (TDD; must keep pyright --strict + ruff clean; 785 baseline stays green)

Unit:
- `filter_cached_rejects`: hit (drop), stale cursor (keep), key-miss (keep), empty ledger
  (no-op), order preserved.
- federal vs state `key_of`/`cursor_of` extraction (incl. state cursor pulled from
  `raw["change_hash"]`; federal slug mapping).
- `load_reject_ledger`: missing → `{}`; malformed → `ConfigError`.
- `record-rejects` merge: insert, idempotent re-record (byte-identical), cursor-advance
  overwrite, new-vs-updated counts.
- `_existing_state_bill_ids`: includes pages, excludes `.text.md` sidecars, missing dir → set().

CLI integration:
- federal `fetch-candidates --skip-existing` drops a cached reject whose cursor is unchanged
  and re-includes one whose cursor advanced.
- state `fetch-state-candidates --skip-existing` drops both already-tracked and cached-reject
  bills and still returns up to `limit` fresh candidates.

## Open implementation details (for research/planning)

1. Confirm `CongressSource.discover` populates `Candidate.update_date` with the same
   `updateDate` string the refresh gate uses (so record-time `bill.update_date` ==
   filter-time `candidate.update_date`).
2. State over-fetch mechanism in `LegiScanSource.discover` (does `getSearchRaw` page / accept
   a count > limit) so `--skip-existing` doesn't shrink the result below `limit`.
3. Confirm `Candidate.native_id` for LegiScan equals `str(bill_id)` and that `bill_id` is the
   stable LegiScan identifier used as the ledger key.
