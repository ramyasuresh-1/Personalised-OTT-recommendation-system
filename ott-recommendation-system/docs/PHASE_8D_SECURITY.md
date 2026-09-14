# Phase 8D Security and Production Hardening

## Status

Security hardening is implemented locally and requires production configuration review before deployment. Phase 8E and deployment were not started.

## Authentication and sessions

- Passwords use salted PBKDF2-HMAC-SHA256 with 310,000 iterations.
- Session tokens are generated with `secrets`, stored only as SHA-256 hashes, and invalidated on logout.
- Session cookies are `HttpOnly`; `SESSION_COOKIE_SECURE` and `SESSION_COOKIE_SAMESITE` are environment-controlled.
- Production must use `SESSION_COOKIE_SECURE=true` and HTTPS. Local development may use `false` and `lax`.
- User watchlist, history, analytics, and authenticated ratings are scoped to the session user.

## CORS and CSRF

- Credentialed CORS uses explicit origins from `CORS_ORIGINS`; wildcard origins are rejected.
- `FRONTEND_URL` is the production origin source when a specific `CORS_ORIGINS` list is not supplied.
- State-changing cross-site requests carrying a session cookie are rejected when the browser sends `Sec-Fetch-Site: cross-site`.
- Production must set the deployed frontend origin explicitly and keep credentials enabled only for required origins.

## Administrative API

`/api/retrain` and `/api/simulate-drift` require the `X-Admin-Token` header and `ADMIN_API_TOKEN`. Ordinary users and unauthenticated callers cannot trigger these operations. The token must be a long random secret supplied through the deployment environment and must never be placed in frontend code.

## Input, SQL, and error handling

- Registration, login, ratings, IDs, and drift simulation types are validated server-side.
- Database operations use parameterized SQL and session ownership checks.
- Unexpected backend failures are logged server-side and return generic client messages without tracebacks, paths, or database details.

## Headers and frontend

The FastAPI middleware emits `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and HTTPS-only HSTS. Nginx emits equivalent headers plus a restrictive CSP for the static frontend. The CSP allows only the existing CDN/font sources used by the application.

## Secrets and environment

`.env` files are ignored by Git; `.env.example` contains placeholders only. Required production values include `DATABASE_PATH`, `MODEL_DIR`, `FRONTEND_URL` or `CORS_ORIGINS`, `SESSION_COOKIE_SECURE=true`, `SESSION_COOKIE_SAMESITE=lax`, `ADMIN_API_TOKEN`, MLflow settings, and a non-default Grafana admin password.

Do not expose database, model, MLflow, Prometheus, or Grafana credentials to frontend JavaScript. Monitoring and MLflow interfaces should be private-network or authenticated administrative services in production; local Compose ports are for development verification only.

## Docker and MLOps

The existing services and Funk SVD/retraining/quality-gate/champion lifecycle are preserved. The backend image includes both `app` and `ml` packages. No recommendation behavior or MLOps thresholds were changed.

## Verification

Run:

```text
python -m compileall backend/app
python -m pytest backend/tests -v
docker compose config
docker compose ps
```

Security tests cover invalid input, protected user data, logout invalidation, admin endpoint authorization, and security headers.

## Known limitations and production blockers

- Full dependency vulnerability scanning and remote CI execution are not performed locally.
- Browser cookie attributes and CSP should be manually verified over the eventual HTTPS deployment origin.
- Grafana, Prometheus, and MLflow remain host-exposed in local Compose and must be network-restricted or protected before production.
- A strong `ADMIN_API_TOKEN`, non-default Grafana password, HTTPS, persistent storage, and a production-specific CORS origin are required before deployment.
