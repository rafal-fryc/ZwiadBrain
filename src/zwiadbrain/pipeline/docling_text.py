"""Thin, typed boundary over Docling's document-to-Markdown conversion (PHASE-12).

Docling pulls in PyTorch and downloads layout models on first use, so the import
is deferred to call time: importing this module (and the rest of the CLI) stays
cheap, and the heavy stack loads only when an extraction actually runs. This is
also the single seam the test suite patches, so unit tests never touch torch.
"""

# Docling is an optional, unlocked extra (DECISIONS: it pins typer<0.22 and pulls
# PyTorch, so it is deliberately NOT a locked dependency). It is therefore absent from
# the type-check / CI environment, where pyright cannot resolve its types. This module
# is the single, intentional boundary where that is tolerated; the rest of the codebase
# stays pyright-strict-clean.
# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any  # Docling's DocumentConverter is untyped (optional, unlocked) — see pragma

from zwiadbrain.exceptions import ExtractionError

_INSTALL_HINT = (
    "Docling is not installed. It is an optional, heavyweight extra (pulls PyTorch) "
    "and is intentionally not a locked dependency. Install it to run extract-text:\n"
    "  uv pip install docling\n"
    "then re-run with `uv run --no-sync zwiadbrain extract-text ...`."
)


def docling_available() -> bool:
    """True when the Docling converter can be imported in this environment."""
    return importlib.util.find_spec("docling.document_converter") is not None


# Cached DocumentConverter. A converter holds no per-document state, so one instance is
# safely reused across every PDF in a run (and the process) — avoiding a fresh heavyweight
# construction (and model load) per PDF (PHASE-20/D79). Reset in unit tests via the fake-
# docling installer; the CLI is a fresh process per render, so this is effectively run-scoped.
_converter: Any = None


def _get_converter() -> Any:
    """Return the cached Docling ``DocumentConverter``, constructing it on first use.

    Raises :class:`ExtractionError` with an install hint when Docling is absent.
    """
    global _converter
    if _converter is None:
        try:
            from docling.document_converter import DocumentConverter  # lazy: heavy ML import
        except ImportError as exc:
            raise ExtractionError(_INSTALL_HINT) from exc
        _converter = DocumentConverter()
    return _converter


def extract_markdown(source: str | Path) -> str:
    """Convert a document (PDF/HTML/... by URL or local path) to Markdown text.

    Docling fetches a URL to a temporary file itself and parses it, so the caller
    keeps only the returned Markdown — no source PDF is persisted. Reuses one cached
    converter (see :func:`_get_converter`). Raises :class:`ExtractionError` with an
    install hint when Docling is absent.
    """
    converter = _get_converter()
    result = converter.convert(source)
    markdown: str = result.document.export_to_markdown()
    return markdown
