---
description: Backfill federal bills into the ZwiadBrain wiki, classifying and summarizing each via subagents (runs on your regular Claude plan usage).
argument-hint: <congress> [limit]
allowed-tools: Bash, Read, Write, Task
---

# ZwiadBrain backfill

Orchestrate a federal backfill end to end. Python does the deterministic fetch and
render; you (this interactive session) do the LLM steps by dispatching subagents,
so the work runs on the regular Claude plan — **not** the API or the Agent SDK
credit. Arguments: `$1` = congress number (required), `$2` = limit (default 5).

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
the wiki pages; `reindex` rebuilds the FTS5 index from the committed wiki.

### 7. Report
Summarize: candidates fetched, classified in vs out (with the out-of-scope
reasons), and pages rendered. Do not commit — leave the wiki changes for review.

## Notes
- Keep `ANTHROPIC_API_KEY` unset so subagents use your plan session, not the API.
- Only `topics[]` is persisted; confidence/rationale/criteria fields stay in the transcript.
