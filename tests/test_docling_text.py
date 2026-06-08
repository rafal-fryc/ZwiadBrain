"""The Docling boundary (PHASE-12).

``extract_markdown`` is a thin wrapper over Docling's ``DocumentConverter`` that
lazy-imports the heavy ML stack only when called. The unit test injects a fake
``docling.document_converter`` module so the suite never imports torch/Docling.
"""

import sys
import types
from pathlib import Path

import pytest

from zwiadbrain.pipeline import docling_text


class _FakeDoc:
    def __init__(self, markdown: str) -> None:
        self._markdown = markdown

    def export_to_markdown(self) -> str:
        return self._markdown


class _FakeResult:
    def __init__(self, markdown: str) -> None:
        self.document = _FakeDoc(markdown)


class _FakeConverter:
    """Records the sources it is asked to convert and returns canned Markdown."""

    calls: list[object] = []
    instances: int = 0  # how many times the converter has been CONSTRUCTED

    def __init__(self) -> None:
        _FakeConverter.instances += 1

    def convert(self, source: object) -> _FakeResult:
        _FakeConverter.calls.append(source)
        return _FakeResult("# Title\n\nBody text.")


def _install_fake_docling(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeConverter.calls = []
    _FakeConverter.instances = 0
    # Reset the run-scoped converter cache so a prior test's fake converter is not reused.
    monkeypatch.setattr(docling_text, "_converter", None, raising=False)
    fake_module = types.ModuleType("docling.document_converter")
    fake_module.DocumentConverter = _FakeConverter  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "docling.document_converter", fake_module)


def test_extract_markdown_converts_source_and_returns_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_docling(monkeypatch)

    result = docling_text.extract_markdown("https://example.gov/bill.pdf")

    assert result == "# Title\n\nBody text."
    assert _FakeConverter.calls == ["https://example.gov/bill.pdf"]


def test_extract_markdown_accepts_local_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_docling(monkeypatch)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    assert docling_text.extract_markdown(pdf) == "# Title\n\nBody text."
    assert _FakeConverter.calls == [pdf]


def test_extract_markdown_reuses_one_converter_across_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """should build the heavy DocumentConverter once and reuse it for every pdf in a run"""
    _install_fake_docling(monkeypatch)

    docling_text.extract_markdown("https://example.gov/a.pdf")
    docling_text.extract_markdown("https://example.gov/b.pdf")

    assert _FakeConverter.instances == 1  # constructed once, reused
    assert _FakeConverter.calls == ["https://example.gov/a.pdf", "https://example.gov/b.pdf"]
