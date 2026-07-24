# SP5 - Static Operations Dashboard and Control API Implementation Plan

## Milestone

Deliver an accessible React 19/Vite static SPA and a secure FastAPI JSON/control
API over the verified SP4 boundary while current production truthfully remains
blocked and empty.

## Task 1 - Typed dashboard contracts and exact projection `[portable]`

Files:

- `src/stoic_derived/dashboard/models.py`
- `src/stoic_derived/dashboard/projection.py`
- `tests/dashboard/test_projection.py`

Define versioned Pydantic request/response contracts, ready/blocked/error state,
open/closed/unresolved projections, exact direction-aware tick P/L, rational R,
hold duration, UTC serialization, terminal reasons, conflicts, and bounded
collections. Compose release readiness before verified Drive plus only
undelivered outbox events.

## Task 2 - Exact SQLite identity, session, and audit store `[portable]`

Files:

- `src/stoic_derived/dashboard/store.py`
- `tests/dashboard/test_store.py`

Implement strict schema/version/DDL/trigger verification, immutable primary
admin bootstrap, invite/sub binding, opaque session digest storage, immediate
revocation, current-role lookup, connection state, bounded key-rotation
workflows, append-only hash-chained audit evidence, transactional mutations,
and fail-closed limits.

## Task 3 - Google authentication and authorization dependencies `[portable]`

Files:

- `src/stoic_derived/dashboard/auth.py`
- `src/stoic_derived/dashboard/settings.py`
- `tests/dashboard/test_auth.py`

Implement GIS form CSRF comparison, official ID-token verification with Web
Client ID audience, Google issuer/expiry/sub/email checks, authoritative
Gmail/Workspace policy, invite binding, secure cookie issuance, session and
admin dependencies, synchronizer CSRF, origin validation, sanitized failures,
and environment-only production configuration.

## Task 4 - Operations and constrained control services `[portable]`

Files:

- `src/stoic_derived/dashboard/operations.py`
- `tests/dashboard/test_api.py`

Implement truthful API/release/Drive/market/outbox/watchdog status, bounded
read-only connection probes, Drive refresh, verified outbox publication, and
secret-free Databento rotation request/verify/cancel workflows. Audit intent
before external operations and completion/failure afterward.

## Task 5 - FastAPI JSON/control API and CLI `[portable]`

Files:

- `src/stoic_derived/dashboard/app.py`
- `src/stoic_derived/dashboard/cli.py`
- `src/stoic_derived/dashboard/__init__.py`
- `tests/dashboard/test_api.py`
- `tests/dashboard/test_boundaries.py`
- `pyproject.toml`

Build an application factory and lifespan-owned dependencies. Expose only the
accepted `/api/v1` routes, explicit response models, bounded bodies, trusted
hosts, secure headers, no HTML/template/static serving, and a secret-free
readiness CLI. Test every role/mutation/CSRF/session/login/OpenAPI boundary.

## Task 6 - React 19 SPA contract and session shell `[portable]`

Files:

- `web/package.json`
- `web/package-lock.json`
- `web/tsconfig*.json`
- `web/vite.config.ts`
- `web/src/api.ts`
- `web/src/schemas.ts`
- `web/src/App.tsx`
- `web/src/main.tsx`
- `web/src/test/*`

Create the strict Vite SPA, same-origin fetch wrapper, Zod decoding for every
response, discriminated application states, GIS redirect login, in-memory CSRF
handling, session reload, logout, viewer/admin navigation, and contract-error
recovery.

## Task 7 - Pacific session console UI `[portable]`

Files:

- `web/src/components/*`
- `web/src/styles.css`
- `web/src/**/*.test.tsx`

Implement the 13:58 Pacific chronology rail, operational evidence strip,
separate open/closed charts and semantic tables, unresolved evidence section,
exact ticks/R/hold time, Pacific timestamps with UTC details, management
workflows, user management, and audit trail. Include keyboard-first behavior,
focus visibility, reduced motion, chart text equivalents, responsive tables,
and test-only realistic API data.

## Task 8 - Full verification and independent audit `[portable]`

Verification:

```bash
uv run pytest -q tests/dashboard
uv run pytest -q
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
uv lock --check
uv run stoic-dashboard readiness
uv build
npm --prefix web ci
npm --prefix web run typecheck
npm --prefix web run test
npm --prefix web run build
npm --prefix web run e2e
npm --prefix web audit --audit-level=high
git diff --check
```

Run desktop and mobile screenshots, keyboard navigation, console/network
checks, responsive verification, and Lighthouse accessibility. Run a separate
Terra audit across authentication, authorization, primary-admin invariants,
CSRF, session fixation/revocation, SQL/IDOR, audit append-only behavior, Drive
authority, P/L semantics, forbidden SSR/fixtures/execution, accessibility, and
supply chain. Fix every material finding, record the final audit, commit one
coherent SP5 milestone, and push `main`.
