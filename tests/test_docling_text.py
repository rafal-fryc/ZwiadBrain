"""The crash-safe Docling boundary (PHASE-12 / D81).

``extract_markdown`` drives an isolated subprocess worker so a native Docling/OCR crash
(``std::bad_alloc`` on a long scanned PDF) takes down only the child and is reported as
``""`` rather than killing the render. These tests fake ``subprocess.run`` so the suite
never spawns a process or imports torch/Docling; the worker's own conversion logic is
exercised separately with a fake ``DocumentConverter``.
"""

import subprocess
from pathlib import Path

import pytest

from zwiadbrain.pipeline import docling_text, docling_worker


def _force_available(monkeypatch: pytest.MonkeyPatch, available: bool = True) -> None:
    monkeypatch.setattr(docling_text, "docling_available", lambda: available)


def _fake_run_writing(markdown: str, returncode: int = 0):
    """Return a fake ``subprocess.run`` that writes *markdown* to the worker's out_path."""

    def _run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        # argv layout: [exe, -m, module, source, max_pages, out_path]
        out_path = Path(cmd[-1])
        if returncode == 0:
            out_path.write_text(markdown, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, returncode, b"", b"")

    return _run


def test_extract_markdown_returns_worker_output_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """should return the markdown the worker wrote when the subprocess exits 0"""
    _force_available(monkeypatch)
    monkeypatch.setattr(subprocess, "run", _fake_run_writing("# Title\n\nBody text."))

    assert docling_text.extract_markdown("https://example.gov/bill.pdf") == "# Title\n\nBody text."


def test_extract_markdown_passes_page_cap_to_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """should hand the OCR page cap to the worker as an argv parameter"""
    _force_available(monkeypatch)
    seen: dict[str, list[str]] = {}

    def _run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        seen["cmd"] = cmd
        Path(cmd[-1]).write_text("ok", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", _run)

    docling_text.extract_markdown("doc.pdf", max_pages=7)

    assert "7" in seen["cmd"]
    assert seen["cmd"][2] == "zwiadbrain.pipeline.docling_worker"


def test_extract_markdown_fail_closes_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """should return '' when the worker subprocess crashes / exits non-zero (bad_alloc)"""
    _force_available(monkeypatch)
    monkeypatch.setattr(subprocess, "run", _fake_run_writing("unused", returncode=1))

    assert docling_text.extract_markdown("scanned.pdf") == ""


def test_extract_markdown_fail_closes_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """should return '' when the conversion subprocess times out"""
    _force_available(monkeypatch)

    def _run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(cmd, 1.0)

    monkeypatch.setattr(subprocess, "run", _run)

    assert docling_text.extract_markdown("huge.pdf") == ""


def test_extract_markdown_returns_empty_when_docling_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """should not spawn a subprocess when Docling is not installed"""
    _force_available(monkeypatch, available=False)

    def _boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("subprocess.run must not be called when Docling is absent")

    monkeypatch.setattr(subprocess, "run", _boom)

    assert docling_text.extract_markdown("doc.pdf") == ""


# --- worker conversion logic (in-process, fake DocumentConverter) ---


class _FakeDoc:
    def __init__(self, markdown: str) -> None:
        self._markdown = markdown

    def export_to_markdown(self) -> str:
        return self._markdown


class _FakeResult:
    def __init__(self, markdown: str) -> None:
        self.document = _FakeDoc(markdown)


class _FakeConverter:
    def __init__(self, ocr: bool, outputs: dict[bool, str], calls: list[object]) -> None:
        self._ocr, self._outputs, self._calls = ocr, outputs, calls

    def convert(self, source: object, *, page_range: tuple[int, int]) -> _FakeResult:
        self._calls.append((source, self._ocr, page_range))
        return _FakeResult(self._outputs[self._ocr])


def _install_fake_converters(
    monkeypatch: pytest.MonkeyPatch, outputs: dict[bool, str]
) -> list[object]:
    calls: list[object] = []

    def make(ocr: bool) -> _FakeConverter:
        return _FakeConverter(ocr, outputs, calls)

    monkeypatch.setattr(docling_worker, "_make_converter", make)
    return calls


_TEXT = "Section 1. A controller may not sell personal data. " * 10


def test_worker_should_read_text_layer_pdfs_without_ocr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """a text-layer PDF is read up to 60 pages, never rejected (D119)"""
    calls = _install_fake_converters(monkeypatch, {False: _TEXT, True: "unused"})
    out = tmp_path / "out.md"

    rc = docling_worker.main(["https://example.gov/a.pdf", "9", str(out)])

    assert rc == 0
    assert out.read_text(encoding="utf-8") == _TEXT
    assert calls == [("https://example.gov/a.pdf", False, (1, 60))]


def test_worker_should_fall_back_to_ocr_when_text_layer_is_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """a scanned PDF (no text layer) is retried with OCR, capped at max_pages"""
    calls = _install_fake_converters(monkeypatch, {False: "<!-- image -->", True: _TEXT})
    out = tmp_path / "out.md"

    rc = docling_worker.main(["scan.pdf", "12", str(out)])

    assert rc == 0
    assert out.read_text(encoding="utf-8") == _TEXT
    assert calls == [("scan.pdf", False, (1, 60)), ("scan.pdf", True, (1, 12))]


def test_worker_rejects_bad_arguments(tmp_path: Path) -> None:
    """should exit non-zero on a malformed argv rather than convert"""
    assert docling_worker.main(["only-one-arg"]) == 2
    assert docling_worker.main(["src", "notanint", str(tmp_path / "o.md")]) == 2
