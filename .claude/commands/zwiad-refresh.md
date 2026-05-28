---
description: Refresh tracked federal bills — detect changed cursors, dispatch classifier/summarizer/amendment-explainer subagents only where triggers fired, preserve PHASE-05 leg-history, flip out-of-scope bills (runs on your regular Claude plan usage).
argument-hint: "[--bill <id>]"
allowed-tools: Bash, Read, Write, Task
---

# ZwiadBrain watchlist refresh (Pass A)

Re-fetch every tracked federal bill, dispatch subagents only on real change,
preserve PHASE-05's expensive cross-modal-verified leg-history (hearings +
statements + narrative), and flip IN→OUT bills to `tracking: false`. Python
does the deterministic fetch + render; you (this interactive session) do the
LLM steps so the work runs on the regular Claude plan, **not** the API or the
Agent SDK credit.

Optional argument: `$1` may be `--bill <id>` to refresh a single bill (rare;
default is all tracking=true federal bills).

## Steps

### 1. Fetch refreshable (Python, deterministic)
Run:
```
uv run zwiadbrain fetch-refreshable
```
Scans `wiki/federal/bills/*.md` frontmatter for tracking=true bills,
re-fetches each via Congress.gov, compares cursors, and writes
`refreshable.json` to `data/runs/<id>/`. **Note the exact path it prints.**

If the file is `[]`, every tracked bill is up to date — report `no
refreshable bills` and STOP. Do not run the subagents in this case.

### 2. Read the refreshable list
`Read` the `refreshable.json`. Each entry is:
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

### 3. Per-bill subagent dispatch
For each entry, build a `bill` object starting from a copy of `fresh`, then:

a. **Classifier** (only if `needs_classifier`): dispatch the **classifier**
   subagent with `fresh.title` and `fresh.summary`. Capture
   `{in_scope, topics, rationale, criterion}`. Save as `classifier_in_scope`,
   `classifier_rationale`, and set `bill.topics = classifier.topics` (only
   when in-scope; leave `bill.topics = prev.topics` on out-of-scope to
   preserve the prior record).

b. **Summarizer** (only if `needs_summarizer` AND classifier returned in-scope
   — out-of-scope bills do not get a fresh summary): dispatch the
   **summarizer** subagent with `fresh` → set `bill.summary` to the returned
   prose.

c. **Amendment-explainer** (only if `changed_amendment_numbers` is non-empty
   AND classifier in-scope): dispatch the **amendment-explainer** with the
   amendments whose `number` is in `changed_amendment_numbers`, and set each
   matching `bill.amendments[i].what_changed`. Carry forward existing
   `what_changed` for amendments NOT in `changed_amendment_numbers`.

When classifier returned out-of-scope, do NOT dispatch summarizer or
amendment-explainer — the bill is being flipped out and re-running the
expensive subagents is wasted plan usage.

### 4. Stage refreshed
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

### 5. Render + index (Python, deterministic)
Run:
```
uv run zwiadbrain render-refreshed --in data/runs/<id>/refreshed.json
```
This applies the D38 + D40 leg-history preservation rule, the IN→OUT flip,
re-renders pages, and reindexes the FTS5 store. It prints
`refresh complete: refreshed N / K flipped-out`.

### 6. Report
Summarize: number of refreshable bills detected, subagent dispatch counts
(classifier / summarizer / explainer calls), bills refreshed, bills flipped
out (with reasons). Do not commit — leave the wiki changes for review.

## Notes
- Keep `ANTHROPIC_API_KEY` unset so subagents use your plan session, not the API.
- The D38 + D40 rule is enforced by `render-refreshed`: prev's
  `leg_history.hearings/statements/narrative` always survive a refresh.
- A bill whose classifier verdict flips IN→OUT is re-rendered with
  `tracking: false` and an audit marker; its page stays at the same path and
  its committed history is preserved (a future `/zwiad-backfill --force <id>`,
  not yet implemented, could re-track it).
