# coding_rules.md

Rules learned from real failures in this repo. Apply them before writing code; add to them when a
subagent reports a new recurring error. Bullets only — no explanations, no history.

## Atomic writes

- `np.save(path, arr)` appends `.npy` to any path not already ending in `.npy` — atomic tmp paths
  like `x.npy.tmp` silently become `x.npy.tmp.npy` and the `os.replace` then fails. Pass an open
  file handle instead: `with open(tmp, "wb") as fh: np.save(fh, arr)`.
- Write to `<target>.tmp` then `os.replace(tmp, target)` for every artifact a run produces.
- Never leave a partially written file at the real path on crash or kill.

## Subprocess and ffmpeg

- ffmpeg infers the output container from the file extension; a temp name like `out.jpg.tmp` fails
  with "Unable to choose an output format". Pass the muxer explicitly (`-f image2`, `-f rawvideo`).
- Always `subprocess.run([...])` with a list, never a shell string — source filenames contain
  spaces and `·`.
- Check `returncode` and surface `stderr` in the raised message.

## Resumability

- Gate a stage on **disk state, not just a status flag**. A stage marked `done` whose outputs were
  deleted must be re-entered and reconcile only the missing pieces.
- Resume granularity is the unit of work (per frame, per file), not per stage.
- A `running` stage with a stale heartbeat is dead — redo it.
- Rewrite the manifest after every stage so a killed run is fully inspectable.
- Log elapsed and ETA per unit; compute throughput only from work done in the current run, and
  exclude already-completed work from both numerator and denominator.

## Artifacts and environment

- All run artifacts under `<repo>/.artifacts/`; scratch under `<repo>/.scratch/`. Never `~`, never
  system temp, never another drive. Env-var override is the only sanctioned relocation.
- Model weight caches too — pass `download_root=` (faster-whisper) rather than letting a library
  default to `~/.cache`.
- `.venv/bin/python` (3.14) for repo work. numpy is available; **Pillow is not** — do not import PIL.
- A script importing a repo-root package needs `sys.path.insert(0, parents[1])` before that import:
  `python scripts/foo.py` puts only `scripts/` on the path, and `[tool.uv] package = false` means
  nothing is installed to fall back on. pytest works via `pythonpath` config; the script does not.
- Declare what you import. `pandas`, `pyarrow` and `databento` were imported by tracked code for
  days without being in `pyproject.toml`; a clean `uv sync` would have broken it.
- Lint with `uvx ruff check --fix`, never a bare `ruff check`. Line length 100.
- No new dependencies without asking.

## Timestamps

- Never add `Timedelta(days=1)` to a **tz-aware** timestamp to mean "the next calendar date" — it
  adds 24h of absolute time, and the DST fall-back day is 25h, so it lands on the same date. Strip
  the zone (`.tz_localize(None)`), shift, then take `.date`.
- Adding a duration to a **UTC** timestamp is safe; UTC has no DST. The bug class is local zones only.
- A local-time bug that only appears in November is DST arithmetic, not bad data.

## Checks and gates

- Every gate needs a **negative control**: inject the fault it exists to catch and confirm it fails.
  A check never observed failing is not evidence of anything.
- Gate the function that **derives** a value, not only the functions that consume it. A DST gate that
  exercised every consumer of `session_date()` and never `session_date()` itself passed a bug that
  corrupted 14 daily bars.
- Ask whether a reported number is **possible** before asking whether it looks reasonable. An
  impossible count is the cheapest bug detector there is.
- Classify an anomaly by evidence, not by the nearest plausible story. A gap with price frozen to
  the penny is a limit halt; a gap with price moved across it is missing data. Naming it wrongly
  turns a defect into a passing "named exception".
- `min()` over `(distance, tiebreak, …)` tuples resolves ties by the later fields — do not report
  that as an argmin. Where ties are expected, ask a membership question ("is x among the minima?"),
  not a positional one.
- A relative comparison inside a small window cannot see a gross error; pair it with an absolute
  bound.
- Stratify before gating. One threshold over a mixed population either gates on the wrong subgroup
  or has to be loosened until it gates on nothing.

## Reporting

- Paste verbatim command output; never summarise a number you were asked to verify.
- State deviations from a spec explicitly; do not silently choose.
- Never quote an **extrapolated** number where a **measured** one now exists, and label which is
  which at the point of use — estimates outlive the moment they were needed.
- Report the top 3 recurring errors hit during a task so they can be added to this file.
