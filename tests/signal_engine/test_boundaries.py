"""Static dependency fitness tests for the live signal package."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "stoic_derived" / "signal_engine"
FORBIDDEN_IMPORT_PREFIXES = (
    "anthropic",
    "databento",
    "httpx",
    "openai",
    "requests",
    "stoic_derived.backtest",
    "stoic_derived.dashboard",
    "stoic_derived.education",
    "stoic_derived.execution",
    "stoic_derived.ledger",
    "stoic_derived.market_data.databento",
)


def test_signal_package_has_no_forbidden_live_path_imports() -> None:
    imports: list[tuple[Path, str]] = []
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend((path, alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append((path, node.module))

    violations = [
        (path.name, module)
        for path, module in imports
        if module.startswith(FORBIDDEN_IMPORT_PREFIXES)
    ]
    assert violations == []
