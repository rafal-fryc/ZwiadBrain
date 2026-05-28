# PHASE-06 — Watchlist refresh (Pass A) + PHASE-05 leftovers

**Status:** design, awaiting implementation plan
**Author:** brainstormed 2026-05-28
**Supersedes / amends:** PLAN.md PHASE-06 (revised per D27, D38); partially supersedes D9 (see D39) and D37 (see D40)

## 1. Outcome

A self-updating federal bill tracker. The user can run `/zwiad-refresh` (interactive Claude Code, no API key) and have any bill whose Congress.gov `updateDate` has advanced since its last render re-fetched, re-classified, re-summarized, and re-rendered — without losing the expensive cross-modal-verified legislative-history research from PHASE-05. Bills whose classifier verdict flips IN→OUT remain on disk with `tracking: false` and an audit comment. Two PHASE-05 carryover items also ship: `Enactment.statutes_at_large` is populated from GovInfo, and the deterministic grounding gate switches from raw-HTML substring match to BeautifulSoup text extraction to lift recall on JS-rendered pages without sacrificing precision.

## 2. Architecture

Mirrors the backfill/leg-history pattern (D27): Python deterministic bookends, Claude Code subagents in the middle, JSON handoff under `data/runs/<id>/`. No Anthropic API key, no Agent SDK — interactive plan only.

```
                            /zwiad-refresh
                                 │
                                 ▼
   Step 1 (Python): zwiadbrain fetch-refreshable
     • read wiki/federal/bills/*.md frontmatter via Store
     • for each tracking=true bill: GET Congress.gov
       /bill/{c}/{t}/{n}   → compare updateDate /
       updateDateIncludingText against stored cursors
     • emit refreshable.json:
         [{ bill_id, prev: {…cursors, summary_hash,
                  amendments_count, leg_history:{hearings,
                  statements, narrative}},
            fresh: <fully re-fetched Bill> }]
                                 │
                                 ▼
   Step 2 (subagents, dispatched by the slash command):
     classifier   if updateDateIncludingText advanced
                  OR summary_hash changed
     summarizer   if updateDateIncludingText advanced
                  OR summary_hash changed
     amendment-
       explainer  for each amendment whose id is new
                  OR latest_action_date advanced
     → writes refreshed.json with subagent outputs
                                 │
                                 ▼
   Step 3 (Python): zwiadbrain render-refreshed
     • merge subagent outputs onto fresh Bill
     • re-attach PRESERVED prev.leg_history.{hearings,
       statements, narrative} (D38 + D40)
     • if classifier flipped to out-of-scope:
         set bill.tracking=False;
         append audit marker; do NOT delete page
     • render + reindex
     • report: refreshed N / unchanged M / flipped-out K
```

**Module placement:** Pass A's pure logic lives in a new `src/zwiadbrain/pipeline/refresh.py`, sibling to `discover.py`, `enrich.py`, and `leg_history.py`. The slash command lives at `.claude/commands/zwiad-refresh.md`.

No new `Source` method is required for Pass A — `CongressSource.fetch()` already returns a fully mapped `Bill` (it only needs to start mapping two additional date fields).

## 3. Trigger logic and cursor state

Congress.gov exposes two update dates:
- `updateDate` — bumps on any bill change (status, action, amendment, summary)
- `updateDateIncludingText` — bumps only when bill text or CRS summary changes

**Per-bill cursors persisted to frontmatter:**

| Field | Source | Used by |
|---|---|---|
| `update_date` | Congress `updateDate` | refreshable detection |
| `update_date_text` | Congress `updateDateIncludingText` | classifier + summarizer trigger |
| `summary_hash` | `sha256(whitespace_normalize(crs_summary_text))` after enrich | summarizer + classifier trigger (belt + suspenders; the text date is known coarse) |
| `amendments_count` | `len(bill.amendments)` after enrich | amendment-explainer trigger |

