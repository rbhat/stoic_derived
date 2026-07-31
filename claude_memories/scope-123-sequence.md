---
name: scope-123-sequence
description: 2026-07-31 restart — scope is the 1-2-3 sequence; edu/123sequence is the source of truth, edu/videos is supporting only
metadata:
  type: project
---

On 2026-07-31 the project restarted on branch `123seq` with the scope narrowed to the **1-2-3
sequence**. The material is tiered, and the tiers are a user decision, not an inference from the
directory layout:

- **`edu/123sequence/` is the main source** — the 1-2-3 sequence itself.
- **`edu/videos/` is supporting** — 3 concept videos that back it up, nothing more.
- **`edu/resources/`** is 8 case-study PDFs kept for *validating* the rulebook later. The 12 videos
  that sat alongside them were deleted (restorable from `videos.zip`); the PDFs stayed because they
  are small, git-tracked, and readable as labelled setups.

**Why:** the earlier build tried to learn the whole Stoic course at once and produced a broad
extraction pipeline and 16 transcript sets with no rulebook to show for it. Narrowing to one
mechanism makes the target concrete enough to write deterministic rules against.

**How to apply:** when weighing what to transcribe, train on, or cite as the method — reach for
`edu/123sequence/` first, `edu/videos/` only to support it, and treat the case-study PDFs as test
material rather than training material. The end goal is unchanged and still governed by
`CLAUDE.md`: SLM offline to help derive the rulebook, plain deterministic code in the live signal
path. See [[opus-expanded-role]] for how the work gets delegated, and `docs/STATE.md` for what has
been transcribed so far.
