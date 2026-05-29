"""Application settings.

Secrets (API keys, the law-brain path) come from a gitignored ``.env``;
operational config (model names, enabled sources, the ``[lawbrain]`` block) comes
from the committed ``zwiadbrain.toml``. The two never overlap, so the loader reads
the TOML into init kwargs and lets pydantic-settings layer ``.env`` on top.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Annotated, Any

from dotenv import dotenv_values
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from zwiadbrain.exceptions import ConfigError

# .env variable name -> Settings field. Process-environment values win over the file.
_SECRET_ENV: dict[str, str] = {
    "CONGRESS_API_KEY": "congress_api_key",
    "GOVINFO_API_KEY": "govinfo_api_key",
    "LEGISCAN_API_KEY": "legiscan_api_key",
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "LAW_BRAIN_PATH": "law_brain_path",
}


class LLMSettings(BaseModel):
    """Claude model selection (see ``[llm]`` in ``zwiadbrain.toml``)."""

    model: str = "claude-opus-4-7"
    classifier_model: str = "claude-haiku-4-5-20251001"


class SourcesSettings(BaseModel):
    """Which data sources are enabled (see ``[sources]``)."""

    enabled: list[str] = []


class StatesSettings(BaseModel):
    """Priority state set for LegiScan coverage (see ``[states]``)."""

    enabled: list[str] = []


class LawBrainSettings(BaseModel):
    """Read-only law-brain integration settings (see ``[lawbrain]``)."""

    enabled: bool = False
    path: Path | None = None
    min_confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.75
    require_shared_key: bool = True
    demote_headings: bool = True
    commentary: bool = True
    discover: bool = False
    commentary_only_types: list[str] = []
    commentary_only_slug_markers: list[str] = []
    type_map: dict[str, str] = {}


class Settings(BaseSettings):
    """Resolved settings: env-sourced secrets plus TOML-sourced operational config."""

    model_config = SettingsConfigDict(extra="ignore")

    # Secrets — sourced from .env / the environment.
    congress_api_key: str | None = None
    govinfo_api_key: str | None = None
    legiscan_api_key: str | None = None
    anthropic_api_key: str | None = None
    law_brain_path: Path | None = None

    # Operational config — sourced from zwiadbrain.toml tables.
    llm: LLMSettings = LLMSettings()
    sources: SourcesSettings = SourcesSettings()
    states: StatesSettings = StatesSettings()
    lawbrain: LawBrainSettings = LawBrainSettings()

    @property
    def effective_law_brain_path(self) -> Path | None:
        """The law-brain path, with the ``LAW_BRAIN_PATH`` env override winning."""
        return self.law_brain_path or self.lawbrain.path

    def require_congress_api_key(self) -> str:
        """Return the Congress API key, raising :class:`ConfigError` if it is unset."""
        if not self.congress_api_key:
            raise ConfigError(
                "CONGRESS_API_KEY is not set — add it to .env (free key: https://api.data.gov/signup/)"
            )
        return self.congress_api_key

    def require_govinfo_api_key(self) -> str:
        """Return the GovInfo API key, raising :class:`ConfigError` if it is unset."""
        if not self.govinfo_api_key:
            raise ConfigError(
                "GOVINFO_API_KEY is not set — add it to .env (free key: https://api.data.gov/signup/)"
            )
        return self.govinfo_api_key

    def require_legiscan_api_key(self) -> str:
        """Return the LegiScan API key, raising :class:`ConfigError` if it is unset."""
        if not self.legiscan_api_key:
            raise ConfigError(
                "LEGISCAN_API_KEY is not set — add it to .env (free key: https://legiscan.com/legiscan)"
            )
        return self.legiscan_api_key


_DEFAULT_TOML = Path("zwiadbrain.toml")
_DEFAULT_ENV = Path(".env")


def _load_secrets(env_file: Path) -> dict[str, str]:
    """Read secret fields from ``env_file`` and the process environment (env wins)."""
    file_values = dotenv_values(env_file) if env_file.exists() else {}
    secrets: dict[str, str] = {}
    for env_name, field in _SECRET_ENV.items():
        value = os.environ.get(env_name) or file_values.get(env_name)
        if value is not None:
            secrets[field] = value
    return secrets


def load_settings(*, toml_path: Path = _DEFAULT_TOML, env_file: Path = _DEFAULT_ENV) -> Settings:
    """Load settings from ``toml_path`` (operational config) and ``env_file`` (secrets).

    Both files are optional: a missing TOML yields default operational config, and a
    missing ``.env`` falls back to the process environment for secrets. The two never
    overlap (secrets are flat fields, operational config is nested tables), so they are
    merged and validated together. Precedence: process environment > ``.env`` > TOML.
    """
    # tomllib returns untyped table data; values feed pydantic's own validation.
    data: dict[str, Any] = {}
    if toml_path.exists():
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    data.update(_load_secrets(env_file))
    return Settings.model_validate(data)
