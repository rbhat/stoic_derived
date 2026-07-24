from __future__ import annotations

import ast
from pathlib import Path

import stoic_derived.ledger as ledger
from stoic_derived.ledger.cli import build_parser

ROOT = Path(__file__).resolve().parents[2]


def test_public_package_exports_only_production_safe_boundaries() -> None:
    assert set(ledger.__all__) == {
        "DriveLedgerConfig",
        "DriveLedgerStore",
        "GoogleDriveTransport",
        "LedgerOutbox",
        "LedgerRunResult",
        "cutoff_events",
        "cutoff_utc_ns",
        "enqueue_cutoff",
        "readiness",
        "reconcile_events",
        "run_release_ledger",
    }


def test_signal_engine_has_no_ledger_dependency() -> None:
    imports: set[str] = set()
    for path in (ROOT / "src/stoic_derived/signal_engine").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

    assert not any("ledger" in name for name in imports)


def test_ledger_production_modules_do_not_import_backtest_or_paper() -> None:
    imports: set[str] = set()
    for path in (ROOT / "src/stoic_derived/ledger").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

    assert not any("backtest" in name or "paper" in name for name in imports)


def test_cli_contains_no_private_production_fixture_path() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    source = (ROOT / "src/stoic_derived/ledger/cli.py").read_text(encoding="utf-8")

    assert "strategy/rulebook.yaml" not in source
    assert "_strategy_neutral_test_program" not in source
    assert "--fixture" not in help_text
