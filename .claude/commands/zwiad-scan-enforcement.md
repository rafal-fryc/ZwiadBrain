---
description: Backfill enforcement actions (FTC + state AGs) into the ZwiadBrain wiki, discovering, classifying, matching, and extracting each via subagents (runs on your regular Claude plan usage).
argument-hint: "[--agency <ftc|ag-slug>] [--limit <N>]"
allowed-tools: Bash, Read, Write, Task
---

# ZwiadBrain enforcement scan

Orchestrate an enforcement-action scan end to end. Python does the deterministic fetch
and render; you (this interactive session) do the LLM steps by dispatching subagents, so
the work runs on the regular Claude plan — **not** the API or the Agent SDK credit.

**Arguments:** `--agency <slug>` runs one source (`ftc` or a configured AG slug like
`ca-oag`). Omit it to run FTC + every enabled `[[enforcement.state_ag]]` in
`zwiadbrain.toml`. `--limit <N>` caps items per source (default 5); every in-scope
action costs a classifier + extractor dispatch, so `--limit` bounds plan usage
directly (D49).

## Steps

### 1. Fetch candidates (Python, deterministic)

Run:
```
uv run zwiadbrain fetch-enforcement-candidates [--agency <slug>] --limit <N>
```
It discovers recent items from the FTC press-release feed and/or configured AG feeds
(forward-from-now), fetches each article's full text, parses a strong key (docket
number or FTC matter number where present), reads existing tracked matters, and writes
`candidates.json` + `matters.json` under `data/runs/<id>/`. **Note the exact path it
prints** — you will use it in steps 2–7.

### 2. Read the candidates

`Read` both files it wrote:
- `candidates.json` — each entry: `title, agency, agency_slug, jurisdiction, url,
  published, text, strong_key, matter_id, match_source`
- `matters.json` — existing tracked matters:
  `{id, agency_slug, jurisdiction, respondent, date_filed, strong_key}`

### 3. Classify each item (subagent: `enforcement-classifier`)

For every candidate, dispatch the **enforcement-classifier** subagent with the item's
`title` and `text`. It returns
`{in_scope, topics, confidence, rationale, positive_criterion, disqualifier_applied}`.
- Log each decision (title, in_scope, confidence, positive_criterion/disqualifier) to
  the transcript.
- **Drop** items where `in_scope` is false. Keep the returned `topics` for the rest.
- **Validate topics**: if the classifier returns any topic not in
  `{ai, privacy, cyber}`, treat it as a classifier error — drop the item to the
  transcript and do NOT dispatch further subagents on it.

### 4. Resolve the matter for each in-scope item

For each in-scope item, determine the matter identity before extracting:

- **Strong-key match** (`matter_id` is already set in `candidates.json`): the Python
  fetcher found an exact docket/matter-number match. Keep `matter_id` as-is;
  set `match_source = "strong_key"`, `match_confidence = 1.0`.
- **Strong key present but unmatched** (`strong_key` is set, `matter_id` is null):
  this is a new action with a parseable key but no existing matter. Set
  `matter_id = null`, `match_source = "none"`, `match_confidence = 0.0`.
- **No strong key**: build a shortlist from `matters.json` — same `agency_slug`,
  overlapping respondent tokens, `published` within ~120 days. If the shortlist is
  non-empty, dispatch **enforcement-matcher** with the item
  (`title, agency, respondent, date, text excerpt`) + the shortlist → `{match,
  confidence}`. Set `matter_id = match` (may be null), `match_source = "llm"`,
  `match_confidence = confidence`. If the shortlist is empty, set
  `matter_id = null`, `match_source = "none"`, `match_confidence = 0.0`.

Note: `render-enforcement` re-confirms any `llm` match deterministically and falls
back to a new page (with a `possible-duplicate-of` note) if confidence is too low —
you do NOT confirm the LLM match here.

### 5. Extract fields (subagent: `enforcement-extractor`)

For each in-scope item, dispatch the **enforcement-extractor** subagent with the
item's `title` and `text`. It returns:
`{summary, respondent, action_type, statutes, penalties, date_filed, date_resolved,
status, allegations, outcome, significance, development_summary}`.
Set `topics` from the classifier output (the extractor does not return topics).

### 6. Stage the classified items

`Write` all in-scope items to `classified.json` in the run directory. Each entry
**must** include every key listed below — `render-enforcement` does hard key access
and will raise `KeyError` on any omission:

**Match keys** (from steps 3–4):
- `matter_id` (string id or null)
- `match_source` (`"strong_key"` | `"llm"` | `"none"`)
- `match_confidence` (float)

**Pass-through from the candidate** (from `candidates.json`):
- `agency`, `agency_slug`, `jurisdiction`, `strong_key`, `title`

**Extractor fields** (from step 5 — use `null` for any the extractor omitted,
e.g. `background`):
- `respondent`, `summary`, `background`, `allegations`, `outcome`, `significance`,
  `action_type`, `statutes`, `penalties`, `status`, `date_filed`, `date_resolved`

**Assembled fields** — the extractor does NOT emit these; you must build them:
- **`development`**: assemble the object
  `{"date": date_filed (or the candidate's published date if date_filed is null),
  "summary": development_summary (from the extractor),
  "source_url": the candidate's url}`.
  `render-enforcement` calls `EnforcementDevelopment.model_validate(e["development"])`
  — the key must be present and `source_url` must be a valid `http(s)` URL.
- **`source_url`**: the candidate's `url` (top-level string).
- **`sources`**: a map of `{<agency display name>: <candidate url>}`,
  e.g. `{"FTC": "https://www.ftc.gov/..."}` or `{"California AG": "https://..."}`.

### 7. Render + index (Python, deterministic)

Run:
```
uv run zwiadbrain render-enforcement --in data/runs/<id>/classified.json
uv run zwiadbrain reindex
```
`render-enforcement` builds matter ids, consolidates strong-key and confirmed matches,
re-confirms LLM matches (failing safe to a new page with a `possible-duplicate-of`
note), and writes pages under `wiki/federal/enforcement/` (FTC) and
`wiki/states/<st>/enforcement/` (state AGs). `reindex` rebuilds the FTS5 index from
the committed wiki.

### 8. Report

Summarize: items discovered per source, classified in vs out (with out-of-scope
reasons), new vs consolidated matters, and any `possible-duplicate-of` flags that
`render-enforcement` emitted. Do not commit — leave the wiki changes for review.

## Notes

- Keep `ANTHROPIC_API_KEY` unset so subagents use your plan session, not the API (D26).
- Only `topics[]` and the extracted fields are persisted; classifier
  confidence/rationale stay in the transcript.
- Re-running this command IS the enforcement refresh (D52) — updates arrive as new
  feed items and consolidate into existing matters by strong key or confirmed match.
- The `--limit` default of 5 is conservative; raise it after reviewing classifier
  verdict rates across sources (D49).
