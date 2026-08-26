# ZwiadBrain Wiki

This directory is **the committed product** of ZwiadBrain: standardized Markdown pages
tracking U.S. federal and state **legislation** and **enforcement actions** in **AI, privacy,
and cybersecurity**.

Everything else — raw scrapes in `data/raw/`, the SQLite index and watchlist — is *derived* and
gitignored, rebuilt from these pages by `zwiadbrain reindex`. **The frontmatter of these pages
is the source of truth.** The body is re-rendered from it, and `render_page` is a pure function:
unchanged input produces byte-identical output, so a no-op re-render leaves `git status` clean
(D20).

Bill evolution — amendments, status flips, newly grounded statements — is captured as git diffs.
The git history of this directory *is* the change record.

## Organization

```
wiki/
  federal/
    bills/          Congress.gov bills           (9 pages)
    enforcement/    FTC enforcement actions      (144 pages)
  states/
    <st>/           36 states, USPS lowercase
      bills/        LegiScan-tracked state bills (242 pages)
      enforcement/  state AG actions — adapters exist, no content yet
  .rejects/
    federal.json    scope-versioned negative cache (1,028 entries)
    state.json                                     (419 entries)
  links.yaml        permanent record of law-brain link decisions
```

Only two filename suffixes exist, and the naming is fully regular:

| Kind | Pattern | Example |
|---|---|---|
| Federal bill | `{congress}-{chamber}-{number}.md` | `117-hr-2471.md` |
| State bill | `{st}-{year}-{chamber}-{number}.md` | `ca-2025-sb-53.md` |
| Enforcement | `{agency}-{docket-slug}.md` | `ftc-1-23-cv-01549.md` |
| Extracted text | `<id>.text.md` | `ca-2025-sb-53.text.md` |

## Page types

### Bill page

Frontmatter carries the watchlist metadata. Federal and state share most of it and diverge on
how each source identifies and versions a bill:

- **Shared** — `id, type, title, bill_number, chamber, jurisdiction, status, enacted,
  introduced_date, latest_action, latest_action_date, update_date, sponsors, sources, topics,
  tracking, summary_hash, amendments_count`
- **Federal only** — `congress`, `policy_area`, `update_date_text` (the Congress.gov change
  cursor)
- **State only** — `session`, `legiscan_bill_id`, `change_hash` (the LegiScan change cursor)

Body sections, in render order: `## Summary` · `## Status & Timeline` · `## Amendments`
(each with a plain-language "what changed") · `## Legislative History` · `## Full Text` ·
`## Extracted Text` · `## Related Bills` · `## Sources`.

### Enforcement page

Frontmatter: `id, type, title, agency, respondent, action_type, docket, jurisdiction, status,
date_filed, date_resolved, statutes, topics, tracking, sources` — plus the prose fields
`summary, background, allegations, outcome, significance, penalties, developments`.

**Why enforcement prose lives in frontmatter and bill prose does not (D40):** bill bodies are
re-derived from the API on every render, so persisting them would be redundant. Enforcement
prose is non-re-derivable LLM output, and consolidation across repeat scans must be monotonic —
a later scan may add to a matter but must never silently lose what an earlier one established.

## Spliced regions

Two body regions are written by *different* commands than the one that renders the page, so
each is delimited by HTML comment markers and spliced idempotently. A command that does not own
a region preserves it verbatim.

| Region | Owner | Purpose |
|---|---|---|
| `extracted-text:region` | `extract-text` (D67) | links the `.text.md` sidecar |
| `lawbrain:region` | `/zwiad-sync-lawbrain` (D63/D64) | `## Commentary & Analysis` + `## Further Reading` |

This is what makes re-render safe: `/zwiad-refresh` can rewrite a bill body without destroying
commentary attached weeks earlier, and `/zwiad-sync-lawbrain` splices commentary in place
without re-rendering the bill.

## `.text.md` sidecars

243 pages carry a companion holding the **full official document text**, extracted with Docling
from the authoritative source and headed with a fixed two-line banner noting that the linked
sources remain authoritative.

They exist for three reasons:

1. **Reviewability.** Some are enormous — one New York bill's sidecar runs 8,277 lines. Keeping
   that out of the main page keeps pages diffable and frontmatter scannable.
2. **Grounding corpus.** Enacted-bill summaries are written against the extracted text rather
   than the API's summary field (D110), and scope decisions get made on it — at least one bill
   was flipped into scope on the strength of its extracted text.
3. **Search.** Sidecar text is indexed into FTS.

Extraction runs **out-of-process** with a 12-page OCR cap and a 300-second wall clock (D105):
Docling's native stack can abort the interpreter outright, so it is isolated, and any failure
returns empty and fails the render closed rather than writing a half-extracted page.

## Legislative history

Not a separate file — a `## Legislative History` section on the bill page, backed by a
`leg_history:` frontmatter block. 120 pages carry one.

Persistence is deliberately split (D37/D40):

- **Persisted to frontmatter** — `hearings`, `statements`, `related_media`, `narrative`.
  Expensive, non-deterministic research output; losing it would mean re-running the whole
  grounding pipeline.
- **Body-only, re-derived every render** — `versions`, `votes`, `committee_reports`,
  `floor_consideration`, `conference`, `enactment`. These come back identically from the API,
  so persisting them would only create drift.

Rendered subsections: `### Legislative Journey` (the narrative) · `### Versions` ·
`### Hearings` · `### Statements` · `### Votes` · `### Committee Reports` ·
`### Floor Consideration` · `### Related Media` · `### Related (Subject Matter)` ·
`### Enactment`.

Every quoted statement renders with a ✓ verified marker and a `[source]` link, and it only
earns that marker by passing the D36 gate: the URL returns 200, the normalized quote is present
verbatim on the page, at least 20 characters, **and** an independent cross-model verifier
agrees. Since D106 the narrative is verifier-checked too, and dropped at render if it fails.

## Provenance beside the wiki

The pages are only half the record. What the wiki *deliberately excludes* is tracked just as
carefully:

| Artifact | Role |
|---|---|
| `.rejects/{federal,state}.json` | Scope-versioned negative cache (D82/D96). A bill classified out-of-scope stays recorded, so it is never re-classified for free — and when scope rules change, staleness is **surfaced** via `stale-rejects`, never auto-invalidated. |
| `links.yaml` | Every law-brain match decision — link, not-in-scope, or reject — recorded permanently, rejections included. |
| `../reference/topics.yaml` | The `ai`/`privacy`/`cyber` taxonomy. Single source for both the recall pre-filter and the classifier's precision rubric, co-located so the two stages cannot drift. |
| `../reference/orrick-ai-tracker-2026-07.yaml` | Snapshot of two external AI-law trackers, parsed deterministically — used as a coverage oracle, not an ingest source. |
| `../reference/tracker-corrections.yaml` | Hand-verified overrides on that snapshot. A correction matching no row is a **hard error**, so stale entries surface instead of rotting. |
| `../docs/backfill/` | Campaign trackers: one row per (jurisdiction × period) unit, plus the leg-history queue. |

## Relationship to the law brain

`## Commentary & Analysis` is **copied verbatim** from a separate, read-only knowledge base —
a topic-per-page LLM wiki maintained by a practicing lawyer, located via `LAW_BRAIN_PATH`.
ZwiadBrain reads it and never writes to it.

The division of labor is stated on every copied block: **the law brain is authoritative for
analysis; official sources are authoritative for bill text and legislative history.**

This is currently a pilot — the machinery is complete, but exactly one page carries commentary.
See [`../docs/law-brain/`](../docs/law-brain/) for what the law brain is and how it works.
