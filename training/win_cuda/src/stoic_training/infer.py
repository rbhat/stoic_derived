"""Offline inference against a local QLoRA checkpoint.

Purpose guardrail: this runs inference for an OFFLINE research assistant
that proposes cited rule candidates for human review; its output never
touches any live trading path.

Accepts either a base+LoRA-adapter checkpoint directory (containing
adapter_config.json) or an already-merged model directory. Generation
defaults are deterministic: do_sample=False, temperature=None, a fixed
max_new_tokens. Output is JSONL compatible with `evaluate.py --predictions`
([{"meta":..., "task":..., "prediction": str}, ...]).

Heavy imports (torch/transformers/peft) are deferred into functions so
importing this module stays cheap and does not require a GPU.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

DEFAULT_MAX_NEW_TOKENS = 256


class InferenceError(ValueError):
    """Raised when a checkpoint or input record cannot be used for inference."""


def is_adapter_dir(path: str | Path) -> bool:
    return (Path(path) / "adapter_config.json").is_file()


def build_quantization_config():
    """The single source of truth for the 4-bit nf4 load used by BOTH the
    adapter path and the baseline path (an 8B bf16 model does not fit the
    16 GB shared VRAM budget)."""
    import torch
    from transformers import BitsAndBytesConfig

    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )


def load_base_model_and_tokenizer(base_repo_id: str | None, *, base_revision: str | None = None):
    """Load the pinned base model 4-bit, NO adapter. Raises InferenceError
    without base_repo_id."""
    if not base_repo_id:
        raise InferenceError("base_repo_id is required to load the baseline (un-fine-tuned) model")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    quant_config = build_quantization_config()
    model = AutoModelForCausalLM.from_pretrained(
        base_repo_id,
        revision=base_revision,
        quantization_config=quant_config,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
    )
    tokenizer = AutoTokenizer.from_pretrained(base_repo_id, revision=base_revision)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model.eval()
    return model, tokenizer


def load_model_and_tokenizer(
    checkpoint: str | Path | None = None,
    *,
    base_repo_id: str | None = None,
    base_revision: str | None = None,
):
    """Load a merged model, a base model with a LoRA adapter attached, or
    (checkpoint=None) the baseline (un-fine-tuned) base model."""
    if checkpoint is None:
        return load_base_model_and_tokenizer(base_repo_id, base_revision=base_revision)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    checkpoint = Path(checkpoint)
    if is_adapter_dir(checkpoint):
        from peft import PeftModel

        if not base_repo_id:
            raise InferenceError("base_repo_id is required to load a LoRA adapter checkpoint")
        quant_config = build_quantization_config()
        base_model = AutoModelForCausalLM.from_pretrained(
            base_repo_id,
            revision=base_revision,
            quantization_config=quant_config,
            dtype=torch.bfloat16,
            attn_implementation="sdpa",
        )
        model = PeftModel.from_pretrained(base_model, checkpoint)
        tokenizer = AutoTokenizer.from_pretrained(base_repo_id, revision=base_revision)
    else:
        model = AutoModelForCausalLM.from_pretrained(
            checkpoint, dtype=torch.bfloat16, attn_implementation="sdpa"
        )
        tokenizer = AutoTokenizer.from_pretrained(checkpoint)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model.eval()
    return model, tokenizer


def generate_one(
    model: Any,
    tokenizer: Any,
    messages: Sequence[Mapping[str, str]],
    *,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
) -> str:
    """Deterministic single-prompt generation: do_sample=False, no sampling temperature."""
    import torch

    prompt_messages = [message for message in messages if message.get("role") != "assistant"]
    if not prompt_messages:
        raise InferenceError("messages must contain at least one non-assistant turn")
    encoded = tokenizer.apply_chat_template(
        prompt_messages, add_generation_prompt=True, return_tensors="pt"
    )
    # transformers 5.x returns a BatchEncoding (Mapping) from apply_chat_template
    # when return_tensors is set, not a bare tensor; normalize both shapes so
    # model.generate() always receives a real tensor via the input_ids kwarg.
    if isinstance(encoded, Mapping):
        input_ids = encoded["input_ids"]
        attention_mask = encoded.get("attention_mask")
    else:
        input_ids = encoded
        attention_mask = None
    input_ids = input_ids.to(model.device)
    if attention_mask is not None:
        attention_mask = attention_mask.to(model.device)
    generate_kwargs: dict[str, Any] = dict(
        max_new_tokens=max_new_tokens,
        do_sample=False,
        temperature=None,
        top_p=None,
        top_k=None,
        pad_token_id=tokenizer.pad_token_id
        if tokenizer.pad_token_id is not None
        else tokenizer.eos_token_id,
    )
    if attention_mask is not None:
        generate_kwargs["attention_mask"] = attention_mask
    with torch.no_grad():
        output_ids = model.generate(input_ids=input_ids, **generate_kwargs)
    completion_ids = output_ids[0, input_ids.shape[-1] :]
    return tokenizer.decode(completion_ids, skip_special_tokens=True).strip()


def run_batch(
    checkpoint: str | Path | None,
    records: Iterable[Mapping[str, Any]],
    *,
    base_repo_id: str | None = None,
    base_revision: str | None = None,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    """Run deterministic generation over a batch of {"task","meta","messages"} records.

    checkpoint=None routes to the baseline (un-fine-tuned) path via
    load_model_and_tokenizer. Each output row carries a stable `example_id`
    and the resolved `prompt` text (see stoic_training.evaluate.
    example_id_for_record / prompt_from_messages) so scores.json `details`
    entries can be paired back to the exact generation that produced them.

    `progress_cb`, when given, is called after each record with
    (completed_count, total_count) so a caller (e.g. evaluate.py) can drive
    a tailable progress line during a long generation run. `records` is
    materialized into a list first so a total is available up front;
    default None reproduces today's exact behaviour.
    """
    # Deferred: evaluate.py itself only imports infer lazily (inside
    # generate_predictions), so this mirrors that and avoids a module-level
    # import cycle between the two.
    from stoic_training.evaluate import example_id_for_record, prompt_from_messages

    model, tokenizer = load_model_and_tokenizer(
        checkpoint, base_repo_id=base_repo_id, base_revision=base_revision
    )
    record_list = list(records)
    total = len(record_list)
    predictions: list[dict[str, Any]] = []
    for completed, record in enumerate(record_list, start=1):
        messages = record.get("messages")
        if not messages:
            raise InferenceError("record missing messages")
        prediction = generate_one(model, tokenizer, messages, max_new_tokens=max_new_tokens)
        predictions.append(
            {
                "example_id": example_id_for_record(record),
                "meta": record.get("meta", {}),
                "task": record.get("task"),
                "prompt": prompt_from_messages(messages),
                "prediction": prediction,
            }
        )
        if progress_cb is not None:
            progress_cb(completed, total)
    return predictions


def write_predictions_jsonl(predictions: Iterable[Mapping[str, Any]], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        for prediction in predictions:
            handle.write(json.dumps(prediction, ensure_ascii=True, sort_keys=True) + "\n")


def _load_jsonl_records(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline single-prompt or JSONL-batch inference against a local checkpoint."
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Merged model dir, or a LoRA adapter dir (omit with --baseline)",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Load the pinned base model with no adapter; mutually exclusive with --checkpoint",
    )
    parser.add_argument(
        "--base-repo-id",
        default=None,
        help="Required if --checkpoint is a LoRA adapter dir, or with --baseline",
    )
    parser.add_argument("--base-revision", default=None)
    parser.add_argument("--input-jsonl", type=Path, default=None, help="Batch mode: JSONL of {task, meta, messages}")
    parser.add_argument("--prompt", default=None, help="Single-prompt mode: a user message string")
    parser.add_argument("--task", default="cited_qa", help="task label used in single-prompt mode")
    parser.add_argument("--output", type=Path, default=None, help="Write predictions JSONL here")
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    # Before the deferred transformers import, which reads HF_HOME at
    # import time; keeps inference on the migrated base-model cache.
    from stoic_training.config import ensure_hf_home

    ensure_hf_home()
    args = parse_args(argv)

    if args.baseline and args.checkpoint is not None:
        raise SystemExit("--baseline cannot be combined with --checkpoint")
    if not args.baseline and args.checkpoint is None:
        raise SystemExit("--checkpoint is required unless --baseline is given")

    if args.input_jsonl is not None:
        records = _load_jsonl_records(args.input_jsonl)
    elif args.prompt is not None:
        records = [
            {
                "task": args.task,
                "meta": {},
                "messages": [{"role": "user", "content": args.prompt}],
            }
        ]
    else:
        raise SystemExit("one of --input-jsonl or --prompt is required")

    predictions = run_batch(
        None if args.baseline else args.checkpoint,
        records,
        base_repo_id=args.base_repo_id,
        base_revision=args.base_revision,
        max_new_tokens=args.max_new_tokens,
    )

    if args.output is not None:
        write_predictions_jsonl(predictions, args.output)
    for prediction in predictions:
        print(json.dumps(prediction, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
