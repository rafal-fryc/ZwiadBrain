"""System trust store for outbound TLS (D120).

Some state portals (le.utah.gov, cga.ct.gov) serve an incomplete certificate chain that
Windows completes but Python's bundled certifi store cannot; every Python fetch to them
failed. ``use_system_trust_store`` routes verification through the OS store.
"""

import pytest

from zwiadbrain import tls


def test_should_inject_the_system_trust_store_into_ssl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(tls.truststore, "inject_into_ssl", lambda: calls.append("inject"))

    tls.use_system_trust_store()

    assert calls == ["inject"]
