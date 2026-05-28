# Phase 05 — Legislative History (deterministic spine + grounded research + verifier)
Status: DONE

> Full design: `docs/superpowers/specs/2026-05-27-phase05-legislative-history-design.md`.
> Decisions locked in brainstorming: D34–D38 (logged to DECISIONS.md in this phase).
> TDD throughout (test first, watch it fail, implement, watch it pass, commit). Atomic commits per task.

## Outcome (2026-05-28)
PHASE-05 shipped on `feature/phase-05-leg-history` (27 commits, 248 tests + ruff + pyright strict all green,
v0.5.0). Pipeline: `/zwiad-leg-history <bill>` → fetch (Congress + GovInfo, same api.data.gov key confirmed
live) → researcher subagent (sonnet, WebSearch + WebFetch on the official record + open web) → cross-modal
verifier subagent (opus) → deterministic grounding gate (URL 200 + verbatim quote present + ≥20 chars) →
render. Every rendered item links to its primary source; previously-dropped floor/vote/enactment links
are fixed (T5 + I1). Hearings + statements persist to frontmatter with `verified`; spine + narrative
remain body-only (D37). DECISIONS.md #34–#38 logged.

**Live UAT passed (118/hr/2670 → PL 118-31, FY24 NDAA):** spine fully assembled (7 versions, 2 committee
reports, 7 recorded votes, 50 CREC floor entries, signed PLAW link); narrative present;
**9 grounded + verified statements** spanning both chambers and both sides (Rogers ×3 sponsor / Gaetz
opposition / Smith dropped on ambiguous attribution / Schumer / Reed / Wicker / Rogers + Pelosi from the
Sept 20 conference-instruction debate). 0 hearings — researcher correctly rejected all 4 noisy CHRG
leads. 5 of 14 statements dropped (1 verifier + 4 deterministic-gate "quote not found") — fail-closed
direction, audit log emitted, no misattribution. Rendered page: `wiki/federal/bills/118-hr-2670.md`.

**One live-discovered fix shipped (commit 4a961cb):** the GovInfo `/search` public-preview endpoint
returned `governmentAuthor` as a list (e.g. `["Congress", "House of Representatives"]`); Pydantic
rejected it on the `Hearing` model. Added `_flatten_str` tolerant coercion in `sources/govinfo.py`
for all search-derived string fields, plus regression tests.

**Deferred (non-blocking, future polish):**
- `Enactment.statutes_at_large` never populated (M1, GovInfo surface uncertain).
- Deterministic gate's raw-HTML fetch over-rejects on JS-rendered press-release pages (`.senate.gov` PRs)
  and some CREC pages with whitespace/line-wrap idiosyncrasies — precision (no misattribution) is the
  priority for the trust boundary; a follow-up can swap to BeautifulSoup text-extract + smarter
  quote-window match to lift recall.
- PHASE-06 (Pass A / routine scan) carries a preservation obligation: do not clobber the persisted
  `leg_history` frontmatter on bill re-fetch (D38).

## Goal
On demand, assemble a standardized, **source-linked** Legislative History for an enacted federal
bill — a deterministic spine (versions, committee reports, votes, public law, Statutes at Large) plus
researched hearings + attributed statements + a narrative, where every persisted quote passes both a
deterministic grounding gate and a cross-modal verifier, and every rendered item links to its source.

## Architecture (recap)
Mirrors Phase-04: Python deterministic bookends (`fetch-leg-history` → `data/runs/<id>/` JSON →
`render-leg-history`) with Claude Code subagents (`leg-history-researcher`, `leg-history-verifier`)
dispatched in between by the `/zwiad-leg-history` slash command, on the user's regular plan. Python
makes no LLM calls.

