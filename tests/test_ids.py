"""Tests for the shared bill-id parser (pipeline/ids.py)."""

import pytest

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.pipeline.ids import parse_bill_id


def test_parse_bill_id_splits_multi_hyphen_type() -> None:
    """should split on first and last hyphen so a multi-char type survives"""
    assert parse_bill_id("118-hjres-45") == (118, "hjres", "45")


def test_parse_bill_id_splits_simple_type() -> None:
    """should parse a plain <congress>-<type>-<number> id"""
    assert parse_bill_id("118-hr-9020") == (118, "hr", "9020")


def test_parse_bill_id_raises_config_error_when_only_one_hyphen() -> None:
    """should raise ConfigError (an AppError), not ValueError, on a two-segment id"""
    with pytest.raises(ConfigError):
        parse_bill_id("hr-1")


def test_parse_bill_id_raises_config_error_when_no_number_segment() -> None:
    """should raise ConfigError when the id has no third segment"""
    with pytest.raises(ConfigError):
        parse_bill_id("118--")


def test_parse_bill_id_raises_config_error_on_non_integer_congress() -> None:
    """should raise ConfigError, not a leaked ValueError, when congress is not an int"""
    with pytest.raises(ConfigError):
        parse_bill_id("abc-hr-1")
