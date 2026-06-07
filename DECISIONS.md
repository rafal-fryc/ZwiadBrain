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

## 2026-05-26 — 20. Frontmatter holds metadata only; the page body holds rendered content
**Chosen:** A committed page's YAML frontmatter carries only metadata/watchlist fields (the source of truth that `reindex` reads); rendered content — summary prose, status timeline, amendments, legislative history, full-text links, and the verbatim copied commentary — lives in the Markdown body, regenerated from the model each run. Each commentary source's verbatim `body` is excluded from frontmatter even though its bookkeeping (`commentary_sources`) is recorded there.
**Alternatives:** Serialize the full model (timelines + commentary text) into frontmatter; or parse the rendered body back into the model.
**Why:** Keeps frontmatter small, diff-readable, and a clean watchlist index; large structured data is re-fetched from authoritative sources each run, so it need not round-trip through the page. A single deterministic renderer driven by the model guarantees byte-identical output for unchanged input (clean `git status`).
**Trade-offs:** A page body cannot be parsed back into a full model — only its metadata. Intentional: models are rebuilt from sources, not from rendered prose.
**Revisit if:** A use case needs full model reconstruction from a page alone (offline, no source access).

## 2026-05-27 — 21. Federal bill id = `{congress}-{type}-{number}`
**Chosen:** A federal bill's page id (and filename slug) is `{congress}-{type}-{number}` lowercased, e.g. `118-hr-8818`.
**Alternatives:** `{type}-{number}` (e.g. `hr-8818`); include a leading `us-` like state ids.
**Why:** Bill numbers recur every congress (118th HR 1 ≠ 117th HR 1), so the congress must be in the id for uniqueness; jurisdiction is already encoded by the `federal/bills/` path, so a `us-` prefix is redundant. Congress-first sorts pages by congress.
**Trade-offs:** Slightly longer slug; differs from the bare `hr-1` used in early Phase-01/02 test fixtures (those are synthetic).
**Revisit if:** A cross-congress canonical bill identity is needed (then add an alias).

## 2026-05-27 — 22. `Source.fetch` returns a mapped `Bill`; enrich is the source-agnostic seam
**Chosen:** Each source maps its own API onto the common `Bill` inside `fetch(native_id) -> Bill`; `pipeline/enrich.py` is source-agnostic and owns cross-source post-processing (currently stamping `last_synced`; the classify gate and change-hash policy attach here later). `pipeline/discover.py` holds the keyword recall filter + since-window helper.
**Alternatives:** `fetch` returns raw source JSON and `enrich.py` does all per-source mapping (one growing dispatcher); or fold discover/enrich into the source.
**Why:** Keeping per-source mapping in the source preserves clean layering (pipeline depends on sources, never the reverse) and a single typed contract (`Bill`), so the pipeline never branches on source-specific JSON. The plan's module names are honored: the source is the transport+mapping client, the pipeline owns orchestration.
**Trade-offs:** `enrich.py` is thin in Phase 03 (just `last_synced`); the per-field mapping lives per-source rather than in one place.
**Revisit if:** Several sources end up sharing substantial mapping logic that wants a common home.

## 2026-05-27 — 23. Phase-03 Summary = official CRS summary (provisional)
**Chosen:** `Bill.summary` is populated from the latest official Congress (CRS) summary, HTML-stripped, in Phase 03. The Claude plain-language summarizer overwrites it in a later phase. (User decision.)
**Alternatives:** Leave `summary` empty until the Claude summarizer phase (no Summary section yet).
**Why:** It is real authoritative data, makes rendered pages immediately useful, and uses the `/summaries` endpoint the enrich step already fetches — without fabricating an LLM summary.
**Trade-offs:** The Summary section temporarily carries official prose rather than the intended plain-language rewrite; the field is overwritten later (same field, no migration).
**Revisit if:** Official summaries prove misleading on the page before the summarizer lands.

## 2026-05-27 — 24. `subjects` and `cosponsors` deferred from Phase-03 enrichment
**Chosen:** Phase 03 maps `policy_area` (from bill detail), primary `sponsors[]`, and `related_bills`; it does not fetch/map `subjects` or `cosponsors`. (User decision.)
**Alternatives:** Add `subjects[]`/`cosponsors[]` model fields and map both endpoints now.
**Why:** `topics` are produced by the Claude classifier with a disqualifying rubric (decision 17), not raw legislative subjects; cosponsors have no model field and would bloat `sponsors[]`/frontmatter. Neither has a consumer yet, and each is an extra API call per bill.
**Trade-offs:** Cosponsor counts and CRS legislative subjects are not surfaced in v1 federal pages.
**Revisit if:** A consumer appears (e.g. sponsor/entity rollups, or subject-seeded discovery).

## 2026-05-27 — 25. Settings loader merges .env + process env + TOML explicitly
**Chosen:** `config.load_settings` reads the TOML tables and the secret env vars itself (`.env` via `dotenv_values`, overlaid by the process environment) and `Settings.model_validate`s the merged dict. Precedence: process env > `.env` > TOML.
**Alternatives:** Rely on pydantic-settings' implicit source chain with `Settings(_env_file=...)`.
**Why:** Secrets (flat fields) and operational config (nested tables) never overlap, so an explicit merge is simple and gives deterministic precedence and trivial test injection of arbitrary file paths; the `_env_file` init kwarg is also not present on pydantic-settings' type-checker-synthesized `__init__`, so the explicit path stays type-clean under `pyright --strict`.
**Trade-offs:** Re-implements a small slice of pydantic-settings' env handling for the four known secrets rather than using its source pipeline.
**Revisit if:** Settings grow many env-sourced fields or need nested/prefixed env parsing — then adopt a custom `SettingsConfigDict` source chain.

