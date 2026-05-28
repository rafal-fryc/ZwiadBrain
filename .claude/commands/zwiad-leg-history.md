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

### 3. Dispatch the researcher subagent

Dispatch the **leg-history-researcher** subagent with:

- `leads.citation`, `leads.congress`, `leads.sponsors` — bill identity
- `leads.hearings` — GovInfo hearing leads (unverified starting points)
- `spine.floor_consideration` — CREC floor references (date, chamber,
  congressional_record citation, url) as anchors for floor statements

The researcher returns:

```json
{
  "hearings": [ <Hearing...> ],
  "statements": [ <Statement...> ],
  "narrative": "<Legislative Journey prose>"
}
```

Handle researcher failure: if it returns malformed JSON or an unexpected shape,
abort and report. If it times out, retry once, then abort. If it returns valid
JSON with empty `statements`/`hearings`, proceed — a bill with no verified
quotes is still a valid legislative history.

### 4. Dispatch the verifier subagent

Dispatch the **leg-history-verifier** subagent with the `statements` from the
researcher, each annotated with its 0-based `index` in the list. Build this
array by list position (highest-stakes step), e.g.:

```python
[{"index": i, "speaker": s["speaker"], "quote": s["quote"], "source_url": s["source_url"]}
 for i, s in enumerate(statements)]
```

`index` MUST match the statement's position in the researcher's `statements`
list — the grounding gate keys verdicts by index, so a mismatch silently applies
a verdict to the wrong statement (misattribution, the project's worst failure).

The verifier independently fetches each `source_url` and returns:

```json
[{"index": 0, "verified": true, "note": "..."}, ...]
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
- Note that any statement whose quote was not found at its source URL OR whose
  verifier verdict was `false` was dropped by the grounding gate — this is
  expected and is the project's trust boundary, not an error.

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
