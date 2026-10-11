# Law brain — architecture

The law brain is a second brain for a practicing lawyer working in data privacy, AI governance
and harms, and cyber law. It follows Karpathy's LLM-maintained wiki pattern.

It is worth understanding one thing up front: **it has no code.** There is no build, no
dependency file, no test suite, no runtime. The entire system is one `CLAUDE.md` rulebook and
five Claude Code slash commands. Everything else is Markdown that Claude reads and writes under
those rules. It is also **not a git repo** — there is no version history.

This makes it the near-inverse of ZwiadBrain, which is 11,000 lines of deterministic Python
whose whole purpose is to make LLM output reproducible.

## Shape

```
law/
  CLAUDE.md              the schema and rulebook (127 lines) — read before any operation
  DECISIONS.md           append-only ADR log (6 entries)
  index.md               catalogue of every wiki page, grouped into 10 categories
  log.md                 one grep-parseable line per operation (487 so far)
  .claude/commands/      ingest · query · lint · brief · sync-zwiad
  wiki/                  204 pages, flat, named <type>-<kebab-slug>.md
  sources/               57 immutable source files (PDFs, dated web snapshots)
    zwiad/               419 synced memos — doubles as the sync ledger
  drafts/                long-form work in progress
```

### Directory contract

Who may write what is stated explicitly, and it is the load-bearing rule of the whole system:

| Path | Who writes it | Rule |
|---|---|---|
| `sources/` | copied in during `/ingest`, never modified after | immutable — source of truth |
| `sources/zwiad/` | `/sync-zwiad` only | immutable ledger of what has been synced |
| `wiki/` | Claude creates and edits | all LLM-maintained knowledge |
| `index.md` | updated on page creation or recategorization | table of contents, no orphans |
| `log.md` | one line appended per operation | grep-parseable activity log |
| `DECISIONS.md` | append-only | never edit past entries |
| `CLAUDE.md` | only on explicit user request | the schema itself |

The separation between `sources/` and `wiki/` is the same distinction ZwiadBrain draws between
`data/raw/` and `wiki/`: raw material is never touched by an LLM; interpretation lives somewhere
else and can always be rebuilt.

## Page schema

Frontmatter: `title`, `type`, `jurisdiction` (a list), `tags`, `created`, `updated`, `sources`
(paths into `sources/`), `status` (`active | stale | draft`), `citation`.

`type` is one of `statute · regulation · case · guidance · enforcement · framework · concept ·
incident · vendor · matter · person`, plus `brief` for `/brief` output. Files are named
`wiki/<type>-<kebab-slug>.md`.

Body sections, in order:

```
## Summary              3–5 lines, plain language
## Key points           concrete rules, tests, facts
## Citations            primary text + secondary authority
## Cross-references     [[slug]] — relationship
## Recent developments  reverse-chronological; maintained by /sync-zwiad
## Open questions       unsettled interpretation, circuit splits, pending amendments
```

Adherence is high across the 204 pages: every page has `## Cross-references`, 203 have
`## Summary`, 197 have `## Citations` and `## Open questions`, and 169 (83%) have accumulated a
`## Recent developments` section.

Current distribution: 78 `concept`, 71 `regulation`, 22 `case`, 12 `incident`, 9 `guidance`,
7 `framework`, 4 `vendor`, 1 `statute`. The `matter`, `person`, `enforcement`, and `brief`
categories exist in the taxonomy but are empty — `matter` deliberately so, under the
confidentiality rule.

## Invariants

These are the interesting part, and several rhyme with ZwiadBrain's.

**No source, no ingest** *(the strongest rule)*. If a source cannot be retrieved, the operation
**halts and reports** — paywall, 403, dead link, broken tooling, unreadable PDF, image-only
content. A source may never be reconstructed from search-engine extracts, aggregator rewrites,
other outlets' coverage, or memory. And explicitly: *a prominent caveat is not a substitute for
stopping.* The stated reasoning is that caveats decay while entries persist — by the next query,
the difference between a page built on a source somebody read and one built on a summary is
invisible.

