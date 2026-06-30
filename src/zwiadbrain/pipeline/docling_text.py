"""Crash-safe, typed boundary over Docling's document-to-Markdown conversion.

Docling pulls in PyTorch and downloads layout models on first use, so the actual
conversion is deferred to an out-of-process worker (:mod:`zwiadbrain.pipeline.docling_worker`):
importing this module (and the rest of the CLI) stays cheap, and the heavy stack loads only
in the child when an extraction actually runs.

Running the conversion in a subprocess is also what makes the grounding gate's "never crash
a render" guarantee real (D81): Docling's RapidOCR/torch stack can abort with a native
``std::bad_alloc`` on long scanned PDFs, and a native abort cannot be caught by a Python
``except``. Isolating it means such a crash takes down only the child (non-zero exit), which
:func:`extract_markdown` reports as ``""`` so the caller fail-closes — exactly as it would for
an unfetchable page. The worker additionally caps OCR pages so the crash is rarely reached.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

# Page cap handed to the worker's ``DocumentConverter.convert(..., max_num_pages=...)``.
# Legislative quote text (signing statements are 1-2 pp) and Tier-2 media identity (page 1)
# are front-loaded, so this bounds OCR well clear of the memory-exhausting tail pages that
# trigger std::bad_alloc on long scanned PDFs, at effectively no recall cost.
_MAX_OCR_PAGES = 12

# Hard wall-clock bound on a single conversion. CPU OCR of a dozen pages is slow but finite;
# a hang past this yields ``""`` (fail-closed) rather than stalling the whole pipeline.
_CONVERT_TIMEOUT_S = 300.0


def docling_available() -> bool:
    """True when the Docling converter can be imported in this environment."""
    return importlib.util.find_spec("docling.document_converter") is not None


def extract_markdown(source: str | Path, *, max_pages: int = _MAX_OCR_PAGES) -> str:
    """Convert a document (PDF/HTML/... by URL or local path) to Markdown text.

    The heavy conversion runs in an isolated subprocess (:mod:`docling_worker`) that writes
    its Markdown to a temp file and caps OCR at ``max_pages`` pages. Returns the extracted
    Markdown on success and ``""`` on ANY failure — a non-zero exit, a native crash
    (``std::bad_alloc`` / segfault on a pathological scanned PDF), a timeout, or Docling
    being absent — so the caller can fail-closed exactly as it does for an unfetchable page.
    Never raises.
    """
    if not docling_available():
        return ""
    out_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as fh:
            out_path = Path(fh.name)
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "zwiadbrain.pipeline.docling_worker",
                str(source),
                str(max_pages),
                str(out_path),
            ],
            capture_output=True,
            timeout=_CONVERT_TIMEOUT_S,
            check=False,
        )
        if proc.returncode != 0:
            return ""
        return out_path.read_text(encoding="utf-8")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        # OSError: spawn failure / unreadable output. TimeoutExpired: OCR hang.
        # All are treated as an extraction miss -> caller fail-closes.
        return ""
    finally:
        if out_path is not None:
            out_path.unlink(missing_ok=True)
