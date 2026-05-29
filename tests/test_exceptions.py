"""Tests for the project exception hierarchy.

Per the project rule that every custom exception inherits from a single
project-level base, these tests pin that contract: a boundary handler can catch
everything ZwiadBrain raises with one `except AppError`.
"""

import pytest

from zwiadbrain.exceptions import (
    AppError,
    ClassificationError,
    ConfigError,
    ItemNotFoundError,
    LawBrainError,
    MatchError,
    RateLimitError,
    RenderError,
    SourceError,
    SourceFetchError,
    StoreError,
    WikiSchemaError,
)

ALL_ERRORS: list[type[AppError]] = [
    ConfigError,
    SourceError,
    SourceFetchError,
    RateLimitError,
    ClassificationError,
    RenderError,
    WikiSchemaError,
    LawBrainError,
    MatchError,
    ItemNotFoundError,
    StoreError,
]


@pytest.mark.parametrize("exc", ALL_ERRORS)
def test_all_errors_subclass_app_error(exc: type[AppError]) -> None:
    """should subclass AppError so one boundary catch handles all of them"""
    assert issubclass(exc, AppError)


def test_source_subclasses_share_the_source_error_base() -> None:
    """should let callers catch fetch + rate-limit failures via SourceError"""
    assert issubclass(SourceFetchError, SourceError)
    assert issubclass(RateLimitError, SourceError)


def test_match_error_is_a_lawbrain_error() -> None:
    """should group matcher failures under the law-brain error family"""
    assert issubclass(MatchError, LawBrainError)


def test_app_error_raises_and_catches_like_a_normal_exception() -> None:
    """should behave as an ordinary exception when raised"""
    with pytest.raises(AppError):
        raise ItemNotFoundError("bill US-CA::SB-362 not found")


def test_store_error_is_an_app_error() -> None:
    """should make StoreError catchable by the single `except AppError` CLI boundary"""
    assert issubclass(StoreError, AppError)
    err = StoreError("index is corrupt")
    assert isinstance(err, AppError)
    assert str(err) == "index is corrupt"