**Per-amendment cursor:** each amendment in frontmatter gains `latest_action_date` (mapped from Congress's `latestAction.actionDate`). The explainer is dispatched only on amendments whose id is new or whose date advanced — not on every amendment for the whole bill.

**Trigger matrix:**

| Condition | Action |
|---|---|
| `update_date` unchanged | skip — not refreshable |
| `update_date` advanced AND text-date unchanged AND amendments unchanged | re-render only (status timeline drift); no subagent |
| `update_date_text` advanced OR `summary_hash` changed | dispatch **classifier** + **summarizer** |
| `amendments_count` grew, OR any amendment's `latest_action_date` advanced | dispatch **amendment-explainer** on those amendments only |

`/zwiad-refresh` defaults to refreshing all `tracking=true` federal bills; `--bill <id>` refreshes one.

## 4. D38 preservation rule (the trust boundary)

Expensive cross-modal-verified outputs from PHASE-05 must not be clobbered by routine refresh. The narrow rule:

**Preserved across a refresh** (re-attached from `prev` onto the fresh Bill):
- `leg_history.hearings` (entire list, `verified` flag intact)
- `leg_history.statements` (entire list, `verified` flag intact)
- `leg_history.narrative` *(new — see D40 below; supersedes the body-only portion of D37 for narrative)*

**Re-derived from the fresh fetch** (NOT preserved):
- `leg_history.versions`, `committee_reports`, `votes`, `floor_consideration`, `enactment` — spine; cheap to re-derive from Congress + GovInfo (`assemble_spine`)
- `bill.topics`, `bill.summary`, `bill.amendments[*].what_changed` — these are subagent outputs that the refresh deliberately re-runs

A routine refresh **does not** dispatch the leg-history researcher or verifier — those are reserved for `/zwiad-leg-history`. Refresh's only job for leg-history is to keep the prev-rendered research alive across a spine re-derive.

**Implementation seam** (`pipeline/refresh.py`):
```python
def preserve_leg_history(prev: LegHistory | None,
                         fresh_spine: LegHistory) -> LegHistory:
    """Re-attach prev's hearings/statements/narrative onto a freshly assembled spine."""
    if prev is None:
        return fresh_spine
    return fresh_spine.model_copy(update={
        "hearings": prev.hearings,
        "statements": prev.statements,
        "narrative": prev.narrative,
    })
```

Frontmatter round-trip (`wiki/schema.py`) extends the PHASE-05 T4 special-case: `leg_history` in frontmatter is `{hearings, statements, narrative}`.

## 5. Out-of-scope flip handling

When the classifier returns `in_scope: false` for a bill whose frontmatter has `tracking: true`:

1. `bill.tracking` is set to `False`.
2. The page's existing `topics` are **kept** (the record of the prior classification stands), not zeroed.
3. The page is re-rendered to the same path with an audit marker prepended to the body:
   ```
   <!-- zwiadbrain:flipped-out date=2026-06-04 reason="classifier: bill now centers on telehealth reimbursement; AI-decision-tool clause struck in HASC markup" -->
   ```
   The classifier's `rationale` (already part of the subagent's JSON output) becomes the audit reason. The marker is in the body so `git log -p` surfaces it and a fresh clone retains it.
4. Future `/zwiad-refresh` runs skip the page (no `tracking: true`).
5. Future `/zwiad-backfill --force <id>` could re-track it; that flag is out of scope for this phase.

OUT→OUT and IN→IN refreshes are normal re-renders. OUT→IN is unreachable here (a `tracking: false` bill is never put into `refreshable.json`).

**Reporting:**
```
refresh complete: 4 refreshed / 1 flipped-out / 17 unchanged
  flipped-out: 118/hr/4521 — "classifier: telehealth reimbursement, AI clause struck"
```

## 6. PHASE-05 leftovers (separable tasks at the end of the phase)

These do not interleave with Pass A code paths and are sized 1–2 hours each.

### L1 — `Enactment.statutes_at_large` population

PHASE-05 left this field declared but unpopulated (M1). The GovInfo path was identified by the T1 spike but not wired through.

- Extend `GovInfoSource` with `fetch_statutes_at_large(plaw_package_id: str) -> StatutesAtLarge | None`. Implementation: `GET /related/{plawPackageId}/STATUTE`; if the related list is empty, return `None` (fail-quiet — some PLAW packages do not yet have a STATUTE row published). Map the row to `StatutesAtLarge(volume, page, citation, url)` where `url` is the human `app/details/<granuleId>` link.
- `assemble_spine` (`pipeline/leg_history.py`) calls `fetch_statutes_at_large` after `enactment.public_law_url` is resolved and attaches the result.
- `wiki/templates.py._leg_history` renders the STAL citation as a link in the Enactment section. The item does not render if URL-less (per existing rule: an item with no link does not render).

### L2 — Grounding-gate recall lift

PHASE-05's deterministic grounding gate over-rejects on JS-rendered `.senate.gov` press-release pages and whitespace-quirky CREC pages. Precision is fine (zero misattribution observed in PHASE-05 UAT); recall is too tight.

- In `pipeline/leg_history.py`, replace the current "fetch raw HTML, normalized substring match" with: parse with BeautifulSoup → `get_text(separator=' ')` → whitespace-collapse → quote-window substring match (the existing normalization, applied to extracted text instead of raw HTML).
- HTTP 200 gate and verifier verdict are unchanged. ≥20-char length floor unchanged.
- `beautifulsoup4` is added to runtime deps in `pyproject.toml`.
- A code comment documents the division of labor: deterministic gate checks quote presence only; speaker attribution is the verifier subagent's job. A misattributed-but-present quote is therefore kept by the gate and dropped by the verifier — by design.

