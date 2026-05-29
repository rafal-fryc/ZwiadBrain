"""Redact secrets from strings before they reach logs or error messages.

Both Congress.gov and GovInfo force key auth as a ``?api_key=`` query param (no
header option), so any request URL that lands in a message could leak the key.
This collapses any api_key= or key= query value to REDACTED.
"""

from __future__ import annotations

import re

# Matches both `api_key=<value>` and a bare `key=<value>` (LegiScan). The \b before
# the alternation, plus listing api_key first, prevents the inner "key" of "api_key"
# from matching separately: "_key" has no word boundary, so \bkey= never fires there.
_SECRET_PARAM_RE = re.compile(r"\b(api_key|key)=[^&\s]+")


def redact_api_key(text: str) -> str:
    """Replace every ``api_key=``/``key=`` value in *text* with ``…=REDACTED``."""
    return _SECRET_PARAM_RE.sub(r"\1=REDACTED", text)
