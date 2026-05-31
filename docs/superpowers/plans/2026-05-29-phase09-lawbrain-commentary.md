# PHASE-09 Law-brain Commentary — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach the read-only sibling law brain as a verbatim commentary overlay + harvested reference links onto already-tracked ZwiadBrain pages, via deterministic key-matching with an LLM fallback gated by a shared-key grounding confirm.

**Architecture:** Post-pivot slash-command/subagent model (D26/D27): `/zwiad-sync-lawbrain` drives a deterministic Python `fetch-lawbrain-candidates` half, a `lawbrain-matcher` subagent for keyless pages only, and a deterministic `render-lawbrain-commentary` half. Mirrors `/zwiad-scan-enforcement`. Most persistence/render/config/store scaffolding already exists from PHASE-02.

**Tech Stack:** Python 3.12, pydantic v2, typer, jinja2, PyYAML, python-frontmatter, pytest, ruff, pyright --strict.

**Full design:** `docs/superpowers/specs/2026-05-29-phase09-lawbrain-commentary-design.md`.

---

## Shared Contracts (single source of truth — every task MUST use these exact names/signatures)

**Project conventions.** Python 3.12, src/ layout, pydantic v2, typer CLI, pytest, ruff, pyright --strict.
Tests live in tests/ mirroring src; offline fixtures under tests/fixtures/lawbrain/ (a mini law-brain wiki + memos).
CLI commands follow the existing pattern: @app.command(name="..."), Annotated typer.Option, a try/except AppError
boundary that does `typer.echo(f"error: {exc}", err=True); raise typer.Exit(1) from exc`, and a typer.echo summary line.
Staging: `from zwiadbrain.pipeline.staging import stage_json, validate_model`; stage_json(payload, name=, out=) -> Path.
Rendering entry: `from zwiadbrain.pipeline.render import write_page`; write_page(item, wiki_root) -> bool (compare-then-write).
Frontmatter parse: `from zwiadbrain.wiki.schema import from_page` -> Bill|EnforcementAction (raises WikiSchemaError).
Exceptions: AppError base; LawBrainError(AppError) and MatchError(LawBrainError) already exist in exceptions.py.

**ALREADY EXISTS — do NOT rebuild (only extend where noted):**
- models.py: CommentarySource{path:str, slug:str, updated:date|None, content_hash:str, matched_by:Literal["deterministic","llm"], confidence:float, body:str|None} and WikiItem.commentary_sources:list[CommentarySource].
- schema.py to_frontmatter: persists commentary_sources bookkeeping, currently `exclude={"body"}`.
- templates.py: _demote_headings(text) (## -> ###), _commentary_block(source), _commentary(sources) (slug-sorted), and the section render of "Commentary & Analysis" inside render_bill_body / render_enforcement_body. _BODY jinja template renders a list of {heading, body} sections.
- config.py: LawBrainSettings{enabled=False, path, min_confidence=0.75, require_shared_key=True, demote_headings=True, commentary=True, discover=False, commentary_only_types:list[str]=[], commentary_only_slug_markers:list[str]=[], type_map:dict[str,str]={}} + Settings.lawbrain + Settings.effective_law_brain_path.
- store.py: lawbrain_pages(slug PK, content_hash, updated, last_seen) + Store.upsert_lawbrain_page + Store.lawbrain_hashes().

**NEW MODULE CONTRACTS (exact):**
- sources/lawbrain.py:
  - class LawBrainPage(BaseModel): slug:str, type:str, jurisdiction:list[str], tags:list[str], title:str, citation:str|None=None, updated:dt.date|None=None, body:str, content_hash:str, source_files:list[str]=[].
  - class LawBrainReader: __init__(self, root: Path); is_available() -> bool ((root/"wiki").is_dir()); pages() -> list[LawBrainPage] (glob wiki/<type>-*.md, skip non-<type>- files; tolerant python-frontmatter parse; jurisdiction coerced scalar-or-list -> list[str]); read_source_memo(rel_path: str) -> str|None (resolve root/rel_path; only .md; None if missing/non-md).
  - module helper _content_hash(text:str)->str = sha256 of text.replace("\r\n","\n").replace("\r","\n"), hexdigest (D5).
- pipeline/lawbrain_keys.py (pure):
  - normalize_jurisdiction(j:str)->str ({"US-Federal":"US"} else j).
  - page_keys(page: LawBrainPage, slug_markers: list[str]) -> set[str]: returns set() if any marker is a substring of page.slug (fail-closed); else jurisdiction-qualified keys "{NORMJURIS}::bill::{PREFIX}-{N}", "docket::{k}", "public_law::{n}" extracted from slug+title+citation+tags.
  - tracked_item_keys(item: Bill|EnforcementAction) -> set[str]: Bill -> "{normjuris}::bill::{type}-{number}" from bill_number; EnforcementAction -> "docket::{docket}" and "public_law::{s}" for each statute that parses.
  - keys_hash(keys: set[str]) -> str (sha256 of sorted joined; for D9 stickiness).
- pipeline/lawbrain_match.py (pure; mirrors pipeline/enforcement.py):
  - class TargetRef(BaseModel): id:str, kind:Literal["bill","enforcement"], jurisdiction:str, title:str, keys:list[str].
  - build_shortlist(page: LawBrainPage, targets: list[TargetRef]) -> list[TargetRef] (same normalized jurisdiction; sorted by tag/keyword overlap desc; never the full corpus).
  - confirm_match(*, page_keys:set[str], target_keys:set[str], confidence:float, min_confidence:float, require_shared_key:bool, override:bool=False) -> bool (confidence>=min_confidence AND (override OR not require_shared_key OR len(page_keys & target_keys)>=1)).
- models.py ADD:
  - class CommentaryLink(BaseModel): text:str, url:str.
  - CommentarySource gains links:list[CommentaryLink]=[].
- schema.py CHANGE: commentary_sources dump uses exclude={"body","links"}.
- pipeline/lawbrain_links.py (pure):
  - harvest_links(*, page_body:str, memo_texts:list[str], primary_source_domains:list[str]) -> list[CommentaryLink]: extract [text](url) markdown links + bare https?:// URLs (anchor=host) from page_body and each memo; drop urls whose host ends with any primary_source_domains suffix; dedup by normalized url (lower host, strip trailing /); stable sort by (host,url).
- pipeline/lawbrain_copy.py (pure):
  - build_commentary_source(*, page: LawBrainPage, matched_by:str, confidence:float, links:list[CommentaryLink]) -> CommentarySource (body=page.body raw; content_hash=page.content_hash; updated=page.updated; path/slug from page).
  - merge_commentary(existing:list[CommentarySource], new:CommentarySource) -> list[CommentarySource] (same slug+same content_hash -> unchanged; same slug+changed hash -> replace; new slug -> append; return slug-sorted).
  - detect_stale(existing:list[CommentarySource], live_slugs:set[str]) -> list[str] (existing slugs not in live_slugs).
- pipeline/lawbrain_registry.py:
  - class LinkDecision(BaseModel): lawbrain_slug:str, decision:Literal["link","not_in_scope","reject"], target_id:str|None=None, matched_by:str|None=None, keys_hash:str, decided:dt.date|None=None.
  - class LinkRegistry: classmethod load(path:Path)->LinkRegistry; decision_for(slug:str)->LinkDecision|None; record(d:LinkDecision)->None; dump(path:Path)->None. YAML list under key "links". A decision is sticky unless its keys_hash differs (D9).
- pipeline/lawbrain_review.py:
  - class ReviewEntry(BaseModel): slug:str, target_id:str|None, reason:Literal["low-confidence","collision","weak-grounding","stale"], status:Literal["pending","accept","reject"]="pending".
  - render_review_queue(entries:list[ReviewEntry])->str (markdown checklist, "- [pending] slug -> target_id (reason)"); parse_review_queue(text:str)->list[ReviewEntry].
- templates.py ADD/CHANGE:
  - _neutralize_wikilinks(text:str)->str = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text).
  - _commentary_block: body = _neutralize_wikilinks(_demote_headings(source.body.strip())) if source.body else "".
  - _further_reading(sources)->str: aggregate dedup links across sources -> "- [text](url)" sorted by (host,url).
  - LAWBRAIN_REGION_BEGIN="<!-- lawbrain:region:begin -->", LAWBRAIN_REGION_END="<!-- lawbrain:region:end -->".
  - _lawbrain_region(sources:list[CommentarySource])->str|None: wrap "## Commentary & Analysis\n\n"+_commentary(sources) + (if any links) "\n\n## Further Reading (via law brain)\n\n"+_further_reading(sources) between the region markers; None if sources empty.
  - render_bill_body / render_enforcement_body: REMOVE "Commentary & Analysis" from the sections list; after body=_BODY.render(sections), compute region=_lawbrain_region([s for s in item.commentary_sources if s.body]); if region: body = body + "\n\n" + region. (Region renders LAST, after Sources. Only sources WITH a body produce a region — a refresh carries body=None metadata so emits no region.)
  - preserve_lawbrain_region(prev_text:str, fresh_text:str)->str: if LAWBRAIN_REGION_BEGIN in fresh_text return fresh_text; extract begin..end (inclusive) from prev_text; if absent return fresh_text; else append "\n\n"+region to fresh_text (preserve single trailing newline).
- render.py CHANGE: write_page reads prev_text when path exists and sets content = preserve_lawbrain_region(prev_text, content) BEFORE the compare-then-write. (Central preservation: every render path keeps a committed region unless the item carries fresh commentary bodies.)
- config.py ADD to LawBrainSettings: further_reading:bool=True; primary_source_domains:list[str]=[".gov","legiscan.com","courtlistener.com","wikipedia.org","europa.eu","legislation.gov.uk"].
- CLI (cli.py):
  - fetch-lawbrain-candidates [--wiki --out --topics? no] : LawBrainReader(settings.effective_law_brain_path); if not is_available() echo no-op + exit 0; read tracked items (Bill+EnforcementAction) from wiki via from_page -> TargetRef list (keys=tracked_item_keys); for each page compute page_keys; consult LinkRegistry (skip decided whose keys_hash unchanged); deterministic match=set intersection over a key->target index (1 -> link conf 1.0; >1 -> collision/review); 0 keys & not slug-marker -> build_shortlist for the matcher; write lawbrain-candidates.json (each: slug,title,type,jurisdiction,tags,citation,summary_excerpt,keys,match("deterministic"|"keyless"|"collision"),target_id?,shortlist?) + targets.json. Mirror fetch-enforcement-candidates structure.
  - render-lawbrain-commentary --in classified.json [--wiki --db]: per-item isolation (dropped list like render-enforcement); for each link (deterministic or llm): if llm, confirm_match (require_shared_key) else fall to review-queue weak-grounding; load target page via glob, read LawBrainPage from reader, harvest_links (page body + read_source_memo for each source_file), build_commentary_source, merge_commentary into target.commentary_sources, write_page (fresh has bodies -> region authoritative); detect_stale -> review note; write/resolve review-queue.md (apply [accept]/[reject], prune); record LinkRegistry; reindex. Mirror render-enforcement structure + the AppError boundary.
  - render-refreshed: ADD before write_page: bill = bill.model_copy(update={"commentary_sources": prev.commentary_sources}) so frontmatter bookkeeping survives; write_page now preserves the body region centrally.
- Subagent .claude/agents/lawbrain-matcher.md: tools: Read, model: sonnet; input slug/title/type/jurisdiction/tags/citation/summary + shortlist of {id,title,kind,jurisdiction,keys}; output ONLY {"decision":"link"|"not_in_scope","target_id":<id|null>,"confidence":0.0,"rationale":"one sentence"}. Conservative: not_in_scope when unsure; a deterministic confirm re-checks any link. Mirror .claude/agents/enforcement-matcher.md.
- Slash command .claude/commands/zwiad-sync-lawbrain.md: allowed-tools Bash,Read,Write,Task; orchestrate fetch-lawbrain-candidates -> read -> dispatch lawbrain-matcher ONLY for keyless+shortlist entries -> stage classified.json -> render-lawbrain-commentary -> reindex -> report; --dry-run; keep ANTHROPIC_API_KEY unset (D26); no auto-commit. Mirror .claude/commands/zwiad-scan-enforcement.md.
- Decisions to log in DECISIONS.md: D57 (re-architecture), D58 (full-body syntax-neutralized copy), D59 (attach on shared key regardless of kind; type_map only PHASE-11), D60 (slug-marker pages fail-closed), D61 (review-resolution folded into render half), D62 (Further Reading link harvest + primary-domain denylist), D63 (lawbrain:region text preservation across non-sync renders). Version bump v0.9.0 (pyproject.toml + __init__.py). Update ARCHITECTURE.md + docs/PLAN.md PHASE-09 status.

**TDD step format for every coding task:** bite-sized checkbox steps — (1) write failing test (show complete pytest code), (2) run it, expect FAIL with reason, (3) write minimal implementation (show complete code), (4) run, expect PASS, (5) commit with a conventional-commit message. Exact file paths always. NO placeholders ("TODO", "add error handling", "write tests for the above"). Mirror existing module/test idioms (read the real files).


---

I now have everything: `frontmatter.loads(text)` gives `.metadata` (dict) and `.content` (body string). `content_hash` is the sha256 of the whole EOL-normalized file text. I have the real SB53 page shape with a `sources:` list, list jurisdiction, and a `citation`. Now I'll author the task section.

### Task 1: Reader — sources/lawbrain.py

**Files:**
- Create: `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\sources\lawbrain.py`
- Create (fixtures): `C:\Users\rafst\documents\projectas\zwiadbrain\tests\fixtures\lawbrain\wiki\regulation-fixture-sb53.md`, `...\tests\fixtures\lawbrain\wiki\concept-fixture-ai-landscape.md`, `...\tests\fixtures\lawbrain\wiki\regulation-fixture-crlf-eol.md`, `...\tests\fixtures\lawbrain\wiki\index.md` (a non-page that MUST be skipped), `...\tests\fixtures\lawbrain\sources\zwiad\fixture-memo.md`
- Create (test): `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_lawbrain_reader.py`

This task delivers the read-only law-brain reader: the `LawBrainPage` model, the `_content_hash` helper (EOL-normalized sha256, D5), and `LawBrainReader` with `is_available()`, `pages()` (tolerant frontmatter parse: scalar-or-list `jurisdiction`, missing `citation`/`updated`, skip non-`<type>-` files), and `read_source_memo()` (resolve against root, `.md` only, `None` if missing/non-md). It is NOT a `Source` (no transport). Everything is offline-unit-tested against a mini-wiki fixture defined below.

---

- [ ] **Step 1: Create the fixture mini-wiki.** These five files are the offline corpus every reader test (and downstream key/match/copy tests in later tasks) reads. They are checked into the repo, not generated. Write each one exactly.

The first page mirrors the real `regulation-california-sb53-tfaia.md` shape — list `jurisdiction`, a `sources:` block, a `citation`, and `[[wikilink]]` cross-references in the body. The `<type>-` prefix is `regulation-`.

Write `C:\Users\rafst\documents\projectas\zwiadbrain\tests\fixtures\lawbrain\wiki\regulation-fixture-sb53.md`:

```markdown
---
title: Fixture SB 53 — Transparency in Frontier AI Act (TFAIA)
type: regulation
jurisdiction: [US-CA]
tags: [ai, frontier-ai, sb-53, tfaia, california]
created: 2026-05-06
updated: 2026-05-06
sources:
  - sources/zwiad/fixture-memo.md
  - sources/zwiad/fixture-missing.md
status: active
citation: California SB 53 (Ch. 138, Stats. 2025) — TFAIA
---

## Summary
Fixture stand-in for SB 53. Successor to SB 1047. See [The bill text](https://leginfo.legislature.ca.gov/sb53)
and a law-firm alert at [Mayer Brown analysis](https://www.mayerbrown.com/sb53).

## Key points
- Retains transparency-focused frontier-model obligations.
- Drops the catastrophic-harm liability and kill-switch mandates.

## Cross-references
- [[regulation-fixture-ab-2013]] — sister California training-data transparency.
```

Write `C:\Users\rafst\documents\projectas\zwiadbrain\tests\fixtures\lawbrain\wiki\concept-fixture-ai-landscape.md` — a multi-subject `concept-` page with a **scalar** (non-list) `jurisdiction`, **no** `citation`, and **no** `updated`, to prove the tolerant parse. Its slug carries the `landscape` marker used by the fail-closed key logic in Task 2:

```markdown
---
title: Fixture California AI Regulatory Landscape
type: concept
jurisdiction: US-CA
tags: [ai, california, landscape, tracker]
created: 2026-05-01
status: active
---

## Summary
A multi-subject tracker page covering the whole California AI stack. References
[[regulation-fixture-sb53]] and several other bills; no single subject.

## Key points
- Catalogs many California AI bills at once.
```

Write `C:\Users\rafst\documents\projectas\zwiadbrain\tests\fixtures\lawbrain\wiki\index.md` — a NON-page (no recognized `<type>-` prefix) that `pages()` MUST skip:

```markdown
# Law Brain Index

This is the table of contents, not a wiki page. The reader must skip it.
```

Write `C:\Users\rafst\documents\projectas\zwiadbrain\tests\fixtures\lawbrain\sources\zwiad\fixture-memo.md` — the memo referenced by the SB 53 fixture's `sources:` list, used by `read_source_memo` (and by the Task-9 link harvester). It carries mixed primary + law-firm links:

```markdown
---
title: Fixture memo — SB 1047 / SB 53
date: 2024-11-08
topic: california-frontier-ai
summary: Comparative analysis memo for the SB 53 fixture page.
---

SB 1047 was a model-centric, catastrophic-harm statute; SB 53 is its transparency
successor. Primary text: https://leginfo.legislature.ca.gov/sb1047 — secondary
commentary: [Crowell client alert](https://www.crowell.com/sb1047) and
[IAPP coverage](https://iapp.org/news/sb1047).
```

The CRLF fixture is written in the next step because it must contain literal `\r\n` bytes that a normal text editor would normalize — it is created programmatically.

- [ ] **Step 2: Create the CRLF fixture file with literal `\r\n` bytes.** This file proves `_content_hash` is EOL-normalized: its on-disk hash must equal the hash of the same content with `\n` endings. Run this exact command (Python writes the bytes in binary mode so the CR survives).

```
uv run python -c "import pathlib; p = pathlib.Path('tests/fixtures/lawbrain/wiki/regulation-fixture-crlf-eol.md'); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b'---\r\ntitle: Fixture CRLF EOL Regulation\r\ntype: regulation\r\njurisdiction: [US]\r\ntags: [eol-test]\r\ncreated: 2026-05-06\r\nupdated: 2026-05-06\r\nstatus: active\r\n---\r\n\r\n## Summary\r\nThis page uses CRLF line endings to prove the content hash is EOL-normalized.\r\n')"
```

Verify the CR bytes are present (expect a non-zero count):

```
uv run python -c "import pathlib; print(pathlib.Path('tests/fixtures/lawbrain/wiki/regulation-fixture-crlf-eol.md').read_bytes().count(b'\r'))"
```

Expected output: `11` (one CR per line). If it prints `0`, the file was normalized — re-run the write command.

- [ ] **Step 3: Write the failing test file.** Full pytest code. Tests cover: `is_available()` true/false; `pages()` enumerates only `<type>-*.md` and skips `index.md`; scalar `jurisdiction` coerced to a one-element list; list `jurisdiction` preserved; missing `citation`/`updated` tolerated as `None`; `source_files` captured from the `sources:` list; `body` is the post-frontmatter content; `_content_hash` is stable, equals the manual EOL-normalized sha256, and is CRLF-invariant; `read_source_memo` resolves an existing `.md`, returns `None` for a missing path, and `None` for a non-`.md` extension.

Write `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_lawbrain_reader.py`:

```python
"""Tests for the read-only law-brain reader (sources/lawbrain.py)."""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

import pytest

from zwiadbrain.sources.lawbrain import LawBrainPage, LawBrainReader, _content_hash

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "lawbrain"


@pytest.fixture
def reader() -> LawBrainReader:
    return LawBrainReader(FIXTURE_ROOT)


def _page_by_slug(reader: LawBrainReader, slug: str) -> LawBrainPage:
    pages = {page.slug: page for page in reader.pages()}
    assert slug in pages, f"{slug} not found; got {sorted(pages)}"
    return pages[slug]


def test_is_available_returns_true_when_wiki_dir_exists(reader: LawBrainReader) -> None:
    assert reader.is_available() is True


def test_is_available_returns_false_when_wiki_dir_missing(tmp_path: Path) -> None:
    assert LawBrainReader(tmp_path / "does-not-exist").is_available() is False


def test_pages_skips_non_type_prefixed_files(reader: LawBrainReader) -> None:
    slugs = {page.slug for page in reader.pages()}
    assert "index" not in slugs
    assert "regulation-fixture-sb53" in slugs
    assert "concept-fixture-ai-landscape" in slugs
    assert "regulation-fixture-crlf-eol" in slugs


def test_pages_preserves_list_jurisdiction(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "regulation-fixture-sb53")
    assert page.jurisdiction == ["US-CA"]


def test_pages_coerces_scalar_jurisdiction_to_list(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "concept-fixture-ai-landscape")
    assert page.jurisdiction == ["US-CA"]


def test_pages_parses_type_title_citation_and_updated(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "regulation-fixture-sb53")
    assert page.type == "regulation"
    assert page.title == "Fixture SB 53 — Transparency in Frontier AI Act (TFAIA)"
    assert page.citation == "California SB 53 (Ch. 138, Stats. 2025) — TFAIA"
    assert page.updated == dt.date(2026, 5, 6)


def test_pages_tolerates_missing_citation_and_updated(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "concept-fixture-ai-landscape")
    assert page.citation is None
    assert page.updated is None


def test_pages_captures_source_files_from_frontmatter(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "regulation-fixture-sb53")
    assert page.source_files == [
        "sources/zwiad/fixture-memo.md",
        "sources/zwiad/fixture-missing.md",
    ]


def test_pages_body_is_content_after_frontmatter(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "regulation-fixture-sb53")
    assert page.body.lstrip().startswith("## Summary")
    assert "[[regulation-fixture-ab-2013]]" in page.body
    assert "title: Fixture SB 53" not in page.body


def test_content_hash_matches_eol_normalized_sha256(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "regulation-fixture-sb53")
    raw = (FIXTURE_ROOT / "wiki" / "regulation-fixture-sb53.md").read_text(encoding="utf-8")
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    expected = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    assert page.content_hash == expected


def test_content_hash_is_crlf_invariant() -> None:
    crlf = "## Summary\r\nLine two.\r\n"
    lf = "## Summary\nLine two.\n"
    assert _content_hash(crlf) == _content_hash(lf)


def test_content_hash_of_crlf_fixture_equals_lf_equivalent(reader: LawBrainReader) -> None:
    page = _page_by_slug(reader, "regulation-fixture-crlf-eol")
    raw_bytes = (FIXTURE_ROOT / "wiki" / "regulation-fixture-crlf-eol.md").read_bytes()
    lf_text = raw_bytes.decode("utf-8").replace("\r\n", "\n")
    expected = hashlib.sha256(lf_text.encode("utf-8")).hexdigest()
    assert page.content_hash == expected


def test_read_source_memo_returns_text_for_existing_md(reader: LawBrainReader) -> None:
    memo = reader.read_source_memo("sources/zwiad/fixture-memo.md")
    assert memo is not None
    assert "Crowell client alert" in memo


def test_read_source_memo_returns_none_for_missing_file(reader: LawBrainReader) -> None:
    assert reader.read_source_memo("sources/zwiad/fixture-missing.md") is None


def test_read_source_memo_returns_none_for_non_md_extension(reader: LawBrainReader) -> None:
    assert reader.read_source_memo("sources/zwiad/fixture-memo.pdf") is None
```

- [ ] **Step 4: Run the test, expect failure (module does not exist yet).**

```
uv run pytest tests/test_lawbrain_reader.py -v
```

Expected: collection error / FAIL — `ModuleNotFoundError: No module named 'zwiadbrain.sources.lawbrain'` (the module is created in the next step).

- [ ] **Step 5: Write the implementation.** Full code, type-hinted, mirroring the legiscan source-module idioms (module docstring, `from __future__ import annotations`, `import datetime as dt`, module logger, small private helpers). Pydantic v2 `BaseModel` with field defaults matching the locked contract. `pages()` is tolerant: any per-file parse error is logged and skipped (one bad page never sinks a run), `jurisdiction` is coerced scalar-or-list to `list[str]`, missing `citation`/`updated` become `None`. `_content_hash` normalizes `\r\n` then bare `\r` to `\n` before hashing (D5).

Write `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\sources\lawbrain.py`:

```python
"""Read-only reader for the sibling law brain — NOT a :class:`Source`.

The law brain (``LAW_BRAIN_PATH/wiki/<type>-<slug>.md``) is a local Markdown
corpus, so this reader does no transport: it enumerates pages, parses their YAML
frontmatter tolerantly, and computes an EOL-normalized content hash used as the
commentary staleness cursor (D5). It also resolves a page's ``sources:`` memo
paths for the Further-Reading link harvester. Strictly read-only — this module
never writes to the law brain (D2).

Tolerance is deliberate: a single malformed page must not sink a whole sync run,
and the two wikis disagree on small shapes (``jurisdiction`` may be a scalar or a
list; ``citation``/``updated`` may be absent). One bad page is logged and skipped.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
from pathlib import Path
from typing import Any

import frontmatter

from pydantic import BaseModel, Field

_LOGGER = logging.getLogger(__name__)


def _content_hash(text: str) -> str:
    """SHA-256 of ``text`` with line endings normalized to ``\\n`` (D5).

    Normalizing CRLF and bare CR to LF before hashing makes the cursor
    insensitive to the EOL style the law brain happens to be saved with, so a
    pure line-ending change never reads as a stale-content diff.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _coerce_str_list(value: Any) -> list[str]:
    """Coerce a scalar-or-list YAML value into a ``list[str]`` (drop blanks)."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _opt_str(value: Any) -> str | None:
    """Return a stripped string, or None for missing/blank values."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_date(value: Any) -> dt.date | None:
    """Parse a ``YYYY-MM-DD`` date for display/attribution only (never diffing).

    ``python-frontmatter`` may already have parsed the YAML scalar into a
    ``datetime.date``; accept that directly, otherwise parse the ISO prefix.
    Any unparseable value yields ``None`` — the date is non-load-bearing.
    """
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = _opt_str(value)
    if text is None:
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


class LawBrainPage(BaseModel):
    """One parsed law-brain wiki page (read-only view).

    ``body`` is the verbatim Markdown after the frontmatter; ``content_hash`` is
    the EOL-normalized hash of the whole file and is the staleness cursor.
    ``updated`` is display/attribution only — never trusted for diffing (D5).
    """

    slug: str
    type: str
    jurisdiction: list[str]
    tags: list[str]
    title: str
    citation: str | None = None
    updated: dt.date | None = None
    body: str
    content_hash: str
    source_files: list[str] = Field(default_factory=list)


class LawBrainReader:
    """Enumerate and parse law-brain wiki pages from a root directory (read-only)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.wiki_dir = root / "wiki"

    def is_available(self) -> bool:
        """True iff ``<root>/wiki`` is a directory — a missing path is a clean no-op."""
        return self.wiki_dir.is_dir()

    def pages(self) -> list[LawBrainPage]:
        """Parse every ``wiki/<type>-*.md`` page; skip non-pages and malformed files.

        A file is a page only if its stem carries a ``<type>-`` prefix (so
        ``index.md``/``log.md``/``CLAUDE.md`` are skipped). Per-page parse errors
        are logged and skipped — one bad page never sinks a sync run.
        """
        if not self.is_available():
            return []
        results: list[LawBrainPage] = []
        for path in sorted(self.wiki_dir.glob("*.md")):
            page_type, sep, _ = path.stem.partition("-")
            if not sep or not page_type:
                continue
            page = self._parse_page(path, page_type)
            if page is not None:
                results.append(page)
        return results

    def _parse_page(self, path: Path, page_type: str) -> LawBrainPage | None:
        try:
            text = path.read_text(encoding="utf-8")
            parsed = frontmatter.loads(text)
        except (OSError, UnicodeDecodeError) as exc:
            _LOGGER.warning("skipping unreadable law-brain page %s: %s", path.name, exc)
            return None
        except Exception as exc:  # noqa: BLE001 — tolerant parse boundary (D5); malformed YAML must not sink the run
            _LOGGER.warning("skipping malformed law-brain page %s: %s", path.name, exc)
            return None
        metadata: dict[str, Any] = parsed.metadata
        return LawBrainPage(
            slug=path.stem,
            type=str(metadata.get("type") or page_type),
            jurisdiction=_coerce_str_list(metadata.get("jurisdiction")),
            tags=_coerce_str_list(metadata.get("tags")),
            title=str(metadata.get("title") or path.stem),
            citation=_opt_str(metadata.get("citation")),
            updated=_parse_date(metadata.get("updated")),
            body=parsed.content,
            content_hash=_content_hash(text),
            source_files=_coerce_str_list(metadata.get("sources")),
        )

    def read_source_memo(self, rel_path: str) -> str | None:
        """Return the text of a ``sources:`` memo, or None if missing or non-``.md``.

        Only ``.md`` memos are readable (a ``source_files`` entry may be a PDF or
        other binary). The path is resolved against the law-brain root and read
        read-only; a missing file yields ``None`` rather than raising.
        """
        candidate = self.root / rel_path
        if candidate.suffix.lower() != ".md":
            return None
        if not candidate.is_file():
            return None
        try:
            return candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            _LOGGER.warning("skipping unreadable law-brain memo %s: %s", rel_path, exc)
            return None
```

- [ ] **Step 6: Run the test, expect PASS.**

```
uv run pytest tests/test_lawbrain_reader.py -v
```

Expected: all 14 tests PASS. If `test_content_hash_of_crlf_fixture_equals_lf_equivalent` fails, the CRLF fixture from Step 2 was normalized on disk — re-run the Step 2 byte-write and the Step 2 verification (expect 11 CRs).

- [ ] **Step 7: Run lint + type-check on the new files, expect clean.**

```
uv run ruff check src/zwiadbrain/sources/lawbrain.py tests/test_lawbrain_reader.py
uv run pyright src/zwiadbrain/sources/lawbrain.py
```

Expected: ruff reports `All checks passed!`; pyright reports `0 errors, 0 warnings, 0 informations`.

- [ ] **Step 8: Commit.**

```
git add src/zwiadbrain/sources/lawbrain.py tests/test_lawbrain_reader.py tests/fixtures/lawbrain/
git commit -m "feat(lawbrain): add read-only law-brain reader (LawBrainPage + LawBrainReader)"
```

Commit message body (use a here-doc / `-m` body if your workflow records bodies) should note: tolerant frontmatter parse (scalar-or-list jurisdiction, optional citation/updated), EOL-normalized content hash (D5), and the offline mini-wiki fixture. End the commit message with the required `Co-Authored-By` trailer.

---

