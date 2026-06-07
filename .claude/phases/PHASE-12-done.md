# Phase 12 — Document Text Extraction (Docling)
Status: DONE

## Goal
Add a dedicated, deterministic `extract-text` step that downloads each tracked item's operative
source document, extracts Markdown via Docling, saves it as a sibling `<slug>.text.md`, links it
from the page, and discards the downloaded PDF — without altering the existing "Full Text" links.

## Tasks
- [x] Docling boundary `pipeline/docling_text.py` (lazy import, `docling_available`) + test
      — NOTE: docling is operator-installed, NOT a locked dep (D68; see deviation below)
- [x] `select_bill_document` operative-version selection (`pipeline/extract.py`) + test
- [x] `discover_enforcement_pdfs` from press-release HTML (`pipeline/extract.py`) + test
- [x] `sidecar_path` + `write_extracted_text_region` (mirror lawbrain region in `pipeline/render.py`) + test
- [x] `extract-text` CLI verb consuming staged `classified.json` + test (+ fail-fast when docling absent)
- [x] Quality gate: 645 pytest pass, pyright strict 0 errors, ruff clean
- [x] Real Docling smoke passed — real Docling converted HTML→Markdown via the boundary
- [x] Log decisions in DECISIONS.md (D67, D68); PR #9 opened

## Acceptance Criteria
- Existing text-version link section on pages is unchanged.
- `extract-text --in <classified.json>` writes `<slug>.text.md` sidecars and an Extracted Text link
  region on each page; re-running is idempotent (byte-identical sidecar + region).
- Operative bill version (enrolled/enacted else latest) extracted; for enforcement, the press
  release and its linked complaint/order/settlement PDFs extracted; downloaded PDFs not persisted.
- `--dry-run` invokes no Docling and writes nothing; `--limit` honored.
- `uv run pytest` green; `uv run pyright` strict clean (only documented ignore in `docling_text.py`);
  `uv run ruff check` clean.
- Unit tests mock the Docling boundary — no torch/model load in the suite.

## Decisions Made This Phase
- **D67** — full text extracted via Docling into sidecar `<id>.text.md` files, linked from the
  page by a preserved `extracted-text:region`; downloaded PDFs discarded; existing links kept.
- **D68** — docling is an optional, operator-installed dependency (NOT locked). The verb +
  boundary lazy-import it and fail fast with an install hint; tests mock the boundary so the
  suite/pyright/CI run docling-free.

### Deviation from the approved plan (surfaced, not silent)
The plan said `uv add docling` (locked dependency). During build, docling was found to hard-pin
`typer>=0.12.5,<0.22`, which forced typer 0.26.1 → 0.21.2; typer 0.21.2's incomplete stubs broke
`pyright --strict` across the **entire pre-existing CLI** (58 errors, none in new code). Raised to
the user with three options; user chose **docling operator-installed (unlocked)**. Net effect:
`pyproject.toml` is byte-identical to main; `uv.lock` carries only an incidental typer
0.26.1 → 0.26.4 patch bump; the single documented pyright suppression lives in `docling_text.py`.
