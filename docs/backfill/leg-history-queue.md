# Legislative-history follow-up queue

> Significant enacted laws flagged during the enacted-laws backfill (D85) for a later,
> **per-law-approved** `/zwiad-leg-history` pass. Leg-history is the expensive multi-subagent
> grounded-research flow and is **not** run during the backfill — it is run on demand, one law at
> a time, after you approve each. The `/zwiad-backfill-enacted[-state]` commands append rows here in
> their step 7.

**Flag a law when** it is a named Act, or otherwise high-salience (a major rewrite, broad scope,
landmark privacy/AI/cyber statute). Skip routine/minor enactments — the queue is for the laws whose
interpretation a sourced legislative history materially helps.

**Status:** `flagged` → `approved` (you OK'd a leg-history run) → `done` (leg-history rendered).

## Queue

| Wiki id | Title | Jurisdiction | Why significant | Status | leg-history cmd |
|---------|-------|--------------|-----------------|--------|-----------------|
| 118-hr-815 | PL 118-50 (carries PADFAA + Protecting Americans from Foreign Adversary Controlled Applications Act / TikTok divestiture) | US | landmark data-broker + foreign-adversary-app statutes; high salience; rode an emergency-supplemental vehicle | flagged | /zwiad-leg-history 118/hr/815 |
| 117-hr-7776 | PL 117-263 / FY23 NDAA — carries the Daniel Anderl Judicial Security and Privacy Act (data-broker ban re: federal judges' info) | US | named data-broker/judicial-security Act; CAVEAT: the relevant history is the *standalone* Daniel Anderl bill, not the NDAA vehicle — leg-history keyed to 117/hr/7776 would surface defense-bill history, low value | flagged | /zwiad-leg-history 117/hr/7776 |

<!--
Example rows (delete once real entries land):
| 118-s-2073 | FAA Reauthorization Act of 2024 | US | named Act, broad scope | flagged | /zwiad-leg-history 118/s/2073 |
| ca-2019-ab-25 | California Consumer Privacy Act amendments | US-CA | landmark privacy statute | flagged | /zwiad-leg-history ca/AB25 |
-->
