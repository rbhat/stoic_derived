# SP5 - Static Operations Dashboard and Control API Design

*Design status: accepted for implementation*

## 1. Objective

SP5 provides an accessibility-first dashboard for the observational Stoic
Derived system. The user-facing application is a compiled, client-rendered
React 19 single-page application. FastAPI exposes only a versioned JSON/control
API and the Google Identity Services login receiver. It does not render
application pages.

The dashboard presents verified SP4 ledger state, operational readiness, safe
management workflows, and invite-only user administration without changing the
strategy, enabling production from private data, claiming executions, or
inventing capital P/L. The repository still has no signed, semantically
complete, human-approved SP0 release. The production dashboard therefore
truthfully starts blocked with zero ledger observations.

## 2. Brainstorm Decisions

### 2.1 Ship a static React SPA, never server-rendered application routes

The frontend lives in `web/` and uses React 19, Vite 7, strict TypeScript, and
Zod 4 runtime decoding. Vite produces static HTML, JavaScript, CSS, fonts, and
other assets for SP6 to deploy on GCP.

FastAPI lives under `src/stoic_derived/dashboard/` and serves `/api/v1/*` JSON
or explicit HTTP redirects from the Google login receiver. It does not contain
Jinja, template engines, React Server Components, Next.js, SSR entry points, or
HTML application routes. In development Vite proxies `/api` to FastAPI. In
production SP6 will place the static SPA and API behind one HTTPS origin.

The browser treats every API response as untrusted. Zod schemas are strict,
derive their TypeScript types, and model boot, ledger, and operation state with
discriminated unions. A response that does not match the declared contract is
an explicit error state, never partially rendered data.

### 2.2 Use Google Identity Services for authentication only

The SPA loads the official GIS browser library and renders the Google button
through its JavaScript API. It initializes redirect UX with the configured GCP
Web Client ID and the same-origin FastAPI login URI. Google posts an
`application/x-www-form-urlencoded` body containing `credential` and
`g_csrf_token` directly to the backend.

The login receiver:

1. requires both the `g_csrf_token` cookie and form field and compares them
   completely with a constant-time comparison;
2. verifies the ID token through `google-auth` with the configured Web Client
   ID as audience;
3. explicitly requires a Google issuer, unexpired token, exact audience,
   non-empty `sub`, non-empty verified email, and an email for which Google is
   authoritative;
4. treats Google as authoritative only for verified `@gmail.com` identities or
   verified Google Workspace identities with a non-empty `hd` claim;
5. uses `sub` as the durable identity after first login and the normalized
   invited email only for initial binding;
6. rejects users who are not enabled in the invite-only server-side store.

Dashboard users never grant Drive scopes and never receive Google access or
refresh tokens. SP4 Drive access remains ADC/service-account or delegated-user
infrastructure.

On success, the API creates random opaque session and CSRF tokens using the
operating-system CSPRNG. Only the session-token digest is stored. The raw
session token is sent in a `Secure`, `HttpOnly`, `SameSite=Lax`,
`Path=/`, `__Host-` cookie with no Domain attribute. The session endpoint
returns the synchronizer CSRF token to authenticated JavaScript. Logout and
every state-changing JSON request require it in `X-CSRF-Token`, and mutation
requests must come from the configured origin.

Every protected request resolves the opaque session in SQLite, joins the
current user record, and checks expiry, enabled state, and role on the server.
Role changes, disabling, and removal revoke all sessions for the affected user
in the same transaction, so authorization changes take effect immediately.
There is no production fixture, debug identity, header impersonation, bearer
bypass, or client-side-only authorization path.

This follows current official behavior rechecked on 2026-07-24:

- [Display the Sign in with Google button](https://developers.google.com/identity/gsi/web/guides/display-button)
- [Verify the Google ID token on your server](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
- [GIS HTML API and server-side POST reference](https://developers.google.com/identity/gsi/web/reference/html-reference)
- [Google authentication and authorization separation](https://developers.google.com/identity/oauth2/web/guides/overview)
- [`google.oauth2.id_token` verification](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.id_token.html)

### 2.3 Make the primary administrator immutable at the database boundary

`rajeevmbhat@gmail.com` is bootstrapped as the one primary administrator. The
record has a stable primary marker, the `admin` role, and enabled state. SQLite
constraints and triggers prevent its deletion, disablement, email change,
primary-marker change, role change, replacement of an already-bound Google
`sub`, or demotion. Service-level validation gives clear errors before the
trigger provides the final fail-closed boundary.

Admins may invite a normalized authoritative Gmail or Workspace address as an
`admin` or `viewer`, change a non-primary user's role or enabled state, and
remove a non-primary user. Email renaming is not an API operation. Viewers can
read the observational ledger and sanitized operational-status endpoint, but
cannot call administration, audit, publication, connection-test, refresh, or
rotation endpoints. Operational visibility is read-only; every control remains
administrator-only.

### 2.4 Keep control state transactional, exact, bounded, and auditable

A portable SQLite control database stores users, sessions, connection-test
status, last successful Drive refresh/publication observations, API-key
rotation workflow state, and an append-only audit chain. It
uses foreign keys, WAL, `synchronous=FULL`, an explicit busy timeout, strict
tables, schema-version checks, and exact `sqlite_master` verification for
tables, indexes, and triggers.

All in-database mutations use `BEGIN IMMEDIATE`. Each admin mutation appends an
audit record in the same transaction. Audit rows include a stable action,
actor snapshot, resource, canonical before/after JSON, UTC timestamp, request
ID, previous-record hash, and content hash. Database triggers reject audit
updates and deletes. Startup verifies the hash chain. Explicit row limits
bound users, sessions, workflows, and audit records; reaching a limit blocks a
new mutation rather than evicting evidence.

External operations create an append-only request audit record before making a
network or Drive change, then append a sanitized completion/failure record.
Secrets, cookies, ID tokens, CSRF values, Google claims, API keys, credential
paths, and raw provider errors never enter audit data or API responses.

### 2.5 Read ledger truth only through the SP0/SP2/SP4 production boundary

The dashboard checks SP4 `readiness(...)` with the configured signed-release
identity. If it is blocked, the dashboard returns a typed blocked ledger with
zero records and does not load the draft rulebook, a test event, a local
fixture, or a private release.

Only after release readiness succeeds may the production ledger projection:

1. verify every acknowledged local event at its exact Drive object;
2. read and verify the bounded SP4 Drive event set;
3. add only locally committed, still-undelivered outbox events;
4. decode all bytes with the SP4 codec and reconcile through
   `reconcile_events(...)`.

Acknowledged local rows never substitute for missing Drive authority.
Backtest, walk-forward, and paper results never enter dashboard readiness.
Tests inject explicit fakes through application dependencies; production
composition has no fixture selector or alternate ledger source.

### 2.6 Project observations without inventing financial results

The API emits three separate collections:

- **open observations:** `pending` and `active`;
- **closed observations:** only deterministic `closed` records;
- **unresolved observations:** terminal records whose evidence cannot form one
  trusted closed chain.

Every row remains an observation, never a trade fill, order, execution, or
broker position. Stop, target, and session-flatten close reasons are explicit.
Unresolved reasons and typed SP4 conflicts remain visible.

For a closed observation, exact signed P/L ticks are:

```text
long:  close_price_ticks - entry_price_ticks
short: entry_price_ticks - close_price_ticks
```

Exact observational R is that integer tick result divided by the signal's
absolute planned entry-to-stop tick risk, reduced to a rational number. The API
returns numerator, denominator, and an exact finite-decimal-or-fraction display
string. It never returns dollar P/L because SP2 signals contain no position
size. Pending, active, and unresolved observations return no P/L rather than a
mark-to-market estimate.

Closed hold time is the exact close-observation timestamp minus entry
observation timestamp. Active hold time is measured against the API snapshot
time. Pending and unresolved-without-entry rows have no hold time.

Canonical API timestamps are UTC RFC 3339 strings derived from SP2/SP4
nanoseconds. The SPA formats them at the edge with
`America/Los_Angeles`, including the current PST/PDT abbreviation. UTC remains
available in accessible labels and details.

### 2.7 Expose constrained, truthful operational controls

The operations API and UI report:

- API process running state and start time;
- release readiness and blockers;
- Drive readiness and authenticated principal, sanitized for display;
- market-data and Drive connection-test status;
- outbox pending/acknowledged counts and maximum pending attempts;
- last successful Drive refresh/publish observation;
- watchdog state derived from readiness and verified current-session cutoff
  evidence, otherwise explicitly `blocked`, `unknown`, or `stale`.

Admin controls have closed vocabularies and accept no URLs, commands, file
paths, credentials, Drive IDs, or secret values:

- **Test connection:** `market_data` or `drive`. The production probe performs
  a bounded, read-only provider call; an unconfigured provider is blocked.
- **Refresh Drive:** verifies authority and rebuilds the projection without a
  write.
- **Publish outbox:** calls SP4's verified retry-safe publication, then
  re-reads authority.
- **Rotate API key:** creates a `databento` rotation workflow that never
  accepts or stores the key. An administrator updates the external secret
  through the SP6 infrastructure boundary, then asks the dashboard to verify
  the newly active credential with the connection probe. The workflow records
  requested, verified, failed, or cancelled state.

These controls cannot start execution, place orders, alter strategy semantics,
approve SP0, change confidence, load fixtures, or bypass readiness.

### 2.8 Use a restrained Pacific session console visual system

The interface serves an operator who needs to determine truth and readiness
quickly. Its visual system is:

- **Fog** `#F1F4F2` canvas, **Paper** `#FAFBF9` surfaces,
  **Sound** `#183035` primary text, **Tide** `#0B6571` action/readiness accent,
  **Cutoff** `#A65A17` for the 13:58 boundary, and **Fault** `#A23A35` for
  blocked/stop/error evidence;
- Atkinson Hyperlegible Next for reading and IBM Plex Mono for timestamps,
  ticks, R values, IDs, and status evidence; both are compiled into the SPA;
- ruled sections and a compact operational strip instead of a grid of generic
  KPI cards;
- one signature Pacific chronology rail whose 13:58 cutoff marker is visually
  dominant and whose copy states that Position observations are exempt;
- no gradients, fake buy/sell controls, candlestick decoration, broker
  language, hover-only information, or decorative market charts.

The design self-review rejected a dark terminal theme and a cream editorial
layout because both are generic defaults and reduce daylight legibility. The
revised overcast-console direction is specific to Pacific time, Drive evidence,
and the observational cutoff.

Open and closed sections each have their own small, truthful chart: open
observations by state and Type, and closed observations by observed terminal
reason. Each SVG has a programmatic title/description and an adjacent text
equivalent. Semantic tables remain the authoritative detailed view.

The SPA meets WCAG 2.2 AA intent: semantic landmarks and headings, real buttons
and labels, table captions and scopes, visible focus, skip link, status
announcements, no color-only meaning, at least 44px touch targets, sufficient
contrast, keyboard-complete dialogs/forms, responsive layouts, and
`prefers-reduced-motion`. Desktop and mobile browser verification plus
Lighthouse accessibility are release checks.

Reference: [WCAG 2.2](https://www.w3.org/TR/WCAG22/).

## 3. API Contracts

All JSON responses include `schema_version: "dashboard-api/v1"`. Unknown input
fields are rejected. The main route groups are:

```text
GET    /api/v1/auth/config
POST   /api/v1/auth/google
GET    /api/v1/session
POST   /api/v1/session/logout

GET    /api/v1/ledger
GET    /api/v1/operations/status

GET    /api/v1/admin/users
POST   /api/v1/admin/users
PATCH  /api/v1/admin/users/{user_id}
DELETE /api/v1/admin/users/{user_id}

POST   /api/v1/admin/operations/connection-tests
POST   /api/v1/admin/operations/drive-refresh
POST   /api/v1/admin/operations/drive-publish

GET    /api/v1/admin/key-rotations
POST   /api/v1/admin/key-rotations
POST   /api/v1/admin/key-rotations/{rotation_id}/verify
POST   /api/v1/admin/key-rotations/{rotation_id}/cancel

GET    /api/v1/admin/audit
```

Only auth configuration and the Google login receiver are unauthenticated.
Every other request performs server-side session and current-user lookup.
Every non-login mutation requires an authenticated admin where applicable,
same-origin validation, CSRF validation, and audit evidence.

## 4. Failure and Restart Semantics

- Missing SP0 release: successful blocked ledger, zero observations, no Drive
  ledger read, no execution, no orders.
- Missing Drive configuration/ADC/capability: operational Drive state blocked;
  no fallback to local acknowledged data.
- Invalid Google CSRF or ID token: no session and no identity binding.
- Uninvited, disabled, non-authoritative, or mismatched-sub identity: generic
  access denial and no session.
- Changed role/removal: current sessions are revoked transactionally and the
  next request fails.
- Session or CSRF mismatch: 401/403 with no mutation.
- SQLite schema, trigger, hash-chain, or version mismatch: application startup
  fails closed.
- Audit capacity exhausted: admin mutation is rejected before its local state
  change. External operations require an intent audit before invocation.
- Drive refresh/publish failure: typed failed operation; existing verified
  projection is not relabeled fresh.
- API response decode failure: SPA shows a contract error and does not render
  partial values.
- Frontend reload: session is reconstructed only through the HttpOnly cookie
  and `/session`; no identity or session token is stored in browser storage.

## 5. Acceptance Criteria

- Production frontend output is a static React 19/Vite SPA; FastAPI has no
  server-rendered page or template path.
- Google redirect POST, GIS double-submit CSRF, `google-auth` verification,
  authoritative-email rules, durable `sub`, whitelist binding, and opaque
  server sessions are covered by tests.
- Every protected endpoint performs server-side current-user authorization;
  viewers cannot mutate or reach admin data.
- `rajeevmbhat@gmail.com` cannot be removed, disabled, renamed, rebound,
  replaced, or demoted through APIs or direct SQL.
- Every admin mutation has append-only, hash-chained audit evidence with no
  secrets; role/removal changes revoke sessions immediately.
- Ledger projection uses release readiness, verified Drive authority, and only
  undelivered outbox events. Current production is blocked and empty.
- Open, closed, and unresolved observations are distinct. Stop, target, and
  session flatten are distinct. Closed ticks and R are exact; dollar P/L is
  absent.
- UTC is canonical and the SPA displays Pacific timestamps and exact hold
  duration.
- Operational, Drive, outbox/sync, watchdog, readiness, connection-test,
  publication, key-rotation, and user-management states are visible and
  truthful.
- Frontend API responses are runtime decoded; no production sample data or
  hidden bypass exists.
- Backend/full Python tests, frontend unit/component tests, strict type-check,
  production build, E2E responsive/keyboard checks, Lighthouse accessibility,
  Ruff, mypy, lock checks, packaging, and boundary scans pass.

## 6. Decisions

- [ADR-0017](../../architecture/adr/0017-static-react-spa-with-json-control-api.md)
- [ADR-0018](../../architecture/adr/0018-google-identity-and-server-side-sessions.md)
- [ADR-0019](../../architecture/adr/0019-drive-authoritative-dashboard-projections.md)
- [ADR-0020](../../architecture/adr/0020-transactional-audited-dashboard-controls.md)