## 7. File map

**Created**

```
src/zwiadbrain/pipeline/refresh.py     — pure functions: detect_refreshable,
                                          preserve_leg_history, apply_classifier_flip,
                                          summary_hash, amendment_delta
.claude/commands/zwiad-refresh.md      — slash command orchestration
tests/test_refresh.py                  — unit tests for the pure functions above
```

**Modified**

| File | Change |
|---|---|
| `src/zwiadbrain/models.py` | `Amendment` gains `latest_action_date`. `Bill` gains `update_date`, `update_date_text`, `summary_hash`, `amendments_count` (computed from amendments at enrich time). `LegHistory.narrative` already exists from PHASE-05; no model change needed — its persistence is added via `schema.py` (next row). |
| `src/zwiadbrain/wiki/schema.py` | `to_frontmatter` emits new cursor fields + `leg_history.narrative`; `from_page` round-trips them. |
| `src/zwiadbrain/sources/congress.py` | `fetch` maps `updateDate` → `update_date`, `updateDateIncludingText` → `update_date_text`; per-amendment `latestAction.actionDate` → `latest_action_date`. |
| `src/zwiadbrain/sources/govinfo.py` | New: `fetch_statutes_at_large(plaw_package_id) -> StatutesAtLarge \| None` (L1). |
| `src/zwiadbrain/pipeline/enrich.py` | Compute `summary_hash` from CRS summary text post-fetch; set `amendments_count`. |
| `src/zwiadbrain/pipeline/leg_history.py` | `assemble_spine` calls `fetch_statutes_at_large` (L1); `ground_items` uses BeautifulSoup text-extract (L2). |
| `src/zwiadbrain/wiki/templates.py` | Renderer emits Statutes-at-Large link in Enactment section; flipped-out audit comment marker before body. |
| `src/zwiadbrain/cli.py` | New: `fetch-refreshable`, `render-refreshed`. |
| `pyproject.toml` | Add `beautifulsoup4` to runtime deps if not already present; bump version to `0.6.0`. |
| `src/zwiadbrain/__init__.py` | Bump `__version__` to `0.6.0`. |
| `DECISIONS.md` | Append D39 (re-classify on refresh, overriding D9 for routine refresh), D40 (narrative also persists, supersedes the body-only portion of D37). |

## 8. Test plan (all offline, respx-mocked)

- `test_refresh.py`:
  - `detect_refreshable`: prev unchanged → empty; `update_date` advanced → present; text-date advanced → flagged for classifier+summarizer; amendments grew → flagged for explainer; combinations.
  - `preserve_leg_history`: `prev=None` → spine returned as-is; `prev` present → hearings/statements/narrative re-attached; spine fields (versions, votes, etc.) come from `fresh`, not `prev`.
  - `apply_classifier_flip`: IN→IN no-op; IN→OUT sets `tracking=false` + audit marker; OUT→IN unsupported (raises; out of scope for this phase); OUT input rejected upfront.
  - `summary_hash`: stable for identical text; differs for any single-character change; whitespace-normalized.
  - `amendment_delta`: new amendments returned; advanced `latest_action_date` returned; unchanged not returned.
- `test_models.py`: round-trip of new cursor fields and per-amendment `latest_action_date`.
- `test_schema.py`: `to_frontmatter`/`from_page` round-trip new fields + `leg_history.narrative`.
- `test_congress.py`: fixture maps both update-dates and per-amendment dates.
- `test_govinfo.py`: `fetch_statutes_at_large` happy path + empty-related fail-quiet (L1).
- `test_leg_history.py`: `ground_items` accepts a JS-rendered fixture currently rejected; still rejects genuinely-absent quotes (L2).
- `test_render.py`: Statutes-at-Large link emits when present (L1); flipped-out audit marker emits when bill flips out.
- `test_cli.py`: `fetch-refreshable` writes correct `refreshable.json` for a fixture wiki with three bills (one unchanged, one text-changed, one amendments-changed); `render-refreshed` applies preservation + flip-out + reindex correctly.
- `test_agents.py`: `.claude/commands/zwiad-refresh.md` frontmatter parses; referenced subagent names exist.

## 9. UAT (interactive, on regular plan)

