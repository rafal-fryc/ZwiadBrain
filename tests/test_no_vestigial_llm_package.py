"""Guard: the pre-pivot ``zwiadbrain.llm`` package must not come back.

All LLM work is interactive Claude Code subagents and there is no Anthropic SDK
(DECISIONS.md D26, D30), so a ``zwiadbrain/llm`` Python package would be dead,
misleading code. This test fails if the directory or an importable package
reappears.
"""

import importlib.util
from pathlib import Path


def test_should_have_no_llm_package_directory() -> None:
    llm_dir = Path(__file__).resolve().parent.parent / "src" / "zwiadbrain" / "llm"
    assert not llm_dir.exists(), f"vestigial pre-pivot package present: {llm_dir}"


def test_should_not_be_able_to_import_zwiadbrain_llm() -> None:
    assert importlib.util.find_spec("zwiadbrain.llm") is None
