# Phase 27 — Harden LegiScan enacted-state discovery
Status: ACTIVE  (PHASE-26 campaign paused until this lands)

## Goal
Make state enacted-discovery yield only genuinely-enacted, de-duplicated laws, and stop recall from silently dropping laws like the NY SHIELD Act — without regressing California or the federal path.

## Tasks
- [ ] Fix 1: exclude memorializing resolutions at the list stage (`_is_resolution` + `number` carry) — legiscan.py
- [ ] Fix 2: `dedupe_companions` post-enrich via `sasts`/related_bills — discover.py + cli.py wiring
- [ ] Fix 3: add targeted recall seeds ("security breach" etc.) under existing keys — topics.yaml
- [ ] Tests: NY masterlist fixture, dedup tests, recall/loader tests; CA fixture untouched
- [ ] Gate green (ruff, pyright, pytest); live NY smoke shows SHIELD; CA still ~870
- [ ] DECISIONS D92/D93/D94

## Acceptance Criteria
- NY 2019 fetch returns a far smaller, resolution-free, de-duplicated set that includes the SHIELD Act.
- CA path unchanged (~870; CCPA cluster still recalled). Federal path untouched.
- Full gate green.
