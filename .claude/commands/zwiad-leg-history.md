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

Each lane returns `{hearings, statements, related_media, narrative}` (every item tagged
with a `relation` of `on_bill` or `related`; `related_media` are Tier-2 videos / reference
pages with NO quote; `narrative` is non-empty only from the `crec` lane and `""` from the
others).

**Write each lane's raw JSON, exactly as returned, to the run directory** as
`<run dir>/lane-<lane>.json` — `lane-crec.json`, `lane-hearings.json`, `lane-press.json`,
`lane-signing.json`. Do **not** merge, reorder, dedup, or re-index anything by hand: the
deterministic assembler (step 4) owns the merge and the index, which is exactly what removes
the old misattribution footgun (D74).

Handle failure per lane: if a lane returns malformed JSON, retry it once; if it still fails,
simply do not write that lane's file. The assembler treats a missing `lane-<lane>.json` as a
dropped lane and proceeds with the others (it prints the drop). Empty `statements` /
`hearings` from a lane is fine — a bill with no verified quotes is still a valid legislative
history.

### 4. Build the verifier input (Python)

Run:

```
uv run zwiadbrain build-verifier-input --run-dir <run dir>
```

This runs the deterministic merge (`merge_lanes`): concatenate the lanes in the FIXED order
`crec, hearings, press, signing`, dedup statements by `(speaker, quote)` and hearings/media
by `url`, take the `narrative` from the `crec` lane, and write `<run dir>/verifier-input.json`
— a `subject` block plus `statements` and `related_media` arrays, **each entry stamped with
its 0-based merged `index`**. Python assigns every index; you never hand-build the index
array. No LLM calls happen in this step.

### 5. Dispatch the verifier subagent

`Read` `<run dir>/verifier-input.json` and dispatch the **leg-history-verifier** subagent
over it. Pass the `subject` block, the `statements` array, and the `related_media` array
exactly as written — each entry already carries its `index`; do not re-number or reorder
them. The verifier independently fetches each `source_url` / `url`, applies the verbatim +
attribution + contiguity checks to statements (and, for `related` items, the
subject-relevance clamp) and a Tier-2 identity check to media, and returns an object with
two arrays:

```json
{
  "statements": [{"index": 0, "speaker": "...", "quote_prefix": "...", "on_subject": true, "verified": true, "note": "..."}, ...],
  "related_media": [{"index": 0, "title_prefix": "...", "verified": true, "note": "..."}, ...]
}
```

**Write the verifier's output object, unmodified, to `<run dir>/verifier.json`.** Do not
reorder or re-key it — the assembler binds each verdict to its merged item by `index` and
re-checks the verifier's echo.

### 6. Assemble the render input (Python)

Run:

```
uv run zwiadbrain assemble-leg-history-input --run-dir <run dir>
```

This re-runs the SAME deterministic merge (byte-identical order to step 4, so the indices
line up by construction), attaches each verifier verdict to its merged statement / media by
`index`, and applies the echo cross-check fail-closed: a verdict whose `speaker` /
`quote_prefix` (or media `title_prefix`) does not match the merged item is downgraded to
`verified: false`, and a statement with no verdict is `verified: false`. It writes
`<run dir>/leghistory-research.json` — the render input. No LLM calls happen in this step.

### 7. Render and reindex (Python)

Run:

```
uv run zwiadbrain render-leg-history --in <run dir>/leghistory-research.json
uv run zwiadbrain reindex
```

`render-leg-history` parses the staging file, runs the deterministic grounding
gate over statements (URL resolution + quote-presence check + verifier verdict) and
over `related_media` (URL resolution + verifier identity verdict, no quote), and renders
the wiki page. A video `source_url` is resolved to its caption text so the unchanged gate
can verbatim-match a transcript quote. `reindex` rebuilds the FTS5 index.

### 8. Report

Summarize:

- Bill id and citation
- Spine counts: versions, committee_reports, votes, floor_consideration,
  enactment present/absent
- Statements: input count / grounded count (from the render output line)
- Hearings: input count / grounded count (from the render output line)
- Related media: input count / grounded count (from the render output line)
- Narrative: present/absent
- The rendered page separates **On This Bill** (the bill's own record, under the
  normal sections) from **Related (Subject Matter)** items (sponsor/official
  statements and hearings on the bill's topic) and a **Related Media** section (Tier-2
  videos / reference pages) — note if any `related` items or media survived.
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
