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

- 56 tests pass;
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
