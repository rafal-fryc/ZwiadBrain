"""Tests for the source API-key redaction helper."""

from zwiadbrain.sources._redact import redact_api_key


def test_redact_api_key_masks_query_param_value() -> None:
    """should replace an api_key query value with REDACTED, leaving the rest intact"""
    url = "https://api.congress.gov/v3/bill/118?api_key=SECRET123&format=json"
    out = redact_api_key(url)
    assert "SECRET123" not in out
    assert "api_key=REDACTED" in out
    assert "format=json" in out


def test_redact_api_key_leaves_strings_without_a_key_untouched() -> None:
    """should pass through a string that carries no api_key param unchanged"""
    assert redact_api_key("/bill/118/hr/8818") == "/bill/118/hr/8818"
