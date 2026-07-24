# SP0 - Strategy Rulebook Implementation Plan

## Milestone

Deliver a source-cited candidate rulebook, deterministic validation/publishing
tooling, generated review dossier, and fitness tests. Do not publish executable
strategy rules until exact entry, stop, target, and confidence choices receive
human validation.

## Task 1 - Record architecture decisions `[portable]`

Files:

- `docs/architecture/adr/0001-rulebook-authoring-and-release.md`
- `docs/architecture/adr/0002-content-addressed-human-approval.md`
- `docs/architecture/adr/0003-bounded-rule-expression-language.md`
- `docs/architecture/adr/0004-strategy-source-authority.md`

Verification:

- decisions state context, trade-off, consequences, and automated compliance;
- boundaries agree with VISION and the system roadmap.

## Task 2 - Author the candidate rulebook `[mac-metal]`

Files:

- `strategy/rulebook.yaml`

Work:

- register primary source evidence with timestamps/pages and SHA-256 digests;
- codify fixed scope and timeframe maps;
- capture explicit qualitative rules without adding thresholds;
- list ambiguities, conflicts, and human decisions needed for publication;
- mark every incomplete live capability as candidate or unknown.

Verification:

- every rule references evidence;
- no non-NQ/ES runtime applicability;
- no model output is normative evidence;
- no exact strategy parameter is inferred.

## Task 3 - Build validation and publication tooling `[portable]`

Files:

- `pyproject.toml`
- `.python-version`
- `src/stoic_derived/__init__.py`
- `src/stoic_derived/strategy/__init__.py`
- `src/stoic_derived/strategy/rulebook.py`
- `src/stoic_derived/strategy/cli.py`

Work:

- strict YAML loading with duplicate-key rejection;
- structural, referential, scope, provenance, semantic, and approval checks;
- stable rulebook digest excluding the approval envelope;
- domain-separated Ed25519 approval verification against a separately pinned
  public key;
- deterministic Markdown review projection;
- canonical JSON publication that fails closed unless live-ready;
- CLI commands: `validate`, `render`, `publish`, `digest`.

Verification:

- two renders and two compilations are byte-identical;
- current candidate validates but is not live-ready;
- `publish` exits nonzero and creates no release for the current candidate.

## Task 4 - Add executable fitness tests `[portable]`

Files:

- `tests/strategy/test_rulebook.py`
- `tests/strategy/fixtures/complete_rulebook.yaml`

Test list:

- repository candidate validates and reports all required blockers;
- fixed instruments/timeframes cannot drift;
- duplicate keys fail;
- missing and stale evidence fails;
- stale or missing approval fails publication;
- unsigned approval, invalid signature, and wrong approver key fail publication
  and release loading;
- unsupported operator, lookahead, execution action, and model dependency fail;
- incomplete signal fields fail publication;
- complete approved fixture publishes canonical JSON;
- generated Markdown is deterministic;
- SP3/backtest input is rejected from publication fields.

Verification:

```bash
uv run pytest
uv run ruff check src tests
uv run mypy src
uv run stoic-rulebook validate strategy/rulebook.yaml
uv run stoic-rulebook render strategy/rulebook.yaml --check strategy/RULEBOOK.md
```

## Task 5 - Audit and milestone delivery `[portable]`

Audit:

- inspect tests first, then tooling, then rulebook content in chunks below 400
  lines;
- recheck VISION guardrails and unresolved strategy claims;
- confirm `VISION.md` is excluded from the commit;
- confirm no secrets, media, data, or scratch output are staged.

Delivery:

- commit one coherent SP0 milestone using a Conventional Commit;
- push to the configured upstream;
- report that SP0 infrastructure is complete while live rule publication remains
  truthfully blocked on human strategy validation.