This is the same trust boundary as ZwiadBrain's D36 grounding gate, reached from the opposite
direction: ZwiadBrain enforces it mechanically (fetch the URL, match the quote byte-for-byte,
have a second model check); the law brain enforces it as a rule the agent must obey. Both fail
closed. A retrieval *failure* is distinguished from a source *limitation* — a retrieved but
incomplete source may be ingested with the limitation recorded.

**Accretion, not duplication.** One canonical page per statute. New developments append a dated
bullet to `## Recent developments`; they do not mint `update-2026-07-14-*.md` pages. When a
regulation changes, the page is **versioned, not overwritten** — a new `## Amendments` section
records the date, what changed, and a cite, and the old text stays.

**No orphans.** Every new page is linked from `index.md` in the same turn. This is holding:
`index.md` has exactly 204 entries for 204 pages after 487 operations.

**Confidentiality by default.** No client identifiers, privileged communications, or
matter-specific facts unless explicitly directed; de-identified placeholders (`Client A`,
`Matter M-01`) otherwise; anything privilege-shaped gets flagged.

**Rule separate from commentary.** Statutory text and citations are kept visually distinct from
analysis and opinion — and where a claim rests on a specific provision, the article or section
is cited *inline in the body*, not only in the Citations block.

**Jurisdiction tags are load-bearing.** `/query` and `/brief` filter on them, so they are tagged
rigorously and the index repeats them in brackets.

## The five pipelines

Four of the five write. All converge on the same three shared-state files: `wiki/`, `index.md`,
`log.md`.

### `/ingest <path-or-url>`

The human-driven entry point. Classify the source first — and if it is client-specific, **stop**
and ask what to store, what to de-identify, and whether anything is privileged. Then acquire it
(URL → fetch and save a dated Markdown snapshot into `sources/` with a header block recording
the original URL, fetch date, and publisher; local file → copy in as-is), read it *fully* —
skimming is explicitly not acceptable — and identify touchpoints by grepping `index.md` and the
wiki filenames for an existing canonical page.

The plan is stated to the user **before** anything is written. Then the wiki updates land with
inline provision cites and bidirectional cross-references, `index.md` gains an entry, and
`log.md` gains a line. The report calls out interpretive tensions and, importantly, whether the
new source **contradicts** an existing wiki claim — in which case both sides get cited and the
user decides.

Writes: `sources/`, `wiki/`, `index.md`, `log.md`.

### `/query <question>`

Read-mostly. Scope the question and its jurisdictions — asking rather than assuming if unclear —
locate pages via `index.md` and then a keyword grep, read the candidates in full, and consult
`sources/` only when the wiki lacks the specific provision text or holding.

The synthesis discipline is the substance: separate rule from application, cite primary authority
inline *and* point every wiki-derived claim at its `wiki/<file>.md` path, flag splits and
unsettled questions without manufacturing clarity, and be explicit about jurisdictional scope.
Output is fixed at six blocks — question restated, short answer, analysis, citations, **gaps**
(candidates for `/ingest`), and caveats about the limits of a wiki-based answer.

If the synthesis produced something durable — a new cross-reference, a novel frame — it is
proposed back as a wiki update and applied on confirmation. Answers are the lawyer's own work
product, never framed as client-facing advice unless asked.

Writes: `log.md` always; `wiki/` only on confirmation.

### `/lint`

Pure read. Ten checks — schema violations, implausible jurisdiction tags, orphans, broken
`[[slug]]` links, stale pages (`status: stale`, or `updated` more than 90 days old on an active
page, prioritized because regulations and guidance move fast), missing source files, citation
gaps, cross-page contradictions within a jurisdiction, index hygiene, and confidentiality red
flags.

It produces a report and stops. The user decides what to fix, and the confidentiality check is
marked review-only: it never auto-redacts.

Writes: `log.md`.

### `/brief <topic>`

Assembles a memo from the wiki — IRAC memo (default), plain-language client advisory,
comparative chart, or compliance checklist. Reads every touching page in full, composes into
`## Issue / Rule / Analysis / Conclusion / Risks & open questions / Authorities`, and files the
result to `wiki/brief-<date>-<topic>.md`.

Note that a brief's `sources:` frontmatter points at **wiki pages**, not `sources/` — it is
synthesis of synthesis. It will not force a conclusion on an unsettled topic, and every rule
statement needs a primary cite.

Writes: `wiki/brief-*.md`, `index.md`, `log.md`.

