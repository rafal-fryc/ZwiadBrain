# Decisions

Append-only. Do not edit past entries — add a new entry if something changes.

Decisions 1–17 are the locked decisions from the implementation plan (`docs/PLAN.md`),
seeded at project start. Decisions 18–19 are project-start decisions required by the
standing engineering rules (language/tooling, merge strategy).

---

## 2026-05-26 — 1. Markdown wiki committed; raw data + index local
**Chosen:** The generated Markdown wiki (`wiki/**`) is the committed product; raw scrapes (`data/raw/`), caches (`data/cache/`), and the SQLite index (`*.sqlite`) are gitignored and derived.
**Alternatives:** Commit the database; commit raw scrapes alongside output.
**Why:** Frontmatter is human-readable, diff-friendly, and rebuildable; bill evolution becomes git history for free. Already encoded in `.gitignore`.
**Trade-offs:** The index must be rebuildable from frontmatter (`reindex`) on a fresh clone.
**Revisit if:** Multi-machine sync needs a shared DB.

## 2026-05-26 — 2. Law brain is strictly read-only; copy verbatim
**Chosen:** ZwiadBrain reads the law brain and copies relevant pages verbatim into its own pages; it never edits the law brain. (User decision.)
**Alternatives:** Write back-references into the law brain; bidirectional sync.
**Why:** The law brain is a separately, carefully hand-maintained asset; one-way copy removes all risk of disrupting it.
**Trade-offs:** Copied content can go stale → handled by content-hash re-copy (decision 5).
**Revisit if:** The user later wants ZwiadBrain to enrich the law brain.

## 2026-05-26 — 3. Law brain = discovery + commentary; official sources authoritative
**Chosen:** The law brain serves both as a discovery hint and a commentary overlay; official sources (Congress.gov/GovInfo/LegiScan/FTC/AG) remain authoritative for bill text, amendments, and legislative history. (User decision.)
**Alternatives:** Commentary-overlay only; law-brain-as-primary-spine.
**Why:** Captures items keyword discovery misses while keeping primary-source authority where it belongs.
**Trade-offs:** Discovery is partly redundant with official scraping → addressed by gating it (decision 14).
**Revisit if:** Law-brain discovery proves purely redundant.

## 2026-05-26 — 4. Hybrid matching: deterministic keys → LLM fallback → review queue
**Chosen:** Deterministic identifier extraction first; Claude fallback only for unmatched pages; low-confidence proposals to a human review queue. (User decision.)
**Alternatives:** Deterministic-only; LLM-decides-every-match.
**Why:** Transparent and accurate where identifiers exist (the common case); LLM only where keys are absent.
**Trade-offs:** Two code paths to maintain.
**Revisit if:** Deterministic matching covers effectively everything (drop the LLM path) or misses too much.

## 2026-05-26 — 5. content_hash is the change cursor for commentary
**Chosen:** sha256 of the whole law-brain file (EOL-normalized to `\n`) decides staleness; the `updated:` date is display-only.
**Alternatives:** Trust the `updated` frontmatter date.
**Why:** The date is hand-maintained and sometimes wrong/duplicated; the hash is authoritative and survives CRLF churn.
**Trade-offs:** A frontmatter-only edit triggers a re-copy (acceptable — the copy includes frontmatter).
**Revisit if:** Hashing the full corpus each run becomes a measured bottleneck.

## 2026-05-26 — 6. Copied headings demoted `##` → `###`
**Chosen:** Copied law-brain `##` headings are demoted to `###`; marker comments preserve provenance.
**Alternatives:** Byte-pure verbatim copy.
**Why:** Keeps the host page's table of contents clean.
**Trade-offs:** Not a literal byte copy (markers + heading shift).
**Revisit if:** The user wants byte-pure copies.

## 2026-05-26 — 7. Tracker/landscape/concept pages are commentary-only — never mint stubs
**Chosen:** Pages whose type or slug marks them as trackers/landscapes/scholarship link to existing items but never create new tracked items.
**Alternatives:** Mint stubs from trackers too.
**Why:** A single tracker page lists dozens of bills; minting from it would flood the wiki with stubs.
**Trade-offs:** A bill mentioned *only* in a tracker won't be auto-discovered (official Pass B should still catch it).
**Revisit if:** Trackers turn out to be the only signal for important bills.

