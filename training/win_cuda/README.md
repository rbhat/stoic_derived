# win_cuda — Windows/WSL QLoRA training package

Reproducible fine-tuning environment for the offline research-assistant SLM.
The model this package trains **proposes cited rule candidates for human
review only** — its output never touches the live signal path (VISION.md).

Runs on WSL2 Ubuntu with an NVIDIA Blackwell GPU (RTX 5070 Ti, 16 GB,
sm_120). CUDA pins live entirely in this subproject's `pyproject.toml` +
`uv.lock`; the repo's portable dev environment must never gain CUDA deps.

## Layout rule: everything relative to the repo

All run artifacts live under the repo working directory in the git-ignored
`.artifacts/` folder (user directive 2026-07-24 — artifacts stay next to
the work, never in `~`, system temp, or another drive; the WSL VHD sits on
the nearly-full C: while the repo drive has room to spare). Default
`STOIC_TRAIN_HOME` is `<repo>/.artifacts/training/`:

```
<repo>/.artifacts/training/
  venv/          # uv project environment (UV_PROJECT_ENVIRONMENT)
  hf/            # HuggingFace cache (HF_HOME, auto-set by config.py)
  datasets/      # built SFT datasets (train/eval jsonl + digest manifest)
  runs/          # checkpoints + run manifests + train.log/progress.json
  exports/       # merged safetensors + GGUF (~25 GB per export)
  logs/          # bootstrap logs from detached launches
  llama.cpp/     # shallow clone, used only for GGUF conversion
```

Accepted trade-off: drvfs I/O on `/mnt/f` is slower than ext4 for
many-small-file workloads (venv, HF cache) and checkpoint saves. Trainer
checkpoints land under `$STOIC_TRAIN_HOME/runs/<run_id>/checkpoint/` with
the final adapter in `checkpoint/final/` — that is the dir to pass to
`export.py --checkpoint`.

## Environment variables

None are required: `STOIC_TRAIN_HOME` defaults to
`<repo>/.artifacts/training` and `config.py` auto-points `HF_HOME` at
`$STOIC_TRAIN_HOME/hf` unless you already set it. To keep the venv in the
same tree, export (per-shell or in `~/.bashrc`):

```bash
export UV_PROJECT_ENVIRONMENT="/mnt/f/dev/stoic_derived/.artifacts/training/venv"
```

Only set `STOIC_TRAIN_HOME` explicitly to relocate the whole artifact tree.
If your `~/.bashrc` still exports the old `~/stoic-training` values from an
earlier revision of this README, remove them.

## Setup

```bash
cd training/win_cuda
uv sync --all-groups     # installs torch cu128 + bitsandbytes into $UV_PROJECT_ENVIRONMENT
uv run pytest            # GPU smoke tests run on this box; skip cleanly elsewhere
```

The pin set is Blackwell-verified: torch built for cu128 with sm_120 kernels,
bitsandbytes with 4-bit (nf4) support on sm_120. Do not bump these pins
without re-running `tests/test_gpu_smoke.py` on the GPU box.

## Commands

```bash
uv run python -m stoic_training.build_dataset   # dataset.jsonl -> SFT pairs + digest (frozen split in splits/)
uv run python -m stoic_training.train           # QLoRA SFT, seeded, resumable
uv run python -m stoic_training.evaluate        # citation fidelity + failure buckets + conflict surfacing
uv run python -m stoic_training.compare A B     # run-over-run deltas, paired flips, McNemar p
uv run python -m stoic_training.calibrate ...   # human calibration audit of the Tier-1 proxy
uv run python -m stoic_training.infer           # offline inference against a local checkpoint
uv run python -m stoic_training.export          # merge LoRA -> safetensors -> GGUF (LM Studio)
```

Every run writes a content-addressed manifest (dataset digest, code rev,
config hash, base-model revision, outputs) under `$STOIC_TRAIN_HOME/runs/`.

## Evaluation, comparison, and the runs index

See `docs/superpowers/specs/2026-07-24-eval-comparison-design.md` for the
rationale. The short version: a score is only meaningful next to another
score computed the same way, so every evaluation records exactly what it was
computed against.

### Per-run evaluation artifacts

With `--run-dir <run_dir>`, evaluation artifacts land **inside the run**:

```
$STOIC_TRAIN_HOME/runs/<run_id>/
  manifest.json           # gains an "evaluation" section (below)
  evaluation/
    predictions.jsonl     # one row per eval example, with a stable example_id
    scores.json           # metrics + failure buckets + scoring provenance
```

