"""CPU-only regression test for stoic_training.infer.generate_one.

transformers 5.14.1 changed tokenizer.apply_chat_template(..., return_tensors="pt")
to return a BatchEncoding (dict-like) instead of a bare tensor when the
tokenizer path takes that branch. generate_one used to pass that value
straight through to model.generate(...) positionally, which internally does
`inputs_tensor.shape[0]` and blows up with AttributeError on a BatchEncoding
(no `.shape` attribute -- `BatchEncoding.__getattr__` only forwards known
dict keys). This exercises both possible return shapes -- a BatchEncoding and
a bare tensor -- against a stub model that asserts it always receives a real
tensor via the `input_ids` kwarg, so the regression is caught without a GPU
or a real checkpoint.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from stoic_training import infer  # noqa: E402


class _StubTokenizer:
    def __init__(self, encoded):
        self._encoded = encoded
        self.pad_token_id = 0
        self.eos_token_id = 1

    def apply_chat_template(self, messages, add_generation_prompt=True, return_tensors="pt"):
        return self._encoded

    def decode(self, ids, skip_special_tokens=True):
        return "decoded"


class _StubModel:
    """Records the kwargs it was called with and asserts input_ids is a real tensor."""

    def __init__(self):
        self.device = "cpu"
        self.received_kwargs: dict | None = None

    def generate(self, **kwargs):
        self.received_kwargs = kwargs
        input_ids = kwargs.get("input_ids")
        assert isinstance(input_ids, torch.Tensor), (
            f"model.generate must receive a real tensor via input_ids, got {type(input_ids)!r}"
        )
        extra = torch.zeros((input_ids.shape[0], 1), dtype=input_ids.dtype)
        return torch.cat([input_ids, extra], dim=-1)


def _messages():
    return [{"role": "user", "content": "hello"}]


def test_generate_one_normalizes_batch_encoding_from_apply_chat_template():
    from transformers.tokenization_utils_base import BatchEncoding

    input_ids = torch.tensor([[5, 6, 7]])
    attention_mask = torch.ones_like(input_ids)
    encoded = BatchEncoding({"input_ids": input_ids, "attention_mask": attention_mask})
    tokenizer = _StubTokenizer(encoded)
    model = _StubModel()

    result = infer.generate_one(model, tokenizer, _messages())

    assert result == "decoded"
    assert torch.equal(model.received_kwargs["input_ids"], input_ids)
    assert torch.equal(model.received_kwargs["attention_mask"], attention_mask)


def test_generate_one_accepts_bare_tensor_from_apply_chat_template():
    input_ids = torch.tensor([[5, 6, 7]])
    tokenizer = _StubTokenizer(input_ids)
    model = _StubModel()

    result = infer.generate_one(model, tokenizer, _messages())

    assert result == "decoded"
    assert torch.equal(model.received_kwargs["input_ids"], input_ids)
    assert "attention_mask" not in model.received_kwargs
