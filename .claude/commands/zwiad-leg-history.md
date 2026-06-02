---
description: Assemble a source-linked legislative history for an enacted federal bill — deterministic spine + researched, grounded, cross-verified hearings/statements + narrative. Runs on your regular Claude plan via subagents.
argument-hint: <congress/type/number>
allowed-tools: Bash, Read, Write, Task
---

# ZwiadBrain Legislative History

Orchestrate the full legislative-history pipeline end to end. Python does the
deterministic fetch and render; you (this interactive session) dispatch the
researcher and verifier subagents, so the LLM work runs on the regular Claude
plan — **not** the API or Agent SDK credits. Argument: `$1` = bill in
`congress/type/number` form, e.g. `118/hr/9020`.

## Steps

### 1. Fetch the deterministic spine (Python)

Run:

```
uv run zwiadbrain fetch-leg-history --bill $1
```

This fetches the enacted bill from Congress.gov and GovInfo, assembles the
deterministic spine (text versions, committee reports, votes, floor
consideration, enactment), collects GovInfo hearing leads, and writes
`leghistory.json` to a timestamped run directory under `data/runs/`.

Note the printed run directory path and `leghistory.json` path.

**If the bill is not enacted**, `fetch-leg-history` prints a "not enacted" error
and exits non-zero. Report cleanly to the user that legislative history is only
assembled for enacted (signed-into-law) bills, and stop.

### 2. Read the staging file

`Read` the `leghistory.json` it wrote. The file contains:

- `bill` — the full `Bill` object (id, title, sponsors, actions, etc.)
- `spine` — the deterministic `LegHistory` (versions, committee_reports, votes,
  floor_consideration, enactment; hearings/statements/narrative are empty)
- `leads` — research starting points: `{id, congress, citation, title,
  sponsors, related_bills, introduced_date, latest_action_date, hearings}`

### 3. Dispatch the researcher subagent — once per lane (fan-out)

Dispatch **leg-history-researcher** once for EACH of the four source lanes, in
parallel (separate `Task` calls in a single message): `crec`, `hearings`,
`press`, `signing`. Give every dispatch the shared context plus its `lane`:

- `lane` — the lane name for this dispatch (one of the four above)
- `leads.citation`, `leads.congress`, `leads.sponsors` — bill identity
- `bill.topics`, `bill.policy_area` — subject tags (the relevance clamp for `related` items)
- `leads.hearings` — GovInfo hearing leads (mainly for the `hearings` lane)
- `spine.floor_consideration`, `spine.committee_reports`, `spine.enactment` — anchors
  (mainly for the `crec` and `signing` lanes)

Each lane returns `{hearings, statements, narrative}` (every item tagged with a
`relation` of `on_bill` or `related`; `narrative` is non-empty only from the
`crec` lane and `""` from the others).

When all four return, **MERGE** them: concatenate `hearings` and `statements`
across lanes in a FIXED order (`crec`, `hearings`, `press`, `signing`), and take
the `narrative` from the `crec` lane. This merged `statements` list defines the
canonical index order used in step 4 — fix it now and do not reorder it.

Handle failure per lane: if a lane returns malformed JSON, retry it once, then
drop just that lane and proceed with the others (note the dropped lane in the
report). Empty `statements`/`hearings` from a lane is fine — a bill with no
verified quotes is still a valid legislative history.

### 4. Dispatch the verifier subagent

Dispatch the **leg-history-verifier** subagent over the MERGED `statements` list.
Provide a `subject` context block and one entry per statement, annotated with its
0-based `index` in the merged list:

```python
{
  "subject": {
    "citation": leads["citation"], "title": leads["title"],
    "topics": bill["topics"], "sponsors": leads["sponsors"],
  },
  "statements": [
    {"index": i, "speaker": s["speaker"], "quote": s["quote"],
     "source_url": s["source_url"], "relation": s.get("relation", "on_bill")}
    for i, s in enumerate(statements)
  ],
}
```

`index` MUST match the statement's position in the MERGED `statements` list — the
grounding gate keys verdicts by index, so a mismatch silently applies a verdict to
the wrong statement (misattribution, the project's worst failure). Do not reorder
`statements` after this point.

The verifier independently fetches each `source_url`, applies the verbatim +
attribution + contiguity checks (and, for `related` items, the subject-relevance
clamp), and returns one entry per statement:

```json
[{"index": 0, "speaker": "...", "quote_prefix": "...", "on_subject": true, "verified": true, "note": "..."}, ...]
```

### 5. Assemble the render-input JSON

Combine the three sources into the render-input object:

```json
{
  "bill":       <bill from leghistory.json>,
  "spine":      <spine from leghistory.json>,
  "hearings":   <hearings from researcher>,
  "statements": <statements from researcher>,
  "narrative":  <narrative from researcher>,
  "verdicts":   <array from verifier>
}
```

`Write` this object to the same run directory as `leghistory-research.json`.

### 6. Render and reindex (Python)

Run:

```
uv run zwiadbrain render-leg-history --in <run dir>/leghistory-research.json
uv run zwiadbrain reindex
```

`render-leg-history` parses the staging file, runs the deterministic grounding
gate (URL resolution + quote-presence check + verifier verdict), and renders the
wiki page. `reindex` rebuilds the FTS5 index.

### 7. Report

Summarize:

- Bill id and citation
- Spine counts: versions, committee_reports, votes, floor_consideration,
  enactment present/absent
- Statements: input count / grounded count (from the render output line)
- Hearings: input count / grounded count (from the render output line)
- Narrative: present/absent
- The rendered page separates **On This Bill** (the bill's own record, under the
  normal sections) from **Related (Subject Matter)** items (sponsor/official
  statements and hearings on the bill's topic) — note if any `related` items survived.
- Note that any statement whose quote was not found at its source URL, whose
  verifier verdict was `false`, or (for a `related` item) that failed the
  subject-relevance clamp was dropped by the grounding gate — this is expected and
  is the project's trust boundary, not an error.

Do **not** commit — leave the wiki changes for review.

## Notes

- Keep `ANTHROPIC_API_KEY` unset so the subagents use your regular plan session,
  not the API.
- The grounding gate drops any statement not verifiably present at its source
  URL and not confirmed by the independent verifier. Dropped quotes are reported
  in the render output; they are expected and intentional.
- The researcher uses `sonnet`; the verifier uses `opus`. This model difference
  is the cross-modal trust boundary — the verifier is deliberately not the same
  model that produced the quotes it checks.
