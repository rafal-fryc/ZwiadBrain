"""Tests that the Claude Code subagent + slash-command definitions are well-formed.

The LLM steps of the backfill pipeline are Claude Code subagents in
``.claude/agents/`` driven by the ``/zwiad-backfill`` slash command (run in an
interactive session = the user's regular plan usage). These tests pin the
contract the Python tooling and the orchestrator rely on: agent names, models,
a restricted tools allowlist, and the command wiring.

The legislative-history pipeline (T11–T13) adds two more subagents
(``leg-history-researcher``, ``leg-history-verifier``) and a slash command
(``/zwiad-leg-history``). The researcher uses ``sonnet`` and the verifier uses
``opus`` — the differing models are an explicit cross-modal trust boundary.
"""

from pathlib import Path

import frontmatter
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_AGENTS = _ROOT / ".claude" / "agents"
_COMMAND = _ROOT / ".claude" / "commands" / "zwiad-backfill.md"
_LEG_COMMAND = _ROOT / ".claude" / "commands" / "zwiad-leg-history.md"

_EXPECTED_MODEL = {
    "classifier": "haiku",
    "summarizer": "sonnet",
    "amendment-explainer": "sonnet",
}


@pytest.mark.parametrize("name", sorted(_EXPECTED_MODEL))
def test_agent_definition_is_well_formed(name: str) -> None:
    """should define each subagent with a matching name, expected model, and a tools allowlist"""
    post = frontmatter.loads((_AGENTS / f"{name}.md").read_text(encoding="utf-8"))
    meta = post.metadata
    assert meta.get("name") == name
    assert meta.get("model") == _EXPECTED_MODEL[name]
    # A restricted allowlist (never an omitted/empty field, which would inherit every tool).
    assert "Read" in str(meta.get("tools", ""))
    assert post.content.strip()  # non-empty system prompt


def test_classifier_prompt_states_its_rubric_and_json_contract() -> None:
    """should tell the classifier to read topics.yaml and emit the in_scope JSON keys"""
    body = (_AGENTS / "classifier.md").read_text(encoding="utf-8")
    assert "topics.yaml" in body
    for key in ("in_scope", "topics", "confidence", "rationale", "criterion"):
        assert key in body


def test_backfill_command_wires_python_steps_and_agents() -> None:
    """should reference both Python staging commands and all three subagents"""
    body = _COMMAND.read_text(encoding="utf-8")
    assert "fetch-candidates" in body
    assert "render-classified" in body
    for name in _EXPECTED_MODEL:
        assert name in body


# ---------------------------------------------------------------------------
# T11 — leg-history-researcher
# ---------------------------------------------------------------------------


def test_leg_history_researcher_is_well_formed() -> None:
    """should parse with name leg-history-researcher, required tools, and model sonnet"""
    post = frontmatter.loads(
        (_AGENTS / "leg-history-researcher.md").read_text(encoding="utf-8")
    )
    meta = post.metadata
    assert meta.get("name") == "leg-history-researcher"
    assert meta.get("model") == "sonnet"
    tools_str = str(meta.get("tools", ""))
    assert "WebSearch" in tools_str
    assert "WebFetch" in tools_str
    assert "Read" in tools_str
    assert post.content.strip()  # non-empty system prompt


def test_leg_history_researcher_prompt_states_output_contract() -> None:
    """should instruct the researcher to emit hearings, statements, and narrative"""
    body = (_AGENTS / "leg-history-researcher.md").read_text(encoding="utf-8")
    # Output fields the render-leg-history --in contract requires from the researcher
    for key in ("hearings", "statements", "narrative"):
        assert key in body
    # Statement fields required by models.Statement
    for key in ("speaker", "role", "quote", "source_url", "source_type", "verified"):
        assert key in body
    # Hearing fields required by models.Hearing
    for key in ("title", "committee", "chamber", "date", "citation", "url"):
        assert key in body


# ---------------------------------------------------------------------------
# T12 — leg-history-verifier
# ---------------------------------------------------------------------------


def test_leg_history_verifier_is_well_formed() -> None:
    """should parse with name leg-history-verifier, required tools, and model opus"""
    post = frontmatter.loads(
        (_AGENTS / "leg-history-verifier.md").read_text(encoding="utf-8")
    )
    meta = post.metadata
    assert meta.get("name") == "leg-history-verifier"
    assert meta.get("model") == "opus"
    tools_str = str(meta.get("tools", ""))
    assert "WebFetch" in tools_str
    assert "Read" in tools_str
    assert post.content.strip()  # non-empty system prompt


