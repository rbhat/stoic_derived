---
name: slide-text-not-in-transcripts
description: "Definitional content lives on slides that no transcript contains, and existing keyframe labels are unverified — one is a hallucinated caption; grep the transcripts is not enough"
metadata:
  type: project
---

`edu/derived/**/transcript.*` captures **audio only**. Much of the education is delivered as
**on-screen text** — slides, template lists, rule statements, chart annotations — and none of it is
in any searchable field.

Found the hard way on 2026-07-26: the First Red/Green Day definition is on a slide in
`concept_simple_stoic_setups_sss` held **00:35:12 → 00:35:57**, and is **never spoken**. Two
sessions of chart-pixel measurement and transcript inference went into circling a question one OCR
pass answers outright. See [[red-day-definition]].

**Existing keyframe labels are unverified and sometimes wrong.** Same video, same slide:

- frame 106 (00:35:12): `label` = "First red day signal", `why` = *"The chart shows the first daily
  close lower after an uptrend…"* — **a hallucinated caption; there is no chart on screen, it is a
  text slide.**
- frame 107 (00:35:57): the cleanest capture of that slide — `label` and `why` both **empty**.

Corpus-wide: 2,233 keyframes, 1,526 with an LLM label, **zero** carrying transcribed slide text.

**How to apply:**

- When asked where something is defined, do **not** conclude from transcripts alone. Check the
  keyframe images at the relevant timestamps before reporting that the material is silent.
- Treat every existing `label` / `why` field as **unverified** (ADR-0021 applies to VLM output just
  as it does to derived numbers).
- `edu/derived/*/transcript.json` has `segments[]` with `start`/`end` — use it for exact video
  citations rather than asking a model to recall a timestamp.

Fix is planned as WP-V: `docs/notes/2026-07-26-exhaustive-visual-extraction-plan.md`.
See [[case-study-fixture-track]], [[slm-model-artifacts]].
