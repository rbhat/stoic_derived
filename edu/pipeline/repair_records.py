#!/usr/bin/env python3
"""Offline, logged, reversible repairs to stored visual records.

NO RE-EXTRACTION. These edits read and rewrite `visual_records.jsonl` in place.
Re-extracting the corpus to fix an OCR token would cost 45-105 h to correct
something that is repairable in seconds, which is why §8 of
`docs/notes/2026-07-27-wpv-33-ocr-gate.md` decided against a prompt change.

WHAT MAY GO IN THE TABLE BELOW, AND WHAT MAY NOT
------------------------------------------------
Only a token whose ground truth has been read off the JPEG **on every frame it
occurs on** -- not sampled, not inferred from a neighbour, not "the familiar
term is probably right". §5 of the same note records three findings that
reversed on inspection (`BLL`, `PHCOM`, and `HCOW`, which was correct where
`HCOM` was the error), and warns in as many words: the instinct to fix a token
toward the familiar term is the same instinct the model has. Every entry
therefore carries `evidence`, and the evidence names frames, not a rationale.

`label` repairs only. Values are NOT repaired: level prices are advisory by
decision and are not trained on (`claude_memories/wpv-32-extraction-findings.md`,
§ Stage B), so correcting them buys nothing and asserting one from a reading
is the exact failure being repaired.

SAFETY
------
- Refuses to touch a video whose extraction is not complete, so it can never
  race the live run.
- `--dry-run` is the default. `--apply` writes.
- Idempotent: re-running after a successful apply is a no-op.
- Every applied change is appended to `.artifacts/research/visual/repairs.jsonl`
  with the before and after text, so any repair can be audited or undone.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from visual_extract import _count_ocr_lines, _strip_axis_ladders

REPO = pathlib.Path(__file__).resolve().parents[2]
VISUAL = REPO / ".artifacts" / "research" / "visual"
LOG = VISUAL / "repairs.jsonl"

# Each entry: a token the model emitted, the token the CHART actually shows, and
# the evidence that settles it. Keep this list short and keep it earned.
REPAIRS = [
    {
        "id": "rhow-to-phow",
        "wrong": "RHOW",
        "right": "PHOW",
        "scope": "cs_vol1_stoic_edge_in_action_case_studies",
        "evidence":
            "All 20 frames carrying RHOW are the same chart, 'BTC Mar 18th, 2026 "
            "(First Red Day)', states 0365-0438. Every one was read off its JPEG "
            "via a contact sheet of the label band from all 20, plus a native-"
            "resolution crop of #0365. Both panels print PHOW 74,100.00 on all 20. "
            "The right panel's P is crossed by the dashed vertical session line, "
            "and stem-plus-bowl reads as R -- the same occlusion mechanism as the "
            "PWH -> BWH finding in ocr-gate note §5. RHOW is not a method term and "
            "appears nowhere else in the corpus. On #0369 the instructor's drawn "
            "stroke crosses the LEFT panel's PHOW, so the model lost it and emitted "
            "only the R-looking right-hand copy -- that frame is the one where this "
            "repair recovers a label rather than de-duplicating one.",
        "note":
            "7 of the 20 carry a non-74,100.00 value on that line (74,200.00 is the "
            "axis tick above the label's own tag; 00 / 9 / 71,998.62 are junk). "
            "Values are deliberately NOT repaired -- see the module docstring.",
    },
]


def token_re(tok: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(tok)}(?![A-Za-z0-9])")


def video_complete(video: str) -> tuple[bool, str]:
    """Never edit a file the extractor may still be appending to.

    The authority is the `extract` stage's own status in `extract_state.json`
    -- the same object the runner owns -- not a line count we infer, which
    would race a partial write."""
    st = VISUAL / video / "extract_state.json"
    if not st.exists():
        return False, "no extract_state.json"
    try:
        stage = json.loads(st.read_text())["stages"]["extract"]
    except Exception as e:
        return False, f"unreadable extract_state.json ({e!r})"
    if stage.get("status") != "done":
        return False, f"extract stage status={stage.get('status')!r}"
    return True, (f"{stage.get('total_states')} states, "
                  f"{stage.get('errors')} errors, finished {stage.get('finished')}")


def apply_to_record(rec: dict, wrong: str, right: str) -> tuple[dict, dict | None]:
    """Rewrite the token in `ocr_text` and in drawn-level / annotation LABELS."""
    pat = token_re(wrong)
    before = {"ocr_text": rec.get("ocr_text", ""),
              "labels": [lv.get("label") for lv in (rec.get("chart") or {}).get(
                  "drawn_levels") or []],
              "annotations": list((rec.get("chart") or {}).get("annotations") or [])}
    hits = 0

    if rec.get("ocr_text") and pat.search(rec["ocr_text"]):
        rec["ocr_text"], n = pat.subn(right, rec["ocr_text"])
        hits += n
    ch = rec.get("chart") or {}
    for lv in ch.get("drawn_levels") or []:
        if lv.get("label") and pat.search(lv["label"]):
            lv["label"], n = pat.subn(right, lv["label"])
            hits += n
    anns = ch.get("annotations")
    if anns:
        for i, a in enumerate(anns):
            if a and pat.search(a):
                anns[i], n = pat.subn(right, a)
                hits += n
    if not hits:
        return rec, None
    return rec, {"id": rec["id"], "substitutions": hits, "before": before}


def restrip_record(rec: dict) -> tuple[dict, dict | None]:
    """Re-derive `ocr_text` by running the CURRENT `_strip_axis_ladders` over
    the model's original output.

    Unlike the token repairs above this asserts nothing about the pixels -- it
    only re-applies deterministic code that has since been fixed, so it needs
    no JPEG evidence. The source is always `ocr_text_raw` when present (the
    untouched model output), never the already-stripped `ocr_text`; that is
    what makes a second pass a no-op and what lets the count come out as the
    total removed rather than the amount removed this time.

    Because raw is untouched it still carries any token an earlier repair
    rewrote, so the token table is re-applied on top of the freshly stripped
    text. Without that, re-stripping `cs_vol1` would put `RHOW` back on 19
    records and delete the `PHOW` that the repair recovered on `#0369`.
    `ocr_text` is therefore defined as strip(raw) + the token table, and the
    two compose in either order.
    """
    raw = rec.get("ocr_text_raw") or rec.get("ocr_text")
    if not raw:
        return rec, None

    cleaned, removed = _strip_axis_ladders(raw)
    for rep in REPAIRS:
        if rec.get("video") == rep["scope"]:
            cleaned = token_re(rep["wrong"]).sub(rep["right"], cleaned)
    if cleaned == rec.get("ocr_text"):
        return rec, None

    before = {"ocr_text": rec.get("ocr_text", ""),
              "axis_lines_stripped": rec.get("axis_lines_stripped", 0),
              "ocr_line_count": rec.get("ocr_line_count")}
    newly = removed - rec.get("axis_lines_stripped", 0)

    unreadable, line_count = _count_ocr_lines(cleaned)
    rec["ocr_text"] = cleaned
    rec["unreadable_lines"] = unreadable
    rec["ocr_line_count"] = line_count
    if removed:
        # Same invariant as _build_ok_record: both keys are carried only when
        # the filter actually fired.
        rec["axis_lines_stripped"] = removed
        rec["ocr_text_raw"] = raw
    return rec, {"id": rec["id"], "lines_removed": newly, "before": before}


def write_atomic(path: pathlib.Path, text: str) -> None:
    """Never leave a partially written `visual_records.jsonl` behind -- it
    costs 45-105 h to regenerate and there is no second copy."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def run_restrip(apply: bool, stamp: str) -> int:
    """Re-strip every video whose extraction is complete."""
    total = 0
    for d in sorted(VISUAL.iterdir()):
        f = d / "visual_records.jsonl"
        if not d.is_dir() or not f.exists():
            continue
        print(f"\n=== restrip: {d.name}")
        ok, why = video_complete(d.name)
        if not ok:
            print(f"  SKIPPED -- extraction not complete ({why}).")
            continue
        print(f"  extraction complete: {why}")

        out, changes = [], []
        for ln in f.read_text().splitlines():
            if not ln.strip():
                out.append(ln)
                continue
            rec, ch = restrip_record(json.loads(ln))
            if ch:
                changes.append(ch)
            out.append(json.dumps(rec, ensure_ascii=False))

        print(f"  records affected  {len(changes)}")
        print(f"  lines removed     {sum(c['lines_removed'] for c in changes)}")
        if not changes:
            print("  nothing to do (already re-stripped, or no axis survived)")
            continue
        if not apply:
            print("  DRY RUN -- pass --apply to write.")
            continue

        write_atomic(f, "\n".join(out) + "\n")
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as fh:
            fh.write(json.dumps({"applied_utc": stamp,
                                 "repair": {"id": "restrip-axis-ladders",
                                            "evidence": "deterministic re-run of "
                                            "_strip_axis_ladders; no pixel claim"},
                                 "video": d.name, "changes": changes},
                                ensure_ascii=False) + "\n")
        total += len(changes)
        print(f"  APPLIED. Logged to {LOG.relative_to(REPO)}.")
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    ap.add_argument("--only", help="run just this repair id")
    ap.add_argument("--restrip", action="store_true",
                    help="re-derive ocr_text through the current "
                         "_strip_axis_ladders instead of running the token table")
    args = ap.parse_args()

    stamp = dt.datetime.now(dt.UTC).isoformat()

    if args.restrip:
        total = run_restrip(args.apply, stamp)
        if args.apply:
            print(f"\n{total} records re-stripped.")
        return 0

    total = 0
    for rep in REPAIRS:
        if args.only and rep["id"] != args.only:
            continue
        video = rep["scope"]
        print(f"\n=== {rep['id']}: {rep['wrong']} -> {rep['right']}  in {video}")
        ok, why = video_complete(video)
        if not ok:
            print(f"  SKIPPED -- extraction not complete ({why}). This tool never "
                  f"edits a file\n  the extractor may still be appending to.")
            continue
        print(f"  extraction complete: {why}")

        f = VISUAL / video / "visual_records.jsonl"
        lines = f.read_text().splitlines()
        out, changes = [], []
        for ln in lines:
            if not ln.strip():
                out.append(ln)
                continue
            rec = json.loads(ln)
            rec, ch = apply_to_record(rec, rep["wrong"], rep["right"])
            if ch:
                changes.append(ch)
            out.append(json.dumps(rec, ensure_ascii=False))

        print(f"  records affected  {len(changes)}")
        print(f"  substitutions     {sum(c['substitutions'] for c in changes)}")
        if changes:
            print("  states            "
                  + ", ".join(c["id"].split("#")[-1] for c in changes))
        if not changes:
            print("  nothing to do (already applied, or the token is gone)")
            continue

        if not args.apply:
            print("  DRY RUN -- pass --apply to write.")
            continue

        write_atomic(f, "\n".join(out) + "\n")
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as fh:
            fh.write(json.dumps({"applied_utc": stamp, "repair": rep,
                                 "video": video, "changes": changes},
                                ensure_ascii=False) + "\n")
        total += len(changes)
        print(f"  APPLIED. Logged to {LOG.relative_to(REPO)} "
              f"(before-text kept, so this is reversible).")

    if args.apply:
        print(f"\n{total} records repaired.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
