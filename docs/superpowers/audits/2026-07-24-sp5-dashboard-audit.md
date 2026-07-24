# SP5 Static Operations Dashboard and Control API Audit

- Date: 2026-07-24
- Result: PASS; PRODUCTION STRATEGY REMAINS BLOCKED AS DESIGNED
- Scope: React 19/Vite static SPA, FastAPI JSON/control API, Google
  authentication, server-side sessions and authorization, SQLite control
  state, Drive-authoritative projections, operational controls, user
  management, audit evidence, accessibility, and supply chain

## Vision and Application Boundary Review

- `VISION.md` is unchanged and unstaged.
- The production frontend is a compiled client-rendered SPA. FastAPI exposes
  versioned JSON and control routes only; it has no HTML, template, static-file,
  Jinja, SSR, React Server Component, or Next.js application route.
- The dashboard cannot change or optimize strategy, approve SP0, select a
  fixture, place an order, connect to a broker, or claim a fill or execution.
- Every ledger and operation response declares `execution: false` and
  `orders_placed: 0`.
- Exact observational P/L is limited to ticks and rational R. Dollar P/L is
  absent because the signal contract has no position size.
- Production ledger reads compose the real signed-release boundary before
  verified SP4 Drive authority plus only undelivered local outbox events.
  Missing readiness remains blocked with zero observations.

## Authentication, Authorization, and Control-State Review

- Google Identity Services posts the ID-token credential to the backend.
  Login verifies the `g_csrf_token` cookie/body pair, then uses the official
  `google-auth` verifier with the configured Web Client ID audience.
- Claim policy explicitly checks issuer, audience, expiry, bounded non-empty
  `sub`, verified email, and Google-authoritative Gmail or Workspace identity.
  Google `sub` is the durable identity after invite-address bootstrap.
- Sessions are random opaque server-side records. Only the token digest is
  stored; the browser receives a `Secure`, `HttpOnly`, `SameSite=Lax`,
  `__Host-` cookie. Current user, enabled state, and role are resolved from
  SQLite on every protected request.
- Viewer access is read-only and limited to the observational ledger plus
  sanitized operational status. Administration, audit evidence, connection
  tests, Drive mutations, and rotation workflows require an admin. Every
  mutation also requires exact-origin and synchronizer-CSRF validation.
- `rajeevmbhat@gmail.com` is protected as the immutable primary admin by both
  service validation and SQLite constraints/triggers. It cannot be renamed,
  disabled, removed, rebound after binding, or demoted.
- Role, enabled-state, and removal changes revoke affected sessions in the
  same transaction. Admin changes and external-operation intent/results append
  hash-chained audit evidence.
- Strict SQLite schema verification, bounded records, bounded request bodies
  and path identifiers, transactional writes, and append-only triggers fail
  closed.

## Ledger, Operations, and UX Review

- Open, closed, and unresolved observations are separate. Pending, active,
  stop, target, and session-flatten states are concrete observational language,
  never executions.
- Canonical timestamps stay UTC while display timestamps use
  `America/Los_Angeles`; hold durations and the 13:58 Pacific cutoff are
  explicit.
- API, release, Drive, market-data connection, outbox/sync, watchdog, and
  process state remain distinct. Provider failures are converted to generic
  user-safe details and Drive principals are masked before API or audit
  exposure.
- Last successful Drive refresh and publication timestamps and counts are
  fixed-size transactional state. Failed or blocked attempts do not replace
  successful evidence.
- Connection tests are bounded and read-only. Drive publication retries only
  committed outbox evidence through SP4. Databento rotation accepts no secret
  value; it records an external-update workflow and verifies the active
  credential.
- Every frontend response is runtime-decoded with strict Zod contracts.
  Loading, ready, blocked, and error behavior never substitutes realistic
  production data. Realistic records exist only in test fixtures.
- Desktop and mobile checks cover semantic headings/tables, keyboard skip
  navigation, explicit confirmation, visible state text, chart text/table
  equivalents, responsive layouts, reduced motion, and automated Axe checks.

## Independent Terra Findings Resolved

The independent Terra audit initially reported five material findings:

1. an unnecessary `httpx2` test dependency increased supply-chain risk;
2. viewer access to sanitized status was not explicit enough in the written
   authorization contract;
3. raw SP4 Drive/provider detail could reach operational responses or audit
   evidence;
4. operational status did not persist the last successful Drive refresh and
   publication evidence;
5. user and rotation identifiers were not bounded at the HTTP path boundary.

The dependency was removed in favor of a direct bounded `httpx` development
dependency. The viewer-status policy is now explicit and regression-tested
while all controls remain admin-only. Drive errors are generically mapped and
principals masked. Successful Drive activity is persisted transactionally and
rendered with Pacific and UTC time. Identifier paths now have exact bounded
patterns. Regression tests cover every correction, including provider-detail
leakage and preservation of last-successful evidence across later blocked
attempts.

The final independent Terra re-audit reported no material findings remaining.

## Verification

```text
uv run pytest -q
360 passed, 1 skipped

uv run pytest -q tests/dashboard
36 passed

uv run ruff format --check src tests
90 files already formatted

uv run ruff check src tests
All checks passed

uv run mypy src
Success: no issues found in 48 source files

uv lock --check
Resolved 83 packages

uv run stoic-dashboard readiness
status: blocked
observation_count: 0
execution: false
orders_placed: 0

uv build
source distribution and wheel built successfully

npm --prefix web ci
found 0 vulnerabilities

npm --prefix web run typecheck
passed

npm --prefix web run test
14 passed

npm --prefix web run build
Vite production build passed

npm --prefix web run e2e
6 desktop/mobile Chromium checks passed, including Axe

npm --prefix web audit --audit-level=low
found 0 vulnerabilities

pip-audit
no known vulnerabilities found

Bandit
no findings

OSV-Scanner 2.3.8 over uv.lock and web/package-lock.json
no issues found

Lighthouse accessibility
1.00

git diff --check
passed
```

The remaining non-material test warning is an upstream Starlette deprecation
notice for its current `httpx` TestClient adapter. The direct dependency is
bounded and the test suite passes; revisit it with a future FastAPI/Starlette
upgrade rather than adding the removed package. Live Google and Drive
integration was not exercised without external production credentials. This
does not weaken the fail-closed boundary: the production API remains blocked
and empty until complete external configuration and the signed,
human-approved SP0 release exist.
