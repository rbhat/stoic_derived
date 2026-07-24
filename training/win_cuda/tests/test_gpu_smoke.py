"""GPU environment smoke checks for the Blackwell (sm_120) pin set.

These tests are the pins-spike verification: torch cu128 sees the GPU and
bitsandbytes can 4-bit-quantize a layer on it. They skip cleanly on machines
without CUDA so the portable test suite stays green.
"""

import pytest

torch = pytest.importorskip("torch")

cuda_required = pytest.mark.skipif(
    not torch.cuda.is_available(), reason="CUDA GPU not available"
)


@cuda_required
def test_cuda_device_is_blackwell_capable():
    major, minor = torch.cuda.get_device_capability(0)
    assert (major, minor) >= (12, 0), f"expected sm_120+, got sm_{major}{minor}"
    # torch must have been built with kernels for this arch
    assert any(
        f"sm_{major}{minor}" in arch for arch in torch.cuda.get_arch_list()
    ), f"torch build lacks sm_{major}{minor}: {torch.cuda.get_arch_list()}"


@cuda_required
def test_cuda_matmul_runs():
    a = torch.randn(64, 64, device="cuda")
    b = torch.randn(64, 64, device="cuda")
    c = a @ b
    assert torch.isfinite(c).all()


@cuda_required
def test_bitsandbytes_4bit_linear_forward():
    import bitsandbytes as bnb

    layer = bnb.nn.Linear4bit(64, 64, quant_type="nf4", compute_dtype=torch.bfloat16)
    layer = layer.to("cuda")
    x = torch.randn(2, 64, device="cuda", dtype=torch.bfloat16)
    y = layer(x)
    assert y.shape == (2, 64)
    assert torch.isfinite(y.float()).all()
