# Extracting full document text (Docling)

Pages store an LLM summary plus **links** to the official text. The `extract-text` verb
additionally pulls the **full source text** into a sidecar file so it is available locally for
reference and search. The existing "Full Text" links are never touched.

## What it does

For each tracked item in a `classified.json` (a list of `Bill` / `EnforcementAction` dumps):

- **Bills** — picks the operative text version (enrolled/enacted, else latest) and extracts it.
- **Enforcement** — extracts the press-release page plus any linked complaint/order/settlement
  PDFs.

Each item's extraction is written to a `<id>.text.md` sibling of its page (e.g.
`wiki/states/ca/bills/ca-2025-sb-53.text.md`) and linked from the page via a preserved
`<!-- extracted-text:region -->` block. Docling fetches each document to a temp file, converts
it to Markdown, and the downloaded PDF is discarded — only the extraction is kept.

## Docling is an optional, operator-installed extra (D68)

Docling pins `typer<0.22` (which breaks `pyright --strict`) and pulls PyTorch + ML models, so it
is **not** a locked dependency. Install it only where you run extraction:

```
uv pip install docling          # heavy: PyTorch + layout models (downloaded on first run)
uv run --no-sync zwiadbrain extract-text --in data/runs/<id>/classified.json
```

`--no-sync` stops `uv run` from re-syncing the lockfile and removing docling. Without docling
installed, a real run fails fast with this hint; `--dry-run` still works (it never invokes
Docling) and lists the documents that would be extracted.

```
# preview without Docling installed
uv run zwiadbrain extract-text --in data/runs/<id>/classified.json --dry-run
# cap how many items to process
uv run --no-sync zwiadbrain extract-text --in data/runs/<id>/classified.json --limit 10
```

The verb is deterministic, idempotent (re-running rewrites the sidecar + re-applies the page
region), and processes items independently — a malformed or unfetchable item is reported as a
skip, never fatal.

## Caveats

- **Source terms:** federal bill text and FTC documents are public-domain U.S. government works;
  **LegiScan-sourced state-bill text** may be restricted from storage/redistribution by
  LegiScan's API license — store it at your discretion (verify the license or keep the repo
  private). See D67.
- **Scanned PDFs** need OCR (`uv pip install "docling[easyocr]"`) for usable output.
- Not wired into `/zwiad-run` yet — run it as an explicit step after a render.
