"""Tests that the Claude Code subagent + slash-command definitions are well-formed.

The LLM steps of the backfill pipeline are Claude Code subagents in
``.claude/agents/`` driven by the ``/zwiad-backfill`` slash command (run in an
interactive session = the user's regular plan usage). These tests pin the
contract the Python tooling and the orchestrator rely on: agent names, models,
a restricted tools allowlist, and the command wiring.
"""

from pathlib import Path

import frontmatter
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_AGENTS = _ROOT / ".claude" / "agents"
_COMMAND = _ROOT / ".claude" / "commands" / "zwiad-backfill.md"

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
