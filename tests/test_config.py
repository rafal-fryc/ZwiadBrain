"""Tests for settings loading: secrets from .env, operational config from TOML."""

from pathlib import Path

import pytest

from zwiadbrain.config import Settings, load_settings
from zwiadbrain.exceptions import ConfigError

_TOML = """
[llm]
model = "claude-opus-4-7"
classifier_model = "claude-haiku-4-5-20251001"

[sources]
enabled = ["congress", "legiscan"]

[states]
enabled = ["ca", "ny"]

[lawbrain]
enabled = true
path = "C:/law"
min_confidence = 0.75

[lawbrain.type_map]
regulation = "bill"
case = "enforcement"
"""


def _write(tmp_path: Path, toml: str = _TOML, env: str = "") -> tuple[Path, Path]:
    toml_path = tmp_path / "zwiadbrain.toml"
    toml_path.write_text(toml, encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text(env, encoding="utf-8")
    return toml_path, env_path


def test_load_settings_reads_secret_from_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should load CONGRESS_API_KEY from the .env file, not from the TOML"""
    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    toml_path, env_path = _write(tmp_path, env="CONGRESS_API_KEY=secret-key-123\n")
    settings = load_settings(toml_path=toml_path, env_file=env_path)
    assert settings.congress_api_key == "secret-key-123"


def test_load_settings_parses_operational_config_from_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should populate nested model/sources/lawbrain settings from the TOML tables"""
    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    toml_path, env_path = _write(tmp_path)
    settings = load_settings(toml_path=toml_path, env_file=env_path)
    assert settings.llm.model == "claude-opus-4-7"
    assert settings.sources.enabled == ["congress", "legiscan"]
    assert settings.lawbrain.min_confidence == 0.75
    assert settings.lawbrain.type_map["regulation"] == "bill"


def test_require_congress_api_key_raises_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should raise ConfigError when no Congress API key is configured"""
    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    toml_path, env_path = _write(tmp_path)
    settings = load_settings(toml_path=toml_path, env_file=env_path)
    with pytest.raises(ConfigError):
        settings.require_congress_api_key()


def test_env_law_brain_path_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """should let LAW_BRAIN_PATH in .env override the TOML [lawbrain].path"""
    monkeypatch.delenv("LAW_BRAIN_PATH", raising=False)
    toml_path, env_path = _write(tmp_path, env="LAW_BRAIN_PATH=D:/override/law\n")
    settings = load_settings(toml_path=toml_path, env_file=env_path)
    assert settings.effective_law_brain_path == Path("D:/override/law")


def test_lawbrain_rejects_out_of_range_min_confidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should reject a [lawbrain].min_confidence above 1.0"""
    from pydantic import ValidationError

    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    bad_toml = _TOML.replace("min_confidence = 0.75", "min_confidence = 1.5")
    toml_path, env_path = _write(tmp_path, toml=bad_toml)
    with pytest.raises(ValidationError):
        load_settings(toml_path=toml_path, env_file=env_path)


def test_process_env_overrides_dotenv_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should let a process environment variable win over the .env file value"""
    toml_path, env_path = _write(tmp_path, env="CONGRESS_API_KEY=from-file\n")
    monkeypatch.setenv("CONGRESS_API_KEY", "from-process")
    settings = load_settings(toml_path=toml_path, env_file=env_path)
    assert settings.congress_api_key == "from-process"


def test_load_settings_tolerates_missing_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should construct defaults when neither the TOML nor the .env exist"""
    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    settings = load_settings(toml_path=tmp_path / "absent.toml", env_file=tmp_path / "absent.env")
    assert settings.congress_api_key is None
    assert settings.sources.enabled == []


def test_load_settings_reads_govinfo_api_key_from_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should load GOVINFO_API_KEY from the .env file"""
    monkeypatch.delenv("GOVINFO_API_KEY", raising=False)
    toml_path, env_path = _write(tmp_path, env="GOVINFO_API_KEY=govinfo-secret-key-456\n")
    settings = load_settings(toml_path=toml_path, env_file=env_path)
    assert settings.govinfo_api_key == "govinfo-secret-key-456"


def test_require_govinfo_api_key_raises_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should raise ConfigError when no GovInfo API key is configured"""
    monkeypatch.delenv("GOVINFO_API_KEY", raising=False)
    toml_path, env_path = _write(tmp_path)
    settings = load_settings(toml_path=toml_path, env_file=env_path)
    with pytest.raises(ConfigError):
        settings.require_govinfo_api_key()


def test_require_govinfo_api_key_returns_key_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should return the GovInfo API key when it is configured"""
    monkeypatch.delenv("GOVINFO_API_KEY", raising=False)
    toml_path, env_path = _write(tmp_path, env="GOVINFO_API_KEY=govinfo-secret-key-456\n")
    settings = load_settings(toml_path=toml_path, env_file=env_path)
    assert settings.require_govinfo_api_key() == "govinfo-secret-key-456"


def test_require_legiscan_api_key_returns_value_when_set() -> None:
    """should return the LegiScan key when present"""
    settings = Settings(legiscan_api_key="lk-123")
    assert settings.require_legiscan_api_key() == "lk-123"


def test_require_legiscan_api_key_raises_when_unset() -> None:
    """should raise ConfigError when the LegiScan key is missing"""
    with pytest.raises(ConfigError):
        Settings(legiscan_api_key=None).require_legiscan_api_key()


def test_lawbrain_further_reading_defaults_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should default [lawbrain].further_reading to True when the TOML omits it"""
    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    toml_path, env_path = _write(tmp_path)
    settings = load_settings(toml_path=toml_path, env_file=env_path)
    assert settings.lawbrain.further_reading is True


def test_lawbrain_primary_source_domains_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should default [lawbrain].primary_source_domains to the built-in denylist"""
    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    toml_path, env_path = _write(tmp_path)
    settings = load_settings(toml_path=toml_path, env_file=env_path)
    assert settings.lawbrain.primary_source_domains == [
        ".gov",
        "legiscan.com",
        "courtlistener.com",
        "wikipedia.org",
        "europa.eu",
        "legislation.gov.uk",
    ]


def test_lawbrain_reads_link_harvest_config_from_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """should parse [lawbrain].further_reading and primary_source_domains from the TOML"""
    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    toml = (
        "[lawbrain]\n"
        "enabled = true\n"
        'path = "C:/law"\n'
        "further_reading = false\n"
        'primary_source_domains = [".gov", "courtlistener.com"]\n'
    )
    toml_path, env_path = _write(tmp_path, toml=toml)
    settings = load_settings(toml_path=toml_path, env_file=env_path)
    assert settings.lawbrain.further_reading is False
    assert settings.lawbrain.primary_source_domains == [".gov", "courtlistener.com"]


def test_enforcement_settings_loaded_from_toml(tmp_path: Path) -> None:
    from zwiadbrain.config import load_settings
    toml = tmp_path / "zwiadbrain.toml"
    toml.write_text(
        "[enforcement]\n"
        "enabled = true\n"
        "lookback_days = 45\n"
        "min_confidence = 0.8\n"
        "match_window_days = 90\n"
        "[enforcement.ftc]\n"
        'rss_url = "https://www.ftc.gov/feeds/press-release.xml"\n'
        "enabled = true\n"
        "[[enforcement.state_ag]]\n"
        'name = "California OAG"\n'
        'agency_slug = "ca-oag"\n'
        'jurisdiction = "US-CA"\n'
        'url = "https://oag.ca.gov/news/press-releases/feed"\n'
        'kind = "rss"\n'
        "enabled = true\n",
        encoding="utf-8",
    )
    settings = load_settings(toml_path=toml, env_file=tmp_path / ".env")
    assert settings.enforcement.lookback_days == 45
    assert settings.enforcement.min_confidence == 0.8
    assert settings.enforcement.ftc.rss_url.endswith("press-release.xml")
    assert settings.enforcement.state_ag[0].agency_slug == "ca-oag"
    assert settings.enforcement.enabled_state_ags()[0].kind == "rss"
