---
description: Attach read-only law-brain commentary (+ Further Reading links) onto the tracked bills and enforcement pages it concerns, via deterministic key-matching with an LLM fallback for keyless pages (runs on your regular Claude plan usage).
argument-hint: "[--dry-run]"
allowed-tools: Bash, Read, Write, Task
---

# ZwiadBrain law-brain sync

Attach commentary from the sibling **law brain** (read-only) onto the items
ZwiadBrain already tracks. Python does the deterministic key-match, copy, and render;
you (this interactive session) do the single LLM step — judging keyless pages — by
dispatching a subagent, so that work runs on the regular Claude plan, **not** the API
or the Agent SDK credit (D26).

This command is **commentary-only**: it never mints new tracked stubs from the law
brain (that is the gated PHASE-11 discovery path, `discover=false`, D14). It is the
**sole** creator/updater/remover of the `<!-- lawbrain:region -->` block on a page
(D63); ordinary `/zwiad-refresh` and `/zwiad-backfill` re-renders preserve that region
verbatim but never rebuild it.

**Arguments:** `--dry-run` runs the fetch + match + subagent steps and prints the
intended writes (commentary attachments, review-queue entries, registry records) with
**zero** edits to `wiki/`. Omit it to apply.

## Steps

### 1. Fetch candidates (Python, deterministic)

Run:
```
uv run zwiadbrain fetch-lawbrain-candidates
```
If the law brain is unavailable (`LAW_BRAIN_PATH` missing or `lawbrain.enabled=false`),
it prints a no-op line and exits 0 — **stop here and report the no-op**. Otherwise it
reads the law-brain wiki, extracts jurisdiction-qualified keys per page, loads the
tracked items (bills + enforcement actions) from the committed wiki as `TargetRef`s,
consults `links.yaml` (skipping pages already decided whose decision hash is unchanged —
the key-set, or for a keyless page its key-set plus candidate shortlist, D9), runs the
deterministic set-intersection match, builds a capped, topically-floored shortlist for
pages with no key match (D124), and writes
`lawbrain-candidates.json` + `targets.json` under `data/runs/<id>/`. **Note the exact
path it prints** — you use it in steps 2–5.

### 2. Read the candidates

`Read` both files it wrote:
- `lawbrain-candidates.json` — each entry: `slug, title, type, jurisdiction, tags,
  citation, summary_excerpt, keys, keys_hash, match ("deterministic" | "keyless" |
  "collision" | "not_in_scope" | "override" | "refresh"), target_id?, shortlist?`
- `targets.json` — the tracked items as `{id, kind, jurisdiction, title, keys}`.

A `match: "deterministic"` entry already has its `target_id` (exactly one shared key,
confidence 1.0) — **do not** dispatch a subagent for it. A `match: "collision"` entry
shares keys with more than one target — the operator picks the target in the review
queue; do not dispatch a subagent for it either. A `match: "not_in_scope"` entry matched no key and
no shortlist candidate cleared the topical floor — it is already decided; stage it as
`not_in_scope` without a dispatch. A `match: "override"` entry is a link the operator
accepted in `review-queue.md` whose commentary is not yet on its target — it carries its
`target_id`; stage it as `matched_by: "llm"`, `confidence: 1.0` without a dispatch
(render honors the recorded override for that target only). A `match: "refresh"` entry
is an existing deterministic link whose law-brain page changed since it was copied —
stage it like a deterministic link (`matched_by: "deterministic"`, `confidence: 1.0`) so
the block is re-copied. Only `match: "keyless"`
entries (zero shared keys, non-empty shortlist) need the LLM step.

### 3. Judge keyless pages (subagent: `lawbrain-matcher`)

For every candidate with `match: "keyless"`, dispatch
the **lawbrain-matcher** subagent with the page's `slug, title, type, jurisdiction,
tags, citation, summary_excerpt` and the entry's `shortlist`. It returns
`{decision, target_id, confidence, rationale}`.
- Log each decision (slug, decision, target_id, confidence, rationale) to the
  transcript.
- Carry the matcher result onto the entry as `matched_by: "llm"`, `target_id`,
  `confidence`. Leave `match: "deterministic"` entries as `matched_by: "deterministic"`,
  `confidence: 1.0`.

Note: `render-lawbrain-commentary` re-confirms every `llm` link deterministically
(require ≥1 shared key, D16) and routes a failed confirm to the review queue with a
`weak-grounding` note — you do NOT confirm the LLM match here.

### 4. Stage the classified items

`Write` the decided entries to `classified.json` in the run directory:
- every deterministic-link, `refresh` and `override` entry, and every `llm`
  `decision: "link"` entry, each with
  `slug`, `target_id`, `matched_by` (`"deterministic"` | `"llm"`) and `confidence`;
- every `not_in_scope` entry — both `match: "not_in_scope"` candidates and keyless
  pages the matcher declined — as `{slug, matched_by: "not_in_scope"}`. **Do not drop
  these**: staging them is what records them in `links.yaml`, so they are not
  re-proposed next run;
- every `collision` entry as `{slug, matched_by: "collision"}`. Render queues one
  `(collision)` line per candidate target in `review-queue.md`. The operator marks one
  `[accept]` (that target is linked on the next sync and its sibling lines are pruned)
  or marks every line `[reject]` (the page is recorded as rejected).

`render-lawbrain-commentary` re-reads the page from the law brain by slug and recomputes
its keys and decision hash from disk (it does not trust keys, hashes, or a body passed
through JSON), so the staged entry stays lightweight.

### 5. Render + index (Python, deterministic)

Run (omit `--dry-run` to apply; include it to preview):
```
uv run zwiadbrain render-lawbrain-commentary --in data/runs/<id>/classified.json [--dry-run]
uv run zwiadbrain reindex
```
`render-lawbrain-commentary` re-confirms each `llm` link, loads the matched law-brain
page, harvests `## Further Reading` links from the page body and its referenced
`sources/zwiad/*.md` memos (primary-source domains excluded), copies the body verbatim,
idempotently merges it into the target's `commentary_sources`, and re-renders the page
— the fresh render carries the commentary bodies, so its `lawbrain:region` is
authoritative (D63). It detects pages deleted from the law brain (`stale`), writes new
uncertain proposals AND applies operator-resolved `[accept]`/`[reject]` tokens in
`review-queue.md` in one pass (D61), records decisions in `links.yaml` (D9), and
isolates malformed entries per-item (dropped list). `reindex` rebuilds the FTS5 index
from the committed wiki. Skip `reindex` when running `--dry-run`.

### 6. Report

Summarize: pages scanned, deterministic links applied, LLM links confirmed vs routed
to review, collisions, stale notes, registry records written, and any per-item drops.
For `--dry-run`, report the intended writes only. **Do not commit** — leave the wiki
changes (and `links.yaml` / `review-queue.md`) for review.

## Notes

- Keep `ANTHROPIC_API_KEY` unset so the subagent uses your plan session, not the API
  (D26).
- The deterministic key path is what attaches commentary at the current corpus size;
  the LLM path is mostly collision-resolution and review-candidate generation until the
  tracked corpus grows (it cannot auto-apply a topical-only match — `confirm_match`
  requires a shared key, D16).
- Re-running this command IS the law-brain refresh: a page whose `content_hash`
  changed re-copies that block; an unchanged page renders byte-identically (clean
  `git status`, D20).
- The law brain is **read-only** (D2). This command never writes under
  `LAW_BRAIN_PATH`.
