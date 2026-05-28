# Phase 05 — Legislative History: Design Spec

Date: 2026-05-27
Status: DESIGN (pre-plan) — consolidates the brainstorming session for PHASE-05.
Supersedes the PLAN.md sketch of PHASE-05 where it conflicts (see "Deltas from PLAN.md").

---

## 1. Purpose

When a federal bill is **enacted**, assemble a standardized **Legislative History** for its
wiki page. Legislative history here is deliberately broad (user definition):

- **Official / structured** (exact, deterministic): text versions, committee reports, recorded
  votes, public-law number, Statutes at Large.
- **Researched / interpretive** (search + judgment + attribution): **hearings held**, **attributed
  statements** by sponsors / members who voted / witnesses, and a **narrative** of the bill's journey.

**Verifiability is a primary goal:** every item in the assembled history must render as a clickable
link to its primary source, so that reading a law's page lets the user check every claim themselves
(see §5 "Source links are first-class").

The data model (`LegHistory`, `TextVersion`, `CommitteeReport`, `FloorAction`, `Vote`, `Enactment`)
and the renderer (`templates._leg_history`, wired into `render_bill_body`) already exist from
phases 01–02. Nothing populates them today — `CongressSource.fetch` leaves `leg_history=None`.
This phase **sources and assembles** the data and **extends** the model/renderer for the
researched parts.

---

## 2. Decisions locked in this brainstorming session

These are user decisions made during brainstorming on 2026-05-27. To be appended to `DECISIONS.md`
as #34–#38 when the phase executes.

- **D34 — One combined phase.** Build the deterministic spine *and* the heavy research layer
  together in PHASE-05. *(User chose this over the recommended split of spine-now / research-later.
  Recorded as a deliberate scope choice; the phase is consequently larger — est. 2–3 sessions.)*
- **D35 — Research draws on the official record + the open web.** GovInfo full-text (CREC, CHRG,
  CRPT) + Congress.gov, **and** open-web (press releases, news, advocacy). Every researched claim
  must carry a **fetchable source URL**; every statement a **verbatim quote** that is verifiable
  against the page it cites.
- **D36 — Cross-modal verifier adopted for leg-history** (activates the escalation PLAN.md reserved
  in decision 17). A statement persists only if it passes **both** a deterministic grounding gate
  (URL 200 + quote substring present) **and** an independent verifier subagent on a **different
  model**. Failures are **dropped and logged**, never silently persisted (decision 16 discipline).
  No review-queue UI in this phase.
- **D37 — Hearings + statements persist to frontmatter** (durable across clones, fed into the FTS
  index, verification status retained). The **deterministic spine** and the **narrative** stay
  **body-only** (spine is re-derivable from APIs like `actions`/`text_versions`; narrative is prose
  like `summary`). *Rationale:* the researched records are expensive, non-deterministic, and carry a
  verification flag that must survive — exactly what frontmatter is for; the spine/narrative follow
  the existing body-only convention.
- **D38 — On-demand command, not routine scan.** `/zwiad-leg-history <bill>` is run deliberately on
  an enacted bill. It is **not** wired into Pass A / routine scan. Pass A's obligation to *preserve*
  persisted leg-history (rather than clobber it on re-fetch) is a **PHASE-06** concern — noted here,
  not built here.

---

## 3. Architecture & data flow

On-demand, per enacted bill. Mirrors the Phase-04 pattern: **Python deterministic bookends +
Claude Code subagents in between**, file-based JSON handoff under `data/runs/<id>/`, running on the
user's **regular plan** (no API key, no Agent SDK credit).

`/zwiad-leg-history <congress/type/num>` (e.g. `118/hr/9020`):

1. **`fetch-leg-history`** (Python, deterministic)
   - Fetch the bill (reuse `CongressSource.fetch`). **Abort with a clear message if not enacted** —
     leg-history is only assembled on enactment.
   - Assemble the **deterministic spine** from Congress.gov + `GovInfoSource`: text versions,
     recorded votes, committee reports, public-law number, Statutes at Large.
   - Collect **research leads**: GovInfo CREC/CHRG package references for the bill, committee names,
     sponsor + cosponsor names, key action dates.
   - Write `leghistory.json` (bill identity + spine + leads) to `data/runs/<id>/`.

2. **`leg-history-researcher`** subagent (`tools: WebSearch, WebFetch, Read`)
   - Given spine + leads, searches the **official record** (GovInfo CREC/CHRG full text) **and** the
     **open web**. Returns strict JSON `{hearings[], statements[], narrative}`.
   - Every hearing and statement carries a `source_url`; every statement carries an **exact verbatim
     quote**, the **speaker**, and the **role**.

3. **`leg-history-verifier`** subagent (**different model** — cross-modal; `tools: WebFetch, Read`)
   - For each statement, independently fetches `source_url` and confirms the quote appears and is
     attributed to the named speaker. Returns `{index, verified, note}` per statement.

