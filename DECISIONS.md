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
