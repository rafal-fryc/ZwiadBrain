"""Classifier input staging (PHASE-30, D118).

The classifier judges scope from title + summary only. Two input shapes defeated it in
past sweeps: a *thin* summary that just repeats the title (the classifier had nothing to
judge), and an *oversized* summary (omnibus CRS summaries past the context budget). These
tests pin how each is repaired with seed-hit snippets before batching.
"""

import datetime as dt
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zwiadbrain.cli import app
from zwiadbrain.models import Bill, TextVersion
from zwiadbrain.pipeline.classifier_input import (
    batch_items,
    classifier_item,
    is_thin_summary,
    seed_snippets,
)

_SEEDS = ["artificial intelligence", "personal data"]


def _bill(summary: str | None, *, title: str = "Data Privacy Amendments") -> Bill:
    return Bill(
        id="ut-2026-hb-450",
        jurisdiction="US-UT",
        bill_number="HB 450",
        title=title,
        summary=summary,
        text_versions=[
            TextVersion(code="Enrolled", date=dt.date(2026, 3, 1), url="https://x/enr.htm"),
        ],
    )


def _no_fetch(url: str) -> str:
    raise AssertionError(f"should not fetch text, fetched {url}")


def test_should_treat_summary_as_thin_when_it_repeats_the_title() -> None:
    assert is_thin_summary("Data Privacy Amendments", "Data Privacy Amendments.")


def test_should_treat_summary_as_thin_when_it_is_missing() -> None:
    assert is_thin_summary("Data Privacy Amendments", None)


def test_should_treat_a_short_paraphrase_of_the_title_as_thin() -> None:
    assert is_thin_summary(
        "Crimes: distribution of intimate images.",
        "An act to amend Section 647 of the Penal Code, relating to crimes.",
    )


def test_should_not_treat_a_substantive_summary_as_thin() -> None:
    summary = (
        "Requires controllers to honor opt-out requests for the sale of personal data and "
        "to conduct data protection assessments before processing sensitive data, with "
        "attorney general enforcement."
    )
    assert not is_thin_summary("Data Privacy Amendments", summary)


def test_should_return_context_around_each_seed_hit() -> None:
    text = "x " * 200 + "the controller shall not sell personal data without consent" + " y" * 200
    snippets = seed_snippets(text, _SEEDS, radius=40)
    assert len(snippets) == 1
    assert "personal data" in snippets[0]
    assert snippets[0].startswith("[personal data]")


def test_should_merge_overlapping_seed_windows_into_one_snippet() -> None:
    text = "artificial intelligence systems that process personal data"
    assert len(seed_snippets(text, _SEEDS, radius=40)) == 1


def test_should_cap_the_number_of_snippets() -> None:
    text = (" filler " * 50).join(["personal data"] * 30)
    assert len(seed_snippets(text, _SEEDS, radius=20, max_snippets=5)) == 5


def test_should_pass_a_substantive_summary_through_without_fetching() -> None:
    summary = (
        "Requires controllers to honor opt-out requests for the sale of personal data and "
        "to conduct data protection assessments before processing sensitive data, with "
        "attorney general enforcement."
    )
    item = classifier_item(_bill(summary), _SEEDS, _no_fetch)
    assert item == {"id": "ut-2026-hb-450", "title": "Data Privacy Amendments", "summary": summary}


def test_should_attach_enacted_text_snippets_when_summary_is_thin() -> None:
    fetched: list[str] = []

    def fetch(url: str) -> str:
        fetched.append(url)
        return "Section 1. A controller may not process personal data of a known child."

    item = classifier_item(_bill("Data Privacy Amendments"), _SEEDS, fetch)
    assert fetched == ["https://x/enr.htm"]
    assert any("personal data" in s for s in item["text_snippets"])
    assert "Enrolled" in item["input_note"]


def test_should_attach_the_opening_text_when_thin_bill_has_no_seed_hits() -> None:
    item = classifier_item(
        _bill("Data Privacy Amendments"), _SEEDS, lambda url: "Section 1. Mining claims."
    )
    assert item["text_snippets"] == ["[opening] Section 1. Mining claims."]


def test_should_flag_review_when_thin_summary_has_no_fetchable_text() -> None:
    item = classifier_item(_bill("Data Privacy Amendments"), _SEEDS, lambda url: "")
    assert "text_snippets" not in item
    assert str(item["input_note"]).startswith("THIN-SUMMARY")


def test_should_replace_an_oversized_summary_with_head_and_snippets() -> None:
    summary = "Division A funds agencies. " * 2000 + "a data broker may not sell personal data."
    item = classifier_item(
        _bill(summary, title="Consolidated Appropriations Act"), _SEEDS, _no_fetch,
        oversized_chars=5000,
    )
    assert len(item["summary"]) <= 5000
    assert any("personal data" in s for s in item["summary_snippets"])
    assert "oversized" in item["input_note"]


def test_should_split_items_into_batches_of_the_given_size() -> None:
    items: list[dict[str, str | list[str]]] = [{"id": str(n)} for n in range(32)]
    assert [len(b) for b in batch_items(items, 15)] == [15, 15, 2]


def test_should_stage_batch_files_from_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stage-classifier-batches writes batchNN.json files and repairs thin summaries"""
    def fake_extract(url: str, *, max_pages: int = 12) -> str:
        return "A controller may not sell personal data of a child."

    monkeypatch.setattr("zwiadbrain.cli.extract_markdown", fake_extract)
    thin = _bill("Data Privacy Amendments")
    full = _bill(
        "Requires data brokers to register with the attorney general, honor consumer deletion "
        "requests within 45 days, and pay civil penalties for each unregistered day.",
        title="X",
    )
    full = full.model_copy(update={"id": "ut-2026-hb-1"})
    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        json.dumps([b.model_dump(mode="json") for b in (thin, full, full, full)]),
        encoding="utf-8",
    )
    out = tmp_path / "batch"
    result = CliRunner().invoke(
        app,
        ["stage-classifier-batches", "--in", str(candidates), "--out-dir", str(out),
         "--size", "3"],
    )
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in out.iterdir()) == ["batch01.json", "batch02.json"]
    first = json.loads((out / "batch01.json").read_text(encoding="utf-8"))
    assert "text_snippets" in first[0]
    assert "1 thin" in result.output