## 2026-05-27 — 26. LLM runs via interactive Claude Code subagents on the regular plan, not the API/SDK
**Chosen:** The relevance classifier, summarizer, and amendment-explainer are Claude Code subagents (`.claude/agents/*.md`) dispatched from an interactive session via a `/zwiad-backfill` slash command. No Anthropic API key, no Agent SDK, no headless `claude -p`.
**Alternatives:** (a) Anthropic API key (metered); (b) Agent SDK with subscription auth; (c) headless `claude -p`.
**Why:** The user wants the work to run on their existing Claude plan. Per support.claude.com (eff. 2026-06-15), `claude -p` and the Agent SDK draw a separate, capped monthly *Agent SDK credit* and then bill API rates; the Agent SDK does not support claude.ai subscription auth at all (verified via docs + open issue #559). Only *interactive* Claude Code uses the regular plan limits. The sibling `Zwiad` project (github.com/rafal-fryc/Zwiad) already runs this way. User decision.
**Trade-offs:** Not headless/cron-able — a session must be open and triggered (the user accepts keeping a terminal open). The classification logic lives in subagent prompts, validated by interactive UAT rather than deterministic offline unit tests.
**Revisit if:** Unattended automation or throughput needs outgrow an open session — then reconsider `claude -p`-on-credit or the API.

## 2026-05-27 — 27. Pipeline pivots to Claude-Code-orchestrated; Python is deterministic tooling
**Chosen:** Claude Code orchestrates the LLM backfill (the slash command); Python provides deterministic, independently-testable commands — `fetch-candidates` (discover → keyword filter → enrich → `candidates.json`) and `render-classified` (validate `topics` → render → index) — exchanging gitignored JSON files under `data/runs/<id>/`. Mirrors Zwiad's file-based agent handoffs.
**Alternatives:** Keep the PLAN's Python-orchestrated pipeline calling an LLM client.
**Why:** Decision 26 means the orchestrator must be the interactive session, not Python. Splitting backfill at the LLM boundary keeps each half single-purpose and the Python half fully unit-testable.
**Trade-offs:** Departs from the PLAN's orchestration model — **PHASE-06** (`run.py` two-pass) becomes a slash command and **PHASE-10** (cron + `claude -p`) becomes in-session scheduling (`/loop` or scheduled task). To be re-planned in those phases.
**Revisit if:** A future headless path is adopted (see decision 26).

## 2026-05-27 — 28. Classify after fetch, on title + CRS summary; gate the expensive LLM steps
**Chosen:** Order is discover → keyword filter → `source.fetch` (cheap HTTP, yields the CRS-extract summary) → classify (title + CRS summary) → IN-SCOPE only: summarize + explain amendments → render. Only `topics[]` is persisted to a page; `confidence`/`rationale`/`criterion` stay in the session transcript.
**Alternatives:** Classify on the title-only candidate before fetch (PLAN diagram order); or enrich fully then classify.
**Why:** Congress candidates carry title only — the summary the DISQUALIFY rubric needs exists only after `fetch`. Classifying before the summarizer/amendment subagents avoids spending plan usage on off-topic bills. Keeping nondeterministic classifier outputs out of frontmatter preserves byte-identical re-renders / clean `git status`.
**Trade-offs:** A few cheap Congress HTTP fetches are spent on bills that get classified out (HTTP, not plan usage).
**Revisit if:** A source begins returning summaries at discovery time (then title+summary classification could precede fetch).

## 2026-05-27 — 29. `topics.yaml` is the single source for both recall seeds and the classifier rubric
**Chosen:** `reference/topics.yaml` holds the taxonomy, keyword seeds, positive criteria, and DISQUALIFY lexicon. `reference/loader.py` exposes `seeds` (flat, deduped → keyword filter) and `topic_keys` (valid `topics[]` values → render-time validation). The `classifier` subagent reads `topics.yaml` directly for the rubric. Subagents are restricted to `tools: Read`.
**Alternatives:** Duplicate the rubric into the classifier `.md`; or render the rubric in Python and pass it in the prompt.
**Why:** One file feeding both the recall and precision stages means they cannot drift. Restricting subagents to `Read` (rather than omitting `tools`, which inherits every tool including Write/Bash) is the safe minimal allowlist for single-shot text tasks.
**Trade-offs:** The classifier performs a file read each invocation (cheap, and keeps the orchestrator prompt small).
**Revisit if:** The rubric needs per-jurisdiction variants, or seed/criteria volume warrants splitting the file.

## 2026-05-27 — 30. Dropped the `anthropic` dependency
**Chosen:** Removed `anthropic` from `pyproject.toml`; Python makes no direct LLM calls.
**Alternatives:** Keep it for a future API fallback.
**Why:** Decisions 26–27 route all LLM work through Claude Code subagents, so the SDK is unused. Carrying an unused dependency invites drift and supply-chain surface.
**Trade-offs:** Re-adding it is one `uv add anthropic` away if an API fallback is ever chosen.
**Revisit if:** A headless/API path is adopted (decision 26).

## 2026-05-27 — 31. Federal discovery recall is a known gap; fix deferred to PHASE-03.1
**Chosen:** Acknowledge that `fetch-candidates`/`discover` has weak recall (newest-updated window + title-only filter miss topical bills, as the Phase-04 UAT showed by returning 0 candidates for `--congress 118 --limit 5`), and defer the fix to an inserted **PHASE-03.1** rather than fold it into the Phase-04 LLM-pipeline UAT.
**Alternatives:** Fix recall now as part of Phase-04; or leave it undocumented.
**Why:** The recall weakness is Phase-03 discovery scope, orthogonal to the Phase-04 classify→summarize→render pipeline. Mixing them would conflate two concerns and block Phase-04 validation. Phase-04 is validated against a widened/curated set; recall gets its own phase. User decision.
**Trade-offs:** Until PHASE-03.1 lands, automated seeded discovery under-recalls; UAT and near-term backfills rely on a wider `--limit` or curated bill sets.
**Revisit if:** N/A — scheduled as PHASE-03.1 (verify Congress.gov v3 search capability first, then choose pagination / since-window / summary-axis filtering).

## 2026-05-27 — 32. Consumer financial-sector data privacy is in scope
**Chosen:** FCRA / credit-reporting / GLBA and financial data-broker bills are IN scope when regulating the collection or sharing of personal data is the bill's operative core (e.g. the Homebuyers Privacy Protection Act's credit-report "trigger-leads" restriction). A financial bill is OUT only when its data/technology mention is incidental to a non-privacy purpose (e.g. the Insurance Data Protection Act's FIO subpoena power).
**Alternatives:** Exclude financial-sector privacy as a separate banking/CFPB beat.
**Why:** FCRA is foundational U.S. consumer-privacy law and credit data is personal data; the `data broker` seed already pulls in financial-data trafficking, so excluding financial privacy would create an inconsistent blind spot. The classifier already draws this line correctly (core data-privacy = in, incidental = out), validated on two real bills in the Phase-04 UAT. User decision.
**Trade-offs:** Some banking-adjacent bills with genuine data-privacy provisions are tracked; pure financial-regulation bills are excluded by the existing "incidental" disqualifier (D5).
**Revisit if:** The tracker should narrow to a "modern privacy + AI + cyber" beat that deliberately excludes sectoral financial privacy — then add a `topics.yaml` disqualifier and re-validate.

## 2026-05-27 — 33. Federal discovery recall: two-stage (wide title scan + policyArea probe)
**Chosen:** Verified Congress.gov v3 has **no keyword/full-text bill search**; the list endpoint returns title + latestAction only (policyArea/summary are detail-only). So discovery uses two-stage recall (PHASE-03.1): **Stage 1** scans wide (one ≤250 request, `fromDateTime` since-window supported) and keeps title keyword-matches; **Stage 2** probes up to `max_probe` (=250) of the remaining bills' `policyArea` via one cheap core-detail GET each (`Source.fetch_policy_area`) and keeps those in a deliberately broad `topics.yaml` `policy_areas` allowlist. The Claude classifier then applies precision. New: `Source.fetch_policy_area`, `pipeline.recall_filter`, `policy_areas` in the taxonomy/loader.
**Alternatives:** A keyword/query param (doesn't exist); title-only filter (the original bug); summary-keyword detail filtering (heavier, 2 calls/probe).
**Why:** The API offers no topical query and the list is too thin to filter by topic, so the only topical signal beyond the title is `policyArea` — one detail GET. A broad allowlist favors recall; the classifier trims the over-inclusion. Explicit `--seed` stays a targeted search (Stage-1 only, no probe).
**Trade-offs:** Stage 2 costs up to `max_probe` detail GETs per run, and the broad allowlist sends more bills to the classifier (plan usage). **Comprehensive historical backfill via offset pagination over a whole congress is DEFERRED** — v1 recalls from the newest-updated 250 + the probe, so topical bills not recently updated in a historical congress remain out of reach until pagination lands.
**Revisit if:** Recall in practice still misses bills (add offset pagination and/or summary-keyword filtering), or classifier plan-usage from the broad allowlist proves too high (narrow the allowlist).

## 2026-05-27 — 34. PHASE-05 legislative history is one combined phase (deterministic spine + research)
**Chosen:** Build the deterministic spine (versions, committee reports, votes, public law, Statutes at Large) AND the heavy research layer (hearings, attributed statements, narrative, open-web search) together in a single PHASE-05.
**Alternatives:** Split it — ship the spine first (offline-testable, shippable on its own) and gate the expensive/risky research layer behind it, mirroring D14 (law-brain commentary-first / discovery-gated) and the PHASE-03.1 carve-out. This was the recommended option.
**Why:** User decision — preferred a complete legislative-history feature in one pass over incremental shipping.
**Trade-offs:** Larger phase (≈2–3 sessions). The research layer is interactive-UAT-only and web-dependent, so more of the phase is validated by live UAT than by offline tests.
**Revisit if:** The combined scope proves unwieldy in a future leg-history change — split the deterministic and research modules then (`pipeline/leg_history.py` is a natural growth point already noted in review).

## 2026-05-27 — 35. Leg-history research draws on the official record + the open web; every claim needs a fetchable URL
**Chosen:** The `leg-history-researcher` subagent may use the official record (GovInfo Congressional Record / hearings / committee reports, Congress.gov) AND the open web (member press releases, reputable news). Every researched hearing and statement MUST carry a fetchable `source_url`; every statement carries a VERBATIM quote that is verifiable against that page.
**Alternatives:** Official-record-only (lower attribution risk, narrower coverage); official-only-now with web-readiness later.
**Why:** User decision — wants the richer picture (sponsor press statements, reactions), not just the official record. The added risk is contained by the grounding gate + cross-modal verifier (D36).
**Trade-offs:** Higher misattribution/hallucination risk than official-only; the verification burden moves to the deterministic gate + verifier, and unverifiable items are dropped (lower recall on quotes).
**Revisit if:** Open-web sources prove too noisy or unverifiable in practice — restrict the researcher to the official record.

## 2026-05-27 — 36. Cross-modal verifier + deterministic gate both gate every persisted quote (activates D17)
**Chosen:** A researched statement persists ONLY if it passes BOTH (a) a deterministic grounding gate — `source_url` returns 200, the normalized verbatim quote appears on the page, and the quote is ≥20 normalized chars — AND (b) an independent `leg-history-verifier` subagent on a DIFFERENT model (researcher = `sonnet`, verifier = `opus`) that re-confirms quote presence + speaker attribution. Failures are dropped and logged, never silently persisted. Hearings are gated by URL-resolves. No review-queue UI this phase. Verdicts are keyed by statement index, so the caller must not reorder statements between verification and grounding.
**Alternatives:** Deterministic grounding only (no second model); trust the researcher (no gate).
**Why:** Attributed quotes are the highest-stakes output in the project — a misattributed quote is worse than a missed bill. This exercises the cross-modal eval that D17 reserved for the single high-stakes output.
**Trade-offs:** Extra model calls per statement (plan usage); the strict gates favor false-rejects over false-accepts, so the tracker under-reports rather than risk a bad quote.
**Revisit if:** Drop rate is too high (loosen normalization / lower the length floor) or attribution precision is still insufficient (strengthen the verifier or add a human review queue).

## 2026-05-27 — 37. Hearings + statements persist to frontmatter; deterministic spine + narrative stay body-only
**Chosen:** `leg_history.hearings` and `leg_history.statements` (with their `verified` flag) serialize to page frontmatter — durable across a clone, fed into the FTS index, verification status retained. The deterministic spine (versions, committee_reports, votes, floor_consideration, enactment) and the `narrative` remain body-only / re-derived, consistent with D20.
**Alternatives:** Whole `LegHistory` → frontmatter (fully self-contained, but long prose in YAML and diverges from D20); whole `LegHistory` body-only (D20-consistent, but the expensive non-deterministic research wouldn't survive a re-render or fresh clone).
**Why:** The researched records are expensive, non-deterministic, and carry a verification flag that must survive; the spine is cheaply re-derivable from the APIs and the narrative is prose (like `summary`).
**Trade-offs:** Splits `LegHistory` persistence (structured research in frontmatter; spine + narrative body-only). A frontmatter-only reconstruction recovers hearings/statements but re-derives the spine and loses the narrative — the same property `summary` already has under D20.
**Revisit if:** The narrative must survive a frontmatter-only rebuild (e.g. PHASE-06 Pass A) — then persist it to frontmatter too.

## 2026-05-27 — 38. Legislative history is on-demand (`/zwiad-leg-history`), not part of the routine scan
**Chosen:** Legislative history is assembled deliberately, per enacted bill, via the `/zwiad-leg-history <congress/type/number>` slash command — not automatically during routine discovery/scan. PHASE-06 (Pass A) must learn to PRESERVE a page's persisted leg-history rather than clobber it on re-fetch.
**Alternatives:** Auto-run the researcher whenever a tracked bill flips to enacted.
**Why:** Heavy multi-source research per bill is token-expensive and high-stakes; making it deliberate keeps routine scans cheap and gives the operator control over when the expensive pass runs.
**Trade-offs:** An enacted bill has no legislative-history section until the command is run for it; PHASE-06 carries a preservation obligation (noted here, not built in this phase).
**Revisit if:** Automating leg-history on enactment becomes worth the cost — wire it into Pass A together with the preservation logic.

## 2026-05-28 — 39. `/zwiad-refresh` re-classifies on text change, overriding D9 for routine refresh
**Chosen:** `/zwiad-refresh` dispatches the classifier on every bill whose `updateDateIncludingText` advanced or whose `summary_hash` changed, even if the bill was previously classified IN-scope and its identifiers haven't changed. Overrides D9 ("decided pages trusted until their identifiers change") narrowly — for the routine-refresh path only. Initial classification (`/zwiad-backfill`) still follows D9.
**Alternatives:** (a) Trust the prior classification; re-run only summarizer + amendment-explainer on refresh; (b) Hold proposed flips in a review queue (requires the PHASE-09 review-queue machinery, which is not yet built).
**Why:** User decision — wants prose freshness (summary + amendments) AND scope freshness (topics) to track together. Avoids the failure mode where a bill silently drifts out of scope (e.g. an AI clause struck in markup) while the wiki keeps tracking + summarizing it as if it were still in scope.
**Trade-offs:** One extra classifier call per text-changed bill (plan usage). Possible flap if the classifier is noisy on borderline bills. Mitigated by the OUT→stay-with-`tracking=false` rule (the page is never deleted; flipping back IN requires explicit `/zwiad-backfill --force` — a follow-up, not built in this phase).
**Revisit if:** Flap is observed (a bill toggles IN/OUT across runs without substantive change) — then narrow to summarizer + explainer per alternative (a), or add the review-queue gate.

## 2026-05-28 — 40. `LegHistory.narrative` persists to frontmatter alongside hearings/statements
**Chosen:** Extend D37's partial-persistence carve-out: page frontmatter's `leg_history` block now carries `{hearings, statements, narrative}` (D37 was `{hearings, statements}` only). Spine fields (versions, committee_reports, votes, floor_consideration, enactment) remain body-only / re-derived per D37.
**Alternatives:** Leave D37 as-is; a routine refresh strips the narrative; user re-runs `/zwiad-leg-history` to regenerate.
**Why:** The narrative is the same kind of expensive, non-deterministic, model-generated output as the verified statements — losing it on routine refresh would silently degrade the most-read part of the leg-history section. Surviving in frontmatter is the same property `hearings`/`statements` already have.
**Trade-offs:** Slightly longer YAML (the narrative is prose, not a structured list). Splits `LegHistory` persistence further: structured research + narrative in frontmatter; spine body-only.
**Revisit if:** Narrative prose in YAML proves unwieldy — then encode it as a path reference to a sidecar file and keep the frontmatter slim.

## 2026-05-28 — 41. Automation is hybrid: headless deterministic detection + interactive LLM dispatch (RECOMMENDED — confirm before PHASE-10)
**Chosen (RECOMMENDED, not yet locked):** Resolve the contradiction between the headline promise of a "scheduled scan a few times/week" and D26 (all LLM work is interactive Claude Code subagents; Python makes zero LLM calls) with a **hybrid**: a real OS cron job runs ONLY the headless, deterministic detection commands — `fetch-candidates` and `fetch-refreshable`, which make zero LLM calls — and writes a "pending dispatch" signal (the gitignored `data/runs/<id>/` candidate/refreshable JSON already serves as this signal). The LLM subagent dispatch (classifier / summarizer / amendment-explainer) still requires an interactive Claude Code session — invoked manually or via `/loop` — because D26 keeps that work on the regular plan. Cron detects and queues; a human (or `/loop`) drains the queue interactively.
**Alternatives:**
1. **Hybrid (recommended):** cron runs headless deterministic detection + writes a pending-dispatch signal; LLM dispatch stays interactive (`/loop` or manual). Keeps detection unattended and cheap; keeps every LLM call on the regular plan per D26.
2. **Pure-interactive + `/loop`:** no OS cron at all; an open Claude Code session runs `/loop` on an interval that does detection AND dispatch in one place. Simplest, fully D26-compliant, but nothing runs when no session is open.
3. **`claude -p` / Agent SDK headless:** make the whole scan unattended by dispatching subagents headless. Rejected for v1 — per D26, `claude -p` and the Agent SDK draw a separate capped *Agent SDK credit* then bill API rates and do not support claude.ai subscription auth, which violates the "runs on the regular plan" constraint.
**Why:** The README/PLAN headline ("scheduled scan a few times/week") implied fully-unattended automation, which D26 explicitly forbids. The hybrid is the only option that honors BOTH the freshness goal (detection runs on a schedule) and D26 (LLM calls stay interactive). Detection is pure deterministic HTTP, so it is safe to run headless; dispatch is the part D26 reserves for interactive sessions.
**Trade-offs:** Not fully hands-off — a person (or an open `/loop` session) must drain the pending-dispatch queue, so freshness of the LLM-derived prose depends on someone running the interactive pass. Cron only guarantees fresh *detection*, not fresh *pages*.
**Revisit if:** D26 is revisited (a headless/API path is adopted), or the pending-dispatch backlog regularly goes stale because no one runs the interactive pass — then reconsider option 3 on the Agent SDK credit. **This decision is RECOMMENDED only; confirm the automation direction with the user before PHASE-10 implements scheduling.**

## 2026-05-28 — 42. Classifier subagent runs on `sonnet`, not `haiku`
**Chosen:** The `classifier` subagent's frontmatter `model:` is `sonnet` (was `haiku`).
**Alternatives:** Keep `haiku` (cheapest, fastest); use `opus` (most capable, matches the leg-history verifier in D36).
**Why:** The classifier is the D17 precision gate — it applies the `positive_criteria` + `disqualify` rubric to decide operative-vs-incidental scope, which is genuinely subtle. The D32 financial-privacy line is the canonical hard case: a credit-report "trigger-leads" restriction is IN (operative data-privacy core), but an FIO-subpoena-power bill is OUT (data mention incidental). The Phase-04 UAT already recorded a haiku false-positive on `118-s-3502`. This borderline operative-substance judgment is sonnet-class work; haiku rubber-stamps near the boundary, which is exactly the failure D17 warns against ("vague verifier criteria rubber-stamp everything and make the loop theater"). `opus` is reserved for the highest-stakes output (the leg-history verifier, D36); routine per-candidate classification does not need it.
**Trade-offs:** Higher plan usage per candidate — the classifier runs once per candidate bill in `/zwiad-backfill`, and once per text-changed bill in `/zwiad-refresh` (D39), so the sonnet cost is multiplied by candidate volume.
**Revisit if:** Plan usage from classification proves too high — then re-validate `haiku` against a curated borderline set (including `118-s-3502` and the two D32 financial bills) before reverting; revert only if haiku reproduces the sonnet verdicts on that set.

## 2026-05-28 — 43. D36 grounding gate is fixed-strength; recall recovery is a prompt fix, never a gate loosening
**Chosen:** When researched leg-history quotes are dropped at a rate that looks too high, the remedy is to improve the `leg-history-researcher` / `leg-history-verifier` subagent PROMPTS (better source selection, more precise verbatim capture) — handled as a Batch 3 prompt task — NOT to weaken the D36 deterministic grounding gate (HTTP 200 + normalized verbatim substring present + ≥20 normalized chars + cross-modal verifier confirm).
**Alternatives:** Loosen normalization, lower the 20-char floor, or drop the second-model verifier to raise quote recall.
**Why:** D36 fixed the trust boundary deliberately: attributed quotes are the highest-stakes output, and the gate favors false-rejects over false-accepts on purpose. A misattributed quote is worse than a missed one. Recovering recall by loosening the gate trades the project's core correctness guarantee for coverage — the wrong trade. The honest lever is the prompt that produces better-grounded candidates upstream of the gate.
**Trade-offs:** Recall improvements are slower (prompt iteration under interactive UAT) than a one-line threshold change would be.
**Revisit if:** D36 itself is formally revisited (its own "Revisit if" — drop rate persistently too high AND prompt fixes are exhausted) — only then consider loosening normalization or the length floor, with the change logged against D36.

## 2026-05-28 — 44. Historical pagination has a home: v1 tracks forward from now; full back-catalog pagination is PHASE-03.1's deferred follow-up
**Chosen:** The comprehensive historical backfill deferred in D33 (offset pagination over a whole congress) is explicitly assigned a home rather than left floating: **v1 tracks forward from now** — discovery recalls from the newest-updated 250 bills + the `policyArea` probe, so a topical bill not recently updated in a historical congress stays out of reach until offset pagination lands. Offset pagination remains a deferred follow-up to PHASE-03.1, not part of PHASE-06.1.
**Alternatives:** Build offset pagination now; or leave the gap undocumented (the status quo before this entry).
**Why:** D33 deferred this but never stated where it lives or what the v1 contract is, leaving an ambiguous gap. Pinning it as "forward-from-now is the v1 contract; back-catalog is a named deferred follow-up" makes the limitation explicit and auditable instead of an unspoken surprise.
**Trade-offs:** Historical bills (not recently updated) are not auto-discovered in v1; comprehensive back-catalog coverage waits for the deferred pagination work.
**Revisit if:** Recall in practice misses bills that are not recently updated in a historical congress — then implement offset pagination as the named PHASE-03.1 follow-up.

## 2026-05-28 — 45. Topics are retained when a refresh flips a bill out of scope — a deliberate historical-record choice
**Chosen:** When `/zwiad-refresh` re-classifies a tracked bill OUT of scope (D39), the page's existing `topics[]` are RETAINED, not cleared; the page stays with `tracking=false` (the OUT→stay rule) but keeps its recorded topics as a historical record of why it was once tracked.
**Alternatives:** Clear `topics[]` on an out-of-scope flip so frontmatter reflects only current scope.
**Why:** A page flipped OUT is never deleted (D39); retaining its topics preserves the audit trail of why it entered the tracker, which matters for understanding scope drift (e.g. an AI clause struck in markup). Logging this makes the behavior an auditable, intentional choice rather than an accident of the refresh code.
**Trade-offs:** Frontmatter `topics[]` on a `tracking=false` page reflects historical, not current, scope — readers must use `tracking` (not `topics`) as the current-scope signal.
**Revisit if:** Retained topics on flipped-out pages cause confusion in the index or FTS results — then clear them on flip and record the scope history elsewhere (e.g. a `former_topics` field or the git history).

## 2026-05-28 — 46. Retry-After honored on 5xx; GovInfo 429 stays non-retryable
**Chosen:** Both source clients parse `Retry-After` (delta-seconds or HTTP-date) on a 503 and prefer it over the blind exponential wait via a tenacity wait callable; an absent/invalid header falls back to exponential. GovInfo 429 remains a non-retryable `RateLimitError` (fail-fast, no in-process retry).
**Alternatives:** (a) Keep blind exponential backoff everywhere; (b) make GovInfo 429 retryable-with-Retry-After.
**Why:** A server-supplied `Retry-After` is more accurate than guessing, and respecting it is polite to a shared public API. GovInfo's 429 is an hourly per-key quota (~the 40/sec shared limit), not a short transient — retrying it in-process cannot clear the quota and only burns attempts; the operator should back off the whole run instead.
**Trade-offs:** A hostile/buggy `Retry-After` could stall a run for the header's duration (bounded only by the server, not `wait_max`); acceptable for these trusted gov APIs. GovInfo 429 still aborts the command rather than degrading gracefully.
**Revisit if:** A run is observed stalling on an oversized `Retry-After` (then cap it at `wait_max`), or GovInfo's 429 proves to be a short rolling window worth retrying.

---

## 2026-05-28 — 47. Source API keys are query-param auth; redact before logging
**Chosen:** Both Congress.gov and GovInfo are called with the key as a `?api_key=` query parameter (their only supported auth), and every string that could carry a request URL into a message or log is routed through `redact_api_key`, which masks the value to `REDACTED`.
**Alternatives:** Header-based auth (not offered by either API); trust that URLs never reach logs.
**Why:** Query-param auth is forced by the upstream APIs, so the key inevitably appears in full request URLs. A single redaction helper makes leak-prevention a one-liner at every boundary rather than a per-message judgment call.
**Trade-offs:** A new helper to remember to apply; it only catches the `api_key` param name (sufficient for these two sources).
**Revisit if:** A third source uses a different secret param name or header — then generalize the redactor to a configurable set of secret keys.

---

## 2026-05-29 — 48. State bill id = `{state}-{year_start}-{type}-{number}`; adds `Bill.legiscan_bill_id`
**Chosen:** A state bill's page id (and global `items.id` primary key) is `{state}-{year_start}-{type}-{number}` — e.g. `ca-2023-sb-362`. `type` and `number` come from splitting the verbatim LegiScan `bill_number` into its leading non-digit-run prefix and its trailing run of digits, both lowercased, with leading zeros stripped from the number (`"SB362"` → `sb` + `362`; `"SB0181"` → `sb` + `181`; `"SBX12"` → `sbx` + `12`). Special sessions self-disambiguate: LegiScan reflects the state's own marker in `bill_number` (California: `SBX1…`, `ABX2…`), so the split is a lossless partition of the verbatim string — distinct bill numbers yield distinct ids within a `(state, year_start)` pair without a separate special-session suffix. `Bill.legiscan_bill_id: int | None` is added as the stable native cursor key for refresh; the wiki id does not contain it, so refresh stores it explicitly to match a page against a `getMasterListRaw` entry. `None` for federal bills; round-trips automatically via `model_dump(exclude_none=True)`. Extends D21.
**Alternatives:** Append `session_id` as a special-session disambiguator (floated during design); include a `us-` prefix on state ids to mirror the federal shape.
**Why:** The verbatim-split rule is deterministic and lossless — it never interprets the state's session marker, only partitions the string, so it is robust to per-state formatting conventions. The `session_id` suffix was rejected because the state's own `X<n>` marker already carries the disambiguation: `SBX12` and `SB12` yield `sbx-12` and `sb-12`, which are distinct without any suffix. A `us-` prefix is redundant because state ids begin with an alpha state code (`ca-…`) and federal ids begin with an integer congress (`118-…`) — the two namespaces never collide.
**Trade-offs:** The split does not semantically segment the special-session marker (it captures `sbx` as one prefix, not `sb` + `x`), but this is intentional: semantic segmentation would require per-state knowledge of marker conventions, while lossless partitioning is universal and collision-free within a session. Other states' special-session formats must be verified during the 50-state rollout.
**Revisit if:** A state uses a `bill_number` with no trailing digit run (letter-suffix numbering), breaking the split; or a cross-congress canonical bill identity is needed (then add an alias, as noted in D21).

## 2026-05-29 — 49. Target coverage = all 50 states; phased rollout via `[states].enabled`; supersedes D12's 7-state scope
**Chosen:** The design target is all 50 U.S. states. The code is state-count-agnostic — `LegiScanSource` accepts any LegiScan-valid 2-letter abbreviation, and the CLI loops over whatever list `[states].enabled` contains. The phased rollout starts with the 7 priority states (CA, NY, TX, CO, VA, WA, IL) and expands coverage by editing the config list, with no code changes required. Supersedes D12's explicit 7-state scope.
**Alternatives:** Keep 7-state scope as the design target and treat broader coverage as a future phase requiring new code; hard-code the state list in the source.
**Why:** The query API design (`getSearchRaw` per state, `getMasterListRaw` per state) is inherently per-state and scales linearly — there is no architectural reason to cap at 7. Making the config list the only gate means expansion is a one-line edit rather than a code change, which is the correct place for an operational decision. The binding constraint at scale is classifier and summarizer plan usage (D26) — the per-state `--limit` is the lever — not LegiScan's 30k-request/month quota (steady-state usage at 50 states with a modest `--limit` is approximately 4k requests/month: one `getMasterListRaw` per state per refresh cycle plus `getBill` only on changed bills).
**Trade-offs:** The 50-state goal commits to eventual broader classifier plan usage; the phased rollout via `--limit` and the config list is the mitigation. Special-session `bill_number` formatting conventions for states outside the priority 7 have not been verified (noted in D48); they will surface during the rollout, not before.
**Revisit if:** LegiScan quota proves binding in practice at scale (then negotiate a higher-tier key or reduce refresh cadence); or per-state classifier plan usage from a broad `--limit` proves too high after the 7-state UAT (then tighten `--limit` per state).

## 2026-05-29 — 50. LegiScan query API (not the bulk dataset API); `change_hash` is the state refresh cursor; `getSearchRaw` full-text is the recall stage
**Chosen:** State bill discovery and refresh use the LegiScan **query API** — `getSearchRaw` for discovery, `getMasterListRaw` for change-detection, and `getBill` for enrichment — rather than the bulk dataset API (`getDataset`). `change_hash` (from `getMasterListRaw`) is the authoritative state refresh cursor, the direct analog of `updateDateIncludingText` for federal bills. `getSearchRaw`'s server-side full-text query is the state recall stage, replacing the federal two-stage title `keyword_filter` + `policyArea` probe (D33): because `getSearchRaw` returns only `relevance`/`bill_id`/`change_hash` per result (no titles), the federal title-based `keyword_filter` cannot apply and is not used.
**Alternatives:** Bulk dataset API (`getDataset`): downloads a whole-session base64 ZIP, requires unpacking and filtering locally, and uses a coarse `dataset_hash` per session rather than a per-bill `change_hash` — no per-bill change cursor. OpenStates v3 as a drop-in alternative behind `sources/base.py` (noted as a documented option in PLAN.md, not used in v1).
**Why:** The query API gives per-bill `change_hash` granularity, which is exactly the cursor needed for the incremental refresh model: one cheap `getMasterListRaw` call per state covers the entire current session and identifies only the bills that changed, so `getBill` is spent only on those. The bulk dataset's coarse `dataset_hash` would require re-processing the full ZIP on any session change and offers no bill-level cursor. `getSearchRaw`'s server-side full-text search is higher-recall than title-only keyword matching for state bills, where title conventions vary more than in federal legislation.
**Trade-offs:** `getSearchRaw` pagination is capped at page 1 in v1 (the relevance-ranked head, bounded by `--limit`); deeper pagination is a deferred follow-up (D44's forward-from-now posture applies here too). The `getMasterListRaw` "current session" shortcut has a known rollover risk at session boundaries (documented in D44 as the prior-session archived-bills behavior); the `getSessionList` pin is the escape hatch if it bites.
**Revisit if:** Per-bill `change_hash` granularity is no longer sufficient (e.g. a session has too many changed bills to poll individually); or `getSearchRaw` recall proves insufficient and a full session scan via the dataset API is needed.

## 2026-05-29 — 51. LegiScan failure signaled as HTTP 200 + `{"status":"ERROR"}`; client branches on body first; `_redact` extended to `key=`
**Chosen:** LegiScan signals API-level failure as an HTTP 200 response with a JSON body of `{"status": "ERROR", "alert": {"message": "…"}}` — not as a 4xx/5xx status code. The client branches on `body.status` first: a quota-exhaustion message (substring match on "limit"/"quota"/"exceeded" in `alert.message`) raises `RateLimitError`; any other ERROR body raises `SourceFetchError`. HTTP 429 (if it occurs) is also a `RateLimitError`; HTTP 5xx is retried via tenacity then raises `SourceFetchError`. The client never relies on a 429 or `Retry-After` existing for quota signals, because the LegiScan manual does not document quota-exhaustion HTTP semantics. The `_redact` helper is extended to mask `key=` (LegiScan's auth param name) in addition to `api_key=` (Congress.gov/GovInfo), using a `\b(api_key|key)=` alternation that prevents the inner `key` of `api_key=` from double-matching. Extends D46 and D47.
**Alternatives:** Rely on HTTP 429 for quota detection (undocumented for LegiScan; fragile); separate redactors per source (duplicates logic and creates a new leak surface with each new source).
**Why:** The LegiScan API manual documents `body.status` as the authoritative failure signal and notes an optional `alert` object — the HTTP status code is unreliable as a quota indicator. Branching on `body.status` first is therefore the correct contract: it handles the documented case (ERROR body on 200) and still handles an unexpected 4xx/5xx as a fallback. The quota substring match is intentionally lenient (any of "limit", "quota", "exceeded") because the exact message is undocumented and may vary. The unified `_redact` extension prevents a `key=SECRET` from appearing in logs whenever a LegiScan URL is logged, which would happen immediately without it.
**Trade-offs:** The quota-message substring match is heuristic — an ERROR message that happens to contain "limit" in a non-quota context would be misclassified as a rate limit; this is acceptable because any ERROR should be treated as terminal until resolved, and the distinction is only between retry-later (`RateLimitError`) and inspect-now (`SourceFetchError`). The `\b` word-boundary approach to preventing `api_key=`'s inner `key` from re-matching is regex-dependent; if a future source uses a param name like `nokey=`, it would not be caught (add it to the alternation).
**Revisit if:** LegiScan begins documenting and using HTTP 429 reliably for quota exhaustion — then add `Retry-After` handling mirroring D46; or a new source uses a secret param name not covered by the current alternation — then extend the regex, as D47 already anticipated.

## 2026-05-29 — 52. Enforcement is discovery-driven; re-running the scan is the refresh (no /zwiad-refresh leg)
**Chosen:** Enforcement currency comes from re-running `/zwiad-scan-enforcement`; there is no enforcement pass in `/zwiad-refresh`.
**Alternatives:** A bill-style change cursor re-fetching a stored press-release URL; a content-hash refresh of tracked pages.
**Why:** Enforcement updates arrive as NEW feed items about the same matter (complaint → settlement), not edits to the original press release, so re-fetching a stored URL detects nothing. Discovery + matter consolidation matches how the data actually arrives.
**Trade-offs:** Currency depends on running the scan; an update published between runs is picked up on the next scan, not immediately.
**Revisit if:** An agency begins materially editing existing pages in place.

## 2026-05-29 — 53. Two-tier enforcement matter matching with a deterministic confirm
**Chosen:** Match a new item to an existing matter by a deterministic strong key (court docket / FTC docket or file number) when present; otherwise by an LLM matcher (`enforcement-matcher`, sonnet) over a deterministic shortlist keyed on investigation target + date. An LLM match auto-applies ONLY after a deterministic `confirm_match` (normalized respondent token-overlap + date proximity + confidence ≥ threshold). Failed confirm → new page + a `possible-duplicate-of` run-report note, never a silent wrong-merge.
**Alternatives:** Strong-key only (misses no-docket AG matters); LLM-only (wrong-merge risk); a committed review queue for every uncertain match (heaviest).
**Why:** AGs frequently publish neither a docket nor a file number, so deterministic-only can't consolidate their multi-item matters; but an unconfirmed LLM merge can fuse unrelated cases. This is the law-brain D16 discipline (deterministic key → LLM fallback → mechanical grounding → fail-safe) applied to enforcement. The overlap floor (0.34) sits deliberately just above the 1/3 score of two two-token names sharing one token; when a match's date is absent on either side, date proximity can't ground it, so a stronger overlap floor (0.6) is required instead.
**Trade-offs:** A confirmed-but-actually-distinct match (same respondent + window, different case) could still merge — fixable manually; acronym/DBA mismatches ("GTL" vs "Global Tel Link") score 0 and won't auto-match (conservative; strong-key or manual link is the escape hatch). A persistent review queue is a named follow-up.
**Revisit if:** Wrong-merge or missed-merge rates prove high in practice (tune thresholds or add the review queue).

## 2026-05-29 — 54. One generic config-driven state-AG adapter with per-source AND per-article failure isolation
**Chosen:** A single `StateAGSource` (`kind = rss | html`, `item_selector`) serves every AG; adding a state is config-only. Discovery failures are caught per source and yield `[]` (logged); additionally, a per-article `fetch_text` failure is caught and that one item skipped, so neither a broken feed nor a single moved press release aborts the multi-agency run.
**Alternatives:** A bespoke scraper class per state (more code, same fragility); abort-on-error (one broken AG kills the scan).
**Why:** AG sites are layout-fragile and numerous; config-driven keeps fragility in data, and isolation keeps the blast radius to one source / one article.
**Trade-offs:** HTML selectors need per-site tuning (done in UAT); a silently-failing source yields nothing until noticed — mitigated by per-source counts in the run report.
**Revisit if:** A high-value AG has a structure the generic adapter can't express (then a targeted adapter behind the same protocol).

## 2026-05-29 — 55. Separate enforcement rubric + subagents; shared taxonomy, model, render, CLI
**Chosen:** Enforcement gets its own rubric block (`positive_criteria_enforcement` / `disqualify_enforcement` in `topics.yaml`) and its own subagents (`enforcement-classifier`, `enforcement-extractor`, `enforcement-matcher`), while reusing the `ai/privacy/cyber` taxonomy keys, the `EnforcementAction` model, and the render/schema/CLI plumbing.
**Alternatives:** Reuse the bill classifier/summarizer unchanged (rubric mismatch — bill criteria enumerate appropriations/resolutions); a fully separate enforcement taxonomy (duplicates ai/privacy/cyber, invites drift).
**Why:** The relevance judgment differs from bills, but the taxonomy keys and page machinery are mechanically identical; one prompt judging both kinds would erode the stated-negative-criteria precision D17 protects, and a duplicate taxonomy would drift.
**Trade-offs:** Two rubric blocks in one file; three new subagent prompts to maintain.
**Revisit if:** The two rubrics converge enough to merge, or a fourth page kind appears.

## 2026-05-29 — 56. EnforcementAction prose persists to frontmatter (unlike Bill) so consolidation is monotonic
**Chosen:** `summary/background/allegations/outcome/significance` persist to frontmatter for `EnforcementAction` (a type-aware body-only exclusion in `to_frontmatter`), while `Bill` keeps its prose body-only.
**Alternatives:** Keep enforcement prose body-only like Bill (consolidation then can't preserve an earlier development's prose — the page shows only the latest item's prose, and idempotency becomes input-dependent); a separate sidecar store.
**Why:** A bill summary is re-derived by re-running the summarizer on each refresh, but enforcement prose is an LLM extraction from a transient article that is never re-fetched — consolidation loads the page from disk and merges, so the prose must round-trip through `from_page` (i.e. persist to frontmatter) for the merge to be monotonic (a settlement item that omits the complaint's allegations must not blank them). Same D40 principle (persist non-re-derivable LLM output); the body is still re-rendered from the persisted model, so D20 holds.
**Trade-offs:** Enforcement frontmatter carries multi-line prose (like the leg_history narrative); slight redundancy (prose in both frontmatter and body). Bill behavior is unchanged.
**Revisit if:** Enforcement prose grows large enough that frontmatter bloat matters, or a re-extract-on-refresh path is added.

## 2026-05-30 — 57. PHASE-09 law-brain commentary re-architected to the post-pivot slash-command/subagent model
**Chosen:** PHASE-09 ships as a `/zwiad-sync-lawbrain` slash command driving a deterministic Python `fetch-lawbrain-candidates` half, a single `lawbrain-matcher` subagent (keyless pages only), and a deterministic `render-lawbrain-commentary` half — mirroring `/zwiad-scan-enforcement`. Most of the persistence/render/config/store layer (`CommentarySource`, `_commentary_block`, `LawBrainSettings`, `lawbrain_pages`) already existed from PHASE-02.
**Alternatives:** PLAN.md's pre-pivot design — a `pipeline/run.py` two-pass loop calling the Anthropic SDK.
**Why:** D26/D27/D30 route all LLM work through interactive Claude Code subagents; Python makes zero LLM calls. The PLAN's `run.py`/SDK design is dead. Splitting at the LLM boundary (fetch → matcher → render) keeps each Python half independently unit-testable.
**Trade-offs:** Departs from PLAN.md's module/orchestration names; the matcher is validated by interactive UAT, not offline tests.
**Revisit if:** A headless/API path is adopted (see D26).

## 2026-05-30 — 58. Commentary copy = full body, syntax-neutralized
**Chosen:** A matched law-brain page's whole body is copied verbatim into the `## Commentary & Analysis` block, with two render-time transforms: ATX headings demoted `##`→`###` (D6) and dead `[[wiki-slug]]` cross-reference links flattened to plain text. All sections retained. The stored `CommentarySource.body` is the raw law-brain body; transforms happen in `templates._commentary_block` so `content_hash` stays tied to the source bytes.
**Alternatives:** Copy only selected sections (Summary/Key points); true byte-verbatim including dead `[[links]]` and original heading levels.
**Why:** Faithful to D2's "verbatim full page" intent while fixing the one real defect — `[[wiki-slug]]` links resolve only inside the law brain and would be dead in ZwiadBrain. Transforms at render keep one source of truth.
**Trade-offs:** Not a literal byte copy (two minimal transforms); a long regulation page produces a long commentary block.
**Revisit if:** The operator wants byte-pure copies or section selection.

## 2026-05-30 — 59. Commentary attaches on a shared jurisdiction-qualified key regardless of ZwiadBrain page kind
**Chosen:** A law-brain page attaches to whichever tracked item shares ≥1 jurisdiction-qualified key (bill number / docket / public law), regardless of ZwiadBrain page kind — a `regulation` page about a statute can attach to the `enforcement` page that enforces it. `type_map` (D8) governs only PHASE-11 stub-minting, not PHASE-09 attachment. The LLM matcher's link is auto-applied only after a deterministic `confirm_match` that recomputes both key-sets FROM DISK (the freshly-read law-brain page + the freshly-loaded target) — never from keys echoed through the subagent's JSON (D16 grounding; mirrors the enforcement matcher grounding the candidate against the on-disk page).
**Alternatives:** Restrict attachment to the `type_map` kind (regulation→bill only) — loses cross-type matches like TAKE IT DOWN Act statute↔FTC enforcement.
**Why:** Cross-type commentary is genuinely useful and the shared-key set-intersection is kind-agnostic. Recomputing keys from disk is the whole point of D16: a deterministic confirm must ground the untrusted LLM proposal, so it cannot trust LLM-passed-through keys.
**Trade-offs:** A correct match with no extractable shared key never auto-applies — it routes to the review queue (operator override in `links.yaml`).
**Revisit if:** Override volume becomes burdensome, or a kind-specific attachment rule is wanted.

## 2026-05-30 — 60. Multi-subject law-brain pages (tracker/landscape/map/scholarship) fail closed
**Chosen:** A page whose slug matches a `commentary_only_slug_markers` entry emits ZERO deterministic keys and is excluded from commentary entirely — it neither mints nor attaches. Key extraction is also hardened so an academic/law-review citation is never misread as a bill/docket. Single-subject `concept`/`regulation`/`case`/… pages attach normally.
**Alternatives:** Let a landscape attach to one "best" target (smears a multi-subject body onto one bill) or to all mentioned items (duplicates a long page across many pages).
**Why:** A landscape/tracker has no single subject; copying its verbatim body onto any one tracked bill is off-topic and onto all is noise. Refines D7.
**Trade-offs:** A bill mentioned only in a tracker gets no law-brain commentary (official discovery still tracks the bill itself).
**Revisit if:** Trackers prove to be the only commentary signal for important items.

## 2026-05-30 — 61. Review-queue resolution is folded into the render half (no separate `review --commit`)
**Chosen:** `render-lawbrain-commentary` both writes new `[pending]` proposals (low-confidence / collision / weak-grounding / stale) to `wiki/review-queue.md` AND, in the same pass, reads operator-resolved `[accept]`/`[reject]` tokens, applies/records them in `links.yaml`, and prunes the resolved entries. An `[accept]` is the operator override D16 allows.
**Alternatives:** A standalone `zwiadbrain review --commit` command (the PLAN's design).
**Why:** One code path handles new and resolved proposals; at the current corpus the queue is near-empty, so a second stateful command is unwarranted.
**Revisit if:** Review volume grows enough to want a dedicated review workflow.

## 2026-05-30 — 62. Harvest secondary/law-firm reference links into a `## Further Reading (via law brain)` section
**Chosen:** When a law-brain page is attached, harvest `[text](url)` + bare URLs from the page body AND the `sources/zwiad/*.md` memos its `sources:` frontmatter references, EXCLUDE primary-source domains (`*.gov`, `legiscan.com`, `courtlistener.com`, `wikipedia.org`, `europa.eu`, `legislation.gov.uk` — a configurable `primary_source_domains` denylist), dedup by normalized URL, and render the remainder in a dedicated `## Further Reading (via law brain)` section. Deterministic, offline, no LLM.
**Alternatives:** Surface all links (re-lists primary sources ZwiadBrain already carries); only page-body links (misses the law-firm links, which live in the memos, not the page body).
**Why:** The unique value the law brain adds is the lawyer's collected secondary commentary (law-firm client alerts, IAPP, natlawreview) — links ZwiadBrain has no other way to get; primary sources are already in each page's `## Sources`.
**Trade-offs:** A URL with `)` in its path (e.g. Wikipedia disambiguation) truncates at the paren — acceptable, since such hosts are denylisted and secondary-commentary hosts don't use paren paths.
**Revisit if:** The denylist needs per-jurisdiction tuning, or the operator wants primary links surfaced too.

## 2026-05-30 — 63. Commentary + Further Reading survive non-sync re-renders via `lawbrain:region` text preservation
**Chosen:** The whole law-brain-contributed region (commentary blocks + Further Reading) is wrapped in `<!-- lawbrain:region:begin -->`…`<!-- lawbrain:region:end -->` markers and rendered LAST (after Sources). `write_page` centrally preserves a committed region: a re-render whose model carries no commentary bodies (a `/zwiad-refresh`/`/zwiad-backfill` of the freshly-fetched item) splices the prior committed region back verbatim instead of dropping it. `/zwiad-refresh` additionally carries `prev.commentary_sources` forward so the frontmatter bookkeeping survives too. `/zwiad-sync-lawbrain` is the SOLE creator/updater/remover of the region (the body-level analog of `preserve_leg_history`). Bodies/links stay out of frontmatter (honors D20).
**Alternatives:** Persist the verbatim body + links to frontmatter (D40/D56 pattern) — but embedding multi-KB markdown documents in YAML is bloaty and byte-fragile; re-sync-after-refresh (leaves a visible data-loss window).
**Why:** Closes a real data-loss gap: a `/zwiad-refresh` re-renders the freshly-fetched bill (empty `commentary_sources`) and would otherwise strip committed commentary. Text-preservation keeps verbatim bodies out of YAML and is byte-identical (the region is copied exactly), so D20 holds.
**Trade-offs:** Render gains a "preserve existing region" step (a function of the model + the prior page text during a non-sync render), a small deviation from pure-function-of-model.
**Revisit if:** A use case needs the commentary reconstructable from frontmatter alone (no prior page / no law brain).

## 2026-05-31 — 64. `/zwiad-sync-lawbrain` attaches the region in place; it never re-renders a bill's body
**Chosen:** `render-lawbrain-commentary` writes via a new `write_lawbrain_region` (`pipeline/render.py`) that reads the committed page, preserves its body byte-for-byte, splices the freshly-built `lawbrain:region` in (replacing any existing one; keeping the committed region verbatim when the item produces no fresh region), and rewrites only the frontmatter `commentary_sources` bookkeeping. It no longer routes through `write_page` (a full re-render of the body from the model).
**Alternatives:** (a) Re-fetch the full bill from LegiScan/Congress before rendering so `write_page`'s model is complete — network-coupled, defeats the offline/deterministic sync design; (b) persist a bill's `summary`/`actions`/`text_versions` to frontmatter so `from_page` can reconstruct them — the bloaty/byte-fragile YAML path D63 already rejected, and it would rewrite every committed bill page.
**Why:** D63 preserved the region across *refresh* re-renders but missed that the *sync* path itself rebuilt the page from frontmatter (`from_page` → `write_page`). A bill's Summary / Status & Timeline / Full Text are body-only (`_BODY_ONLY_FIELDS` — deliberately re-derivable, not serialized), so that re-render dropped them, reducing a tracked bill page to `## Sources` + the commentary region. Caught by the first live UAT against the real law brain (the showcase SB-53 page); the 609 unit tests missed it because the render fixtures seed body-less target pages.
**Trade-offs:** A second write path (`write_lawbrain_region`) alongside `write_page`; the two must stay byte-compatible (same `to_frontmatter` + region spacing). A rich-body regression test (`test_render_lawbrain_preserves_existing_bill_body`) now guards it, and the existing re-run test guards idempotency.
**Revisit if:** Bill bodies ever become reconstructable from frontmatter (then `write_page` + D63 region preservation alone would suffice).

## 2026-05-31 — 65. PHASE-10 scheduling = one interactive `/zwiad-run`, externally triggered
**Chosen:** A single interactive orchestration command (`/zwiad-run`) sequences all enabled source flows and auto-commits per source; an external runner that opens an interactive Claude Code session triggers it on a schedule. ZwiadBrain ships no OS-scheduler wiring.
**Alternatives:** D41's split hybrid (OS cron for headless detection + separate interactive dispatch); pure `/loop`; headless `claude -p` (D26-forbidden).
**Why:** The user will drive scheduling via an external interactive-session runner, which can do BOTH detection and dispatch in one session — collapsing D41's hybrid to a single entrypoint and keeping every LLM call on the regular plan (D26). Scheduler-agnostic so the trigger can be anything.
**Trade-offs:** Nothing runs unless the runner opens a session; a long single-session run dispatches many subagents.
**Revisit if:** A headless path is ever adopted (see D26), or single-session runs grow too large to complete reliably (then split per-source).

## 2026-05-31 — 66. `/zwiad-run` auto-commits per source; run-log is the audit trail
**Chosen:** Each source's changes are auto-committed as the run proceeds (conventional messages); a committed append-only `scan-log.md` records one grep-parseable block per run via the deterministic `zwiadbrain run-log` verb. Leg-history is flagged, never auto-run. Law brain stays read-only.
**Alternatives:** Stage-only (review-before-commit, the other 6 commands' convention); auto-commit to a per-run branch + PR.
**Why:** Unattended/runner-driven operation needs the changes committed without a human in the loop each run; git history + `scan-log.md` are the after-the-fact review surface. Leg-history is the heaviest, rarest flow, so it is surfaced for a deliberate manual run.
**Trade-offs:** Commits land without per-run human review (mitigated by diffs + the run-log); a bad scrape could commit noise (mitigated by the existing classifiers + idempotent renders).
**Revisit if:** Auto-committed noise becomes a problem — switch to the dated-branch-+-PR variant.

## 2026-06-01 — 67. Full document text is extracted with Docling into sidecar `.text.md` files
**Chosen:** A dedicated, deterministic `extract-text` CLI verb downloads each tracked item's operative source document — a bill's enrolled/latest text version, or an enforcement action's press release plus linked filing PDFs — runs it through Docling (`DocumentConverter` → Markdown), writes the result to a `<id>.text.md` sibling of the page, links it from the page via a preserved `extracted-text:region`, and discards the downloaded PDF. The pre-existing "Full Text" source links are left untouched.
**Alternatives:** Inline the text in the page body (bloats pages + diffs); a separate `texts/` tree or git-LFS (more plumbing); keep links only as before (D3 — no full text stored); a lighter extractor such as pypdf/pymupdf4llm (no layout/table ML, lower fidelity).
**Why:** Pages only stored an LLM summary + links; the operator wanted the actual source text captured for reference/search. Docling gives layout-aware PDF/HTML→Markdown locally with no LLM/API call, fitting the deterministic Python layer (D26/D27). A sidecar keeps the page diff small while the extraction can be large. The region mirrors the law-brain region's preserve/splice so a later `write_page` re-render (refresh) stays byte-identical (D20/D63).
**Trade-offs:** Extraction is a separate opt-in step (not wired into `/zwiad-run` yet); sidecars grow the repo; scanned PDFs need an OCR extra for good output. LegiScan's API terms may restrict storing/redistributing state-bill text — federal bill text and FTC documents are public-domain U.S. government works, but LegiScan-sourced state-bill extractions are stored at the operator's discretion (verify the license or keep the repo private).
**Revisit if:** Sidecar repo growth becomes a problem (move to git-LFS / a `texts/` tree); extract-text should run inside `/zwiad-run`; or LegiScan's license forbids stored state-bill text (then gate state extraction off).

## 2026-06-01 — 68. Docling is an optional, operator-installed dependency — not locked in pyproject
**Chosen:** `docling` is NOT a declared/locked project dependency. The `extract-text` verb and the `pipeline/docling_text` boundary lazy-import it and fail fast with an install hint (`uv pip install docling`, then `uv run --no-sync zwiadbrain extract-text …`) when it is absent. The unit suite mocks the boundary, so tests + pyright + CI run docling-free. `docling_text.py` carries the single documented file-level `# pyright:` suppression for the (env-absent) docling import.
**Alternatives:** Lock docling in `[project.dependencies]` (forces typer<0.22, whose incomplete stubs break `pyright --strict` across the whole CLI — 58 errors in pre-existing commands); relax pyright on `cli.py` (weakens the strict gate); drop Docling for a lighter extractor (lower fidelity, reverses D67).
**Why:** `docling-slim[standard]` / `docling-core` pin `typer>=0.12.5,<0.22`, conflicting with the project's typer 0.26.x; typer 0.21.2's stubs fail strict pyright project-wide. Keeping docling out of the lock preserves the strict gate and the lightweight core install, while the heavyweight ML stack (PyTorch + layout models) is pulled only when an operator actually runs extraction.
**Trade-offs:** docling is not pinned for reproducibility; a fresh environment needs a manual install before real extraction (documented); `uv run`'s re-sync removes it (use `--no-sync`).
**Revisit if:** Docling relaxes its typer cap (then lock it normally), or extraction becomes a core/CI-required step (then isolate it via a separate environment or a conflict-aware extra).

## 2026-06-02 — 69. Leg-history breadth via a tiered trust model + on-bill/related page split, not a weaker gate
**Chosen:** Expand legislative-history source coverage by making the *unit of trust* explicit rather than loosening the D36 gate. Tier 1 = attributed verbatim quote (`Statement`) — must clear the unchanged D36 gate; new Tier-1 sources are executive signing statements (`source_type: "signing"`) and sponsors' subject-matter statements. Tier 2 = related media/reference (hearing videos, subject-matter hearing links) — listed *without* an attributed quote, so there is nothing to misattribute (modeled in Phase A as `Hearing` entries with a URL and no quote; a dedicated `RelatedMedia` model is deferred to Phase B). Every item carries a `relation` of `on_bill` or `related`; the renderer keeps on-bill items in the existing sections and gathers `related` items under a labeled "Related (Subject Matter)" section. The Python grounding gate (`ground_items`), quote normalization, and the verifier echo cross-check are unchanged byte-for-byte.
**Alternatives:** Loosen the verbatim/normalization gate to admit more sources (reverses D36/D43, risks misattribution — the project's worst failure); admit videos as Tier-1 quotes without a transcript (ungroundable); one flat "Statements" section mixing on-bill and subject-matter items (misleads readers into thinking a topical statement was about this bill).
**Why:** The user wants a wide variety of sources (signing statements, sponsors' past/subject-matter statements, hearing videos). The crown-jewel guarantee is "no persisted attributed quote unless verbatim-grounded + cross-verified." Tiers deliver breadth where it can be proven (quotes that ground) and link the rest as media, so the guarantee survives intact.
**Trade-offs:** Two-class rendering adds a section and a `relation` field on `Statement`/`Hearing` (frontmatter-persisted, default `on_bill`, backward-compatible). Video-derived quotes need transcript grounding (Phase B) — until then videos are media-only.
**Revisit if:** A `RelatedMedia` model is needed for richer media metadata (Phase B), or readers find the on-bill/related split confusing.

## 2026-06-02 — 70. "Related (subject-matter)" items are bounded by a sponsor/official relevance clamp
**Chosen:** A `related` (subject-matter) statement or hearing is admitted only when ALL hold: (a) it ties to one of the bill's `topics`/`policy_area`; (b) it is by a **sponsor or cosponsor of this bill** OR is an **official record** (hearing/committee/floor); and (c) an independent relevance check (the verifier's `on_subject`) confirms it. The researcher applies the clamp when emitting `related` items; the verifier re-checks it independently and folds an off-subject `related` item into `verified: false`, so the existing `verified`-keyed grounding gate drops it — no Python gate change.
**Alternatives:** Open topic-match (any source on the bill's topic by anyone) — maximizes breadth but is the main misleading-inclusion / dilution risk (a random think-tank op-ed would qualify); enforce relevance in new Python (changes the gate, more surface area).
**Why:** "Related to the subject matter" is far looser than "about this bill"; without a clamp the section fills with tangential noise. The clamp keeps the user's wanted content (sponsors' past statements on the topic) while excluding the firehose. Enforcing it through the verifier's `verified` flag keeps the deterministic gate untouched.
**Trade-offs:** A genuinely relevant non-sponsor third-party statement is excluded by design (precision over recall). Relevance enforcement depends on the LLM verifier rather than deterministic code this phase.
**Revisit if:** Operators want curated non-sponsor commentary admitted, or relevance needs deterministic enforcement.

## 2026-06-02 — 71. Leg-history research fans out by source lane (single lane-aware researcher, dispatched per lane)
**Chosen:** The `/zwiad-leg-history` orchestrator dispatches one `leg-history-researcher` per source lane — `crec`, `hearings`, `press`, `signing` — in parallel, then merges their outputs in a fixed order and runs a single verifier pass over the merged statement list. The researcher is a single lane-aware agent file (the dispatch names the lane) rather than four near-duplicate agent files. Only the `crec` lane writes the narrative.
**Alternatives:** One do-everything researcher in a single long prompt (cheaper — one dispatch — but lower recall and weaker per-source verbatim discipline); four separate agent files (duplicated prompt text, drift risk).
**Why:** Focused per-lane prompts with sharper source lists raise recall and quote discipline; the user asked for fan-out. A single lane-parameterized agent avoids prompt duplication. The merge happens before the single verifier pass, preserving the index↔verdict contract the gate depends on.
**Trade-offs:** More subagent dispatches per run (more regular-plan usage) on an on-demand command; the merge step must fix statement order before verification or risk misattribution (documented in the command).
**Revisit if:** Plan-usage cost of four dispatches is too high (fall back to one enriched researcher), or lanes need different models.

## 2026-06-02 — 72. RelatedMedia is a first-class Tier-2 model; spoken quotes ground via transcript-preferred / caption-fallback — gate unchanged
**Chosen:** Phase B promotes D69's deferred Tier-2 media to a dedicated `RelatedMedia` model (`title`, http-validated `url`, `kind` video|page|other, `publisher`, `date`, `relation`, `note`) on `LegHistory.related_media`. It carries NO attributed quote, so it is grounded by a SEPARATE gate `ground_related` (URL-200 + an independent verifier *identity* verdict) — never the verbatim-quote gate. It renders in its own `### Related Media` subsection (after "Related (Subject Matter)"), persists to frontmatter, and is carried across refresh by `preserve_leg_history`. A spoken quote becomes a Tier-1 `Statement` ONLY when the verbatim words are carried by fetchable text, in preference order: (1) an official transcript page (researcher sets `source_url` to it — the high-yield path), or (2) the video's captions via `youtube-transcript-api` (researcher sets `source_url` to the YouTube watch URL; a transcript-aware fetch wrapper resolves it to caption text). The D36 deterministic gate — `ground_items`, `_normalize_text`, and the verifier echo cross-check — is byte-for-byte unchanged: the transcript path only changes the `fetch` callable passed in, not the gate logic.
**Alternatives:** Keep modeling videos as quote-less `Hearing` entries (Phase A stopgap — conflates a hearing record with a video and has no kind/publisher metadata); admit video quotes as Tier-1 without any transcript grounding (ungroundable — reverses D36); loosen the gate to accept captions despite missing punctuation/casing (reverses D36/D43, the misattribution risk).
**Trade-offs:** Auto-generated captions lack punctuation/casing, so the case-sensitive verbatim gate USUALLY drops a caption-grounded quote (fail-closed by design, not a bug) — the official-transcript path is the realistic Tier-1 source; the caption path is low-yield. `relation` on `RelatedMedia` defaults to `related` and currently does not change rendering (all media render together in `### Related Media`); it is carried for parallelism with `Statement`/`Hearing` and possible future filtering. The render-leg-history staging contract gains `related_media` + `media_verdicts` keys, and the verifier output becomes an object with `statements` + `related_media` arrays (the orchestrator maps the latter to `media_verdicts`).
**Revisit if:** The caption path proves worth its weight (then add a researcher step that reads captions before quoting) or never fires (then drop the YouTube-caption fallback and keep transcript-page-only); or `relation` on media needs to affect rendering.

## 2026-06-02 — 73. `youtube-transcript-api` is a declared (locked) dependency — unlike Docling (D68)
**Chosen:** `youtube-transcript-api>=1.2,<2` is added to `[project.dependencies]` and locked in `uv.lock`. This is the OPPOSITE call from Docling (D68, kept optional/operator-installed), and is justified by the dependency actually resolving clean: a dry-run resolves it as a single added package (its `requests`/`defusedxml` deps already satisfied) with NO `typer` downgrade, and `pyright --strict` reports 0 errors on a probe import (it ships type information). The phase pre-authorized the optional fallback only "if it conflicts (the D68 typer<0.22 trap)"; that condition is not met, so the primary "lock it" instruction stands. The transcript helper still lazy-imports the library inside `_youtube_captions` and fails closed to `(0, "")` on any error (missing lib, disabled/absent captions, network), so a stripped environment degrades to Tier-2 media rather than crashing — and unrelated CLI commands do not pay the import cost at startup.
**Alternatives:** Keep it optional/lazy like Docling (D68) — unnecessary here because, unlike `docling-slim`'s `typer>=0.12.5,<0.22` cap that breaks strict pyright project-wide, this library is conflict-free and typed; vendoring a minimal caption fetcher (reinvents a maintained library against YouTube's undocumented caption endpoint); no caption path at all (loses D72's fallback).
**Trade-offs:** Adds `requests` + `defusedxml` to the locked tree (the project otherwise uses `httpx`); the caption path is low-yield (auto-captions usually fail the gate, D72) so the dependency earns its keep mostly via the official-transcript path, which needs no library. YouTube's caption endpoint is undocumented and ToS-gray; the fail-closed boundary contains breakage to "no quote, video stays Tier-2 media."
**Revisit if:** The library starts pulling heavy/conflicting pins on a future release (then pin tighter or move it optional like Docling), the caption path proves never-used (drop the dependency), or YouTube blocks the endpoint (the fail-closed path already degrades gracefully).

## 2026-06-02 — 74. Leg-history orchestration is a TWO-step deterministic assembler, not one command
**Chosen:** Replace the by-hand lane-merge + verifier-index assembly with two pure Python CLI steps that share one merge helper, `merge_lanes` (`pipeline/leg_history.py`). Step 1 `build-verifier-input` reads `leghistory.json` + the four `lane-{crec,hearings,press,signing}.json` files, merges them deterministically (fixed lane order; dedup statements by `(speaker, quote)`, hearings + media by `url`; narrative from the `crec` lane only; drop a malformed lane / parse-drop a malformed item), and writes `verifier-input.json` — a `subject` block plus index-stamped `statements`/`related_media`. The interactive session dispatches the verifier over THAT and saves `verifier.json`. Step 2 `assemble-leg-history-input` re-runs `merge_lanes` (byte-identical order, same inputs) and attaches verdicts keyed by merged index with the verifier echo cross-check applied fail-closed (`verified:false` on a speaker/quote_prefix or title_prefix mismatch, or a missing verdict), writing `leghistory-research.json` — the render-input `render-leg-history` already consumes. Python assigns every index on both sides of the verifier, so the verdict↔statement alignment is correct by construction, not by hand.
**Alternatives:** A single `assemble-leg-history-input` that content-binds verifier verdicts to merged statements by the `(speaker, quote_prefix)` echo and ignores the verifier's self-reported index (one command, but introduces a new join model and a same-speaker/prefix-collision edge case); index-primary with a content fallback (most branching to test); keeping the hand assembly (the status-quo footgun the phase exists to remove). User chose the two-step option.
**Why:** Making the merge deterministic on BOTH sides of the verifier is the most literal fix for "the lane-merge + verifier-index assembly was done by hand": the verifier is numbered by Python, so its echoed indices line up with the assembler's re-merge with zero coordination risk, and the existing, tested render-leg-history index+echo logic is reused unchanged rather than replaced by a new content-join. The `subject` block lives in the verifier-input (where the verifier reads it), not the render-input — resolving the original Task-1 wording that put it in the render-input.
**Trade-offs:** Two commands + a Python step between lanes and verifier (the orchestrator command gains a step vs. the single-command sketch); correctness assumes the lane files are unchanged between the two steps (true in the orchestrated flow — the merge is pure, so identical inputs give identical order). The echo cross-check is duplicated in semantics between the assembler and render-leg-history (intentional defense in depth; render is not refactored this phase to keep feature and refactor separate — a later refactor can DRY both onto one helper).
**Revisit if:** The two steps ever read divergent lane inputs (then fold the merge into a single command that also dispatches nothing), or the duplicated echo check drifts (then extract a shared `echo_matches` helper and route both call sites through it).

## 2026-06-04 — 75. State leg-history spine assembles from one getBill; votes parsed inline, supplements → Tier-2 leads; Bill model unchanged
**Chosen:** Extend legislative history to enacted state bills (Phase D) by mirroring the federal spine→leads→render flow off a SINGLE LegiScan `getBill` call, without touching the committed `Bill` model. A new `LegiScanSource.fetch_leg_history(native_id)` does one `getBill` and returns a transient `StateLegHistoryInputs(bill, votes, supplement_media)`: `bill` via the existing `_to_bill`; `votes` via a new `_parse_votes` (roll calls → `Vote(date, chamber, result, roll_call_url=state_link or url)`); `supplement_media` via a new `_parse_supplement_media` (each supplement → a Tier-2 `RelatedMedia` lead, `kind="page"`, url-less supplements skipped). `assemble_state_spine(bill, votes)` (pipeline/leg_history.py) builds the spine: `versions ← bill.text_versions`, `votes ← parsed`, `floor_consideration ← []` (left empty — see below), `enactment ← Enactment(date_signed=_state_signed_date(bill), url=state_link or LegiScan url)`; researcher fields empty. `collect_state_leads(bill, supplement_media)` returns the researcher leads (`state` instead of `congress`, `supplement_media` dicts, `enacted_date`). The new `fetch-state-leg-history` CLI writes the same `{bill, spine, leads}` `leghistory.json`, so the unchanged `build-verifier-input` → verifier → `assemble-leg-history-input` → `render-leg-history` chain and the US-XX→states/xx/ routing are fully reused. The governor signing message (Tier-1 `signing`) and any state-legislature hearing video (Tier-2) are researcher directives carried in the command/lead context, not deterministic spine data. Enacted gate = `bill.enacted` (LegiScan status==4 / Chaptered progress event 8).
**Alternatives:** (a) Add `votes`/`supplements` fields to the shared `Bill` model (literal phase reading) — rejected: pollutes the committed frontmatter model with two state-only fields, duplicates `LegHistory.votes`, and breaks the federal invariant that votes live ONLY in the re-derived spine. (b) Mirror the federal Protocol exactly with `assemble_state_spine(bill, legiscan_source)` calling `legiscan_source.recorded_votes()` / `supplements()` — rejected: re-fetches `getBill` per method (LegiScan quota waste) when one call already returns everything. (c) Populate state `floor_consideration` from passage/reading history actions — rejected: `FloorAction` has no free-text field and state actions carry no CR citation or per-action URL, so it renders as bare "date chamber" bullets or empties and duplicates the bill's Status & Timeline; the roll-call passage events render in the Votes section (with LegiScan rollcall links) instead. Both forks were put to the user, who chose "keep Bill clean" and "leave floor empty."
**Why:** State data arrives in one `getBill` response (unlike federal's Congress.gov + GovInfo fan-out), so a transient return type is the natural carrier and keeps the persisted model and its frontmatter round-trip untouched. Treating supplements as Tier-2 `RelatedMedia` leads reuses D72's existing gate (`ground_related`: URL-200 + verifier identity, no quote) with zero new model. Keeping the spine deterministic and the governor/video items as researcher leads preserves the D36/D69 trust boundary unchanged.
**Trade-offs:** `assemble_state_spine` takes parsed data, not sources, so its signature is not byte-parallel to `assemble_spine(bill, congress_source, govinfo_source)` (justified by the genuinely different data shape). `_to_bill` itself does not parse votes/supplements — sibling helpers do — a small deviation from the literal "_to_bill parses" task wording. State `floor_consideration` is always empty. The CA chapter number ("Chapter 709") is NOT captured as a public-law analog this phase (deferred to Phase E's CA leginfo integration). Governor-signing recovery depends on the researcher finding the message, as federal signing statements already do.
**Revisit if:** A second state source (not LegiScan) needs the same spine (then lift `assemble_state_spine` to a shared shape), the chapter/statute citation becomes worth capturing (Phase E), or floor-level state detail is wanted (then add a description-bearing floor model rather than overloading `congressional_record`).

## 2026-06-04 — 76. Grounding-gate fetcher hardened (browser UA + Docling PDF extraction); gate stays deterministic
**Chosen:** Harden the deterministic grounding gate's fetch layer (`cli._fetch_url`) so it retrieves the same content the independent verifier's WebFetch sees, WITHOUT making the gate LLM-dependent. (Fix 1) Send a browser-like `User-Agent`/`Accept` so WAF/bot-gated hosts (e.g. gov.ca.gov, which 403s the default `python-httpx` agent) return 200. (Fix 2) Detect a PDF response (content-type or `%PDF-` magic bytes) and extract its text via the existing Docling boundary (`extract_markdown`, D67/D68): the UA-fetched bytes are written to a temp file and parsed locally. `_extract_pdf_text` is deterministic and never raises — when Docling is absent (optional/unlocked, D68) or extraction fails it returns `""`, and the gate fail-closed drops the item exactly as for an unfetchable page. The gate LOGIC (`ground_items`, `ground_related`, `_normalize_text`, `_page_text`) is BYTE-UNCHANGED — only the fetch layer changed.
**Alternatives:** (a) Route the gate through an LLM/WebFetch like the verifier — rejected: collapses gate and verifier into one model and destroys the cross-modal independence that is the core of the trust model. (b) A single shared fetch+extract cache both gate and verifier read — stronger consistency but removes the verifier's independent second fetch; deferred as possible v2. (c) A light locked PDF lib (pypdf) instead of Docling — lower fidelity; the project already depends on Docling for document text (D67), so reuse is consistent (operator chose Docling). (d) Headless-browser JS rendering (Fix 3) — heavy, lowest ROI; deferred.
**Why:** The PHASE-16 SB-53 UAT dropped verifier-confirmed quotes purely because the gate's raw `httpx.get` couldn't fetch what the verifier's WebFetch could: gov.ca.gov 403'd the default UA (dropping the Governor's signing statement) and PDF committee analyses returned un-parseable bytes (dropping 7 sponsor/analysis quotes). Hardening the deterministic fetch — not weakening the gate or the verifier — closes the asymmetry while preserving the deterministic-verbatim + independent-verifier trust boundary.
**Trade-offs:** Docling is heavyweight (PyTorch + OCR models); the gate now pays that cost for each PDF source during an interactive render (a new `DocumentConverter` per call — caching deferred). When Docling is absent the PDF path silently degrades to a drop (as before this phase), so CI/type-check envs and Docling-free installs are unaffected — but a Docling-free operator still won't ground PDF quotes. The spoofed browser UA only affects which pages the read-only grounding fetch can read. Superscript/ligature-bearing PDF quotes (e.g. `10²⁶`) may still fail-closed after extraction.
**Revisit if:** Per-PDF Docling cost becomes painful (cache the converter, or pre-extract+cache shared by gate and verifier — the deferred v2), JS-rendered sources need grounding (Fix 3), or Docling is dropped (then add a locked light PDF extractor).

---

## 2026-06-07 — 77. Near-duplicate statements collapse POST-grounding, keyed by normalized speaker + quote
**Chosen:** Add a `dedup_statements` pass that collapses statements whose `(_normalize_speaker(speaker), _normalize_text(quote))` key matches, first-occurrence wins, applied in `render-leg-history` to `result.statements` AFTER the grounding gate. `_normalize_speaker` lowercases, maps curly→ASCII, turns periods to spaces, and strips a curated set of leading honorifics/titles (Gov./Governor/Sen./Senator/Attorney General/…) with a guard that never empties the name. The render summary reports a new `near-dup` count; the input/grounded/parse-drop/ground-drop reconciliation stays exact. `merge_lanes`' exact `(speaker, quote)` dedup is left byte-unchanged.
**Alternatives:** (a) Quote-only dedup (ignore speaker) — rejected: two different officials sharing a verbatim quote would wrongly collapse. (b) Collapse at `merge_lanes` time on the normalized key — rejected: merge dedup is first-wins by LANE_ORDER, and the press-lane copy (JS-rendered url, fail-closed drops) sorts before the signing-lane copy (gov.ca.gov, grounds); collapsing pre-grounding could keep the ungroundable copy → a grounding-yield REGRESSION. (c) Do nothing — the PHASE-17 SB-53 UAT showed the same Newsom quote listed twice ("Gavin Newsom" + "Gov. Gavin Newsom").
**Why:** PHASE-17 surfaced the near-dup: dedup-by-exact-`(speaker, quote)` can't see that an honorific-prefixed speaker is the same person. Deduping among ALREADY-grounded statements is regression-safe (every survivor already passed the gate) and is the only placement that cannot trade a groundable copy for an ungroundable one.
**Trade-offs:** Speaker normalization is heuristic (a curated honorific list, not an identity resolver); paired with quote normalization in the key, a false collapse needs two genuinely different people to share BOTH a normalized name AND a verbatim 20+ char quote — accepted as vanishingly unlikely. The honorific list is US/CA-centric and will need extension for other titles. Behavior is covered by deterministic unit + render-integration tests; a live SB-53 re-render UAT is deferred to a batched live run after the fetch-layer phases (PHASE-19/20).
**Revisit if:** A real false-collapse is observed (then tighten — e.g. require role match too, or drop speaker normalization for that case), or the honorific list misses titles in new jurisdictions (extend `_SPEAKER_HONORIFICS`).
