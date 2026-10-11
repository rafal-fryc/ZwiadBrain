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
from typing import Any

from zwiadbrain.tls import use_system_trust_store

# Below this many characters a no-OCR pass found no usable text layer (a scanned PDF).
_MIN_TEXT_CHARS = 200
# Text-layer pages are cheap (no OCR: 60 pp of UT HB 450 in 85 s); long bills put their core
# past page 12 (MN HF 4757's privacy chapter, VT S.71). ``max_pages`` still caps the OCR fallback.
_TEXT_LAYER_PAGES = 60


# Any: Docling is an optional, untyped extra absent from the type-check environment.
def _make_converter(ocr: bool) -> Any:
    # lazy: heavy ML import
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = ocr
    # Table-structure recognition took ~4x the whole conversion on line-numbered bill PDFs
    # (270s vs 58s, UT HB 450) and bill text needs words, not cell geometry (D119).
    options.do_table_structure = False
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def _convert(source: str, max_pages: int) -> str:
    """Convert a document's text layer, using OCR (on ``max_pages`` pages) only as a fallback.

    ``page_range`` (not ``max_num_pages``, which REJECTS longer documents outright — D119)
    bounds both passes; the small OCR cap keeps a long scan's tail away from RapidOCR, the
    std::bad_alloc trigger. Most legislative PDFs carry a text layer, so OCR (minutes per
    document) runs only when the text pass finds under ``_MIN_TEXT_CHARS``.
    """
    text_pages = (1, max(_TEXT_LAYER_PAGES, max_pages))
    text_pass = _make_converter(False).convert(source, page_range=text_pages)
    markdown: str = text_pass.document.export_to_markdown()
    if len(markdown.strip()) >= _MIN_TEXT_CHARS:
        return markdown
    ocr_markdown: str = (
        _make_converter(True)
        .convert(source, page_range=(1, max_pages))
        .document.export_to_markdown()
    )
    return ocr_markdown


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
    use_system_trust_store()  # D120: Docling fetches URLs itself via requests
    markdown = _convert(source, max_pages)
    Path(out_path).write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
