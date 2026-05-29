"""Redact secrets from strings before they reach logs or error messages.

Both Congress.gov and GovInfo force key auth as a ``?api_key=`` query param (no
header option), so any request URL that lands in a message could leak the key.
This collapses any ``api_key`` query value to ``REDACTED``.
"""

from __future__ import annotations

import re

_API_KEY_RE = re.compile(r"(api_key=)[^&\s]+")


def redact_api_key(text: str) -> str:
    """Replace every ``api_key=<value>`` occurrence in *text* with ``api_key=REDACTED``."""
    return _API_KEY_RE.sub(r"\1REDACTED", text)
