---
name: coverage-claims-need-enumeration
description: A sweep that covers "132 rows" proves nothing about a target with 132 rows — diff the IDs, and list the source directory before claiming the material is silent
metadata:
  type: feedback
---

Never accept a coverage claim on a **count**. Verify it by **enumerating both sets and diffing the
identifiers**. Two instances, found together on 2026-08-08 in the Phase 2a audit:

1. **The sweep's 132 was not §1–§9's 132.** Three subagent sweeps reported 132 rows; `docs/RULEBOOK.md`
   §1–§9 holds 132 definitional rows. The totals reconciled perfectly and the sets were different:
   the sweeps had decomposed 11 prose paragraphs into rows and **missed 11 numbered rules**, including
   `5.3.4` — a rule the audit's own F-1 finding named as needing re-checking — and `5.4.7c`, stated
   **M** on a condition the corpus never states. Extracting the rule IDs from both sides and running
   `comm` exposed it in one command.

2. **Three marked-up charts in `edu/123sequence/` had never been opened.** `stoic_trade2.png`,
   `stoic_live_trade3.png`, `stoic_live_trade4.png` — in the repo since the restart cull, referenced
   nowhere in `docs/`. Hashing every image asset to check source independence enumerated them as a
   side effect. One of them falsified a claim in `docs/RULEBOOK.md` §10.7.

**Why:** the first failure let an audit report a clean bill of health over 107 of 118 rules. The
second is the same failure as **D-23**, which had to be rewritten because `TPA` was assumed silent and
was not — see [[audit-hard-rules-not-in-material]]. A rule recorded as a human decision "because the
material is silent" is only as good as the enumeration of the material behind it.

**How to apply:** before writing that a sweep, audit or search is complete —

- Emit the identifiers of both the target set and the covered set, sort them, and `comm -23` / `comm -13`.
  Matching cardinality is not coverage; it is a coincidence that hides gaps.
- Before recording "the material does not say X", `ls` the source directory and confirm every file in
  it has actually been read. Grep only finds text in files you thought to search.
- Hashing assets to test source independence (per `docs/CONSTRAINTS.md`) doubles as an inventory —
  run it early, not only when two sources look suspiciously alike.
