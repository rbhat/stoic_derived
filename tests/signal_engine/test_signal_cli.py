"""Readiness CLI tests keep draft inspection separate from live compilation."""

from __future__ import annotations

import json
from pathlib import Path

from stoic_derived.signal_engine.cli import main

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_repository_candidate_reports_truthful_blocked_json(capsys: object) -> None:
    exit_code = main(
        [
            "readiness",
            "--candidate",
            str(REPOSITORY_ROOT / "strategy" / "rulebook.yaml"),
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.out)
    assert payload["kind"] == "authoring_candidate"
    assert payload["status"] == "blocked"
    assert payload["sp0_publication_ready"] is False
    assert payload["signal_engine_ready"] is False
    assert "candidate_sha256" in payload
    assert any("human approval" in blocker for blocker in payload["blockers"])


def test_release_requires_external_hash_and_public_key(capsys: object, tmp_path: Path) -> None:
    release = tmp_path / "release.json"
    release.write_text("{}", encoding="utf-8")

    try:
        main(["readiness", "--release", str(release)])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover - argparse must exit
        raise AssertionError("missing release pins must be rejected")

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "--release requires --sha256 and --public-key-hex" in captured.err
