"""Stub-based regression test for stoic_training.infer's baseline (no-adapter) load path.

Project lesson (2026-07-25, see the apply_chat_template BatchEncoding crash
fixed in generate_one / tests/test_infer.py -- design doc section 6): any
code path that touches transformers generation APIs needs a stub-based
regression test, not a "trust the library" assumption, because
transformers' return shapes and call conventions have changed under us
before. This file fakes torch/transformers/peft entirely (rather than
pytest.importorskip'ing the real libraries, as tests/test_infer.py does) so
it exercises the baseline load path with no GPU and no 16 GB model
download, and pins down two things a real GPU run cannot cheaply assert on
every CI run:

  (a) the exact quantization_config used for the un-fine-tuned baseline
      load -- load_in_4bit=True, bnb_4bit_quant_type="nf4",
      bnb_4bit_use_double_quant=True (infer.build_quantization_config,
      contract C11) -- an 8B bf16 model does not fit the 16 GB shared VRAM
      budget without it;
  (b) that the baseline path NEVER attaches a LoRA adapter
      (no PeftModel.from_pretrained call).

Uses monkeypatch.setitem on sys.modules so the fakes are removed again at
teardown regardless of what other tests in this session have already done
with the real torch/transformers (see tests/test_infer.py, which imports
the real libraries).
"""

from __future__ import annotations

import sys
import types
from typing import ClassVar

import pytest
from stoic_training import infer


class _FakeBitsAndBytesConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeTokenizer:
    def __init__(self):
        self.pad_token = None
        self.eos_token = "<eos>"
        self.pad_token_id = 0
        self.eos_token_id = 1


class _FakeModel:
    def eval(self):
        return self


class _FakeAutoModelForCausalLM:
    calls: ClassVar[list[tuple[str, dict]]] = []

    @classmethod
    def from_pretrained(cls, repo_id, **kwargs):
        cls.calls.append((repo_id, kwargs))
        return _FakeModel()


class _FakeAutoTokenizer:
    calls: ClassVar[list[tuple[str, dict]]] = []

    @classmethod
    def from_pretrained(cls, repo_id, **kwargs):
        cls.calls.append((repo_id, kwargs))
        return _FakeTokenizer()


class _FakePeftModel:
    calls: ClassVar[list[tuple]] = []

    @classmethod
    def from_pretrained(cls, base_model, checkpoint, **kwargs):
        cls.calls.append((base_model, checkpoint, kwargs))
        return base_model


@pytest.fixture
def fake_transformers_stack(monkeypatch):
    """Install fake torch/transformers/peft modules for the duration of one test."""
    _FakeAutoModelForCausalLM.calls = []
    _FakeAutoTokenizer.calls = []
    _FakePeftModel.calls = []

    fake_torch = types.ModuleType("torch")
    fake_torch.bfloat16 = "bfloat16"

    fake_transformers = types.ModuleType("transformers")
    fake_transformers.AutoModelForCausalLM = _FakeAutoModelForCausalLM
    fake_transformers.AutoTokenizer = _FakeAutoTokenizer
    fake_transformers.BitsAndBytesConfig = _FakeBitsAndBytesConfig

    fake_peft = types.ModuleType("peft")
    fake_peft.PeftModel = _FakePeftModel

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "peft", fake_peft)
    return types.SimpleNamespace(
        model=_FakeAutoModelForCausalLM, tokenizer=_FakeAutoTokenizer, peft=_FakePeftModel
    )


def _assert_baseline_quant_config(kwargs):
    quant_config = kwargs["quantization_config"]
    assert quant_config.load_in_4bit is True
    assert quant_config.bnb_4bit_quant_type == "nf4"
    assert quant_config.bnb_4bit_use_double_quant is True


def test_load_base_model_and_tokenizer_uses_4bit_nf4_and_no_adapter(fake_transformers_stack):
    model, tokenizer = infer.load_base_model_and_tokenizer(
        "Qwen/Qwen3-8B", base_revision="deadbeef"
    )

    assert model is not None
    assert tokenizer is not None
    assert len(fake_transformers_stack.model.calls) == 1
    repo_id, kwargs = fake_transformers_stack.model.calls[0]
    assert repo_id == "Qwen/Qwen3-8B"
    assert kwargs["revision"] == "deadbeef"
    _assert_baseline_quant_config(kwargs)

    assert fake_transformers_stack.peft.calls == []  # never attaches a LoRA adapter


