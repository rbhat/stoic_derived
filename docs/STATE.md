# Current state — what is true right now

**Updated: 2026-07-27.** One file, overwritten in place. If it disagrees with a dated note, this
file wins for *status*; the note wins for *findings*.

## Running now

**WP-V §3.2 VLM extraction** — pid in `.artifacts/jobs/wpv-32-extract/pid`, started 2026-07-26
20:49 PDT.

```bash
scripts/extract.sh --status     # safe while live
scripts/extract.sh              # start or resume — always safe, resumes per state
scripts/extract.sh --stop       # e.g. the laptop is hot
```

- 2,476 / 10,120 states (24.5 %), **0 errors**, one `prompt_sha` (`3eccf9049745`), unreadable-line
  rate 0.0000.
- Concept videos (5) complete. `cs_vol1` at 353/439. `cs_vol2-7` and 4 `live_*` not started.
- Measured wall rate **33.5 s/state** (work 21.4 s + the designed thermal duty cycle).
  **~29 h to end of `cs_vol7`, ~77 h to full corpus** — inside the recorded 20–47 h / 45–105 h bracket.
- `--status` prints an ETA built only from states done *this run*; it is not a corpus ETA.
- **Do not stop it.** The reasoning, and every candidate for a prompt change that was rejected, is in
  `docs/notes/2026-07-27-wpv-33-ocr-gate.md` §8. The window for a cheap prompt change closes as it
  advances, and every defect found so far is repairable offline.

## Next, in order

1. **Decision 12, `primary-evidence-review` — needs the user, ~10 minutes.** The gate is built and
   enforced (ADR-0022, status *Proposed*); what is missing is the reviews themselves. Run
   `stoic-rulebook review-queue strategy/rulebook.yaml`: **10 cited ranges, 9m16s of video.** Watch
   each, confirm the claim, sign. Until then no candidate can become `validated`, so this still
   gates the other eleven decisions.
2. Re-run the §3.3 OCR gate on the full corpus — design in
   `docs/notes/2026-07-27-wpv-33-ocr-gate.md` §8. **The tooling is built** (`--videos` prefix filter,
   the capped stratum, `methodterm`); what remains is grading 60 frames against their JPEGs, which
   waits for `10120/10120`. `methodterm`'s first run left 17 tokens to open — the table is in §8.
3. Re-run the spec-coverage probe — `docs/notes/2026-07-27-spec-coverage-probe.md`. Its tier-3
   zeros are a statement about the concept videos only; the case studies and live sessions are the
   worked-example material and are still absent.
4. Rebuild `edu/derived/dataset.jsonl` — read the constraints for Stage B first, they are specific
   and easy to violate.
5. Stage C on WSL: eval delta → QLoRA retrain → eval. Cannot start until Stage A is pushed.

## Known open items

- `_strip_axis_ladders` misses a date axis emitted as **one long line** (it matches runs of ≥4
  lines). Cosmetic, repairable offline against stored records. Not fixed.
- `ocr_confidence` has no enum value for "no text present", so blank frames report `unreadable`.
  Affects ~7 records. Not worth a corpus split.
- `frame_class` flips between `slide` and `chart_annotated` on slides the instructor drew over.
  Not fixable mid-run; handled at dataset build.

## Monitoring

A persistent monitor watches the extraction and reports video completions, error records, a
`prompt_sha` split, and the extractor going down or coming back. Script:
`$CLAUDE_JOB_DIR/tmp/watch_extract.py` (session-scoped, not in the repo).

## Where the depth is

| you want | read |
|---|---|
| what binds the next step | `docs/CONSTRAINTS.md` |
| the extraction: how to run, resume, what breaks | `claude_memories/wpv-32-extraction-ops.md` |
| what the extraction output says, and what not to re-audit | `claude_memories/wpv-32-extraction-findings.md` |
| whether the OCR is trustworthy, and where it is not | `claude_memories/wpv-33-ocr-gate.md` |
| whether the material can answer the 12 open decisions | `docs/notes/2026-07-27-spec-coverage-probe.md` |
| the whole retrain chain across two machines | `docs/notes/2026-07-26-slm-retrain-plan.md` |
| an index of every note | `head -3 docs/notes/*.md` — each carries title, date and status |

Use the command, not a hand-written index: an index file is a copy, and copies drift. Same reason
`docs/CONSTRAINTS.md` points instead of paraphrasing.

## What does not belong in this file

Completed work. This file says what is true now; `git log` says what happened. An item is deleted
when it is done, not struck through, and never annotated with what it used to say. The same holds
for `docs/CONSTRAINTS.md` and the memories: history earns its place only when it stops a repeat —
"two checks were built against `drawn_levels` and retired" is worth keeping, "this file was split"
is not. Dated notes under `docs/notes/` are the exception; they are records and keep their history.
