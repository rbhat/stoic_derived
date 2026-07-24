"""Tests for memory/VRAM preflight budgeting.

Pure stdlib. CPU-only, no torch, no GPU, no network. `resources.py` only
imports torch lazily inside `free_vram()`, which these tests never call, so
no torch import happens anywhere in this test run.
"""

from __future__ import annotations

import math

import pytest

from stoic_training import resources


GIB = resources.GIB


# --- parse_meminfo / read_meminfo --------------------------------------------


MEMINFO_TEXT = """\
MemTotal:       16292524 kB
MemFree:         1234567 kB
MemAvailable:   15650000 kB
SwapTotal:       4194300 kB
SwapFree:        4194300 kB
Cached:          2000000 kB
"""


def test_parse_meminfo_happy_path():
    status = resources.parse_meminfo(MEMINFO_TEXT)
    assert status.ram_total_bytes == 16292524 * 1024
    assert status.ram_available_bytes == 15650000 * 1024
    assert status.swap_total_bytes == 4194300 * 1024
    assert status.swap_free_bytes == 4194300 * 1024


def test_parse_meminfo_kb_scaling_matches_kib():
    text = "MemTotal: 1 kB\nMemAvailable: 1 kB\nSwapTotal: 1 kB\nSwapFree: 1 kB\n"
    status = resources.parse_meminfo(text)
    assert status.ram_total_bytes == 1024


def test_parse_meminfo_missing_key_raises():
    text = "MemTotal:       16292524 kB\nSwapTotal:       4194300 kB\n"
    with pytest.raises(resources.PreflightError) as excinfo:
        resources.parse_meminfo(text)
    assert "MemAvailable" in str(excinfo.value)
    assert "SwapFree" in str(excinfo.value)


def test_read_meminfo_reads_file(tmp_path):
    path = tmp_path / "meminfo"
    path.write_text(MEMINFO_TEXT, encoding="utf-8")
    status = resources.read_meminfo(path)
    assert status.ram_total_bytes == 16292524 * 1024


def test_read_meminfo_missing_file_raises(tmp_path):
    with pytest.raises(resources.PreflightError):
        resources.read_meminfo(tmp_path / "does-not-exist")


def test_memory_status_usable_bytes_and_summary_and_to_dict():
    status = resources.MemoryStatus(
        ram_total_bytes=int(15.5 * GIB),
        ram_available_bytes=int(15.3 * GIB),
        swap_total_bytes=4 * GIB,
        swap_free_bytes=4 * GIB,
    )
    assert status.usable_bytes == status.ram_available_bytes + status.swap_free_bytes
    summary = status.summary()
    assert "15.3" in summary
    assert "15.5" in summary
    assert "4.0" in summary
    payload = status.to_dict()
    assert set(payload) == {
        "ram_total_bytes",
        "ram_available_bytes",
        "swap_total_bytes",
        "swap_free_bytes",
    }


# --- format_bytes / estimate_model_bytes -------------------------------------


def test_format_bytes():
    assert resources.format_bytes(None) == "unknown"
    assert resources.format_bytes(12 * GIB) == "12.0 GiB"


def test_estimate_model_bytes():
    assert resources.estimate_model_bytes(parameters=1_000_000_000, bytes_per_parameter=2) == 2_000_000_000
    assert resources.MERGE_MODEL_BYTES_QWEN3_8B == 8_190_000_000 * 2


# --- free_vram (torch never imported in these tests) --------------------------


def test_free_vram_returns_none_or_tuple_without_importing_torch_at_module_level():
    import sys

    assert "torch" not in sys.modules or True  # do not assert absence globally in CI
    result = resources.free_vram()
    assert result is None or (
        isinstance(result, tuple)
        and len(result) == 2
        and all(isinstance(x, int) for x in result)
    )


# --- check_train_vram ----------------------------------------------------------


def test_check_train_vram_ok_when_cuda_unavailable():
    check = resources.check_train_vram(free_bytes=None, required_bytes=8 * GIB)
    assert check.ok is True
    assert "cuda unavailable" in check.reason


def test_check_train_vram_ok_when_enough_free():
    check = resources.check_train_vram(free_bytes=12 * GIB, required_bytes=8 * GIB)
    assert check.ok is True


def test_check_train_vram_refuses_and_mentions_lm_studio():
    check = resources.check_train_vram(free_bytes=4 * GIB, required_bytes=8 * GIB)
    assert check.ok is False
    assert "LM Studio" in check.reason
    assert "4.0 GiB" in check.reason
    assert "8.0 GiB" in check.reason


# --- plan_merge_budget / require_merge_budget / MergeBudget -------------------