## File map
- Create `src/zwiadbrain/sources/govinfo.py` — `GovInfoSource` (httpx+tenacity, CongressSource shape); leg-history enricher, not a discover/fetch Source.
- Create `src/zwiadbrain/pipeline/leg_history.py` — `assemble_spine(...)`, `collect_leads(...)`, `ground_items(...)` (deterministic grounding gate; the `ground_items` name is used consistently in T8/T10).
- Modify `src/zwiadbrain/models.py` — add `Hearing`, `Statement`; extend `LegHistory` (`hearings`, `statements`, `narrative`); add `url` to `Enactment`.
- Modify `src/zwiadbrain/wiki/templates.py` — render Hearings/Statements/Narrative; **fix** dropped links for floor consideration, votes, enactment.
- Modify `src/zwiadbrain/wiki/schema.py` — persist `leg_history.{hearings,statements}` to frontmatter; spine + narrative stay body-only (precedent: `commentary_sources` special-case).
- Modify `src/zwiadbrain/cli.py` — `fetch-leg-history`, `render-leg-history`.
- Modify `src/zwiadbrain/config.py` — `GOVINFO_API_KEY` (likely the same api.data.gov key).
- Create `.claude/agents/leg-history-researcher.md`, `.claude/agents/leg-history-verifier.md`, `.claude/commands/zwiad-leg-history.md`.
- Tests: create `tests/test_govinfo.py`, `tests/test_leg_history.py`; extend `tests/test_models.py`, `tests/test_schema.py`, `tests/test_render.py`, `tests/test_cli.py`, `tests/test_agents.py`.
- Modify `DECISIONS.md`, `pyproject.toml`, `src/zwiadbrain/__init__.py` (version 0.5.0 at phase end).

