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
- `.venv/bin/python` (3.14) for repo work. numpy is available; **Pillow is not** — do not import PIL.
- Lint with `uvx ruff check --fix`, never a bare `ruff check`. Line length 100.
- No new dependencies without asking.

## Reporting

- Paste verbatim command output; never summarise a number you were asked to verify.
- State deviations from a spec explicitly; do not silently choose.
- Report the top 3 recurring errors hit during a task so they can be added to this file.
