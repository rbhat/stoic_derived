"""Tests for prompt variants and reasoning-block splitting.

These pin the two defects that made run baseline-211b3f1a05efed81 a 2.6 GPU-hour
measurement of nothing: an unbounded reasoning block eating the whole generation
budget, and an output contract that scoring enforces but no prompt ever states.
See docs/superpowers/specs/2026-07-25-baseline-redo-decision.md.
"""

from __future__ import annotations

import pytest
from stoic_training import evaluate, prompts

# --- reasoning splitting -----------------------------------------------------


def test_split_reasoning_removes_a_closed_block():
    answer, reasoning = prompts.split_reasoning(
        "<think>weighing the options</think>\nAnswer body\nCitation: v1 00:00:01"
    )
    assert answer == "Answer body\nCitation: v1 00:00:01"
    assert "weighing the options" in reasoning


def test_split_reasoning_on_truncated_block_yields_no_answer():
    """The exact shape of 639 of the 699 invalid baseline predictions.

    The point is that this must NOT look like a well-formed answer: the model ran
    out of budget mid-reasoning and said nothing scoreable.
    """
    answer, reasoning = prompts.split_reasoning(
        "<think>Okay, the user wants a structured rule candidate. Let me start by"
    )
    assert answer == ""
    assert reasoning.startswith("<think>")


def test_split_reasoning_leaves_plain_text_untouched():
    text = "Rule candidate: X\nCitation: v1 00:00:01"
    assert prompts.split_reasoning(text) == (text, "")


def test_truncated_reasoning_is_visible_in_generation_health():
    """Scoring still buckets an empty answer as a schema violation (frozen under
    scoring_version "1"), so the truncation has to surface somewhere else."""
    health = evaluate.generation_health(
        [
            {"prediction": "", "prediction_raw": "<think>cut off", "reasoning": "<think>cut off"},
            {"prediction": "ok\nCitation: v1 00:00:01"},
        ]
    )
    assert health == {
        "reasoning_blocks": 1,
        "truncated_reasoning": 1,
        "empty_predictions": 1,
    }


# --- prompt variants ---------------------------------------------------------


def test_stock_variant_leaves_messages_alone():
    messages = [{"role": "system", "content": "orig"}, {"role": "user", "content": "q"}]
    assert prompts.apply_prompt_variant(messages, prompts.PROMPT_VARIANT_STOCK) == messages


def test_format_instructed_appends_to_the_system_turn_without_dropping_it():
    """Appending, not replacing: the dataset's system turn carries the
    "candidates for human review, never trading signals" guardrail."""
    messages = [
        {"role": "system", "content": "You are an offline research assistant."},
        {"role": "user", "content": "q"},
    ]
    varied = prompts.apply_prompt_variant(messages, prompts.PROMPT_VARIANT_FORMAT_INSTRUCTED)

    assert varied[0]["role"] == "system"
    assert "offline research assistant" in varied[0]["content"]
    assert "Citation: <video_id> <HH:MM:SS>" in varied[0]["content"]
    assert varied[1] == {"role": "user", "content": "q"}
    assert messages[0]["content"] == "You are an offline research assistant."  # not mutated


def test_format_instructed_prepends_a_system_turn_when_there_is_none():
    varied = prompts.apply_prompt_variant(
        [{"role": "user", "content": "q"}], prompts.PROMPT_VARIANT_FORMAT_INSTRUCTED
    )
    assert varied[0]["role"] == "system"
    assert len(varied) == 2


def test_unknown_variant_is_refused():
    with pytest.raises(prompts.PromptVariantError):
        prompts.apply_prompt_variant([{"role": "user", "content": "q"}], "nope")


def test_variant_identity_digests_the_instruction_text():
    stock = prompts.prompt_variant_identity(prompts.PROMPT_VARIANT_STOCK)
    instructed = prompts.prompt_variant_identity(prompts.PROMPT_VARIANT_FORMAT_INSTRUCTED)
    assert stock["instruction_sha256"] is None
    assert instructed["instruction_sha256"] is not None
    assert stock != instructed


# --- the contract the variant states must be the contract scoring enforces ----


def test_format_contract_states_every_rule_candidate_label_scoring_requires():
    """Guards the drift risk of writing the contract in prose: if
    evaluate._RULE_CANDIDATE_PREFIXES gains or renames a label, the instructed
    baseline would be asking for the wrong thing and silently score as a
    formatting failure."""
    for prefix in evaluate._RULE_CANDIDATE_PREFIXES:
        assert prefix in prompts.FORMAT_CONTRACT


def test_an_answer_following_the_contract_actually_passes_the_schema_gate():
    """The contract is only worth stating if obeying it clears Tier-0."""
    obedient = (
        "Rule candidate: Breakout at previous daily high\n"
        "Setup / entry condition: Price closes above the previous daily high.\n"
        "Invalidation / caveat: not specified in the cited material\n"
        "Citation: v1 00:00:01"
    )
    assert not evaluate.schema_violation("rule_candidate", obedient)
    assert evaluate.trailing_citation(obedient) == ("v1", "00:00:01")