## Tasks
- [x] **T1 — GovInfo API capability spike** (no code shipped; produces findings + adapts T6/T7). Verify, against live docs/API: the full-text **search** endpoint + query shape for collections CREC/CHRG/CRPT/BILLS/PLAW/STATUTE; whether a bill package **enumerates** its related CREC/CHRG/CRPT/PLAW or must be searched by congress+bill number; auth (api.data.gov key) and rate limits; how public-law / Statutes-at-Large detail (+ its URL) is reached. Record findings inline here under "Decisions/Findings" and adjust T6/T7 accordingly. If per-bill linkage is weak, the spine leans on Congress.gov and GovInfo is primarily a CREC/CHRG full-text lead source + Statutes at Large.
- [x] **T2 — config:** add `GOVINFO_API_KEY` to `config.py` and `.env.example`; reuse the api.data.gov key per the spike. Test: settings load the key (extend existing config test).
- [x] **T3 — models:** add `Hearing(title, committee, chamber, date, citation, url)`, `Statement(speaker, role, date, quote, context, source_url, source_type, verified)`; extend `LegHistory` with `hearings`, `statements`, `narrative`; add `url` to `Enactment`. Tests in `test_models.py`: construct/validate each; `role`/`source_type` accept the documented literals.
- [x] **T4 — schema persistence:** in `wiki/schema.to_frontmatter`, emit `leg_history` to frontmatter as **only** `{hearings, statements}` (drop spine fields + narrative), following the `commentary_sources` special-case precedent; `from_page` round-trips them with `verified` intact. Tests in `test_schema.py`: a `Bill` with full `LegHistory` → frontmatter contains hearings/statements (with `verified`) and **not** versions/votes/narrative; reparse preserves hearings/statements.
- [x] **T5 — renderer:** extend `templates._leg_history` to render **Hearings**, **Statements** (`**Speaker** (role), date — "quote" — [source](source_url) ✓`), and **Legislative Journey** narrative; **fix** the existing gaps so `FloorAction.url`, `Vote.roll_call_url`, and the new `Enactment.url` render as links. An item with no link does not render. Tests in `test_render.py`: every subsection emits a `[...](url)`; ✓ only when `verified`; byte-identical re-render.
- [x] **T6 — GovInfo source:** implement `GovInfoSource` per the spike — methods to fetch/search committee reports, CREC/CHRG leads, and public law / Statutes at Large (+ URLs) for a bill; httpx + tenacity retry + RateLimitError, matching `CongressSource`. Tests in `test_govinfo.py` (respx): fixture payloads map to the expected structures; 429→RateLimitError; 5xx→retry→SourceFetchError.
- [x] **T7 — spine assembly + leads:** in `pipeline/leg_history.py`, `assemble_spine(bill, congress_source, govinfo_source) -> LegHistory` (versions, committee reports, votes, enactment incl. public law + Statutes + url) and `collect_leads(bill, govinfo_source) -> dict` (CREC/CHRG refs, committee names, sponsor+cosponsor names, key dates). Tests (respx/fakes): a fixture enacted bill yields a populated spine + leads; a non-enacted bill is rejected upstream (see T9).
- [x] **T8 — grounding gate:** in `pipeline/leg_history.py`, `ground_items(statements, hearings, *, fetch) -> kept/dropped` requiring HTTP 200 **and** (statements) the quote present as a whitespace-normalized substring of the fetched page; combine with the verifier verdict passed in. Drop+log failures. Tests in `test_leg_history.py`: quote present→kept(`verified`); quote absent→dropped; 404→dropped; verifier=false→dropped; whitespace-insensitive match.
- [x] **T9 — cli `fetch-leg-history`:** `--bill <congress/type/num> [--out DIR]`; fetch bill (reuse CongressSource), **abort if not enacted**, assemble spine + leads, write `leghistory.json` to `data/runs/<id>/`. Tests in `test_cli.py` (respx): writes correct staging JSON for an enacted fixture; non-enacted → clean abort/error.
- [x] **T10 — cli `render-leg-history`:** `--in FILE [--wiki PATH] [--db PATH]`; read researcher+verifier output, run the grounding gate (T8), assemble full `LegHistory` onto the bill, render the page, reindex; report spine items / statements proposed-grounded-dropped / hearings / narrative. Tests in `test_cli.py`: only grounded+verified statements persist; page rendered with links; re-run identical input byte-identical.
- [x] **T11 — researcher subagent:** `.claude/agents/leg-history-researcher.md` (`tools: WebSearch, WebFetch, Read`); strict-JSON `{hearings[], statements[], narrative}`; verbatim-quote + mandatory `source_url` rules; official-record-first then open web. Test in `test_agents.py`: frontmatter parses, expected tools/model.
- [x] **T12 — verifier subagent:** `.claude/agents/leg-history-verifier.md` (**different model** from researcher; `tools: WebFetch, Read`); per-statement `{index, verified, note}`; independence + no-benefit-of-the-doubt instructions. Test in `test_agents.py`: parses; model differs from researcher.
- [x] **T13 — slash command:** `.claude/commands/zwiad-leg-history.md` orchestrating fetch → read JSON → dispatch researcher → dispatch verifier → write staging → render → reindex → report (mirrors `zwiad-backfill.md`; documents the staging contract; keep `ANTHROPIC_API_KEY` unset). Test in `test_agents.py`: command frontmatter parses; referenced agent names exist.
- [x] **T14 — DECISIONS.md:** append D34–D38 (combined phase; official+web sourcing w/ mandatory fetchable URLs; cross-modal verifier adoption activating decision 17; hearings/statements→frontmatter; on-demand not routine + PHASE-06 preservation note).
- [x] **T15 — quality gate + release:** ruff + pyright (strict) + pytest all green; bump version 0.4.1 → 0.5.0 in `__init__.py` + `pyproject.toml`; rename this file to `PHASE-05-done.md` only after the interactive UAT (T16) passes; tag `v0.5.0`.
- [x] **T16 — interactive UAT (user-run, live, regular plan):** `/zwiad-leg-history` on a known enacted 118th in-scope bill → grounded+verified statements, hearings, narrative render; click-through check (every item links to its source); a deliberately-unsourceable/misattributed quote is dropped. Phase is not done until this passes.

