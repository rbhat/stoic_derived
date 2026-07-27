"""`edu/pipeline/` holds standalone scripts with no `__init__.py`, so the module
under test is loaded by path. It must be registered in `sys.modules` before
`exec_module`, or the `@dataclass` at module scope cannot resolve its own
module and raises."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PIPELINE = Path(__file__).resolve().parents[2] / "edu" / "pipeline"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, PIPELINE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def visual_extract():
    return _load("visual_extract")


@pytest.fixture(scope="session")
def repair_records():
    return _load("repair_records")
