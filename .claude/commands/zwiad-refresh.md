---
description: Refresh tracked federal and state bills — detect changed cursors, dispatch classifier/summarizer/amendment-explainer subagents only where triggers fired, preserve PHASE-05 leg-history, flip out-of-scope bills (runs on your regular Claude plan usage).
allowed-tools: Bash, Read, Write, Task
---

# ZwiadBrain watchlist refresh (Pass A — federal + state)

Re-fetch every tracked federal and state bill, dispatch subagents only on real change,
preserve PHASE-05's expensive cross-modal-verified leg-history (hearings +
statements + narrative), and flip IN→OUT bills to `tracking: false`. Python
does the deterministic fetch + render; you (this interactive session) do the
LLM steps so the work runs on the regular Claude plan, **not** the API or the
Agent SDK credit.

> **Re-tracking a flipped-out bill (F7).** A bill flipped to `tracking: false` is
> excluded from this refresh (it can never come back on its own). To bring one back,
> run `uv run zwiadbrain backfill --force <congress/type/number>` (re-fetches and writes
> it re-tracked), then dispatch the **classifier** subagent on it — an in-scope verdict
> keeps it tracked; an out-of-scope verdict means it flips out again on the next refresh.

## Steps

### 1. Fetch refreshable — federal (Python, deterministic)
Run:
```
uv run zwiadbrain fetch-refreshable
```
Scans `wiki/federal/bills/*.md` frontmatter for tracking=true bills,
re-fetches each via Congress.gov, compares cursors, and writes
`refreshable.json` to `data/runs/<id>/`. **Note the exact path it prints.**

### 2. Fetch refreshable — state (Python, deterministic)
Run (write to a `state/` SUBDIRECTORY so it cannot collide with the federal file):
```
uv run zwiadbrain fetch-state-refreshable --out data/runs/<id>/state
```
(Use the same `<id>` directory that step 1 printed.) This writes a SEPARATE
`data/runs/<id>/state/refreshable.json` — it does NOT append to or overwrite the
federal `refreshable.json` from step 1. Scans `wiki/states/*/bills/*.md`
frontmatter for tracking=true state bills that carry `legiscan_bill_id`, calls
`getMasterListRaw` once per state to get the full current-session `change_hash`
map, and re-fetches only bills whose stored hash differs via `getBill`.

**Invariant:** the federal `data/runs/<id>/refreshable.json` and the state
`data/runs/<id>/state/refreshable.json` are TWO files. The interactive session
concatenates their arrays into one in-memory list of entries, which is rendered
by a SINGLE `render-refreshed` call in step 6. State bill entries carry their new
`change_hash` and `legiscan_bill_id` through unchanged, so the next refresh can
diff correctly. Do not run two separate `render-refreshed` calls.

### 3. Read the refreshable lists and merge
`Read` BOTH files and concatenate their arrays into one in-memory list of entries:
- `data/runs/<id>/refreshable.json` (federal, from step 1)
- `data/runs/<id>/state/refreshable.json` (state, from step 2 — if it does not
  exist because there were no tracked state bills, treat it as `[]`)

Each entry (federal or state) is:
```json
{
  "bill_id": "...",
  "prev": {full prev Bill},
  "fresh": {full fresh Bill, with leg_history.spine re-derived if enacted},
  "needs_classifier": true|false,
  "needs_summarizer": true|false,
  "changed_amendment_numbers": ["H.Amdt. 1", ...]
}
```
Federal and state entries share this schema. State entries additionally have
`legiscan_bill_id` and `change_hash` inside `fresh` — leave them untouched
when merging subagent outputs back.

**Early-exit rule:** the rule applies to the CONCATENATED list. If the union of
federal and state entries is empty, every tracked bill is up to date — report
`no refreshable bills` and STOP. Do not run the subagents.

### 4. Per-bill subagent dispatch
For each entry, build a `bill` object starting from a copy of `fresh`, then:

a. **Classifier** (only if `needs_classifier`): dispatch the **classifier**
   subagent with `fresh.title` and `fresh.summary`. Capture
   `{in_scope, topics, rationale, criterion}`. Save as `classifier_in_scope`,
   `classifier_rationale`, and set `bill.topics = classifier.topics` (only
   when in-scope; leave `bill.topics = prev.topics` on out-of-scope to
   preserve the prior record).

b. **Summarizer** (only if `needs_summarizer` AND classifier returned in-scope
   — out-of-scope bills do not get a fresh summary): dispatch the
   **summarizer** subagent with `fresh`, adding `text_path` — the bill's
   existing `<id>.text.md` sidecar path under the wiki — when that sidecar
   exists (D110: the summary is written from the bill text, not a possibly
   stale official synopsis; note if the sidecar predates the text change, the
   refresh re-extraction will update it). Set `bill.summary` to the returned
   prose.

c. **Amendment-explainer** (only if `changed_amendment_numbers` is non-empty
   AND classifier in-scope): dispatch the **amendment-explainer** with the
   amendments whose `number` is in `changed_amendment_numbers`, and set each
   matching `bill.amendments[i].what_changed`. Carry forward existing
   `what_changed` for amendments NOT in `changed_amendment_numbers`.

When classifier returned out-of-scope, do NOT dispatch summarizer or
amendment-explainer — the bill is being flipped out and re-running the
expensive subagents is wasted plan usage.

### 5. Stage refreshed
`Write` a `refreshed.json` array in the same run directory. Each entry:
```json
{
  "bill_id": "...",
  "prev": {prev Bill verbatim},
  "bill": {bill with all subagent outputs merged},
  "classifier_in_scope": true|false,
  "classifier_rationale": "..."
}
```
When `needs_classifier` was false, set `classifier_in_scope: true` and
`classifier_rationale: ""` so the Python step sees a consistent shape.

### 6. Render + index (Python, deterministic)
Run:
```
uv run zwiadbrain render-refreshed --in data/runs/<id>/refreshed.json
```
This applies the D38 + D40 leg-history preservation rule, the IN→OUT flip,
re-renders pages, and reindexes the FTS5 store. It prints
`refresh complete: refreshed N / K flipped-out`.

### 7. Report
Summarize: number of refreshable bills detected, subagent dispatch counts
(classifier / summarizer / explainer calls), bills refreshed, bills flipped
out (with reasons). Also flag any tracked bill whose `update_date` is older
than its `latest_action_date` as **"stale cursor — consider forced refresh"**
(the 2026-07 audit traced off-by-one vote tallies and months-stale pages to
snapshots taken before the source finished recording a day's actions). Do not
commit — leave the wiki changes for review.

## Notes
- Keep `ANTHROPIC_API_KEY` unset so subagents use your plan session, not the API.
- The D38 + D40 rule is enforced by `render-refreshed`: prev's
  `leg_history.hearings/statements/narrative` always survive a refresh.
- A bill whose classifier verdict flips IN→OUT is re-rendered with
  `tracking: false` and an audit marker; its page stays at the same path and
  its committed history is preserved (a future `/zwiad-backfill --force <id>`,
  not yet implemented, could re-track it).
