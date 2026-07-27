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

- 3,062 / 10,120 states (30.3 %), **0 errors**, one `prompt_sha` (`3eccf9049745`), unreadable-line
  rate 0.0000.
- Concept videos (5) **and `cs_vol1`** complete — 6 of 16. `cs_vol2` at 500/568. `cs_vol3-7` and
  the 4 `live_*` not started.
- Measured wall rate **33.5 s/state** (work 21.4 s + the designed thermal duty cycle).
  **~29 h to end of `cs_vol7`, ~77 h to full corpus** — inside the recorded 20–47 h / 45–105 h bracket.
- `--status` prints an ETA built only from states done *this run*; it is not a corpus ETA.
- **Do not stop it.** The reasoning, and every candidate for a prompt change that was rejected, is in
  `docs/notes/2026-07-27-wpv-33-ocr-gate.md` §8. The window for a cheap prompt change closes as it
  advances, and every defect found so far is repairable offline.

## Next, in order

1. Re-run the §3.3 OCR gate on the full corpus — design in
   `docs/notes/2026-07-27-wpv-33-ocr-gate.md` §8. **The tooling is built** (`--videos` prefix filter,
   the capped stratum, `methodterm`); what remains is grading 60 frames against their JPEGs, which
   waits for `10120/10120`. `methodterm`'s first run left 17 tokens to open — the table is in §8.
2. Re-run the spec-coverage probe — `docs/notes/2026-07-27-spec-coverage-probe.md`. Its tier-3
   zeros are a statement about the concept videos only; the case studies and live sessions are the
   worked-example material and are still absent. Re-run `edu/pipeline/ohlc_join.py --audit` with it.
   **Its §1 `DATED` column counts frames and is inflated ~5× by repetition** — 232 OHLC frames are
   44 distinct quadruples, of which 7 resolve, all to one trading date (§3a). Read §3a before
   quoting any tier-1 count.
3. Rebuild `edu/derived/dataset.jsonl` — read the constraints for Stage B first, they are specific
   and easy to violate.
4. Stage C on WSL: eval delta → QLoRA retrain → eval. Cannot start until Stage A is pushed.

## Repairing stored records — do this instead of re-extracting

`edu/pipeline/repair_records.py` edits `visual_records.jsonl` in place: dry-run by default,
idempotent, refuses any video whose `extract` stage is not `done`, and logs every change with its
before-text to `.artifacts/research/visual/repairs.jsonl`. **Re-extracting to fix an OCR token costs
45–105 h; this costs seconds.** An entry needs ground truth read off the JPEG on *every* frame it
touches — not a sample, not a plausible neighbour. Labels only; values are never repaired.

Applied so far: `RHOW` → `PHOW` in `cs_vol1` (20 records, 39 substitutions).

## Known open items

- `_strip_axis_ladders` misses a date axis emitted as **one long line** (it matches runs of ≥4
  lines). Cosmetic. **Now has a mechanism** — fix the filter, then re-apply offline via
  `repair_records.py`. Not fixed.
- `ocr_confidence` has no enum value for "no text present", so blank frames report `unreadable`.
  Affects ~7 records. Not worth a corpus split.
- `frame_class` flips between `slide` and `chart_annotated` on slides the instructor drew over.
  Not fixable mid-run; handled at dataset build.

## Monitoring

A monitor polls `scripts/extract.sh --status` and emits an event on: a video completing, an error
record appearing, a `prompt_sha` split, the extractor going down or coming back, and the corpus
finishing. **It is session-scoped and dies with the session — re-arm it at the start of each one.**
Nothing depends on it; it only saves polling.

§8 of the OCR-gate note names the milestones worth a real look. Milestone 1 (`cs_vol1`) is **done**.
**Milestone 2 is `cs_vol3_gold_futures_study`** — the gold study, where `HCOM`/`HCOW`/`LCOM`/`LCOW`
recur heavily, so it is the real test of whether §5's `HCOW` → `HCOM` substitution rate generalises.
Milestone 3 is the first `live_*`, where `mixed` and `talking_head` should first appear.

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
