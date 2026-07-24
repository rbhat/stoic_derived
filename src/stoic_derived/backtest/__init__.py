"""Public observational SP3 boundary.

The package exposes release-bound measurement and immutable artifact operations
only. It cannot accept private strategy fixtures or influence live readiness.
"""

from stoic_derived.backtest.artifact import inspect_artifact, write_artifact
from stoic_derived.backtest.chronological_replay import run_chronological_replay
from stoic_derived.backtest.paper import observe_paper
from stoic_derived.backtest.runner import production_readiness, run_replay

__all__ = [
    "inspect_artifact",
    "observe_paper",
    "production_readiness",
    "run_chronological_replay",
    "run_replay",
    "write_artifact",
]
