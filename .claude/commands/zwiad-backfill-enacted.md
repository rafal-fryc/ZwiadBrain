---
description: Backfill ENACTED federal laws (one Congress) into the ZwiadBrain wiki — enacted-only discovery, classify + summarize via subagents, per-unit review gate (runs on your regular Claude plan usage).
argument-hint: <congress> [--classify-all]
allowed-tools: Bash, Read, Write, Edit, Task
---

# ZwiadBrain enacted-federal backfill (one campaign unit)

Backfill the **enacted public laws** of a single Congress — the federal half of the
prior-years enacted-laws campaign (D84/D85). One run = one campaign **unit** = one
Congress = one review gate = one commit. Python does the deterministic fetch/render;
you (this interactive session) do the LLM steps via subagents, so the work runs on the
regular Claude plan — **not** the API or Agent SDK credit.

**Arguments:** `$1` = Congress number (required; the campaign covers 116, 117, 118).
`$2` = optional `--classify-all` to skip the recall pre-filter and classify *every* enacted
law (zero recall risk; ~6× more classifier work — use only if a review revealed a missed law).

Unlike `/zwiad-backfill`, discovery is **enacted-only by construction**: `/law/{congress}/pub`
lists only bills that became public law, so no pending/failed bill ever enters the pipeline.

## Steps

### 1. Fetch enacted candidates (Python, deterministic)
Run:
```
uv run zwiadbrain fetch-enacted-candidates --congress $1 --skip-existing $2
```
It discovers the Congress's enacted public laws via `/law/{congress}/pub`, applies the
two-stage `recall_filter` (title seeds + `policyArea` probe over the whole enacted set; skipped
under `--classify-all`), enriches the survivors, drops anything already tracked or in
`wiki/.rejects/federal.json`, and writes `candidates.json` under `data/runs/<id>/`. **Note the
exact path it prints.**

### 2. Read the candidates
`Read` the `candidates.json`. Each entry is a full enacted `Bill` (id, title, summary, status,
`enacted: true`, `public_law`, sponsors, actions, amendments).

### 3. Classify each bill (subagent: `classifier`) → `verdicts.json`
For every candidate, dispatch the **classifier** subagent with the bill's `title` and `summary`.
It reads `reference/topics.yaml` and returns `{in_scope, topics, confidence, rationale,
positive_criterion, disqualifier_survived, disqualifier_applied}`.
- Log each decision (id, in_scope, confidence, criterion/disqualifier) to the transcript.
- **Validate topics**: any topic not in `{ai, privacy, cyber}` is a classifier error — record the
  bill out-of-scope (`in_scope: false`) and do not enrich it.
- Collect one entry per classified bill into `verdicts.json` — `[{ "id", "in_scope", "topics",
  "reason" }]` — and `Write` it to the run directory.

`verdicts.json` is the resumable record (backfill gap 1): a cutoff loses only the unclassified
tail — re-run the classifier on the remaining ids, append, continue.

### 4. Apply verdicts (Python, deterministic)
```
uv run zwiadbrain apply-verdicts --in data/runs/<id>/candidates.json --verdicts data/runs/<id>/verdicts.json
```
Splits into `classified.json` (in-scope, topics applied) + `rejects.json`, reporting any
**pending** (un-classified) candidates. If pending > 0, classify those, append, re-run.

### 4a. Record the rejects (reject ledger)
```
uv run zwiadbrain record-rejects --in data/runs/<id>/rejects.json --scope federal
```
Upserts each into `wiki/.rejects/federal.json` keyed by bill id + `updateDateIncludingText` (D82),
stamped with the taxonomy's current `scope_version` (D96). Commit `wiki/.rejects/` alongside the
rendered pages. After any scope-rule change (a `topics.yaml` `scope_version` bump), run
`uv run zwiadbrain stale-rejects --scope federal` to review rejects recorded under the old rules.

### 5. Summarize the in-scope bills (subagent: `batch-summarizer`) → `summaries.json`
`Read` `classified.json`. Dispatch the **batch-summarizer** ONCE with the full list of in-scope
bills (`id`, `title`, `summary`, `status`, sponsors, latest action). It returns a single
`{id: summary}` map. `Write` it to `summaries.json`, then:
```
uv run zwiadbrain apply-summaries --in data/runs/<id>/classified.json --summaries data/runs/<id>/summaries.json
```
Sets each summary in place, reporting any **pending** (un-summarized) bills (backfill gap 2).

If an in-scope bill has amendments, dispatch the **amendment-explainer** subagent for that bill and
set each amendment's `what_changed` by editing `classified.json` directly (disjoint fields — order
vs `apply-summaries` does not matter).

### 6. Render + index (Python, deterministic)
```
uv run zwiadbrain render-classified --in data/runs/<id>/classified.json
uv run zwiadbrain reindex
```

### 7. Flag significant laws for legislative history
For each rendered in-scope law that is **significant** (a named Act, or otherwise high-salience —
major rewrite, broad scope), append a row to `docs/backfill/leg-history-queue.md` (see its
format). Leg-history itself is a **separate, per-law-approved** `/zwiad-leg-history` pass — do NOT
run it here.

### 8. Update the campaign tracker + report (review gate)
Edit `docs/backfill/enacted-campaign.md`: set this unit's status to `in-review` and fill in the
counts (enacted discovered, in vs out with reject reasons, pages rendered, leg-history flags).
Then **report** to the user and **stop — do NOT commit** (no `git add`). Leave the wiki + tracker +
queue + reject-ledger changes in the working tree for the user's review. On approval, the user (or a
follow-up) commits the unit and marks it `done` in the tracker.

## Notes
- Keep `ANTHROPIC_API_KEY` unset so subagents use your plan session, not the API.
- Only `topics[]` is persisted; confidence/rationale stay in the transcript.
- One unit per run. Re-running with `--skip-existing` (default above) re-stages nothing already
  tracked or cached-rejected, so an interrupted unit resumes cleanly.