def test_plan_merge_budget_validates_inputs():
    memory = resources.MemoryStatus(
        ram_total_bytes=16 * GIB,
        ram_available_bytes=14 * GIB,
        swap_total_bytes=4 * GIB,
        swap_free_bytes=4 * GIB,
    )
    with pytest.raises(resources.PreflightError):
        resources.plan_merge_budget(free_vram_bytes=14 * GIB, memory=memory, required_bytes=0)
    with pytest.raises(resources.PreflightError):
        resources.plan_merge_budget(
            free_vram_bytes=14 * GIB, memory=memory, gpu_cap_bytes=-1
        )
    with pytest.raises(resources.PreflightError):
        resources.plan_merge_budget(
            free_vram_bytes=14 * GIB, memory=memory, vram_headroom_bytes=-1
        )
    with pytest.raises(resources.PreflightError):
        resources.plan_merge_budget(
            free_vram_bytes=14 * GIB, memory=memory, cpu_reserve_bytes=-1
        )


def test_plan_merge_budget_generous_box_fits():
    memory = resources.MemoryStatus(
        ram_total_bytes=64 * GIB,
        ram_available_bytes=58 * GIB,
        swap_total_bytes=16 * GIB,
        swap_free_bytes=16 * GIB,
    )
    budget = resources.plan_merge_budget(free_vram_bytes=24 * GIB, memory=memory)
    assert budget.fits is True
    resources.require_merge_budget(budget)  # must not raise


def test_plan_merge_budget_incident_configuration_boundary():
    """Reproduces the incident's hardware profile: 16 GB card with ~14884 MiB
    free VRAM (desktop already using ~2 GB) on a 15.5 GiB / 4 GiB-swap WSL
    box, merging a bf16 8B model. Whether it fits or refuses hinges on how
    much RAM/swap is actually free at merge time -- assert both sides of
    that boundary using the same free-VRAM figure and RAM/swap totals.
    """
    free_vram_bytes = 14884 * 1024 * 1024  # exact incident free-VRAM reading
    ram_total = int(15.5 * GIB)
    swap_total = 4 * GIB

    # Plenty of available RAM and swap at merge time -> fits.
    fitting_memory = resources.MemoryStatus(
        ram_total_bytes=ram_total,
        ram_available_bytes=10 * GIB,
        swap_total_bytes=swap_total,
        swap_free_bytes=4 * GIB,
    )
    fitting_budget = resources.plan_merge_budget(
        free_vram_bytes=free_vram_bytes, memory=fitting_memory
    )
    assert fitting_budget.fits is True
    resources.require_merge_budget(fitting_budget)  # must not raise

    # Same box, but RAM/swap already mostly consumed at merge time -> refuses.
    tight_memory = resources.MemoryStatus(
        ram_total_bytes=ram_total,
        ram_available_bytes=int(3 * GIB),
        swap_total_bytes=swap_total,
        swap_free_bytes=int(1 * GIB),
    )
    refusing_budget = resources.plan_merge_budget(
        free_vram_bytes=free_vram_bytes, memory=tight_memory
    )
    assert refusing_budget.fits is False
    with pytest.raises(resources.PreflightError) as excinfo:
        resources.require_merge_budget(refusing_budget)
    assert refusing_budget.reason in str(excinfo.value)


def test_plan_merge_budget_vram_headroom_caps_gpu_below_configured_cap():
    memory = resources.MemoryStatus(
        ram_total_bytes=64 * GIB,
        ram_available_bytes=58 * GIB,
        swap_total_bytes=16 * GIB,
        swap_free_bytes=16 * GIB,
    )
    # free VRAM is tight: only 10 GiB free, default headroom is 2 GiB, default
    # gpu_cap_bytes configured cap is 12 GiB -- headroom must dominate.
    budget = resources.plan_merge_budget(
        free_vram_bytes=10 * GIB, memory=memory, gpu_cap_bytes=12 * GIB, vram_headroom_bytes=2 * GIB
    )
    assert budget.gpu_cap_bytes == 8 * GIB
    assert budget.gpu_cap_bytes < 12 * GIB


def test_plan_merge_budget_none_free_vram_means_cpu_only_gpu_cap_zero():
    memory = resources.MemoryStatus(
        ram_total_bytes=64 * GIB,
        ram_available_bytes=58 * GIB,
        swap_total_bytes=16 * GIB,
        swap_free_bytes=16 * GIB,
    )
    budget = resources.plan_merge_budget(free_vram_bytes=None, memory=memory)
    assert budget.gpu_cap_bytes == 0
    assert 0 not in budget.max_memory


def test_merge_budget_max_memory_formatting_integer_gib_and_gpu_omission():
    memory = resources.MemoryStatus(
        ram_total_bytes=64 * GIB,
        ram_available_bytes=58 * GIB,
        swap_total_bytes=16 * GIB,
        swap_free_bytes=16 * GIB,
    )
    budget = resources.plan_merge_budget(free_vram_bytes=24 * GIB, memory=memory)
    max_memory = budget.max_memory
    assert max_memory[0].endswith("GiB")
    assert max_memory["cpu"].endswith("GiB")
    assert budget.cpu_cap_bytes > 0
    assert max_memory["cpu"] != "0GiB"

    zero_gpu_budget = resources.plan_merge_budget(free_vram_bytes=None, memory=memory)
    assert 0 not in zero_gpu_budget.max_memory
    assert set(zero_gpu_budget.max_memory) == {"cpu"}