I now have everything I need. The test file imports `LawBrainPage` from `zwiadbrain.sources.lawbrain` (Task 1, which precedes this task). I have the exact contract for `LawBrainPage`, `Bill`, `EnforcementAction`, and `parse_strong_key`. Let me write the Task 2 section.

A few precise observations that shape the implementation:
- `parse_strong_key` is the single hardened docket extractor — `tracked_item_keys` for `EnforcementAction` and `page_keys` docket extraction reuse it.
- Bill type normalization: law-brain title "H.R. 8818" → `HR-8818`; tracked `Bill.bill_number` like "SB 53" must produce `SB-53`. I need a small bill-number→`{PREFIX}-{N}` normalizer that strips dots/spaces in the prefix and leading zeros from the number.
- The fail-closed slug-marker check returns `set()` if any marker is a substring of the slug.
- A law-review reporter citation (`103 Calif. L. Rev. 513`) must NOT yield a bill key — so the bill regex must be anchored to recognized bill-type prefixes only, and `Calif. L. Rev.` does not match `S` / `HR` / etc. with a word boundary structure.

Here is the task section.

---

### Task 2: Keys — pipeline/lawbrain_keys.py

**Files:**
- Create: `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\pipeline\lawbrain_keys.py`
- Modify: none
- Test: `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_lawbrain_keys.py`

This task is pure (no I/O). It depends on `LawBrainPage` from Task 1 (`src/zwiadbrain/sources/lawbrain.py`) and on `parse_strong_key` from `src/zwiadbrain/pipeline/ids.py` (the single hardened docket extractor — reuse it, do not reinvent a docket regex). The key space is jurisdiction-qualified strings shared by law-brain pages and tracked items; `match = page_keys(page) & tracked_item_keys(item)`.

- [ ] **Step 1: Write the failing test file.**

Write the complete test file at `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_lawbrain_keys.py`:

```python
from zwiadbrain.models import Bill, EnforcementAction
from zwiadbrain.pipeline.lawbrain_keys import (
    keys_hash,
    normalize_jurisdiction,
    page_keys,
    tracked_item_keys,
)
from zwiadbrain.sources.lawbrain import LawBrainPage

_MARKERS = ["tracker", "landscape", "map", "scholarship"]


def _page(
    *,
    slug: str,
    jurisdiction: list[str],
    title: str = "",
    citation: str | None = None,
    tags: list[str] | None = None,
    type_: str = "regulation",
) -> LawBrainPage:
    return LawBrainPage(
        slug=slug,
        type=type_,
        jurisdiction=jurisdiction,
        tags=tags or [],
        title=title,
        citation=citation,
        updated=None,
        body="",
        content_hash="0" * 64,
        source_files=[],
    )


def test_normalize_jurisdiction_maps_us_federal_to_us() -> None:
    assert normalize_jurisdiction("US-Federal") == "US"


def test_normalize_jurisdiction_passes_through_state_codes() -> None:
    assert normalize_jurisdiction("US-CA") == "US-CA"


def test_page_keys_extracts_state_bill_jurisdiction_qualified() -> None:
    page = _page(
        slug="regulation-california-sb53-tfaia",
        jurisdiction=["US-CA"],
        title="California SB 53 (TFAIA)",
    )
    assert "US-CA::bill::SB-53" in page_keys(page, _MARKERS)


def test_page_keys_normalizes_federal_bill_from_title() -> None:
    page = _page(
        slug="regulation-take-it-down-act",
        jurisdiction=["US-Federal"],
        title="TAKE IT DOWN Act (H.R. 8818)",
    )
    assert "US::bill::HR-8818" in page_keys(page, _MARKERS)


def test_page_keys_extracts_docket_via_parse_strong_key() -> None:
    page = _page(
        slug="case-acme-data-breach",
        jurisdiction=["US"],
        title="United States v. Acme",
        body=None,  # type: ignore[arg-type]  # not used; docket comes from title below
    ) if False else _page(
        slug="case-acme-data-breach",
        jurisdiction=["US"],
        title="United States v. Acme, Docket 2:25-cv-12295",
    )
    assert "docket::2-25-cv-12295" in page_keys(page, _MARKERS)


def test_page_keys_extracts_public_law() -> None:
    page = _page(
        slug="regulation-take-it-down-act",
        jurisdiction=["US"],
        title="TAKE IT DOWN Act",
        citation="Pub. L. 119-12",
    )
    assert "public_law::119-12" in page_keys(page, _MARKERS)


def test_page_keys_fail_closed_on_scholarship_slug_marker() -> None:
    page = _page(
        slug="concept-ai-liability-scholarship",
        jurisdiction=["US-CA"],
        title="AI Liability — SB 53 discussion",
    )
    assert page_keys(page, _MARKERS) == set()


def test_page_keys_fail_closed_on_landscape_slug_marker() -> None:
    page = _page(
        slug="concept-california-ai-regulatory-landscape",
        jurisdiction=["US-CA"],
        title="California AI Regulatory Landscape (SB 53, AB 1064)",
    )
    assert page_keys(page, _MARKERS) == set()


def test_page_keys_law_review_citation_yields_no_bill_key() -> None:
    page = _page(
        slug="concept-algorithmic-accountability",
        jurisdiction=["US"],
        title="Algorithmic Accountability",
        citation="103 Calif. L. Rev. 513 (2015)",
    )
    keys = page_keys(page, _MARKERS)
    assert not any(k.endswith("::bill::S-513") for k in keys)
    assert not any("::bill::" in k for k in keys)


def test_tracked_item_keys_for_state_bill() -> None:
    bill = Bill(
        id="ca-2025-sb-53",
        jurisdiction="US-CA",
        title="SB 53",
        bill_number="SB 53",
    )
    assert tracked_item_keys(bill) == {"US-CA::bill::SB-53"}


def test_tracked_item_keys_for_federal_bill() -> None:
    bill = Bill(
        id="119-hr-8818",
        jurisdiction="US",
        title="TAKE IT DOWN Act",
        bill_number="H.R. 8818",
    )
    assert tracked_item_keys(bill) == {"US::bill::HR-8818"}


def test_tracked_item_keys_for_enforcement_docket_and_public_law() -> None:
    action = EnforcementAction(
        id="ftc-2-25-cv-12295",
        jurisdiction="US",
        title="United States v. Acme",
        agency="FTC",
        docket="2:25-cv-12295",
        statutes=["Pub. L. 119-12", "15 U.S.C. 45"],
    )
    keys = tracked_item_keys(action)
    assert "docket::2-25-cv-12295" in keys
    assert "public_law::119-12" in keys


def test_page_and_tracked_keys_intersect_on_shared_state_bill() -> None:
    page = _page(
        slug="regulation-california-sb53-tfaia",
        jurisdiction=["US-CA"],
        title="California SB 53 (TFAIA)",
    )
    bill = Bill(id="ca-2025-sb-53", jurisdiction="US-CA", title="SB 53", bill_number="SB 53")
    assert page_keys(page, _MARKERS) & tracked_item_keys(bill) == {"US-CA::bill::SB-53"}


def test_keys_hash_is_order_independent_and_stable() -> None:
    a = keys_hash({"US::bill::HR-8818", "public_law::119-12"})
    b = keys_hash({"public_law::119-12", "US::bill::HR-8818"})
    assert a == b
    assert len(a) == 64
    assert keys_hash(set()) == keys_hash(set())
    assert keys_hash({"x"}) != keys_hash({"y"})
```

Note: the `if False else` ternary in `test_page_keys_extracts_docket_via_parse_strong_key` is an artifact — replace that whole test body with the clean version below to avoid the dead branch. Use this instead (overwrite that one function before running):

```python
def test_page_keys_extracts_docket_via_parse_strong_key() -> None:
    page = _page(
        slug="case-acme-data-breach",
        jurisdiction=["US"],
        title="United States v. Acme, Docket 2:25-cv-12295",
    )
    assert "docket::2-25-cv-12295" in page_keys(page, _MARKERS)
```

- [ ] **Step 2: Run the test, expect FAIL (module does not exist).**

```
uv run pytest tests/test_lawbrain_keys.py -v
```

Expected: collection error / FAIL — `ModuleNotFoundError: No module named 'zwiadbrain.pipeline.lawbrain_keys'` (the implementation module does not exist yet).

- [ ] **Step 3: Write the implementation.**

Write the complete module at `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\pipeline\lawbrain_keys.py`:

```python
"""Pure key-extraction for law-brain commentary matching (PHASE-09).

Both halves of a match are projected into one jurisdiction-qualified string
key space, so a match is a plain set intersection:
``page_keys(page) & tracked_item_keys(item)``. Nothing here does I/O.

Three key families:

* ``"{NORMJURIS}::bill::{PREFIX}-{N}"`` — a legislative bill, e.g.
  ``"US-CA::bill::SB-53"`` or ``"US::bill::HR-8818"`` (after ``US-Federal``
  -> ``US`` normalization). ``PREFIX`` is an uppercased recognized bill-type
  token; ``N`` is the bill number with leading zeros stripped.
* ``"docket::{key}"`` — a court/agency docket, extracted by the single hardened
  :func:`zwiadbrain.pipeline.ids.parse_strong_key` (reused, never re-implemented).
* ``"public_law::{N}"`` — an enacted public law, e.g. ``"public_law::119-12"``;
  the cross-type bridge between a statute page and an enforcement page (D59).

Fail-closed (D60): a page whose slug carries a multi-subject marker
(``tracker``/``landscape``/``map``/``scholarship``) emits **zero** keys — it
has no single subject, so it neither mints nor attaches commentary. Bill/docket
extraction is also anchored tightly enough that an academic reporter citation
(``103 Calif. L. Rev. 513``) is never misread as a bill key.
"""

from __future__ import annotations

import hashlib
import re

from zwiadbrain.models import Bill, EnforcementAction
from zwiadbrain.pipeline.ids import parse_strong_key
from zwiadbrain.sources.lawbrain import LawBrainPage

# Recognized legislative bill-type prefixes (federal + state). Longest-first so
# "HJRES" matches before "H"; case-insensitive at the regex level. Dots and
# spaces inside a prefix ("H.R.", "H R") are tolerated and stripped.
_BILL_PREFIXES: tuple[str, ...] = (
    "HJRES", "SJRES", "HCONRES", "SCONRES", "HRES", "SRES",
    "HR", "SB", "HB", "AB", "SCR", "HCR", "ACR", "SR", "S", "H",
)

# A bill reference is a recognized prefix (with optional internal dots/spaces),
# optional whitespace, then a run of digits. Anchored on a word boundary at the
# start so "...Calif. L. Rev. 513" does not match "S"/"H" mid-token: the char
# before the prefix must be a non-word char or the string start (\b). The
# prefix alternation is built longest-first to avoid "S" eating "SB".
_BILL_RE = re.compile(
    r"\b(" + "|".join(
        # Insert "[.\s]*" between letters so "H.R." / "H R" / "HR" all match.
        r"[.\s]*".join(ch for ch in prefix)
        for prefix in _BILL_PREFIXES
    ) + r")[.\s]*0*(\d+)\b",
    re.IGNORECASE,
)

# A public-law citation: "Pub. L. 119-12", "Public Law 119-12", "P.L. 119-12".
_PUBLIC_LAW_RE = re.compile(
    r"\b(?:pub(?:lic)?\.?\s*l(?:aw)?\.?)\s*(\d+-\d+)\b",
    re.IGNORECASE,
)


def normalize_jurisdiction(j: str) -> str:
    """Map a law-brain jurisdiction onto the ZwiadBrain code space.

    ``US-Federal`` -> ``US``; every other value (``US-CA``, ``US`` …) passes
    through unchanged.
    """
    return "US" if j == "US-Federal" else j


def _normalize_bill_prefix(raw: str) -> str:
    """Strip internal dots/spaces and uppercase a matched bill-type token."""
    return re.sub(r"[.\s]", "", raw).upper()


def _bill_keys_from_text(text: str, normjuris: str) -> set[str]:
    """Extract ``{normjuris}::bill::{PREFIX}-{N}`` keys from one text blob."""
    keys: set[str] = set()
    for match in _BILL_RE.finditer(text):
        prefix = _normalize_bill_prefix(match.group(1))
        number = match.group(2).lstrip("0") or "0"
        keys.add(f"{normjuris}::bill::{prefix}-{number}")
    return keys


def _bill_key_from_number(bill_number: str, normjuris: str) -> str | None:
    """Project a tracked ``bill_number`` ("SB 53", "H.R. 8818") into one bill key.

    Returns ``None`` when *bill_number* does not parse as ``<prefix><digits>``.
    """
    match = _BILL_RE.search(bill_number)
    if match is None:
        return None
    prefix = _normalize_bill_prefix(match.group(1))
    number = match.group(2).lstrip("0") or "0"
    return f"{normjuris}::bill::{prefix}-{number}"


def page_keys(page: LawBrainPage, slug_markers: list[str]) -> set[str]:
    """Extract jurisdiction-qualified match keys from a law-brain *page*.

    Returns an empty set (fail-closed, D60) when any *slug_markers* entry is a
    substring of ``page.slug`` — a multi-subject tracker/landscape/map/
    scholarship page has no single subject and must neither mint nor attach.

    Otherwise scans slug + title + citation + each tag for bill, docket, and
    public-law references. Bill keys are qualified by the page's normalized
    jurisdiction (the first listed); docket and public_law keys are
    jurisdiction-agnostic identifiers.
    """
    if any(marker in page.slug for marker in slug_markers):
        return set()

    keys: set[str] = set()
    text_fields = [page.slug, page.title, page.citation or "", *page.tags]
    blob = "\n".join(text_fields)

    # Bill keys need the page's jurisdiction; use the first listed (normalized).
    normjuris = normalize_jurisdiction(page.jurisdiction[0]) if page.jurisdiction else ""
    if normjuris:
        keys |= _bill_keys_from_text(blob, normjuris)

    docket = parse_strong_key(blob)
    if docket is not None:
        keys.add(f"docket::{docket}")

    for match in _PUBLIC_LAW_RE.finditer(blob):
        keys.add(f"public_law::{match.group(1)}")

    return keys


def tracked_item_keys(item: Bill | EnforcementAction) -> set[str]:
    """Project a tracked ZwiadBrain item into the same key space as :func:`page_keys`.

    A ``Bill`` yields a single ``{normjuris}::bill::{PREFIX}-{N}`` key from its
    ``bill_number``. An ``EnforcementAction`` yields ``docket::{key}`` from its
    ``docket`` (via :func:`parse_strong_key`) and a ``public_law::{N}`` key for
    each statute that parses as a public-law citation — the cross-type bridge.
    """
    keys: set[str] = set()
    if isinstance(item, Bill):
        normjuris = normalize_jurisdiction(item.jurisdiction)
        key = _bill_key_from_number(item.bill_number, normjuris)
        if key is not None:
            keys.add(key)
        return keys

    if item.docket:
        docket = parse_strong_key(item.docket)
        if docket is not None:
            keys.add(f"docket::{docket}")
    for statute in item.statutes:
        match = _PUBLIC_LAW_RE.search(statute)
        if match is not None:
            keys.add(f"public_law::{match.group(1)}")
    return keys


def keys_hash(keys: set[str]) -> str:
    """SHA-256 over the sorted, newline-joined key set (D9 stickiness cursor).

    Order-independent: ``keys_hash({"a", "b"}) == keys_hash({"b", "a"})``. Used
    by the link registry to detect when a settled page's extracted keys change.
    """
    joined = "\n".join(sorted(keys))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run the test, expect PASS.**

```
uv run pytest tests/test_lawbrain_keys.py -v
```

Expected: all tests PASS. Confirm in particular `test_page_keys_law_review_citation_yields_no_bill_key` (the `S`/`H` prefixes must not match inside `Calif. L. Rev. 513`), `test_page_keys_normalizes_federal_bill_from_title` (`H.R. 8818` -> `HR-8818`), `test_page_keys_fail_closed_on_scholarship_slug_marker` and `..._landscape_...` (empty set), and `test_keys_hash_is_order_independent_and_stable`.

- [ ] **Step 5: Lint, type-check, then run the full suite to confirm no regressions.**

```
uv run ruff check src/zwiadbrain/pipeline/lawbrain_keys.py tests/test_lawbrain_keys.py
uv run pyright --strict src/zwiadbrain/pipeline/lawbrain_keys.py
uv run pytest -q
```

Expected: ruff clean, pyright clean, full suite green (existing tests unaffected — this module is additive).

- [ ] **Step 6: Commit.**

```
git add src/zwiadbrain/pipeline/lawbrain_keys.py tests/test_lawbrain_keys.py
git commit -m "feat(lawbrain): add jurisdiction-qualified key extraction for commentary matching"
```

Commit message body (optional, only if you want the why recorded — the diff already shows the what):

```
feat(lawbrain): add jurisdiction-qualified key extraction for commentary matching

page_keys / tracked_item_keys project law-brain pages and tracked items into
one string key space (bill / docket / public_law); match is set intersection.
Slug-marker pages fail closed to zero keys (D60); docket extraction reuses the
hardened ids.parse_strong_key. keys_hash is the D9 stickiness cursor.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

I now have everything I need. The contracts depend on `LawBrainPage` (from Task 1, `sources/lawbrain.py`) and the keys helpers (Task 2). For this Task 3 test, I'll construct `LawBrainPage` directly and `TargetRef` objects, matching the locked contract. Let me write the task section.

```markdown
### Task 3: Match — `pipeline/lawbrain_match.py`

Pure jurisdiction-scoped shortlist + shared-key grounding confirm. Mirrors `pipeline/enforcement.py` (`MatterRef` / `build_shortlist` / `confirm_match`): nothing here does I/O, and `confirm_match` is the deterministic trust boundary that grounds the `lawbrain-matcher` subagent's proposal (D16). A purely topical LLM link (no shared key) never auto-applies when `require_shared_key=True` — it falls to the review queue. `build_shortlist` filters to the page's normalized jurisdiction and ranks by tag/keyword overlap, so the subagent never sees the full corpus.

**Files:**
- Create: `src/zwiadbrain/pipeline/lawbrain_match.py`
- Test: `tests/test_lawbrain_match.py`
- (Depends on Task 1 `src/zwiadbrain/sources/lawbrain.py::LawBrainPage` and Task 2 `src/zwiadbrain/pipeline/lawbrain_keys.py::normalize_jurisdiction` — both already landed.)

- [ ] **Step 1: Write the failing test.** Create `tests/test_lawbrain_match.py` with the complete contents below. It exercises `TargetRef`, `build_shortlist` (jurisdiction scoping + overlap ranking + never-full-corpus), and `confirm_match` (shared-key gating, override, confidence floor, `require_shared_key=False` topical pass).

```python
import datetime as dt

from zwiadbrain.sources.lawbrain import LawBrainPage
from zwiadbrain.pipeline.lawbrain_match import (
    TargetRef,
    build_shortlist,
    confirm_match,
)


def _page(
    *,
    slug: str = "regulation-california-sb53-tfaia",
    jurisdiction: list[str] | None = None,
    tags: list[str] | None = None,
    title: str = "California SB 53 (TFAIA)",
    citation: str | None = "SB 53",
) -> LawBrainPage:
    return LawBrainPage(
        slug=slug,
        type="regulation",
        jurisdiction=jurisdiction if jurisdiction is not None else ["US-CA"],
        tags=tags if tags is not None else ["ai", "transparency", "sb-53"],
        title=title,
        citation=citation,
        updated=dt.date(2026, 1, 1),
        body="## Summary\n\nBody.",
        content_hash="deadbeef",
        source_files=[],
    )


def test_build_shortlist_scopes_to_normalized_jurisdiction() -> None:
    page = _page(jurisdiction=["US-CA"], tags=["ai", "sb-53"])
    targets = [
        TargetRef(id="ca-2025-sb-53", kind="bill", jurisdiction="US-CA",
                  title="SB 53 — AI transparency", keys=["US-CA::bill::SB-53"]),
        TargetRef(id="ca-2025-ab-1064", kind="bill", jurisdiction="US-CA",
                  title="AB 1064 — chatbots", keys=["US-CA::bill::AB-1064"]),
        TargetRef(id="118-hr-2670", kind="bill", jurisdiction="US",
                  title="HR 2670 — NDAA", keys=["US::bill::HR-2670"]),
    ]
    short = build_shortlist(page, targets)
    ids = [t.id for t in short]
    assert "118-hr-2670" not in ids  # other jurisdiction excluded entirely
    assert set(ids) == {"ca-2025-sb-53", "ca-2025-ab-1064"}


def test_build_shortlist_ranks_by_tag_keyword_overlap_desc() -> None:
    page = _page(jurisdiction=["US-CA"], tags=["sb-53", "transparency"],
                 title="SB 53 transparency")
    targets = [
        TargetRef(id="ca-2025-ab-1337", kind="bill", jurisdiction="US-CA",
                  title="AB 1337 — unrelated employment topic",
                  keys=["US-CA::bill::AB-1337"]),
        TargetRef(id="ca-2025-sb-53", kind="bill", jurisdiction="US-CA",
                  title="SB 53 transparency requirements",
                  keys=["US-CA::bill::SB-53"]),
    ]
    short = build_shortlist(page, targets)
    assert [t.id for t in short][0] == "ca-2025-sb-53"  # higher overlap ranks first


def test_build_shortlist_normalizes_us_federal_against_us_targets() -> None:
    page = _page(jurisdiction=["US-Federal"], tags=["ndaa"], title="NDAA FY2024",
                 citation="H.R. 2670")
    targets = [
        TargetRef(id="118-hr-2670", kind="bill", jurisdiction="US",
                  title="HR 2670 — NDAA", keys=["US::bill::HR-2670"]),
        TargetRef(id="ca-2025-sb-53", kind="bill", jurisdiction="US-CA",
                  title="SB 53", keys=["US-CA::bill::SB-53"]),
    ]
    short = build_shortlist(page, targets)
    assert [t.id for t in short] == ["118-hr-2670"]  # US-Federal -> US


def test_build_shortlist_empty_when_no_jurisdiction_match() -> None:
    page = _page(jurisdiction=["US-NY"])
    targets = [
        TargetRef(id="ca-2025-sb-53", kind="bill", jurisdiction="US-CA",
                  title="SB 53", keys=["US-CA::bill::SB-53"]),
    ]
    assert build_shortlist(page, targets) == []


def test_confirm_match_links_when_confidence_and_shared_key() -> None:
    assert confirm_match(
        page_keys={"US-CA::bill::SB-53"},
        target_keys={"US-CA::bill::SB-53"},
        confidence=0.9,
        min_confidence=0.75,
        require_shared_key=True,
    ) is True


def test_confirm_match_rejects_no_shared_key_when_required() -> None:
    # Topical LLM proposal, no identifier overlap -> falls to review (weak-grounding).
    assert confirm_match(
        page_keys={"US-CA::bill::SB-53"},
        target_keys={"US-CA::bill::AB-1064"},
        confidence=0.95,
        min_confidence=0.75,
        require_shared_key=True,
    ) is False


def test_confirm_match_override_bypasses_shared_key() -> None:
    # Operator override recorded in links.yaml -> apply despite no shared key.
    assert confirm_match(
        page_keys={"US-CA::bill::SB-53"},
        target_keys={"US-CA::bill::AB-1064"},
        confidence=0.8,
        min_confidence=0.75,
        require_shared_key=True,
        override=True,
    ) is True


def test_confirm_match_rejects_below_confidence_floor() -> None:
    # Confidence floor is checked first; shared key alone does not rescue it.
    assert confirm_match(
        page_keys={"US-CA::bill::SB-53"},
        target_keys={"US-CA::bill::SB-53"},
        confidence=0.5,
        min_confidence=0.75,
        require_shared_key=True,
    ) is False
    # Even an override cannot bypass the confidence floor.
    assert confirm_match(
        page_keys={"US-CA::bill::SB-53"},
        target_keys={"US-CA::bill::SB-53"},
        confidence=0.5,
        min_confidence=0.75,
        require_shared_key=True,
        override=True,
    ) is False


def test_confirm_match_topical_passes_when_shared_key_not_required() -> None:
    # require_shared_key=False -> confidence alone suffices (topical link allowed).
    assert confirm_match(
        page_keys={"US-CA::bill::SB-53"},
        target_keys={"US-CA::bill::AB-1064"},
        confidence=0.8,
        min_confidence=0.75,
        require_shared_key=False,
    ) is True