## 2026-05-26 — 8. type_map: which law-brain types map to which page kind
**Chosen:** law-brain `regulation`/`statute` → bill page; `case`/`guidance`/`incident`/`enforcement` → enforcement page; rest commentary-only.
**Alternatives:** One-to-one type mapping; manual per-page.
**Why:** Matches the substantive nature of each law-brain page type to the right ZwiadBrain page kind.
**Trade-offs:** Edge cases (a regulation page that is really about an enforcement sweep) may need override.
**Revisit if:** Mismapping is observed frequently.

## 2026-05-26 — 9. Decided pages trusted until their identifiers change
**Chosen:** Once a law-brain page has a recorded decision in `links.yaml`, it is not re-classified each run unless its extracted identifiers change.
**Alternatives:** Re-classify every page every run.
**Why:** Saves tokens and avoids churn; decisions are sticky.
**Trade-offs:** A page whose *scope* changes without its identifiers changing won't be re-evaluated.
**Revisit if:** Scope drift without identifier change becomes common.

## 2026-05-26 — 10. Case pages attach to enforcement pages; bill pages cross-link
**Chosen:** A law-brain case page attaches its commentary to the enforcement page; the related bill page cross-links to it. Each page carries its own matched commentary.
**Alternatives:** Mirror a challenging-case's commentary onto the bill page too.
**Why:** Keeps each page's commentary on-topic and avoids duplication.
**Trade-offs:** A reader on the bill page must follow a cross-link to read the case commentary.
**Revisit if:** The user wants case commentary mirrored onto the bill page.

## 2026-05-26 — 11. Law-brain page cache lives in the SQLite index
**Chosen:** Prior content-hashes for change detection live in a `lawbrain_pages` table in the existing derived SQLite index.
**Alternatives:** A separate JSON cache in `data/cache/`.
**Why:** One derived store, rebuilt by `reindex`.
**Trade-offs:** None significant.
**Revisit if:** The index schema needs to stay minimal for another reason.

## 2026-05-26 — 12. Claude + prompt caching; local cron; v1 priority states
**Chosen:** LLM = Claude via the Anthropic SDK with prompt caching on the reference/taxonomy prefix; automation = local cron; v1 state coverage = CA, NY, TX, CO, VA, WA, IL. (Carried forward; user decision.)
**Alternatives:** GitHub Actions automation; broader/narrower state set; other LLM providers.
**Why:** Local cron needs no repo secrets and resolves `LAW_BRAIN_PATH` at runtime; the seven states are the highest-activity AI/privacy/cyber legislatures.
**Trade-offs:** Automation depends on the user's machine being on.
**Revisit if:** A hosted runner or more states are needed.

## 2026-05-26 — 13. Retrieval is lexical-only (SQLite FTS5/BM25); deterministic keys are the primary matcher
**Chosen:** No embeddings/vector DB; SQLite FTS5/BM25 over derived columns, with regex key-extraction as the primary matcher.
**Alternatives:** Vector/embedding retrieval; hybrid from day one.
**Why:** A controlled study found inline grep ≥ inline vector on 10/10 (harness, model) pairs, with the gain mechanism being verbatim-span recovery — exactly this domain's identifiers (bill numbers, dockets, public-law numbers). A sibling legal-AI system runs FTS5-only. *(tech-brain: concept-agentic-search-grep-vs-vector, tool-lavern, project-lq-ai)*
**Trade-offs:** Paraphrase-heavy semantic search isn't supported.
**Revisit if:** A genuinely paraphrase-heavy need appears — then *add* hybrid, don't replace lexical.

## 2026-05-26 — 14. Law-brain integration phased: commentary-first (PHASE-09), discovery gated (PHASE-11)
**Chosen:** Build the deterministic, high-value commentary path first; gate the stub-minting discovery path behind production evidence; `discover=false` until approved.
**Alternatives:** Build the whole law-brain subsystem at once.
**Why:** The discovery path is the most intricate subsystem in the project and serves a path the honest caveat calls *mostly redundant* with official Pass-B scraping — building it on spec is premature complexity. *(tech-brain: tool-lavern)*
**Trade-offs:** Discovery ships later (or never).
**Revisit if:** Production shows Pass B regularly misses law-brain-known items.

