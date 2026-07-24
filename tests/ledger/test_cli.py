from __future__ import annotations

import json

from stoic_derived.ledger.cli import build_parser, main


def test_readiness_command_reports_blocked_zero_without_drive_access(capsys) -> None:
    exit_code = main(["readiness"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "blocked"
    assert payload["signal_count"] == 0
    assert payload["event_count"] == 0
    assert payload["execution"] is False
    assert payload["orders_placed"] == 0


def test_cli_has_no_fixture_strategy_performance_or_execution_switch() -> None:
    help_text = build_parser().format_help().lower()
    command_names = set(build_parser()._subparsers._group_actions[0].choices)

    assert command_names == {"readiness", "run", "watchdog", "reconcile", "sync"}
    for forbidden in (
        "fixture",
        "candidate",
        "backtest",
        "performance",
        "promote",
        "broker",
        "order",
    ):
        assert forbidden not in help_text