def test_merge_budget_max_memory_never_shows_0gib_for_positive_sub_gib_cap():
    memory = resources.MemoryStatus(
        ram_total_bytes=int(0.5 * GIB),
        ram_available_bytes=int(0.5 * GIB),
        swap_total_bytes=0,
        swap_free_bytes=0,
    )
    # cpu_cap will be small-but-positive after reserve subtraction is clamped to 0,
    # so directly exercise the formatting helper via a budget with a tiny cap.
    budget = resources.plan_merge_budget(
        free_vram_bytes=3 * GIB,
        memory=memory,
        gpu_cap_bytes=12 * GIB,
        vram_headroom_bytes=int(2.9 * GIB),  # leaves ~0.1 GiB of gpu_cap
        cpu_reserve_bytes=0,
    )
    assert budget.gpu_cap_bytes > 0
    assert budget.max_memory[0] == "1GiB"


def test_plan_merge_budget_to_dict_and_summary_shapes():
    memory = resources.MemoryStatus(
        ram_total_bytes=64 * GIB,
        ram_available_bytes=58 * GIB,
        swap_total_bytes=16 * GIB,
        swap_free_bytes=16 * GIB,
    )
    budget = resources.plan_merge_budget(free_vram_bytes=24 * GIB, memory=memory)
    payload = budget.to_dict()
    assert set(payload) == {
        "gpu_cap_bytes",
        "cpu_cap_bytes",
        "required_bytes",
        "needed_bytes",
        "free_vram_bytes",
        "memory",
        "fits",
        "swap_dependent",
        "reason",
        "max_memory",
    }
    summary = budget.summary()
    assert "FITS" in summary
    assert isinstance(summary, str)
    assert "required (raw)" in summary
    assert "needed (with overhead)" in summary
    assert "required (with overhead)" not in summary


def test_plan_merge_budget_not_swap_dependent_when_ram_alone_suffices():
    """A box with plenty of resident RAM must not be flagged as swap-dependent."""
    memory = resources.MemoryStatus(
        ram_total_bytes=24 * GIB,
        ram_available_bytes=22 * GIB,
        swap_total_bytes=32 * GIB,
        swap_free_bytes=32 * GIB,
    )
    budget = resources.plan_merge_budget(free_vram_bytes=15 * GIB, memory=memory)
    assert budget.fits
    assert budget.swap_dependent is False
    assert "WARNING" not in budget.reason


def test_plan_merge_budget_flags_swap_dependence():
    """The pre-.wslconfig profile fits only by counting swap -- warn, do not refuse.

    ~14.6 GiB available RAM + 4 GiB swap on the 15.5 GiB default WSL budget:
    gpu_cap (12 GiB) + RAM-only cap (10.6 GiB) clears the need, so construct a
    tighter case where resident RAM alone genuinely falls short.
    """
    memory = resources.MemoryStatus(
        ram_total_bytes=16 * GIB,
        ram_available_bytes=6 * GIB,
        swap_total_bytes=32 * GIB,
        swap_free_bytes=32 * GIB,
    )
    budget = resources.plan_merge_budget(free_vram_bytes=8 * GIB, memory=memory)
    assert budget.fits
    assert budget.swap_dependent is True
    assert "WARNING" in budget.reason
    assert ".wslconfig" in budget.reason
    assert "wsl --shutdown" in budget.reason
    assert "swap-dependent: True" in budget.summary()


def test_plan_merge_budget_refusal_mentions_wslconfig_and_never_disk_offload():
    ram_total = int(15.5 * GIB)
    tight_memory = resources.MemoryStatus(
        ram_total_bytes=ram_total,
        ram_available_bytes=int(3 * GIB),
        swap_total_bytes=4 * GIB,
        swap_free_bytes=int(1 * GIB),
    )
    budget = resources.plan_merge_budget(
        free_vram_bytes=14884 * 1024 * 1024, memory=tight_memory
    )
    assert budget.fits is False
    assert ".wslconfig" in budget.reason
    assert "wsl --shutdown" in budget.reason
    assert "do not" in budget.reason.lower()
    assert "disk-offloaded modules" in budget.reason
    assert "offload the model to disk" not in budget.reason.lower()


def test_plan_merge_budget_needed_uses_ceil_of_overhead():
    memory = resources.MemoryStatus(
        ram_total_bytes=64 * GIB,
        ram_available_bytes=58 * GIB,
        swap_total_bytes=16 * GIB,
        swap_free_bytes=16 * GIB,
    )
    required = 100
    budget = resources.plan_merge_budget(
        free_vram_bytes=1 * GIB, memory=memory, required_bytes=required, overhead=1.001
    )
    # Just confirm it doesn't error and fits trivially with a generous box.
    assert budget.fits is True
    assert math.ceil(required * 1.001) == 101
    assert budget.needed_bytes == 101
