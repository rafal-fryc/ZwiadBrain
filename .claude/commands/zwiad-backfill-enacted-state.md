---
description: Backfill ENACTED state laws (one state-session) into the ZwiadBrain wiki — enacted-only LegiScan discovery, classify + summarize via subagents, per-unit review gate (runs on your regular Claude plan usage).
argument-hint: <state> <year> [--classify-all]
allowed-tools: Bash, Read, Write, Edit, Task
---

# ZwiadBrain enacted-state backfill (one campaign unit)

Backfill the **enacted bills** of one state legislative session — the state half of the
prior-years enacted-laws campaign (D84/D85). One run = one campaign **unit** = one
(state × session) = one review gate = one commit. Python does the deterministic fetch/render;
you do the LLM steps via subagents (regular Claude plan, **not** API/Agent SDK credit).

**Arguments:** `$1` = two-letter state (e.g. `ca`; campaign states: ca, ny, tx, co, va, wa, il).
`$2` = year (resolves to the LegiScan session covering it; the campaign covers sessions across
2019–2024). `$3` = optional `--classify-all` to skip recall and classify every enacted bill.

Discovery is **enacted-only by construction**: `getSessionList` resolves the year → session, then
`getMasterList` lists that session's bills and only `status == 4 (Passed)` are kept — failed/vetoed/
pending bills never enter the pipeline.

## Steps

### 1. Fetch enacted candidates (Python, deterministic)
Run:
```
uv run zwiadbrain fetch-state-enacted-candidates --state $1 --year $2 --skip-existing $3
```
It resolves the session, lists its enacted (`status==4`) bills via `getMasterList`, applies a free
title+description keyword recall (skipped under `--classify-all`), enriches survivors via `getBill`,
drops anything already tracked or in `wiki/.rejects/state.json`, and writes `candidates.json` under
`data/runs/<id>/`. **Note the exact path.** State bills have `jurisdiction` like `US-CA`.

> If it errors with `no <st> session covers year <year>`, the year falls outside the state's
> session ranges — re-run the **full step-1 invocation** (keep `--skip-existing $3`) with a
> `--year <Y>` that a real session spans. The state's sessions come from LegiScan `getSessionList`;
> pick a year inside one of the listed `[year_start, year_end]` spans.

### 2. Read the candidates
`Read` `candidates.json` — each is a full enacted `Bill` (id, title, summary = LegiScan
`description`, status, `enacted: true`, sponsors, actions, amendments, `legiscan_bill_id`).

### 3. Classify each bill (subagent: `classifier`) → `verdicts.json`
For every candidate, dispatch the **classifier** with `title` + `summary`. It reads
`reference/topics.yaml` and returns the verdict object.
- Log each decision; **validate topics** (only `{ai, privacy, cyber}` — any other = classifier
  error → `in_scope: false`, do not enrich).
- Collect `[{ "id", "in_scope", "topics", "reason" }]` into `verdicts.json` and `Write` it (resumable
  tail — backfill gap 1).

### 4. Apply verdicts (Python, deterministic)
```
uv run zwiadbrain apply-verdicts --in data/runs/<id>/candidates.json --verdicts data/runs/<id>/verdicts.json
```
Splits into `classified.json` + `rejects.json`, reporting **pending** candidates. Classify any
pending, append, re-run before continuing.

### 4a. Record the rejects (reject ledger)
```
uv run zwiadbrain record-rejects --in data/runs/<id>/rejects.json --scope state
```
Upserts each into `wiki/.rejects/state.json` keyed by `bill_id` + `change_hash` (D82), stamped
with the taxonomy's current `scope_version` (D96). Commit `wiki/.rejects/` alongside the pages.
After any scope-rule change (a `topics.yaml` `scope_version` bump), run
`uv run zwiadbrain stale-rejects --scope state` to review rejects recorded under the old rules.

### 5. Render + extract text FIRST, then summarize from the enacted text (D110)

These are enacted laws, and LegiScan's `description` is routinely the *introduced*-version
synopsis — the 2026-07 accuracy audit found summaries carrying provisions that amendments
had removed. So render + extract come first, and the summary is written from the extracted
enacted text.

**5a. Render + extract (Python, deterministic; extract is optional — skip, never fail):**
```
uv run zwiadbrain render-classified --in data/runs/<id>/classified.json
uv run --no-sync zwiadbrain extract-text --in data/runs/<id>/classified.json
```
Pages render under `wiki/states/$1/bills/` (with the raw official summary, replaced in 5b);
`extract-text` (requires Docling — `uv pip install docling`, a deliberately unlocked heavy
extra, D68) writes `<id>.text.md` sidecars next to the new pages and links them from each
page. If Docling is NOT installed, skip `extract-text`, note "extraction deferred" in the
unit report, and continue — do NOT fail the unit. Deferred sidecars are backfilled later
with `uv run --no-sync zwiadbrain extract-tracked` (skip-if-sidecar makes it resumable).
Commit sidecars with the unit.

**5b. Summarize the in-scope bills (subagent: `batch-summarizer`) → `summaries.json`:**
`Read` `classified.json`. Dispatch **batch-summarizer** ONCE with the full in-scope list,
adding to each bill whose sidecar exists a `text_path` — the path of
`wiki/states/$1/bills/<id>.text.md` — so its summary is written from the enacted text, not
the synopsis (bills without a sidecar go without `text_path`; the agent's enacted-fidelity
rules still apply). `Write` the `{id: summary}` map to `summaries.json`, then:
```
uv run zwiadbrain apply-summaries --in data/runs/<id>/classified.json --summaries data/runs/<id>/summaries.json
```
Reports **pending** un-summarized bills (backfill gap 2). For bills with amendments, dispatch
**amendment-explainer** and set `what_changed` by editing `classified.json` (disjoint fields).

### 6. Re-render + index (Python, deterministic)
```
uv run zwiadbrain render-classified --in data/runs/<id>/classified.json
uv run zwiadbrain reindex
```
Re-renders the pages with the applied plain-language summaries (cheap — unchanged pages are
skipped) and indexes the sidecars so the full statutory text is searchable.

### 7. Flag significant laws for legislative history
Append any **significant** enacted laws (named Act / high-salience) to
`docs/backfill/leg-history-queue.md`. Leg-history is a **separate, per-law-approved**
`/zwiad-leg-history <state>/<bill>` pass — do NOT run it here.

### 8. Update the campaign tracker + report (review gate)
Edit `docs/backfill/enacted-campaign.md`: set this (state × session) unit's status to `in-review`
with counts (enacted discovered, in vs out + reject reasons, pages rendered, leg-history flags).
Then **report** and **stop — do NOT commit** (no `git add`). Leave the changes in the working tree
for the user's review; on approval, commit the unit and mark it `done`.

## Notes
- Keep `ANTHROPIC_API_KEY` unset so subagents use your plan session.
- State bills carry `legiscan_bill_id` (needed for the `change_hash` incremental refresh that
  `/zwiad-refresh` runs later).
- One (state × session) per run. `--skip-existing` (default) makes re-runs idempotent — an
  interrupted unit resumes cleanly.
- A big-state session (e.g. CA) can hold >1,000 enacted bills; recall trims to the topical few.
  Review the classifier verdict rate before raising scope.
