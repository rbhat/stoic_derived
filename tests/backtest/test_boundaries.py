"""Static architecture checks for the observational SP3 package.

These tests deliberately inspect source rather than importing the package.  The
boundary must remain true even when a blocked release keeps normal SP3 runtime
paths unexercised.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKTEST_ROOT = REPOSITORY_ROOT / "src" / "stoic_derived" / "backtest"
SIGNAL_ENGINE_ROOT = REPOSITORY_ROOT / "src" / "stoic_derived" / "signal_engine"

FORBIDDEN_BACKTEST_IMPORT_PREFIXES = (
    "anthropic",
    "aiohttp",
    "databento",
    "httpx",
    "openai",
    "requests",
    "socket",
    "urllib3",
    "websocket",
    "websockets",
    "stoic_derived.dashboard",
    "stoic_derived.execution",
    "stoic_derived.ledger",
    "stoic_derived.market_data.cli",
    "stoic_derived.market_data.databento",
    "stoic_derived.market_data.live",
    "stoic_derived.signal_engine.compiler",
    "stoic_derived.signal_engine.engine",
    "stoic_derived.signal_engine.evaluator",
    "stoic_derived.strategy",
)
FORBIDDEN_SP2_TEST_SEAMS = frozenset(
    {
        "_from_program_for_test",
        "_strategy_neutral_test_program",
        "compile_production_release",
        "evaluate_profile_for_program",
        "load_rulebook",
    }
)
FORBIDDEN_PUBLIC_TOKENS = (
    "engine",
    "fixture",
    "optimizer",
    "program",
    "signal",
    "simulator",
    "strategy",
    "tracker",
)
FORBIDDEN_COMMAND_TOKENS = (
    "disable",
    "enable",
    "execute",
    "filter",
    "optim",
    "order",
    "place",
    "promote",
    "tune",
)
FORBIDDEN_INJECTION_ARGUMENTS = frozenset(
    {
        "engine",
        "fixture",
        "program",
        "rulebook",
        "signal",
        "signals",
        "strategy",
    }
)
FORBIDDEN_ORDER_CALLS = frozenset(
    {
        "cancel_order",
        "execute_order",
        "place_order",
        "send_order",
        "submit_order",
    }
)


def _python_files(root: Path) -> tuple[Path, ...]:
    assert root.is_dir(), f"missing package root: {root}"
    return tuple(sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts))


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_for(path: Path, root: Path) -> str:
    relative = path.relative_to(root.parents[1])
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolved_import(path: Path, node: ast.ImportFrom, root: Path) -> str:
    if node.level == 0:
        return node.module or ""

    package = _module_for(path, root).split(".")
    if path.name != "__init__.py":
        package.pop()
    package = package[: len(package) - node.level + 1]
    if node.module:
        package.extend(node.module.split("."))
    return ".".join(package)


def _imports(path: Path, root: Path) -> Iterator[str]:
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            yield _resolved_import(path, node, root)


def _matches_prefix(module: str, prefixes: Iterable[str]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


def _string_values(node: ast.AST) -> tuple[str, ...]:
    return tuple(
        constant.value
        for constant in ast.walk(node)
        if isinstance(constant, ast.Constant) and isinstance(constant.value, str)
    )


def _module_definitions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _function_argument_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    arguments = (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
    names = {argument.arg for argument in arguments}
    if node.args.vararg is not None:
        names.add(node.args.vararg.arg)
    if node.args.kwarg is not None:
        names.add(node.args.kwarg.arg)
    return names


def _all_exports(tree: ast.Module) -> tuple[str, ...] | None:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            raise AssertionError("backtest __all__ must be a literal sequence")
        values = tuple(
            element.value
            for element in node.value.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        )
        assert len(values) == len(node.value.elts), "backtest __all__ entries must be strings"
        return values
    return None


def _exported_function_definitions(
    package_tree: ast.Module, exports: tuple[str, ...]
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    definitions = _module_definitions(package_tree)
    imported: dict[str, tuple[str, str]] = {}
    for node in package_tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        module = _resolved_import(BACKTEST_ROOT / "__init__.py", node, BACKTEST_ROOT)
        for alias in node.names:
            imported[alias.asname or alias.name] = (module, alias.name)

    exported: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for name in exports:
        if name in definitions:
            exported[name] = definitions[name]
            continue
        if name not in imported:
            continue  # Public immutable result/contract classes are allowed.
        module, imported_name = imported[name]
        if not module.startswith("stoic_derived.backtest"):
            continue
        relative = module.removeprefix("stoic_derived.backtest").lstrip(".")
        source = BACKTEST_ROOT / (relative.replace(".", "/") + ".py")
        if source.is_file():
            exported_definition = _module_definitions(_tree(source)).get(imported_name)
            if exported_definition is not None:
                exported[name] = exported_definition
    return exported


def test_sp2_never_imports_observational_backtest() -> None:
    violations = [
        (path.name, module)
        for path in _python_files(SIGNAL_ENGINE_ROOT)
        for module in _imports(path, SIGNAL_ENGINE_ROOT)
        if _matches_prefix(module, ("stoic_derived.backtest",))
    ]
    assert violations == []


def test_backtest_uses_only_public_offline_dependencies_and_no_test_seams() -> None:
    forbidden_imports: list[tuple[str, str]] = []
    forbidden_references: list[tuple[str, str]] = []
    for path in _python_files(BACKTEST_ROOT):
        tree = _tree(path)
        forbidden_imports.extend(
            (path.name, module)
            for module in _imports(path, BACKTEST_ROOT)
            if _matches_prefix(module, FORBIDDEN_BACKTEST_IMPORT_PREFIXES)
        )
        for node in ast.walk(tree):
            reference = (
                node.id
                if isinstance(node, ast.Name)
                else node.attr
                if isinstance(node, ast.Attribute)
                else node.value
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
                else None
            )
            if reference in FORBIDDEN_SP2_TEST_SEAMS:
                forbidden_references.append((path.name, reference))

    assert forbidden_imports == []
    assert forbidden_references == []


def test_backtest_public_surface_is_observational_and_cannot_inject_strategy_state() -> None:
    package_path = BACKTEST_ROOT / "__init__.py"
    assert package_path.is_file(), "backtest package must have an explicit public boundary"
    tree = _tree(package_path)
    exports = _all_exports(tree)
    if exports is None:
        return

    forbidden_exports = [
        name for name in exports if any(token in name.lower() for token in FORBIDDEN_PUBLIC_TOKENS)
    ]
    assert forbidden_exports == []
    assert all(not name.startswith("_") for name in exports)

    direct_simulator_imports = [
        module
        for module in _imports(package_path, BACKTEST_ROOT)
        if module
        in {
            "stoic_derived.backtest.simulator",
            "stoic_derived.backtest.tracker",
        }
    ]
    assert direct_simulator_imports == []

    forbidden_arguments = {
        name: sorted(_function_argument_names(definition) & FORBIDDEN_INJECTION_ARGUMENTS)
        for name, definition in _exported_function_definitions(tree, exports).items()
        if _function_argument_names(definition) & FORBIDDEN_INJECTION_ARGUMENTS
    }
    assert forbidden_arguments == {}


def test_backtest_public_exports_are_the_reviewed_observational_allowlist() -> None:
    package_path = BACKTEST_ROOT / "__init__.py"
    exports = _all_exports(_tree(package_path))

    assert exports == (
        "inspect_artifact",
        "observe_paper",
        "production_readiness",
        "run_chronological_replay",
        "run_replay",
        "write_artifact",
    )


def test_backtest_cli_has_no_strategy_injection_tuning_or_order_commands() -> None:
    cli_path = BACKTEST_ROOT / "cli.py"
    assert cli_path.is_file(), "backtest CLI must be explicit and auditable"
    tree = _tree(cli_path)
    commands: list[str] = []
    options: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"add_argument", "add_parser"}:
            continue
        values = _string_values(node)
        if node.func.attr == "add_parser":
            commands.extend(values[:1])
        else:
            options.extend(value for value in values if value.startswith("--"))

    forbidden_commands = [
        command
        for command in commands
        if any(token in command.lower() for token in FORBIDDEN_COMMAND_TOKENS)
    ]
    forbidden_options = [
        option
        for option in options
        if any(
            token in option.lower()
            for token in (*FORBIDDEN_COMMAND_TOKENS, *FORBIDDEN_INJECTION_ARGUMENTS)
        )
    ]
    assert forbidden_commands == []
    assert forbidden_options == []


def test_backtest_never_calls_broker_order_apis_or_claims_execution() -> None:
    forbidden_calls: list[tuple[str, str]] = []
    execution_values: list[object] = []
    orders_placed_values: list[object] = []
    for path in _python_files(BACKTEST_ROOT):
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = (
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else None
                )
                if call_name in FORBIDDEN_ORDER_CALLS:
                    forbidden_calls.append((path.name, call_name))
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=True):
                if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                    continue
                if key.value == "execution" and isinstance(value, ast.Constant):
                    execution_values.append(value.value)
                elif key.value == "orders_placed" and isinstance(value, ast.Constant):
                    orders_placed_values.append(value.value)

    assert forbidden_calls == []
    # `execution: false` and `orders_placed: 0` are required artifact disclaimers,
    # not broker claims.  Do not reject the word "execution" elsewhere.
    assert all(value is False for value in execution_values)
    assert all(value == 0 and not isinstance(value, bool) for value in orders_placed_values)