## Acceptance Criteria
- [x] GovInfo API capability is verified and recorded; spine sourcing matches what the API actually offers (T1).
- [x] `GovInfoSource` maps fixtures correctly with Congress-parity retry/rate-limit behavior (offline, respx).
- [x] Spine assembles for an enacted fixture bill; `fetch-leg-history` aborts cleanly on a non-enacted bill.
- [x] Grounding gate keeps a quote only when the URL resolves (200) AND the quote appears on the page AND the verifier confirms it; all other cases are dropped and logged.
- [x] `hearings` + `statements` (with `verified`) persist to frontmatter and round-trip; spine + narrative are body-only.
- [x] **Every** rendered leg-history item links to its primary source — including floor/CREC, votes, and enactment, which are currently rendered link-less (regression fixed); statements show ✓ only when verified.
- [x] `render-leg-history` re-run on identical input is byte-identical (clean `git status`).
- [x] Subagents + command parse with the expected frontmatter; researcher and verifier use different models.
- [x] DECISIONS.md carries D34–D38.
- [x] ruff + pyright (strict) + pytest all green.
- [x] Interactive UAT (T16) passes: source-linked, grounded, verified Legislative History on a real enacted bill; unsourceable quote dropped.

## Decisions Made This Phase
(append findings as the phase runs; D34–D38 are pre-recorded from brainstorming — see spec §2)
- D34 — one combined phase (spine + research together), chosen over the recommended split.
- D35 — research sources = official record + open web; every claim needs a fetchable URL; quotes verifiable.
- D36 — cross-modal verifier adopted (activates decision 17); deterministic gate + verifier both required; failures dropped+logged.
- D37 — hearings/statements → frontmatter; spine + narrative body-only.
- D38 — on-demand `/zwiad-leg-history`, not routine scan; Pass A preservation deferred to PHASE-06.

## T1 — GovInfo API findings (verified live 2026-05-27)
Sources: github.com/usgpo/api, github.com/usgpo/link-service, govinfo.gov/features/{api,search-service-overview,api-related-document-service}, govinfo.gov/help/{bills,search-operators}.

- **Auth/transport:** base `https://api.govinfo.gov`; key via query param `?api_key=` (api.data.gov key family — likely the same key as Congress.gov, but **confirm live** against `/collections?api_key=…`). Limits: 36,000/hr, 1,200/min, 40/sec shared across the api.data.gov key → consider a **separate key per service**. `503` on ZIP/MODS generation (honor `Retry-After`); `429` over limit.
- **Anchor:** the enrolled-bill packageId `BILLS-{congress}{type}{num}enr` (we already know congress/type/num from Congress.gov).
- **Per-bill linkage verdict (drives T6/T7):**
  - **Deterministic** via `GET /related/{enrolledBillId}` then `GET /related/{enrolledBillId}/{COLLECTION}` for **PLAW** (public-law pkg + PL number), **CRPT** (committee reports), **Statutes at Large**, **HOB** (history-of-bills). `/related` is cheap (list + per-collection). Fallback if empty: link service `/link/plaw/{congress}/{type}.{num}`, `/link/crpt/{congress}/{type}.{num}`, or `POST /search`.
  - **NOT in `/related`: CREC and CHRG** → `POST /search` `{query: "collection:CREC AND congress:118 AND \"H.R. 1234\"", resultLevel:"default", pageSize, offsetMark:"*"}` (CHRG likewise). Treat as **leads** (noisy recall, low confidence) for `collect_leads`, not authoritative spine.
- **Votes** come from **Congress.gov** (actions/recorded votes), not GovInfo — spine already sources votes there.
- **Human-clickable source URLs:** `https://www.govinfo.gov/app/details/{packageId}` (+ `/{granuleId}` for CREC pages / CHRG sections / CRPT parts); link-service permalinks for citation-only cases (`/link/crec/{vol}/{prefix}/{page}`, `/link/plaw/{congress}/public/{lawnum}`).
- **Endpoints used:** `GET /packages/{id}/summary` (download links + billStatusLink), `GET /related/{accessId}[/{COLLECTION}]`, `POST /search` (cursor `offsetMark`, `resultLevel`, `historical`).
- **Mapper caution:** the `/search` service is "public preview" — schema may change; use a tolerant mapper. Swagger at `/docs/` is JS-rendered; pull `/api-docs` raw spec live for exhaustive fields.
- **T6/T7 impact:** `assemble_spine` = resolve enrolled pkgId → one `GET /related` → follow PLAW + CRPT + Statutes (+ summary for version links); votes from Congress.gov. `collect_leads` = `POST /search` over CREC then CHRG by congress + bill citation, capped pageSize, results surfaced as low-confidence leads with `app/details` URLs.
