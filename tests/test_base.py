"""Tests for the Source protocol contract."""

import inspect

from zwiadbrain.sources.base import Source
from zwiadbrain.sources.congress import CongressSource


def test_source_protocol_discover_signature_matches_congress_source() -> None:
    """should declare the same discover keyword params the concrete source exposes"""
    proto_params = set(inspect.signature(Source.discover).parameters)
    concrete_params = set(inspect.signature(CongressSource.discover).parameters)
    # the Protocol must name every keyword the concrete source accepts (congress included)
    assert {"congress", "since", "limit"} <= proto_params
    assert concrete_params <= proto_params


def test_congress_source_satisfies_source_protocol() -> None:
    """should make CongressSource a structural Source (runtime_checkable)"""
    assert isinstance(CongressSource(api_key="k"), Source)
