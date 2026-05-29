"""Shared staging + validation helpers for the CLI's fetch/render commands.

``stage_json`` owns the run-dir convention (``<out>`` or a timestamped
``data/runs/<ts>`` directory) and the indented-JSON write that all three
``fetch-*`` commands duplicated.  ``validate_model`` wraps a pydantic
``model_validate`` so a malformed staging payload surfaces as a labelled
:class:`~zwiadbrain.exceptions.ConfigError`, not a raw ``ValidationError``.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from zwiadbrain.exceptions import ConfigError


def stage_json(payload: object, *, name: str, out: Path | None) -> Path:
    """Write *payload* as indented JSON to ``<out>/<name>`` and return the path.

    When *out* is ``None`` the file lands under a fresh timestamped
    ``data/runs/<YYYYMMDDTHHMMSS>`` directory (the convention the fetch commands
    share).  The parent directory is created if missing.
    """
    run_dir = out or Path("data/runs") / dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def validate_model[ModelT: BaseModel](
    model: type[ModelT], data: object, *, label: str
) -> ModelT:
    """Validate *data* into *model*, re-raising a failure as a labelled ConfigError."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"could not parse '{label}': {exc}") from exc
