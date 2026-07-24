"""Memory/VRAM preflight budgeting for the offline research-assistant SLM.

Purpose guardrail: this budgets host RAM/swap and GPU VRAM for training and
merging an OFFLINE research assistant that proposes cited rule candidates
for human review; its output never touches any live trading path.

Real incident this fixes: export.py once merged an 8B bf16 model with
max_memory={0:"13GiB","cpu":"10GiB"} on a 16 GB card whose desktop already
used ~2 GB; WDDM shared-memory paging plus WSL swap thrash hung the whole
box and forced a hard reboot. Every entrypoint that can repeat that mistake
must call the preflight helpers here and REFUSE with a clear, actionable
message instead of thrashing the machine.

Pure stdlib at import time. `torch` is imported lazily, inside
`free_vram()` only, so this module (and every test that exercises it)
stays importable and runnable on a CPU-only box with no GPU and no torch
installed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GIB: int = 1024**3


class PreflightError(RuntimeError):
    """Raised when a memory/VRAM preflight check fails or cannot be parsed."""


@dataclass(frozen=True, slots=True)
class MemoryStatus:
    ram_total_bytes: int
    ram_available_bytes: int
    swap_total_bytes: int
    swap_free_bytes: int

    @property
    def usable_bytes(self) -> int:
        return self.ram_available_bytes + self.swap_free_bytes

    def to_dict(self) -> dict[str, int]:
        return {
            "ram_total_bytes": self.ram_total_bytes,
            "ram_available_bytes": self.ram_available_bytes,
            "swap_total_bytes": self.swap_total_bytes,
            "swap_free_bytes": self.swap_free_bytes,
        }

    def summary(self) -> str:
        ram_avail = self.ram_available_bytes / GIB
        ram_total = self.ram_total_bytes / GIB
        swap_free = self.swap_free_bytes / GIB
        swap_total = self.swap_total_bytes / GIB
        return (
            f"RAM {ram_avail:.1f}/{ram_total:.1f} GiB available, "
            f"swap {swap_free:.1f}/{swap_total:.1f} GiB free"
        )


_REQUIRED_MEMINFO_KEYS = ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree")


def parse_meminfo(text: str) -> MemoryStatus:
    """Parse /proc/meminfo-format text into a MemoryStatus.

    Handles lines like "MemTotal:  16292524 kB" (kB -> *1024) and tolerates
    unit-less values (already bytes).
    """
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        fields = rest.split()
        if not fields:
            continue
        try:
            amount = int(fields[0])
        except ValueError:
            continue
        unit = fields[1].lower() if len(fields) > 1 else ""
        if unit in ("kb", "kib"):
            amount *= 1024
        values[key] = amount

    missing = [key for key in _REQUIRED_MEMINFO_KEYS if key not in values]
    if missing:
        raise PreflightError(f"meminfo missing required key(s): {', '.join(missing)}")

    return MemoryStatus(
        ram_total_bytes=values["MemTotal"],
        ram_available_bytes=values["MemAvailable"],
        swap_total_bytes=values["SwapTotal"],
        swap_free_bytes=values["SwapFree"],
    )


def read_meminfo(path: str | Path = "/proc/meminfo") -> MemoryStatus:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PreflightError(f"could not read {path}: {exc}") from exc
    return parse_meminfo(text)


def free_vram() -> tuple[int, int] | None:
    """Return (free_bytes, total_bytes) for the current CUDA device, or None.

    Imports torch lazily so this module never requires torch at import
    time. Returns None (never raises) when torch is missing, CUDA is
    unavailable, or the CUDA query itself fails.
    """
    try:
        import torch
    except ImportError:
        return None
    try:
        if not torch.cuda.is_available():
            return None
        free_bytes, total_bytes = torch.cuda.mem_get_info()
    except RuntimeError:
        return None
    return int(free_bytes), int(total_bytes)


def format_bytes(n: float | None) -> str:
    if n is None:
        return "unknown"
    return f"{n / GIB:.1f} GiB"


# --- training preflight ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class VramCheck:
    free_bytes: int | None
    total_bytes: int | None
    required_bytes: int
    ok: bool
    reason: str


def check_train_vram(
    *,
    free_bytes: int | None,
    total_bytes: int | None = None,
    required_bytes: int,
) -> VramCheck:
    if free_bytes is None:
        return VramCheck(
            free_bytes=None,
            total_bytes=total_bytes,
            required_bytes=required_bytes,
            ok=True,
            reason="cuda unavailable; skipping VRAM preflight",
        )

    if free_bytes < required_bytes:
        reason = (
            f"insufficient VRAM: {format_bytes(free_bytes)} free but "
            f"{format_bytes(required_bytes)} required; another process is probably "
            "holding VRAM -- LM Studio is the usual culprit, eject the loaded model "
            "there and retry"
        )
        return VramCheck(
            free_bytes=free_bytes,
            total_bytes=total_bytes,
            required_bytes=required_bytes,
            ok=False,
            reason=reason,
        )

    reason = (
        f"sufficient VRAM: {format_bytes(free_bytes)} free >= "
        f"{format_bytes(required_bytes)} required"
    )
    return VramCheck(
        free_bytes=free_bytes,
        total_bytes=total_bytes,
        required_bytes=required_bytes,
        ok=True,
        reason=reason,
    )


# --- merge/export preflight -------------------------------------------------


def estimate_model_bytes(*, parameters: int, bytes_per_parameter: int = 2) -> int:
    return int(parameters) * int(bytes_per_parameter)


MERGE_MODEL_BYTES_QWEN3_8B: int = estimate_model_bytes(
    parameters=8_190_000_000, bytes_per_parameter=2
)


def _gib_floor_str(n_bytes: int) -> str:
    """Format n_bytes as an integer-GiB accelerate max_memory string.

    Floors to whole GiB (the correct, conservative behaviour for a cap: an
    accelerate max_memory string must never claim more than is actually
    available), but never renders "0GiB" for a positive byte count -- a
    positive-but-sub-GiB cap still gets at least "1GiB".
    """
    if n_bytes <= 0:
        return "0GiB"
    gib = n_bytes // GIB
    if gib < 1:
        gib = 1
    return f"{gib}GiB"


@dataclass(frozen=True, slots=True)
class MergeBudget:
    gpu_cap_bytes: int
    cpu_cap_bytes: int
    required_bytes: int
    needed_bytes: int
    free_vram_bytes: int | None
    memory: MemoryStatus
    fits: bool
    swap_dependent: bool
    reason: str

    @property
    def max_memory(self) -> dict[str | int, str]:
        result: dict[str | int, str] = {}
        if self.gpu_cap_bytes > 0:
            result[0] = _gib_floor_str(self.gpu_cap_bytes)
        result["cpu"] = _gib_floor_str(self.cpu_cap_bytes)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "gpu_cap_bytes": self.gpu_cap_bytes,
            "cpu_cap_bytes": self.cpu_cap_bytes,
            "required_bytes": self.required_bytes,
            "needed_bytes": self.needed_bytes,
            "free_vram_bytes": self.free_vram_bytes,
            "memory": self.memory.to_dict(),
            "fits": self.fits,
            "swap_dependent": self.swap_dependent,
            "reason": self.reason,
            "max_memory": self.max_memory,
        }

    def summary(self) -> str:
        lines = [
            f"merge budget: {'FITS' if self.fits else 'REFUSED'}",
            f"  required (raw): {format_bytes(self.required_bytes)}",
            f"  needed (with overhead): {format_bytes(self.needed_bytes)}",
            f"  free VRAM: {format_bytes(self.free_vram_bytes)}",
            f"  gpu_cap: {format_bytes(self.gpu_cap_bytes)}",
            f"  cpu_cap: {format_bytes(self.cpu_cap_bytes)}",
            f"  host memory: {self.memory.summary()}",
            f"  swap-dependent: {self.swap_dependent}",
            f"  max_memory: {self.max_memory}",
            f"  reason: {self.reason}",
        ]
        return "\n".join(lines)


def plan_merge_budget(
    *,
    free_vram_bytes: int | None,
    memory: MemoryStatus,
    required_bytes: int = MERGE_MODEL_BYTES_QWEN3_8B,
    gpu_cap_bytes: int = 12 * GIB,
    vram_headroom_bytes: int = 2 * GIB,
    cpu_reserve_bytes: int = 4 * GIB,
    overhead: float = 1.15,
) -> MergeBudget:
    if required_bytes <= 0:
        raise PreflightError(f"required_bytes must be positive, got {required_bytes}")
    if gpu_cap_bytes < 0:
        raise PreflightError(f"gpu_cap_bytes must not be negative, got {gpu_cap_bytes}")
    if vram_headroom_bytes < 0:
        raise PreflightError(
            f"vram_headroom_bytes must not be negative, got {vram_headroom_bytes}"
        )
    if cpu_reserve_bytes < 0:
        raise PreflightError(f"cpu_reserve_bytes must not be negative, got {cpu_reserve_bytes}")

    if free_vram_bytes is None:
        gpu_cap = 0
    else:
        gpu_cap = max(0, min(gpu_cap_bytes, free_vram_bytes - vram_headroom_bytes))

    cpu_cap = max(0, memory.usable_bytes - cpu_reserve_bytes)
    needed = math.ceil(required_bytes * overhead)
    fits = (gpu_cap + cpu_cap) >= needed

    # A plan that only closes once swap is counted is the exact shape of the
    # incident: resident RAM runs out mid-merge and the box starts thrashing.
    # It is not a refusal (swap genuinely absorbs the peak once .wslconfig
    # gives it room), but it must be surfaced loudly.
    ram_only_cap = max(0, memory.ram_available_bytes - cpu_reserve_bytes)
    swap_dependent = fits and (gpu_cap + ram_only_cap) < needed

    if fits:
        reason = (
            f"merge plan fits: gpu_cap={format_bytes(gpu_cap)} + cpu_cap={format_bytes(cpu_cap)} "
            f">= needed={format_bytes(needed)} (required {format_bytes(required_bytes)} x "
            f"{overhead:g} overhead)"
        )
        if swap_dependent:
            reason += (
                f". WARNING: this plan only fits by counting swap -- resident RAM alone "
                f"offers {format_bytes(gpu_cap + ram_only_cap)} against "
                f"{format_bytes(needed)} needed. Swap thrash on an undersized WSL budget "
                "is what hung this box before. Confirm %UserProfile%\\.wslconfig "
                "grants a large memory+swap budget and that `wsl --shutdown` has been "
                "run since it was last edited."
            )
    else:
        shortfall = needed - (gpu_cap + cpu_cap)
        reason = (
            f"merge budget REFUSED: gpu_cap={format_bytes(gpu_cap)} + "
            f"cpu_cap={format_bytes(cpu_cap)} is short of needed={format_bytes(needed)} "
            f"(required {format_bytes(required_bytes)} x {overhead:g} overhead) by "
            f"{format_bytes(shortfall)}. Raise the WSL memory/swap budget in "
            "%UserProfile%\\.wslconfig and run `wsl --shutdown` from PowerShell, "
            "and close other VRAM consumers (e.g. eject any model loaded in LM "
            "Studio) before retrying. Do not attempt disk offload: peft cannot merge "
            "disk-offloaded modules."
        )

    return MergeBudget(
        gpu_cap_bytes=gpu_cap,
        cpu_cap_bytes=cpu_cap,
        required_bytes=required_bytes,
        needed_bytes=needed,
        free_vram_bytes=free_vram_bytes,
        memory=memory,
        fits=fits,
        swap_dependent=swap_dependent,
        reason=reason,
    )


def require_merge_budget(budget: MergeBudget) -> None:
    if not budget.fits:
        raise PreflightError(budget.reason)


__all__ = [
    "GIB",
    "MERGE_MODEL_BYTES_QWEN3_8B",
    "MemoryStatus",
    "MergeBudget",
    "PreflightError",
    "VramCheck",
    "check_train_vram",
    "estimate_model_bytes",
    "format_bytes",
    "free_vram",
    "parse_meminfo",
    "plan_merge_budget",
    "read_meminfo",
    "require_merge_budget",
]
