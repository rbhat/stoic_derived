"""Prompt variants for evaluation generation, and the reasoning-block splitter.

Why this module exists: run `baseline-211b3f1a05efed81` scored 0.00 not because
the base model cannot cite, but because it never emitted an answer -- 639 of 699
predictions were truncated inside a `<think>` block. Checking that also showed the
eval set's system prompt never states the output contract that scoring enforces
(the trailing `Citation: <video_id> <hms>` line, and rule_candidate's three
labelled lines); that contract lives only in the fine-tuning targets. See
`docs/superpowers/specs/2026-07-25-baseline-redo-decision.md`.

So a baseline needs two knobs this module owns:

- a **prompt variant**, so we can run both an uninstructed floor and a
  format-instructed zero point that isolates citation *selection* from citation
  *formatting*; and
- `split_reasoning`, so a stray reasoning block is attributed to reasoning rather
  than silently scored as a schema violation.

This module is deliberately dependency-free (no torch, no evaluate import) so both
`infer` and `evaluate` can import it without a cycle and tests can run on CPU.

The contract text below mirrors the checks in `evaluate.schema_violation` /
`evaluate.trailing_citation`. It is duplicated in prose rather than generated from
the regexes on purpose -- a model needs an instruction, not a pattern -- so the
drift risk is real and `tests/test_prompts.py` pins the two together.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence

PROMPT_VARIANT_STOCK = "stock"
PROMPT_VARIANT_FORMAT_INSTRUCTED = "format_instructed"
DEFAULT_PROMPT_VARIANT = PROMPT_VARIANT_STOCK

#: Spelled-out form of what `evaluate.classify_prediction` structurally requires.
#: Appended to (never replacing) the record's own system message, so the offline
#: research-assistant guardrail in that message survives.
FORMAT_CONTRACT = """
Output format requirements (followed exactly, with no preamble, commentary, or
markdown fences):

- End every answer with a citation on its own final line, in exactly this form:
  Citation: <video_id> <HH:MM:SS>
  The timestamp always has two digits per field. Nothing may follow that line.
- For a conflict check, give one such Citation: line per source segment, citing at
  least two distinct video_ids, and state plainly that the segments conflict or are
  ambiguous.
- For a rule candidate, the answer body is exactly three labelled lines, each on
  its own line and in this order, before the citation line:
  Rule candidate: <short name>
  Setup / entry condition: <condition>
  Invalidation / caveat: <caveat, or "not specified in the cited material">
- For any other question, the answer body is prose, then the citation line.
""".strip()

PROMPT_VARIANTS: dict[str, str | None] = {
    PROMPT_VARIANT_STOCK: None,
    PROMPT_VARIANT_FORMAT_INSTRUCTED: FORMAT_CONTRACT,
}

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_UNCLOSED_THINK_RE = re.compile(r"<think>.*\Z", re.DOTALL)


class PromptVariantError(ValueError):
    """Raised for an unknown prompt-variant name."""


def resolve_variant(variant: str | None) -> str:
    name = variant or DEFAULT_PROMPT_VARIANT
    if name not in PROMPT_VARIANTS:
        known = ", ".join(sorted(PROMPT_VARIANTS))
        raise PromptVariantError(f"unknown prompt variant {name!r} (known: {known})")
    return name


def prompt_variant_identity(variant: str | None) -> dict[str, str | None]:
    """Identity payload for a variant: its name AND a digest of its instruction text.

    The digest is what makes editing FORMAT_CONTRACT change the run id. Without it
    two runs whose prompts differ would collide in one run dir under the same name
    -- the same class of bug as the generation config missing from
    `evaluate.baseline_run_id` (see decision doc section 5).
    """
    name = resolve_variant(variant)
    instruction = PROMPT_VARIANTS[name]
    digest = None if instruction is None else hashlib.sha256(instruction.encode()).hexdigest()
    return {"name": name, "instruction_sha256": digest}


def apply_prompt_variant(
    messages: Sequence[Mapping[str, str]], variant: str | None
) -> list[dict[str, str]]:
    """Return messages with the variant's instruction appended to the system turn.

    Appending (rather than replacing) keeps the dataset's own framing -- including
    the "never trading signals" guardrail -- intact. A record with no system turn
    gets one prepended, so the variant is never silently dropped.
    """
    name = resolve_variant(variant)
    instruction = PROMPT_VARIANTS[name]
    result = [dict(message) for message in messages]
    if instruction is None:
        return result

    for message in result:
        if message.get("role") == "system":
            existing = (message.get("content") or "").rstrip()
            message["content"] = f"{existing}\n\n{instruction}" if existing else instruction
            return result

    return [{"role": "system", "content": instruction}, *result]


def split_reasoning(text: str) -> tuple[str, str]:
    """Split a completion into (answer, reasoning).

    Handles both shapes seen from Qwen3: a closed `<think>...</think>` block, and a
    block truncated by the token budget before it ever closes. The truncated case is
    the one that matters -- it has no answer at all, and returning "" for the answer
    lets scoring record that honestly instead of blaming the schema.
    """
    reasoning_parts = _THINK_BLOCK_RE.findall(text)
    answer = _THINK_BLOCK_RE.sub("", text)

    unclosed = _UNCLOSED_THINK_RE.search(answer)
    if unclosed is not None:
        reasoning_parts.append(unclosed.group(0))
        answer = answer[: unclosed.start()]

    reasoning = "\n".join(part.strip() for part in reasoning_parts).strip()
    return answer.strip(), reasoning
