# Backfill scaling gaps 1 + 2 — verdict & summary persistence

Design for the two code-bearing gaps in `docs/backfill-scaling.md`: resumable
classification (gap 1) and a leaner summary handoff (gap 2). Gap 3 (push/merge
cadence) is convention-only and gap 4 (LegiScan quota) has no clean API hook, so
neither is implemented here.

## Problem

Classification verdicts and plain-language summaries live only in the interactive
session's context, applied by hand or by ad-hoc `data/runs/build_*.py` scripts. A
plan rate-limit or context cutoff mid-batch loses that work. The 2026-06-08 session
hit exactly this (8 of 16 classifiers died) and forced composing summaries inline to
finish six states. The fix is to persist both the classifier verdict and the
summary to committed-or-staged JSON, and add two small CLIs that apply them — so a
cutoff only loses the *unprocessed tail*, and a rerun resumes from the persisted files.

## Architecture

Two symmetric "apply" CLIs, each backed by a pure helper in a new pipeline module —
mirroring how `pipeline/rejects.py` backs the `record-rejects` command. The existing
`render-classified` and `record-rejects` commands are unchanged; this slots in
*before* them.

```
fetch-candidates            → candidates.json
  classifier subagent       → verdicts.json    [{id, in_scope, topics, reason}]
  apply-verdicts            → classified.json (topics applied) + rejects.json
  batch-summarizer subagent → summaries.json   {id: summary}
  apply-summaries           → classified.json (summaries merged in, in place)
  render-classified  (unchanged) → wiki pages
  record-rejects     (unchanged) → reject ledger
```

The two persisted files (`verdicts.json`, `summaries.json`) are the resumability
layer: classification persists in the first, summarization in the second, decoupled
because they come from different subagents.

## Components

### 1. `Verdict` model — `src/zwiadbrain/pipeline/verdicts.py`

A pydantic model, deliberately **not** in `models.py` (which is the typed shape of
committed wiki frontmatter; a verdict is a transient staging artifact):

| Field | Type | Notes |
|-------|------|-------|
| `id` | `str` | candidate bill id |
| `in_scope` | `bool` | classifier verdict |
| `topics` | `list[str] = []` | applied to in-scope bills |
| `reason` | `str = ""` | rationale, kept for the audit trail; not persisted to the page |

### 2. Pure functions — `verdicts.py`

Both operate on `Bill` objects (the CLI parses `candidates.json`/`classified.json`
into `Bill`s first, so candidates are validated on the way in and output JSON is
canonical):

- `split_by_verdict(candidates: list[Bill], verdicts: list[Verdict]) -> tuple[list[Bill], list[Bill], list[str]]`
  returns `(classified, rejects, pending_ids)`:
  - in-scope verdict → candidate with `topics` applied via `model_copy`, into `classified`
  - out-of-scope verdict → candidate unchanged, into `rejects`
  - no verdict for a candidate → its id into `pending_ids` (the unclassified tail; **not** emitted, **not** an error)

- `apply_summaries(classified: list[Bill], summaries: dict[str, str]) -> tuple[list[Bill], list[str]]`
  returns `(updated, pending_ids)`:
  - each bill with an entry in `summaries` → `summary` set via `model_copy`
  - each bill with no entry → its id into `pending_ids` (the un-summarized tail)

### 3. CLI commands — `cli.py`

- `apply-verdicts --in <candidates.json> --verdicts <verdicts.json> [--out <dir>]`
  reads both files, runs `split_by_verdict`, writes `classified.json` + `rejects.json`
  (default location: next to `candidates.json`; `--out` overrides). Echoes
  `applied N verdict(s): X in-scope, Y reject(s), Z pending`.

- `apply-summaries --in <classified.json> --summaries <summaries.json>`
  reads both, runs `apply_summaries`, **rewrites `classified.json` in place**. Echoes
  `applied M summarie(s): K set, Z pending`. Re-applying the same summaries is
  byte-identical (D20).

Both reuse `stage_json`'s indent-2 write and the `validate_model` boundary helper.
`summaries.json` is a JSON object (`{id: summary}`); a non-object is a `ConfigError`.

### 4. Gap-2 prompt + skill changes (markdown, not unit-tested code)

- New `.claude/agents/batch-summarizer.md`: takes N bills in one prompt, returns a
  `{id: summary}` JSON map. The existing per-bill `.claude/agents/summarizer.md` is
  left untouched (still used by `/zwiad-refresh`, where one bill changes at a time).
- Updated steps in `.claude/commands/zwiad-scan-states.md` and
  `.claude/commands/zwiad-backfill.md` to the new flow: classifier → `verdicts.json`
  → `apply-verdicts` → batch-summarizer → `summaries.json` → `apply-summaries` →
  `render-classified` → `record-rejects`.

## Error handling

Fail loud at the boundary; tolerate the tail.

- **ConfigError → exit 1** (via the CLI's existing `except AppError` path):
  - unreadable or non-list `candidates.json` / `verdicts.json`; non-object `summaries.json`
  - a verdict `id` that matches no candidate (stale / typo guard)
  - an `in_scope` verdict with **zero topics** (a classified-in bill must carry a topic)
  - a summary key that matches no classified bill (stale / typo guard)
- **Reported, never an error:** pending (uncovered) candidates and summaries. This is
  the resumability contract — a cutoff loses only the tail; the operator reruns the
  classifier/summarizer on the pending ids, appends to the JSON, and re-applies.

Taxonomy validation (topic ∈ `{ai, privacy, cyber}`) is **not** duplicated here —
`render-classified` remains the single taxonomy gate. `apply-verdicts` only enforces
the structural "in-scope ⇒ ≥1 topic" rule.

## Testing (TDD)

- `tests/test_verdicts.py` — pure functions, mirroring `tests/test_rejects.py`:
  happy split, pending tail, reject pass-through, stale-verdict `ConfigError`,
  in-scope-with-no-topics `ConfigError`; `apply_summaries` set / pending / stale-key
  `ConfigError` / idempotency.
- Extend `tests/test_cli.py` — `apply-verdicts` and `apply-summaries` via `CliRunner`
  against `tmp_path` fixtures, asserting written `classified.json` / `rejects.json`
  contents, exit codes, and the reported count lines.

## Out of scope / deferred

- The one-off `data/runs/build_*.py` and `data/runs/extract_states.py` scripts are
  **superseded** by `apply-verdicts` but **not deleted** in this change — they are
  throwaway run artifacts, and removal stays separate from the feature.
- Gap 3 (push/merge cadence) — convention, no code.
- Gap 4 (LegiScan quota surfacing) — LegiScan's free tier exposes no clean
  per-response quota signal; left as a manual operational check.

## Decision to log (DECISIONS.md)

The verdict-persistence convention and the two-CLI split (over folding the summary
into `verdicts.json`): keeping classification and summarization in separate persisted
files keeps the two subagents decoupled, so a classifier rerun does not require
summaries to already exist.