4. **`render-leg-history`** (Python, deterministic grounding gate + apply)
   - For each statement/hearing: fetch the URL — require **HTTP 200** and (for quotes) the quote
     present as a **whitespace-normalized substring**. Combine with the verifier verdict.
   - A statement persists **only if both** the deterministic check and the verifier pass
     (`verified: true`); otherwise it is **dropped and logged** to the transcript.
   - Assemble the full `LegHistory`, attach to the bill, render the page, reindex.
   - Report: spine items; statements proposed / grounded / dropped; hearings kept; narrative present.

```
/zwiad-leg-history 118/hr/9020
  └─ fetch-leg-history (Py)  → spine + leads → data/runs/<id>/leghistory.json
  └─ leg-history-researcher (subagent: web + official) → {hearings, statements(quote+url), narrative}
  └─ leg-history-verifier   (subagent: different model) → per-statement {verified, note}
  └─ render-leg-history (Py) → deterministic grounding gate (URL 200 + quote substring)
                             → both gates pass ⇒ persist; else drop+log
                             → assemble LegHistory → write page → reindex → report
```

---

## 4. First task — GovInfo API capability spike

Like PHASE-03.1 began by verifying what the Congress API could actually do, PHASE-05 begins by
verifying GovInfo, because the spine sourcing depends on it. Confirm:

- The **full-text search** endpoint and query shape (collections CREC, CHRG, CRPT, BILLS, PLAW, STATUTE).
- **Per-bill linkage**: does a bill/granule package enumerate its related CREC/CHRG/CRPT/PLAW, or
  must we search by bill number + congress?
- **Auth** (expected: the same `api.data.gov` key as Congress.gov) and **rate limits**.
- What `public_law` / Statutes at Large detail is reachable (PLAW vs STATUTE granule).

The spine sourcing adapts to what the spike confirms. If per-bill linkage is weak, the spine leans on
Congress.gov (which already yields versions, votes-as-actions, committee-report references, public law)
and GovInfo is used primarily for CREC/CHRG full-text leads + Statutes at Large.

---

## 5. Schema & rendering changes

New models in `models.py`:

- `Hearing(title, committee, chamber, date, citation, url)`
- `Statement(speaker, role, date, quote, context, source_url, source_type, verified)`
  - `role`: `sponsor | cosponsor | member | witness | other`
  - `source_type`: `CREC | hearing | press | news | other`
  - `verified: bool` — set true only after both grounding gates pass.

Extend `LegHistory`: add `hearings: list[Hearing] = []`, `statements: list[Statement] = []`,
`narrative: str | None = None`. Add `url` to the existing `Enactment` model (link to the public-law /
Statutes-at-Large document).

Renderer (`templates._leg_history`): add **Hearings**, **Statements** (grouped, attributed, linked to
source, with a ✓ marker when `verified`), and a **Legislative Journey** narrative subsection. Empty
subsections are dropped (existing pattern).

**Source links are first-class (user requirement).** The whole point of a leg-history page is that the
reader can click through and check the source themselves. Therefore **every rendered item links to its
primary source**, inline, right where the item appears:

- Text versions, committee reports → already linked; keep.
- **Floor / CREC consideration, votes (roll call), enactment (public law / Statutes) — currently NOT
  rendered as links; this phase fixes that.** `templates._leg_history` must surface `FloorAction.url`,
  `Vote.roll_call_url`, and the new `Enactment.url`.
- **Hearings** render as `**Hearing:** "title" — committee, date — [source](url)`.
- **Statements** render as `**Speaker** (role), date — "verbatim quote" — [source](source_url) ✓`
  (the ✓ only when `verified`). The link target is the exact page the quote was grounded against, so
  the reader's click lands on the verification evidence.

A statement or hearing that has no usable link does not render (and, per §7, does not persist) — the
absence of a checkable source is itself disqualifying.

**Persistence mechanism (D37).** `hearings` + `statements` are persisted to frontmatter under the
`leg_history` key; the spine fields and `narrative` are body-only / re-derived. Implementation
follows the existing `commentary_sources` special-case precedent in `wiki/schema.to_frontmatter`
(emit only the durable subset). Exact mechanism (frontmatter `leg_history: {hearings, statements}`
subset vs. promoting the two lists to top-level `Bill` fields) is finalized in the plan; the
**behavior** is fixed: hearings/statements survive a frontmatter-only reconstruction with their
`verified` status; spine + narrative do not (re-derived from APIs / re-run by the command — same
property `summary`/`actions` already have).

---

## 6. New / changed files

- `src/zwiadbrain/sources/govinfo.py` — `GovInfoSource` (httpx + tenacity, same shape as
  `CongressSource`). A **leg-history enricher**, *not* a discover/fetch `Source`.
- `.claude/agents/leg-history-researcher.md` — `tools: WebSearch, WebFetch, Read`; strict-JSON
  output contract `{hearings[], statements[], narrative}`; verbatim-quote + source-URL requirements.
