# PHASE-09 — Law-brain Commentary (design)

> Status: design approved 2026-05-29. Supersedes the pre-pivot PHASE-09 design in
> `docs/PLAN.md` ("Law-brain integration subsystem"), which assumed a
> `pipeline/run.py` loop + Anthropic SDK. The locked *behavioral* decisions
> (D2–D11, D14, D16) survive; the *architecture* is re-cast onto the post-pivot
> slash-command/subagent model (D26/D27/D30), mirroring `/zwiad-scan-enforcement`.

## 1. Goal

Attach the sibling **law brain** (`C:\Users\rafst\Documents\projectas\Brains\law`,
read-only) as a **commentary overlay** onto items ZwiadBrain *already tracks*. A
matched law-brain page is copied verbatim (with two minimal transforms) into a
`## Commentary & Analysis` section on the tracked bill/enforcement page, with
provenance markers and a content-hash staleness cursor. Matching is deterministic
key-extraction first, an LLM fallback second, and every LLM link is gated by a
deterministic shared-key grounding confirm. The same match also harvests the law
brain's collected **reference links** (law-firm client alerts, IAPP, natlawreview, …)
— from the matched page and the `sources/zwiad` memos it references — into a dedicated
`## Further Reading (via law brain)` section.

**This phase is commentary-only.** It does NOT mint new tracked stubs from the law
brain — that is the gated PHASE-11 discovery path (D14, `discover=false`).

## 2. Context: most of the machinery already exists

PHASE-02 pre-wired the persistence/render/config/store layer for commentary. The
following already exist and MUST NOT be rebuilt:

| Layer | What exists | File |
|---|---|---|
| Model | `CommentarySource{path, slug, updated, content_hash, matched_by, confidence, body}` + `WikiItem.commentary_sources` | `models.py:36,184` |
| Frontmatter | `to_frontmatter` persists commentary bookkeeping, strips the verbatim `body` (D20) | `schema.py:82` |
| Render | `_demote_headings` (##→###), `_commentary_block` (markers + attribution), `## Commentary & Analysis` on **both** Bill and EnforcementAction | `templates.py:48,239,283,317` |
| Config | `LawBrainSettings` (enabled, path, min_confidence=0.75, require_shared_key, demote_headings, commentary, discover, commentary_only_types, commentary_only_slug_markers, type_map) + `Settings.lawbrain` + `effective_law_brain_path` + `LAW_BRAIN_PATH` env | `config.py:85,117,120` |
| Store | `lawbrain_pages(slug PK, content_hash, updated, last_seen)` + `upsert_lawbrain_page` + `lawbrain_hashes()` | `store.py:46,228,243` |
| Exceptions | `LawBrainError`, `MatchError` | `exceptions.py:45,49` |

So PHASE-09 builds **only the gap**: the reader, the matching pipeline, the copy
orchestration, the registry, the subagent, and the command wiring.

## 3. The law-brain corpus (verified against the real wiki)

154 pages: 58 `concept`, 56 `regulation`, 19 `case`, 9 `guidance`, 8 `incident`,
3 `framework`, 1 `vendor`. Page schema (`Brains/law/CLAUDE.md`): YAML frontmatter
(`title, type, jurisdiction[], tags[], created, updated, sources[], status,
citation`) + body sections (`## Summary`, `## Key points`, `## Citations`,
`## Cross-references` with `[[wiki-slug]]` links, `## Recent developments`,
`## Open questions`). File naming `wiki/<type>-<kebab-slug>.md`.

**Jurisdiction format differs between the two wikis** and must be normalized:
law-brain uses `US-Federal`, `US-CA`, `US-AL`, …; ZwiadBrain uses `US` (federal)
and `US-XX` (state, exactly 5 chars). Normalization: law-brain `US-Federal` →
ZwiadBrain `US`; law-brain `US-XX` ↔ ZwiadBrain `US-XX`.

**ZwiadBrain currently tracks 6 items**: `118-hr-2670`, `ca-2025-ab-1064`,
`ca-2025-ab-1337`, `ca-2025-sb-53`, `ftc-2026-cox-media-group`,
`ftc-2026-nudify-tool-operators`. Verified matches in the real data:
- `regulation-california-sb53-tfaia` → `ca-2025-sb-53` via `US-CA::bill::SB-53`
  (clean deterministic match — the showcase).
- `regulation-take-it-down-act` relates to `ftc-2026-nudify-tool-operators`
  (cross-type; attaches iff a shared `public_law`/docket key exists, else review).
- `concept-california-ai-regulatory-landscape`, `concept-state-ai-chatbot-tracker`,
  `concept-federal-ai-legislation-tracker` reference the CA bills but are
  multi-subject trackers → **fail-closed, excluded** (decision 4 below).

## 4. Decisions taken in this design session

1. **Scope = full locked commentary path.** Reader + deterministic keys + LLM
   `lawbrain-matcher` + deterministic grounding confirm + verbatim copy + staleness
   + `links.yaml` registry + review queue + slash command. Honors D4/D16; builds
   the review-queue machinery D39 already references. (Logged D57.)
2. **Copy = full body, syntax-neutralized.** The whole law-brain page body is
   copied verbatim with two render-time transforms: demote `##`→`###` (D6) and
   neutralize dead `[[wiki-slug]]` cross-reference links to plain text. All sections
   retained. (Logged D58, refines D2/D6.)
3. **Attach on shared key regardless of ZwiadBrain page kind.** Commentary attaches
   to whichever tracked item shares a jurisdiction-qualified key; `type_map` (D8)
   governs only PHASE-11 stub-minting, not PHASE-09 attachment. A law-brain
   regulation page about a statute can attach to a ZwiadBrain enforcement page that
   enforces it. (Logged D59.)
4. **Multi-subject pages fail closed.** Pages whose slug carries a marker in
   `commentary_only_slug_markers` (tracker, landscape, map, scholarship) emit zero
   keys and are excluded from commentary — they neither mint nor attach. They have
   no single subject; copying a long multi-subject body onto one bill is off-topic.
   Single-subject `concept`/`regulation`/`case`/… pages attach normally. (Logged
   D60, refines D7.)
5. **Review-resolution folded into the render half.** No separate `review --commit`
   command; the render half writes new proposals AND applies operator-resolved
   (`[accept]`/`[reject]`) queue entries in one pass. (Logged D61.)
6. **Harvest law-brain reference links into a `## Further Reading (via law brain)`
   section.** A matched law-brain page's `sources:` frontmatter points at
   `sources/zwiad/*.md` memo files that are rich with **law-firm / secondary
   commentary links** (Mayer Brown, Crowell, Troutman, Morgan Lewis, Sidley, Wilson
   Sonsini, Perkins Coie, Ropes & Gray, Akin Gump, JD Supra, IAPP, natlawreview, …) —
   links the verbatim body-copy does NOT capture (they live in the memos, not the
   page body). Deterministically harvest `[text](url)` links from the matched page
   body + its referenced `.md` memos, **exclude primary-source domains** (`*.gov`,
   `legiscan.com`, `courtlistener.com`, `wikipedia.org`, `*.europa.eu`,
   `legislation.gov.uk` — ZwiadBrain already carries authoritative primary sources),
   dedup, and render the remainder in a dedicated `## Further Reading (via law brain)`
   section. (Logged D62.)
7. **Commentary + Further Reading survive non-sync re-renders via text-level marker
   preservation.** Their `body`/links stay OUT of frontmatter (honors D20); instead,
   `/zwiad-refresh` and any other re-render of a tracked page carry the committed
   law-brain region forward **verbatim** (marker-delimited), the body-level analog of
   `preserve_leg_history`. `/zwiad-sync-lawbrain` is the **sole** creator/updater/
   remover of that region. Closes a real data-loss gap: `render-refreshed` currently
   re-renders the freshly-fetched bill (empty `commentary_sources`) and would strip
   committed commentary. (Logged D63.)

## 5. Architecture

One sound shape, fully determined by D26/D27 + the existing scaffolding. Mirrors
`/zwiad-scan-enforcement` exactly: a deterministic Python fetch half, an
interactive subagent for the LLM fallback only, a deterministic Python render half,
exchanging gitignored JSON under `data/runs/<id>/`.

```
/zwiad-sync-lawbrain  (interactive Claude Code session)
  │
  ├─ fetch-lawbrain-candidates (Python, deterministic)
  │     read law brain (no-op if unavailable) → parse pages → extract keys →
  │     load tracked items from the index → deterministic set-intersection match →
  │     consult links.yaml (skip decided-unchanged, D9) → for keyless single-subject
  │     pages build a shortlist → write lawbrain-candidates.json + targets.json
  │
  ├─ lawbrain-matcher subagent (interactive; ONLY for keyless pages w/ shortlist)
  │     → {decision: link|not_in_scope, target_id, confidence, rationale}
  │
  └─ render-lawbrain-commentary (Python, deterministic)
        confirm_match grounds every LLM link (require ≥1 shared key, D16) →
        copy verbatim + idempotent merge into target.commentary_sources →
        write/resolve review-queue.md → record links.yaml → reindex
```

`--dry-run` runs fetch + match + prints intended writes with zero edits. The command
**never auto-commits** (D26 review-before-commit). `is_available()` makes the whole
command a clean no-op when `LAW_BRAIN_PATH` is missing or `lawbrain.enabled=false`.

### 5.1 Reader — `sources/lawbrain.py` (read-only; NOT a `Source`)
A `LawBrainPage{slug, type, jurisdiction: list[str], tags: list[str], title,
citation: str|None, updated: date|None, body: str, content_hash: str,
source_files: list[str]}`.
- Enumerate `effective_law_brain_path/wiki/<type>-*.md`; ignore anything without a
  recognized `<type>-` prefix and the root `index.md`/`log.md`/`CLAUDE.md`/`DECISIONS.md`.
- Parse with `python-frontmatter`; tolerate scalar-or-list `jurisdiction`,
  missing/unquoted `citation`, duplicate/missing `updated`. `source_files` = the
  `sources:` frontmatter list (paths relative to the law-brain root).
- `content_hash` = sha256 of the **whole file**, EOL-normalized to `\n` (D5). The
  `updated` date is display/attribution only, never trusted for diffing.
- `read_source_memo(rel_path) -> str | None` resolves a `source_files` entry against
  the law-brain root and returns the `.md` memo text (None for missing files or
  non-`.md` sources like PDFs). Used only by the link harvester (§5.9); read-only.
- `is_available()` → bool; a missing path makes the stage a no-op.

### 5.2 Keys — `pipeline/lawbrain_keys.py` (pure)
Extract jurisdiction-qualified keys from slug → title → citation → tags, and map
tracked items into the **same** key space; match = set intersection.
- **Bills:** regex `AB|SB|HB|HR|H.R.|S|HJRes|SJRes|…` + digits → `{PREFIX}-{int}`
  (+ zero-padded alias); jurisdiction-qualified → `US-CA::bill::SB-53`,
  `US::bill::HR-8818` (after `US-Federal`→`US` normalization).
- **Dockets:** reuse `ids.parse_strong_key` → `docket::2-25-cv-12295`.
- **Public law:** `Pub. L. 119-12` → `public_law::119-12` (tie-breaker; the
  cross-type bridge for statute↔enforcement matches).
- **Tracked-item mapping:** a `Bill` → `{juris}::bill::{TYPE}-{number}` from
  `bill_number`; an `EnforcementAction` → `docket::{docket}` and/or
  `public_law::{statute}` from `docket`/`statutes`.
- **Fail closed (two mechanisms):** (a) a page whose slug matches a
  `commentary_only_slug_markers` entry (tracker/landscape/map/scholarship) is
  force-excluded — it emits **zero keys** and never attaches (decision 4); (b) key
  extraction is hardened so an academic citation (`103 Calif. L. Rev. 513 (2015)`)
  or a "Multi-state tracker…" title is never misread as a bill/docket — such pages
  emit zero keys naturally and fall to the LLM fallback, which returns
  `not_in_scope` absent a shared key. Both paths attach nothing.
- **Outcomes:** exactly 1 shared key → `link` (conf 1.0, `matched_by="deterministic"`);
  >1 (collision) → review-queue; 0 → LLM fallback (if eligible).

### 5.3 Matcher + grounding — `pipeline/lawbrain_match.py` (pure; mirrors `enforcement.py`)
- `build_shortlist(page, tracked_items)` → candidate tracked items sharing
  jurisdiction (and, where available, a tag/topic overlap); never the full corpus.
- The `lawbrain-matcher` subagent proposes `{decision, target_id, confidence}` for a
  keyless page over its shortlist.
- `confirm_match(page, target_id, confidence)` (deterministic, D16): require
  `confidence ≥ min_confidence` (0.75) **and** (`require_shared_key` ⇒) the proposed
  target shares ≥1 jurisdiction-qualified key with the page, OR an operator override
  recorded in `links.yaml`. Pass → apply; fail → review-queue (`weak-grounding`).
- **Honest consequence:** because confirm requires a shared identifier, a purely
  *topical* LLM match (no shared key) never auto-applies — it routes to review. At
  the current 6-item corpus the LLM path is mostly dormant (collision-resolution +
  review-candidate generation); the deterministic key path is what attaches
  commentary now. Value compounds as the tracked corpus grows.

### 5.4 Copy + staleness — `pipeline/lawbrain_copy.py` (pure) + render half (I/O)
- Build a `CommentarySource` from a matched page: `body` = the **raw** law-brain
  markdown body (verbatim); transforms (`_demote_headings` + new
  `_neutralize_wikilinks`) are applied at **render time** in `_commentary_block`, so
  the stored body stays faithful and `content_hash` stays tied to the source bytes.
- Idempotent merge into `target.commentary_sources`: same slug + unchanged
  `content_hash` → no-op; changed hash → replace that block only; new slug → append.
  The renderer slug-sorts, so unchanged inputs → byte-identical render → clean
  `git status` (D20). Compare-then-write.
- **Staleness:** source page deleted from the law brain → keep the existing block,
  emit a `stale` review note (never silently delete analysis).

### 5.5 Registry — `pipeline/lawbrain_registry.py` → `wiki/links.yaml` (committed, permanent)
Entries `{lawbrain_slug, decision: link|not_in_scope|reject, target_id, matched_by,
keys_hash, decided}`. The fetch half consults `decision_for(slug)` before building
candidates and skips a decided page unless its freshly-extracted key-set differs
from the recorded `keys_hash` (D9). This keeps the subagent from re-judging settled
pages every run and records the operator overrides D16 relies on.

### 5.6 Review queue — `wiki/review-queue.md` (committed, transient)
One `[pending]` entry per uncertain proposal: low-confidence, key collision, LLM
`weak-grounding`, or `stale`. The operator flips `[pending]`→`[accept]`/`[reject]`.
The render half (D61) reads resolved tokens, applies `[accept]` (copy + write
`links.yaml`), records `[reject]`, and prunes resolved entries — one code path for
new and resolved proposals.

### 5.7 Subagent — `.claude/agents/lawbrain-matcher.md`
`tools: Read`, `model: sonnet` (mirrors `enforcement-matcher`). Input: the page's
`slug/title/type/jurisdiction/tags/citation` + its `## Summary` + a shortlist of
`{id, title, type, jurisdiction, keys}`. Output: a single JSON object
`{decision: "link"|"not_in_scope", target_id, confidence, rationale}`. Conservative:
when unsure, `not_in_scope` — a deterministic confirm re-checks any `link`.

### 5.8 CLI + command
- `fetch-lawbrain-candidates [--dry-run]` and `render-lawbrain-commentary --in <path>
  [--dry-run]` in `cli.py` (reuse `staging.py` `stage_json`/`validate_model`).
- `.claude/commands/zwiad-sync-lawbrain.md` orchestrates fetch → read → matcher
  (keyless only) → render → report. Keeps `ANTHROPIC_API_KEY` unset (D26).

### 5.9 Reference links — `pipeline/lawbrain_links.py` (pure) — decision 6
- `CommentaryLink{text: str, url: str}` (a small model). `CommentarySource` gains
  `links: list[CommentaryLink] = []`, treated body-only exactly like `body` —
  excluded from frontmatter (`exclude={"body", "links"}` in `to_frontmatter`),
  carried in-memory during sync render only.
- `harvest_links(page, memo_texts, primary_source_domains) -> list[CommentaryLink]`:
  - Extract markdown links `\[([^\]]+)\]\((https?://[^)]+)\)` from the matched
    page body AND each referenced `.md` memo (`read_source_memo`); also capture bare
    `https?://…` URLs not already in a markdown link (anchor text = the URL's host).
  - **Filter out primary-source domains** (host ends with any configured suffix:
    `.gov`, `legiscan.com`, `courtlistener.com`, `wikipedia.org`, `europa.eu`,
    `legislation.gov.uk`) — ZwiadBrain already carries authoritative primary sources.
  - Dedup by normalized URL (lowercase host, strip trailing `/`); stable sort by
    `(host, url)` for byte-identical render (D20). No cap (dedup is the noise control).
- Fully deterministic and offline — no LLM, no network.

### 5.10 Further Reading render + region preservation — decision 7
- **New render helper `_neutralize_wikilinks`** (`templates.py`, beside
  `_demote_headings`): `[[regulation-foo]]` → `regulation-foo`. Applied in
  `_commentary_block` so dead law-brain cross-refs render as plain text (decision 2).
- **Further Reading section** rendered after `## Commentary & Analysis`, aggregating
  `commentary_sources[].links` (deduped across sources): `## Further Reading (via law
  brain)` → `- [anchor text](url)` bullets. Omitted entirely when there are no links.
- **Region markers for preservation.** The whole law-brain-contributed region (the
  commentary blocks + Further Reading) is wrapped in an outer marker pair
  `<!-- lawbrain:region:begin -->` … `<!-- lawbrain:region:end -->`. (The per-slug
  `lawbrain:begin/end slug=` markers remain inside it.)
- **`preserve_lawbrain_region(prev_page_text, fresh_body) -> str`** (pure): if
  `prev_page_text` contains a `lawbrain:region` block, splice it verbatim onto
  `fresh_body` (which a non-sync render produces WITHOUT the region, since the
  freshly-fetched model has empty `commentary_sources`). The `render-refreshed` and
  `render-classified` CLI paths call this so a refresh/backfill re-render never
  strips committed commentary/Further Reading. Byte-identical because the region is
  copied exactly (D20 holds; deterministic). `/zwiad-sync-lawbrain` alone rebuilds the
  region from the law brain (create/update/remove), via compare-then-write.

## 6. Config / TOML

`LawBrainSettings` exists; populate the `[lawbrain]` block in `zwiadbrain.toml`:
`enabled=true`, `path`/`LAW_BRAIN_PATH`, `min_confidence=0.75`,
`require_shared_key=true`, `demote_headings=true`, `commentary=true`,
`discover=false`,
`commentary_only_slug_markers=["tracker","landscape","map","scholarship"]`
(**load-bearing now** — the PHASE-09 exclusion list),
`commentary_only_types=["concept","framework","vendor","person","matter"]` and
`type_map={statute:"bill", regulation:"bill", case:"enforcement",
guidance:"enforcement", incident:"enforcement", enforcement:"enforcement"}`
(populated for PHASE-11; not used for attachment per decision 3). Add
`LAW_BRAIN_PATH` to `.env.example`.

Two new `LawBrainSettings` fields for decision 6: `further_reading: bool = True`
(toggle the `## Further Reading` section) and `primary_source_domains: list[str]`
(the harvest denylist, default `[".gov", "legiscan.com", "courtlistener.com",
"wikipedia.org", "europa.eu", "legislation.gov.uk"]`). Both surfaced in the
`[lawbrain]` TOML block.

## 7. Testing (fully offline — the strength of this phase)

The law brain is local files, so every deterministic module is offline-unit-tested
against a `tests/fixtures/lawbrain/` mini-wiki (no mocked HTTP). Mirrors the
test-heavy phases 01/02/06.

- **`test_lawbrain_reader.py`** — enumerate + skip non-pages; tolerant parse
  (scalar/list jurisdiction, missing citation, duplicate updated); `content_hash`
  stable + EOL-normalized; `is_available()` no-op on missing path.
- **`test_lawbrain_keys.py`** — `SB 53`→`US-CA::bill::SB-53` (+padded alias);
  `H.R. 8818`→`US::bill::HR-8818` (US-Federal normalization); docket; `Pub. L. 119-12`
  →`public_law::119-12`; scholarship/landscape/tracker-slug → **zero keys**;
  collision → `review`; tracked-item mapping for Bill + EnforcementAction.
- **`test_lawbrain_match.py`** — shortlist build (jurisdiction-scoped, never full
  corpus); `confirm_match`: link+shared-key→apply, link+no-key→review
  (`weak-grounding`), target-not-in-shortlist→review, conf<0.75→review; cross-type
  match via `public_law` key→apply (decision 3); operator override→apply.
- **`test_commentary_copy.py`** — first apply adds `CommentarySource` + renders block
  with markers/attribution/demoted-headings/neutralized-links; **re-run identical →
  byte-identical file, zero writes**; multi-source → slug-sorted blocks.
- **`test_commentary_staleness.py`** — body bump → only that block re-copied;
  `updated`-only bump → **no** re-copy (proves hash authoritative); page deleted →
  block kept + `stale` note.
- **`test_lawbrain_registry.py`** — decided page skipped; keys-changed → re-evaluated;
  accept/reject round-trip in `links.yaml`.
- **`test_review_queue.py`** — low-conf/weak-grounding/collision/stale → `[pending]`,
  no `links.yaml`; `[accept]` + render → link applied, `links.yaml` written, entry
  pruned; `[reject]` → recorded, skipped next run.
- **templates** — `_neutralize_wikilinks` (`[[regulation-foo]]`→`regulation-foo`)
  and the unchanged `_demote_headings`.
- **`test_lawbrain_links.py`** (decision 6) — `[text](url)` + bare-URL extraction from
  page body and from referenced memos; primary-source denylist drops `*.gov`/leginfo/
  legiscan/wikipedia while keeping law-firm/IAPP/natlawreview; dedup by normalized URL;
  stable sort. Fixture: a mini memo with mixed primary + law-firm links.
- **`test_further_reading_render.py`** (decision 6) — `## Further Reading (via law
  brain)` lists deduped commentary links; section omitted when no links; links
  excluded from frontmatter (`to_frontmatter` round-trip drops `links`).
- **`test_region_preservation.py`** (decision 7) — `preserve_lawbrain_region`: a
  fresh body with no region + a prior page WITH a `lawbrain:region` block → spliced
  verbatim; no region in prior → fresh body unchanged; a refresh re-render of a
  commentary-bearing page keeps the region byte-identical (the data-loss regression
  guard).
- **Semi-integration (high-value):** render the **real** SB 53 commentary +
  Further Reading from the local law brain and assert a valid, byte-identical re-render.

The `lawbrain-matcher` subagent is validated by interactive UAT (D26), not offline
unit tests.

## 8. Decisions to log (`DECISIONS.md`, D57–D61)

- **D57** — PHASE-09 re-architected to the post-pivot model (slash command +
  deterministic fetch/render halves + `lawbrain-matcher` subagent), superseding
  PLAN's `run.py`/SDK design (per D26/D27/D30).
- **D58** — Commentary copy = full body, syntax-neutralized (demote headings D6 +
  neutralize `[[wiki-slug]]` at render time); refines D2/D6.
- **D59** — Commentary attaches on shared key + jurisdiction regardless of ZwiadBrain
  page kind; `type_map` (D8) governs only PHASE-11 minting.
- **D60** — Multi-subject slug-marker pages (tracker/landscape/map/scholarship) fail
  closed — excluded from commentary; refines D7.
- **D61** — Review-resolution folded into the render half (no separate
  `review --commit` command).
- **D62** — Harvest secondary/law-firm reference links from a matched page + its
  referenced `sources/zwiad/*.md` memos into a dedicated `## Further Reading (via law
  brain)` section; primary-source domains excluded via a configurable denylist;
  deterministic, deduped, body-only.
- **D63** — Commentary + Further Reading survive non-sync re-renders via text-level
  `lawbrain:region` marker preservation (the body-level analog of
  `preserve_leg_history`); bodies/links stay out of frontmatter (honors D20);
  `/zwiad-sync-lawbrain` is the sole creator/updater of the region.

## 9. Scope boundaries (explicitly NOT in this phase)

- **No stub-minting / discovery** — PHASE-11, `discover=false` (D14).
- **No scheduling** — PHASE-10 (D41).
- **No entity propagation** — deferred past v1 (D15).
- **No writes to the law brain** — strictly read-only (D2).
- **No Precedent-Board tentative→confirmed link promotion** — D16 optional polish.

## 10. Verification & acceptance

- Offline: ruff + `pyright --strict` + `pytest` all green; the full suite grows by
  the test files in §7 with no regressions.
- `uv run zwiadbrain fetch-lawbrain-candidates --dry-run` against the real
  `LAW_BRAIN_PATH` prints match results + grounding outcomes + intended writes, no
  edits.
- `/zwiad-sync-lawbrain` (interactive UAT): `regulation-california-sb53-tfaia`
  commentary appears on `ca-2025-sb-53`, with a `## Further Reading (via law brain)`
  section listing the law-firm/IAPP/natlawreview links harvested from its referenced
  memos (and no `*.gov`/legiscan duplicates); weak-grounding/low-confidence items land
  in `review-queue.md`; decisions recorded in `links.yaml`; re-run → byte-identical
  (clean `git status`).
- **Refresh-preservation:** after commentary is attached, run `/zwiad-refresh` on
  that bill → the `lawbrain:region` (commentary + Further Reading) is preserved
  byte-identical, not stripped (D63 regression guard).
- **`Brains/law` is untouched** (`git -C …/Brains/law status` clean, mtimes
  unchanged) — the read-only invariant (D2).
- Version bump **v0.9.0**; `DECISIONS.md` D57–D63, `ARCHITECTURE.md`, `docs/PLAN.md`
  PHASE-09 status updated.

**Expected first-run yield (honest):** ~1–2 commentary attachments (SB 53 cleanly;
TAKE IT DOWN possibly) out of 154 law-brain pages — the rest correctly
`not_in_scope` against a 6-item corpus. The pipeline's value compounds as the
tracked corpus grows with each backfill.
