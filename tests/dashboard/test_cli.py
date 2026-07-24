from __future__ import annotations

from stoic_derived.dashboard.cli import readiness_payload


def test_readiness_without_configuration_is_blocked_and_zero() -> None:
    payload = readiness_payload({})

    assert payload["status"] == "blocked"
    assert payload["observation_count"] == 0
    assert payload["execution"] is False
    assert payload["orders_placed"] == 0
    assert payload["blockers"], "missing environment configuration must be explicit"
