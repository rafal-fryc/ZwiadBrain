"""CLI tests for both halves of /zwiad-sync-lawbrain.

The fetch half (``fetch-lawbrain-candidates``) is exercised first; the render
half (``render-lawbrain-commentary``) follows. Both are fully offline: the law
brain is the committed mini-wiki under tests/fixtures/lawbrain/, targets are
rendered to a tmp wiki, and classified.json is hand-built to stand in for the
(subagent/operator) fetch+match output. No network, no LLM.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zwiadbrain.cli import _summary_excerpt, app  # pyright: ignore[reportPrivateUsage]
from zwiadbrain.config import LawBrainSettings, Settings
from zwiadbrain.models import Bill
from zwiadbrain.pipeline.render import write_page
from zwiadbrain.wiki.schema import from_page

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
                "sources: {}",
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


def _write_enforcement(wiki: Path, *, id_: str, public_law: str = "Pub. L. 119-12") -> None:
    """Render a tracked enforcement page citing a public law (the cross-type key)."""
    page = wiki / "enforcement" / f"{id_}.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "\n".join(
            [
                "---",
                f"id: {id_}",
                "type: enforcement",
                "jurisdiction: US",
                f"title: United States v. {id_}",
                "agency: FTC",
                "statutes:",
                f"  - {public_law}",
                "sources: {}",
                "commentary_sources: []",
                "---",
                "",
                "## Background",
                "",
                "Fixture enforcement action.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_take_it_down_lawbrain_page(law_brain: Path) -> None:
    """A single-subject law-brain page whose citation yields the public-law key."""
    page = law_brain / "wiki" / "regulation-take-it-down-act.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "\n".join(
            [
                "---",
                'title: "TAKE IT DOWN Act"',
                "type: regulation",
                "jurisdiction: US",
                "tags:",
                "  - ncii",
                "citation: \"Pub. L. 119-12\"",
                "status: active",
                "---",
                "",
                "## Summary",
                "",
                "Federal NCII statute enacted as Pub. L. 119-12.",
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
    result = _RUNNER.invoke(app, ["fetch-lawbrain-candidates", "--out", str(out)])

    # Assert — exit 0, a no-op message, and no candidates file written.
    assert result.exit_code == 0, result.output
    assert "law brain unavailable" in result.output
    assert not (out / "lawbrain-candidates.json").exists()


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
    assert {"id": "ca-2025-sb-53", "kind": "bill"}.items() <= {
        "id": targets[0]["id"],
        "kind": targets[0]["kind"],
    }.items()


def test_fetch_lawbrain_candidates_keyless_single_subject_gets_shortlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a single-subject law-brain page with no extractable key, plus a
    # same-jurisdiction tracked target the matcher could consider.
    law_brain = tmp_path / "law"
    (law_brain / "wiki").mkdir(parents=True)
    (law_brain / "wiki" / "concept-ai-liability-doctrine.md").write_text(
        "\n".join(
            [
                "---",
                'title: "AI Liability Doctrine"',
                "type: concept",
                "jurisdiction: US-CA",
                "tags:",
                "  - liability",
                "  - frontier-ai",
                "status: active",
                "---",
                "",
                "## Summary",
                "",
                "A single-subject doctrinal note with no bill, docket, or public-law key.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    wiki = tmp_path / "wiki"
    _write_sb53_bill(wiki)
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: _settings(law_brain))
    out = tmp_path / "run"

    # Act
    result = _RUNNER.invoke(
        app, ["fetch-lawbrain-candidates", "--wiki", str(wiki), "--out", str(out)]
    )

    # Assert — keyless single-subject page gets a shortlist for the LLM matcher.
    assert result.exit_code == 0, result.output
    candidates = json.loads(
        (out / "lawbrain-candidates.json").read_text(encoding="utf-8")
    )
    by_slug = {c["slug"]: c for c in candidates}
    entry = by_slug["concept-ai-liability-doctrine"]
    assert entry["match"] == "keyless"
    assert entry["target_id"] is None
    assert entry["keys"] == []
    # The same-jurisdiction (US-CA) SB 53 target appears in the shortlist.
    assert entry["shortlist"] == ["ca-2025-sb-53"]


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

    effective_path = settings.effective_law_brain_path
    assert effective_path is not None
    reader = LawBrainReader(effective_path)
    sb53_page = next(
        p for p in reader.pages() if p.slug == "regulation-california-sb53-tfaia"
    )
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


def test_fetch_lawbrain_candidates_collision_when_two_targets_share_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — two tracked enforcement actions citing the same public law, and a
    # law-brain page whose citation yields that shared key -> a key collision.
    law_brain = tmp_path / "law"
    (law_brain / "wiki").mkdir(parents=True)
    _write_take_it_down_lawbrain_page(law_brain)
    wiki = tmp_path / "wiki"
    _write_enforcement(wiki, id_="ftc-acme")
    _write_enforcement(wiki, id_="ftc-beta")
    monkeypatch.setattr("zwiadbrain.cli.load_settings", lambda: _settings(law_brain))
    out = tmp_path / "run"

    # Act
    result = _RUNNER.invoke(
        app, ["fetch-lawbrain-candidates", "--wiki", str(wiki), "--out", str(out)]
    )

    # Assert — the page collides on the shared key; both targets listed, no auto-link.
    assert result.exit_code == 0, result.output
    candidates = json.loads(
        (out / "lawbrain-candidates.json").read_text(encoding="utf-8")
    )
    by_slug = {c["slug"]: c for c in candidates}
    entry = by_slug["regulation-take-it-down-act"]
    assert entry["match"] == "collision"
    assert entry["target_id"] is None
    assert entry["shortlist"] == ["ftc-acme", "ftc-beta"]
    assert "public_law::119-12" in entry["keys"]


def test_fetch_lawbrain_candidates_no_op_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — an available law brain on disk, but lawbrain.enabled is False.
    law_brain = tmp_path / "law"
    shutil.copytree(_FIXTURE_LAWBRAIN, law_brain)
    monkeypatch.setattr(
        "zwiadbrain.cli.load_settings", lambda: _settings(law_brain, enabled=False)
    )
    out = tmp_path / "run"

    # Act
    result = _RUNNER.invoke(app, ["fetch-lawbrain-candidates", "--out", str(out)])

    # Assert — exit 0, no-op message, no candidates file (disabled guard, not error).
    assert result.exit_code == 0, result.output
    assert "law brain unavailable" in result.output
    assert not (out / "lawbrain-candidates.json").exists()


def test_summary_excerpt_skips_headings_and_handles_empty() -> None:
    # All-headings body -> no paragraph -> "".
    assert _summary_excerpt("# Title\n\n## Summary\n\n### Detail") == ""
    # Empty body -> "".
    assert _summary_excerpt("") == ""
    # Normal body -> first non-heading paragraph, truncated to the limit.
    body = "## Summary\n\nThe first real paragraph of prose.\n\nA second one."
    assert _summary_excerpt(body) == "The first real paragraph of prose."
    # Truncation at the 280-char limit.
    long_para = "## Summary\n\n" + "x" * 400
    assert _summary_excerpt(long_para) == "x" * 280


# ---------------------------------------------------------------------------
# Render half: render-lawbrain-commentary
# ---------------------------------------------------------------------------
#
# These tests drive load_settings() via a real zwiadbrain.toml in a chdir'd
# tmp_path (the render command reads settings itself, not a monkeypatched one).
# The asserted Further Reading hosts match the committed SB-53 fixture: the page
# body carries a Mayer Brown link, and the referenced sb53-memo.md carries Morgan
# Lewis / IAPP / a bare Sidley URL plus two primary sources (leginfo, Wikipedia)
# that must be filtered out by the primary-source denylist.


def _write_render_settings(tmp_path: Path) -> None:
    """Enable the law brain (pointed at the offline fixture) via a real TOML."""
    toml = tmp_path / "zwiadbrain.toml"
    toml.write_text(
        "[lawbrain]\n"
        "enabled = true\n"
        f'path = "{_FIXTURE_LAWBRAIN.as_posix()}"\n'
        "min_confidence = 0.75\n"
        "require_shared_key = true\n"
        "demote_headings = true\n"
        "commentary = true\n"
        "further_reading = true\n",
        encoding="utf-8",
    )


def _seed_sb53_target(wiki: Path) -> None:
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


_SB53_PAGE = ("states", "ca", "bills", "ca-2025-sb-53.md")


def test_render_lawbrain_attaches_commentary_and_further_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(_classified_deterministic()), encoding="utf-8"
    )

    # Act
    result = _RUNNER.invoke(
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

    # Assert — command succeeded and reported one link.
    assert result.exit_code == 0, result.output
    assert "1 linked" in result.output

    page = (wiki / Path(*_SB53_PAGE)).read_text(encoding="utf-8")
    # Commentary region with the slug marker, demoted headings, neutralized wikilink.
    assert "## Commentary & Analysis" in page
    assert "<!-- lawbrain:region:begin -->" in page
    assert "<!-- lawbrain:begin slug=regulation-california-sb53-tfaia -->" in page
    assert "### Summary" in page  # source "## Summary" demoted to "###"
    assert "concept-california-ai-regulatory-landscape" in page  # [[...]] neutralized
    assert "[[concept-california-ai-regulatory-landscape]]" not in page
    # Further Reading harvested from page body + referenced memo, primary sources dropped.
    assert "## Further Reading (via law brain)" in page
    assert "morganlewis.com" in page  # from the memo (markdown link)
    assert "iapp.org" in page  # from the memo (markdown link)
    assert "sidley.com" in page  # from the memo (bare URL captured)
    assert "mayerbrown.com" in page  # from the page body itself
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
    # Arrange — first render.
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(_classified_deterministic()), encoding="utf-8"
    )
    page_path = wiki / Path(*_SB53_PAGE)
    first = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )
    assert first.exit_code == 0, first.output
    after_first = page_path.read_text(encoding="utf-8")
    links_after_first = (wiki / "links.yaml").read_text(encoding="utf-8")

    # Act — identical second render.
    second = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — byte-identical page AND registry (D20: idempotent, clean git status).
    assert second.exit_code == 0, second.output
    assert page_path.read_text(encoding="utf-8") == after_first
    assert (wiki / "links.yaml").read_text(encoding="utf-8") == links_after_first


def test_render_lawbrain_weak_grounding_routes_to_review_not_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — an LLM-proposed link with NO shared key: confirm_match fails the
    # require_shared_key gate, so it must land in review-queue.md, NOT links.yaml.
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
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
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — no commentary attached, a review entry written, no links.yaml decision.
    assert result.exit_code == 0, result.output
    assert "1 review" in result.output
    page = (wiki / Path(*_SB53_PAGE)).read_text(encoding="utf-8")
    assert "## Commentary & Analysis" not in page
    review = (wiki / "review-queue.md").read_text(encoding="utf-8")
    assert "regulation-california-sb53-tfaia" in review
    assert "weak-grounding" in review
    assert not (wiki / "links.yaml").exists()


def test_render_lawbrain_accept_flip_is_recorded_and_pruned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a review-queue.md with one operator-flipped [accept] entry. The
    # render pass must record it as a link decision in links.yaml and prune the
    # resolved entry from the queue (D61: resolution folded into the render half).
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    wiki.mkdir(parents=True, exist_ok=True)
    (wiki / "review-queue.md").write_text(
        "- [accept] regulation-california-sb53-tfaia -> ca-2025-sb-53 (collision)\n",
        encoding="utf-8",
    )
    run = tmp_path / "run"
    run.mkdir()
    # No new proposals this pass — only the resolved queue token to apply.
    (run / "classified.json").write_text("[]", encoding="utf-8")

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — decision recorded in links.yaml, queue pruned to empty.
    assert result.exit_code == 0, result.output
    links_yaml = (wiki / "links.yaml").read_text(encoding="utf-8")
    assert "regulation-california-sb53-tfaia" in links_yaml
    assert "ca-2025-sb-53" in links_yaml
    # The resolved [accept] line is gone (queue cleared to empty).
    review = (wiki / "review-queue.md").read_text(encoding="utf-8")
    assert "regulation-california-sb53-tfaia" not in review


def test_render_lawbrain_reject_flip_records_reject_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a [reject] queue token must be recorded as a not-a-link decision
    # and pruned, so the page is never re-proposed (sticky reject).
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    wiki.mkdir(parents=True, exist_ok=True)
    (wiki / "review-queue.md").write_text(
        "- [reject] regulation-fixture-sb53 -> ca-2025-sb-53 (weak-grounding)\n",
        encoding="utf-8",
    )
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text("[]", encoding="utf-8")

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — reject recorded; the SB-53 target keeps no commentary.
    assert result.exit_code == 0, result.output
    links_yaml = (wiki / "links.yaml").read_text(encoding="utf-8")
    assert "regulation-fixture-sb53" in links_yaml
    assert "reject" in links_yaml
    review = (wiki / "review-queue.md").read_text(encoding="utf-8")
    assert "regulation-fixture-sb53" not in review


def test_render_lawbrain_not_in_scope_is_recorded_not_attached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a not_in_scope decision attaches no commentary but IS recorded in
    # links.yaml (Shared Contract: not_in_scope/reject -> record, no attach) so the
    # page is never re-proposed (sticky, D9).
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(
            [
                {
                    "slug": "regulation-fixture-sb53",
                    "target_id": None,
                    "matched_by": "not_in_scope",
                    "confidence": 0.0,
                    "page_keys": ["US-CA::bill::SB-53"],
                    "target_keys": [],
                }
            ]
        ),
        encoding="utf-8",
    )

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — recorded as a not_in_scope decision; no commentary attached anywhere.
    assert result.exit_code == 0, result.output
    assert "0 linked" in result.output
    assert "1 recorded" in result.output
    page = (wiki / Path(*_SB53_PAGE)).read_text(encoding="utf-8")
    assert "## Commentary & Analysis" not in page
    links_yaml = (wiki / "links.yaml").read_text(encoding="utf-8")
    assert "regulation-fixture-sb53" in links_yaml
    assert "not_in_scope" in links_yaml


def test_render_lawbrain_dry_run_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    run = tmp_path / "run"
    run.mkdir()
    (run / "classified.json").write_text(
        json.dumps(_classified_deterministic()), encoding="utf-8"
    )
    page_path = wiki / Path(*_SB53_PAGE)
    before = page_path.read_text(encoding="utf-8")

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite"), "--dry-run"],
    )

    # Assert — intended write reported, page untouched, no registry/queue written.
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
    _write_render_settings(tmp_path)
    wiki = tmp_path / "wiki"
    _seed_sb53_target(wiki)
    run = tmp_path / "run"
    run.mkdir()
    entries = _classified_deterministic() + [{"matched_by": "deterministic"}]
    (run / "classified.json").write_text(json.dumps(entries), encoding="utf-8")

    # Act
    result = _RUNNER.invoke(
        app,
        ["render-lawbrain-commentary", "--in", str(run / "classified.json"),
         "--wiki", str(wiki), "--db", str(tmp_path / "index.sqlite")],
    )

    # Assert — the good link applied, the malformed one isolated as a drop.
    assert result.exit_code == 0, result.output
    assert "1 linked" in result.output
    assert "1 dropped" in result.output
    assert "dropped:" in result.output