### `/sync-zwiad`

The one that actually carries the traffic. It walks an external Syncthing-synced folder of daily
regulatory memos, finds the ones not yet in `sources/zwiad/`, and integrates them.

Per memo: read it fully, **copy** (never move) it into `sources/zwiad/`, route it to the
canonical wiki page for its topic, append a dated bullet to that page's `## Recent developments`
(newest first, positioned after `## Key points` and before `## Cross-references`), and bump
`updated:`. A memo spanning several topics gets a bullet on each page, all citing the same source
file.

Three guardrails carry the design:

- **Ambiguous routing defers.** If it is unclear which canonical page a memo belongs to, the memo
  is reported for human decision and *not* copied to `sources/zwiad/` — so it stays in the
  unsynced queue for next time. The ledger is only stamped once the memo is genuinely placed.
- **The ledger is the filename.** Presence of `sources/zwiad/<filename>` means done, which makes
  the command idempotent: a clean re-run syncs nothing. An existing file is never overwritten.
- **Accretion is enforced.** Significant memos are *flagged* for possible promotion to a
  dedicated page, but promotion is a separate human decision — the command will not create
  per-memo pages.

The upstream folder is treated as read-only: a subscription, never a thing to write back to.

Writes: `sources/zwiad/`, `wiki/`, `index.md`, `log.md`.

## What actually drives it

Of 487 logged operations between 2026-04-13 and 2026-08-24:

| Operation | Count |
|---|---|
| `sync-zwiad` | 428 |
| `ingest` | 50 |
| `query` | 5 |
| `lint` | 3 |
| `brief` | 0 |

The external memo stream, not manual ingestion, is what feeds this brain — 88% of all activity,
and 81% of wiki pages cite at least one memo. Worth knowing before reasoning about it as a
hand-curated wiki: it is mostly an accretion buffer with a strict routing discipline.

## Relationship to ZwiadBrain

Two links, pointing in opposite directions. **They do not form a loop**, and the shared name
actively obscures that.

### ZwiadBrain reads the law brain

`.env` sets `LAW_BRAIN_PATH` to the law brain's root. `/zwiad-sync-lawbrain` matches a law-brain
page to a tracked bill or enforcement matter — deterministic key extraction first, with an
LLM matcher fallback gated behind a deterministic confirm — and copies that page's analysis
**verbatim** into a spliced `lawbrain:region` on the ZwiadBrain page, headed:

> Law brain authoritative for analysis; official sources authoritative for bill text and
> legislative history.

That sentence is the division of labor. **ZwiadBrain never writes to the law brain.** Every match
decision, rejections included, is recorded permanently in `wiki/links.yaml`.

Status: a pilot. The machinery is complete and exactly one ZwiadBrain page carries commentary.

### The law brain does *not* read ZwiadBrain

Despite its name, `/sync-zwiad` has nothing to do with this repository. It consumes
`ZwiadFiles/ZwiadRep/`, a Syncthing folder of daily regulatory memos — a different upstream
entirely. The law brain contains no reference to "ZwiadBrain" anywhere.

**So nothing carries ZwiadBrain's 395 primary-source pages back into the law brain.** The law
brain learns about new statutes from the memo stream, not from the tracker built to track them.
That is a real gap, and naming it here is the point of this section.

### How they differ

| | Law brain | ZwiadBrain |
|---|---|---|
| Unit | a topic | one bill / one enforcement action |
| Pages are | **written** — prose is the artifact | **compiled** — prose is a render target |
| Source of truth | the prose | the frontmatter |
| Implementation | 5 prompt workflows, no code | 11k lines of Python, 57 test modules |
| Versioning | none — not a git repo | git; byte-identical render enforced by test |
| Scope | privacy, AI governance, AI harms, cyber — **global** | AI/privacy/cyber legislation — **US federal + state** |
| Updates | accrete a dated bullet | diff a cursor, re-render the page |
| Scope control | human judgment | `topics.yaml` rubric + committed reject ledger |
| Answers | what the law *means* | what the law *says*, and when it changed |

The complementarity is genuine: ZwiadBrain can tell you that a state bill was amended on a
particular date and quote the amendment; the law brain can tell you whether that matters. The
`lawbrain:region` splice is the one place those two currently meet.
