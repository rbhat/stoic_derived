# ADR-0017: Static React SPA with JSON Control API

- Status: accepted
- Date: 2026-07-24

## Context

SP5 needs an interactive dashboard that SP6 can deploy on GCP. Application
rendering must not be coupled to the Python server.

## Decision

Build `web/` as a React 19, Vite 7, strict-TypeScript SPA whose production
artifact is static. FastAPI serves only versioned JSON/control endpoints and
the GIS login receiver. It does not serve templates, SSR application routes,
React Server Components, or frontend fixtures.

Production uses one HTTPS origin. Vite proxies `/api` during development.
Every API response is runtime-decoded in the browser.

## Consequences

SP6 can deploy/cache frontend assets independently while keeping session
cookies same-origin. Browser boot requires explicit loading/error states.
There is no server-rendered fallback.
