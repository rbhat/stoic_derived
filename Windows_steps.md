# Windows Steps

Use WSL 2 with Ubuntu for the portable Windows work. Keep the repository inside
the WSL filesystem (for example `~/dev/stoic_derived`), not under `/mnt/c`, for
faster file operations.

## 1. One-time WSL setup

If WSL is not installed, open PowerShell as Administrator:

```powershell
wsl --install
```

Restart Windows when prompted, open Ubuntu, and finish the initial user setup.
Then install Git, `curl`, and `uv` from the Ubuntu shell:

```bash
sudo apt update
sudo apt install -y git curl
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv --version
```

## 2. Get the repository

For a new checkout:

```bash
mkdir -p ~/dev
cd ~/dev
git clone git@github.com:rbhat/stoic_derived.git
cd stoic_derived
```

For an existing checkout:

```bash
cd ~/dev/stoic_derived
git checkout main
git pull --ff-only origin main
```

Confirm that the SP0 milestone (`0cbfeab`) or a newer commit is present:

```bash
git log -1 --oneline
git status --short --branch
```

## 3. Install the locked environment

`uv` installs the pinned Python version and locked dependencies:

```bash
uv sync --group dev
```

Do not copy `.env`, approval private keys, Databento credentials, or other
secrets into the repository.

## 4. Run the portable SP0 checks

```bash
uv run pytest -q
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
uv lock --check
uv run stoic-rulebook validate strategy/rulebook.yaml --skip-source-verification
uv run stoic-rulebook render strategy/rulebook.yaml --check strategy/RULEBOOK.md
```

Expected result:

- all tests pass (the suite grows as roadmap milestones land);
- formatting, lint, typing, lock, and dossier drift checks pass;
- rulebook validation says `valid` and `readiness: BLOCKED`;
- blockers are expected because exact strategy rules and human approval are not
  yet complete.

`--skip-source-verification` is appropriate when the large education files have
not been synced to Windows. If the complete `edu/` source corpus is available,
also run strict source verification:

```bash
uv run stoic-rulebook validate strategy/rulebook.yaml
```

## 5. Report the result

Capture the verification output without changing tracked files:

```bash
mkdir -p .scratch/windows
uv run pytest -q 2>&1 | tee .scratch/windows/sp0-pytest.txt
uv run stoic-rulebook validate strategy/rulebook.yaml --skip-source-verification \
  2>&1 | tee .scratch/windows/sp0-rulebook.txt
git status --short --branch
```

The CUDA fine-tuning package is a later, offline research task. It is not part
of this SP0 verification and does not gate deterministic live signals.

## 6. Run the portable SP1 checks

After the SP1 milestone is announced and pushed:

```bash
cd ~/dev/stoic_derived
git checkout main
git pull --ff-only origin main
uv sync --group dev
uv run pytest -q
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
uv lock --check
```

These checks use fakes and require neither a Databento key nor local DBN files.
Expected result: every command passes.

If the small NQ tail DBN has also been copied into `data/historical/`, run:

```bash
mkdir -p .scratch/windows
TAIL_FILE='data/historical/GLBX.MDP3__NQ__2026-06-06__2026-06-10T16:45:00.trades.dbn.zst'
CALENDAR='config/market_data/calendars/cme-equity-index-2026-06-tail-v1.json'

uv run stoic-data inspect "$TAIL_FILE"
uv run stoic-data sample "$TAIL_FILE" \
  --records 10000 \
  --calendar-manifest "$CALENDAR" \
  > .scratch/windows/sp1-sample.json
```

The sample should report 10,000 events, all six timeframes, no issues, and six
degraded final bars because the bounded sample intentionally ends inside open
intervals. Do not copy a Databento API key into the repository.