def test_load_model_and_tokenizer_none_checkpoint_routes_to_baseline_path(fake_transformers_stack):
    infer.load_model_and_tokenizer(None, base_repo_id="Qwen/Qwen3-8B", base_revision="deadbeef")

    assert len(fake_transformers_stack.model.calls) == 1
    repo_id, kwargs = fake_transformers_stack.model.calls[0]
    assert repo_id == "Qwen/Qwen3-8B"
    assert kwargs["revision"] == "deadbeef"
    _assert_baseline_quant_config(kwargs)
    assert fake_transformers_stack.peft.calls == []


def test_load_model_and_tokenizer_defaults_checkpoint_to_none():
    # No fixture needed: base_repo_id is missing, so the InferenceError is
    # raised before any torch/transformers import is attempted.
    with pytest.raises(infer.InferenceError):
        infer.load_model_and_tokenizer()


def test_load_base_model_and_tokenizer_requires_base_repo_id():
    with pytest.raises(infer.InferenceError):
        infer.load_base_model_and_tokenizer(None)


def test_run_batch_rows_carry_example_id_and_prompt(monkeypatch):
    from stoic_training import evaluate

    def _fake_load_model_and_tokenizer(checkpoint, *, base_repo_id=None, base_revision=None):
        assert checkpoint is None  # baseline path
        return object(), object()

    def _fake_generate_one(model, tokenizer, messages, *, max_new_tokens=256):
        return "generated text"

    monkeypatch.setattr(infer, "load_model_and_tokenizer", _fake_load_model_and_tokenizer)
    monkeypatch.setattr(infer, "generate_one", _fake_generate_one)

    records = [
        {
            "task": "cited_qa",
            "meta": {"video_id": "v1", "hms": "00:00:01"},
            "messages": [{"role": "user", "content": "hello"}],
        }
    ]
    predictions = infer.run_batch(None, records, base_repo_id="Qwen/Qwen3-8B")

    assert len(predictions) == 1
    row = predictions[0]
    assert row["task"] == "cited_qa"
    assert row["prediction"] == "generated text"
    assert row["prompt"] == "hello"
    assert row["example_id"] == evaluate.example_id_for_record(records[0])


def test_example_id_survives_the_generation_to_scoring_round_trip(monkeypatch, tmp_path):
    """The invariant paired comparison rests on (design doc section 4.1/4.3).

    An eval row's id is derived from `messages`; the written prediction row
    no longer has `messages`, only `prompt`. If those two derivations ever
    drifted apart, `compare` would silently see two disjoint id sets --
    every example "only_in_a"/"only_in_b", zero flips, and a meaningless
    p-value -- rather than failing loudly. So pin the round trip through an
    actual predictions.jsonl write + reload.
    """
    from stoic_training import evaluate

    monkeypatch.setattr(
        infer,
        "load_model_and_tokenizer",
        lambda checkpoint, *, base_repo_id=None, base_revision=None: (object(), object()),
    )
    monkeypatch.setattr(
        infer, "generate_one", lambda model, tokenizer, messages, *, max_new_tokens=256: "text"
    )

    eval_rows = [
        {
            "task": "rule_candidate",
            "meta": {"video_id": "v1", "hms": "00:00:01", "category": "concept"},
            "messages": [
                {"role": "system", "content": "ignored: not a user turn"},
                {"role": "user", "content": "Narration window ...\nPropose a rule candidate."},
                {"role": "assistant", "content": "ignored: the gold answer"},
            ],
        }
    ]
    expected = evaluate.example_id_for_record(eval_rows[0])

    predictions = infer.run_batch(None, eval_rows, base_repo_id="Qwen/Qwen3-8B")
    path = tmp_path / "predictions.jsonl"
    infer.write_predictions_jsonl(predictions, path)
    reloaded = evaluate.load_predictions(path)

    assert reloaded[0]["example_id"] == expected
    # Recomputed from the reloaded row (which has `prompt`, not `messages`).
    assert evaluate.example_id_for_record(reloaded[0]) == expected