They used to land in `datasets/v1/` and were clobbered by every run — that
bug is what this layout fixes. Without `--run-dir`, ad-hoc scoring still
writes `scores.json` next to the predictions file as before.

The manifest's `evaluation` section records the scores/predictions paths and
sha256s, headline metrics + bucket counts, `scoring_version`, the scoring
params, the corpus digest, and the eval-set digest. **`run_id` never changes**
— it derives only from the identity fields fixed when the manifest was
created.

### Metrics: headline rates plus failure buckets

`scores.json` reports `citation_fidelity` and `conflict_handling` overall,
per-task, and per-category, and additionally classifies every prediction into
exactly one failure bucket. For citation-scored tasks (`rule_candidate`,
`cited_qa`), checked schema-first:

| bucket | meaning |
|---|---|
| `schema_violation` | Tier-0 structure missing (rule_candidate's labelled lines; an empty body) |
| `no_citation` | no well-formed trailing `Citation: <video_id> HH:MM:SS` line |
| `citation_not_in_corpus` | cited record does not exist — the hallucination bucket |
| `weak_overlap` | citation is real but the body does not support it at the threshold |
| `pass` | — |

`conflict_check` has its own namespace: `insufficient_citations`,
`no_conflict_marker`, `pass`. A run that improves the headline while growing
`citation_not_in_corpus` is a regression by definition (design §7).

`scoring_version` (currently `"1"`) is stamped into every `scores.json`
alongside the params. Changing how scoring works means bumping it, which
starts a new comparison lineage — `compare` refuses across versions rather
than silently comparing incomparable numbers.

### Stable example ids

Every prediction row and every `scores.json` details entry carries
`example_id = sha256("task=…\x1fvideo_id=…\x1fhms=…\x1fprompt=…")[:16]`
(`\x1f` = ASCII unit separator, which cannot occur in those fields). This is
what makes *paired* comparison possible: the same eval example is
identifiable across runs even though the generated text differs.

### Pre-registering a hypothesis

```bash
uv run python -m stoic_training.train --hypothesis "1 epoch instead of 2 will cut hallucinated citations"
```

Written into the manifest **before launch**. A run whose gain wasn't
predicted is a lead, not a result. `evaluate.py` also accepts `--hypothesis`
(for evaluation-only runs such as baselines); if the manifest already has a
different one it keeps the original and warns — pre-registration you can
rewrite afterwards is worthless.

### Baseline: the zero point

Without the un-fine-tuned base model's score we cannot claim the fine-tune
helps at all. Baseline mode loads the pinned base model with the **same
4-bit nf4 quantization** as the adapter path (an 8B bf16 model does not fit
this box's 16 GB shared VRAM) and no adapter:

```bash
cd /mnt/f/dev/stoic_derived/training/win_cuda
nohup uv run python -m stoic_training.evaluate --baseline \
    --base-repo-id Qwen/Qwen3-8B \
    --base-revision b968826d9c46dd6066d109eabc6255188de91218 \
    --eval-jsonl ../../.artifacts/training/datasets/v1/eval.jsonl \
    --hypothesis "base model cites almost nothing verifiable" \
  >> ../../.artifacts/training/logs/baseline-$(date +%Y%m%dT%H%M%S).log 2>&1 &
```

It creates its own run dir `runs/baseline-<digest>/`, where the digest is
derived from the eval-set digest + `scoring_version` + base-model revision —
so re-running the same baseline is idempotent, and a changed eval set or
scoring version gets a new baseline rather than overwriting the old one.
Manifest fields that do not apply (training config, dataset ref,
checkpoints) are explicitly null with a `notes` field explaining why.

### Comparing two runs

```bash
uv run python -m stoic_training.compare <run_a> <run_b>          # run ids under $STOIC_TRAIN_HOME/runs
uv run python -m stoic_training.compare <run_dir_a> <run_dir_b>  # or paths
uv run python -m stoic_training.compare A B --json               # machine-readable
```

Prints headline deltas, per-task deltas, per-bucket count/rate deltas, and
the **paired flips**: how many examples went fail→pass (`fixed`), pass→fail
(`broke`), and a McNemar exact p-value — because on 699 examples an
aggregate +3% is noise, while "fixed 41, broke 6" is signal. The flipped
example ids are listed both ways so regressions are inspectable one by one.

`compare` **refuses** (exit 2) unless the corpus digest, eval-set digest, and
`scoring_version` all match. Exit 1 covers IO/usage problems, 0 on success.
Pure stdlib — it runs off the GPU box with nothing loaded.

### Runs index

`$STOIC_TRAIN_HOME/runs/index.jsonl` is the experiment history: one
append-only JSON line per completed evaluation, written by the `--run-dir`
path. Each line carries `run_id`, `date`, `config_sha256`, `knob_diff` (the
resolved-config keys that changed since the previous line), `hypothesis`,
`metrics` (headline + bucket counts), `scoring_version`, `eval_set_sha256`,
and `corpus_sha256`. It is never rewritten, so a crash can't corrupt history
that already landed.

```bash
tail -3 ../../.artifacts/training/runs/index.jsonl | python3 -m json.tool --json-lines
```

## Split protocol v2: dev, sealed holdout, quarantine

Runs are blind to eval data — but *we* are not. Reading a score and picking
the next change because it raised that score leaks information about the
fixed eval sample through our choices (design §5.1). After ~20 such
iterations against ±3% noise you can "gain" 5–10% that generalizes to
nothing. The countermeasure is two eval tiers.

### The split files

`splits/split-v1.json` is immutable and unchanged: 13 train videos, 3 eval
videos (seed 20260724, one per category). `splits/split-v2.json` **does not
re-split anything** — it names v1 as its parent and only subdivides v1's
eval videos:

| tier | videos | use |
|---|---|---|
| train | v1's 13, read from the parent file at build time | training |
| dev | `cs_vol3_gold_futures_study`, `live_4_14r_on_nq` | read every run, iterate freely |
| holdout | `concept_simple_stoic_setups_sss` | **sealed** — release candidates only |

The 2 dev / 1 holdout assignment is seeded-deterministic (seed 20260725):
sort the parent's eval videos, shuffle with `random.Random(f"{seed}:v2")`,
take the first `round(n/3)` (min 1, cap n−1) as holdout. The procedure is
written into the file itself and reproducible via
`splits.partition_eval_videos`; a test asserts the committed file still
matches it. Tooling refuses any v2 whose dev+holdout is not *exactly* the
parent's eval set, so a v2 can never promote an eval video into training.

**Known coarseness, accepted (design §5.3):** with one eval video per
category a 2/1 partition cannot be stratified — dev here covers case_study +
live_session and holdout covers concept only, so dev-vs-holdout differences
confound "sealed vs not" with "concept vs the rest". One holdout video also
means wide error bars. Use the holdout as a release-candidate sanity check,
never as a precise number. The fix is more mined videos, not a cleverer
partition of three. Within-video splits remain banned outright.

### Building `datasets/v2/`

The split version is auto-detected from the `--split` file's contents, and
the dataset dir is named after it, so v1 and v2 can never overwrite each
other:

```bash
uv run python -m stoic_training.build_dataset --split splits/split-v2.json
# -> $STOIC_TRAIN_HOME/datasets/v2/{train.jsonl,eval_dev.jsonl,eval_holdout.jsonl,dataset_manifest.json}
```

`train.jsonl` is **byte-identical to v1's** — subdividing the eval set must
not change what the model trains on. The v2 `dataset_manifest.json` records
a per-file `sha256` and `role` (`train`/`dev`/`holdout`); that digest+role
pair is what the unseal guard matches on. (A conflict_check pair straddling
dev and holdout is dropped from both, exactly as v1 drops train/eval-
straddling pairs — keeping it would put holdout narration into the dev set.)

### The holdout seal and the unseal ledger

`evaluate.py` **refuses (exit 2)** to score a holdout eval set:

```
error: refusing to score a SEALED HOLDOUT eval set: .../datasets/v2/eval_holdout.jsonl
```

Two independent detectors, either of which seals a file:

1. **content sha256** — the file's digest matches a `role: "holdout"` entry
   in the `dataset_manifest.json` sitting next to it. Renaming the file
   changes nothing; the bytes are the same.
2. **filename backstop** — the stem is `eval_holdout`, even with no manifest
   beside it. This catches copying the file somewhere else and leaving the
   manifest behind.

Neither fires for an ad-hoc file, so hand-made eval/predictions files score
with no friction. To proceed deliberately:

```bash
uv run python -m stoic_training.evaluate --run-dir <run_dir> \
    --checkpoint <checkpoint> \
    --eval-jsonl ../../.artifacts/training/datasets/v2/eval_holdout.jsonl \
    --unseal "scoring release candidate rc1 before rulebook handoff"
```

That appends one row — run id, ISO date, eval-set path, reason — to the
committed `splits/unseal-ledger.md`, **after** the holdout has actually been
scored (a crashed attempt disclosed nothing and must not consume budget).
The ledger is append-only. **Budget: single-digit unsealings per split
version.** If the count approaches ten the holdout is consumed: retire it
and cut a new split version rather than pretending the number generalizes.

### New-video quarantine

Newly mined videos are the truly-unseen future, so they are **quarantined
into the holdout pool** (design §5.2) — never silently into train or dev,
and never silently dropped. Split files are immutable, so the enforcement
point is the builder:

```bash
# a corpus that gained videos no longer matches the split's corpus_sha256:
uv run python -m stoic_training.build_dataset --split splits/split-v2.json
# error: corpus_sha256 mismatch ... re-run with --allow-corpus-drift

uv run python -m stoic_training.build_dataset --split splits/split-v2.json --allow-corpus-drift
# quarantined into holdout (1 new video(s) not named by the split): <video_id>

uv run python -m stoic_training.build_dataset --split splits/split-v2.json \
    --allow-corpus-drift --on-new-videos fail    # stop instead of quarantining
```

`--allow-corpus-drift` permits the corpus to **grow** only: if a split video
went missing, the build still fails. Quarantined videos are listed in the
build summary and recorded in `dataset_manifest.json`
(`quarantined_videos`, `corpus_drift`).

## Calibration: the metric's measured error bar

Tier 1 scores claim-vs-narration support by token overlap at a fixed
threshold. It is a *biased* proxy — it fails some genuinely-supported
paraphrases and passes some coincidental overlaps. That is tolerable only
because the bias is stable across runs **and quantified** (design §2). The
`calibrate` module quantifies it, turning "the metric is subjective" into
"the metric has a measured 12% false-fail rate".

```bash
# 1. draw a seeded, pass/fail-stratified sample from a scored run
uv run python -m stoic_training.calibrate sample --run-dir <run_dir> --size 50

# 2. label human_label ("supported" / "not_supported" / "unsure") in the
#    sheet JSONL, reading the .md companion beside it

# 3. score the filled sheet into the committed calibration record
uv run python -m stoic_training.calibrate ingest --sheet <sheet>.jsonl
```

`sample` reads `<run_dir>/evaluation/{predictions.jsonl,scores.json}` and
writes `<run_dir>/evaluation/calibration/sheet-<scoring_version>.{jsonl,md}`.
Half the sample is `pass`; the other half is spread **evenly across the
failure buckets that occurred**, not proportionally — a proportional sample
of a 20%-pass run would be nearly all `weak_overlap` and would tell us
nothing about whether the hallucination bucket is correctly identified.
Selection is deterministic for a fixed seed (strata are sorted by
`example_id` before the seeded shuffle).

Each row carries the prediction, the `(video_id, hms)` it cited, and *that
record's* narration/why from the corpus, so support can be judged without
hunting through the corpus. The eval set's gold answer is deliberately **not
included** — it would anchor the judgement it is supposed to be independent
of.

`ingest` treats human `supported` as ground truth and the Tier-1 *pass*
verdict as the prediction under test:

| metric | formula | reading |
|---|---|---|
| `precision` | TP/(TP+FP) | of what Tier-1 passed, how much the human agrees is supported |
| `recall` | TP/(TP+FN) | of what is genuinely supported, how much Tier-1 passed |
| `false_fail_rate` | FN/(TP+FN) | = 1 − recall; the headline error bar of §2 |
| `false_pass_rate` | FP/(FP+TN) | of what is genuinely unsupported, how much Tier-1 let through |
| `agreement` | (TP+TN)/labeled | overall |

`unsure` rows are excluded from every denominator and reported separately —
folding them in either direction would invent a judgement the labeler
explicitly declined to make. Rates with an empty denominator are `null`, not
`0.0`. Per-bucket label counts are recorded too.

The record lands in `evaluation/calibration/<scoring_version>.json`
(committed) with `run_id`, date, sheet path + sha256, sample size, and the
agreement block. `ingest` **refuses to overwrite** an existing record for the
same `scoring_version` without `--force`: that record is the committed error
bar for that metric lineage. If agreement degrades, revise the metric and
bump `SCORING_VERSION` — which starts a new lineage rather than rewriting
the old one.

## Long runs: launch, tail, status

Training, export, and generation-mode evaluation can all run for hours.
Launch them detached so a dropped terminal (SSH drop, closed window) never
kills the run, tail their output live, and poll status without waiting on
the run to finish.

### Detached launch

The run dir (and therefore its `train.log`) is not known until train.py
actually starts, so the detached-launch pattern captures stdout/stderr to a
timestamped **bootstrap log** first:

```bash
cd /mnt/f/dev/stoic_derived/training/win_cuda
mkdir -p ../../.artifacts/training/logs
nohup uv run python -m stoic_training.train --config config/qlora.yaml \
  >> ../../.artifacts/training/logs/train-$(date +%Y%m%dT%H%M%S).log 2>&1 &
```

`setsid uv run python -m stoic_training.train ...` is an equivalent
alternative to `nohup ... &` if you'd rather fully detach from the
controlling terminal's process group. Either way, train.py's first lines of
output print (and log) the run_id, run_dir, and the absolute paths of
`train.log` and `progress.json` -- read the bootstrap log once at startup to
learn exactly what to tail next.

### Tailing

```bash
# raw stdout/stderr from the detached process (crashes, tracebacks, warnings)
tail -f ../../.artifacts/training/logs/<bootstrap-log-name>.log

# structured, human-readable progress lines with a live ETA
tail -f <run_dir>/train.log
```

### Status, without tailing

```bash
uv run python -m stoic_training.status                       # newest run, auto-selected
uv run python -m stoic_training.status --run-id <run_id>
uv run python -m stoic_training.status --run-dir <run_dir>
```

Prints the run dir, a formatted snapshot of `progress.json` (phase, step,
loss, rate, ETA, staleness), and a `tail -f` reminder. Exits 1 with a clear
message (no traceback) if nothing has run yet.

### Watcher discipline (don't self-match, don't wait forever)

Two hard rules for anything (human, agent, or script) that watches a
detached run:

1. **The pgrep self-match trap.** `pgrep -f stoic_training.train` matches
   the watcher's *own shell* whenever the pattern appears in its command
   line, so a `while pgrep ...; do sleep ...; done` loop never exits (this
   cost a real run 2.5 idle hours). Always break self-matching with a
   character class: `pgrep -f "[s]toic_training.train"`.
2. **Liveness is not progress.** Pair every process check with stall
   detection (log mtime / progress.json age) and a crash scan (traceback in
   the newest bootstrap log). "No news" must resolve to RUNNING, STALLED,
   CRASHED, or DONE — never to "keep waiting".

Both rules are packaged in `scripts/health.sh`:

```bash
scripts/health.sh                  # one-shot: status of train/evaluate/export
scripts/health.sh export           # one-shot, single phase
scripts/health.sh --wait export    # block until exit/crash/stall
                                   # exit 0=clean exit, 1=crash, 2=stalled
```

Use `--wait` as the canonical wake-on-event watcher for detached launches
(including from agents): it returns the moment there is something to act
on, with the reason in its last output lines.

### Same pattern for export and evaluate

```bash
nohup uv run python -m stoic_training.export --checkpoint <checkpoint> \
    --base-repo-id Qwen/Qwen3-8B --run-id <run_id> \
  >> ../../.artifacts/training/logs/export-$(date +%Y%m%dT%H%M%S).log 2>&1 &
tail -f <run_dir>/export.log

nohup uv run python -m stoic_training.evaluate --run-dir <run_dir> \
    --checkpoint <checkpoint> --eval-jsonl <path/to/eval.jsonl> \
  >> ../../.artifacts/training/logs/evaluate-$(date +%Y%m%dT%H%M%S).log 2>&1 &
tail -f <run_dir>/evaluate.log
```

`evaluate.py`'s progress log/`progress.json` are opt-in via `--run-dir`, as
are the run-dir evaluation artifacts and the runs-index line (see
"Evaluation, comparison, and the runs index" above); the default scoring-only
invocation (no `--run-dir`) still writes `scores.json` next to the
predictions file.

### Memory guardrails on this box

- The RTX 5070 Ti's 16 GB VRAM is shared with the Windows desktop (~2 GB
  used at idle). `train.py` refuses to start when free VRAM falls below
  `resources.min_free_vram_gib` -- if it refuses, eject any model loaded in
  LM Studio and retry (`--allow-low-vram` overrides this, only when you know
  what else is using the GPU).
- `export.py`'s merge step computes a host-specific memory budget from
  `config.resources.*` and **refuses rather than thrashing the machine**
  when the budget does not fit, instead of the hardcoded
  `max_memory={0:"13GiB","cpu":"10GiB"}` that once hung the whole box and
  required a hard reboot (`--allow-unfit-budget` downgrades that refusal to
  a loud warning; use only if you are certain).
- WSL's RAM/swap ceiling is governed by `/mnt/c/Users/rajee/.wslconfig`.
  Changes there only take effect after running `wsl --shutdown` from
  PowerShell (not just closing the WSL terminal).

## Base model

See `MODEL_CARD.md` for the pinned repo id, revision hash, and license
record. No HF token is required.
