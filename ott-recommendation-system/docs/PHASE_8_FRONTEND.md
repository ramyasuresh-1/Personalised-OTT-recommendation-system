# Phase 8A Frontend

## Page Structure

The frontend is a single semantic HTML application with client-side view switching. It contains Dashboard, Movies, Genres, Search, Recommendations, Watchlist, History, Ratings, My Analytics, Profile, and Settings views. Movie details and rating submission use accessible modal dialogs.

## Sidebar

- Home: Dashboard
- Discover: Movies, Genres, Search
- Personal: Recommendations, Watchlist, History, Ratings
- Analytics: My Analytics
- Account: Profile, Settings

The sidebar is fixed and visible on desktop-sized screens. At smaller widths it becomes a slide-in drawer opened by the hamburger button. Navigation items only target implemented views.

## API Integrations

- `GET /api/health`: backend availability and model status.
- `GET /api/movies`: live movie catalog, used by discovery, genres, search, ratings, and details.
- `GET /api/recommend?user_id=...`: personalized recommendation cards and dashboard content.
- `POST /api/rate`: validated 1-5 rating submission.
- `GET /api/monitoring/metrics`: live telemetry, drift, and model status for the dashboard and analytics view.
- `GET /metrics`: remains a backend Prometheus endpoint and is not modified by the frontend.
- `POST /api/retrain`: backend contract remains unchanged and is not invoked by this user-facing app.

## Frontend Configuration

`frontend/config.js` resolves the backend URL from `window.APP_CONFIG.API_BASE_URL`, `window.__APP_API_URL__`, local browser storage, or the local development fallback. Settings can persist a configured backend base URL in browser storage. No future production URL is hard-coded.

## Features Implemented

- Live catalog loading with client-side title search, genre filtering, and sorting.
- Live recommendation loading with refresh, loading, empty, malformed-response, and network-error states.
- Movie details from available catalog fields only.
- Rating selector with validation, submit progress, success feedback, and friendly error feedback.
- Dashboard using live recommendations, catalog data, health, and monitoring telemetry where available.
- Analytics uses the authenticated user's ratings, rating distribution, favorite genres, and watchlist count from `/api/analytics/me`.
- Responsive layout, keyboard focus styles, semantic controls, live feedback regions, and accessible modal labels.

## Features Requiring Future Backend Support

- Recommendation event history is not currently stored; rating history is implemented through `/api/history/ratings`.
- Additional account preferences and profile editing require future product requirements and persistence fields.

Phase 8B added cookie-based authentication, persistent watchlists, authenticated ratings, rating history, user analytics, and session-backed profile/settings flows. See [PHASE_8B_PRODUCT_FEATURES.md](PHASE_8B_PRODUCT_FEATURES.md).

## Responsive Design

The grid, dashboard panels, filters, dialogs, sidebar, and topbar adapt across desktop, laptop, tablet, and mobile widths. Mobile navigation uses a drawer, controls retain usable touch targets, and content avoids fixed-width horizontal overflow.

## Validation

Frontend JavaScript is syntax-checked with Node. Backend regression validation remains:

```text
python -m compileall backend/app
python -m pytest backend/tests -v
```