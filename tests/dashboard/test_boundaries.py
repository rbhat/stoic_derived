from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_SOURCE = ROOT / "src" / "stoic_derived" / "dashboard"


def test_dashboard_has_no_template_ssr_rsc_or_execution_imports() -> None:
    forbidden_modules = {
        "jinja2",
        "next",
        "stoic_derived.backtest",
        "stoic_derived.strategy.rulebook",
    }
    violations: list[str] = []
    for path in DASHBOARD_SOURCE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {node.module or ""}
            else:
                continue
            for name in names:
                if any(name == item or name.startswith(f"{item}.") for item in forbidden_modules):
                    violations.append(f"{path.name}: {name}")

    assert not violations, "dashboard cannot import templates, SSR, backtest, or draft strategy"


def test_dashboard_source_has_no_production_fixture_or_bypass_vocabulary() -> None:
    forbidden = (
        "fixture_mode",
        "bypass_auth",
        "impersonate_user",
        "production_fixture",
        "load_sample_data",
        "place_order",
        "broker_api",
    )
    combined = "\n".join(
        path.read_text(encoding="utf-8").casefold()
        for path in sorted(DASHBOARD_SOURCE.glob("*.py"))
    )

    assert not {term for term in forbidden if term in combined}, (
        "production dashboard source cannot expose fixtures, auth bypasses, or execution"
    )
