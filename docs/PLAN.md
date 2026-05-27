# ZwiadBrain — AI/Privacy/Cyber Legislation & Enforcement Tracker, with Law-Brain Integration

## Context

`ZwiadBrain` is a bare scaffold (`README.md`, `.gitignore`, `.gitattributes`, one init commit — no code yet). Goal: an LLM-driven wiki + agent system that tracks U.S. **federal and state** legislation and **enforcement actions** in **AI, privacy, and cybersecurity**, assembles standardized **legislative history** once a bill is enacted, and stays current via a **scheduled scan** (local cron, a few times/week).

This planning session refined one thing decisively: how ZwiadBrain integrates the existing **law brain** at `C:\Users\rafst\Documents\projectas\Brains\law`. Exploration revealed the law brain is **not a flat reference corpus** — it is a full sibling wiki using the same Karpathy Markdown+YAML pattern (155 curated pages: `regulation-*`, `case-*`, `concept-*`, `guidance-*`, `incident-*`, `framework-*`, `vendor-*`), with an `index.md`, `CLAUDE.md` rulebook, `DECISIONS.md`, and grep-parseable `log.md`. It is itself fed several times a week by daily "Zwiad" regulatory-news/commentary memos (in `…\ZwiadFiles\ZwiadRep\`, synced via Syncthing) through a manual `/sync-zwiad` command. **The law brain is the curated commentary layer; ZwiadBrain is the authoritative primary-source tracker.** ZwiadBrain reads the law brain read-only on its cron and copies relevant content into itself.

The `.gitignore` already encodes the core design decision: `data/raw/`, `data/cache/`, `*.sqlite`, `*.db` are ignored. **Raw scrapes + working index stay local; the generated markdown wiki is the committed product.** Bill evolution (amendments, status flips) is naturally captured as git diffs over time.

> **This plan was revised on 2026-05-26 after a structured review against a sibling tech-knowledge-base.** The revisions tighten three things the first draft under-specified — retrieval evidence base, LLM-output grounding, and the scope/sequencing of the law-brain subsystem — and defer one feature (entity propagation). Every change carries its reasoning in **"Revisions from tech-brain review"** at the end of this document. Citations of the form *(tech-brain: page-slug)* point at pages in the sibling `Brains\tech` wiki and are the evidence base for the design choices.

### Design lineage & evidence base (added this revision)

ZwiadBrain is a concrete instance of the **Karpathy LLM-Wiki pattern** — a git-backed corpus of typed markdown pages, edited by an LLM, retrieved by lexical search, **with no LLM in the retrieval loop**. Its page schema maps beat-for-beat onto the "compiled truth + append-only timeline + raw sidecars" structure that the same lineage uses elsewhere *(tech-brain: concept-meta-meta-prompting, tool-gbrain)*:

| ZwiadBrain | Karpathy-lineage role |
|---|---|
| committed wiki frontmatter + body | **compiled truth** (current best understanding, rewritable) |
| git history of `wiki/**` (bill amendments, status flips) | **append-only timeline** (audit-friendly, diff-readable) |
| `data/raw/` + `data/cache/` (gitignored) | **raw sidecars** (source material, not the product) |
| SQLite index, rebuilt by `reindex` from frontmatter | derived lexical resolver — *no embeddings* |

This is not a stylistic note: it justifies the retrieval architecture below and is the reason the SQLite/FTS5-only design is a defensible default rather than unfinished debt.

### User decisions locked this session
- **Law-brain access:** strictly **read-only**. ZwiadBrain never edits the law brain. It reads and copies relevant content into its own pages.
- **Law-brain role:** **discovery + commentary.** Each run, ZwiadBrain reads the law brain to (a) discover bills/enforcement actions it isn't yet tracking, and (b) attach commentary to pages it already tracks. Official sources (Congress.gov/GovInfo/LegiScan/FTC/state AG) remain authoritative for bill text, amendments, and legislative history.
- **Copy style:** **verbatim full-page copy** of the matched law-brain page into a `## Commentary & Analysis` section, with an attribution line (source slug + law-brain `updated` date) and re-copy on change.
- **Matching:** **hybrid** — deterministic identifier extraction first, Claude fallback for unmatched pages (link / new item / not-in-scope), low-confidence proposals held in a human review queue. **LLM match decisions are gated by a deterministic shared-key confirmation before auto-apply** (see revised matcher below).

### Prior decisions carried forward (from the pasted remote plan)
- **LLM:** Claude via Anthropic Python SDK, prompt caching on the reference/taxonomy prefix.
- **Automation:** local/server **cron** (crontab/Task Scheduler); keys in gitignored `.env`. No GitHub Actions.
- **v1 coverage:** Federal (Congress.gov + GovInfo) + priority states **CA, NY, TX, CO, VA, WA, IL** (LegiScan). Enforcement: **FTC** + state AGs for those states.

### Honest caveat (now load-bearing for phase sequencing)
Law-brain discovery is partly **redundant** — the law brain is downstream of the Zwiad memo stream, and the official Congress/LegiScan scrapers should independently catch most active bills. Treat law-brain discovery as a **secondary safety net** for items the keyword seeds miss, not the primary discovery path. **This caveat is now the basis for splitting the law-brain work into a commentary-first phase and a separately-gated discovery phase** (see Phases) — we do not build the most intricate subsystem in the project on spec for a path we expect to be mostly redundant.

---

## Architecture at a glance

```
SOURCES (official, authoritative)         LAW BRAIN (read-only, commentary)
  Congress.gov v3  -> federal bills          C:\…\Brains\law\wiki\*.md
  GovInfo          -> reports/CREC/PLAW       (regulation/case/guidance/…)
  LegiScan         -> state bills (7 states)
  FTC + state AGs  -> enforcement actions
        |                                            |
        v                                            v
  CRON (Mon/Wed/Fri) -> run.py two-pass + law-brain stage
        |
  Pass A (refresh):  re-check every tracked item via change cursor
                     (LegiScan change_hash / Congress updateDate)
                     + refresh_commentary() per item (re-copy if law-brain page changed)
  Law-brain stage:   read changed law-brain pages -> hybrid match
                     -> deterministic shared-key CONFIRM -> link commentary
                     -> (discovery phase only) mint new tracked stub / queue for review
  Pass B (discovery):keyword-seed + since-window queries on official APIs
        |
  classify (Claude, disqualify-rubric) -> enrich (official) -> render markdown+frontmatter
        |
  wiki/ (COMMITTED)  --reindex-->  SQLite index/watchlist (derived, gitignored, FTS5)
        |
  git add wiki/ review-queue.md links.yaml -> commit -> push (retry w/ backoff)
```

**Source of truth = committed wiki frontmatter.** SQLite is a derived cache; `reindex` rebuilds it from `wiki/**/*.md`. The index doubles as the watchlist. Copied commentary + link decisions also live in committed files (`commentary_sources` frontmatter, `links.yaml`), so a fresh clone is self-contained. **No embeddings, no vector DB** — retrieval is lexical (SQLite FTS5 over derived columns); see "Retrieval architecture" for the evidence.

---

## Repository layout

```
pyproject.toml                 # src/ layout, pinned deps, console entrypoint, pytest/ruff/pyright config
zwiadbrain.toml                # enabled sources, state list, model names, topic taxonomy, keyword seeds, [lawbrain] block
.env.example                   # CONGRESS_API_KEY, LEGISCAN_API_KEY, ANTHROPIC_API_KEY, LAW_BRAIN_PATH
DECISIONS.md                   # seeded at project start (see Locked Decisions below)
.claude/phases/                # phase files, one active at a time (user-mandated)
src/zwiadbrain/
  __main__.py  cli.py          # typer CLI: scan, backfill, render, reindex, sync-lawbrain, review, lawbrain-status
  config.py                    # pydantic-settings: toml + .env; LawBrainSettings nested model
  exceptions.py                # AppError base + typed subclasses (per python rules)
  models.py                    # Bill, Action, Amendment, TextVersion, LegHistory, EnforcementAction, WikiItem, CommentarySource
  store.py                     # SQLite index (FTS5) + reindex-from-frontmatter; watchlist; lawbrain_pages cache table
  reference/loader.py          # topic taxonomy/keyword seeds -> cacheable LLM context blocks
  llm/
    client.py                  # Anthropic wrapper + prompt-cache helper (cache_control prefix)
    classify.py summarize.py amendments.py leg_history.py enforcement.py
  sources/
    base.py                    # Source protocol: discover(since)->candidates; fetch(id)->detail
    congress.py govinfo.py legiscan.py
    lawbrain.py                # READ-ONLY LawBrainReader (NOT a Source); enumerate/parse/hash/diff
    enforcement/base.py enforcement/ftc.py enforcement/state_ag.py
  pipeline/
    discover.py classify.py enrich.py render.py
    lawbrain_keys.py           # deterministic key extraction (pure, heavily tested)
    lawbrain_match.py          # matcher + deterministic shared-key CONFIRM (grounding verifier)
    lawbrain_copy.py           # verbatim copier + staleness (commentary-first phase)
    lawbrain_discover.py       # stub-minting from law-brain (GATED discovery phase, PHASE-11)
    lawbrain_registry.py       # links.yaml load/query (permanent decisions)
    run.py                     # Pass A + law-brain stage + Pass B orchestration
  wiki/
    schema.py                  # frontmatter pydantic models + validation (incl. commentary_sources)
    templates.py               # jinja2 bill + enforcement page builders (incl. ## Commentary & Analysis)
scripts/
  scan.sh                      # cron entrypoint: scan -> git add -> commit -> push (4x backoff retry)
  install-cron.md
reference/
  topics.yaml                  # AI/privacy/cyber taxonomy + keyword seed lexicon + DISQUALIFY lexicon
wiki/                          # THE committed output
  README.md  federal/{bills,enforcement}/  states/{ca,ny,tx,co,va,wa,il}/{bills,enforcement}/
  review-queue.md              # pending low-confidence link proposals (committed, transient)
  links.yaml                   # permanent accepted/rejected law-brain link decisions
tests/
  fixtures/                    # Congress/LegiScan/FTC JSON+RSS; tests/fixtures/lawbrain/ mini-wiki
  test_models.py test_schema.py test_render.py test_classify.py
  test_lawbrain_keys.py test_lawbrain_reader.py test_lawbrain_match.py
  test_match_grounding.py test_commentary_copy.py test_commentary_staleness.py
  test_review_queue.py test_lawbrain_discovery.py
```

(`lawbrain_sync.py` from the first draft is split into `lawbrain_match.py` / `lawbrain_copy.py` / `lawbrain_discover.py` so the commentary-first and discovery-gated phases have clean module boundaries — see Phases.)

---

## Data sources (concrete)

- **Federal bills — Congress.gov v3** (`api.congress.gov`, free api.data.gov key, 5k req/hr). Discover via `/bill?fromDateTime&toDateTime&sort=updateDate+desc` + keyword text search. Enrich via `/bill/{congress}/{type}/{num}` + `actions, amendments, text, summaries, committees, relatedbills, subjects, cosponsors`. Enacted via `/law/{congress}/pub/{n}`.
- **Legislative history — GovInfo** (`api.govinfo.gov`, same key): committee reports (CRPT), Congressional Record (CREC), public law / Statutes at Large (PLAW).
- **State bills — LegiScan** (`api.legiscan.com`, free account key). `getMasterListRaw` → cheap `change_hash` per bill for a whole state session in one call (ideal incremental detection); only spend `getBill` when hash changes. `getSearchRaw` for keyword discovery. (OpenStates v3 is a documented drop-in behind `sources/base.py`.)
- **Enforcement — FTC** (RSS + Cases & Proceedings) and **state AGs** (CA incl. CPPA, NY, TX, CO, VA, WA, IL). Each AG is a config entry in `zwiadbrain.toml` (`name, jurisdiction, url, kind=rss|html, item_selector`). `feedparser` for RSS, `beautifulsoup4` for HTML lists; article text handed to Claude for relevance + structured extraction (robust to layout drift).

---

## Retrieval architecture (made explicit this revision)

**Decision: lexical-only (SQLite FTS5 / BM25 over derived columns), no embeddings, deterministic key-extraction as the primary matcher.** This is evidence-backed, not a shortcut:

- A controlled factorial study (Sen et al., PwC) found **inline grep beat inline vector on 10/10 (harness, model) pairs** on a long-memory benchmark; the mechanism is *verbatim-span recovery* — questions licensed by a small set of literal spans (exact dates, names, numbers) *(tech-brain: concept-agentic-search-grep-vs-vector)*.
- **Legislative/enforcement tracking is the purest verbatim-span domain there is:** bill numbers (`SB 362`, `H.R. 8818`), dockets (`2:25-cv-12295`), public-law numbers (`Pub. L. 119-12`), statute cites, dates. Lexical precision is brutal here; vector retrieval would only add topical false-friends.
- Our `lawbrain_keys.py` (regex over slug → title → citation) **is** the "generate a discriminative substring" move the study rewards. The deterministic-first matcher is therefore the empirically-correct default, with the LLM only as a fallback for pages that emit no key.
- Independent corroboration: a sibling open-source legal-AI system ships an **FTS5-only (BM25) knowledge base** and the same study reframes "no vector retrieval" as a defensible default rather than mere debt *(tech-brain: tool-lavern, project-lq-ai)*.

Revisit only if a future need is genuinely paraphrase-heavy (e.g., semantic search over commentary prose) — and even then, add hybrid retrieval, do not replace lexical.

---

## Relevance pipeline

1. **Keyword pre-filter (recall stage)** from `reference/topics.yaml` seed lexicon (AI: *artificial intelligence, automated decision, facial recognition, biometric, deepfake*; privacy: *personal data, data broker, breach, consumer privacy*; cyber: *ransomware, critical infrastructure, CISA, encryption*) — narrows the API query universe cheaply. Tuned for recall; over-inclusion is fine here because the next stage filters.
2. **Claude relevance classifier (precision stage)** (`llm/classify.py`): title + summary (+snippet) → `{in_scope, topics[], confidence, rationale}`. Taxonomy + reference sent as a `cache_control` prefix.
   - **The prompt carries an explicit *disqualifying* rubric, not just "is this in scope?"** A bare "check if it's relevant" classifier rubber-stamps everything — vague verifier criteria make the loop theater *(tech-brain: pattern-generator-verifier)*. The rubric enumerates concrete negative criteria (e.g., *appropriations riders with no AI/privacy/cyber operative text; ceremonial resolutions; bills mentioning a seed term only in findings/whereas clauses; tax/budget bills that merely reference "data"*) drawn from a `DISQUALIFY` block in `reference/topics.yaml`. The classifier must state which positive criterion an in-scope item satisfies, and (for borderline items) which disqualifier it survived.
   - Keyword filter = **recall**; classifier = **precision with stated negative criteria.** The two stages are explicitly different jobs.
3. Only in-scope items are enriched and rendered.

> **Cross-modal eval is deliberately NOT used here.** Role-decomposing the verifier across heterogeneous models *(tech-brain: concept-meta-meta-prompting)* costs N model calls per output and is overkill for routine classification. It is reserved, if adopted at all, for the one high-stakes output: **assembled legislative history on enactment** (PHASE-05), where a precision/recall/genericness split could be justified.

## Tracking & watchlist (two-pass scan)

A classified-relevant bill becomes **tracked**: committed wiki page + frontmatter cursor (`change_hash` for LegiScan, `updateDate`/`updateDateIncludingText` for Congress). Each cron run:
- **Pass A — watchlist refresh.** Load tracked items from index (rebuilt from frontmatter via `reindex`). States: one `getMasterListRaw` per tracked session → compare `change_hash`. Federal: compare stored `updateDate`. Only **changed** items re-enriched/re-rendered. Terminal items (enacted/dead/failed) stay in the wiki but drop out of polling (`tracking: false`). **Also calls `refresh_commentary(item)`** to re-copy law-brain commentary if its source page changed.
- **Pass B — discovery.** Keyword-seed + since-window queries surface new candidates → classify → add to watchlist.

---

## Standardized page schemas

**Bill page** frontmatter: `id, type=bill, jurisdiction (US | US-CA…), chamber, bill_number, congress/session, title, status, topics[], policy_area, sponsors[], introduced_date, latest_action_date, latest_action, enacted, public_law, sources{}, tracking(bool), change_hash, update_date, last_synced, commentary_sources[]`. Body: **Summary** (Claude) · **Status & Timeline** (deterministic) · **Amendments** (per-amendment + Claude "what changed") · **Legislative History** (assembled on enactment: versions, committee reports, floor consideration w/ CREC cites, votes, conference, enactment + public law no. + Statutes at Large) · **Full Text** · **Related Bills** · **Commentary & Analysis** (copied law-brain content) · **Sources**.

**Enforcement page** frontmatter: `id, type=enforcement, agency, respondent, jurisdiction, action_type, statutes[], topics[], date_filed, date_resolved, penalties, status, docket, sources{}, commentary_sources[]`. Body: Summary · Background · Allegations · Outcome · Significance · **Commentary & Analysis** · Sources.

> **Entity propagation is deliberately deferred to a later milestone (not v1).** The compounding mechanism in this lineage is bidirectional: ingesting an event walks the entities it mentions (sponsors, agencies, related bills) and updates *their* pages too — that is the difference between a journal and a graph that thickens over time *(tech-brain: concept-meta-meta-prompting, tool-gbrain)*. ZwiadBrain has the raw material (`sponsors[]`, `relatedbills`, `agency`) but **no propagation loop in v1.** This is a conscious scope cut, not an oversight: get the primary-source tracker correct first, add propagation once page volume makes the graph worth thickening. Logged as decision 15.

---

## Law-brain integration subsystem

> **Sequencing note (revised):** this subsystem is split into a **commentary-first** path (PHASE-09, low-risk, deterministic, high-value on pages we already track) and a **separately-gated discovery** path (PHASE-11, mints new tracked stubs from the law brain). The discovery path is the most intricate machinery in the whole project and serves a path the honest caveat says is *mostly redundant* with official Pass-B scraping. We do not build it on spec — PHASE-11 is gated behind observing, in production, how often Pass B actually misses something the law brain caught. Reasoning in revisions + decision 14.

### Reader — `sources/lawbrain.py` (read-only)
- `glob(LAW_BRAIN_PATH/wiki/*.md)`; skip `index.md`, `log.md`, `CLAUDE.md`, `DECISIONS.md`, `sources/`, `drafts/`. `is_available()` makes the whole stage a clean no-op if the path is missing.
- Parse with `python-frontmatter`; tolerate mixed flow/block YAML, unquoted/missing `citation`, scalar-vs-list `jurisdiction`, occasional duplicate `updated`.
- **Change detection = `content_hash` = sha256 of the whole file, EOL-normalized to `\n`** (authoritative; survives CRLF churn). `updated:` date is human-readable signal only (used in attribution, not trusted for diffing). Page bytes read fresh each run; prior hashes cached in SQLite `lawbrain_pages(slug PK, content_hash, updated, last_seen)`.

### Deterministic keys — `pipeline/lawbrain_keys.py` (pure)
Extract jurisdiction-qualified keys from **slug → title → citation**; map tracked items into the same key space; match = set intersection.
- **Bills:** regex on `AB|SB|HB|HR|H.R.|S|S.|LB|LD|HF|SF|AJR|SCR|ACR` + digits → `{PREFIX}-{int}` (+ zero-padded alias). **Jurisdiction-qualify mandatorily** (collisions are real: `SB 24` ×19, `HB 24` ×12 across states). Key = `US-CA::bill::SB-362`, `US-Federal::bill::HR-8818`. Session/congress is a refinement, not a hard key.
- **Dockets:** `No. \d{1,2}:\d{2}-[a-z]{2,3}-\d{3,6}` → `docket::2:25-cv-12295` (globally unique). Appellate `No. 26-1591` is a weak secondary.
- **Statutes / public law:** statute cites are tie-breakers only; `Pub. L. 119-12` → `public_law::119-12` (maps to our `public_law` field).
- **Fail closed:** scholarship/concept pages (e.g. `…103 Calif. L. Rev. 513 (2015)`, "Multi-state tracker…") must emit **zero keys** so they hit the cheap LLM "not-in-scope" path — never misread reporter/page numbers as bills.
- **Match outcomes:** exactly one intersection → `link` conf 1.0; >1 (collision, no session) → `review`; zero → LLM fallback.

### Matcher + grounding confirm — `pipeline/lawbrain_match.py`
The LLM fallback runs only for deterministically-unresolved pages. Reuses `llm/client.py` prompt-cache: static system prompt (task + closed JSON schema + valid jurisdictions/types) as a cached block; per-page user turn varies; `temperature=0`. Inputs: page `title/type/jurisdiction/tags/citation` + its `## Summary` + a deterministically-built shortlist (~15) of candidate tracked items sharing jurisdiction/tag (never the full corpus). Output: `{decision: link|new|not_in_scope, target_id, confidence, rationale}`.

**New this revision — a deterministic grounding verifier gates every auto-apply.** An LLM matcher can emit a confident `target_id` that is plausible but wrong, or doesn't actually share an identifier with the page. Borrowing the *mechanical grounding verifier* pattern (string-match the claim against the source before it persists) *(tech-brain: tool-lavern)* and the citation cascade's *"failed candidates do not persist; absence is the signal"* discipline *(tech-brain: project-lq-ai, pattern-generator-verifier)*:

1. LLM proposes `target_id` (must already be in the shortlist, else → review).
2. **`confirm_match(page, target_id)` runs deterministically:** recompute the page's extracted keys and the target item's keys; require **≥1 shared jurisdiction-qualified key** (bill number, docket, or public-law) OR an explicit operator override recorded in `links.yaml`. No shared key → the link is **not** auto-applied; it goes to the review queue with a `weak-grounding` note.
3. Only `confidence ≥ min_confidence` (default 0.75) **and** a passing deterministic confirm → auto-apply. Anything else, or `not_in_scope`, is recorded in the registry so it isn't re-classified.

LLM output only *gates* an action; the deterministic confirm *grounds* it; page bytes come from the deterministic renderer, so model nondeterminism can't dirty `git status`.

### Verbatim copy + staleness — `pipeline/lawbrain_copy.py` (PHASE-09)
Append `## Commentary & Analysis`, one marker-fenced block per source slug:
```
<!-- lawbrain:begin slug=regulation-california-delete-act -->
> Source: law brain page `regulation-california-delete-act` (updated 2026-05-06).
> Copied verbatim. Law brain authoritative for analysis; official sources authoritative
> for bill text and legislative history.

<verbatim body; copied ## headings demoted to ### for clean host TOC>
<!-- lawbrain:end slug=regulation-california-delete-act -->
```
Bookkeeping in frontmatter: `commentary_sources: [{path, slug, updated, content_hash, matched_by, confidence}]` (a `CommentarySource` model; round-trips through `reindex`). Staleness: recompute each source's `content_hash`; differ → re-copy that block only. Source page deleted → keep section, emit `stale` review note (never silently delete analysis). **Idempotency:** LF-normalized hashing + single jinja2 template + fixed markers/attribution + compare-then-write + stable slug-sorted `commentary_sources` ⇒ unchanged inputs → byte-identical pages → clean `git status`.

### Stub minting from the law brain — `pipeline/lawbrain_discover.py` (PHASE-11, GATED)
A `new` decision (page describes an item we don't yet track) mints a minimal `Bill`/`EnforcementAction` stub (`tracking=True` + extracted identifiers) and routes it through the **existing** `pipeline/enrich.py` against the authoritative `Source` — identical to a Pass-B candidate — then attaches commentary. **This is the redundant-with-Pass-B path; it ships only after PHASE-09/10 are in production and we have evidence the official scrapers miss law-brain-known items.** Tracker/landscape/concept pages never mint stubs (decision 7).

### Review queue + registry — `wiki/review-queue.md`, `wiki/links.yaml`
- `review-queue.md` (committed, transient): one entry per pending proposal (low confidence, collision, **or weak grounding**); user flips a status token `[pending]`→`[accept]`/`[reject]`.
- `links.yaml` (committed, permanent): `{lawbrain_slug, decision: link|not_in_scope|reject, target_id, matched_by, decided, status}`. Every run consults `LinkRegistry.decision_for(slug)` **before** classifying, so decided pages are never re-proposed.
  - **Optional polish (decision 16):** instead of binary accept/reject, the registry may carry a `tentative → confirmed` status that promotes after a match recurs across runs — borrowing the reinforce/decay "Precedent Board" idea *(tech-brain: tool-lavern)*. Not required for v1; the binary human-decided record already sidesteps the recency-bias trap that purely-LLM debate matchers fall into.
- `cli review --commit` performs accepted actions, writes `links.yaml`, prunes the queue.

### Pipeline wiring — `pipeline/run.py`
Distinct **law-brain stage** between Pass A and Pass B (own review gating + filesystem-diff semantics; keeps failure isolation/logging clean). In PHASE-09 the stage does match + confirm + commentary copy only. In PHASE-11 the same stage additionally routes `new` decisions through stub-minting. Pass B (keyword/official) stays unchanged.

### Config + CLI
`[lawbrain]` block: `enabled, path, min_confidence=0.75, require_shared_key=true, demote_headings=true, commentary=true, discover=false (PHASE-11 gate), type_map{regulation/statute→bill, case/guidance/incident/enforcement→enforcement}, commentary_only_types=[concept,framework,vendor,person,matter], commentary_only_slug_markers=[tracker,landscape,map,scholarship]`. New CLI: `sync-lawbrain [--dry-run] [--no-apply]`, `review [--list] [--commit]`, `lawbrain-status`. `discover` defaults **off** until PHASE-11 is approved. `scripts/scan.sh` runs normal `run` (law-brain stage included).

---

## Locked decisions (seed `DECISIONS.md` at project start)

1. **Markdown wiki committed; raw/index local** — already in `.gitignore`. Revisit if multi-machine sync needs the DB shared.
2. **Law brain strictly read-only; copy verbatim into ZwiadBrain.** (User decision.)
3. **Law brain = discovery + commentary; official sources authoritative.** (User decision.) Revisit if law-brain discovery proves purely redundant — **and note decision 14 already acts on this risk by gating the discovery path.**
4. **Hybrid matching (deterministic keys → LLM fallback → review queue).** (User decision.)
5. **content_hash (not `updated` date) is the change cursor for commentary.** Dates are hand-maintained/unreliable.
6. **Copied `##` headings demoted to `###`.** Clean host TOC; markers preserve provenance. (Default chosen; revisit if you want byte-pure copies.)
7. **Tracker/landscape/concept pages are commentary-only — never mint stubs.** Avoids stub floods. Trade-off: a bill mentioned *only* in a tracker won't be auto-discovered (official Pass B should still catch it).
8. **type_map:** law-brain `regulation/statute`→bill page; `case/guidance/incident/enforcement`→enforcement page; rest commentary-only.
9. **Decided pages trusted until their identifiers change** — no re-classification on every edit (saves tokens).
10. **A case page attaches to the enforcement page; the bill page cross-links to it.** Both pages carry their own matched commentary. Revisit if you want a challenging-case's commentary mirrored onto the bill page.
11. **lawbrain cache = SQLite table** in the existing derived index (one derived store).
12. **LLM = Claude/Anthropic SDK + prompt caching; cron = local; v1 states = CA/NY/TX/CO/VA/WA/IL.** (Carried forward.)
13. **Retrieval is lexical-only (SQLite FTS5/BM25), no embeddings; deterministic key-extraction is the primary matcher.** *Why:* a controlled study found inline grep ≥ inline vector on 10/10 (harness, model) pairs, and legislative/enforcement tracking is a pure verbatim-span domain (bill numbers, dockets, public-law numbers); a sibling legal-AI system runs FTS5-only and the same evidence reframes that as defensible, not debt *(tech-brain: concept-agentic-search-grep-vs-vector, tool-lavern, project-lq-ai)*. *Revisit if:* a genuinely paraphrase-heavy need appears — and then add hybrid, don't replace lexical.
14. **Law-brain integration is phased: commentary-first (PHASE-09), discovery/stub-minting gated (PHASE-11).** *Why:* the discovery path is the most intricate subsystem in the project and serves a path the honest caveat calls *mostly redundant* with official Pass-B scraping. Building it on spec is premature complexity — the canonical "I started with ~10 agents and kept adding; it's probably too many" failure mode *(tech-brain: tool-lavern)*. *Revisit if:* in production, Pass B is observed to miss law-brain-known items often enough to justify the machinery. (`discover=false` until then.)
15. **Entity propagation deferred past v1.** *Why:* it's the real compounding mechanism in this lineage *(tech-brain: concept-meta-meta-prompting, tool-gbrain)*, but correctness of the primary-source tracker comes first; propagation is worth its complexity only once page volume makes the entity graph worth thickening. *Revisit if:* sponsor/agency/related-bill pages become first-class and the user wants cross-page rollups.
16. **LLM match decisions require deterministic shared-key confirmation before auto-apply; failed grounding → review queue, never silent persist.** *Why:* a confident LLM `target_id` can be plausibly wrong; mechanical grounding (string-match against source) and "failed candidates don't persist, absence is the signal" are the proven guards *(tech-brain: tool-lavern, project-lq-ai)*. *Trade-off:* a correct match with no extractable shared key needs a one-time operator override in `links.yaml`.
17. **The relevance classifier carries an explicit disqualifying rubric (negative criteria), not a bare "in scope?" prompt.** *Why:* vague verifier criteria make the loop theater and rubber-stamp everything *(tech-brain: pattern-generator-verifier)*; keyword filter is recall, classifier is precision-with-stated-negatives. *Revisit if:* false-positive rate stays high — then escalate to cross-modal eval only on high-stakes outputs (leg-history), not routine classification.

---

## Phases (`.claude/phases/`, one active at a time — do not start the next without approval)

- **PHASE-01 — Skeleton.** `pyproject.toml` (httpx, pydantic, pydantic-settings, anthropic, python-frontmatter, PyYAML, feedparser, beautifulsoup4, tenacity, typer, jinja2, python-dotenv; dev: pytest, respx, ruff, pyright), `zwiadbrain.toml`, `.env.example`, `DECISIONS.md` (seed all 17 decisions), `exceptions.py`, `models.py`, dir tree, `wiki/README.md`. `mypy/pyright --strict` from day one.
- **PHASE-02 — Wiki layer.** `wiki/schema.py`, `wiki/templates.py` (incl. `## Commentary & Analysis`), `pipeline/render.py`, `store.py` + `reindex` (FTS5 derived columns). Fully testable offline.
- **PHASE-03 — Federal source.** `sources/congress.py` + `pipeline/discover.py` + `pipeline/enrich.py`.
- **PHASE-04 — LLM agents.** `llm/*` + `reference/loader.py`, wired into classify/summarize/amendments. **Classifier ships with the disqualify rubric + `DISQUALIFY` lexicon (decision 17).**
- **PHASE-05 — Legislative history.** `sources/govinfo.py` + `llm/leg_history.py` (standardized section on enactment). **Only candidate for cross-modal eval, if any.**
- **PHASE-06 — Watchlist.** `store.py` tracking fields + `pipeline/run.py` two-pass orchestration. Fixture-tested.
- **PHASE-07 — Priority states.** `sources/legiscan.py` with `change_hash` incremental sync (7 states).
- **PHASE-08 — Enforcement.** `sources/enforcement/ftc.py` + `state_ag.py` (config-driven) + `llm/enforcement.py`.
- **PHASE-09 — Law-brain COMMENTARY.** `sources/lawbrain.py`, `pipeline/lawbrain_keys.py`, `lawbrain_match.py` (incl. deterministic shared-key confirm, decision 16), `lawbrain_copy.py`, `lawbrain_registry.py`; `CommentarySource` model; `[lawbrain]` config with `discover=false`; `sync-lawbrain`/`review`/`lawbrain-status` CLI; review queue. Wire the match+copy law-brain stage into `run.py`. **Attaches commentary to pages we already track — deterministic, low-risk, high-value. Does NOT mint stubs.**
- **PHASE-10 — Cron.** `scripts/scan.sh` + `scripts/install-cron.md`; end-to-end dry run. (Brought forward of discovery — a self-contained, committed tracker with commentary is already shippable.)
- **PHASE-11 — Law-brain DISCOVERY (GATED).** `pipeline/lawbrain_discover.py`: `new`-decision stub-minting routed through `enrich.py`; flip `discover=true`. **Do not start until PHASE-09/10 have run in production and there is evidence Pass B misses law-brain-known items (decision 14).** May prove unnecessary.

Estimate: roughly one focused session per phase (PHASE-09 likely 1–2; the scraping phases depend on live-API iteration). This is a multi-session build — phases 1–2, 6, 9 are testable fully offline with fixtures. **PHASE-11 may never be needed; that is the point of gating it.**

---

## Verification

- **Offline unit tests (`pytest`, no network):**
  - Render a fixture bill → frontmatter validates + required sections present; `reindex` reconstructs SQLite (FTS5) from `wiki/**`; classifier parsing with mocked Anthropic (`respx`).
  - **Classifier rubric:** an appropriations rider / ceremonial resolution / seed-term-only-in-whereas fixture → `in_scope=false` with the surviving-disqualifier rationale; a genuine AI-transparency bill → `in_scope=true` citing the satisfied positive criterion.
  - **Law-brain keys:** `SB 362 (2023)`→`US-CA::bill::SB-362`(+session); `H.R. 8818`→`US-Federal::bill::HR-8818`; `SB 0508`→`SB-508`+padded; `No. 2:25-cv-12295`→`docket::…`; `Pub. L. 119-12`→`public_law::119-12`; scholarship cite + "Multi-state tracker…"→**zero keys**; `SB-24` collision→`review`.
  - **Match grounding (decision 16):** LLM `{link,0.9}` with a shared key→apply; `{link,0.9}` with **no** shared key→**review queue, no write** (`weak-grounding`); target-not-in-shortlist→queue; `{0.6}`→queue; malformed JSON→handled→queue; asserts cache-control + `temperature=0`.
  - **Copy idempotency:** first apply adds section/markers/attribution/demoted headings/`commentary_sources`; **re-run identical inputs → byte-identical file, zero writes**; multi-source → stable-sorted blocks.
  - **Staleness:** bump body→only that block re-copied; bump *only* `updated`→**no re-copy** (proves hash authoritative); page deleted→section kept + `stale` note.
  - **Review queue:** low-confidence/weak-grounding→`[pending]`, no `links.yaml`; `[accept]`+`review --commit`→link performed, `links.yaml` updated, entry pruned; `[reject]`→skipped next run.
  - **Discovery (PHASE-11):** `new` regulation w/ untracked bill→stub minted→enrich path (mocked Source)→page+commentary; tracker-slug page→**not** minted (commentary-only). *(Test ships with PHASE-11, not PHASE-09.)*
- **Federal end-to-end** (needs `CONGRESS_API_KEY`): `python -m zwiadbrain backfill --congress 118 --limit 5` → inspect 5 pages under `wiki/federal/bills/`; confirm timeline + amendments + (enacted) legislative history.
- **State:** `python -m zwiadbrain scan --states ca --limit 5` → `wiki/states/ca/bills/`.
- **Watchlist re-check:** scan twice → Pass A re-checks via stored cursor, re-renders only changed items, leaves the rest byte-identical (clean `git status`).
- **Law-brain commentary (offline-capable, PHASE-09):** `python -m zwiadbrain sync-lawbrain --dry-run` against the real `LAW_BRAIN_PATH` → prints `MatchResult`s + grounding-confirm outcomes + intended writes, no edits. Then `sync-lawbrain` → confirm `## Commentary & Analysis` blocks appear on matched-and-grounded pages, weak-grounding/low-confidence items land in `review-queue.md`, decisions recorded in `links.yaml`. Re-run → byte-identical (clean `git status`). Confirm `Brains\law` is **untouched** (`git -C …\Brains\law status` clean, mtimes unchanged).
- **Enforcement:** `python -m zwiadbrain scan --enforcement ftc,state_ag --states ca,ny --limit 5`.
- **LLM-off sanity:** rerun with `--no-llm` to verify the deterministic pipeline independent of API cost/availability.
- **Cron dry run:** execute `scripts/scan.sh` once manually; confirm the commit touches only `wiki/`, `review-queue.md`, `links.yaml` and pushes cleanly.

> Network note: scan needs egress to api.congress.gov, api.govinfo.gov, api.legiscan.com, ftc.gov, state AG sites, and api.anthropic.com — fine on the user's machine where cron runs. In a sandboxed session, live calls may be blocked; all unit tests run fully offline with fixtures + mocked HTTP.

---

## Open items the user may want to revisit later (defaulted for now)
- Heading demotion (decision 6), tracker/landscape minting (7), case→bill commentary mirroring (10) — all defaulted; flag if you'd prefer otherwise.
- **Entity propagation (decision 15)** — deferred; the first real compounding feature when the brain outgrows a flat tracker.
- **Precedent-Board-style tentative→confirmed link promotion (decision 16 polish)** — optional registry upgrade.
- **Cross-modal eval on leg-history (decision 17)** — only if classification/assembly precision proves insufficient.
- SEC / HHS OCR and additional states slot in later as config/sources behind `sources/base.py`.

---

## Revisions from tech-brain review (2026-05-26)

This plan was reviewed against the sibling `Brains\tech` knowledge base. The original draft was strong and largely survives; the changes below are the deltas, each with its reasoning and source. Citations point at pages in `Brains\tech\wiki\`.

1. **Made the lexical-only retrieval choice explicit and evidence-backed (new "Retrieval architecture" section + decision 13).**
   *Original:* SQLite index was specified but never justified; "why no embeddings?" was unanswered and would resurface.
   *Change/why:* A controlled factorial study found inline grep beat inline vector on 10/10 (harness, model) pairs, with the gain mechanism being verbatim-span recovery — exactly this domain's identifiers (bill numbers, dockets, public-law numbers). The deterministic key-extraction *is* that winning move. A sibling legal-AI system runs FTS5-only and the same study reframes that as defensible. *(concept-agentic-search-grep-vs-vector, tool-lavern, project-lq-ai)*

2. **Added a deterministic shared-key grounding verifier on the LLM matcher (revised `lawbrain_match.py` + decision 16).**
   *Original:* LLM match auto-applied on `confidence ≥ 0.75` + target-in-shortlist. A confident-but-wrong `target_id` could link two unrelated items.
   *Change/why:* Require ≥1 shared jurisdiction-qualified key (or recorded operator override) before auto-apply; otherwise → review queue with `weak-grounding`. This is the mechanical-grounding-verifier pattern (string-match the claim against the source) plus the "failed candidates don't persist, absence is the signal" discipline. *(tool-lavern, project-lq-ai, pattern-generator-verifier)*

3. **Gave the relevance classifier an explicit disqualifying rubric (revised Relevance pipeline + decision 17).**
   *Original:* `{in_scope, topics[], confidence}` from title+summary — a bare "is it relevant?" verifier.
   *Change/why:* Vague verifier criteria rubber-stamp everything and make the loop theater. The classifier now enumerates concrete negative criteria (appropriations riders, ceremonial resolutions, seed-term-only-in-whereas, etc.) from a `DISQUALIFY` lexicon, and states which positive criterion an in-scope item meets. Keyword filter = recall, classifier = precision-with-negatives. *(pattern-generator-verifier)*

4. **Split the law-brain subsystem into commentary-first (PHASE-09) and gated discovery (PHASE-11); brought Cron forward to PHASE-10 (decision 14).**
   *Original:* One monolithic PHASE-09 built reader + keys + matcher + verbatim copy + staleness + stub-minting + review + registry all at once — for a discovery path the plan itself calls "mostly redundant" with official scraping.
   *Change/why:* This is the canonical "started with ~10 agents, kept adding, it's probably too many" over-build. Ship the deterministic, high-value commentary path first; make a self-contained committed tracker shippable via cron; gate the intricate stub-minting machinery behind production evidence that Pass B actually misses law-brain-known items. `discover=false` until then; PHASE-11 may prove unnecessary. *(tool-lavern)*

5. **Named the Karpathy LLM-wiki lineage and mapped the page schema to compiled-truth + timeline + sidecars (new "Design lineage" section).**
   *Original:* The git-diff-as-history insight was present but unframed.
   *Change/why:* Naming the pattern (committed wiki = compiled truth, git history = append-only timeline, `data/raw/` = sidecars, reindex = no-LLM-in-retrieval-loop) anchors the retrieval and schema decisions in a known-good architecture. *(concept-meta-meta-prompting, tool-gbrain)*

6. **Deferred entity propagation explicitly (decision 15) instead of leaving it implicit.**
   *Original:* `sponsors[]`/`relatedbills`/`agency` captured, but no statement about cross-page rollups.
   *Change/why:* Entity propagation is *the* compounding mechanism in this lineage (event ingestion walks mentioned entities and updates their pages). It's worth it later, not in v1 — get the primary-source tracker correct first. Logged as a conscious scope cut so it isn't mistaken for an oversight. *(concept-meta-meta-prompting, tool-gbrain)*

7. **Scoped cross-modal eval out of routine classification, reserved it for leg-history only (note in Relevance pipeline + decision 17).**
   *Original:* No mention; risk of over-applying multi-model verification.
   *Change/why:* Role-decomposed multi-model verification costs N calls per output and is overkill for routine in/out-of-scope calls. Reserve it, if used at all, for the single high-stakes artifact (assembled legislative history). *(concept-meta-meta-prompting, pattern-generator-verifier)*

8. **Optional Precedent-Board-style link promotion noted (decision 16 polish).**
   *Why:* The binary human-decided `links.yaml` already sidesteps the recency-bias trap that purely-LLM debate matchers fall into; a tentative→confirmed-after-recurrence upgrade is available if useful but not required. *(tool-lavern)*

> Net effect: the same end-state, reached more safely and in a more shippable order. The biggest single change is #4 — it converts the riskiest, most speculative phase from "build it all up front" into "ship the certain value, gate the speculative machinery behind evidence."
