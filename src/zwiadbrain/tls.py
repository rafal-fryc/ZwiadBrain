"""Verify outbound TLS against the operating system's trust store (D120).

Python verifies certificates against certifi's bundled roots and, unlike the OS, never
fetches a missing intermediate certificate. Several state legislature portals
(le.utah.gov, cga.ct.gov) serve incomplete chains, so every Python fetch to them failed
verification while curl and browsers succeeded. ``truststore`` delegates verification
to the OS store — still full verification, never ``verify=False``.
"""

from __future__ import annotations

import truststore


def use_system_trust_store() -> None:
    """Route all subsequently created SSL contexts through the OS trust store.

    Call once at process start, before any HTTP client is built.
    """
    truststore.inject_into_ssl()
