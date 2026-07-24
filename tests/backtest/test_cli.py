"""Production CLI tests for observational SP3 workflows."""

from __future__ import annotations

import json
from pathlib import Path

from stoic_derived.backtest.cli import main


def test_readiness_reports_current_blocked_zero_population(capsys: object) -> None:
    exit_code = main(["readiness"])

    assert exit_code == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.out)
    assert payload["status"] == "blocked"
    assert payload["readiness_blockers"]
    assert payload["signal_count"] == 0
    assert payload["trade_count"] == 0
    assert payload["execution"] is False
    assert payload["orders_placed"] == 0


def test_run_publishes_blocked_artifact_without_strategy_release(
    capsys: object, tmp_path: Path
) -> None:
    input_path = tmp_path / "batches.jsonl"
    input_path.write_bytes(b"")
    target = tmp_path / "artifact"

    exit_code = main(
        [
            "run",
            "--input",
            str(input_path),
            "--output",
            str(target),
            "--entry-slippage-ticks",
            "1",
            "--exit-slippage-ticks",
            "1",
            "--fees-ticks-round-turn",
            "1",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.out)
    assert payload["status"] == "blocked"
    assert payload["execution"] is False
    assert payload["orders_placed"] == 0
    assert (target / "run_manifest.json").is_file()


def test_inspect_verifies_and_projects_an_existing_artifact(capsys: object, tmp_path: Path) -> None:
    input_path = tmp_path / "batches.jsonl"
    input_path.write_bytes(b"")
    target = tmp_path / "artifact"
    run_args = [
        "run",
        "--input",
        str(input_path),
        "--output",
        str(target),
        "--entry-slippage-ticks",
        "1",
        "--exit-slippage-ticks",
        "1",
        "--fees-ticks-round-turn",
        "1",
    ]
    assert main(run_args) == 0
    first = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]

    assert main(["inspect", str(target)]) == 0
    inspected = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]

    assert inspected["manifest_id"] == first["manifest_id"]
    assert inspected["run_id"] == first["run_id"]
    assert inspected["status"] == "blocked"
    assert inspected["execution"] is False
    assert inspected["orders_placed"] == 0


def test_run_rejects_implicit_zero_cost_assumptions(capsys: object, tmp_path: Path) -> None:
    input_path = tmp_path / "batches.jsonl"
    input_path.write_bytes(b"")

    exit_code = main(
        [
            "run",
            "--input",
            str(input_path),
            "--output",
            str(tmp_path / "artifact"),
            "--entry-slippage-ticks",
            "0",
            "--exit-slippage-ticks",
            "0",
            "--fees-ticks-round-turn",
            "0",
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "zero-costs declaration" in captured.err
    assert not (tmp_path / "artifact").exists()
