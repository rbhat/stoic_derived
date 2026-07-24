# ADR-0018: Google Identity and Server-Side Opaque Sessions

- Status: accepted
- Date: 2026-07-24

## Context

The dashboard is invite-only, requires Google authentication, and must apply
user removal and role changes immediately. Dashboard users do not need Google
Drive authorization.

## Decision

Use GIS authentication-only redirect POST with cookie/body `g_csrf_token`
verification. Verify the Google ID token with `google-auth` and the configured
Web Client ID. Require a verified Google-authoritative Gmail or Workspace
email, bind invitations on first login, and use `sub` thereafter.

Issue random opaque sessions in `Secure`, `HttpOnly`, `SameSite=Lax`,
`__Host-` cookies. Resolve the session and current user from SQLite on every
protected request. Use a per-session synchronizer CSRF token plus exact Origin
validation for mutations.

## Consequences

No Google access/refresh token or Drive scope is stored. Role changes and
removal can revoke sessions immediately. The API must maintain a durable
server-side session store.
