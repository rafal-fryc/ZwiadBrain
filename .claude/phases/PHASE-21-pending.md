# Phase 21 — CA leginfo deep integration (committee analyses + vote records)
Status: PENDING

> Phase E continuation. D77-revisit note (DECISIONS.md): state leg-history currently
> rides the LegiScan spine; chapter/statute citation and floor-level CA detail were
> left for a deeper leginfo integration.

## Goal
Enrich CA state-bill leg-history with committee-analysis sources and vote records
pulled directly from leginfo.legislature.ca.gov, so CA bills carry the same depth
the federal pipeline gets from Congress.gov/CREC.

## Open design decision (confirm before building)
Scope/source choice — which leginfo artifacts to ingest, and via what fetch path
(leginfo is partly JS-rendered; may depend on PHASE-19's render fallback). Confirm:
1. Committee analyses (PDF) only — reuse PHASE-17 Docling PDF path.
2. + Vote records (roll-call) into the spine `votes`.
3. + Chapter/statute citation on enactment.
Decision + the leginfo URL contract must be logged before implementation.

## Tasks (provisional — finalize after the decision)
- [ ] leginfo source adapter (deterministic fetch; respects robots/UA)
- [ ] Map committee analyses -> Statement/Hearing inputs for the existing gate
- [ ] Map roll-call votes -> spine `votes`
- [ ] TDD with recorded leginfo fixtures (no live network in unit tests)
- [ ] Live UAT on CA SB-53 (or a fresh CA bill)
- [ ] Decision log entry

## Acceptance Criteria
- A CA bill render includes leginfo-sourced committee analyses and/or votes
- All new fetches deterministic and fail-closed; unit tests use fixtures
- Full gate green