```

- [ ] **Step 2: Run the test, expect FAIL.** The module does not exist yet, so collection fails on the import.

```
uv run pytest tests/test_lawbrain_match.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'zwiadbrain.pipeline.lawbrain_match'` (collection error, 0 tests run).

- [ ] **Step 3: Write the minimal implementation.** Create `src/zwiadbrain/pipeline/lawbrain_match.py` with the complete contents below. `build_shortlist` filters to the page's normalized jurisdiction (any of the page's jurisdictions, normalized via `normalize_jurisdiction`, matching the target's normalized jurisdiction) and ranks survivors by descending tag/title-keyword overlap — never returning the full corpus, only same-jurisdiction candidates. `confirm_match` mirrors `enforcement.confirm_match`: confidence floor first, then the shared-key gate (satisfiable by `override` or by `require_shared_key=False`).

```python
"""Pure jurisdiction-scoped shortlist + shared-key grounding confirm for law-brain
commentary matching.

Nothing here does I/O (mirrors :mod:`zwiadbrain.pipeline.enforcement`). The CLI fetch
half composes :func:`build_shortlist` to hand the ``lawbrain-matcher`` subagent a small,
same-jurisdiction candidate set instead of the full tracked corpus; the render half
composes :func:`confirm_match` as the deterministic trust boundary that grounds every
LLM-proposed link (D16). When ``require_shared_key`` is on, a purely *topical* match —
high confidence but no shared jurisdiction-qualified identifier — never auto-applies; it
falls to the review queue as ``weak-grounding``. An operator ``override`` recorded in
``links.yaml`` bypasses the shared-key gate but never the confidence floor.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from zwiadbrain.pipeline.lawbrain_keys import normalize_jurisdiction
from zwiadbrain.sources.lawbrain import LawBrainPage

# Tokens dropped before tag/keyword overlap scoring (corpus noise / structural words),
# so two single-subject pages compare on their substantive terms, not boilerplate.
_STOPWORDS: frozenset[str] = frozenset(
    {"the", "and", "of", "a", "an", "for", "to", "in", "on", "act", "bill",
     "ai", "law", "rule", "regulation"}
)


class TargetRef(BaseModel):
    """A lightweight reference to a tracked ZwiadBrain item (a shortlist candidate).

    ``keys`` are the item's jurisdiction-qualified keys (from
    :func:`zwiadbrain.pipeline.lawbrain_keys.tracked_item_keys`); ``confirm_match``
    intersects them with the page's keys to ground an LLM proposal.
    """

    id: str
    kind: Literal["bill", "enforcement"]
    jurisdiction: str
    title: str
    keys: list[str]


def _tokens(text: str) -> frozenset[str]:
    raw = text.lower().replace("-", " ").replace(":", " ").replace(".", " ")
    return frozenset(
        t for t in re.split(r"\s+", raw) if t and t not in _STOPWORDS
    )


def _overlap(page: LawBrainPage, target: TargetRef) -> int:
    """Count of shared significant tokens between the page (tags + title) and the
    target (title). A coarse topical ranking signal — not a confirmation."""
    page_tokens = _tokens(" ".join(page.tags) + " " + page.title)
    target_tokens = _tokens(target.title)
    return len(page_tokens & target_tokens)


def build_shortlist(page: LawBrainPage, targets: list[TargetRef]) -> list[TargetRef]:
    """Candidate tracked items for the ``lawbrain-matcher`` subagent: those sharing the
    page's normalized jurisdiction, ranked by descending tag/keyword overlap.

    Jurisdiction is the hard filter (``US-Federal`` normalizes to ``US`` to match
    ZwiadBrain's federal targets); never returns the full corpus.
    """
    page_jurisdictions = {normalize_jurisdiction(j) for j in page.jurisdiction}
    in_scope = [
        t for t in targets if normalize_jurisdiction(t.jurisdiction) in page_jurisdictions
    ]
    return sorted(in_scope, key=lambda t: (-_overlap(page, t), t.id))


def confirm_match(
    *,
    page_keys: set[str],
    target_keys: set[str],
    confidence: float,
    min_confidence: float,
    require_shared_key: bool,
    override: bool = False,
) -> bool:
    """Deterministic grounding of an LLM-proposed link (D16).

    Confidence must clear the floor first; then the shared-key gate is satisfied when an
    operator ``override`` is recorded, OR the deployment does not require a shared key,
    OR the page and target share at least one jurisdiction-qualified key. An ``override``
    bypasses the shared-key gate but never the confidence floor.
    """
    if confidence < min_confidence:
        return False
    return override or not require_shared_key or len(page_keys & target_keys) >= 1
```

- [ ] **Step 4: Run the test, expect PASS.**

```
uv run pytest tests/test_lawbrain_match.py -v
```

Expected: PASS — all 9 tests green (`test_build_shortlist_scopes_to_normalized_jurisdiction`, `..._ranks_by_tag_keyword_overlap_desc`, `..._normalizes_us_federal_against_us_targets`, `..._empty_when_no_jurisdiction_match`, `test_confirm_match_links_when_confidence_and_shared_key`, `..._rejects_no_shared_key_when_required`, `..._override_bypasses_shared_key`, `..._rejects_below_confidence_floor`, `..._topical_passes_when_shared_key_not_required`).

- [ ] **Step 5: Run the gates, then commit.** Confirm ruff + pyright --strict are clean on the new module/test and the full suite has no regressions, then commit.

```
uv run ruff check src/zwiadbrain/pipeline/lawbrain_match.py tests/test_lawbrain_match.py
uv run pyright src/zwiadbrain/pipeline/lawbrain_match.py
uv run pytest tests/test_lawbrain_match.py -q
git add src/zwiadbrain/pipeline/lawbrain_match.py tests/test_lawbrain_match.py
git commit -m "feat(lawbrain): add jurisdiction-scoped shortlist + shared-key confirm_match"
```

Expected: ruff clean, pyright 0 errors, tests pass; commit created on `feature/phase-09-lawbrain-commentary`.
```

---

I have everything I need. I now understand the exact models, the `to_frontmatter` dump line (`exclude={"body"}`), and the test idioms. Here is the task section.

### Task 4: Model — CommentaryLink + CommentarySource.links + frontmatter exclusion

Add a `CommentaryLink` model, give `CommentarySource` a `links: list[CommentaryLink] = []` field, and change the `to_frontmatter` commentary dump from `exclude={"body"}` to `exclude={"body", "links"}` so that both the verbatim body and the harvested links stay out of frontmatter (they are rendered into the page body / Further Reading, not the metadata source-of-truth).

**Files:**
- Modify: `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\models.py` (add `CommentaryLink`; add `links` to `CommentarySource`)
- Modify: `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\wiki\schema.py` (change commentary dump exclude set)
- Test: `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_schema.py` (extend)

---

- [ ] **Step 1: Write the failing test for `links` round-tripping out of frontmatter.**

Append the following test to the end of `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_schema.py`. It builds a `CommentarySource` carrying both a `body` and `links`, serializes the parent bill, and asserts that the commentary bookkeeping survives while BOTH `body` and `links` are dropped from frontmatter. It also asserts the in-memory model still holds the links (proving the field exists and is populated, not silently absent).

```python
def test_to_frontmatter_drops_commentary_body_and_links() -> None:
    """should keep commentary bookkeeping but drop both body and links from frontmatter"""
    from zwiadbrain.models import CommentaryLink

    bill = Bill(
        id="us-ca-sb-362",
        jurisdiction="US-CA",
        title="California Delete Act",
        bill_number="SB 362",
        commentary_sources=[
            CommentarySource(
                path="wiki/regulation-california-delete-act.md",
                slug="regulation-california-delete-act",
                content_hash="abc123",
                matched_by="deterministic",
                confidence=1.0,
                body="Verbatim copied commentary body.",
                links=[
                    CommentaryLink(
                        text="EFF analysis",
                        url="https://www.eff.org/delete-act",
                    )
                ],
            )
        ],
    )

    # The in-memory model carries the link (the field exists and is populated).
    assert bill.commentary_sources[0].links[0].url == "https://www.eff.org/delete-act"

    fm = to_frontmatter(bill)
    sources = fm["commentary_sources"]
    assert isinstance(sources, list)
    assert sources[0]["slug"] == "regulation-california-delete-act"
    assert sources[0]["matched_by"] == "deterministic"
    assert "body" not in sources[0]
    assert "links" not in sources[0]
```

---

- [ ] **Step 2: Run the new test — expect FAIL.**

```
uv run pytest "tests/test_schema.py::test_to_frontmatter_drops_commentary_body_and_links" -v
```

Expected: FAIL. First with `ImportError: cannot import name 'CommentaryLink' from 'zwiadbrain.models'` (the model does not exist yet). After Step 3 adds `CommentaryLink` but before Step 5 fixes the dump, it would instead fail on `assert "links" not in sources[0]` because the dump still excludes only `{"body"}`, leaving `links` in the serialized dict.

---

- [ ] **Step 3: Add the `CommentaryLink` model and the `links` field to `CommentarySource`.**

In `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\models.py`, insert the `CommentaryLink` class immediately before `CommentarySource` (so the forward reference in the field annotation resolves), and add the `links` field to `CommentarySource`. Replace this block:

```python
class CommentarySource(BaseModel):
    """A law-brain page whose content has been copied onto a tracked page.

    Carries the bookkeeping that lets Pass A detect when copied commentary is
    stale and re-copy it (``content_hash``), plus how the link was established.
    """

    path: str
    slug: str
    updated: dt.date | None = None
    content_hash: str
    matched_by: Literal["deterministic", "llm"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    body: str | None = None  # verbatim copied page body; rendered, not stored in frontmatter
```

with:

```python
class CommentaryLink(BaseModel):
    """An external reference harvested from a law-brain page or its source memos.

    Rendered into the page body's "Further Reading (via law brain)" section; never
    stored in frontmatter (it is re-derived from the copied body on each render).
    """

    text: str
    url: str


class CommentarySource(BaseModel):
    """A law-brain page whose content has been copied onto a tracked page.

    Carries the bookkeeping that lets Pass A detect when copied commentary is
    stale and re-copy it (``content_hash``), plus how the link was established.
    """

    path: str
    slug: str
    updated: dt.date | None = None
    content_hash: str
    matched_by: Literal["deterministic", "llm"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    body: str | None = None  # verbatim copied page body; rendered, not stored in frontmatter
    links: list[CommentaryLink] = []  # harvested external refs; rendered, not stored in frontmatter
```

---

- [ ] **Step 4: Change the `to_frontmatter` commentary dump to exclude `links` as well as `body`.**

In `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\wiki\schema.py`, the comment above the commentary dump references only the body. Update both the comment and the `exclude` set. Replace:

```python
    # Commentary sources are built from the typed model so the verbatim body can
    # be excluded cleanly (it is rendered into the page body, not the frontmatter).
    if item.commentary_sources:
        fm["commentary_sources"] = [
            source.model_dump(mode="json", exclude_none=True, exclude={"body"})
            for source in item.commentary_sources
        ]
```

with:

```python
    # Commentary sources are built from the typed model so the verbatim body and
    # the harvested links can be excluded cleanly (both are rendered into the page
    # body — the body as commentary, the links as "Further Reading" — not the
    # frontmatter, which holds only the stale-detection bookkeeping).
    if item.commentary_sources:
        fm["commentary_sources"] = [
            source.model_dump(mode="json", exclude_none=True, exclude={"body", "links"})
            for source in item.commentary_sources
        ]
```

---

- [ ] **Step 5: Run the new test plus the existing commentary test — expect PASS.**

```
uv run pytest "tests/test_schema.py::test_to_frontmatter_drops_commentary_body_and_links" "tests/test_schema.py::test_to_frontmatter_keeps_commentary_bookkeeping_but_drops_body" -v
```

Expected: both PASS. The pre-existing `test_to_frontmatter_keeps_commentary_bookkeeping_but_drops_body` must remain green — its sample source has no `links`, so `exclude_none`/empty handling leaves the bookkeeping untouched and confirms no regression in the body-drop behavior.

---

- [ ] **Step 6: Run the full schema and models suites plus type/lint gates — expect all PASS/clean.**

```
uv run pytest tests/test_schema.py tests/test_models.py -q
uv run pyright src/zwiadbrain/models.py src/zwiadbrain/wiki/schema.py
uv run ruff check src/zwiadbrain/models.py src/zwiadbrain/wiki/schema.py
```

Expected: all tests PASS; `pyright` reports 0 errors (the `list[CommentaryLink]` default `[]` is a pydantic field default, not a mutable class attribute — pydantic handles it, matching `commentary_sources: list[CommentarySource] = []` already in the file); `ruff` reports no findings.

---

- [ ] **Step 7: Commit.**

```
git add src/zwiadbrain/models.py src/zwiadbrain/wiki/schema.py tests/test_schema.py
git commit -m "feat(lawbrain): add CommentaryLink model and exclude links from frontmatter"
```

The commit message body is not required for this atomic change; the diff (new model + field + exclude-set widening + test) is self-describing.

---

I have everything needed. The `CommentaryLink` model (with `text:str, url:str` per locked contract) is assumed already added in an earlier task (Task that adds models.py `CommentaryLink` + `CommentarySource.links`). Task 5 imports it. Here is the task section.

---

### Task 5: Links — pipeline/lawbrain_links.py

Pure, offline link harvester for the `## Further Reading (via law brain)` section (spec §5.9, D62). Extracts `[text](url)` markdown links and bare `https?://` URLs from a matched page body and its referenced memos, drops primary-source domains via a host-suffix denylist, dedups by normalized URL, and stable-sorts by `(host, url)` for byte-identical render (D20).

**Files:**
- Create: `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\pipeline\lawbrain_links.py`
- Test: `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_lawbrain_links.py`
- (Depends on `CommentaryLink` already added to `src\zwiadbrain\models.py` in the models task — Task 5 only imports it; it does not modify `models.py`.)

---

- [ ] **Step 1: Write the failing test.**

Create `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_lawbrain_links.py` with the complete contents below. It exercises markdown + bare-URL extraction from page body and memo, the primary-source denylist (`.gov` / `legiscan.com` / `wikipedia.org` dropped; `natlawreview.com` / `mayerbrown.com` kept), dedup across page+memo, anchor-text preservation, and stable `(host, url)` sort.

```python
from zwiadbrain.models import CommentaryLink
from zwiadbrain.pipeline.lawbrain_links import harvest_links

_DENYLIST = [
    ".gov",
    "legiscan.com",
    "courtlistener.com",
    "wikipedia.org",
    "europa.eu",
    "legislation.gov.uk",
]

# A mini memo mixing primary-source links (dropped) and law-firm/secondary links (kept).
_MEMO = """\
## Sources

- [California CPPA enforcement order](https://cppa.ca.gov/announcements/order.pdf)
- [Bill text on LegiScan](https://legiscan.com/CA/text/SB53)
- [Mayer Brown client alert](https://www.mayerbrown.com/en/insights/publications/2026/05/cppa-alert)
- [The National Law Review analysis](https://natlawreview.com/article/cppa-onstar)
- Bare reference: https://www.jdsupra.com/legalnews/cppa-settlement-12345/
- Primary statute: https://leginfo.legislature.ca.gov/faces/billText.xhtml
- Background: https://en.wikipedia.org/wiki/California_Consumer_Privacy_Act
"""

_PAGE_BODY = """\
## Summary

The CPPA settled with GM/OnStar. See the [Mayer Brown client alert](https://www.mayerbrown.com/en/insights/publications/2026/05/cppa-alert)
and the agency's own [order](https://cppa.ca.gov/announcements/order.pdf).

Further commentary: https://iapp.org/news/a/cppa-onstar-takeaways/
"""


def test_harvest_links_extracts_markdown_links_from_page_body() -> None:
    links = harvest_links(
        page_body=_PAGE_BODY,
        memo_texts=[],
        primary_source_domains=_DENYLIST,
    )
    assert CommentaryLink(
        text="Mayer Brown client alert",
        url="https://www.mayerbrown.com/en/insights/publications/2026/05/cppa-alert",
    ) in links


def test_harvest_links_preserves_anchor_text() -> None:
    links = harvest_links(
        page_body="",
        memo_texts=[_MEMO],
        primary_source_domains=_DENYLIST,
    )
    by_url = {link.url: link.text for link in links}
    assert by_url["https://natlawreview.com/article/cppa-onstar"] == "The National Law Review analysis"


def test_harvest_links_bare_url_anchor_is_host() -> None:
    links = harvest_links(
        page_body="See https://iapp.org/news/a/cppa-onstar-takeaways/ for more.",
        memo_texts=[],
        primary_source_domains=_DENYLIST,
    )
    assert links == [
        CommentaryLink(text="iapp.org", url="https://iapp.org/news/a/cppa-onstar-takeaways/"),
    ]


def test_harvest_links_drops_primary_source_domains() -> None:
    links = harvest_links(
        page_body=_PAGE_BODY,
        memo_texts=[_MEMO],
        primary_source_domains=_DENYLIST,
    )
    hosts = {link.url for link in links}
    # .gov, legiscan.com, wikipedia.org, leginfo.legislature.ca.gov (.gov) all dropped.
    assert "https://cppa.ca.gov/announcements/order.pdf" not in hosts
    assert "https://legiscan.com/CA/text/SB53" not in hosts
    assert "https://en.wikipedia.org/wiki/California_Consumer_Privacy_Act" not in hosts
    assert "https://leginfo.legislature.ca.gov/faces/billText.xhtml" not in hosts
    # Law-firm / secondary commentary kept.
    assert "https://www.mayerbrown.com/en/insights/publications/2026/05/cppa-alert" in hosts
    assert "https://natlawreview.com/article/cppa-onstar" in hosts
    assert "https://www.jdsupra.com/legalnews/cppa-settlement-12345/" in hosts
    assert "https://iapp.org/news/a/cppa-onstar-takeaways/" in hosts


def test_harvest_links_dedups_across_page_and_memo() -> None:
    # The Mayer Brown alert appears in BOTH the page body and the memo -> one entry.
    links = harvest_links(
        page_body=_PAGE_BODY,
        memo_texts=[_MEMO],
        primary_source_domains=_DENYLIST,
    )
    mayer = [link for link in links if link.url.startswith("https://www.mayerbrown.com")]
    assert len(mayer) == 1


def test_harvest_links_dedups_trailing_slash_and_host_case() -> None:
    links = harvest_links(
        page_body="[A](https://Example.com/path/) and [B](https://example.com/path)",
        memo_texts=[],
        primary_source_domains=[],
    )
    assert len(links) == 1


def test_harvest_links_stable_sort_by_host_then_url() -> None:
    links = harvest_links(
        page_body=_PAGE_BODY,
        memo_texts=[_MEMO],
        primary_source_domains=_DENYLIST,
    )
    keyed = [(link.url.split("/")[2].lower(), link.url) for link in links]
    assert keyed == sorted(keyed)


def test_harvest_links_empty_when_no_links() -> None:
    assert harvest_links(
        page_body="A page body with no links at all.",
        memo_texts=["Memo with no links."],
        primary_source_domains=_DENYLIST,
    ) == []


def test_harvest_links_markdown_link_not_double_counted_as_bare_url() -> None:
    # A URL already inside a [text](url) link must not ALSO appear as a bare-url anchor.
    links = harvest_links(
        page_body="[IAPP](https://iapp.org/news/a/x/)",
        memo_texts=[],
        primary_source_domains=[],
    )
    assert links == [
        CommentaryLink(text="IAPP", url="https://iapp.org/news/a/x/"),
    ]
```

---

- [ ] **Step 2: Run the test, expect FAIL.**

```
uv run pytest tests/test_lawbrain_links.py -v
```

Expected: collection/import error — `ModuleNotFoundError: No module named 'zwiadbrain.pipeline.lawbrain_links'` (the module does not exist yet). All 9 tests error out at import.

---

- [ ] **Step 3: Write the minimal implementation.**

Create `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\pipeline\lawbrain_links.py` with the complete contents below.

Design notes baked into the code:
- Markdown links are matched first; their raw URL spans are recorded so the bare-URL pass can skip any URL already captured inside a `(...)` anchor (avoids the double-count guarded by `test_harvest_links_markdown_link_not_double_counted_as_bare_url`).
- A bare URL's trailing sentence punctuation (`.`, `,`, `;`, `:`, `)`) is trimmed so `https://x/y.` does not leak the period into the URL.
- Host extraction is via `urllib.parse.urlsplit().hostname` (already lowercased by stdlib); the denylist check is a host-suffix match (`host == suffix or host.endswith(suffix)`), so `.gov` matches `cppa.ca.gov` and `leginfo.legislature.ca.gov`, and `legiscan.com` matches `www.legiscan.com`.
- Dedup key = `(lowercase host, path-with-trailing-slash-stripped)` reconstructed; the first occurrence's anchor text wins (page body is scanned before memos, so a page-body anchor is preferred over a memo anchor for the same URL).
- Final sort is by `(host, url)` — both lowercased host and the normalized url — matching the locked contract and D20.

```python
"""Deterministic, offline harvest of secondary-commentary reference links (D62).

The verbatim body-copy of a matched law-brain page (PHASE-09 §5.4) captures only the
links present in the page body. The richer law-firm / IAPP / natlawreview links live in
the ``sources/zwiad/*.md`` memos the page references. This module pulls ``[text](url)``
markdown links and bare ``https?://`` URLs out of the page body AND each referenced memo,
drops primary-source domains (ZwiadBrain already carries authoritative primary sources),
dedups by normalized URL, and stable-sorts by ``(host, url)`` so a re-render is
byte-identical (D20). No LLM, no network — pure text in, ``CommentaryLink`` list out.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from zwiadbrain.models import CommentaryLink

# [text](https://host/path) — non-greedy text, http(s) URL up to the closing paren.
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
# A bare http(s) URL: run of non-whitespace after the scheme.
_BARE_URL = re.compile(r"https?://[^\s)\]]+")
# Sentence punctuation that commonly trails a bare URL and is not part of it.
_TRAILING_PUNCT = ".,;:)\u201d\"'"


def _host(url: str) -> str:
    """Lowercase host of *url* (``urlsplit().hostname`` is already lowercased)."""
    return (urlsplit(url).hostname or "").lower()


def _normalized_url(url: str) -> str:
    """Dedup key: lowercase host spliced back in, one trailing ``/`` stripped."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    rest = url[url.lower().find(host) + len(host):] if host else url
    rebuilt = f"{parts.scheme}://{host}{rest}"
    return rebuilt[:-1] if rebuilt.endswith("/") else rebuilt


def _is_primary_source(url: str, primary_source_domains: list[str]) -> bool:
    """True if the URL's host equals or ends with any configured denylist suffix."""
    host = _host(url)
    if not host:
        return False
    for suffix in primary_source_domains:
        bare = suffix.lstrip(".")
        if host == bare or host.endswith("." + bare):
            return True
    return False


def _strip_trailing_punct(url: str) -> str:
    return url.rstrip(_TRAILING_PUNCT)


def harvest_links(
    *,
    page_body: str,
    memo_texts: list[str],
    primary_source_domains: list[str],
) -> list[CommentaryLink]:
    """Extract secondary-commentary links from *page_body* and each memo (D62).

    Markdown ``[text](url)`` links keep their anchor text; bare ``https?://`` URLs use
    their host as the anchor. URLs whose host ends with a ``primary_source_domains``
    suffix are dropped. Results are deduped by normalized URL (lowercase host, one
    trailing ``/`` stripped) — first occurrence's anchor text wins — and stable-sorted
    by ``(host, normalized url)``.
    """
    # Ordered dict keyed by normalized URL preserves first-seen anchor text.
    seen: dict[str, CommentaryLink] = {}

    for text in (page_body, *memo_texts):
        consumed: set[str] = set()
        # Markdown links first; record their URL spans so the bare pass skips them.
        for match in _MARKDOWN_LINK.finditer(text):
            anchor, url = match.group(1).strip(), match.group(2)
            consumed.add(url)
            if _is_primary_source(url, primary_source_domains):
                continue
            key = _normalized_url(url)
            if key not in seen:
                seen[key] = CommentaryLink(text=anchor, url=url)
        # Bare URLs not already captured inside a markdown link.
        for match in _BARE_URL.finditer(text):
            url = _strip_trailing_punct(match.group(0))
            if url in consumed or match.group(0) in consumed:
                continue
            if _is_primary_source(url, primary_source_domains):
                continue
            key = _normalized_url(url)
            if key not in seen:
                seen[key] = CommentaryLink(text=_host(url), url=url)

    return sorted(seen.values(), key=lambda link: (_host(link.url), _normalized_url(link.url)))
```

---

- [ ] **Step 4: Run the test, expect PASS.**

```
uv run pytest tests/test_lawbrain_links.py -v
```

Expected: 9 passed. Then confirm lint and types are clean:

```
uv run ruff check src/zwiadbrain/pipeline/lawbrain_links.py tests/test_lawbrain_links.py
uv run pyright src/zwiadbrain/pipeline/lawbrain_links.py
```

Expected: ruff reports `All checks passed!` and pyright reports `0 errors, 0 warnings, 0 informations`.

---

- [ ] **Step 5: Commit.**

```
git add src/zwiadbrain/pipeline/lawbrain_links.py tests/test_lawbrain_links.py
git commit -m "feat(lawbrain): harvest secondary-commentary links for Further Reading (D62)"
```

The commit body is optional; the single conventional-commit subject above is sufficient (atomic: one pure module + its offline tests, no unrelated changes).

---

I have everything I need. The contract specifies `build_commentary_source` takes `links: list[CommentaryLink]`, and `merge_commentary`/`detect_stale` operate on `CommentarySource` lists. The `CommentaryLink` model and `CommentarySource.links` field are added in an earlier task (Task contracts state these as prerequisites). I'll write the task to depend on those existing.

Here is the markdown for the task section.

---

### Task 6: Copy — pipeline/lawbrain_copy.py

**Files:**
- Create: `src/zwiadbrain/pipeline/lawbrain_copy.py`
- Test: `tests/test_commentary_copy.py`
- Test: `tests/test_commentary_staleness.py`

> Depends on: `LawBrainPage` (`sources/lawbrain.py`), and `CommentaryLink` + `CommentarySource.links` already added to `models.py` (earlier tasks). This task is pure — no I/O. It mirrors the idempotent-merge idiom of `pipeline/enforcement.py::merge_developments` (dedup-and-sort, re-seeing an unchanged item is a no-op).

---

- [ ] **Step 1: Write the failing test for `build_commentary_source` (raw body, hash/updated/path/slug carried from the page).**

Create `tests/test_commentary_copy.py` with the first test:

```python
import datetime as dt

import pytest

from zwiadbrain.models import CommentaryLink, CommentarySource
from zwiadbrain.pipeline.lawbrain_copy import (
    build_commentary_source,
    merge_commentary,
)
from zwiadbrain.sources.lawbrain import LawBrainPage


def _page(
    slug: str = "regulation-california-sb53-tfaia",
    *,
    body: str = "## Summary\n\nThe TFAIA frontier-model law.\n",
    content_hash: str = "h0",
    updated: dt.date | None = dt.date(2025, 9, 1),
) -> LawBrainPage:
    return LawBrainPage(
        slug=slug,
        type="regulation",
        jurisdiction=["US-CA"],
        tags=["ai", "frontier-models"],
        title="California SB 53 (TFAIA)",
        citation="Cal. SB 53",
        updated=updated,
        body=body,
        content_hash=content_hash,
        source_files=["sources/zwiad/sb53.md"],
    )


def test_build_commentary_source_copies_body_verbatim_and_carries_bookkeeping() -> None:
    page = _page()
    links = [CommentaryLink(text="IAPP analysis", url="https://iapp.org/news/a")]

    src = build_commentary_source(
        page=page, matched_by="deterministic", confidence=1.0, links=links
    )

    assert isinstance(src, CommentarySource)
    assert src.body == "## Summary\n\nThe TFAIA frontier-model law.\n"  # raw, untransformed
    assert src.slug == "regulation-california-sb53-tfaia"
    assert src.path == "regulation-california-sb53-tfaia"
    assert src.content_hash == "h0"
    assert src.updated == dt.date(2025, 9, 1)
    assert src.matched_by == "deterministic"
    assert src.confidence == 1.0
    assert src.links == links
```

- [ ] **Step 2: Run it, expect FAIL (module does not exist yet).**

```
uv run pytest tests/test_commentary_copy.py::test_build_commentary_source_copies_body_verbatim_and_carries_bookkeeping -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'zwiadbrain.pipeline.lawbrain_copy'` (the test collects but the import resolves to nothing).

- [ ] **Step 3: Write the minimal implementation — module docstring + `build_commentary_source`.**

Create `src/zwiadbrain/pipeline/lawbrain_copy.py`:

```python
"""Pure copy/merge/staleness helpers for law-brain commentary consolidation.

Nothing here does I/O. The render half composes these with the renderer to fold a
matched law-brain page into an existing tracked page's ``commentary_sources``
idempotently, and to surface pages that have vanished from the law brain.

The idempotency contract mirrors :func:`zwiadbrain.pipeline.enforcement.merge_developments`:
re-seeing the same slug at the same ``content_hash`` returns the existing list
unchanged, so a repeated sync produces a byte-identical render and a clean
``git status`` (D20). A body bump (new ``content_hash``) replaces only that one block;
a new slug appends. The result is always slug-sorted so the renderer's output is
deterministic regardless of merge order.

The stored ``body`` is the **raw** law-brain markdown (verbatim); the render-time
transforms (``_demote_headings`` + ``_neutralize_wikilinks``) are applied in
``templates._commentary_block``, keeping ``content_hash`` tied to the source bytes (D58).
"""

from __future__ import annotations

from zwiadbrain.models import CommentaryLink, CommentarySource
from zwiadbrain.sources.lawbrain import LawBrainPage


def build_commentary_source(
    *,
    page: LawBrainPage,
    matched_by: str,
    confidence: float,
    links: list[CommentaryLink],
) -> CommentarySource:
    """Build a :class:`CommentarySource` from a matched law-brain page.

    ``body`` is the raw page body (verbatim — render-time transforms are applied
    later); ``content_hash`` and ``updated`` are carried from the page so staleness
    detection compares against the source bytes, not display metadata. ``path`` and
    ``slug`` both come from the page slug (the law-brain page is addressed by slug).
    """
    return CommentarySource(
        path=page.slug,
        slug=page.slug,
        updated=page.updated,
        content_hash=page.content_hash,
        matched_by=matched_by,  # pyright: ignore[reportArgumentType]  # validated by CommentarySource (Literal)
        confidence=confidence,
        body=page.body,
        links=links,
    )
```

- [ ] **Step 4: Run it, expect PASS.**

```
uv run pytest tests/test_commentary_copy.py::test_build_commentary_source_copies_body_verbatim_and_carries_bookkeeping -v
```

Expected: PASS.

- [ ] **Step 5: Write the failing test for `merge_commentary` — first apply appends.**

Append to `tests/test_commentary_copy.py`:

```python
def test_merge_commentary_first_apply_appends() -> None:
    src = build_commentary_source(
        page=_page(), matched_by="deterministic", confidence=1.0, links=[]
    )

    merged = merge_commentary([], src)

    assert [s.slug for s in merged] == ["regulation-california-sb53-tfaia"]
    assert merged[0].content_hash == "h0"
```

- [ ] **Step 6: Run it, expect FAIL (function not yet defined).**

```
uv run pytest tests/test_commentary_copy.py::test_merge_commentary_first_apply_appends -v
```

Expected: FAIL with `ImportError: cannot import name 'merge_commentary' from 'zwiadbrain.pipeline.lawbrain_copy'`.

- [ ] **Step 7: Implement `merge_commentary`.**

Append to `src/zwiadbrain/pipeline/lawbrain_copy.py`:

```python
def merge_commentary(
    existing: list[CommentarySource], new: CommentarySource
) -> list[CommentarySource]:
    """Fold *new* into *existing*, deduped by slug, returned slug-sorted.

    - same slug + unchanged ``content_hash`` -> the existing list is returned unchanged
      (no-op; a repeated sync is idempotent — mirrors ``merge_developments``).
    - same slug + changed ``content_hash`` -> replace that one block only.
    - new slug -> append.

    The result is always sorted by slug so the renderer emits a deterministic,
    byte-identical block order regardless of the order pages were merged in.
    """
    for current in existing:
        if current.slug == new.slug:
            if current.content_hash == new.content_hash:
                return existing  # unchanged: no-op, preserves byte-identical render
            replaced = [new if s.slug == new.slug else s for s in existing]
            return sorted(replaced, key=lambda s: s.slug)
    combined = [*existing, new]
    return sorted(combined, key=lambda s: s.slug)
```

- [ ] **Step 8: Run it, expect PASS.**

```
uv run pytest tests/test_commentary_copy.py::test_merge_commentary_first_apply_appends -v
```

Expected: PASS.

- [ ] **Step 9: Write the failing tests for idempotency, replace-on-hash-change, and new-slug-append-sorted.**

Append to `tests/test_commentary_copy.py`:

```python
def test_merge_commentary_same_hash_reapply_is_noop_identity() -> None:
    src = build_commentary_source(
        page=_page(), matched_by="deterministic", confidence=1.0, links=[]
    )
    existing = merge_commentary([], src)

    # Re-seeing the same slug at the same content_hash returns the SAME list object
    # (identity), guaranteeing a byte-identical render and clean git status (D20).
    again = build_commentary_source(
        page=_page(content_hash="h0"), matched_by="deterministic", confidence=1.0, links=[]
    )
    assert merge_commentary(existing, again) is existing


def test_merge_commentary_changed_hash_replaces_only_that_block() -> None:
    a0 = build_commentary_source(
        page=_page(slug="regulation-a", content_hash="a0"),
        matched_by="deterministic", confidence=1.0, links=[],
    )
    b0 = build_commentary_source(
        page=_page(slug="regulation-b", content_hash="b0"),
        matched_by="deterministic", confidence=1.0, links=[],
    )
    existing = merge_commentary(merge_commentary([], a0), b0)

    a1 = build_commentary_source(
        page=_page(slug="regulation-a", body="## Summary\n\nAmended.\n", content_hash="a1"),
        matched_by="deterministic", confidence=1.0, links=[],
    )
    merged = merge_commentary(existing, a1)

    assert {s.slug: s.content_hash for s in merged} == {
        "regulation-a": "a1",  # replaced
        "regulation-b": "b0",  # untouched
    }
    assert next(s for s in merged if s.slug == "regulation-a").body == "## Summary\n\nAmended.\n"


def test_merge_commentary_new_slug_appends_and_sorts_by_slug() -> None:
    z = build_commentary_source(
        page=_page(slug="regulation-zebra", content_hash="z0"),
        matched_by="deterministic", confidence=1.0, links=[],
    )
    a = build_commentary_source(
        page=_page(slug="regulation-alpha", content_hash="a0"),
        matched_by="llm", confidence=0.9, links=[],
    )
    merged = merge_commentary(merge_commentary([], z), a)

    assert [s.slug for s in merged] == ["regulation-alpha", "regulation-zebra"]
```

- [ ] **Step 10: Run the three new tests, expect PASS (the Step 7 implementation already satisfies them).**

```
uv run pytest tests/test_commentary_copy.py -v
```

Expected: all PASS (`build_commentary_source` test + the four `merge_commentary` tests).

- [ ] **Step 11: Write the failing test for `detect_stale` in its own file.**

Create `tests/test_commentary_staleness.py`:

```python
import datetime as dt

from zwiadbrain.models import CommentarySource
from zwiadbrain.pipeline.lawbrain_copy import detect_stale


def _src(slug: str, content_hash: str = "h") -> CommentarySource:
    return CommentarySource(
        path=slug,
        slug=slug,
        updated=dt.date(2025, 9, 1),
        content_hash=content_hash,
        matched_by="deterministic",
        confidence=1.0,
        body="## Summary\n\nbody\n",
    )


def test_detect_stale_returns_existing_slugs_absent_from_live_set() -> None:
    existing = [_src("regulation-a"), _src("regulation-b"), _src("regulation-c")]
    live = {"regulation-a", "regulation-c"}

    assert detect_stale(existing, live) == ["regulation-b"]


def test_detect_stale_empty_when_all_existing_are_still_live() -> None:
    existing = [_src("regulation-a"), _src("regulation-b")]
    live = {"regulation-a", "regulation-b", "regulation-c"}

    assert detect_stale(existing, live) == []


def test_detect_stale_is_slug_sorted_and_deduped_by_existing_order() -> None:
    existing = [_src("regulation-zebra"), _src("regulation-alpha")]
    live: set[str] = set()  # both dropped from the law brain

    # Both vanished pages reported, slug-sorted for deterministic review-note output.
    assert detect_stale(existing, live) == ["regulation-alpha", "regulation-zebra"]
```

- [ ] **Step 12: Run it, expect FAIL (`detect_stale` not yet defined).**

```
uv run pytest tests/test_commentary_staleness.py -v
```

Expected: FAIL with `ImportError: cannot import name 'detect_stale' from 'zwiadbrain.pipeline.lawbrain_copy'`.

- [ ] **Step 13: Implement `detect_stale`.**

Append to `src/zwiadbrain/pipeline/lawbrain_copy.py`:

```python
def detect_stale(
    existing: list[CommentarySource], live_slugs: set[str]
) -> list[str]:
    """Return the slugs of existing commentary whose source page has vanished.

    A page deleted from the law brain is never silently dropped from the tracked
    page; instead its slug is reported here so the render half can emit a ``stale``
    review note (D-staleness). Result is slug-sorted for a deterministic note.
    """
    return sorted(s.slug for s in existing if s.slug not in live_slugs)
```

- [ ] **Step 14: Run the staleness tests, expect PASS.**

```
uv run pytest tests/test_commentary_staleness.py -v
```

Expected: all three PASS.

- [ ] **Step 15: Run the full new-file suite plus lint and type checks.**

```
uv run pytest tests/test_commentary_copy.py tests/test_commentary_staleness.py -v
uv run ruff check src/zwiadbrain/pipeline/lawbrain_copy.py tests/test_commentary_copy.py tests/test_commentary_staleness.py
uv run pyright src/zwiadbrain/pipeline/lawbrain_copy.py
```

Expected: all tests PASS, ruff reports no issues, pyright reports 0 errors.

- [ ] **Step 16: Commit.**

```
git add src/zwiadbrain/pipeline/lawbrain_copy.py tests/test_commentary_copy.py tests/test_commentary_staleness.py
git commit -m "feat(lawbrain): add pure commentary copy/merge/staleness helpers"
```

Commit body (paste into the editor or use a second `-m`):

```
build_commentary_source carries raw body + content_hash/updated/path/slug from a
matched LawBrainPage; merge_commentary is idempotent (same slug+hash -> unchanged
list identity), replaces only the changed block on a hash bump, appends new slugs,
and returns slug-sorted for byte-identical renders (D20). detect_stale reports
existing commentary whose source page vanished so the render half can raise a stale
review note rather than silently dropping analysis. Pure, no I/O; mirrors
enforcement.merge_developments idempotency.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

I have all the idioms I need. Here is the task section.

### Task 7: Templates + render preservation

**Files:**
- Modify: `src/zwiadbrain/wiki/templates.py` (add `_neutralize_wikilinks`, `_further_reading`, region markers, `_lawbrain_region`, `preserve_lawbrain_region`; rewire `_commentary_block`, `render_bill_body`, `render_enforcement_body`)
- Modify: `src/zwiadbrain/pipeline/render.py` (`write_page` reads `prev_text` and applies `preserve_lawbrain_region` before compare-then-write)
- Create test: `tests/test_lawbrain_render.py`
- Create test: `tests/test_region_preservation.py`

This task is the D63 data-loss regression guard: a non-sync re-render (e.g. `render-refreshed`) must never strip a committed `lawbrain:region`. The region is rendered LAST (after Sources), only from commentary sources that carry a `body`, and is otherwise spliced forward verbatim from the previous page.

---

- [ ] **Step 1: Write a failing test for `_neutralize_wikilinks`.**

`_neutralize_wikilinks` strips dead `[[wiki-slug]]` cross-reference links to plain text (the law brain is a separate wiki, so those links would 404). It must handle multiple links on a line, links with spaces, and leave non-wikilink markdown untouched.

Create `tests/test_lawbrain_render.py`:

```python
"""Tests for the law-brain commentary render layer (Phase 09).

Covers wikilink neutralization, Further Reading aggregation, the marker-delimited
``lawbrain:region`` (rendered last, only from sources carrying a body), and the
region-omitted case for refresh metadata that carries ``body=None``.
"""

import datetime as dt

from zwiadbrain.models import Bill, CommentaryLink, CommentarySource, EnforcementAction
from zwiadbrain.wiki.templates import (
    LAWBRAIN_REGION_BEGIN,
    LAWBRAIN_REGION_END,
    _further_reading,
    _lawbrain_region,
    _neutralize_wikilinks,
    render_bill_body,
    render_enforcement_body,
)


def _bill() -> Bill:
    return Bill(
        id="us-119-hr-1",
        jurisdiction="US",
        bill_number="HR 1",
        title="An Act",
        summary="A summary.",
        sources={"Congress.gov": "https://www.congress.gov/bill/119/hr/1"},
    )


def _source(
    *,
    slug: str,
    body: str | None,
    links: list[CommentaryLink] | None = None,
    updated: dt.date | None = None,
) -> CommentarySource:
    return CommentarySource(
        path=f"wiki/regulation-{slug}.md",
        slug=slug,
        updated=updated,
        content_hash="deadbeef",
        matched_by="deterministic",
        confidence=1.0,
        body=body,
        links=links or [],
    )


def test_neutralize_wikilinks_strips_double_bracket_refs() -> None:
    text = "See [[regulation-foo]] and [[Some Other Page]] for context."
    assert _neutralize_wikilinks(text) == "See regulation-foo and Some Other Page for context."


def test_neutralize_wikilinks_leaves_markdown_links_untouched() -> None:
    text = "See [the rule](https://example.gov/rule) for details."
    assert _neutralize_wikilinks(text) == "See [the rule](https://example.gov/rule) for details."
```

Run it, expecting an ImportError (the symbols do not exist yet):

```
uv run pytest tests/test_lawbrain_render.py::test_neutralize_wikilinks_strips_double_bracket_refs -v
```

Expected: FAIL — `ImportError: cannot import name 'LAWBRAIN_REGION_BEGIN' from 'zwiadbrain.wiki.templates'`.

---

- [ ] **Step 2: Add `_neutralize_wikilinks`, region markers, and rewire `_commentary_block`.**

Add the markers as module constants near `_COMMENTARY_NOTE`, the new helper next to `_demote_headings`, and update `_commentary_block` to neutralize wikilinks after demoting headings (per the contract). Update the `models` import to include `CommentaryLink`.

In `src/zwiadbrain/wiki/templates.py`, change the import block:

```python
from zwiadbrain.models import (
    Action,
    Amendment,
    Bill,
    CommentaryLink,
    CommentarySource,
    Enactment,
    EnforcementAction,
    EnforcementDevelopment,
    FloorAction,
    Hearing,
    LegHistory,
    Statement,
    TextVersion,
    Vote,
)
```

Add the markers after the `_COMMENTARY_NOTE` definition:

```python
LAWBRAIN_REGION_BEGIN = "<!-- lawbrain:region:begin -->"
LAWBRAIN_REGION_END = "<!-- lawbrain:region:end -->"
```

Add the helper immediately after `_demote_headings`:

```python
def _neutralize_wikilinks(text: str) -> str:
    """Strip dead ``[[wiki-slug]]`` cross-reference links to plain text.

    The law brain is a separate wiki: its ``[[...]]`` links resolve nowhere in
    this corpus, so copied commentary renders them as their inner text only.
    """
    return re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
```

Update `_commentary_block` so the body is heading-demoted then wikilink-neutralized:

```python
def _commentary_block(source: CommentarySource) -> str:
    updated = f" (updated {source.updated.isoformat()})" if source.updated else ""
    body = _neutralize_wikilinks(_demote_headings(source.body.strip())) if source.body else ""
    return "\n".join(
        [
            f"<!-- lawbrain:begin slug={source.slug} -->",
            f"> Source: law brain page `{source.slug}`{updated}.",
            f"> {_COMMENTARY_NOTE}",
            "",
            body,
            f"<!-- lawbrain:end slug={source.slug} -->",
        ]
    )
```

Run the two neutralize tests, expecting PASS:

```
uv run pytest tests/test_lawbrain_render.py -k neutralize -v
```

Expected: PASS (2 passed).

---

- [ ] **Step 3: Write a failing test for `_further_reading`.**

`_further_reading` aggregates `CommentaryLink`s across all sources, dedups by normalized url (lower host, strip trailing `/`), and renders `- [text](url)` sorted by `(host, url)`. Append to `tests/test_lawbrain_render.py`:

```python
def test_further_reading_dedups_and_sorts_by_host() -> None:
    sources = [
        _source(
            slug="b-rule",
            body="x",
            links=[
                CommentaryLink(text="Zeta analysis", url="https://zeta.example/a"),
                CommentaryLink(text="Alpha brief", url="https://alpha.example/x"),
            ],
        ),
        _source(
            slug="a-rule",
            body="y",
            links=[
                # duplicate of zeta.example/a after trailing-slash normalization
                CommentaryLink(text="Zeta (dup)", url="https://zeta.example/a/"),
                CommentaryLink(text="Beta note", url="https://beta.example/n"),
            ],
        ),
    ]
    assert _further_reading(sources) == (
        "- [Alpha brief](https://alpha.example/x)\n"
        "- [Beta note](https://beta.example/n)\n"
        "- [Zeta analysis](https://zeta.example/a)"
    )


def test_further_reading_empty_when_no_links() -> None:
    assert _further_reading([_source(slug="a", body="x")]) == ""
```

Run it, expecting FAIL:

```
uv run pytest tests/test_lawbrain_render.py::test_further_reading_dedups_and_sorts_by_host -v
```

Expected: FAIL — `ImportError: cannot import name '_further_reading'`.

---

- [ ] **Step 4: Implement `_further_reading`.**

Add it after `_commentary` in `src/zwiadbrain/wiki/templates.py`. Dedup keeps the first link seen per normalized url (sources iterated in slug order so the dedup winner is stable); rows are sorted by `(host, url)`.

```python
def _normalize_url(url: str) -> str:
    """Normalize a url for dedup: lowercase host, strip a single trailing slash."""
    match = re.match(r"^(https?://)([^/]+)(.*)$", url)
    if not match:
        return url.rstrip("/")
    scheme, host, rest = match.groups()
    return f"{scheme}{host.lower()}{rest}".rstrip("/")


def _link_host(url: str) -> str:
    match = re.match(r"^https?://([^/]+)", url)
    return match.group(1).lower() if match else url


def _further_reading(sources: list[CommentarySource]) -> str:
    """Aggregate and dedup ``Further Reading`` links across commentary sources.

    Links are deduped by normalized url (lower host, single trailing slash
    stripped) keeping the first occurrence in slug order, then rendered as
    ``- [text](url)`` sorted by ``(host, url)``.
    """
    seen: set[str] = set()
    unique: list[CommentaryLink] = []
    for source in sorted(sources, key=lambda s: s.slug):
        for link in source.links:
            key = _normalize_url(link.url)
            if key in seen:
                continue
            seen.add(key)
            unique.append(link)
    unique.sort(key=lambda link: (_link_host(link.url), link.url))
    return "\n".join(f"- [{link.text}]({link.url})" for link in unique)
```

Run the Further Reading tests, expecting PASS:

```
uv run pytest tests/test_lawbrain_render.py -k further_reading -v
```

Expected: PASS (2 passed).

---

- [ ] **Step 5: Write a failing test for `_lawbrain_region`.**

`_lawbrain_region` wraps `## Commentary & Analysis` + the commentary blocks, plus (when any links exist) a `## Further Reading (via law brain)` section, between the two region markers. It returns `None` when the source list is empty. Append to `tests/test_lawbrain_render.py`:

```python
def test_lawbrain_region_wraps_commentary_and_further_reading_in_markers() -> None:
    sources = [
        _source(
            slug="x-rule",
            body="## Background\n\nText with [[regulation-foo]].",
            links=[CommentaryLink(text="Ref", url="https://ref.example/a")],
            updated=dt.date(2026, 5, 1),
        )
    ]
    region = _lawbrain_region(sources)
    assert region is not None
    assert region.startswith(LAWBRAIN_REGION_BEGIN)
    assert region.endswith(LAWBRAIN_REGION_END)
    assert "## Commentary & Analysis" in region
    assert "## Further Reading (via law brain)" in region
    assert "- [Ref](https://ref.example/a)" in region
    # heading demoted (## -> ###) and wikilink neutralized inside the block
    assert "### Background" in region
    assert "regulation-foo" in region
    assert "[[regulation-foo]]" not in region


def test_lawbrain_region_omits_further_reading_when_no_links() -> None:
    region = _lawbrain_region([_source(slug="x", body="Just prose.")])
    assert region is not None
    assert "## Commentary & Analysis" in region
    assert "## Further Reading (via law brain)" not in region


def test_lawbrain_region_none_when_empty() -> None:
    assert _lawbrain_region([]) is None
```

Run it, expecting FAIL:

```
uv run pytest tests/test_lawbrain_render.py::test_lawbrain_region_none_when_empty -v
```

Expected: FAIL — `ImportError: cannot import name '_lawbrain_region'`.

---

- [ ] **Step 6: Implement `_lawbrain_region`.**

Add it after `_further_reading` in `src/zwiadbrain/wiki/templates.py`:

```python
def _lawbrain_region(sources: list[CommentarySource]) -> str | None:
    """Render the marker-delimited law-brain region, or ``None`` if no sources.

    The region is the commentary blocks under ``## Commentary & Analysis`` plus,
    when any source carries links, a ``## Further Reading (via law brain)``
    section, wrapped between :data:`LAWBRAIN_REGION_BEGIN` and
    :data:`LAWBRAIN_REGION_END`. Callers append it last, after ``Sources``.
    """
    if not sources:
        return None
    parts = ["## Commentary & Analysis\n\n" + _commentary(sources)]
    further = _further_reading(sources)
    if further:
        parts.append("## Further Reading (via law brain)\n\n" + further)
    inner = "\n\n".join(parts)
    return f"{LAWBRAIN_REGION_BEGIN}\n{inner}\n{LAWBRAIN_REGION_END}"
```

Run the region tests, expecting PASS:

```
uv run pytest tests/test_lawbrain_render.py -k lawbrain_region -v
```

Expected: PASS (3 passed).

---

- [ ] **Step 7: Write a failing test for region placement in `render_bill_body` / `render_enforcement_body`.**

Commentary must move OUT of the section list and the region must be appended LAST (after `Sources`). Only sources WITH a body produce a region — a refresh-only source carries `body=None` and must emit no region. Append to `tests/test_lawbrain_render.py`:

```python
def test_render_bill_body_appends_region_after_sources() -> None:
    bill = _bill()
    bill.commentary_sources = [
        _source(
            slug="x-rule",
            body="## Analysis\n\nCommentary text.",
            links=[CommentaryLink(text="Ref", url="https://ref.example/a")],
        )
    ]
    body = render_bill_body(bill)
    # region present and wrapped in markers
    assert LAWBRAIN_REGION_BEGIN in body
    assert LAWBRAIN_REGION_END in body
    # region renders LAST: after the Sources section
    assert body.index("## Sources") < body.index(LAWBRAIN_REGION_BEGIN)
    # commentary is no longer an inline section header outside the region
    assert body.count("## Commentary & Analysis") == 1
    assert body.index(LAWBRAIN_REGION_BEGIN) < body.index("## Commentary & Analysis")


def test_render_bill_body_omits_region_for_body_none_source() -> None:
    bill = _bill()
    # refresh-carried metadata: body is None, so no region should render
    bill.commentary_sources = [_source(slug="x-rule", body=None)]
    body = render_bill_body(bill)
    assert LAWBRAIN_REGION_BEGIN not in body
    assert "## Commentary & Analysis" not in body


def test_render_enforcement_body_appends_region_after_sources() -> None:
    action = EnforcementAction(
        id="us-ftc-2025-acme",
        jurisdiction="US",
        agency="FTC",
        title="In re Acme",
        summary="A matter.",
        sources={"FTC": "https://www.ftc.gov/acme"},
    )
    action.commentary_sources = [_source(slug="acme-rule", body="Commentary.")]
    body = render_enforcement_body(action)
    assert LAWBRAIN_REGION_BEGIN in body
    assert body.index("## Sources") < body.index(LAWBRAIN_REGION_BEGIN)
```

Run it, expecting FAIL:

```
uv run pytest tests/test_lawbrain_render.py::test_render_bill_body_appends_region_after_sources -v
```

Expected: FAIL — `AssertionError: assert LAWBRAIN_REGION_BEGIN in body` (commentary still renders inline as a section, region markers absent).

---

- [ ] **Step 8: Move Commentary out of the section list and append the region last.**

In `src/zwiadbrain/wiki/templates.py`, remove the inline `Commentary & Analysis` section from `render_bill_body` (delete this block):

```python
    if bill.commentary_sources:
        sections.append(
            {"heading": "Commentary & Analysis", "body": _commentary(bill.commentary_sources)}
        )
```

Then change the tail of `render_bill_body` from:

```python
    body = _BODY.render(sections=sections)
    if bill.flipped_out:
```

to:

```python
    body = _BODY.render(sections=sections)
    region = _lawbrain_region([s for s in bill.commentary_sources if s.body])
    if region:
        body = body + "\n\n" + region
    if bill.flipped_out:
```

In `render_enforcement_body`, remove the inline section block:

```python
    if action.commentary_sources:
        sections.append(
            {"heading": "Commentary & Analysis", "body": _commentary(action.commentary_sources)}
        )
```

and change the final line from:

```python
    return _BODY.render(sections=sections)
```

to:

```python
    body = _BODY.render(sections=sections)
    region = _lawbrain_region([s for s in action.commentary_sources if s.body])
    if region:
        body = body + "\n\n" + region
    return body
```

Run the placement tests, expecting PASS:

```
uv run pytest tests/test_lawbrain_render.py -v
```

Expected: PASS (all tests in the file pass).

---

- [ ] **Step 9: Write a failing test for `preserve_lawbrain_region`.**

`preserve_lawbrain_region(prev_text, fresh_text)` is the D63 splice: if `fresh_text` already has a region it is authoritative (returned unchanged); else the region is extracted from `prev_text` (begin..end inclusive) and appended to `fresh_text` preserving a single trailing newline; if `prev_text` has no region, `fresh_text` is returned unchanged.

Create `tests/test_region_preservation.py`:

```python
"""D63 regression guard: a non-sync re-render must not strip a committed region.

``preserve_lawbrain_region`` splices a prior page's ``lawbrain:region`` block
forward verbatim onto a freshly rendered body that lacks one, so that
``render-refreshed`` (and any other non-sync render path) keeps committed
commentary and Further Reading byte-identical.
"""

from zwiadbrain.wiki.templates import (
    LAWBRAIN_REGION_BEGIN,
    LAWBRAIN_REGION_END,
    preserve_lawbrain_region,
)

_REGION = (
    f"{LAWBRAIN_REGION_BEGIN}\n"
    "## Commentary & Analysis\n\n"
    "<!-- lawbrain:begin slug=x-rule -->\n"
    "> Source: law brain page `x-rule`.\n"
    "> Copied verbatim.\n\n"
    "Analysis body.\n"
    "<!-- lawbrain:end slug=x-rule -->\n\n"
    "## Further Reading (via law brain)\n\n"
    "- [Ref](https://ref.example/a)\n"
    f"{LAWBRAIN_REGION_END}"
)


def test_prev_region_spliced_onto_fresh_without_region() -> None:
    prev = f"---\ntitle: A\n---\n\n## Summary\n\nOld.\n\n## Sources\n\n- x\n\n{_REGION}\n"
    fresh = "---\ntitle: A\n---\n\n## Summary\n\nNew.\n\n## Sources\n\n- x\n"
    result = preserve_lawbrain_region(prev, fresh)
    # fresh body retained, region appended verbatim, single trailing newline
    assert result == fresh.rstrip("\n") + "\n\n" + _REGION + "\n"
    assert _REGION in result
    assert result.endswith(_REGION + "\n")


def test_prev_without_region_leaves_fresh_unchanged() -> None:
    prev = "---\ntitle: A\n---\n\n## Summary\n\nOld.\n"
    fresh = "---\ntitle: A\n---\n\n## Summary\n\nNew.\n"
    assert preserve_lawbrain_region(prev, fresh) == fresh


def test_fresh_with_region_is_authoritative() -> None:
    # a sync render produced its own region: prev region must be ignored
    prev = f"---\ntitle: A\n---\n\n## Sources\n\n- x\n\n{_REGION}\n"
    fresh_region = _REGION.replace("Analysis body.", "Updated analysis.")
    fresh = f"---\ntitle: A\n---\n\n## Sources\n\n- x\n\n{fresh_region}\n"
    assert preserve_lawbrain_region(prev, fresh) == fresh
```

Run it, expecting FAIL:

```
uv run pytest tests/test_region_preservation.py::test_prev_region_spliced_onto_fresh_without_region -v
```

Expected: FAIL — `ImportError: cannot import name 'preserve_lawbrain_region'`.

---

- [ ] **Step 10: Implement `preserve_lawbrain_region`.**

Add it at the end of `src/zwiadbrain/wiki/templates.py`:

```python
def preserve_lawbrain_region(prev_text: str, fresh_text: str) -> str:
    """Splice a prior page's ``lawbrain:region`` block forward onto a fresh body.

    This is the body-level analog of ``preserve_leg_history`` (D63). A non-sync
    render (e.g. ``render-refreshed``) produces ``fresh_text`` WITHOUT a region,
    since the item carries commentary metadata with ``body=None``; this re-attaches
    the committed region verbatim so the data is not lost.

    - If ``fresh_text`` already contains a region, it is authoritative — returned
      unchanged (the sync path owns create/update/remove of the region).
    - Else, the begin..end block is extracted from ``prev_text`` (inclusive) and
      appended to ``fresh_text``, preserving a single trailing newline.
    - If ``prev_text`` has no region, ``fresh_text`` is returned unchanged.
    """
    if LAWBRAIN_REGION_BEGIN in fresh_text:
        return fresh_text
    begin = prev_text.find(LAWBRAIN_REGION_BEGIN)
    if begin == -1:
        return fresh_text
    end = prev_text.find(LAWBRAIN_REGION_END, begin)
    if end == -1:
        return fresh_text
    region = prev_text[begin : end + len(LAWBRAIN_REGION_END)]
    return fresh_text.rstrip("\n") + "\n\n" + region + "\n"
```

Run the preservation tests, expecting PASS:

```
uv run pytest tests/test_region_preservation.py -v
```

Expected: PASS (3 passed).

---

- [ ] **Step 11: Write a failing test for `write_page` central preservation.**

`write_page` must read the existing file and apply `preserve_lawbrain_region` before the compare-then-write, so a refresh that drops the region (item carries `body=None` commentary) does not strip it from disk. Create the test in `tests/test_region_preservation.py` (append):

```python
import datetime as dt
from pathlib import Path

from zwiadbrain.models import Bill, CommentaryLink, CommentarySource
from zwiadbrain.pipeline.render import page_path, render_page, write_page
from zwiadbrain.wiki.templates import LAWBRAIN_REGION_BEGIN


def _commentary_bill() -> Bill:
    return Bill(
        id="us-119-hr-1",
        jurisdiction="US",
        bill_number="HR 1",
        title="An Act",
        summary="A summary.",
        sources={"Congress.gov": "https://www.congress.gov/bill/119/hr/1"},
    )


def test_write_page_preserves_region_across_body_none_refresh(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    # 1. initial sync render: bill carries a commentary source WITH a body -> region committed
    synced = _commentary_bill()
    synced.commentary_sources = [
        CommentarySource(
            path="wiki/regulation-x.md",
            slug="x-rule",
            updated=dt.date(2026, 5, 1),
            content_hash="hash1",
            matched_by="deterministic",
            confidence=1.0,
            body="## Analysis\n\nCommentary body.",
            links=[CommentaryLink(text="Ref", url="https://ref.example/a")],
        )
    ]
    assert write_page(synced, wiki) is True
    committed = page_path(synced, wiki).read_text(encoding="utf-8")
    assert LAWBRAIN_REGION_BEGIN in committed

    # 2. a refresh re-render carries the SAME source as metadata-only (body=None)
    refreshed = _commentary_bill()
    refreshed.summary = "An updated summary."
    refreshed.commentary_sources = [
        CommentarySource(
            path="wiki/regulation-x.md",
            slug="x-rule",
            updated=dt.date(2026, 5, 1),
            content_hash="hash1",
            matched_by="deterministic",
            confidence=1.0,
            body=None,
            links=[],
        )
    ]
    # render_page alone (no preservation) drops the region — proves the hazard
    assert LAWBRAIN_REGION_BEGIN not in render_page(refreshed)

    # write_page preserves it centrally
    assert write_page(refreshed, wiki) is True
    after = page_path(refreshed, wiki).read_text(encoding="utf-8")
    assert LAWBRAIN_REGION_BEGIN in after
    assert "An updated summary." in after
    assert "Commentary body." in after
```

Run it, expecting FAIL:

```
uv run pytest tests/test_region_preservation.py::test_write_page_preserves_region_across_body_none_refresh -v
```

Expected: FAIL — `AssertionError: assert LAWBRAIN_REGION_BEGIN in after` (current `write_page` writes `render_page(refreshed)` straight to disk, stripping the region).

---

- [ ] **Step 12: Wire central preservation into `write_page`.**

In `src/zwiadbrain/pipeline/render.py`, add the import and read-prev-then-preserve step before compare-then-write.

Change the import line:

```python
from zwiadbrain.wiki.templates import render_bill_body, render_enforcement_body
```

to:

```python
from zwiadbrain.wiki.templates import (
    preserve_lawbrain_region,
    render_bill_body,
    render_enforcement_body,
)
```

Change `write_page` from:

```python
def write_page(item: Bill | EnforcementAction, wiki_root: Path) -> bool:
    """Write the rendered page, skipping the write when content is unchanged.

    Returns True if the file was created or changed, False if already up to date,
    so an unchanged scan leaves a clean ``git status``.
    """
    path = page_path(item, wiki_root)
    content = render_page(item)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True
```

to:

```python
def write_page(item: Bill | EnforcementAction, wiki_root: Path) -> bool:
    """Write the rendered page, skipping the write when content is unchanged.

    Returns True if the file was created or changed, False if already up to date,
    so an unchanged scan leaves a clean ``git status``.

    Central D63 preservation: when the page already exists, a committed
    ``lawbrain:region`` is spliced forward onto the freshly rendered body unless
    the item supplies its own region (i.e. carries commentary bodies). Every
    render path therefore keeps committed commentary/Further Reading intact;
    only ``/zwiad-sync-lawbrain`` creates, updates, or removes the region.
    """
    path = page_path(item, wiki_root)
    content = render_page(item)
    if path.exists():
        prev_text = path.read_text(encoding="utf-8")
        content = preserve_lawbrain_region(prev_text, content)
        if prev_text == content:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True
```

Run the full preservation suite plus the render suite, expecting PASS:

```
uv run pytest tests/test_region_preservation.py tests/test_lawbrain_render.py -v
```

Expected: PASS (all tests pass).

---

- [ ] **Step 13: Guard against regressions in the existing renderer/refresh suites.**

The section reshuffle and the `write_page` change touch shared rendering paths, so run the existing renderer, refresh, and render-page tests to confirm no regression:

```
uv run pytest tests/test_templates.py tests/test_render.py tests/pipeline -v
```

Expected: PASS (existing suites green; if a fixture asserted the old inline `## Commentary & Analysis` ordering, that is intentional behavior change — see the section move in Step 8 — and the fixture must be updated to expect the region-last placement, not the implementation reverted).

---

- [ ] **Step 14: Lint and type-check the touched modules.**

```
uv run ruff check src/zwiadbrain/wiki/templates.py src/zwiadbrain/pipeline/render.py tests/test_lawbrain_render.py tests/test_region_preservation.py
uv run pyright src/zwiadbrain/wiki/templates.py src/zwiadbrain/pipeline/render.py
```

Expected: ruff reports no issues; pyright reports no new errors (the pre-existing `frontmatter` stub warning in `render.py` is known infrastructure debt and not introduced here).

---

- [ ] **Step 15: Commit.**

```
git add src/zwiadbrain/wiki/templates.py src/zwiadbrain/pipeline/render.py tests/test_lawbrain_render.py tests/test_region_preservation.py
git commit -m "feat(lawbrain): render commentary region last and preserve it across non-sync renders (D63)"
```

The commit must land green: `uv run pytest tests/test_lawbrain_render.py tests/test_region_preservation.py -v` passing before committing.

---

I have enough context. The repo uses `import yaml` with `yaml.safe_load`/`yaml.YAMLError`, pydantic v2 `model_dump(mode="json", exclude_none=True)`, `datetime as dt`, and `ConfigError`/`LawBrainError` exceptions. Now I'll write the Task 8 markdown section.

### Task 8: Registry — pipeline/lawbrain_registry.py (links.yaml)

**Files:**
- Create: `src/zwiadbrain/pipeline/lawbrain_registry.py`
- Test: `tests/test_lawbrain_registry.py`

The registry is the durable record of "we already decided about this law-brain page." Each `LinkDecision` is keyed by `lawbrain_slug` and carries a `keys_hash` snapshot (D9). `decision_for` always returns the stored decision verbatim — it does NOT decide for the caller whether the decision is still valid. The caller (the `fetch-lawbrain-candidates` CLI) compares the *current* `keys_hash` of the page against the stored decision's `keys_hash`: equal -> sticky, skip; different -> the underlying keys changed, so re-evaluate. Keeping the staleness comparison in the caller (not in the registry) means the registry stays a dumb persistent store and the D9 stickiness rule lives in exactly one place.

YAML shape (`wiki/links.yaml`):
```yaml
links:
  - lawbrain_slug: regulation-california-sb53-tfaia
    decision: link
    target_id: ca-2025-sb-53
    matched_by: deterministic
    keys_hash: 3f1a9c...
    decided: 2026-05-29
  - lawbrain_slug: regulation-gdpr
    decision: not_in_scope
    target_id: null
    matched_by: null
    keys_hash: 9c0b2d...
    decided: 2026-05-29
```

Mirror the YAML idioms already in the repo: `import yaml`, `yaml.safe_load`, guard `yaml.YAMLError`, raise the project exception (`LawBrainError`), and use pydantic v2 `model_dump(mode="json", exclude_none=False)` so `target_id: null` round-trips explicitly.

---

- [ ] **Step 1: Write the failing test file.**

Create `tests/test_lawbrain_registry.py` with the complete test suite. These cover: `decision_for` returns a recorded decision; `decision_for` returns `None` for an unknown slug; a re-`record` of the same slug replaces (not duplicates) the prior decision; the keys_hash-unchanged sticky path and the keys_hash-changed re-evaluate path are both exercised by the caller-style comparison; `load` of a missing file yields an empty registry; `dump`/`load` round-trips every field including `target_id: null` and the `decided` date; and malformed YAML raises `LawBrainError`.

```python
"""Tests for the law-brain link-decision registry (wiki/links.yaml).

The registry is a dumb persistent store of prior link decisions keyed by
lawbrain_slug. Stickiness (D9) is enforced by the *caller* comparing a page's
current keys_hash against the stored decision's keys_hash — the registry itself
never decides staleness, it only stores and returns decisions verbatim.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from zwiadbrain.exceptions import LawBrainError
from zwiadbrain.pipeline.lawbrain_registry import LinkDecision, LinkRegistry


def _decision(
    *,
    slug: str = "bill-us-hr-1234",
    decision: str = "link",
    target_id: str | None = "us-hr-1234",
    matched_by: str | None = "deterministic",
    keys_hash: str = "hash-aaa",
    decided: dt.date | None = dt.date(2026, 5, 29),
) -> LinkDecision:
    return LinkDecision(
        lawbrain_slug=slug,
        decision=decision,  # type: ignore[arg-type]
        target_id=target_id,
        matched_by=matched_by,
        keys_hash=keys_hash,
        decided=decided,
    )


def test_should_return_recorded_decision_when_slug_was_decided() -> None:
    # Arrange
    registry = LinkRegistry.load(Path("does-not-exist.yaml"))
    decision = _decision()
    registry.record(decision)

    # Act
    found = registry.decision_for("bill-us-hr-1234")

    # Assert
    assert found is not None
    assert found.target_id == "us-hr-1234"
    assert found.decision == "link"
    assert found.keys_hash == "hash-aaa"


def test_should_return_none_when_slug_was_never_decided() -> None:
    # Arrange
    registry = LinkRegistry.load(Path("does-not-exist.yaml"))

    # Act / Assert
    assert registry.decision_for("bill-unknown-slug") is None


def test_should_replace_in_place_when_recording_same_slug_twice() -> None:
    # Arrange
    registry = LinkRegistry.load(Path("does-not-exist.yaml"))
    registry.record(_decision(decision="not_in_scope", target_id=None, matched_by=None))

    # Act — re-decide the same slug as a confirmed link
    registry.record(_decision(decision="link", target_id="us-hr-1234"))
    found = registry.decision_for("bill-us-hr-1234")

    # Assert — one entry, updated, not duplicated
    assert found is not None
    assert found.decision == "link"
    assert found.target_id == "us-hr-1234"


def test_should_be_sticky_when_keys_hash_is_unchanged() -> None:
    # Arrange — a prior decision and a page whose keys still hash the same
    registry = LinkRegistry.load(Path("does-not-exist.yaml"))
    registry.record(_decision(keys_hash="hash-stable"))
    current_keys_hash = "hash-stable"

    # Act — the caller's stickiness check (D9): same hash => reuse decision
    prior = registry.decision_for("bill-us-hr-1234")
    assert prior is not None
    is_sticky = prior.keys_hash == current_keys_hash

    # Assert
    assert is_sticky is True


def test_should_signal_reevaluation_when_keys_hash_changed() -> None:
    # Arrange — page keys changed since the decision was recorded
    registry = LinkRegistry.load(Path("does-not-exist.yaml"))
    registry.record(_decision(keys_hash="hash-old"))
    current_keys_hash = "hash-new"

    # Act — decision_for still returns the stored decision verbatim...
    prior = registry.decision_for("bill-us-hr-1234")
    assert prior is not None
    # ...and the caller compares hashes to decide staleness.
    is_sticky = prior.keys_hash == current_keys_hash

    # Assert — different hash => caller must re-evaluate
    assert is_sticky is False
    assert prior.keys_hash == "hash-old"


def test_should_round_trip_every_field_through_dump_and_load(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "links.yaml"
    registry = LinkRegistry.load(path)
    registry.record(_decision(slug="bill-us-hr-1234"))
    registry.record(
        _decision(
            slug="bill-eu-gdpr-overview",
            decision="not_in_scope",
            target_id=None,
            matched_by=None,
            keys_hash="hash-bbb",
            decided=dt.date(2026, 4, 1),
        )
    )

    # Act
    registry.dump(path)
    reloaded = LinkRegistry.load(path)

    # Assert — link decision survives intact
    link = reloaded.decision_for("bill-us-hr-1234")
    assert link is not None
    assert link.decision == "link"
    assert link.target_id == "us-hr-1234"
    assert link.matched_by == "deterministic"
    assert link.keys_hash == "hash-aaa"
    assert link.decided == dt.date(2026, 5, 29)

    # Assert — not_in_scope decision with explicit null target survives intact
    nis = reloaded.decision_for("bill-eu-gdpr-overview")
    assert nis is not None
    assert nis.decision == "not_in_scope"
    assert nis.target_id is None
    assert nis.matched_by is None
    assert nis.decided == dt.date(2026, 4, 1)


def test_should_yield_empty_registry_when_file_is_missing(tmp_path: Path) -> None:
    # Arrange / Act
    registry = LinkRegistry.load(tmp_path / "absent.yaml")

    # Assert
    assert registry.decision_for("anything") is None


def test_should_yield_empty_registry_when_file_has_no_links_key(tmp_path: Path) -> None:
    # Arrange — a valid-but-empty YAML document
    path = tmp_path / "links.yaml"
    path.write_text("links: []\n", encoding="utf-8")

    # Act
    registry = LinkRegistry.load(path)

    # Assert
    assert registry.decision_for("anything") is None


def test_should_raise_lawbrain_error_when_yaml_is_malformed(tmp_path: Path) -> None:
    # Arrange — unbalanced bracket is not parseable YAML
    path = tmp_path / "links.yaml"
    path.write_text("links: [unterminated\n", encoding="utf-8")

    # Act / Assert
    with pytest.raises(LawBrainError):
        LinkRegistry.load(path)
```

- [ ] **Step 2: Run the test and confirm it FAILS.**

```
uv run pytest tests/test_lawbrain_registry.py -v
```

Expected: collection error / FAIL — `ModuleNotFoundError: No module named 'zwiadbrain.pipeline.lawbrain_registry'` (the module and its `LinkDecision` / `LinkRegistry` symbols do not exist yet).

- [ ] **Step 3: Write the minimal implementation.**

Create `src/zwiadbrain/pipeline/lawbrain_registry.py` with the complete module. `load` is a classmethod that tolerates a missing file (empty registry) and raises `LawBrainError` on unparseable YAML, mirroring `reference/loader.py`. `record` replaces any existing entry for the same slug (dict keyed by slug preserves last-write-wins and prevents duplicates). `dump` writes the `links:` list with deterministic, slug-sorted ordering and explicit nulls so `not_in_scope` round-trips. The keys_hash staleness comparison deliberately lives in the caller, not here (D9).

```python
"""Durable registry of law-brain link decisions (``wiki/links.yaml``).

A :class:`LinkDecision` is the persistent record of "we already decided about
this law-brain page": link it to a tracked target, mark it out of scope, or
reject it. Each decision snapshots the page's ``keys_hash`` at decision time.

Stickiness (D9) is enforced by the *caller*, not here: ``decision_for`` returns
the stored decision verbatim, and the caller compares the page's current
``keys_hash`` against ``decision.keys_hash`` — equal means reuse the decision,
different means the underlying keys moved and the page must be re-evaluated.
Keeping that comparison in the caller leaves this module a dumb store and the
staleness rule expressed in exactly one place (the ``fetch-lawbrain-candidates``
half).

The on-disk shape is a single ``links:`` list under the YAML root, mirroring the
``topics.yaml`` loader idiom (``yaml.safe_load`` + a pydantic model, with
``yaml.YAMLError`` mapped to a project exception).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

from zwiadbrain.exceptions import LawBrainError


class LinkDecision(BaseModel):
    """One recorded decision about a single law-brain page.

    ``keys_hash`` is the hash of the page's extracted keys at decision time; the
    caller compares it against the page's current keys_hash to honor D9.
    """

    lawbrain_slug: str
    decision: Literal["link", "not_in_scope", "reject"]
    target_id: str | None = None
    matched_by: str | None = None
    keys_hash: str
    decided: dt.date | None = None


class LinkRegistry:
    """In-memory view of ``wiki/links.yaml`` keyed by ``lawbrain_slug``."""

    def __init__(self, decisions: list[LinkDecision] | None = None) -> None:
        # Keyed by slug so record() is last-write-wins and never duplicates.
        self._by_slug: dict[str, LinkDecision] = {
            d.lawbrain_slug: d for d in (decisions or [])
        }

    @classmethod
    def load(cls, path: Path) -> LinkRegistry:
        """Load decisions from *path*.

        A missing file yields an empty registry (first run). Unparseable YAML or a
        malformed ``links`` entry raises :class:`LawBrainError`.
        """
        if not path.exists():
            return cls([])
        try:
            raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise LawBrainError(f"link registry is not valid YAML: {path}") from exc
        if raw is None:
            return cls([])
        if not isinstance(raw, dict):
            raise LawBrainError(f"link registry must be a YAML mapping: {path}")
        entries = raw.get("links") or []
        if not isinstance(entries, list):
            raise LawBrainError(f"link registry 'links' must be a list: {path}")
        try:
            decisions = [LinkDecision.model_validate(entry) for entry in entries]
        except Exception as exc:  # noqa: BLE001 — boundary: surface any malformed entry as LawBrainError
            raise LawBrainError(f"link registry is malformed: {path}\n{exc}") from exc
        return cls(decisions)

    def decision_for(self, slug: str) -> LinkDecision | None:
        """Return the stored decision for *slug*, or ``None`` if never decided.

        Returns the decision verbatim — staleness (the keys_hash comparison) is the
        caller's responsibility, not this method's.
        """
        return self._by_slug.get(slug)

    def record(self, decision: LinkDecision) -> None:
        """Insert or replace the decision for ``decision.lawbrain_slug`` in place."""
        self._by_slug[decision.lawbrain_slug] = decision

    def dump(self, path: Path) -> None:
        """Write all decisions to *path* as a slug-sorted ``links:`` list.

        ``exclude_none=False`` keeps ``target_id: null`` / ``matched_by: null``
        explicit so out-of-scope decisions round-trip through ``load``.
        """
        ordered = sorted(self._by_slug.values(), key=lambda d: d.lawbrain_slug)
        payload = {
            "links": [d.model_dump(mode="json", exclude_none=False) for d in ordered]
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
```

- [ ] **Step 4: Run the test and confirm it PASSES.**

```
uv run pytest tests/test_lawbrain_registry.py -v
```

Expected: PASS — all nine tests green (`test_should_return_recorded_decision_when_slug_was_decided`, `test_should_return_none_when_slug_was_never_decided`, `test_should_replace_in_place_when_recording_same_slug_twice`, `test_should_be_sticky_when_keys_hash_is_unchanged`, `test_should_signal_reevaluation_when_keys_hash_changed`, `test_should_round_trip_every_field_through_dump_and_load`, `test_should_yield_empty_registry_when_file_is_missing`, `test_should_yield_empty_registry_when_file_has_no_links_key`, `test_should_raise_lawbrain_error_when_yaml_is_malformed`).

- [ ] **Step 5: Lint and type-check the new files.**

```
uv run ruff check src/zwiadbrain/pipeline/lawbrain_registry.py tests/test_lawbrain_registry.py
uv run pyright src/zwiadbrain/pipeline/lawbrain_registry.py tests/test_lawbrain_registry.py
```

Expected: ruff reports no issues; pyright reports 0 errors, 0 warnings.

- [ ] **Step 6: Commit.**

```
git add src/zwiadbrain/pipeline/lawbrain_registry.py tests/test_lawbrain_registry.py
git commit -m "feat(lawbrain): add LinkRegistry for sticky link decisions in links.yaml"
```

---

I have enough to match the repo idioms: pydantic v2 `BaseModel`, `from __future__ import annotations`, `Literal` types, module docstring style, regex-based parsing, and the pytest test style (flat module-level functions, descriptive names, AAA structure). Now I'll write the Task 9 markdown section.

### Task 9: Review queue — pipeline/lawbrain_review.py (review-queue.md)

**Files:**
- Create: `src/zwiadbrain/pipeline/lawbrain_review.py`
- Test: `tests/test_review_queue.py`

This task builds the **pure** review-queue model plus its render/parse round-trip. No I/O — the render half (Task 18) reads `wiki/review-queue.md` from disk and feeds the text to `parse_review_queue`, then writes `render_review_queue` back. The contract: `render_review_queue` then `parse_review_queue` round-trips exactly, and the operator-flippable status token `[pending]` / `[accept]` / `[reject]` parses back to the right `status`.

The review-queue line format (matches spec §5.6 — "`[pending]` slug -> target_id (reason)"):

```
- [pending] regulation-take-it-down-act -> ftc-2026-nudify-tool-operators (weak-grounding)
- [accept] regulation-foo -> ftc-2026-bar (collision)
- [reject] concept-state-ai-chatbot-tracker -> None (low-confidence)
```

`target_id` renders as the literal `None` when it is `None` (a stale/unmatched entry can have no target). The four `reason` values are `low-confidence`, `collision`, `weak-grounding`, `stale`; the three `status` values are `pending`, `accept`, `reject`.

---

- [ ] **Step 1: Write the failing test file.**

Create `tests/test_review_queue.py` with the complete test code:

```python
from zwiadbrain.pipeline.lawbrain_review import (
    ReviewEntry,
    parse_review_queue,
    render_review_queue,
)


def test_review_entry_defaults_to_pending_status() -> None:
    # Arrange / Act
    entry = ReviewEntry(
        slug="regulation-take-it-down-act",
        target_id="ftc-2026-nudify-tool-operators",
        reason="weak-grounding",
    )
    # Assert
    assert entry.status == "pending"


def test_render_review_queue_emits_one_checklist_line_per_entry() -> None:
    # Arrange
    entries = [
        ReviewEntry(
            slug="regulation-take-it-down-act",
            target_id="ftc-2026-nudify-tool-operators",
            reason="weak-grounding",
        ),
        ReviewEntry(
            slug="concept-state-ai-chatbot-tracker",
            target_id=None,
            reason="low-confidence",
        ),
    ]
    # Act
    text = render_review_queue(entries)
    # Assert
    assert text.splitlines() == [
        "- [pending] regulation-take-it-down-act -> ftc-2026-nudify-tool-operators (weak-grounding)",
        "- [pending] concept-state-ai-chatbot-tracker -> None (low-confidence)",
    ]


def test_render_then_parse_round_trips() -> None:
    # Arrange
    entries = [
        ReviewEntry(
            slug="regulation-take-it-down-act",
            target_id="ftc-2026-nudify-tool-operators",
            reason="weak-grounding",
            status="pending",
        ),
        ReviewEntry(
            slug="regulation-collision-foo",
            target_id="ftc-2026-bar",
            reason="collision",
            status="pending",
        ),
        ReviewEntry(
            slug="concept-state-ai-chatbot-tracker",
            target_id=None,
            reason="stale",
            status="pending",
        ),
    ]
    # Act
    parsed = parse_review_queue(render_review_queue(entries))
    # Assert
    assert parsed == entries


def test_parse_review_queue_reads_accept_and_reject_tokens() -> None:
    # Arrange
    text = "\n".join(
        [
            "- [accept] regulation-california-sb53-tfaia -> ca-2025-sb-53 (collision)",
            "- [reject] concept-state-ai-chatbot-tracker -> None (low-confidence)",
        ]
    )
    # Act
    parsed = parse_review_queue(text)
    # Assert
    assert parsed[0].status == "accept"
    assert parsed[0].slug == "regulation-california-sb53-tfaia"
    assert parsed[0].target_id == "ca-2025-sb-53"
    assert parsed[0].reason == "collision"
    assert parsed[1].status == "reject"
    assert parsed[1].target_id is None
    assert parsed[1].reason == "low-confidence"


def test_parse_review_queue_ignores_blank_and_non_entry_lines() -> None:
    # Arrange — a header and a blank line surround a single real entry
    text = "\n".join(
        [
            "# Review queue",
            "",
            "- [pending] regulation-take-it-down-act -> ftc-2026-nudify-tool-operators (stale)",
            "",
        ]
    )
    # Act
    parsed = parse_review_queue(text)
    # Assert
    assert len(parsed) == 1
    assert parsed[0].slug == "regulation-take-it-down-act"
    assert parsed[0].status == "pending"


def test_render_review_queue_empty_returns_empty_string() -> None:
    # Arrange / Act / Assert
    assert render_review_queue([]) == ""
```

---

- [ ] **Step 2: Run the test, expect FAIL (module does not exist).**

```
uv run pytest tests/test_review_queue.py -v
```

Expected: collection/import error — `ModuleNotFoundError: No module named 'zwiadbrain.pipeline.lawbrain_review'` (all six tests error out, none pass).

---

- [ ] **Step 3: Write the implementation.**

Create `src/zwiadbrain/pipeline/lawbrain_review.py` with the complete code:

```python
"""Review queue for uncertain law-brain commentary proposals (PHASE-09, D61).

A pure render/parse pair over the committed-but-transient ``wiki/review-queue.md``
checklist. Uncertain proposals (low-confidence, key collision, LLM weak-grounding,
or a stale source page) are emitted as ``[pending]`` lines; the operator flips a
line to ``[accept]`` or ``[reject]`` and the render half (``render-lawbrain-commentary``)
reads the resolved tokens back, applies them, and prunes the queue in one pass.

This module does no I/O: it converts between a list of :class:`ReviewEntry` and the
markdown text. The render half owns reading/writing the file.

Line format (one checklist item per entry)::

    - [pending] regulation-take-it-down-act -> ftc-2026-nudify-tool-operators (weak-grounding)

``target_id`` renders as the literal ``None`` when an entry has no target (e.g. a
``stale`` block whose source page vanished). Lines that do not match the format
(headers, blanks, prose) are ignored on parse, so the operator can annotate freely.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

ReviewReason = Literal["low-confidence", "collision", "weak-grounding", "stale"]
ReviewStatus = Literal["pending", "accept", "reject"]


class ReviewEntry(BaseModel):
    slug: str
    target_id: str | None
    reason: ReviewReason
    status: ReviewStatus = "pending"


# - [<status>] <slug> -> <target_id> (<reason>)
# target_id is a token run (no spaces) or the literal "None"; reason is one of the
# fixed set. The capture groups partition a well-formed line losslessly.
_ENTRY_RE = re.compile(
    r"^- \[(pending|accept|reject)\] (\S+) -> (\S+) "
    r"\((low-confidence|collision|weak-grounding|stale)\)$"
)


def render_review_queue(entries: list[ReviewEntry]) -> str:
    """Render *entries* as a markdown checklist, one ``- [status] ...`` line each.

    Entries are rendered in the order given (the render half decides ordering).
    A ``None`` *target_id* renders as the literal ``None``. Returns the empty
    string for an empty list (no trailing newline to add).
    """
    return "\n".join(
        f"- [{e.status}] {e.slug} -> {e.target_id if e.target_id is not None else 'None'} "
        f"({e.reason})"
        for e in entries
    )


def parse_review_queue(text: str) -> list[ReviewEntry]:
    """Parse review-queue markdown back into :class:`ReviewEntry` objects.

    The inverse of :func:`render_review_queue` for well-formed lines. Lines that do
    not match the checklist format (headers, blank lines, free-form notes) are
    skipped, so the file may carry an operator-authored header without breaking the
    round-trip. The literal ``None`` token parses back to ``target_id=None``.
    """
    entries: list[ReviewEntry] = []
    for line in text.splitlines():
        match = _ENTRY_RE.match(line.rstrip())
        if match is None:
            continue
        status, slug, raw_target, reason = match.groups()
        target_id = None if raw_target == "None" else raw_target
        entries.append(
            ReviewEntry(
                slug=slug,
                target_id=target_id,
                reason=reason,  # type: ignore[arg-type]  # regex alternation guarantees a valid ReviewReason
                status=status,  # type: ignore[arg-type]  # regex alternation guarantees a valid ReviewStatus
            )
        )
    return entries
```

---

- [ ] **Step 4: Run the test, expect PASS.**

```
uv run pytest tests/test_review_queue.py -v
```

Expected: all six tests pass — `test_review_entry_defaults_to_pending_status`, `test_render_review_queue_emits_one_checklist_line_per_entry`, `test_render_then_parse_round_trips`, `test_parse_review_queue_reads_accept_and_reject_tokens`, `test_parse_review_queue_ignores_blank_and_non_entry_lines`, `test_render_review_queue_empty_returns_empty_string`.

Then confirm the new module is clean under the project's static gates (the `type: ignore` comments narrow the regex-alternation strings to their `Literal` types, matching the repo's pattern of explaining each suppression inline):

```
uv run ruff check src/zwiadbrain/pipeline/lawbrain_review.py tests/test_review_queue.py
uv run pyright --strict src/zwiadbrain/pipeline/lawbrain_review.py
```

Expected: ruff reports `All checks passed!`; pyright reports `0 errors, 0 warnings, 0 informations`.

---

- [ ] **Step 5: Commit.**

```
git add src/zwiadbrain/pipeline/lawbrain_review.py tests/test_review_queue.py
git commit -m "feat(lawbrain): add review-queue render/parse round-trip"
```

Expected: one commit on the current feature branch containing the new module and its test file.

---

I have everything I need. The `.env.example` already contains `LAW_BRAIN_PATH`, and `zwiadbrain.toml` already has most of the `[lawbrain]` block — I need to add `primary_source_domains` and `further_reading` there, and add the two new fields to `LawBrainSettings`. Let me write the task section.

### Task 10: Config + TOML

**Files:**
- Modify: `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\config.py` (add `further_reading` + `primary_source_domains` to `LawBrainSettings`)
- Modify: `C:\Users\rafst\documents\projectas\zwiadbrain\zwiadbrain.toml` (extend `[lawbrain]` block)
- Modify: `C:\Users\rafst\documents\projectas\zwiadbrain\.env.example` (verify `LAW_BRAIN_PATH` present + add `[lawbrain]` Further Reading pointer comment)
- Test: `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_config.py` (add cases for new fields + defaults)

Note on existing state (read these before editing — they are already partially populated): `LawBrainSettings` in `config.py` (lines 85-97) already has `enabled/path/min_confidence/require_shared_key/demote_headings/commentary/discover/commentary_only_types/commentary_only_slug_markers/type_map`. `zwiadbrain.toml` already has the `[lawbrain]` block (lines 21-40) and `[lawbrain.type_map]`. `.env.example` (line 16) already has `LAW_BRAIN_PATH`. This task ONLY adds the two new fields and the matching TOML keys — do not rebuild what exists.

---

- [ ] **Step 1: Write failing test — `further_reading` and `primary_source_domains` defaults.**

This locks the new defaults specified in the contract: `further_reading=True` and the 6-element `primary_source_domains` denylist. Append both tests to `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_config.py` (after the existing `test_lawbrain_rejects_out_of_range_min_confidence`, keeping the file's existing import block and `_write`/`_TOML` helpers).

```python
def test_lawbrain_further_reading_defaults_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should default [lawbrain].further_reading to True when the TOML omits it"""
    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    toml_path, env_path = _write(tmp_path)
    settings = load_settings(toml_path=toml_path, env_file=env_path)
    assert settings.lawbrain.further_reading is True


def test_lawbrain_primary_source_domains_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should default [lawbrain].primary_source_domains to the built-in denylist"""
    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    toml_path, env_path = _write(tmp_path)
    settings = load_settings(toml_path=toml_path, env_file=env_path)
    assert settings.lawbrain.primary_source_domains == [
        ".gov",
        "legiscan.com",
        "courtlistener.com",
        "wikipedia.org",
        "europa.eu",
        "legislation.gov.uk",
    ]
```

- [ ] **Step 2: Run the new tests — expect FAIL.**

```
uv run pytest "tests/test_config.py::test_lawbrain_further_reading_defaults_true" "tests/test_config.py::test_lawbrain_primary_source_domains_default" -v
```

Expected: both FAIL with `AttributeError: 'LawBrainSettings' object has no attribute 'further_reading'` (and `... 'primary_source_domains'`), because those fields do not yet exist on the model.

- [ ] **Step 3: Add the two fields to `LawBrainSettings` — minimal implementation.**

In `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\config.py`, replace the `LawBrainSettings` class body. The existing fields are unchanged; the two new fields are appended after `type_map` so the model order reads stable-key → toggles → mappings → link-harvest config. Use a `Field(default_factory=...)` for the mutable list default (pydantic v2 idiom; the existing `[]`/`{}` literals are pydantic-deep-copied per instance, but a 6-element shared literal is clearer as a factory and avoids any reviewer flagging a shared-mutable-default).

```python
class LawBrainSettings(BaseModel):
    """Read-only law-brain integration settings (see ``[lawbrain]``)."""

    enabled: bool = False
    path: Path | None = None
    min_confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.75
    require_shared_key: bool = True
    demote_headings: bool = True
    commentary: bool = True
    discover: bool = False
    commentary_only_types: list[str] = []
    commentary_only_slug_markers: list[str] = []
    type_map: dict[str, str] = {}
    further_reading: bool = True
    primary_source_domains: list[str] = Field(
        default_factory=lambda: [
            ".gov",
            "legiscan.com",
            "courtlistener.com",
            "wikipedia.org",
            "europa.eu",
            "legislation.gov.uk",
        ]
    )
```

`Field` is already imported at the top of `config.py` (line 17: `from pydantic import BaseModel, Field`), so no import change is needed.

- [ ] **Step 4: Run the new tests — expect PASS.**

```
uv run pytest "tests/test_config.py::test_lawbrain_further_reading_defaults_true" "tests/test_config.py::test_lawbrain_primary_source_domains_default" -v
```

Expected: both PASS.

- [ ] **Step 5: Write failing test — TOML overrides for the two new fields.**

This proves the live `zwiadbrain.toml` keys (added in Step 7) parse through the loader. Append to `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_config.py`.

```python
def test_lawbrain_reads_link_harvest_config_from_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should parse [lawbrain].further_reading and primary_source_domains from the TOML"""
    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    toml = (
        "[lawbrain]\n"
        "enabled = true\n"
        'path = "C:/law"\n'
        "further_reading = false\n"
        'primary_source_domains = [".gov", "courtlistener.com"]\n'
    )
    toml_path, env_path = _write(tmp_path, toml=toml)
    settings = load_settings(toml_path=toml_path, env_file=env_path)
    assert settings.lawbrain.further_reading is False
    assert settings.lawbrain.primary_source_domains == [".gov", "courtlistener.com"]
```

- [ ] **Step 6: Run the override test — expect PASS already.**

```
uv run pytest "tests/test_config.py::test_lawbrain_reads_link_harvest_config_from_toml" -v
```

Expected: PASS. The loader feeds the TOML `[lawbrain]` table straight into `Settings.model_validate`, so the fields added in Step 3 already accept these keys — this test guards against future regressions and documents the override contract. (If it FAILS, the field names in Step 3 do not match the contract — fix Step 3, do not loosen the test.)

- [ ] **Step 7: Populate the live `[lawbrain]` block in `zwiadbrain.toml`.**

In `C:\Users\rafst\documents\projectas\zwiadbrain\zwiadbrain.toml`, the `[lawbrain]` block already sets `enabled`, `path`, `min_confidence`, `require_shared_key`, `demote_headings`, `commentary`, `discover`, `commentary_only_types`, and `commentary_only_slug_markers` (and `[lawbrain.type_map]` below it). Add the two new keys to the end of the scalar block, immediately after the `commentary_only_slug_markers` line and before the blank line that precedes `[lawbrain.type_map]`. Replace this exact text:

```
commentary_only_types = ["concept", "framework", "vendor", "person", "matter"]
commentary_only_slug_markers = ["tracker", "landscape", "map", "scholarship"]

[lawbrain.type_map]
```

with:

```
commentary_only_types = ["concept", "framework", "vendor", "person", "matter"]
commentary_only_slug_markers = ["tracker", "landscape", "map", "scholarship"]
further_reading = true            # decision 62: harvest a "Further Reading (via law brain)" link list
# decision 62: drop harvested links whose host ends with any of these suffixes (primary sources, not commentary).
primary_source_domains = [".gov", "legiscan.com", "courtlistener.com", "wikipedia.org", "europa.eu", "legislation.gov.uk"]

[lawbrain.type_map]
```

The keys placed before `[lawbrain.type_map]` keep them inside the `[lawbrain]` table — a TOML key after a `[table]` header would silently land in the wrong table, so order matters here.

- [ ] **Step 8: Confirm `.env.example` documents `LAW_BRAIN_PATH` (already present) and add a Further Reading note.**

`C:\Users\rafst\documents\projectas\zwiadbrain\.env.example` line 16 already declares `LAW_BRAIN_PATH=...`. No new secret is introduced by this task. Tighten the existing comment so the `.env.example` mentions that the law brain now also feeds Further Reading (so a reader knows the path enables more than commentary copy). Replace this exact line:

```
# Absolute path to the local, read-only law brain. Overrides [lawbrain].path in zwiadbrain.toml.
```

with:

```
# Absolute path to the local, read-only law brain (commentary + Further Reading link harvest).
# Overrides [lawbrain].path in zwiadbrain.toml. Read-only: ZwiadBrain never edits the law brain.
```

- [ ] **Step 9: Run the full config test module — expect all PASS.**

The live `zwiadbrain.toml` is parsed by the loader at runtime; the test module uses isolated temp TOMLs, so this run also guards that the model change did not break any existing case (`test_load_settings_parses_operational_config_from_toml`, `test_lawbrain_rejects_out_of_range_min_confidence`, etc.).

```
uv run pytest tests/test_config.py -v
```

Expected: every test in the module PASSES (the four new/extended assertions plus the pre-existing suite).

- [ ] **Step 10: Verify the committed TOML loads under the real loader and lint/type-check the change.**

This catches a malformed `[lawbrain]` edit (e.g. a key after the `[lawbrain.type_map]` header) that the temp-TOML tests would not surface, and enforces repo style on the touched module.

```
uv run python -c "from zwiadbrain.config import load_settings; s = load_settings(); print(s.lawbrain.further_reading, s.lawbrain.primary_source_domains)"
uv run ruff check src/zwiadbrain/config.py tests/test_config.py
uv run pyright src/zwiadbrain/config.py
```

Expected: the first command prints `True ['.gov', 'legiscan.com', 'courtlistener.com', 'wikipedia.org', 'europa.eu', 'legislation.gov.uk']` (the committed TOML omits both new keys, so defaults apply); `ruff check` reports no issues; `pyright` reports 0 errors.

- [ ] **Step 11: Commit.**

```
git add src/zwiadbrain/config.py zwiadbrain.toml .env.example tests/test_config.py
git commit -m "feat(lawbrain): add further_reading + primary_source_domains config"
```

Commit body (use a here-string per the PowerShell note; keep the conventional-commit subject under 72 chars):

```
feat(lawbrain): add further_reading + primary_source_domains config

Add the two link-harvest fields to LawBrainSettings (further_reading
defaults true; primary_source_domains defaults to the .gov/legiscan/
courtlistener/wikipedia/europa/legislation.gov.uk denylist) and surface
them in the committed [lawbrain] block. Documents D62 (Further Reading
link harvest + primary-domain denylist). LAW_BRAIN_PATH already present
in .env.example; comment extended to note Further Reading.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

I have enough context. Let me write the task section now.

```markdown
### Task 11: CLI — fetch-lawbrain-candidates

Build the deterministic fetch half of `/zwiad-sync-lawbrain`. The command reads the law brain (no-op when unavailable), enumerates `LawBrainPage`s, builds `TargetRef`s from every tracked `Bill`+`EnforcementAction` page in the wiki, computes each page's keys, consults the `LinkRegistry` to skip settled pages whose key-set is unchanged (D9), runs a deterministic set-intersection match over a key→target index (1 shared key → `link` conf 1.0; >1 → `collision`; 0 keys → `build_shortlist` for the LLM matcher unless the slug is a fail-closed marker), and stages `lawbrain-candidates.json` + `targets.json` in one run directory. Mirrors `fetch-enforcement-candidates`.

**Files:**
- Modify: `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\cli.py` (add imports, `_lawbrain_targets` helper, `fetch_lawbrain_candidates` command)
- Test: `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_lawbrain_cli.py` (fetch half)
- Test fixtures (created in this task): `C:\Users\rafst\documents\projectas\zwiadbrain\tests\fixtures\lawbrain\wiki\regulation-california-sb53-tfaia.md`, `...\concept-state-ai-chatbot-tracker.md`, `...\sources\zwiad\sb53-memo.md`

> Depends on Tasks 1–10 (reader `sources/lawbrain.py`, keys `pipeline/lawbrain_keys.py`, match `pipeline/lawbrain_match.py`, registry `pipeline/lawbrain_registry.py`) already landed — they supply `LawBrainReader`, `tracked_item_keys`, `page_keys`, `keys_hash`, `TargetRef`, `build_shortlist`, `LinkRegistry`. This task wires them into the CLI. It does NOT redefine any of them.

---

- [ ] **Step 1: Create the offline fixture law brain + a tracked-wiki SB 53 page.**

The fetch test needs (a) a mini law brain with one single-subject page that has a deterministic key (`regulation-california-sb53-tfaia` → `US-CA::bill::SB-53`) and one fail-closed marker page (`concept-state-ai-chatbot-tracker`), and (b) a tracked ZwiadBrain bill page whose `bill_number` yields the matching key. The tracked page is written by the test (via the project's own renderer fixtures) — here we create only the law-brain side plus a memo for later tasks.

Create `C:\Users\rafst\documents\projectas\zwiadbrain\tests\fixtures\lawbrain\wiki\regulation-california-sb53-tfaia.md`:

```markdown
---
title: "California SB 53 (TFAIA)"
type: regulation
jurisdiction: US-CA
tags:
  - california
  - frontier-ai
  - transparency
created: 2025-09-01
updated: 2025-10-15
citation: "Cal. SB 53 (2025)"
sources:
  - sources/zwiad/sb53-memo.md
status: active
---

## Summary

The Transparency in Frontier Artificial Intelligence Act (SB 53) imposes
safety-framework disclosure duties on large frontier developers.

## Key points

- Applies to frontier developers above a compute threshold.
- See [Mayer Brown client alert](https://www.mayerbrown.com/en/insights/sb53).

## Cross-references

- [[concept-california-ai-regulatory-landscape]]
```

Create `C:\Users\rafst\documents\projectas\zwiadbrain\tests\fixtures\lawbrain\wiki\concept-state-ai-chatbot-tracker.md`:

```markdown
---
title: "State AI Chatbot Tracker"
type: concept
jurisdiction: US-CA
tags:
  - tracker
  - chatbot
created: 2025-08-01
updated: 2025-10-01
status: active
---

## Summary

A running multi-state tracker of AI chatbot bills, including CA SB 53 and AB 1064.
```

Create `C:\Users\rafst\documents\projectas\zwiadbrain\tests\fixtures\lawbrain\wiki\sources\zwiad\sb53-memo.md`:

```markdown
# SB 53 memo

Secondary commentary:
- [IAPP analysis](https://iapp.org/news/a/sb53-overview)
- Primary text at https://leginfo.legislature.ca.gov/sb53
```

- [ ] **Step 2: Write the failing test for the unavailable-path no-op.**

Add to a new file `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_lawbrain_cli.py`. This first test pins the contract that a missing/disabled law brain makes the command a clean no-op (exit 0, no candidates file). It mirrors how `test_cli.py` invokes commands via `typer.testing.CliRunner` and monkeypatches `load_settings`.

```python
"""CLI tests for the law-brain fetch half (``fetch-lawbrain-candidates``)."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zwiadbrain.cli import app
from zwiadbrain.config import LawBrainSettings, Settings

_RUNNER = CliRunner()
_FIXTURE_LAWBRAIN = Path(__file__).parent / "fixtures" / "lawbrain"


def _settings(law_brain_path: Path | None, *, enabled: bool = True) -> Settings:
    """A Settings whose lawbrain block points at a (possibly missing) law brain."""
    lawbrain = LawBrainSettings(
        enabled=enabled,
        path=law_brain_path,
        commentary_only_slug_markers=["tracker", "landscape", "map", "scholarship"],
    )
    return Settings(lawbrain=lawbrain)


def _write_sb53_bill(wiki: Path) -> None:
    """Render a tracked CA SB 53 bill page so its key matches the law-brain page."""
    page = wiki / "bills" / "ca-2025-sb-53.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "\n".join(
            [
                "---",
                "id: ca-2025-sb-53",
                "type: bill",
                "jurisdiction: US-CA",
                "title: Transparency in Frontier Artificial Intelligence Act",
                "bill_number: SB 53",
                "status: enrolled",
                "relevance: []",
                "sources: []",
                "commentary_sources: []",
                "---",
                "",
                "## Summary",
                "",
                "State frontier-AI transparency bill.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_fetch_lawbrain_candidates_no_op_when_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — point lawbrain at a path with no wiki/ subdir (is_available() False).
    missing = tmp_path / "no-law-brain"
    missing.mkdir()
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: _settings(missing))
    out = tmp_path / "run"

    # Act
    result = _RUNNER.invoke(
        app, ["fetch-lawbrain-candidates", "--out", str(out)]
    )

    # Assert — exit 0, a no-op message, and no candidates file written.
    assert result.exit_code == 0, result.output
    assert "law brain unavailable" in result.output
    assert not (out / "lawbrain-candidates.json").exists()
```

- [ ] **Step 3: Run the test, expect FAIL (command not registered).**

```bash
uv run pytest tests/test_lawbrain_cli.py::test_fetch_lawbrain_candidates_no_op_when_unavailable -v
```

Expected: FAIL — the runner exits non-zero with `No such command 'fetch-lawbrain-candidates'` (the command does not exist yet), so `result.exit_code == 0` fails.

- [ ] **Step 4: Add imports and the `_lawbrain_targets` helper to `cli.py`.**

Add the new imports alongside the existing pipeline imports (after the `from zwiadbrain.pipeline.refresh import (...)` block, line ~57). Insert these import lines:

```python
from zwiadbrain.pipeline.lawbrain_keys import keys_hash, page_keys, tracked_item_keys
from zwiadbrain.pipeline.lawbrain_match import TargetRef, build_shortlist
from zwiadbrain.pipeline.lawbrain_registry import LinkRegistry
from zwiadbrain.sources.lawbrain import LawBrainReader
```

Then add the `_lawbrain_targets` helper next to `_existing_matters` (after line 570, before `@app.command(name="fetch-enforcement-candidates")`). It reads every tracked `Bill` and `EnforcementAction` page in the wiki into a `TargetRef`, attaching the deterministic key-set via `tracked_item_keys`:

```python
def _lawbrain_targets(wiki: Path) -> list[TargetRef]:
    """Read every tracked Bill + EnforcementAction page into a TargetRef.

    A TargetRef carries the deterministic key-set (``tracked_item_keys``) the
    law-brain matcher intersects against page keys. Malformed pages are skipped
    (per-page isolation; mirrors ``_existing_matters``). Both kinds participate:
    commentary attaches on a shared jurisdiction-qualified key regardless of
    ZwiadBrain page kind (D59).
    """
    targets: list[TargetRef] = []
    for page in sorted(wiki.glob("**/*.md")):
        try:
            item = from_page(page.read_text(encoding="utf-8"))
        except (WikiSchemaError, ConfigError):
            continue
        if isinstance(item, Bill):
            kind = "bill"
        elif isinstance(item, EnforcementAction):
            kind = "enforcement"
        else:
            continue
        targets.append(
            TargetRef(
                id=item.id,
                kind=kind,
                jurisdiction=item.jurisdiction,
                title=item.title,
                keys=sorted(tracked_item_keys(item)),
            )
        )
    return targets
```

Note `from_page` is already imported in `cli.py` (used by `_existing_matters`); confirm via the existing `from zwiadbrain.wiki.schema import from_page` import — do not re-add it.

- [ ] **Step 5: Add the `fetch_lawbrain_candidates` command to `cli.py`.**

Insert this command immediately after `fetch_enforcement_candidates` (after its `typer.echo` line, ~632) so the fetch commands sit together. It builds the key→target index once, walks every law-brain page, consults the registry, classifies each page, and stages both files in one run directory (the `targets.json`/`candidates.json` two-file pattern of the enforcement fetch).

```python
@app.command(name="fetch-lawbrain-candidates")
def fetch_lawbrain_candidates(
    wiki: Annotated[
        Path, typer.Option(help="Wiki root (for tracked targets).")
    ] = Path("wiki"),
    out: Annotated[
        Path | None, typer.Option(help="Run directory for lawbrain-candidates.json.")
    ] = None,
) -> None:
    """Read the law brain, match pages to tracked items by deterministic key, and
    stage lawbrain-candidates.json + targets.json for the interactive matcher.

    A clean no-op when the law brain is unavailable or disabled (``is_available``).
    One shared key → deterministic ``link`` (conf 1.0); a key collision → ``collision``
    (review); zero keys on a single-subject page → ``keyless`` with a shortlist for the
    ``lawbrain-matcher`` subagent. Fail-closed slug-marker pages emit no keys and are
    skipped entirely (D60). Settled registry pages whose key-set is unchanged are
    skipped (D9). Mirrors fetch-enforcement-candidates.
    """
    try:
        settings = load_settings()
        reader = LawBrainReader(settings.effective_law_brain_path)
        if not settings.lawbrain.enabled or not reader.is_available():
            typer.echo("law brain unavailable or disabled; nothing to do")
            return
        targets = _lawbrain_targets(wiki) if wiki.exists() else []
        # Build a key -> target-ids index once. A page's match is the set of targets
        # sharing >=1 key with the page (set intersection over this index, D-keys).
        index: dict[str, list[str]] = {}
        for target in targets:
            for key in target.keys:
                index.setdefault(key, []).append(target.id)
        registry = LinkRegistry.load(_lawbrain_registry_path(wiki))
        markers = settings.lawbrain.commentary_only_slug_markers
        candidates: list[dict[str, object]] = []
        for page in reader.pages():
            keys = page_keys(page, markers)
            # Fail-closed: a slug-marker (tracker/landscape/…) page emits zero keys.
            # Without a key it cannot deterministically attach; with no single subject
            # it must not go to the matcher either, so it is skipped entirely (D60).
            if not keys and _is_marker_slug(page.slug, markers):
                continue
            khash = keys_hash(keys)
            decided = registry.decision_for(page.slug)
            # Skip a settled page unless its freshly-extracted key-set differs (D9).
            if decided is not None and decided.keys_hash == khash:
                continue
            matched_ids = sorted(
                {tid for key in keys for tid in index.get(key, [])}
            )
            if len(matched_ids) == 1:
                match, target_id, shortlist = "deterministic", matched_ids[0], None
            elif len(matched_ids) > 1:
                match, target_id, shortlist = "collision", None, matched_ids
            else:
                # Zero keys on a single-subject page -> the LLM matcher decides over a
                # jurisdiction-scoped shortlist (never the full corpus).
                match, target_id = "keyless", None
                shortlist = [
                    t.id for t in build_shortlist(page, targets)
                ]
            entry: dict[str, object] = {
                "slug": page.slug,
                "title": page.title,
                "type": page.type,
                "jurisdiction": page.jurisdiction,
                "tags": page.tags,
                "citation": page.citation,
                "summary_excerpt": _summary_excerpt(page.body),
                "keys": sorted(keys),
                "keys_hash": khash,
                "match": match,
                "target_id": target_id,
                "shortlist": shortlist,
            }
            candidates.append(entry)
        # Stage both files in the SAME run directory: stage_json returns the
        # candidates path, so targets.json reuses its parent (mirrors the
        # candidates.json/matters.json pairing in fetch-enforcement-candidates).
        path = stage_json(candidates, name="lawbrain-candidates.json", out=out)
        stage_json(
            [t.model_dump(mode="json") for t in targets],
            name="targets.json",
            out=path.parent,
        )
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"staged {len(candidates)} law-brain candidate(s) to {path.parent}"
    )
```

Add the two small module-level helpers this command uses, placed just above the command (after `_lawbrain_targets`):

```python
def _lawbrain_registry_path(wiki: Path) -> Path:
    """The committed link-decision registry lives beside the wiki (wiki/links.yaml)."""
    return wiki / "links.yaml"


def _is_marker_slug(slug: str, markers: list[str]) -> bool:
    """True when any fail-closed marker is a substring of the page slug (D60)."""
    return any(marker in slug for marker in markers)


def _summary_excerpt(body: str, *, limit: int = 280) -> str:
    """First non-heading paragraph of a law-brain page body, truncated for the matcher.

    Mirrors the ``text``-excerpt convention the enforcement candidates use to give the
    subagent a compact grounding snippet without shipping the whole body.
    """
    for block in body.split("\n\n"):
        stripped = block.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:limit]
    return ""
```

- [ ] **Step 6: Run the no-op test, expect PASS.**

```bash
uv run pytest tests/test_lawbrain_cli.py::test_fetch_lawbrain_candidates_no_op_when_unavailable -v
```

Expected: PASS — `is_available()` returns `False` for a path with no `wiki/` subdir, the command echoes `law brain unavailable or disabled; nothing to do`, returns before staging, and exits 0.

- [ ] **Step 7: Write the failing test for a deterministic key match + marker exclusion.**

Add this test to `tests/test_lawbrain_cli.py`. It points the law brain at the fixture wiki, renders a matching tracked SB 53 bill, runs the command, and asserts the candidates file pins (a) the SB 53 page as a `deterministic` match to `ca-2025-sb-53`, and (b) the chatbot-tracker page excluded entirely (fail-closed). It also pins that `targets.json` is staged beside the candidates file.

```python
def test_fetch_lawbrain_candidates_deterministic_match_and_marker_exclusion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a real fixture law brain + a tracked SB 53 bill sharing its key.
    law_brain = tmp_path / "law"
    shutil.copytree(_FIXTURE_LAWBRAIN, law_brain)
    wiki = tmp_path / "wiki"
    _write_sb53_bill(wiki)
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: _settings(law_brain))
    out = tmp_path / "run"

    # Act
    result = _RUNNER.invoke(
        app, ["fetch-lawbrain-candidates", "--wiki", str(wiki), "--out", str(out)]
    )

    # Assert — staged both files; SB 53 is a deterministic link, tracker excluded.
    assert result.exit_code == 0, result.output
    candidates_path = out / "lawbrain-candidates.json"
    assert candidates_path.exists()
    assert (out / "targets.json").exists()

    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    by_slug = {c["slug"]: c for c in candidates}

    assert "concept-state-ai-chatbot-tracker" not in by_slug  # fail-closed (D60)

    sb53 = by_slug["regulation-california-sb53-tfaia"]
    assert sb53["match"] == "deterministic"
    assert sb53["target_id"] == "ca-2025-sb-53"
    assert "US-CA::bill::SB-53" in sb53["keys"]
    assert sb53["shortlist"] is None

    targets = json.loads((out / "targets.json").read_text(encoding="utf-8"))
    assert {"id": "ca-2025-sb-53", "kind": "bill"} <= {
        "id": targets[0]["id"],
        "kind": targets[0]["kind"],
    }
```

- [ ] **Step 8: Run the match test, expect PASS.**

```bash
uv run pytest tests/test_lawbrain_cli.py::test_fetch_lawbrain_candidates_deterministic_match_and_marker_exclusion -v
```

Expected: PASS — the SB 53 fixture page yields key `US-CA::bill::SB-53`, the tracked bill's `bill_number: SB 53` under `US-CA` yields the same key via `tracked_item_keys`, so the index gives exactly one matched target → `deterministic`/`ca-2025-sb-53`; the chatbot-tracker page's slug contains `tracker`, so `page_keys` returns empty and `_is_marker_slug` skips it.

> If this test fails on the `from_page` parse of the tracked bill fixture (e.g. a required `Bill` field the minimal frontmatter omits), do NOT broaden the command's `except` — fix the fixture frontmatter in `_write_sb53_bill` to satisfy the real `Bill` schema (read `src/zwiadbrain/wiki/schema.py` `from_page` + `models.py` `Bill` for the required fields). The command's per-page isolation must stay scoped to malformed pages, not used to mask a fixture gap (debug rule 4: do not mask errors).

- [ ] **Step 9: Write the failing test for registry stickiness (D9) skip.**

Add this test. It seeds `wiki/links.yaml` with a decision for the SB 53 page whose `keys_hash` equals the page's current key-set hash, then asserts the page is skipped on the next fetch (no candidate emitted) — and conversely that a stale `keys_hash` re-surfaces it.

```python
def test_fetch_lawbrain_candidates_skips_settled_registry_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — record a link decision whose keys_hash matches the live key-set.
    from zwiadbrain.pipeline.lawbrain_keys import keys_hash, page_keys
    from zwiadbrain.pipeline.lawbrain_registry import LinkDecision, LinkRegistry
    from zwiadbrain.sources.lawbrain import LawBrainReader

    law_brain = tmp_path / "law"
    shutil.copytree(_FIXTURE_LAWBRAIN, law_brain)
    wiki = tmp_path / "wiki"
    _write_sb53_bill(wiki)
    wiki.mkdir(parents=True, exist_ok=True)

    settings = _settings(law_brain)
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: settings)

    reader = LawBrainReader(settings.effective_law_brain_path)
    sb53_page = next(p for p in reader.pages() if p.slug == "regulation-california-sb53-tfaia")
    live_hash = keys_hash(
        page_keys(sb53_page, settings.lawbrain.commentary_only_slug_markers)
    )

    registry = LinkRegistry.load(wiki / "links.yaml")
    registry.record(
        LinkDecision(
            lawbrain_slug="regulation-california-sb53-tfaia",
            decision="link",
            target_id="ca-2025-sb-53",
            matched_by="deterministic",
            keys_hash=live_hash,
            decided=dt.date(2026, 5, 29),
        )
    )
    registry.dump(wiki / "links.yaml")
    out = tmp_path / "run"

    # Act
    result = _RUNNER.invoke(
        app, ["fetch-lawbrain-candidates", "--wiki", str(wiki), "--out", str(out)]
    )

    # Assert — the settled page is skipped (keys_hash unchanged, D9).
    assert result.exit_code == 0, result.output
    candidates = json.loads(
        (out / "lawbrain-candidates.json").read_text(encoding="utf-8")
    )
    slugs = {c["slug"] for c in candidates}
    assert "regulation-california-sb53-tfaia" not in slugs
```

- [ ] **Step 10: Run the stickiness test, expect PASS.**

```bash
uv run pytest tests/test_lawbrain_cli.py::test_fetch_lawbrain_candidates_skips_settled_registry_page -v
```

Expected: PASS — the command computes the same `keys_hash` for the SB 53 page, `registry.decision_for(slug)` returns the recorded decision with a matching `keys_hash`, so the page is skipped and never appears in `candidates`.

- [ ] **Step 11: Run the full file, ruff, and pyright, expect all green.**

```bash
uv run pytest tests/test_lawbrain_cli.py -v
uv run ruff check src/zwiadbrain/cli.py tests/test_lawbrain_cli.py
uv run pyright src/zwiadbrain/cli.py
```

Expected: all three PASS — three tests green; ruff clean; pyright `--strict` reports 0 errors for `cli.py` (the `index`/`candidates`/`entry` dict annotations and the `match`/`target_id`/`shortlist` locals are explicitly typed; `_lawbrain_targets`/`_summary_excerpt` are fully annotated).

> If pyright flags the `shortlist` local as `list[str] | None` narrowing across the branches, keep it explicit — the `entry` dict value type is `object` (matching `fetch-enforcement-candidates`' `dict[str, object]`), which already accepts `list[str] | None`. Do not add `# type: ignore`; the contract types resolve cleanly.

- [ ] **Step 12: Commit.**

```bash
git add src/zwiadbrain/cli.py tests/test_lawbrain_cli.py tests/fixtures/lawbrain/wiki/regulation-california-sb53-tfaia.md tests/fixtures/lawbrain/wiki/concept-state-ai-chatbot-tracker.md tests/fixtures/lawbrain/wiki/sources/zwiad/sb53-memo.md
git commit -m "feat(lawbrain): add fetch-lawbrain-candidates CLI fetch half

Read the law brain (no-op when unavailable/disabled), build TargetRefs from
tracked Bill+EnforcementAction pages, compute page keys, consult the
LinkRegistry for D9 stickiness, run deterministic set-intersection matching
with collision detection, build jurisdiction-scoped shortlists for keyless
single-subject pages, and stage lawbrain-candidates.json + targets.json.
Fail-closed slug-marker pages (D60) are skipped. Mirrors
fetch-enforcement-candidates.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
```

---

I have everything I need. I now understand the full pattern: the per-item isolation loop, the `try/except AppError` boundary, `write_page`, `Store.reindex`, `from_page`, and the contracts for the new lawbrain modules. Task 12 consumes modules built in earlier tasks (reader, copy, links, registry, review, match) and the template region helpers.

Now I'll write the Task 12 markdown section.

### Task 12: CLI — render-lawbrain-commentary

The deterministic render half of `/zwiad-sync-lawbrain`. Reads a `classified.json` of operator/subagent-decided links, deterministically re-confirms every LLM link against shared keys, copies the matched law-brain page body + harvested Further Reading links into the target's `commentary_sources`, writes the page (region renders authoritatively from the fresh bodies), records decisions to `wiki/links.yaml`, writes/resolves `wiki/review-queue.md`, and reindexes. Per-item isolation (a malformed entry is dropped, never fatal); `--dry-run` computes intended writes with zero edits. Mirrors `render-enforcement` exactly (the `try/except AppError` boundary, the `dropped` list, the summary line, `Store(db).reindex`).

This task assumes Tasks 1–11 have already shipped these (verify the imports resolve before writing the implementation — if any is missing, STOP and report which task is incomplete):

- `sources/lawbrain.py`: `LawBrainReader`, `LawBrainPage`
- `pipeline/lawbrain_keys.py`: `page_keys`, `tracked_item_keys`, `keys_hash`
- `pipeline/lawbrain_match.py`: `confirm_match` (the lawbrain one — keyword-only signature; distinct from the enforcement `confirm_match` already imported in `cli.py`)
- `pipeline/lawbrain_copy.py`: `build_commentary_source`, `merge_commentary`, `detect_stale`
- `pipeline/lawbrain_links.py`: `harvest_links`
- `pipeline/lawbrain_registry.py`: `LinkRegistry`, `LinkDecision`
- `pipeline/lawbrain_review.py`: `ReviewEntry`, `render_review_queue`, `parse_review_queue`
- `models.py`: `CommentaryLink`, `CommentarySource.links`
- `templates.py`: `_lawbrain_region` wired into `render_bill_body`/`render_enforcement_body`; `render.py write_page` calls `preserve_lawbrain_region`

**Files:**

- **Modify:** `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\cli.py` (add the `render-lawbrain-commentary` command + small module-level helpers `_lawbrain_page_by_id` / `_resolve_review_queue`; new imports)
- **Test:** `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_lawbrain_cli.py` (render half)
- **Fixture (create):** `C:\Users\rafst\documents\projectas\zwiadbrain\tests\fixtures\lawbrain\wiki\regulation-california-sb53-tfaia.md` and `C:\Users\rafst\documents\projectas\zwiadbrain\tests\fixtures\lawbrain\sources\zwiad\sb53-memo.md` (mini law brain for the SB-53 showcase) — only if Task 1's reader tests did not already create them; reuse the existing fixture if present

---

- [ ] **Step 1: Add the offline mini-law-brain fixture for the SB-53 showcase**

The render half must read a real `LawBrainPage` from a `LawBrainReader` root. Reuse `tests/fixtures/lawbrain/` if Task 1 created it; otherwise create exactly these two files. First check:

```
uv run python -c "from pathlib import Path; p=Path('tests/fixtures/lawbrain/wiki/regulation-california-sb53-tfaia.md'); print('EXISTS' if p.exists() else 'MISSING')"
```

If it prints `MISSING`, create the page fixture at `C:\Users\rafst\documents\projectas\zwiadbrain\tests\fixtures\lawbrain\wiki\regulation-california-sb53-tfaia.md`:

```markdown
---
title: "California SB 53 (TFAIA)"
type: regulation
jurisdiction: US-CA
tags:
  - ai
  - frontier-models
  - transparency
citation: "SB 53"
created: 2025-09-01
updated: 2025-10-15
sources:
  - sources/zwiad/sb53-memo.md
status: active
---

## Summary

California SB 53, the Transparency in Frontier Artificial Intelligence Act (TFAIA),
imposes safety-framework publication and incident-reporting duties on developers of
frontier models. See [Cooley client alert](https://www.cooley.com/news/insight/2025/sb53)
for a practitioner walkthrough.

## Key points

- Applies to frontier developers above a compute threshold.
- Cross-reference: [[concept-california-ai-regulatory-landscape]] situates it.

## Citations

- Official text: https://leginfo.legislature.ca.gov/sb53
```

And the referenced memo at `C:\Users\rafst\documents\projectas\zwiadbrain\tests\fixtures\lawbrain\sources\zwiad\sb53-memo.md`:

```markdown
# SB 53 research memo

Secondary commentary collected during research:

- [Morgan Lewis analysis](https://www.morganlewis.com/pubs/2025/sb53)
- [IAPP coverage](https://iapp.org/news/a/california-sb-53)
- Bare law-firm URL: https://www.sidley.com/insights/sb53

Primary sources (should be filtered out of Further Reading):

- [Official CA text](https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=sb53)
- [Wikipedia](https://en.wikipedia.org/wiki/SB_53)
```

If the fixture already exists from Task 1, do NOT overwrite it — instead read it and adjust the test's expected hosts in Step 2 to whatever the existing memo actually contains.

---

- [ ] **Step 2: Write the failing test for `render-lawbrain-commentary` (deterministic link attaches commentary + Further Reading; byte-identical re-run; weak-grounding routes to review-queue, not links.yaml)**

Create `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_lawbrain_cli.py`:

```python
"""CLI tests for the render half of /zwiad-sync-lawbrain (render-lawbrain-commentary).

Fully offline: the law brain is a local mini-wiki under tests/fixtures/lawbrain/,
the target page is rendered to a tmp wiki, and classified.json is hand-built to
stand in for the (subagent/operator) fetch+match output. No network, no LLM.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zwiadbrain.cli import app
from zwiadbrain.models import Bill
from zwiadbrain.pipeline.render import write_page
from zwiadbrain.wiki.schema import from_page

runner = CliRunner()
_LB_FIX = Path(__file__).parent / "fixtures" / "lawbrain"


def _write_settings(tmp_path: Path) -> None:
    """Enable the law brain, pointed at the offline fixture, and disable shared-key
    requirement defaults we don't exercise (the deterministic path supplies keys)."""
    toml = tmp_path / "zwiadbrain.toml"
    toml.write_text(
        "[lawbrain]\n"
        "enabled = true\n"
        f'path = "{_LB_FIX.as_posix()}"\n'
        "min_confidence = 0.75\n"
        "require_shared_key = true\n"
        "demote_headings = true\n"
        "commentary = true\n"
        "further_reading = true\n",
        encoding="utf-8",
    )


def _seed_sb53(wiki: Path) -> None:
    """Render the tracked CA SB 53 bill page (the deterministic-match target)."""
    bill = Bill(
        id="ca-2025-sb-53",
        jurisdiction="US-CA",
        title="California SB 53 — Transparency in Frontier AI Act",
        bill_number="SB 53",
        topics=["ai"],
        summary="A California frontier-model transparency bill.",
        sources={"LegiScan": "https://legiscan.com/CA/bill/SB53/2025"},
    )
    write_page(bill, wiki)


def _classified_deterministic() -> list[dict[str, object]]:
    """One deterministic SB-53 link (the showcase) the fetch half would emit."""
    return [
        {
            "slug": "regulation-california-sb53-tfaia",
            "target_id": "ca-2025-sb-53",
            "matched_by": "deterministic",
            "confidence": 1.0,
            "page_keys": ["US-CA::bill::SB-53"],
            "target_keys": ["US-CA::bill::SB-53"],
        }
    ]


def test_render_lawbrain_attaches_commentary_and_further_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    _write_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53(wiki)
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(_classified_deterministic()), encoding="utf-8"
    )

    # Act
    result = runner.invoke(
        app,
        [
            "render-lawbrain-commentary",
            "--in",
            str(run / "classified.json"),
            "--wiki",
            str(wiki),
            "--db",
            str(tmp_path / "index.sqlite"),
        ],
    )

    # Assert — command succeeded and reported one link
    assert result.exit_code == 0, result.output
    assert "1 linked" in result.output

    page = (wiki / "states" / "ca" / "bills" / "ca-2025-sb-53.md").read_text(
        encoding="utf-8"
    )
    # Commentary region with the slug marker, demoted headings, neutralized wikilink.
    assert "## Commentary & Analysis" in page
    assert "<!-- lawbrain:region:begin -->" in page
    assert "<!-- lawbrain:begin slug=regulation-california-sb53-tfaia -->" in page
    assert "### Summary" in page  # source "## Summary" demoted to "###"
    assert "concept-california-ai-regulatory-landscape" in page  # [[...]] neutralized
    assert "[[concept-california-ai-regulatory-landscape]]" not in page
    # Further Reading harvested from page body + referenced memo, primary sources dropped.
    assert "## Further Reading (via law brain)" in page
    assert "morganlewis.com" in page
    assert "iapp.org" in page
    assert "sidley.com" in page  # bare URL captured
    assert "cooley.com" in page  # from the page body itself
    assert "leginfo.legislature.ca.gov" not in page  # *.gov primary source filtered
    assert "en.wikipedia.org" not in page  # wikipedia primary source filtered
    # A decided link is recorded in the committed registry, not the review queue.
    links_yaml = (wiki / "links.yaml").read_text(encoding="utf-8")
    assert "regulation-california-sb53-tfaia" in links_yaml
    assert "ca-2025-sb-53" in links_yaml
    # commentary body/links stay OUT of frontmatter (D20): reload via from_page.
    reloaded = from_page(page)
    assert len(reloaded.commentary_sources) == 1
    assert reloaded.commentary_sources[0].slug == "regulation-california-sb53-tfaia"
    assert reloaded.commentary_sources[0].body is None  # bookkeeping only
    assert reloaded.commentary_sources[0].links == []


def test_render_lawbrain_rerun_is_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — first render
    monkeypatch.chdir(tmp_path)
    _write_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53(wiki)
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(_classified_deterministic()), encoding="utf-8"
    )
    page_path = wiki / "states" / "ca" / "bills" / "ca-2025-sb-53.md"
    first = runner.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )
    assert first.exit_code == 0, first.output
    after_first = page_path.read_text(encoding="utf-8")

    # Act — identical second render
    second = runner.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — byte-identical, clean git status (D20)
    assert second.exit_code == 0, second.output
    assert page_path.read_text(encoding="utf-8") == after_first


def test_render_lawbrain_weak_grounding_routes_to_review_not_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — an LLM-proposed link with NO shared key: confirm_match fails the
    # require_shared_key gate, so it must land in review-queue.md, NOT links.yaml.
    monkeypatch.chdir(tmp_path)
    _write_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53(wiki)
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(
            [
                {
                    "slug": "regulation-california-sb53-tfaia",
                    "target_id": "ca-2025-sb-53",
                    "matched_by": "llm",
                    "confidence": 0.9,
                    "page_keys": [],  # no key -> grounding confirm fails
                    "target_keys": ["US-CA::bill::SB-53"],
                }
            ]
        ),
        encoding="utf-8",
    )

    # Act
    result = runner.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — no commentary attached, a review entry written, no links.yaml decision
    assert result.exit_code == 0, result.output
    assert "1 review" in result.output
    page = (wiki / "states" / "ca" / "bills" / "ca-2025-sb-53.md").read_text(
        encoding="utf-8"
    )
    assert "## Commentary & Analysis" not in page
    review = (wiki / "review-queue.md").read_text(encoding="utf-8")
    assert "regulation-california-sb53-tfaia" in review
    assert "weak-grounding" in review
    assert not (wiki / "links.yaml").exists()


def test_render_lawbrain_dry_run_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    _write_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53(wiki)
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(_classified_deterministic()), encoding="utf-8"
    )
    page_path = wiki / "states" / "ca" / "bills" / "ca-2025-sb-53.md"
    before = page_path.read_text(encoding="utf-8")

    # Act
    result = runner.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite"), "--dry-run"],
    )

    # Assert — intended write reported, page untouched, no registry/queue written
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output.lower()
    assert page_path.read_text(encoding="utf-8") == before  # zero edits
    assert "## Commentary & Analysis" not in before
    assert not (wiki / "links.yaml").exists()
    assert not (wiki / "review-queue.md").exists()


def test_render_lawbrain_drops_malformed_entry_without_failing_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — one good deterministic link + one entry missing required keys.
    monkeypatch.chdir(tmp_path)
    _write_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53(wiki)
    run = tmp_path / "run"
    run.mkdir()
    entries = _classified_deterministic() + [{"matched_by": "deterministic"}]
    (run / "classified.json").write_text(json.dumps(entries), encoding="utf-8")

    # Act
    result = runner.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — the good link applied, the malformed one isolated as a drop.
    assert result.exit_code == 0, result.output
    assert "1 linked" in result.output
    assert "1 dropped" in result.output
    assert "dropped:" in result.output
```

---

- [ ] **Step 3: Run the test — expect FAIL (command does not exist yet)**

```
uv run pytest tests/test_lawbrain_cli.py -v
```

Expected: FAIL. The `render-lawbrain-commentary` command is not registered, so `runner.invoke` returns a non-zero exit code (typer reports "No such command") and the `exit_code == 0` assertions fail. (If you instead see an `ImportError` on `from zwiadbrain.cli import app`, a dependency from Tasks 1–11 is missing — STOP and report which import is unresolved rather than implementing around it.)

---

- [ ] **Step 4: Implement the command in `cli.py`**

First add the new imports. Find the existing law-brain-adjacent import block and the enforcement import block. Add these imports near the other `pipeline` imports (after the `from zwiadbrain.pipeline.render import write_page` line). Note `confirm_match` from enforcement is already imported under that exact name, so the law-brain one is imported with an alias `lawbrain_confirm_match` to avoid the collision:

```python
from zwiadbrain.pipeline.lawbrain_copy import (
    build_commentary_source,
    detect_stale,
    merge_commentary,
)
from zwiadbrain.pipeline.lawbrain_keys import keys_hash
from zwiadbrain.pipeline.lawbrain_links import harvest_links
from zwiadbrain.pipeline.lawbrain_match import confirm_match as lawbrain_confirm_match
from zwiadbrain.pipeline.lawbrain_registry import LinkDecision, LinkRegistry
from zwiadbrain.pipeline.lawbrain_review import (
    ReviewEntry,
    parse_review_queue,
    render_review_queue,
)
from zwiadbrain.sources.lawbrain import LawBrainPage, LawBrainReader
```

Add `CommentaryLink` to the existing `from zwiadbrain.models import (...)` block (insert it alphabetically before `EnforcementAction`):

```python
from zwiadbrain.models import (
    Bill,
    CommentaryLink,
    EnforcementAction,
    EnforcementDevelopment,
    Hearing,
    LegHistory,
    Statement,
)
```

Now add the two module-level helpers next to `_enforcement_page_by_id` (after its definition, before `render_enforcement`):

```python
def _lawbrain_page_by_id(wiki: Path, target_id: str) -> Path | None:
    """Locate an existing tracked page (bill OR enforcement) by id under any jurisdiction.

    Commentary attaches regardless of page kind (D59), so both wiki subtrees are
    searched; the first match wins (ids are unique across the wiki).
    """
    matches = list(wiki.glob(f"**/bills/{target_id}.md")) + list(
        wiki.glob(f"**/enforcement/{target_id}.md")
    )
    return matches[0] if matches else None


def _lawbrain_page_by_slug(reader: LawBrainReader, slug: str) -> LawBrainPage | None:
    """Return the parsed law-brain page with this slug, or None if it is gone (stale)."""
    return next((p for p in reader.pages() if p.slug == slug), None)
```

Now add the command itself. Place it immediately after `render_enforcement` (after line 815, before `_as_list`):

```python
@app.command(name="render-lawbrain-commentary")
def render_lawbrain_commentary(
    input_file: Annotated[
        Path, typer.Option("--in", help="classified.json of decided law-brain links.")
    ],
    wiki: Annotated[Path, typer.Option(help="Wiki root to write commentary onto.")] = Path(
        "wiki"
    ),
    db: Annotated[Path, typer.Option(help="SQLite index path.")] = Path(
        "data/cache/index.sqlite"
    ),
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print intended writes; make zero edits.")
    ] = False,
) -> None:
    """Render law-brain commentary onto tracked pages — the render half of /zwiad-sync-lawbrain.

    A ``deterministic`` link is trusted; an ``llm`` link is re-grounded by
    :func:`lawbrain_confirm_match` (require >=1 shared jurisdiction-qualified key, D16)
    and demoted to a ``weak-grounding`` review-queue entry when the confirm fails —
    never a silent topical merge. For each applied link the matched page body is copied
    verbatim and its secondary reference links harvested (D62) into the target's
    ``commentary_sources``; the renderer rebuilds the ``lawbrain:region`` authoritatively
    from those fresh bodies (D63). Operator-resolved queue tokens (``[accept]``/
    ``[reject]``) are applied in the same pass (D61). Idempotent; ``--dry-run`` is read-only.
    """
    try:
        try:
            raw: object = json.loads(input_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"could not read classified file {input_file}: {exc}") from exc
        if not isinstance(raw, list):
            raise ConfigError(f"classified file must be a JSON list, got {type(raw).__name__}")
        entries: list[object] = list(raw)  # pyright: ignore[reportUnknownArgumentType]
        settings = load_settings()
        reader = LawBrainReader(settings.effective_law_brain_path or Path("."))
        if not (settings.lawbrain.enabled and reader.is_available()):
            typer.echo("lawbrain: disabled or unavailable — no-op")
            raise typer.Exit(0)

        registry_path = wiki / "links.yaml"
        queue_path = wiki / "review-queue.md"
        registry = LinkRegistry.load(registry_path)
        review: list[ReviewEntry] = []
        # Pages touched in this run; staleness is checked per target after copying.
        linked = reviewed = 0
        notes: list[str] = []
        intended: list[str] = []  # dry-run preview lines
        # Per-item isolation: a malformed entry is recorded as a drop and skipped,
        # never fatal — mirrors render-enforcement.
        dropped: list[tuple[str, str]] = []
        for i, item in enumerate(entries):
            if not isinstance(item, dict):
                dropped.append((f"entry[{i}]", "classified entry is not a JSON object"))
                continue
            e: dict[str, object] = item  # pyright: ignore[reportUnknownVariableType]
            slug = str(e.get("slug") or f"entry[{i}]")
            try:
                slug = str(e["slug"])
                target_id = str(e["target_id"])
                matched_by = str(e["matched_by"])
                if matched_by not in ("deterministic", "llm"):
                    raise ConfigError(f"unknown matched_by {matched_by!r}")
                confidence = float(e["confidence"])  # pyright: ignore[reportArgumentType]
                page_key_set = {str(k) for k in _as_list(e.get("page_keys"), "page_keys")}
                target_key_set = {
                    str(k) for k in _as_list(e.get("target_keys"), "target_keys")
                }
                override = registry.decision_for(slug) is not None and (
                    registry.decision_for(slug).decision == "link"  # type: ignore[union-attr]
                )
                # Re-ground an LLM-proposed link deterministically (D16). A
                # deterministic link is already key-grounded by the fetch half.
                if matched_by == "llm":
                    ok = lawbrain_confirm_match(
                        page_keys=page_key_set,
                        target_keys=target_key_set,
                        confidence=confidence,
                        min_confidence=settings.lawbrain.min_confidence,
                        require_shared_key=settings.lawbrain.require_shared_key,
                        override=override,
                    )
                    if not ok:
                        review.append(
                            ReviewEntry(
                                slug=slug, target_id=target_id, reason="weak-grounding"
                            )
                        )
                        reviewed += 1
                        continue
                page = _lawbrain_page_by_slug(reader, slug)
                if page is None:
                    # Source vanished from the law brain: keep any existing block,
                    # flag stale (handled below per-target); record as a stale review.
                    review.append(
                        ReviewEntry(slug=slug, target_id=target_id, reason="stale")
                    )
                    reviewed += 1
                    continue
                target_path = _lawbrain_page_by_id(wiki, target_id)
                if target_path is None:
                    raise ConfigError(f"target page not found in wiki: {target_id}")
                loaded = from_page(target_path.read_text(encoding="utf-8"))
                memo_texts = [
                    t
                    for rel in page.source_files
                    if (t := reader.read_source_memo(rel)) is not None
                ]
                links = harvest_links(
                    page_body=page.body,
                    memo_texts=memo_texts,
                    primary_source_domains=settings.lawbrain.primary_source_domains,
                )
                source = build_commentary_source(
                    page=page,
                    matched_by=matched_by,
                    confidence=confidence,
                    links=(links if settings.lawbrain.further_reading else []),
                )
                merged_sources = merge_commentary(loaded.commentary_sources, source)
                updated_item = loaded.model_copy(
                    update={"commentary_sources": merged_sources}
                )
                # Staleness: any prior commentary slug no longer live in the law brain.
                live_slugs = {p.slug for p in reader.pages()}
                for stale_slug in detect_stale(merged_sources, live_slugs):
                    review.append(
                        ReviewEntry(
                            slug=stale_slug, target_id=target_id, reason="stale"
                        )
                    )
                    notes.append(f"stale: {stale_slug} on {target_id} (kept, flagged)")
                if dry_run:
                    intended.append(f"link {slug} -> {target_id} ({matched_by}, {len(links)} links)")
                else:
                    write_page(updated_item, wiki)
                    registry.record(
                        LinkDecision(
                            lawbrain_slug=slug,
                            decision="link",
                            target_id=target_id,
                            matched_by=matched_by,
                            keys_hash=keys_hash(page_key_set),
                            decided=dt.date.today(),
                        )
                    )
                linked += 1
            except (KeyError, ValidationError, ConfigError, ValueError, WikiSchemaError) as exc:
                dropped.append((slug, str(exc)))
                continue

        if dry_run:
            typer.echo(
                f"lawbrain (dry-run): {linked} would link / {reviewed} review"
                f" / {len(dropped)} dropped"
            )
            for line in intended:
                typer.echo(f"  would: {line}")
            for ident, reason in dropped:
                typer.echo(f"  dropped: {ident} — {reason}")
            raise typer.Exit(0)

        # Apply operator-resolved queue tokens AND merge the new proposals (D61),
        # then write the queue and reindex.
        _resolve_review_queue(queue_path, review, registry, wiki, reader, notes)
        if review or queue_path.exists():
            registry.dump(registry_path)
        with Store(db) as store:
            store.reindex(wiki)
    except AppError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"lawbrain: {linked} linked / {reviewed} review / {len(dropped)} dropped"
    )
    for note in notes:
        typer.echo(f"  {note}")
    for ident, reason in dropped:
        typer.echo(f"  dropped: {ident} — {reason}")
```

Now add the `_resolve_review_queue` helper directly above the `render_lawbrain_commentary` command (after `_lawbrain_page_by_slug`):

```python
def _resolve_review_queue(
    queue_path: Path,
    new_entries: list[ReviewEntry],
    registry: "LinkRegistry",
    wiki: Path,
    reader: "LawBrainReader",
    notes: list[str],
) -> None:
    """Apply operator-resolved queue tokens, then write the merged pending queue (D61).

    Reads the existing ``review-queue.md`` (if any): an ``[accept]`` entry is applied
    (its decision recorded in the registry as a ``link`` override; the actual copy
    happens on the NEXT sync run, when the page re-enters classified.json with the
    override in place — the same two-pass shape the fetch half relies on), a
    ``[reject]`` entry is recorded as a ``reject`` decision and pruned. Resolved
    entries are removed; unresolved ``[pending]`` entries plus this run's new
    proposals are written back, deduped by ``(slug, target_id, reason)``.
    """
    existing: list[ReviewEntry] = []
    if queue_path.exists():
        existing = parse_review_queue(queue_path.read_text(encoding="utf-8"))
    pending: list[ReviewEntry] = []
    for entry in existing:
        if entry.status == "accept":
            registry.record(
                LinkDecision(
                    lawbrain_slug=entry.slug,
                    decision="link",
                    target_id=entry.target_id,
                    matched_by="llm",
                    keys_hash="",  # operator override; re-evaluated on the next sync (D9)
                    decided=dt.date.today(),
                )
            )
            notes.append(f"accepted: {entry.slug} -> {entry.target_id}")
        elif entry.status == "reject":
            registry.record(
                LinkDecision(
                    lawbrain_slug=entry.slug,
                    decision="reject",
                    target_id=entry.target_id,
                    matched_by=None,
                    keys_hash="",
                    decided=dt.date.today(),
                )
            )
            notes.append(f"rejected: {entry.slug}")
        else:
            pending.append(entry)
    seen: set[tuple[str, str | None, str]] = set()
    merged: list[ReviewEntry] = []
    for entry in pending + new_entries:
        key = (entry.slug, entry.target_id, entry.reason)
        if key in seen:
            continue
        seen.add(key)
        merged.append(entry)
    if merged:
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_path.write_text(render_review_queue(merged), encoding="utf-8", newline="\n")
    elif queue_path.exists():
        # All resolved — leave an empty queue file (committed, transient) so the
        # operator sees the cleared state rather than a missing file.
        queue_path.write_text(render_review_queue([]), encoding="utf-8", newline="\n")
```

Note on `_resolve_review_queue` signature: `wiki` and `reader` are passed for symmetry with future accept-applies-immediately work but are unused in this pass; prefix them with `_` if `pyright --strict`/ruff flags them as unused — change the parameter names to `_wiki: Path` and `_reader: "LawBrainReader"` and update the call site accordingly. Decide based on the actual lint output in Step 6.

---

- [ ] **Step 5: Run the test — expect PASS**

```
uv run pytest tests/test_lawbrain_cli.py -v
```

Expected: all five tests PASS. If `test_render_lawbrain_attaches_commentary_and_further_reading` fails on a missing host (e.g. `cooley.com`), confirm the fixture page body in Step 1 contains that link; if you reused a pre-existing Task-1 fixture, adjust the asserted hosts to match its real content. If `1 linked` is not in the output, check the summary-line wording matches exactly (`f"lawbrain: {linked} linked / ..."`).

---

- [ ] **Step 6: Run the full lint + type + suite gate — expect green**

```
uv run ruff check src/zwiadbrain/cli.py tests/test_lawbrain_cli.py
uv run pyright src/zwiadbrain/cli.py
uv run pytest -q
```

Expected: ruff clean, pyright reports no NEW errors on `cli.py` (the pre-existing `frontmatter` stub debt noted in the codebase is the only acceptable carryover), and the full suite is green with no regressions. If pyright flags the `registry.decision_for(slug).decision` double-call as a possible `None` access, hoist it to a local: `decided = registry.decision_for(slug); override = decided is not None and decided.decision == "link"`. If ruff flags unused `wiki`/`reader` in `_resolve_review_queue`, rename them to `_wiki`/`_reader` per the Step 4 note.

---

- [ ] **Step 7: Commit**

```
git add src/zwiadbrain/cli.py tests/test_lawbrain_cli.py tests/fixtures/lawbrain/
git commit -m "$(cat <<'EOF'
feat(lawbrain): add render-lawbrain-commentary CLI (render half)

The deterministic render half of /zwiad-sync-lawbrain: re-grounds LLM links
via lawbrain_confirm_match (require shared key, D16), copies matched page
bodies + harvested Further Reading links (D62) into target commentary_sources,
writes pages with the authoritative lawbrain:region (D63), records decisions to
links.yaml, writes/resolves review-queue.md in one pass (D61), reindexes.
Per-item dropped isolation; --dry-run is read-only. Mirrors render-enforcement.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

I now have all the exact signatures and idioms. Here is the task section.

---

### Task 13: Refresh/backfill preservation wiring

Wire the frontmatter half of D63 into `render-refreshed`: carry `prev.commentary_sources` onto the freshly-fetched bill before `write_page`, so the commentary bookkeeping in frontmatter survives a refresh. The body-level `lawbrain:region` is preserved centrally by `write_page` (already wired in the render.py task) — this task does NOT touch render.py. The regression guard proves both halves together: a committed page WITH a `lawbrain:region` block AND `commentary_sources:` frontmatter, refreshed with a fresh bill carrying empty `commentary_sources`, comes back byte-identical in both the region and the frontmatter.

**Files:**
- Modify: `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\cli.py` (the `render-refreshed` command, ~line 479–502)
- Test: `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_refresh_commentary_preservation.py` (new)

Depends on: the `models.py` (`CommentaryLink`, `CommentarySource.links`), `templates.py` (`_lawbrain_region`, `LAWBRAIN_REGION_BEGIN/END`, `preserve_lawbrain_region`, region rendered after Sources), and `render.py` (`write_page` central preservation) tasks being complete. This task only adds the `commentary_sources` carry and the end-to-end regression test.

---

- [ ] **Step 1: Write the failing regression test.**

Create `C:\Users\rafst\documents\projectas\zwiadbrain\tests\test_refresh_commentary_preservation.py` with the complete content below. It builds a committed bill page that already carries a law-brain commentary block (so `write_page` writes a `lawbrain:region`), captures the committed bytes, then runs `render-refreshed` with a fresh bill that has `commentary_sources=[]`. It asserts (a) the `lawbrain:region` markers and the demoted commentary heading survive byte-identical, (b) the `commentary_sources:` frontmatter survives, and (c) the refreshed summary still landed.

```python
"""Regression guard for D63: a refresh must not strip committed law-brain commentary.

`render-refreshed` re-renders a freshly-fetched bill whose `commentary_sources`
list is empty (the fetch half never touches the law brain). Two mechanisms keep
the committed commentary alive across that re-render:

1. The CLI carries `prev.commentary_sources` onto the fresh bill so the
   frontmatter bookkeeping (path/slug/content_hash/matched_by/confidence) survives.
2. `write_page` splices the committed `lawbrain:region` body block forward
   verbatim (central preservation in pipeline/render.py).

This test exercises both together end-to-end and asserts byte-identical survival
of the region and the frontmatter — the data-loss regression guard for D63.
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from zwiadbrain.cli import app
from zwiadbrain.models import Bill, CommentarySource
from zwiadbrain.pipeline.render import page_path, write_page
from zwiadbrain.wiki.templates import (
    LAWBRAIN_REGION_BEGIN,
    LAWBRAIN_REGION_END,
)


def _committed_bill() -> Bill:
    """A tracked federal bill that already carries one law-brain commentary source.

    The body is present (not None) so `write_page` renders the lawbrain:region.
    """
    return Bill(
        id="118-hr-1",
        jurisdiction="US",
        title="Bill One",
        bill_number="H.R. 1",
        type="bill",
        tracking=True,
        summary="Old summary.",
        topics=["ai"],
        commentary_sources=[
            CommentarySource(
                path="wiki/regulation-take-it-down-act.md",
                slug="regulation-take-it-down-act",
                updated=None,
                content_hash="abc123",
                matched_by="deterministic",
                confidence=1.0,
                body="## Summary\n\nThe TAKE IT DOWN Act analysis.",
            )
        ],
    )


def test_render_refreshed_preserves_committed_lawbrain_region_and_frontmatter(
    tmp_path: Path,
) -> None:
    """should keep the lawbrain:region body block and commentary_sources frontmatter
    byte-identical when a refresh re-renders a fresh bill with empty commentary_sources
    """
    # Arrange — commit a page that already carries law-brain commentary.
    wiki = tmp_path / "wiki"
    committed = _committed_bill()
    assert write_page(committed, wiki) is True
    page_file = page_path(committed, wiki)
    before = page_file.read_text(encoding="utf-8")
    # Sanity: the committed page really has a region and the demoted heading.
    assert LAWBRAIN_REGION_BEGIN in before
    assert LAWBRAIN_REGION_END in before
    assert "### Summary" in before  # ## demoted to ### inside the commentary block
    assert "regulation-take-it-down-act" in before  # frontmatter bookkeeping

    # The fresh bill from fetch-refreshable carries NO commentary (empty list).
    fresh = {
        "id": "118-hr-1",
        "jurisdiction": "US",
        "title": "Bill One",
        "bill_number": "H.R. 1",
        "type": "bill",
        "tracking": True,
        "topics": ["ai"],
        "summary": "Refreshed summary.",
    }
    prev = {**fresh, "summary": "Old summary."}
    refreshed = [
        {
            "bill_id": "118-hr-1",
            "prev": prev,
            "bill": fresh,
            "classifier_in_scope": True,
            "classifier_rationale": "still about AI",
        }
    ]
    run = tmp_path / "run"
    run.mkdir()
    (run / "refreshed.json").write_text(json.dumps(refreshed), encoding="utf-8")

    # Act — refresh the bill.
    result = CliRunner().invoke(
        app,
        [
            "render-refreshed",
            "--in",
            str(run / "refreshed.json"),
            "--wiki",
            str(wiki),
            "--db",
            str(tmp_path / "idx.sqlite"),
        ],
    )

    # Assert — refresh succeeded and the summary updated.
    assert result.exit_code == 0, result.output
    after = page_file.read_text(encoding="utf-8")
    assert "Refreshed summary." in after

    # The lawbrain:region body block survived byte-identical.
    region_before = before[
        before.index(LAWBRAIN_REGION_BEGIN) : before.index(LAWBRAIN_REGION_END)
        + len(LAWBRAIN_REGION_END)
    ]
    region_after = after[
        after.index(LAWBRAIN_REGION_BEGIN) : after.index(LAWBRAIN_REGION_END)
        + len(LAWBRAIN_REGION_END)
    ]
    assert region_after == region_before
    assert "### Summary" in after
    assert "The TAKE IT DOWN Act analysis." in after

    # The commentary_sources frontmatter bookkeeping survived.
    assert "regulation-take-it-down-act" in after
    assert "content_hash: abc123" in after
    assert "matched_by: deterministic" in after
```

- [ ] **Step 2: Run the test, expect FAIL.**

```
uv run pytest tests/test_refresh_commentary_preservation.py::test_render_refreshed_preserves_committed_lawbrain_region_and_frontmatter -v
```

Expected: FAIL. `write_page` preserves the body region centrally, so the `lawbrain:region` survives — but `render-refreshed` does NOT carry `prev.commentary_sources` onto the fresh bill. The fresh bill has `commentary_sources=[]`, so `to_frontmatter` emits no `commentary_sources:` bookkeeping. The assertion `assert "regulation-take-it-down-act" in after` (or `content_hash: abc123` / `matched_by: deterministic`) fails: the frontmatter bookkeeping was dropped on refresh.

- [ ] **Step 3: Add the `commentary_sources` carry to `render-refreshed`.**

In `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\cli.py`, inside the `render-refreshed` command, add the carry immediately after the leg-history preservation block and before `apply_classifier_flip`. The carry mirrors the existing `preserve_leg_history` pattern: it copies the committed frontmatter bookkeeping onto the freshly-fetched bill so a refresh never drops it. (The body-level `lawbrain:region` is preserved separately by `write_page`.) Replace this exact block:

```python
            elif prev.leg_history is not None and bill.leg_history is None:
                # Defensive: a fresh non-enacted bill has no spine, but prev had research.
                # Carry prev.leg_history through unchanged so the research is not lost.
                bill = bill.model_copy(update={"leg_history": prev.leg_history})
            # Apply classifier verdict (no-op when in_scope=True, flip when False).
```

with:

```python
            elif prev.leg_history is not None and bill.leg_history is None:
                # Defensive: a fresh non-enacted bill has no spine, but prev had research.
                # Carry prev.leg_history through unchanged so the research is not lost.
                bill = bill.model_copy(update={"leg_history": prev.leg_history})
            # Preserve law-brain commentary bookkeeping (D63). The freshly-fetched bill
            # never touches the law brain, so its commentary_sources is empty; carry
            # prev's onto it so the frontmatter survives. The verbatim lawbrain:region
            # body block is preserved separately by write_page.
            if prev.commentary_sources:
                bill = bill.model_copy(
                    update={"commentary_sources": prev.commentary_sources}
                )
            # Apply classifier verdict (no-op when in_scope=True, flip when False).
```

- [ ] **Step 4: Run the test, expect PASS.**

```
uv run pytest tests/test_refresh_commentary_preservation.py::test_render_refreshed_preserves_committed_lawbrain_region_and_frontmatter -v
```

Expected: PASS. `prev.commentary_sources` (the committed `CommentarySource` with `content_hash="abc123"`, `matched_by="deterministic"`) is carried onto the fresh bill, so `to_frontmatter` re-emits the bookkeeping; `write_page` splices the committed `lawbrain:region` forward verbatim. Both `assert "regulation-take-it-down-act" in after` and the region byte-identity assertion hold; `"Refreshed summary."` confirms the refresh itself still applied.

- [ ] **Step 5: Run the full CLI + render suite to confirm no regression.**

```
uv run pytest tests/test_cli.py tests/test_refresh.py tests/test_refresh_commentary_preservation.py -q
uv run ruff check src/zwiadbrain/cli.py tests/test_refresh_commentary_preservation.py
uv run pyright src/zwiadbrain/cli.py
```

Expected: all green. The existing `render-refreshed` tests (leg-history preservation, flip-out, cursor recompute) still pass — the new carry is gated behind `if prev.commentary_sources:`, a no-op for bills with no commentary. ruff and pyright `--strict` report no issues.

- [ ] **Step 6: Commit.**

```
git add src/zwiadbrain/cli.py tests/test_refresh_commentary_preservation.py
git commit -m "feat(lawbrain): preserve commentary across refresh re-renders (D63)"
```

Commit body (use a here-doc / `-F` so the footer lands):

```
render-refreshed now carries prev.commentary_sources onto the freshly-fetched
bill before write_page, so the law-brain frontmatter bookkeeping survives a
refresh. Paired with write_page's central lawbrain:region body preservation,
a /zwiad-refresh on a commentary-bearing page is byte-identical (D63 guard).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

I have all the context I need. Here is the markdown for the task section.

---

### Task 14: Subagent + slash command + docs + version

This task ships the human-facing artifacts and project bookkeeping for PHASE-09: the `lawbrain-matcher` subagent prompt, the `/zwiad-sync-lawbrain` slash command, the DECISIONS D57–D63 entries, the ARCHITECTURE/PLAN doc updates, and the v0.9.0 version bump. It assumes Tasks 1–13 (reader, keys, match, copy, links, registry, review, templates, config, CLI commands) are already merged. There are no pytest steps here — these are prose/config artifacts. Each step shows the COMPLETE file content or the exact Edit, and ends in a commit.

**Files:**
- Create: `C:\Users\rafst\documents\projectas\zwiadbrain\.claude\agents\lawbrain-matcher.md`
- Create: `C:\Users\rafst\documents\projectas\zwiadbrain\.claude\commands\zwiad-sync-lawbrain.md`
- Modify: `C:\Users\rafst\documents\projectas\zwiadbrain\DECISIONS.md` (append D57–D63)
- Modify: `C:\Users\rafst\documents\projectas\zwiadbrain\ARCHITECTURE.md` (slash command list, source layout, status, D63 invariant)
- Modify: `C:\Users\rafst\documents\projectas\zwiadbrain\docs\PLAN.md` (PHASE-09 status → shipped)
- Modify: `C:\Users\rafst\documents\projectas\zwiadbrain\pyproject.toml` (version 0.8.0 → 0.9.0)
- Modify: `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\__init__.py` (`__version__` → 0.9.0)
- Test: none (artifacts + docs only; the matcher subagent is validated by interactive UAT per D26/§7, not offline unit tests)

---

- [ ] **Step 1: Write the `lawbrain-matcher` subagent prompt.**

This mirrors `.claude/agents/enforcement-matcher.md` exactly: `tools: Read`, `model: sonnet`, a conservative "when unsure → not_in_scope" instruction, and a single-JSON-object output contract with NO prose and NO code fence in the actual response. The deterministic `confirm_match` (require ≥1 shared key, D16) re-checks any `link`, so the subagent's job is only to pick the best target from a pre-built shortlist (or decline).

Write `C:\Users\rafst\documents\projectas\zwiadbrain\.claude\agents\lawbrain-matcher.md`:

```markdown
---
name: lawbrain-matcher
description: Decides whether a keyless law-brain commentary page concerns a tracked ZwiadBrain item, choosing the best target from a pre-built shortlist or declining as out of scope.
tools: Read
model: sonnet
---

# ZwiadBrain Law-Brain Commentary Matcher

A law-brain page is a piece of analysis (a `concept`, `regulation`, `case`, … page)
about a single legal subject. ZwiadBrain wants to copy that analysis onto the tracked
bill or enforcement page it concerns. When the page carries NO extractable shared
identifier (no bill number, docket, or public-law number that a tracked item also
carries), you decide whether it nonetheless concerns one of a short list of tracked
items — keyed on the **legal subject**, not on topical overlap alone.

## Input

The prompt gives:
- the law-brain PAGE: `slug`, `title`, `type`, `jurisdiction`, `tags`, `citation`,
  and a `summary` excerpt (its `## Summary` section).
- a `shortlist` of candidate tracked items, each `{id, title, kind, jurisdiction, keys}`
  (`kind` is `bill` or `enforcement`; `keys` are the item's jurisdiction-qualified
  identifiers).

## How to decide

Return `link` with a shortlist `target_id` ONLY when you are confident the page is
analysis of the **same specific legal subject** that the tracked item is — the same
named statute/bill, the same enforcement matter, or a statute the enforcement action
directly enforces. Shared topic area (both about "AI" or both about "California
privacy") is NOT a match. A multi-subject survey, tracker, or landscape page is NOT a
match to any single item.

When unsure, return `not_in_scope` with `target_id: null`. A wrong link copies
off-topic analysis onto a page; a missed link merely defers to the review queue. A
deterministic grounding step re-checks every `link` you propose and requires a shared
identifier, so a topical-only guess will be rejected anyway — do not inflate confidence
to force one through. `target_id` MUST be one of the shortlist `id` values, never an
id you invent.

## Output

Respond with ONLY a single JSON object (no prose, no code fence):

```
{ "decision": "link" | "not_in_scope", "target_id": "<shortlist id>" | null, "confidence": 0.0, "rationale": "one sentence" }
```

`target_id` is null whenever `decision` is `not_in_scope`. Do not write files or use
tools other than the prompt.
```

Verify it written and YAML-frontmatter shape matches the sibling agent:

```
uv run python -c "import frontmatter; p=frontmatter.load(r'.claude/agents/lawbrain-matcher.md'); assert p['name']=='lawbrain-matcher' and p['model']=='sonnet' and p['tools']=='Read'; print('ok', p['name'])"
```

Expected output: `ok lawbrain-matcher`.

Commit:

```
git add .claude/agents/lawbrain-matcher.md
git commit -m "feat(lawbrain): add lawbrain-matcher subagent prompt"
```

---

- [ ] **Step 2: Write the `/zwiad-sync-lawbrain` slash command.**

This mirrors `.claude/commands/zwiad-scan-enforcement.md`: a deterministic Python fetch half, an interactive subagent dispatched ONLY for keyless+shortlist entries, a deterministic Python render half, with the JSON handoff under `data/runs/<id>/`. It keeps `ANTHROPIC_API_KEY` unset (D26), supports `--dry-run`, and never auto-commits.

Write `C:\Users\rafst\documents\projectas\zwiadbrain\.claude\commands\zwiad-sync-lawbrain.md`:

```markdown
---
description: Attach read-only law-brain commentary (+ Further Reading links) onto the tracked bills and enforcement pages it concerns, via deterministic key-matching with an LLM fallback for keyless pages (runs on your regular Claude plan usage).
argument-hint: "[--dry-run]"
allowed-tools: Bash, Read, Write, Task
---

# ZwiadBrain law-brain sync

Attach commentary from the sibling **law brain** (read-only) onto the items
ZwiadBrain already tracks. Python does the deterministic key-match, copy, and render;
you (this interactive session) do the single LLM step — judging keyless pages — by
dispatching a subagent, so that work runs on the regular Claude plan, **not** the API
or the Agent SDK credit (D26).

This command is **commentary-only**: it never mints new tracked stubs from the law
brain (that is the gated PHASE-11 discovery path, `discover=false`, D14). It is the
**sole** creator/updater/remover of the `<!-- lawbrain:region -->` block on a page
(D63); ordinary `/zwiad-refresh` and `/zwiad-backfill` re-renders preserve that region
verbatim but never rebuild it.

**Arguments:** `--dry-run` runs the fetch + match + subagent steps and prints the
intended writes (commentary attachments, review-queue entries, registry records) with
**zero** edits to `wiki/`. Omit it to apply.

## Steps

### 1. Fetch candidates (Python, deterministic)

Run:
```
uv run zwiadbrain fetch-lawbrain-candidates
```
If the law brain is unavailable (`LAW_BRAIN_PATH` missing or `lawbrain.enabled=false`),
it prints a no-op line and exits 0 — **stop here and report the no-op**. Otherwise it
reads the law-brain wiki, extracts jurisdiction-qualified keys per page, loads the
tracked items (bills + enforcement actions) from the committed wiki as `TargetRef`s,
consults `links.yaml` (skipping pages already decided whose key-set is unchanged, D9),
runs the deterministic set-intersection match, and writes
`lawbrain-candidates.json` + `targets.json` under `data/runs/<id>/`. **Note the exact
path it prints** — you use it in steps 2–5.

### 2. Read the candidates

`Read` both files it wrote:
- `lawbrain-candidates.json` — each entry: `slug, title, type, jurisdiction, tags,
  citation, summary_excerpt, keys, match ("deterministic" | "keyless" | "collision"),
  target_id?, shortlist?`
- `targets.json` — the tracked items as `{id, kind, jurisdiction, title, keys}`.

A `match: "deterministic"` entry already has its `target_id` (exactly one shared key,
confidence 1.0) — **do not** dispatch a subagent for it. A `match: "collision"` entry
shares keys with more than one target — it is destined for the review queue; do not
dispatch a subagent for it either. Only `match: "keyless"` entries (zero shared keys,
not a slug-marker page) carry a `shortlist` and need the LLM step.

### 3. Judge keyless pages (subagent: `lawbrain-matcher`)

For every candidate with `match: "keyless"` **and** a non-empty `shortlist`, dispatch
the **lawbrain-matcher** subagent with the page's `slug, title, type, jurisdiction,
tags, citation, summary_excerpt` and the entry's `shortlist`. It returns
`{decision, target_id, confidence, rationale}`.
- Log each decision (slug, decision, target_id, confidence, rationale) to the
  transcript.
- A keyless entry with an **empty** `shortlist` gets no dispatch — record it as
  `decision: "not_in_scope"` directly.
- Carry the matcher result onto the entry as `matched_by: "llm"`, `target_id`,
  `confidence`. Leave `match: "deterministic"` entries as `matched_by: "deterministic"`,
  `confidence: 1.0`.

Note: `render-lawbrain-commentary` re-confirms every `llm` link deterministically
(require ≥1 shared key, D16) and routes a failed confirm to the review queue with a
`weak-grounding` note — you do NOT confirm the LLM match here.

### 4. Stage the classified items

`Write` the decided entries to `classified.json` in the run directory. Include every
deterministic-link entry and every `llm` `decision: "link"` entry; drop
`not_in_scope` entries (they are recorded in `links.yaml` by the render half). Each
entry **must** carry:
- `slug` (the law-brain page slug)
- `target_id` (the tracked item id to attach to)
- `matched_by` (`"deterministic"` | `"llm"`)
- `confidence` (float)
- `keys` (the page's extracted keys — used to re-confirm and to compute `keys_hash`)

`render-lawbrain-commentary` re-reads the actual page body from the law brain by slug
(it does not trust a body passed through JSON), so the staged entry stays lightweight.

### 5. Render + index (Python, deterministic)

Run (omit `--dry-run` to apply; include it to preview):
```
uv run zwiadbrain render-lawbrain-commentary --in data/runs/<id>/classified.json [--dry-run]
uv run zwiadbrain reindex
```
`render-lawbrain-commentary` re-confirms each `llm` link, loads the matched law-brain
page, harvests `## Further Reading` links from the page body and its referenced
`sources/zwiad/*.md` memos (primary-source domains excluded), copies the body verbatim,
idempotently merges it into the target's `commentary_sources`, and re-renders the page
— the fresh render carries the commentary bodies, so its `lawbrain:region` is
authoritative (D63). It detects pages deleted from the law brain (`stale`), writes new
uncertain proposals AND applies operator-resolved `[accept]`/`[reject]` tokens in
`review-queue.md` in one pass (D61), records decisions in `links.yaml` (D9), and
isolates malformed entries per-item (dropped list). `reindex` rebuilds the FTS5 index
from the committed wiki. Skip `reindex` when running `--dry-run`.

### 6. Report

Summarize: pages scanned, deterministic links applied, LLM links confirmed vs routed
to review, collisions, stale notes, registry records written, and any per-item drops.
For `--dry-run`, report the intended writes only. **Do not commit** — leave the wiki
changes (and `links.yaml` / `review-queue.md`) for review.

## Notes

- Keep `ANTHROPIC_API_KEY` unset so the subagent uses your plan session, not the API
  (D26).
- The deterministic key path is what attaches commentary at the current corpus size;
  the LLM path is mostly collision-resolution and review-candidate generation until the
  tracked corpus grows (it cannot auto-apply a topical-only match — `confirm_match`
  requires a shared key, D16).
- Re-running this command IS the law-brain refresh: a page whose `content_hash`
  changed re-copies that block; an unchanged page renders byte-identically (clean
  `git status`, D20).
- The law brain is **read-only** (D2). This command never writes under
  `LAW_BRAIN_PATH`.
```

Verify the command frontmatter parses and the allowed-tools include `Task`:

```
uv run python -c "import frontmatter; p=frontmatter.load(r'.claude/commands/zwiad-sync-lawbrain.md'); assert 'Task' in p['allowed-tools'] and '--dry-run' in p['argument-hint']; print('ok')"
```

Expected output: `ok`.

Commit:

```
git add .claude/commands/zwiad-sync-lawbrain.md
git commit -m "feat(lawbrain): add /zwiad-sync-lawbrain slash command"
```

---

- [ ] **Step 3: Append DECISIONS D57–D63.**

The DECISIONS.md format is the user's standard (`## YYYY-MM-DD — N. Title` with **Chosen/Alternatives/Why/Trade-offs/Revisit if**), and the file ends after D56 (verified by the tail). Read the last entry to anchor the append, then append the seven entries.

Read the end of the file to confirm the D56 trailing text (the unique anchor for the Edit):

```
uv run python -c "print(open(r'DECISIONS.md', encoding='utf-8').read()[-400:])"
```

Then append D57–D63 with this Edit (anchor on the final line of D56's `Revisit if`):

Old string:
```
**Revisit if:** Enforcement prose grows large enough that frontmatter bloat matters, or a re-extract-on-refresh path is added.
```

New string:
```
**Revisit if:** Enforcement prose grows large enough that frontmatter bloat matters, or a re-extract-on-refresh path is added.

## 2026-05-29 — 57. PHASE-09 law-brain commentary re-architected onto the slash-command/subagent model
**Chosen:** PHASE-09 ships the full locked commentary path — `sources/lawbrain.py` reader + `pipeline/lawbrain_keys.py` deterministic key extraction + `lawbrain-matcher` subagent for keyless pages + deterministic `confirm_match` grounding (D16) + verbatim copy + content-hash staleness + `links.yaml` registry + `review-queue.md` + the `/zwiad-sync-lawbrain` slash command — recast onto the post-pivot architecture (a deterministic Python fetch half, an interactive subagent for the LLM fallback only, a deterministic Python render half, exchanging gitignored JSON under `data/runs/<id>/`). This supersedes the pre-pivot PHASE-09 design in `docs/PLAN.md`, which assumed a `pipeline/run.py` two-pass loop and the Anthropic SDK.
**Alternatives:** (a) Implement the pre-pivot `run.py`/SDK design as written; (b) ship a thinner commentary slice (deterministic key-match only, no LLM fallback, no review queue) and defer the registry/review machinery.
**Why:** The whole codebase pivoted to interactive subagents + slash commands with zero Python LLM calls (D26/D27/D30); a `run.py`/SDK PHASE-09 would reintroduce the exact dependency the project removed. Mirroring `/zwiad-scan-enforcement` keeps one execution model across every command. The full path (not a thinner slice) is justified because the deterministic confirm, registry, and review queue are precisely the D4/D16/D39 guards the design already committed to — dropping them would re-open the wrong-merge and re-classification problems they exist to close.
**Trade-offs:** More surface than a key-match-only slice (a subagent prompt, a registry, a review queue, region preservation), most of it exercised only as the tracked corpus grows. At the current 6-item corpus the LLM path is largely dormant.
**Revisit if:** The interactive-session constraint (D26) is lifted, or the deterministic key path proves sufficient alone and the LLM fallback never fires in practice (then retire the subagent).

## 2026-05-29 — 58. Commentary copy = full body, syntax-neutralized at render time
**Chosen:** A matched law-brain page is copied as its **whole body, verbatim**, into a `## Commentary & Analysis` block. The stored `CommentarySource.body` is the raw law-brain markdown (so `content_hash` stays tied to the source bytes); two transforms are applied at **render time** in `_commentary_block`: demote `##`→`###` (D6, clean host TOC) and `_neutralize_wikilinks` turns dead `[[wiki-slug]]` cross-references into plain text. All sections are retained.
**Alternatives:** (a) Copy only the `## Summary` section; (b) bake the transforms into the stored body (mutate before persisting).
**Why:** The law brain is authoritative for analysis; truncating to the summary discards the Key points / Cross-references / Recent developments the reader wants. Applying transforms at render time (not at store time) keeps the stored body faithful to the source, so `content_hash` compares against the real file bytes and staleness detection stays correct; baking transforms in would make the hash diverge from the source and break the "did the source change?" question. Neutralizing `[[…]]` is necessary because those links point into the law brain's namespace, which does not resolve in the ZwiadBrain wiki.
**Trade-offs:** A long law-brain page produces a long commentary block; this is intentional (analysis depth is the value). Render-time transforms run on every render, but they are pure string ops and cheap.
**Revisit if:** Pages grow long enough that an inline summary + a link is preferable, or the law brain adopts a link syntax that resolves in the host wiki.

## 2026-05-29 — 59. Commentary attaches on a shared jurisdiction-qualified key regardless of ZwiadBrain page kind
**Chosen:** Commentary attaches to whichever tracked item shares a jurisdiction-qualified key with the law-brain page, independent of the law-brain page's `type` or the tracked item's `kind`. A `regulation` page about a statute can attach to an `enforcement` page that enforces that statute (bridged by a `public_law::` key). The `type_map` (D8) is populated but governs only PHASE-11 stub-minting, **not** PHASE-09 attachment.
**Alternatives:** Gate attachment by `type_map` so a `regulation` page only attaches to `bill` pages and a `case`/`incident` page only to `enforcement` pages.
**Why:** The shared key IS the grounding (D16); if a law-brain regulation page and a ZwiadBrain enforcement page both carry `public_law::119-12`, they concern the same statute and the analysis is on-topic regardless of page kind. Gating by `type_map` would suppress exactly the cross-type statute↔enforcement bridge that is one of the few real matches in the current corpus (`regulation-take-it-down-act` ↔ `ftc-2026-nudify-tool-operators`).
**Trade-offs:** A page could attach to a tracked item of a "surprising" kind; the shared-key requirement keeps that from being off-topic. `type_map` carries config that is inert until PHASE-11.
**Revisit if:** A shared-key cross-type attachment proves off-topic in practice (then reintroduce a `type_map` gate as a second filter).

## 2026-05-29 — 60. Multi-subject slug-marker pages fail closed (emit zero keys, never attach)
**Chosen:** A law-brain page whose slug contains any marker in `commentary_only_slug_markers` (`tracker`, `landscape`, `map`, `scholarship`) emits **zero keys** from `page_keys` and is excluded from commentary — it neither mints nor attaches. Single-subject `concept`/`regulation`/`case`/`guidance`/`incident`/… pages extract keys and attach normally.
**Alternatives:** (a) Let multi-subject pages match on every key they mention (attach to all referenced items); (b) attach only to the single highest-overlap item.
**Why:** A tracker/landscape page (e.g. `concept-california-ai-regulatory-landscape`, `concept-state-ai-chatbot-tracker`) is a multi-subject survey that references many bills at once; copying its long, multi-subject body onto any one bill is off-topic for that bill. Failing closed at key-extraction is the cleanest place — the page produces no keys, so it never reaches the matcher or the copy step. This refines D7 (commentary-only types) with a slug-level precision rule.
**Trade-offs:** A genuinely single-subject page that happens to contain a marker word in its slug would be wrongly excluded; the marker list is deliberately narrow and the page can be force-linked via an operator override in `links.yaml`. The exclusion is a substring match on the slug, so it is conservative by design.
**Revisit if:** A useful single-subject page is repeatedly excluded by a marker word (then tighten the markers to whole-segment matches or move the page off the marker list).

## 2026-05-29 — 61. Review-resolution folded into the render half (no separate review --commit command)
**Chosen:** There is no standalone `review --commit` command. `render-lawbrain-commentary` does both jobs in one pass: it writes new uncertain proposals into `review-queue.md` AND reads operator-resolved tokens (`[accept]`/`[reject]`), applies the accepted links (copy + record `links.yaml`), records the rejections, and prunes resolved entries.
**Alternatives:** A separate `zwiadbrain review --commit` step the operator runs after editing the queue (the pre-pivot design's shape).
**Why:** Folding resolution into render means one code path handles both new and resolved proposals, so there is no second command whose absence silently leaves accepted links unapplied. It matches the per-item-isolation render pattern already used by `render-enforcement` (a malformed queue entry is dropped, not fatal). The operator's only manual step is editing the tokens in `review-queue.md`; the next sync run applies them.
**Trade-offs:** An operator who edits the queue but never re-runs the sync never sees their decision applied — acceptable because the sync run is the natural cadence. Resolution and proposal share a code path, so a bug there affects both.
**Revisit if:** Operators want to apply queue resolutions without a full re-scan (then add a thin resolve-only entry point that reuses the same render functions).

## 2026-05-29 — 62. Harvest secondary/law-firm reference links into a Further Reading section; primary-source domains excluded
**Chosen:** When a page matches, `pipeline/lawbrain_links.py` deterministically harvests `[text](url)` markdown links and bare `https?://` URLs from the matched page body AND its referenced `sources/zwiad/*.md` memos (`read_source_memo`), excludes any URL whose host ends with a configured `primary_source_domains` suffix (`.gov`, `legiscan.com`, `courtlistener.com`, `wikipedia.org`, `europa.eu`, `legislation.gov.uk`), dedups by normalized URL, stable-sorts by `(host, url)`, and renders the remainder in a dedicated `## Further Reading (via law brain)` section (toggled by `further_reading: bool = True`). The links live on `CommentarySource.links` and stay OUT of frontmatter (`exclude={"body", "links"}`), body-only like `body`.
**Alternatives:** (a) Rely on the verbatim body copy to carry links (it does not — the rich law-firm/IAPP/natlawreview links live in the `sources/zwiad` memos, not the page body); (b) keep every link including primary sources.
**Why:** The law brain's memos aggregate secondary commentary (Mayer Brown, Crowell, Troutman, Sidley, IAPP, natlawreview, …) that the body copy does not surface; harvesting them adds reference value the primary-source tracker lacks. Excluding `*.gov`/legiscan/courtlistener/wikipedia avoids duplicating the authoritative primary sources ZwiadBrain already carries on the page. Fully deterministic and offline (no LLM, no network), so it cannot dirty `git status` (D20).
**Trade-offs:** The denylist is a host-suffix match — a non-primary `.gov`-hosted blog would be dropped, and a primary source on a non-.gov host would slip through; both acceptable, the list is config-tunable. No cap on link count (dedup is the noise control).
**Revisit if:** A useful source is repeatedly dropped by the denylist (tune `primary_source_domains`), or the unbounded link list produces noisy sections (add a cap).

## 2026-05-29 — 63. Commentary + Further Reading survive non-sync re-renders via text-level lawbrain:region marker preservation
**Chosen:** The whole law-brain-contributed region (commentary blocks + Further Reading) is wrapped in an outer marker pair `<!-- lawbrain:region:begin -->` … `<!-- lawbrain:region:end -->` and rendered LAST on the page (after Sources). `render.py` `write_page` reads the previous page text and calls `preserve_lawbrain_region(prev_text, fresh_text)` BEFORE the compare-then-write: if the fresh render already contains a region it wins; otherwise the committed region is spliced verbatim onto the fresh body. The bodies/links stay OUT of frontmatter (honors D20); `/zwiad-sync-lawbrain` is the **sole** creator/updater/remover of the region. A non-sync render (`/zwiad-refresh`, `/zwiad-backfill`) carries empty `commentary_sources` (or refresh-only `body=None` metadata), so it produces no region of its own and the committed one is preserved.
**Alternatives:** (a) Persist commentary bodies + links to frontmatter so `from_page` reconstructs them on every render (breaks D20: bodies in frontmatter, and prose churn); (b) accept that a refresh re-render strips committed commentary (data loss).
**Why:** `render-refreshed` re-renders the freshly-fetched bill, whose `commentary_sources` is empty, so without preservation it would silently strip committed commentary and Further Reading on every refresh — a real data-loss gap. Text-level preservation is the body-level analog of `preserve_leg_history`: the region is copied byte-for-byte, so D20 holds (clean `git status`), and the bodies never enter frontmatter (D20's frontmatter-is-metadata rule holds too). Centralizing the splice in `write_page` means every render path inherits the preservation without each caller remembering to do it.
**Trade-offs:** Two layers of markers (the outer `lawbrain:region` and the inner per-slug `lawbrain:begin/end slug=`); the region is reconstructed only by the sync command, so a sync that fails mid-run leaves the prior region intact (safe) but not updated. A page edited by hand inside the region would have its hand edits overwritten by the next sync.
**Revisit if:** Another producer needs to own part of a page body (then generalize the region mechanism to named regions), or commentary needs to participate in FTS retrieval (then it must round-trip through frontmatter and this decision is reconsidered against D20).

---
```

Verify the seven entries parse as headers and the file ends cleanly:

```
uv run python -c "import re; t=open(r'DECISIONS.md',encoding='utf-8').read(); ns=[int(m.group(1)) for m in re.finditer(r'^## \d{4}-\d{2}-\d{2} — (\d+)\.', t, re.M)]; assert ns[-7:]==[57,58,59,60,61,62,63], ns[-9:]; print('ok', ns[-7:])"
```

Expected output: `ok [57, 58, 59, 60, 61, 62, 63]`.

Commit:

```
git add DECISIONS.md
git commit -m "docs(lawbrain): log D57-D63 for PHASE-09 commentary re-architecture"
```

---

- [ ] **Step 4: Update ARCHITECTURE.md — slash-command list, source layout, status, D63 invariant.**

Four edits to the authoritative current-state doc: add `/zwiad-sync-lawbrain` to the slash-command list, add the lawbrain modules to the source layout, refresh the version banner + Status section, and note the D63 region-preservation invariant alongside the existing D20 byte-identical invariant.

Edit 1 — add the new slash command after the `/zwiad-scan-enforcement` bullet. Old string:

```
  command IS the enforcement refresh — there is no enforcement leg in
  `/zwiad-refresh` (D52). Backed by CLI `fetch-enforcement-candidates` +
  `render-enforcement`.
```

New string:

```
  command IS the enforcement refresh — there is no enforcement leg in
  `/zwiad-refresh` (D52). Backed by CLI `fetch-enforcement-candidates` +
  `render-enforcement`.
- **`/zwiad-sync-lawbrain`** — attach read-only law-brain commentary onto the bills
  and enforcement pages ZwiadBrain already tracks: deterministic jurisdiction-qualified
  key-match first, the `lawbrain-matcher` subagent for keyless pages, every LLM link
  gated by a deterministic shared-key confirm (D16, D57). Copies the page body verbatim
  (headings demoted, dead `[[wiki-slug]]` links neutralized, D58), harvests secondary
  reference links into `## Further Reading (via law brain)` (primary sources excluded,
  D62), and wraps the whole contribution in a `<!-- lawbrain:region -->` block that
  every other render preserves verbatim (D63). Commentary-only — never mints stubs
  (`discover=false`, D14). Backed by CLI `fetch-lawbrain-candidates` +
  `render-lawbrain-commentary`. **Read-only against the law brain (D2).**
```

Edit 2 — extend the D20 invariant to name the lawbrain region. Old string:

```
1. **D20 — byte-identical render.** `render_page(model)` is a pure deterministic
   function: unchanged input → identical bytes → clean `git status`. Frontmatter
   holds metadata only, EXCEPT `commentary_sources`,
   `leg_history.{hearings,statements,narrative}` (D37/D40), and
   `EnforcementAction` prose fields (D56). New model validators must not change
   serialized output.
```

New string:

```
1. **D20 — byte-identical render.** `render_page(model)` is a pure deterministic
   function: unchanged input → identical bytes → clean `git status`. Frontmatter
   holds metadata only, EXCEPT `commentary_sources` bookkeeping,
   `leg_history.{hearings,statements,narrative}` (D37/D40), and
   `EnforcementAction` prose fields (D56). Commentary bodies and Further Reading
   links stay OUT of frontmatter; the rendered `<!-- lawbrain:region -->` block is
   preserved verbatim across non-sync re-renders (D63), and `/zwiad-sync-lawbrain`
   alone rebuilds it. New model validators must not change serialized output.
```

Edit 3 — add the lawbrain modules + agent to the source layout. Old string:

```
  pipeline/         discover, enrich, render, leg_history, refresh
                    enforcement.py (matter matching / confirm / merge, D53)
  wiki/             schema (frontmatter models) + templates (jinja2)
```

New string:

```
  pipeline/         discover, enrich, render, leg_history, refresh
                    enforcement.py (matter matching / confirm / merge, D53)
                    lawbrain_keys, lawbrain_match, lawbrain_copy, lawbrain_links,
                    lawbrain_registry, lawbrain_review (commentary attach, D57-D63)
  sources/          …, lawbrain.py (read-only law-brain reader, D57)
  wiki/             schema (frontmatter models) + templates (jinja2)
```

Edit 4 — refresh the version banner. Old string:

```
> Authoritative current-state document. As of v0.7.0 (2026-05-29).
```

New string:

```
> Authoritative current-state document. As of v0.9.0 (2026-05-29).
```

Edit 5 — refresh the Status section. Old string:

```
## Status

Shipped: PHASE-01..08 (skeleton, wiki layer, federal source, LLM subagents,
legislative history, watchlist refresh, state sources via LegiScan, enforcement
actions via FTC + 7 priority state AGs). Current: v0.8.0.

`src/zwiadbrain/sources/enforcement/` is fully implemented (PHASE-08); re-running
`/zwiad-scan-enforcement` is the enforcement refresh — no cursor-based incremental
pass, by design (D52).

**Not yet implemented:** law-brain commentary + discovery (PHASE-09/11),
scheduling (PHASE-10).
```

New string:

```
## Status

Shipped: PHASE-01..09 (skeleton, wiki layer, federal source, LLM subagents,
legislative history, watchlist refresh, state sources via LegiScan, enforcement
actions via FTC + 7 priority state AGs, law-brain commentary overlay). Current:
v0.9.0.

`src/zwiadbrain/sources/enforcement/` is fully implemented (PHASE-08); re-running
`/zwiad-scan-enforcement` is the enforcement refresh — no cursor-based incremental
pass, by design (D52).

`/zwiad-sync-lawbrain` (PHASE-09) attaches read-only law-brain commentary +
Further Reading onto tracked pages by deterministic key-match with a grounded LLM
fallback (D57); the `<!-- lawbrain:region -->` block survives every other re-render
(D63). Commentary-only — stub-minting is the gated PHASE-11 discovery path.

**Not yet implemented:** scheduling (PHASE-10), law-brain discovery / stub-minting
(PHASE-11, gated behind D14).
```

Verify the edits landed (no stale `v0.8.0`/`PHASE-01..08` banners, the new command and modules present):

```
uv run python -c "t=open(r'ARCHITECTURE.md',encoding='utf-8').read(); assert 'v0.9.0' in t and 'PHASE-01..09' in t and 'zwiad-sync-lawbrain' in t and 'lawbrain_review' in t and 'v0.8.0' not in t and 'PHASE-01..08' not in t; print('ok')"
```

Expected output: `ok`.

Commit:

```
git add ARCHITECTURE.md
git commit -m "docs(lawbrain): record /zwiad-sync-lawbrain + lawbrain modules in ARCHITECTURE"
```

---

- [ ] **Step 5: Mark PHASE-09 shipped in docs/PLAN.md.**

The PHASE-09 bullet currently ends `*Unimplemented.*`. Flip it to a shipped note in the same style as the PHASE-07/PHASE-08 bullets (which read `*Shipped as `/zwiad-…` …*`).

Edit — old string:

```
- **PHASE-09 — Law-brain COMMENTARY.** `sources/lawbrain.py`, `pipeline/lawbrain_keys.py`, `lawbrain_match.py` (deterministic shared-key confirm, D16), `lawbrain_copy.py`, `lawbrain_registry.py`; `CommentarySource` model; `[lawbrain]` config with `discover=false`; review queue. The match+copy stage and any LLM fallback wire into a slash command, not `run.py` (D27). **Attaches commentary to pages we already track; does NOT mint stubs.** *Unimplemented.*
```

New string:

```
- **PHASE-09 — Law-brain COMMENTARY.** `sources/lawbrain.py`, `pipeline/lawbrain_keys.py`, `lawbrain_match.py` (deterministic shared-key confirm, D16), `lawbrain_copy.py`, `lawbrain_links.py`, `lawbrain_registry.py`, `lawbrain_review.py`; `CommentarySource`/`CommentaryLink` models; `[lawbrain]` config with `discover=false`; `links.yaml` registry + `review-queue.md`. The match+copy stage and the keyless-page LLM fallback wire into a slash command, not `run.py` (D27, D57). **Attaches commentary to pages we already track; does NOT mint stubs.** *Shipped as `/zwiad-sync-lawbrain` (deterministic key-match + `lawbrain-matcher` subagent for keyless pages + grounded confirm; verbatim syntax-neutralized body copy D58; cross-type attach on shared key D59; slug-marker pages fail closed D60; review folded into render D61; `## Further Reading` link harvest D62; `lawbrain:region` text preservation D63) + CLI `fetch-lawbrain-candidates` / `render-lawbrain-commentary`.*
```

Verify the flip (no `Unimplemented` left on the PHASE-09 line, the shipped marker present):

```
uv run python -c "import re; t=open(r'docs/PLAN.md',encoding='utf-8').read(); l=[x for x in t.splitlines() if x.startswith('- **PHASE-09')][0]; assert 'Shipped as `/zwiad-sync-lawbrain`' in l and 'Unimplemented' not in l; print('ok')"
```

Expected output: `ok`.

Commit:

```
git add docs/PLAN.md
git commit -m "docs(lawbrain): mark PHASE-09 shipped in PLAN"
```

---

- [ ] **Step 6: Bump the version to 0.9.0.**

Two synchronized edits per the project's versioning rule (phase boundary = minor increment): `pyproject.toml` and `src/zwiadbrain/__init__.py`.

Edit `C:\Users\rafst\documents\projectas\zwiadbrain\pyproject.toml` — old string:

```
version = "0.8.0"
```

New string:

```
version = "0.9.0"
```

Edit `C:\Users\rafst\documents\projectas\zwiadbrain\src\zwiadbrain\__init__.py` — old string:

```
__version__ = "0.8.0"
```

New string:

```
__version__ = "0.9.0"
```

Verify both report 0.9.0 and that they agree:

```
uv run python -c "import tomllib, zwiadbrain; v=tomllib.load(open('pyproject.toml','rb'))['project']['version']; assert v=='0.9.0' and zwiadbrain.__version__=='0.9.0', (v, zwiadbrain.__version__); print('ok', v)"
```

Expected output: `ok 0.9.0`.

Run the full suite once to confirm the version bump and doc edits did not break anything (artifacts only, so it should stay green):

```
uv run ruff check src tests
uv run pyright
uv run pytest -q
```

Expected: ruff clean, pyright 0 errors, pytest all green (no new failures vs. the pre-task baseline).

Commit and tag the phase boundary:

```
git add pyproject.toml src/zwiadbrain/__init__.py
git commit -m "chore(release): bump version to 0.9.0 for PHASE-09"
git tag -a v0.9.0 -m "Phase 9 complete: read-only law-brain commentary overlay (key-match + grounded LLM fallback, Further Reading harvest, region preservation)"
```

(Leave the tag local; the user pushes tags themselves per the no-auto-push rule.)