def test_leg_history_verifier_prompt_states_output_contract() -> None:
    """should instruct the verifier to emit an array of {index, verified, note} verdicts"""
    body = (_AGENTS / "leg-history-verifier.md").read_text(encoding="utf-8")
    for key in ("index", "verified", "note"):
        assert key in body


# ---------------------------------------------------------------------------
# T11 + T12 cross-modal assertion
# ---------------------------------------------------------------------------


def test_researcher_and_verifier_use_different_models() -> None:
    """should use different models — researcher sonnet, verifier opus (cross-modal check)"""
    researcher = frontmatter.loads(
        (_AGENTS / "leg-history-researcher.md").read_text(encoding="utf-8")
    )
    verifier = frontmatter.loads(
        (_AGENTS / "leg-history-verifier.md").read_text(encoding="utf-8")
    )
    researcher_model = researcher.metadata.get("model")
    verifier_model = verifier.metadata.get("model")
    assert researcher_model != verifier_model, (
        f"researcher and verifier must use different models; both are '{researcher_model}'"
    )
    assert researcher_model == "sonnet"
    assert verifier_model == "opus"


# ---------------------------------------------------------------------------
# T13 — zwiad-leg-history command
# ---------------------------------------------------------------------------


def test_leg_history_command_is_well_formed() -> None:
    """should parse with description, argument-hint, and allowed-tools including Task"""
    post = frontmatter.loads(_LEG_COMMAND.read_text(encoding="utf-8"))
    meta = post.metadata
    assert meta.get("description"), "command must have a non-empty description"
    assert meta.get("argument-hint"), "command must have an argument-hint"
    allowed = str(meta.get("allowed-tools", ""))
    assert "Task" in allowed
    assert post.content.strip()  # non-empty body


def test_leg_history_command_references_both_subagents() -> None:
    """should name both subagents and the Python CLI commands it orchestrates"""
    body = _LEG_COMMAND.read_text(encoding="utf-8")
    # Both subagent files must exist and be referenced by name in the command body
    for agent_name in ("leg-history-researcher", "leg-history-verifier"):
        assert agent_name in body, f"command must reference subagent '{agent_name}'"
        agent_file = _AGENTS / f"{agent_name}.md"
        assert agent_file.exists(), f"agent file {agent_file} must exist"
    # Python CLI commands wired by the orchestrator
    assert "fetch-leg-history" in body
    assert "render-leg-history" in body


# ---------------------------------------------------------------------------
# T9 — zwiad-refresh command
# ---------------------------------------------------------------------------


def test_zwiad_refresh_command_frontmatter_parses() -> None:
    """should declare description, argument-hint, and allow Bash/Read/Write/Task"""
    refresh_cmd = _ROOT / ".claude" / "commands" / "zwiad-refresh.md"
    text = refresh_cmd.read_text(encoding="utf-8")
    post = frontmatter.loads(text)
    meta = post.metadata
    assert meta.get("description"), "command must have a non-empty description"
    allowed = str(meta.get("allowed-tools", ""))
    assert "Bash" in allowed
    assert "Read" in allowed
    assert "Write" in allowed
    assert "Task" in allowed


def test_zwiad_refresh_references_existing_subagents() -> None:
    """should reference the classifier, summarizer, amendment-explainer subagents"""
    refresh_cmd = _ROOT / ".claude" / "commands" / "zwiad-refresh.md"
    text = refresh_cmd.read_text(encoding="utf-8")
    assert "classifier" in text
    assert "summarizer" in text
    assert "amendment-explainer" in text


def test_zwiad_refresh_has_all_six_orchestration_steps() -> None:
    """should contain all 6 H3 step headings, in order, in the slash command body"""
    refresh_cmd = _ROOT / ".claude" / "commands" / "zwiad-refresh.md"
    text = refresh_cmd.read_text(encoding="utf-8")
    required_steps = [
        "### 1. Fetch refreshable",
        "### 2. Read the refreshable list",
        "### 3. Per-bill subagent dispatch",
        "### 4. Stage refreshed",
        "### 5. Render + index",
        "### 6. Report",
    ]
    last_pos = -1
    for step in required_steps:
        pos = text.find(step)
        assert pos > last_pos, f"Step out of order or missing: {step!r}"
        last_pos = pos
