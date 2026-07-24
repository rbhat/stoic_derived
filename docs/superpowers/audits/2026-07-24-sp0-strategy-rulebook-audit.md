# SP0 - Strategy Rulebook Audit

- Date: 2026-07-24
- Milestone result: **PASS**
- Live publication result: **BLOCKED AS DESIGNED**

## Outcome

SP0 delivers the candidate rulebook, source provenance, generated review
dossier, strict validation, authenticated publication boundary, and release
loader required to keep unvalidated strategy content out of the live signal
path.

The current rulebook is intentionally not executable. Exact B&R/SFP predicates,
entry-model selection, entry/stop/target construction, session policy, and
confidence parameters remain unresolved and require source review plus human
approval. No release artifact was produced.

## Review Scope

The audit reviewed tests first, followed by the validator/publisher, CLI,
candidate rulebook, generated dossier, design, plan, and ADRs. Source files were
reviewed in chunks below 400 lines.

Primary media/transcript locators were checked for each normative claim.
Illustrative NQ and ES PDF pages were rendered and visually inspected; they
remain non-normative. Every cited local asset is SHA-256 pinned.

## Vision Alignment

- Runtime scope is exactly NQ and ES.
- All four timeframe maps match `VISION.md`.
- The artifact produces signals only and contains no execution or broker action.
- Models, prompts, network calls, backtests, and training outputs are excluded
  from the release grammar and live loader.
- Strategy research cannot alter live rules without a fresh digest-bound human
  Ed25519 approval verified against an externally pinned public key.
- Backtesting remains a parallel measurement path and does not tune, publish,
  or gate the live strategy.
- `VISION.md` is unchanged.

## Adversarial Findings Resolved

- Forged or hand-edited release JSON is rejected by canonical hash, provenance,
  source digest, compiler, schema, approval, scope, and readiness checks.
- Executable predicates and signal operands use closed schemas with
  unknown-key rejection, finite constants, bounded lookbacks, and no future-bar
  access.
- Media evidence requires its transcript and both source hashes; CLI validation
  verifies sources by default.
- Approval timestamps require UTC `Z`, signatures use a domain-separated
  message, and any semantic edit invalidates approval.
- Entry, stop, and target are dynamic closed operands; price operands are OHLC
  only, literal prices must be positive exact 0.25-point ticks, and each
  direction has an orientation guard.
- Every validated profile requires an allowlisted entry model.
- A stale approval digest blocks readiness and the dossier cannot describe such
  a candidate as pending publication.

## Verification

The final verification produced:

- `uv run pytest -q`: 56 passed
- `uv run ruff format --check src tests`: passed
- `uv run ruff check src tests`: passed
- `uv run mypy src`: passed
- `uv lock --check`: passed
- strict and structural candidate validation: valid and correctly blocked
- generated Markdown drift check: passed
- education pipeline QA: 16 videos and 2,233 dataset rows, all clean
- `git diff --check`: passed
- release hygiene: no `strategy/releases/` directory or candidate release file

Independent implementation testing and two architecture/security audit passes
found no remaining concrete SP0 defects.

## Open Items

Human strategy validation remains the only path to an executable release. The
generated dossier lists every unresolved decision and source conflict.

Full-repository Ruff currently reports 20 pre-existing violations in
`edu/pipeline/`; the SP0-owned `src/` and `tests/` scopes are clean. That legacy
debt does not affect this milestone.
