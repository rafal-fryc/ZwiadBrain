# Phase 03 — Federal source
Status: PENDING

## Goal
Discover and enrich U.S. federal bills from Congress.gov v3 into tracked wiki pages.

## Tasks
- [ ] `sources/base.py` — Source protocol: `discover(since) -> candidates`; `fetch(id) -> detail`
- [ ] `sources/congress.py` — Congress.gov v3 client (httpx + tenacity retry): discover via `/bill?fromDateTime&sort=updateDate+desc`; enrich `/bill/{congress}/{type}/{num}` + `actions`, `amendments`, `text`, `summaries`, `subjects`, `cosponsors`, `relatedbills`
- [ ] `config.py` — pydantic-settings loader for `zwiadbrain.toml` + `.env` (first real need: `CONGRESS_API_KEY`)
- [ ] `pipeline/discover.py` — keyword-seed + since-window candidate discovery
- [ ] `pipeline/enrich.py` — candidate -> full `Bill` model (timeline, amendments, text versions)
- [ ] cli: `backfill --congress N --limit K` that enriches and renders federal bills

## Acceptance Criteria
- [ ] Offline: fixture Congress.gov JSON (respx-mocked) -> enriched `Bill` -> rendered page with timeline + amendments
- [ ] Live (needs `CONGRESS_API_KEY`): `backfill --congress 118 --limit 5` -> 5 pages under `wiki/federal/bills/`
- [ ] pytest + ruff + pyright (strict) all green

## Decisions Made This Phase
(append as you go)