- **Pass A baseline:** `/zwiad-refresh` on the existing committed federal bills (currently 118/hr/2670) → confirm `unchanged` because the page is fresh from PHASE-05.
- **Pass A live refresh:** backfill a second, deliberately-stale bill (one whose Congress update-date we know advanced since the local copy was rendered) → re-run `/zwiad-refresh` → confirm one bill refreshes, subagent dispatch only on the changed bill, persisted leg-history (hearings/statements/narrative) survives.
- **L1 UAT:** re-run `/zwiad-leg-history 118/hr/2670` → STAL link appears in the Enactment section.
- **L2 UAT:** re-run `/zwiad-leg-history` on a bill whose `.senate.gov` press-release statement was dropped in PHASE-05 → confirm it now grounds + verifies.

## 10. Tasks (high-level — will become TDD steps in the implementation plan)

| # | Task |
|---|---|
| T1 | `models.py` — add cursor fields to `Bill` + `Amendment` |
| T2 | `wiki/schema.py` — round-trip new fields + `leg_history.narrative` |
| T3 | `sources/congress.py` — map new dates from `fetch` |
| T4 | `pipeline/enrich.py` — compute `summary_hash` + `amendments_count` |
| T5 | `pipeline/refresh.py` — pure detection + preservation + flip functions |
| T6 | cli — `fetch-refreshable` command |
| T7 | cli — `render-refreshed` command |
| T8 | `.claude/commands/zwiad-refresh.md` — slash command |
| T9 | `wiki/templates.py` — flipped-out audit comment marker |
| L1 | GovInfo Statutes-at-Large + spine assembly + render |
| L2 | Grounding gate BeautifulSoup text-extract |
| T10 | `DECISIONS.md` — D39, D40 |
| T11 | Quality gate + version `0.6.0` + tag `v0.6.0` |
| T12 | Interactive UAT (Pass A + L1 + L2) |

## 11. Decisions logged this phase

### D39 — Watchlist refresh re-classifies every text-changed bill, overriding D9 for routine refresh
**Chosen:** `/zwiad-refresh` dispatches the classifier on every bill whose `updateDateIncludingText` advanced or whose `summary_hash` changed, even if the bill was previously classified IN-scope and its identifiers haven't changed. Overrides D9 ("decided pages trusted until their identifiers change") for the routine-refresh path. Initial classification (`/zwiad-backfill`) still follows D9.
**Alternatives:** (a) Trust the prior classification; re-run only summarizer + amendment-explainer; (b) Hold proposed flips in a review queue.
**Why:** User decision — wants prose freshness (summary + amendments) AND scope freshness (topics) to track together. Avoids the failure mode where a bill silently drifts out of scope (e.g. AI clause struck in markup) and the wiki keeps tracking + summarizing it as if it were still in scope.
**Trade-offs:** One extra subagent call per text-changed bill; possible flap if the classifier is noisy on borderline bills. Mitigated by the OUT→stay-with-`tracking=false` rule (the page is never deleted; flipping back IN requires explicit `/zwiad-backfill --force`).
**Revisit if:** Flap is observed (a bill toggles IN/OUT across runs without substantive change) — then narrow to summarizer + explainer per the alternative above, or add the review-queue gate.

### D40 — `LegHistory.narrative` persists to frontmatter alongside hearings/statements
**Chosen:** Extend D37's special-case: page frontmatter's `leg_history` block carries `{hearings, statements, narrative}` (D37 was `{hearings, statements}` only). Spine fields (versions, committee_reports, votes, floor_consideration, enactment) remain body-only / re-derived per D37.
**Alternatives:** Leave D37 as-is; a routine refresh strips the narrative; user re-runs `/zwiad-leg-history` to regenerate.
**Why:** The narrative is the same kind of expensive, non-deterministic, model-generated output as the verified statements — losing it on routine refresh would silently degrade the most-read part of the leg-history section. Surviving in frontmatter is the same property `hearings`/`statements` already have.
**Trade-offs:** Slightly longer YAML (the narrative is prose, not a structured list). Splits `LegHistory` persistence further: structured research + narrative in frontmatter; spine body-only.
**Revisit if:** Narrative prose in YAML proves unwieldy — then encode it as a path reference to a sidecar file and keep the frontmatter slim.

## 12. Open follow-ups (out of scope for this phase, named for future work)

- `/zwiad-backfill --force <id>` — explicit re-tracking of a flipped-out bill. Out of scope here; named so D39's "explicit re-track" requirement has a concrete future home.
- State (LegiScan) Pass A. Stays in PHASE-07.
- Enforcement (FTC + state AG) refresh. Awaits PHASE-08 ship.
- A scheduled trigger for `/zwiad-refresh`. PHASE-10 territory (or in-session `/loop`, per D27's note about PHASE-10 being re-planned as in-session scheduling).
- A standalone `/zwiad-refresh-llm` that re-runs only the LLM subagents on an already-tracked bill without re-fetching. Currently subsumed by `/zwiad-refresh`; named here in case the manual case appears.
