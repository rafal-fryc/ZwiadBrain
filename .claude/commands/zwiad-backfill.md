---
description: Backfill federal bills into the ZwiadBrain wiki, classifying and summarizing each via subagents (runs on your regular Claude plan usage).
argument-hint: <congress> [limit] [--force <congress/type/number>]
allowed-tools: Bash, Read, Write, Task
---

# ZwiadBrain backfill

Orchestrate a federal backfill end to end. Python does the deterministic fetch and
render; you (this interactive session) do the LLM steps by dispatching subagents,
so the work runs on the regular Claude plan — **not** the API or the Agent SDK
credit. Arguments: `$1` = congress number (required), `$2` = limit (default 5).
`$3` = optional `--force <congress/type/number>` to re-track a previously flipped-out bill
(skips discovery: re-fetches that one bill, then classify it — an in-scope verdict keeps it tracked).

## Steps

### 1. Fetch candidates (Python, deterministic)
Run:
```
uv run zwiadbrain fetch-candidates --congress $1 --limit ${2:-5}
```
It discovers bills, applies the `reference/topics.yaml` keyword recall filter,
fetches each, and writes enriched `Bill`s to a `candidates.json` under
`data/runs/<id>/`. Note the exact path it prints.

### 2. Read the candidates
`Read` the `candidates.json` it wrote. Each entry is a full bill (id, title,
summary, status, sponsors, actions, amendments).

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
uv run zwiadbrain record-rejects --in data/runs/<id>/rejects.json --scope federal
```
This upserts each rejected bill into `wiki/.rejects/federal.json` keyed by bill id and its
Congress `updateDateIncludingText` cursor, so a future `--skip-existing` sweep skips it until
the bill changes (D82). Commit `wiki/.rejects/` alongside the rendered pages.

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
`render-classified` validates each bill's `topics` against the taxonomy and writes the wiki
pages; `reindex` rebuilds the FTS5 index from the committed wiki.

### 7. Report
Summarize: candidates fetched, classified in vs out (with the out-of-scope
reasons), and pages rendered. Do not commit — leave the wiki changes for review.

## Notes
- Keep `ANTHROPIC_API_KEY` unset so subagents use your plan session, not the API.
- Only `topics[]` is persisted; confidence/rationale/criteria fields stay in the transcript.
- `--skip-existing` now also drops bills already in `wiki/.rejects/federal.json` whose change cursor is unchanged.