- `.claude/agents/leg-history-verifier.md` — **different model**; `tools: WebFetch, Read`; per-statement
  `{index, verified, note}` contract; independence + no-benefit-of-the-doubt instructions.
- `.claude/commands/zwiad-leg-history.md` — slash command orchestrating the flow (mirrors
  `zwiad-backfill.md`): `fetch-leg-history` → read JSON → dispatch researcher → dispatch verifier →
  write staging → `render-leg-history` → `reindex` → report. Documents the staging-file contract.
- `src/zwiadbrain/cli.py` — `fetch-leg-history` and `render-leg-history` commands.
- `src/zwiadbrain/models.py`, `wiki/templates.py`, `wiki/schema.py` — schema + render + persistence.
- `src/zwiadbrain/config.py` — `GOVINFO_API_KEY` (likely the same `api.data.gov` key).
- `DECISIONS.md` — entries #34–#38.

---

## 7. Verification & grounding (the high-stakes core)

Attributed quotes are the highest-stakes output in the project; misattribution is worse than a missed
bill. Two **independent** gates, both required to persist a quote as `verified: true`:

1. **Deterministic gate** (Python, no LLM): `source_url` returns HTTP 200 **and** the quote appears
   as a whitespace-normalized substring of the fetched page text. Absence ⇒ not persisted.
2. **Cross-modal verifier** (subagent, different model from the researcher): independently re-fetches
   the source and confirms the quote + attribution.

A statement failing either gate is **dropped and logged** (no review-queue UI this phase). The
deterministic spine never touches an LLM, so its citations stay exact by construction.

---

## 8. Testing / UAT

**Offline (pytest + respx), no network, no LLM:**
- `GovInfoSource` maps fixture payloads to spine structures correctly; transient-retry / rate-limit
  behavior matches `CongressSource`.
- Spine assembly from a fixture enacted bill (versions, reports, votes, public law, Statutes).
- Grounding gate: quote present on fetched page ⇒ keep; quote absent or URL 404 ⇒ drop.
- `LegHistory` (with hearings + statements) round-trips through frontmatter; `verified` survives.
- Renderer output for hearings / statements / narrative; **byte-identical re-render** from identical
  staging input (clean `git status`).
- **Every rendered leg-history item carries a link to its source** — assert the renderer emits the
  URL for text versions, committee reports, **floor/CREC, votes (roll call), and enactment** (the
  three currently dropped), plus hearings and statements. A fixture `LegHistory` with URLs in every
  subsection → the rendered Markdown contains a `[...](url)` for each item.
- `fetch-leg-history` aborts cleanly on a non-enacted bill.

**Interactive UAT (live, regular plan):**
- `/zwiad-leg-history` on a **known enacted 118th in-scope bill** → inspect the rendered Legislative
  History: grounded + verified statements, hearings, narrative; eyeball attributions against cited
  sources; confirm a deliberately-unsourceable / misattributed quote is **dropped**.
- **Click-through check:** open the rendered page and confirm every leg-history item is a working
  link to its primary source (versions, reports, floor/CREC, votes, hearings, statements, enactment) —
  this is the user-facing acceptance test for "I can check the sources myself."

---

## 9. Scope boundaries (what PHASE-05 is NOT)

- **Federal only** — GovInfo is federal. State leg-history is out of scope.
- **On-demand only** — not wired into routine scan / Pass A (PHASE-06). PHASE-06 must learn to
  preserve persisted leg-history rather than clobber it on re-fetch (noted, not built here).
- **No review-queue UI** — statements that fail grounding are dropped + logged, not queued.
- **No state / enforcement leg-history.**

---

## 10. Deltas from PLAN.md

- PLAN.md PHASE-05 = "`sources/govinfo.py` + `llm/leg_history.py` (standardized section on
  enactment)." This spec **replaces `llm/leg_history.py`** (a Python Anthropic-SDK module) with
  Claude Code **subagents** (`leg-history-researcher` + `leg-history-verifier`) per the Phase-04
  architectural pivot. Python makes no LLM calls.
- PLAN.md called leg-history "the only candidate for cross-modal eval, if any." This spec **adopts**
  the cross-modal verifier (D36) — the reservation in decision 17 is now exercised.
- PLAN.md scoped leg-history narrowly (structured assembly, ~1 session). The user **broadened** it to
  include hearings + attributed statements + narrative + open-web research (D34/D35), making it a
  2–3 session phase.

---

## 11. Open items for the plan (not blockers)

- Exact GovInfo endpoints + per-bill linkage — resolved by the §4 spike before spine code is written.
- Final persistence mechanism (nested-subset vs. top-level lists) — §5; behavior is fixed.
- Researcher / verifier model assignment (must be different models for the cross-modal check) —
  defaulted in the plan; e.g. researcher = sonnet (heavy web work), verifier = opus (high-stakes check).
- Whether `fetch-leg-history` reuses the existing `data/runs/<id>/` run-id scheme or its own.
