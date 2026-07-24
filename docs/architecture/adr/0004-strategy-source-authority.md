# ADR-0004: Keep Primary Stoic Material as Normative Evidence

- Status: Accepted
- Date: 2026-07-24

## Context

Transcription, VLM captioning, SLM mining, and dataset labels accelerate
research but can omit, paraphrase, or hallucinate details.

## Decision

We will treat Stoic media and PDFs as primary evidence. Transcripts locate media
segments and require human verification before publication. Model-derived
artifacts may aid discovery but cannot be the sole normative source.

## Consequences

- Publication requires provenance and human review.
- Mining remains useful without entering the live path.
- Some rules remain candidates longer when the source is ambiguous.

## Compliance

The validator requires a primary media/PDF record for every executable rule,
checks asset digests and locators, and rejects model-only evidence.
