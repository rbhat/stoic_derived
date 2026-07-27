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

- ~2,500 / 10,120 states, **0 errors**, one `prompt_sha` (`3eccf9049745`), unreadable-line rate 0.0000.
- Concept videos (5) complete. `cs_vol1` in progress. `cs_vol2-7` and 4 `live_*` not started.
- Measured wall rate **33.5 s/state** (work 21.4 s + the designed thermal duty cycle).
  **~29 h to end of `cs_vol7`, ~77 h to full corpus** — inside the recorded 20–47 h / 45–105 h bracket.
- `--status` prints an ETA built only from states done *this run*; it is not a corpus ETA.
- **Do not stop it.** The reasoning, and every candidate for a prompt change that was rejected, is in
  `docs/notes/2026-07-27-wpv-33-ocr-gate.md` §8. The window for a cheap prompt change closes as it
  advances, and every defect found so far is repairable offline.

## Next, in order

1. **Resolve unresolved decision 12, `primary-evidence-review`.** It is the ADR-0004 gate the other
   eleven decisions pass through — see `docs/CONSTRAINTS.md`.
2. Re-run the §3.3 OCR gate on the full corpus — design in
   `docs/notes/2026-07-27-wpv-33-ocr-gate.md` §8. Needs a small `--videos` filter on `sample`.
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
| the extraction: how to run, resume, what breaks | `claude_memories/wpv-32-extraction-run.md` |
| whether the OCR is trustworthy, and where it is not | `claude_memories/wpv-33-ocr-gate.md` |
| whether the material can answer the 12 open decisions | `docs/notes/2026-07-27-spec-coverage-probe.md` |
| the whole retrain chain across two machines | `docs/notes/2026-07-26-slm-retrain-plan.md` |
| an index of every note | `head -3 docs/notes/*.md` — each carries title, date and status |

Use the command, not a hand-written index: an index file is a copy, and copies drift. Same reason
`docs/CONSTRAINTS.md` points instead of paraphrasing.

## Structural debt

- **`claude_memories/wpv-32-extraction-run.md` is 422 lines doing six jobs** — how to run the job,
  the durability contract, the thermal cycle, the token/context trap, the findings, and the
  "STOP AUDITING `drawn_levels`" directive. It is 31 % of all memory, and it is where a fact that
  was already recorded got missed on 2026-07-27 because nothing surfaced it at the point of need.
  Split into an ops memory and a findings memory. Not done — it needs care, and the STOP directive
  must stay prominent in both.
