"""Tests for export.py's plan_export_budget preflight wiring.

CPU-only, no GPU, no network, no torch/transformers import: `probe` and
`meminfo` are injected stubs, so no real hardware is ever touched. Nothing
in export.py that actually merges a model is exercised here -- a real merge
is what hung the box once (see export.py's module docstring); this file
only covers the pure budgeting/refusal wiring.
"""

from __future__ import annotations

import pytest

from stoic_training import export, resources

GIB = 1024**3


def make_memory(*, ram_available_gib: float, swap_free_gib: float, ram_total_gib: float = 64.0, swap_total_gib: float = 16.0):
    return resources.MemoryStatus(
        ram_total_bytes=int(ram_total_gib * GIB),
        ram_available_bytes=int(ram_available_gib * GIB),
        swap_total_bytes=int(swap_total_gib * GIB),
        swap_free_bytes=int(swap_free_gib * GIB),
    )


def test_plan_export_budget_fitting_case():
    memory = make_memory(ram_available_gib=58.0, swap_free_gib=16.0)
    budget = export.plan_export_budget(
        gpu_cap_bytes=12 * GIB,
        vram_headroom_bytes=2 * GIB,
        cpu_reserve_bytes=4 * GIB,
        probe=lambda: (24 * GIB, 32 * GIB),
        meminfo=lambda: memory,
    )
    assert budget.fits is True
    resources.require_merge_budget(budget)  # must not raise


def test_plan_export_budget_refusing_case_mentions_wslconfig():
    memory = make_memory(ram_available_gib=3.0, swap_free_gib=1.0, ram_total_gib=15.5, swap_total_gib=4.0)
    budget = export.plan_export_budget(
        gpu_cap_bytes=12 * GIB,
        vram_headroom_bytes=2 * GIB,
        cpu_reserve_bytes=4 * GIB,
        probe=lambda: (14884 * 1024 * 1024, 16 * GIB),
        meminfo=lambda: memory,
    )
    assert budget.fits is False
    with pytest.raises(resources.PreflightError) as excinfo:
        resources.require_merge_budget(budget)
    assert ".wslconfig" in str(excinfo.value)


def test_plan_export_budget_vram_headroom_caps_gpu_cap():
    memory = make_memory(ram_available_gib=58.0, swap_free_gib=16.0)
    budget = export.plan_export_budget(
        gpu_cap_bytes=12 * GIB,
        vram_headroom_bytes=2 * GIB,
        cpu_reserve_bytes=4 * GIB,
        probe=lambda: (10 * GIB, 16 * GIB),  # only 10 GiB free; headroom must dominate
        meminfo=lambda: memory,
    )
    assert budget.gpu_cap_bytes == 8 * GIB
    assert budget.gpu_cap_bytes < 12 * GIB


def test_plan_export_budget_free_vram_none_is_cpu_only():
    memory = make_memory(ram_available_gib=58.0, swap_free_gib=16.0)
    budget = export.plan_export_budget(
        gpu_cap_bytes=12 * GIB,
        vram_headroom_bytes=2 * GIB,
        cpu_reserve_bytes=4 * GIB,
        probe=lambda: None,  # CPU-only box / torch missing / cuda unavailable
        meminfo=lambda: memory,
    )
    assert budget.gpu_cap_bytes == 0
    assert 0 not in budget.max_memory
    assert set(budget.max_memory) == {"cpu"}


@pytest.mark.parametrize(
    "probe_result",
    [
        (24 * GIB, 32 * GIB),
        (10 * GIB, 16 * GIB),
        None,
    ],
)
def test_plan_export_budget_max_memory_never_uses_old_dangerous_13gib_cap(probe_result):
    memory = make_memory(ram_available_gib=58.0, swap_free_gib=16.0)
    budget = export.plan_export_budget(
        gpu_cap_bytes=12 * GIB,
        vram_headroom_bytes=2 * GIB,
        cpu_reserve_bytes=4 * GIB,
        probe=lambda: probe_result,
        meminfo=lambda: memory,
    )
    assert budget.max_memory.get(0) != "13GiB"
    assert budget.max_memory.get("cpu") != "10GiB"
    for value in budget.max_memory.values():
        assert value != "13GiB"
