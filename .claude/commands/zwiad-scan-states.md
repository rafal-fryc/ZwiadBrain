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
**every candidate costs one classifier dispatch, and each run's in-scope bills share a single batch-summarizer dispatch**, so limit bounds
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

### 3. Classify each bill (subagent: `classifier`) → `verdicts.json`

For every candidate, dispatch the **classifier** subagent with the bill's `title` and
`summary`. It reads `reference/topics.yaml` and returns
`{in_scope, topics, confidence, rationale, positive_criterion, disqualifier_survived, disqualifier_applied}`.
- Log each decision (id, in_scope, confidence, positive_criterion/disqualifier) to the transcript.
- **Validate topics**: if the classifier returns any topic not in `{ai, privacy, cyber}`,
  treat it as a classifier error — record the bill as out-of-scope in the transcript and set
  `in_scope: false` in its verdict (do not enrich it).
- Collect one entry per classified bill into `verdicts.json` —
  `[{ "id", "in_scope", "topics", "reason" }]`, where `reason` is the classifier's rationale —
  and `Write` it to the run directory.

`verdicts.json` is the resumable classification record (backfill gap 1): if a plan rate-limit
or context cutoff interrupts classification, only the *unclassified tail* is lost. Re-run the
classifier on the remaining ids, append their verdicts, and continue.

### 4. Apply verdicts (Python, deterministic)

Run:
```
uv run zwiadbrain apply-verdicts --in data/runs/<id>/candidates.json --verdicts data/runs/<id>/verdicts.json
```
It splits candidates into `classified.json` (in-scope, with `topics` applied) and
`rejects.json` (out-of-scope), and reports any **pending** candidates that have no verdict
yet. If pending > 0, classify those, append to `verdicts.json`, and re-run before continuing.

### 4a. Record the rejects (reject ledger — the negative cache)

Run:
```
uv run zwiadbrain record-rejects --in data/runs/<id>/rejects.json --scope state
```
This upserts each into `wiki/.rejects/state.json` keyed by LegiScan `bill_id` and its
`change_hash` cursor. Pass `--skip-existing --wiki wiki` to `fetch-state-candidates` on later
runs to skip already-tracked and cached-reject bills (D82). Commit `wiki/.rejects/`.

### 5. Summarize the in-scope bills (subagent: `batch-summarizer`) → `summaries.json`

`Read` `classified.json`. Dispatch the **batch-summarizer** subagent ONCE with the full list
of in-scope bills (each bill's `id`, `title`, `summary`, `status`, sponsors, latest action).
It returns a single `{id: summary}` JSON map. `Write` it to `summaries.json`, then run:
```
uv run zwiadbrain apply-summaries --in data/runs/<id>/classified.json --summaries data/runs/<id>/summaries.json
```
This sets each bill's plain-language summary in place, reporting any **pending**
(un-summarized) bills. The single batch dispatch replaces the old one-summarizer-per-bill
round-trip (backfill gap 2); a cutoff loses only the un-summarized tail.

If an in-scope bill has amendments, dispatch the **amendment-explainer** subagent for that
bill and set each amendment's `what_changed` by editing `classified.json` directly. This
touches only the `amendments`, leaving the applied `summary` and `topics` intact (order
relative to `apply-summaries` does not matter — they update disjoint fields).

### 6. Render + index (Python, deterministic)

Run:
```
uv run zwiadbrain render-classified --in data/runs/<id>/classified.json
uv run zwiadbrain reindex
```
`render-classified` validates each bill's `topics` against the taxonomy and writes wiki pages
under `wiki/states/<st>/bills/`; `reindex` rebuilds the FTS5 index from the committed wiki.

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
