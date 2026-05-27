# Phase 03 — Federal source
Status: DONE

## Goal
Discover and enrich U.S. federal bills from Congress.gov v3 into tracked wiki pages.

## Tasks
- [x] `sources/base.py` — `Candidate` model + `Source` protocol (`discover(*, since, limit) -> candidates`; `fetch(native_id) -> Bill`)
- [x] `sources/congress.py` — Congress.gov v3 client (httpx + tenacity retry): discover via `/bill[/{congress}]?sort=updateDate desc`; enrich `/bill/{congress}/{type}/{num}` + `actions`, `amendments`, `text`, `summaries`, `relatedbills` (subjects + cosponsors deferred — see decisions)
- [x] `config.py` — settings loader for `zwiadbrain.toml` + `.env` (`CONGRESS_API_KEY`)
- [x] `pipeline/discover.py` — keyword recall filter + since-window candidate discovery
- [x] `pipeline/enrich.py` — candidate -> full `Bill` model (mapping in the source; enrich stamps `last_synced`)
- [x] cli: `backfill --congress N --limit K [--wiki PATH] [--seed ...]` that enriches and renders federal bills

## Acceptance Criteria
- [x] Offline: fixture Congress.gov JSON (respx-mocked) -> enriched `Bill` -> rendered page with timeline + amendments (`test_congress.py`, `test_cli.py::test_backfill_command_renders_federal_bill_pages`)
- [x] Live: `backfill --congress 118 --limit 5` produced 5 real pages under `wiki/federal/bills/` (verified 2026-05-27 with user's key; sample pages removed afterward — they were unclassified/off-topic, expected pre-classifier).
- [x] pytest (68) + ruff + pyright (strict) all green

## Decisions Made This Phase
- Federal bill `id` = `{congress}-{type}-{number}` (e.g. `118-hr-8818`) so ids stay unique across congresses (HR 1 recurs each congress). DECISIONS.md #21.
- `Source.fetch` returns a fully-mapped `Bill`; per-source API→model mapping lives in each source, so the pipeline never sees source JSON. `pipeline/enrich.py` is the source-agnostic seam (stamps `last_synced`; future classify/change-hash hooks). DECISIONS.md #22.
- Summary populated from the latest official CRS summary, HTML-stripped (provisional; the Claude summarizer supersedes it later). User decision. DECISIONS.md #23.
- `subjects` + `cosponsors` deferred (no model field; topics are classifier-derived per #17; cosponsors would bloat `sponsors[]`/frontmatter). Mapped now: `policy_area`, primary `sponsors[]`, `related_bills`. User decision. DECISIONS.md #24.
- `config.load_settings` merges `.env` + process env + TOML explicitly and `model_validate`s (precedence: process env > `.env` > TOML), instead of pydantic-settings' implicit source chain — testable, type-clean. DECISIONS.md #25.
- Transport policy: 5xx/transport errors retried (tenacity, exp backoff); 429 -> `RateLimitError` (no retry); other 4xx -> `SourceFetchError`.
- Live-data fix: timeline orders same-date actions chronologically. Congress returns actions newest-first, so `_build_timeline` reverses before the stable date-sort (introduced-before-referred). Found during live `backfill` verification; covered by a same-date fixture case.