## 2026-05-26 — 15. Entity propagation deferred past v1
**Chosen:** No cross-page entity-propagation loop in v1, though `sponsors[]`/`related_bills`/`agency` are captured.
**Alternatives:** Build propagation now.
**Why:** Propagation is the real compounding mechanism in this lineage, but correctness of the primary-source tracker comes first; it's worth its complexity only once page volume makes the entity graph worth thickening. *(tech-brain: concept-meta-meta-prompting, tool-gbrain)*
**Trade-offs:** No automatic sponsor/agency rollup pages in v1.
**Revisit if:** Sponsor/agency/related-bill pages become first-class and the user wants rollups.

## 2026-05-26 — 16. LLM match auto-apply requires a deterministic shared-key confirm
**Chosen:** Before any LLM-proposed link auto-applies, `confirm_match` requires ≥1 shared jurisdiction-qualified key (bill number/docket/public-law) or a recorded operator override; otherwise it goes to the review queue with a `weak-grounding` note. Failed grounding never silently persists.
**Alternatives:** Auto-apply on confidence + shortlist membership alone.
**Why:** A confident LLM `target_id` can be plausibly wrong; mechanical grounding and "failed candidates don't persist, absence is the signal" are the proven guards. *(tech-brain: tool-lavern, project-lq-ai, pattern-generator-verifier)*
**Trade-offs:** A correct match with no extractable shared key needs a one-time operator override in `links.yaml`.
**Revisit if:** Override volume becomes burdensome.

## 2026-05-26 — 17. Relevance classifier carries an explicit disqualifying rubric
**Chosen:** The classifier prompt enumerates concrete negative criteria (appropriations riders, ceremonial resolutions, seed-term-only-in-whereas, etc.) from a `DISQUALIFY` lexicon, not a bare "is it relevant?"; keyword filter = recall, classifier = precision-with-stated-negatives.
**Alternatives:** Bare in/out-of-scope prompt.
**Why:** Vague verifier criteria rubber-stamp everything and make the loop theater. *(tech-brain: pattern-generator-verifier)*
**Trade-offs:** The rubric must be maintained as new false-positive patterns appear.
**Revisit if:** False-positive rate stays high — then escalate to cross-modal eval only on high-stakes outputs (leg-history), not routine classification.

## 2026-05-26 — 18. Python 3.12 + uv/hatchling, pydantic v2, typer, httpx, Anthropic SDK
**Chosen:** Python 3.12 with `src/` layout; `uv` + `hatchling` for env/deps/build; pydantic v2 + pydantic-settings for models/config; typer for the CLI; httpx for HTTP; the official `anthropic` SDK for Claude; `pyright --strict` + `ruff` + `pytest` from day one.
**Alternatives:** Poetry/pip-tools; dataclasses + manual validation; click/argparse; requests.
**Why:** uv is fast and reproducible; pydantic v2 gives validated, typed frontmatter (the source of truth) with discriminated unions; typer/httpx are well-typed and ergonomic; strict typing + lint from the start prevents retrofitting.
**Trade-offs:** uv is newer tooling; pydantic v2 has a learning curve vs plain dataclasses.
**Revisit if:** A dependency proves unmaintained or a packaging constraint forces a change.

## 2026-05-26 — 19. Merge strategy: squash-merge feature branches; main acceptable during MVP
**Chosen:** Feature branches squash-merge into `main` to keep history clean; during early single-developer MVP work, committing directly to `main` is acceptable, with phase boundaries tagged as minor version bumps (`v0.1.0` = PHASE-01).
**Alternatives:** Merge commits preserving branch history; rebase for linear history.
**Why:** Squash keeps `main` readable; phase-boundary tags map the phase system onto version history for easy rollback.
**Trade-offs:** Interim branch commits are lost on squash.
**Revisit if:** The project gains other contributors or production deployments (then: branch + PR for every change).
