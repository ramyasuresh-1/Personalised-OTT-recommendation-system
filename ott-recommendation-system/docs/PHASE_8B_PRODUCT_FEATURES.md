# Phase 8B Product Features

## Authentication Architecture

AURA now uses minimal cookie-based sessions. Registration and login create an opaque 32-byte random session token. The browser receives it as an `HttpOnly` cookie named `aura_session`; only its SHA-256 hash is persisted in SQLite. Sessions expire after 30 days and logout deletes the server-side session.

Endpoints:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

Registration validates usernames, email format, and an eight-character minimum password. Duplicate usernames or emails return `409`. Invalid credentials return `401`.

## User Model

The idempotent `users` table contains `id`, `username`, `email`, `password_hash`, and `created_at`. Passwords use PBKDF2-HMAC-SHA256 with a random salt and 310,000 iterations. Password hashes are never returned by the API.

New account IDs start above the seeded anonymous recommender IDs so existing Phase 1-7 rating data remains intact and is not accidentally presented as a new account's private history.

## Database Changes

Added idempotent SQLite tables:

- `users`
- `sessions`
- `watchlist`

The existing `ratings` table remains keyed by `(user_id, movie_id)`. Rating submission updates the existing row and timestamp, so each user has one current rating per movie. Existing movies, ratings, inference logs, retraining history, and model data are preserved.

## Watchlist API

- `GET /api/watchlist`
- `POST /api/watchlist/{movie_id}`
- `DELETE /api/watchlist/{movie_id}`

Watchlist rows are uniquely keyed by user and movie. Duplicate additions return `409`; unknown movies return `404`. Every query is scoped to the authenticated session user.

## Ratings and History API

`POST /api/rate` remains compatible with existing anonymous callers. Authenticated frontend requests must use the session user's ID and cannot submit ratings for another user. Invalid ratings return `400` and mismatched authenticated IDs return `403`.

`GET /api/history/ratings` returns only the authenticated user's joined movie/rating records, including rating timestamps.

## Analytics API

`GET /api/analytics/me` returns only session-scoped data: total ratings, average rating, rating distribution, favorite genres derived from the user's ratings, and watchlist count. Global monitoring telemetry is not presented as personal analytics.

## Profile and Settings

`GET /api/auth/me` provides the authenticated profile fields: ID, username, email, and account creation time. The frontend Profile page uses this response and never exposes password data. Settings provides the configurable backend URL and a real logout action. No fake preferences or authentication state are stored in local storage.

## Frontend Authentication Flow

The existing vanilla frontend retains public Dashboard, Movies, Genres, and Search access. Recommendations, Watchlist, History, Ratings, Analytics, Profile, and Settings require authentication and show a login/register prompt when accessed as a guest. The login/register modal restores the session through `/api/auth/me`, sends cookies with API requests, and updates the sidebar/account controls after login or logout.

Movie cards can add titles to the persistent watchlist. Watchlist cards remove titles through the delete API. History and Analytics render real authenticated responses with loading, empty, and error states.

## Security Decisions

- Passwords are salted and hashed with PBKDF2-HMAC; plaintext passwords are never stored.
- Session tokens are generated with `secrets.token_urlsafe`, stored only as hashes, and sent with `HttpOnly` cookies.
- Cookie `secure` behavior is environment-configurable with `SESSION_COOKIE_SECURE`; local development defaults to false. `SESSION_COOKIE_SAMESITE` is configurable and defaults to `lax`.
- CORS remains controlled by `CORS_ORIGINS` and credentials remain enabled for cookie sessions.
- SQL queries use parameterized values.
- Personal endpoints derive user identity from the session and reject unauthenticated access.
- No secrets, passwords, or production URLs were committed.

## Compatibility and MLOps

Existing `/api/health`, `/api/movies`, `/api/recommend`, `/api/rate`, `/api/monitoring/metrics`, `/metrics`, and `/api/retrain` routes remain present. The Funk SVD implementation, monitoring, Evidently drift detection, Prometheus instrumentation, MLflow tracking, retraining, quality gates, champion protection, and CI/CD configuration were not rewritten.

## Tests

Phase 8B adds tests for registration, duplicate registration, invalid login, logout, protected routes, watchlist persistence and isolation, rating update behavior, rating history, analytics, and analytics isolation. The full backend suite passes with 70 tests.

## Known Limitations

Recommendation history is intentionally not added. The product now has meaningful rating history, and storing every recommendation response would add database growth without a current interaction/event model. A future phase could add explicit recommendation interaction events if product requirements call for them.