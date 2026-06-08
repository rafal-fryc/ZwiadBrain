---
description: Backfill state bills into the ZwiadBrain wiki via LegiScan, classifying and summarizing each via subagents (runs on your regular Claude plan usage).
argument-hint: [--state <st>] [--limit <N>]
allowed-tools: Bash, Read, Write, Task
---

# ZwiadBrain state-legislation backfill

Orchestrate a LegiScan state-bill backfill end to end. Python does the deterministic
fetch and render; you (this interactive session) do the LLM steps by dispatching
subagents, so the work runs on the regular Claude plan — **not** the API or the Agent
SDK credit.

**Arguments:** `--state <st>` runs a single two-letter state (e.g. `ca`). Omit `--state`
to run every state in `[states].enabled` in `zwiadbrain.toml` (currently: ca, ny, tx,
co, va, wa, il). `--limit <N>` caps candidates per state (default 5); keep this low —
**every in-scope bill costs one classifier + one summarizer dispatch**, so limit bounds
plan usage directly (D49).

## Steps

### 1. Determine states and fetch candidates (Python, deterministic)

If `--state <st>` was given, loop over that one state. Otherwise, loop over all states
in `[states].enabled` from `zwiadbrain.toml`.

For each state `<st>`, run:
```
uv run zwiadbrain fetch-state-candidates --state <st> --limit <N>
```
(where `<N>` is the `--limit` argument, defaulting to 5 when not provided).

It searches LegiScan's current session for the state using the `reference/topics.yaml`
keyword seeds as the full-text query, enriches each result via `getBill`, and writes
enriched `Bill`s to `candidates.json` under `data/runs/<id>/`. **Note the exact path it
prints** — you will use it in steps 5–6.

If running multiple states, accumulate all candidates from all states before proceeding;
each state gets its own `fetch-state-candidates` call (one `getMasterListRaw` per state).

### 2. Read the candidates

`Read` the `candidates.json` it wrote. Each entry is a full bill (id, title,
summary — the LegiScan `description` field — status, sponsors, actions, amendments).
State bills have `jurisdiction` like `US-CA`, `US-NY`, etc.

### 3. Classify each bill (subagent: `classifier`)

For every candidate, dispatch the **classifier** subagent with the bill's `title`
and `summary`. It reads `reference/topics.yaml` and returns
`{in_scope, topics, confidence, rationale, positive_criterion, disqualifier_survived, disqualifier_applied}`.
- Log each decision (id, in_scope, confidence, positive_criterion/disqualifier) to the transcript.
- **Drop** bills where `in_scope` is false. Keep the returned `topics` for the rest.
- **Validate topics**: if the classifier returns any topic not in `{ai, privacy, cyber}`,
  treat it as a classifier error — drop the bill to the transcript and do NOT enrich it.
  (`render-classified` validates topics again, but catching it here avoids a wasted
  summarizer/amendment-explainer dispatch.)

### 3a. Record the rejects (reject ledger — the negative cache)

`Write` the OUT-of-scope bills (full `Bill` JSON objects) to `rejects.json`, then run:
```
uv run zwiadbrain record-rejects --in data/runs/<id>/rejects.json --scope state
```
This upserts each into `wiki/.rejects/state.json` keyed by LegiScan `bill_id` and its
`change_hash` cursor. Pass `--skip-existing --wiki wiki` to `fetch-state-candidates` on
later runs to skip already-tracked and cached-reject bills (D82). Commit `wiki/.rejects/`.

### 4. Enrich the in-scope bills (subagents: `summarizer`, `amendment-explainer`)

For each in-scope bill:
- Dispatch **summarizer** with the bill data → set the bill's `summary` to the returned prose.
- If the bill has amendments, dispatch **amendment-explainer** with the bill's amendments
  → set each amendment's `what_changed` from the returned `{number: explanation}` map.
- Set the bill's `topics` to the classifier's `topics`.

### 5. Stage the classified bills

`Write` the in-scope, enriched bills (same `Bill` JSON shape as `candidates.json`)
to `classified.json` in the same run directory.

### 6. Render + index (Python, deterministic)

Run:
```
uv run zwiadbrain render-classified --in data/runs/<id>/classified.json
uv run zwiadbrain reindex
```
`render-classified` validates each bill's `topics` against the taxonomy and writes
wiki pages under `wiki/states/<st>/bills/`; `reindex` rebuilds the FTS5 index from
the committed wiki.

### 7. Report

Summarize: candidates fetched per state, classified in vs out (with the out-of-scope
reasons), and pages rendered. Do not commit — leave the wiki changes for review.

## Notes

- Keep `ANTHROPIC_API_KEY` unset so subagents use your plan session, not the API.
- Only `topics[]` is persisted; confidence/rationale/criteria fields stay in the transcript.
- State bills carry `legiscan_bill_id` in their frontmatter — required for the
  `change_hash` incremental refresh that `/zwiad-refresh` runs on subsequent passes.
- The `--limit` default of 5 is intentionally conservative for a first run. Raise it
  only after reviewing classifier verdict rates for the state (D49).
