"""Tests for the shared bill-id parser (pipeline/ids.py)."""

import pytest

from zwiadbrain.exceptions import ConfigError
from zwiadbrain.pipeline.ids import build_state_bill_id, format_state_bill_number, parse_bill_id


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


@pytest.mark.parametrize(
    ("state", "year", "number", "expected"),
    [
        ("CA", 2023, "SB362", "ca-2023-sb-362"),
        ("CA", 2023, "AB1", "ca-2023-ab-1"),
        ("MD", 2019, "SB0181", "md-2019-sb-181"),   # leading zeros stripped
        ("CA", 2023, "SBX12", "ca-2023-sbx-12"),     # special session, trailing-digit split
        ("ny", 2023, "S1234", "ny-2023-s-1234"),
    ],
)
def test_build_state_bill_id(state: str, year: int, number: str, expected: str) -> None:
    """should build a globally-unique lowercased state id from state/year/bill_number"""
    assert build_state_bill_id(state, year, number) == expected


def test_build_state_bill_id_rejects_number_without_trailing_digits() -> None:
    """should raise ConfigError on a bill number with no trailing digit run"""
    with pytest.raises(ConfigError):
        build_state_bill_id("CA", 2023, "SBA")


def test_two_states_same_number_do_not_collide() -> None:
    """should produce distinct ids for the same bill number in two states (global key)"""
    assert build_state_bill_id("CA", 2023, "SB1") != build_state_bill_id("NY", 2023, "SB1")


@pytest.mark.parametrize(
    ("number", "expected"),
    [("SB362", "SB 362"), ("AB1", "AB 1"), ("SB0181", "SB 181"), ("SBX12", "SBX 12")],
)
def test_format_state_bill_number(number: str, expected: str) -> None:
    """should render a display bill number with a space and stripped leading zeros"""
    assert format_state_bill_number(number) == expected
