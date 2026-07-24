#!/usr/bin/env python3
"""
Visual QA: sample extracted keyframes and judge them with the local LM Studio VLM.

Confirms screenshots are readable trading charts rather than black frames,
transitions, blur, or talking-head/webcam shots. Uses only the local VLM — no
cloud calls. Resumable: rerunning skips frames already judged.

Usage
  .venv/bin/python edu/pipeline/visual_qa.py                # 2 frames/video
  .venv/bin/python edu/pipeline/visual_qa.py --per-video 4
  .venv/bin/python edu/pipeline/visual_qa.py --only concept # substring filter
"""

from __future__ import annotations

import argparse
import base64
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

EDU_ROOT = Path(__file__).resolve().parents[1]
DERIVED = EDU_ROOT / "derived"
REPORT = EDU_ROOT.parent / ".scratch" / "visual_qa.json"

URL = "http://localhost:1234/v1/chat/completions"
MODEL = "qwen3-vl-30b-a3b-instruct-mlx"
PROMPT = ("Reply with exactly one word first — USABLE if this is a readable trading "
          "price chart (candles/levels/annotations visible), or BAD if it is a black "
          "frame, transition, blur, or mostly a person's face/webcam. Then a colon "
          "and a short reason.")


def vlm(img: Path) -> str:
    b64 = base64.b64encode(img.read_bytes()).decode()
    for attempt in range(2):
        try:
            r = requests.post(URL, json={"model": MODEL, "messages": [{"role": "user",
                "content": [{"type": "text", "text": PROMPT},
                            {"type": "image_url",
                             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
                "temperature": 0, "max_tokens": 60}, timeout=90)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:  # noqa: BLE001
            if attempt == 1:
                return f"ERROR: {str(exc)[:80]}"
            time.sleep(3)
    return "ERROR: unreachable"


def verdict_of(reply: str) -> str:
    if reply.startswith("ERROR"):
        return "ERROR"
    return "BAD" if reply.upper().lstrip().startswith("BAD") else "USABLE"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-video", type=int, default=2,
                    help="how many frames to sample per video (default 2)")
    ap.add_argument("--only", help="substring filter on video_id")
    args = ap.parse_args()

    dataset = DERIVED / "dataset.jsonl"
    if not dataset.exists():
        print(f"no dataset at {dataset}; run extract_video_knowledge.py first")
        return 1

    rows = [json.loads(l) for l in dataset.read_text().splitlines() if l.strip()]
    by_vid: dict[str, list] = defaultdict(list)
    for r in rows:
        if args.only and args.only.lower() not in r["video_id"].lower():
            continue
        by_vid[r["video_id"]].append(r)

    # evenly spaced frames per video, preferring LLM-selected moments
    sample = []
    n = max(1, args.per_video)
    for items in by_vid.values():
        items.sort(key=lambda x: x["t"])
        pool = [x for x in items if x["source"] == "llm"] or items
        for k in range(n):
            frac = (k + 0.5) / n
            sample.append(pool[min(int(len(pool) * frac), len(pool) - 1)])

    prev = json.loads(REPORT.read_text()) if REPORT.exists() else {"results": [], "done": []}
    done = set(prev["done"])
    results = prev["results"]
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    for i, r in enumerate(sample, 1):
        if r["image"] in done:
            continue
        reply = vlm(DERIVED / r["image"])
        v = verdict_of(reply)
        results.append({"video_id": r["video_id"], "hms": r["hms"],
                        "source": r["source"], "image": r["image"],
                        "verdict": v, "reply": reply})
        done.add(r["image"])
        REPORT.write_text(json.dumps({"results": results, "done": sorted(done)}, indent=2))
        print(f"[{i}/{len(sample)}] {v:7} {r['video_id'][:44]:44} {r['hms']}", flush=True)

    c = Counter(x["verdict"] for x in results)
    print(f"\n=== VISUAL QA: {len(results)} frames | "
          f"USABLE={c['USABLE']} BAD={c['BAD']} ERROR={c['ERROR']} ===")
    for x in results:
        if x["verdict"] != "USABLE":
            print(f"  {x['verdict']} {x['video_id']} {x['hms']} :: "
                  f"{x['reply'][:70]} :: {x['image']}")
    print(f"\nreport: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
