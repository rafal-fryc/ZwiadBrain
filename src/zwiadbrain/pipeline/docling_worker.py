"""Out-of-process Docling conversion worker (PHASE-21 / D81).

Run as ``python -m zwiadbrain.pipeline.docling_worker <source> <max_pages> <out_path>``.
It performs the heavyweight Docling conversion in an ISOLATED process and writes the
resulting Markdown to ``<out_path>`` (utf-8), exiting 0 on success.

Why a separate process: Docling's RapidOCR/torch stack can exhaust memory on long
scanned PDFs and abort with a native ``std::bad_alloc`` — an abort that a Python
``except`` cannot catch, so it would otherwise kill the whole render/build. Running the
conversion here means such a native crash takes down only this child (non-zero exit);
the parent driver (:func:`zwiadbrain.pipeline.docling_text.extract_markdown`) observes
the failure and fail-closes to ``""``. The page cap (``max_num_pages``) keeps OCR from
reaching the memory-exhausting tail pages in the first place; the isolation contains
whatever still slips past.

Markdown is written to a file rather than stdout because torch/RapidOCR emit progress
bars and INFO logs to the standard streams, which would otherwise contaminate the output.
"""

# Docling is an optional, unlocked extra that pulls PyTorch and is absent from the
# type-check / CI environment — see docling_text.py for the rationale behind this pragma.
# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false
from __future__ import annotations

import sys
from pathlib import Path


def _convert(source: str, max_pages: int) -> str:
    from docling.document_converter import DocumentConverter  # lazy: heavy ML import

    converter = DocumentConverter()
    # ``max_num_pages`` bounds OCR so a long scanned PDF never feeds its image-heavy tail
    # pages to RapidOCR (the std::bad_alloc trigger). Legislative quote text and Tier-2
    # media identity are front-loaded, so the cap costs effectively no recall in practice.
    result = converter.convert(source, max_num_pages=max_pages)
    markdown: str = result.document.export_to_markdown()
    return markdown


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: docling_worker <source> <max_pages> <out_path>", file=sys.stderr)
        return 2
    source, max_pages_raw, out_path = argv
    try:
        max_pages = int(max_pages_raw)
    except ValueError:
        print(f"invalid max_pages: {max_pages_raw!r}", file=sys.stderr)
        return 2
    markdown = _convert(source, max_pages)
    Path(out_path).write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
