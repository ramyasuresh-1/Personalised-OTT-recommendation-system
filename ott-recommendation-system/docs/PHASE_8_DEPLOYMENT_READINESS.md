# Phase 8 Deployment Readiness

## 1. Original blockers

The project was not ready for production deployment because the project still assumed local-only execution for key runtime assets:

- frontend was hard-coded to `http://localhost:8000`
- backend CORS used wildcard access with credentials enabled
- database persistence was local SQLite under the project source tree
- model artifacts were stored in local files under the backend model directory
- DVC remote configuration was not verified for production
- MLflow was running with local SQLite and file-based artifacts
- Prometheus and Grafana were part of the internal ops stack and were not treated as internal-only services
- Grafana used a default admin password in Docker Compose
- retraining was background-task based and not production-scheduled

## 2. Changes made

Production-readiness changes were limited to config and deployment safeguards while preserving the existing MLOps architecture:

- frontend runtime API configuration is now supplied through a config file instead of a hard-coded localhost URL
- backend CORS is now governed by the `CORS_ORIGINS` environment variable
- database path is now configurable via `DATABASE_PATH`
- model directory is now configurable via `MODEL_DIR`
- Docker Compose passes environment configuration for database/model/CORS/MLflow/Grafana settings
- Grafana admin credentials are now environment-driven instead of fixed at `admin`
- production startup uses the production Uvicorn command and not `--reload`
- documentation was added for environment variables and deployment recognitions

## 3. Frontend configuration

The frontend is static HTML/CSS/JS and does not use a Vite or React runtime config system. To keep it production-safe without rewriting the app, a lightweight runtime file was added:

- `frontend/config.js`

This exposes:

```js
window.APP_CONFIG = window.APP_CONFIG || {};
window.APP_CONFIG.API_BASE_URL = window.APP_CONFIG.API_BASE_URL || 'http://localhost:8000';
```

The app script reads this configuration before making backend calls instead of hard-coding localhost. This allows deployment environments to override the backend URL without touching the app logic.

## 4. Backend configuration

The backend now reads the following from environment variables:

- `CORS_ORIGINS`
- `DATABASE_PATH`
- `MODEL_DIR`
- `MLFLOW_TRACKING_URI`
- `MLFLOW_ARTIFACT_ROOT`
- `MLFLOW_EXPERIMENT_NAME`

The backend still preserves local development behavior by defaulting to localhost-friendly values when the environment is absent.

## 5. Database strategy

The project uses SQLite for local persistence and works by default with local disk storage. This is acceptable for local dev and small, single-instance deployments, but it is not a production-grade database for multi-instance scale or managed backups.

Current database behavior:

- database file is under `backend/data/ott_recommendation.db`
- data access uses SQLite tables for movies, ratings, inference logs, and retraining history
- DB path can now be overridden through `DATABASE_PATH`

Limitations:

- backup and restore are manual if file-based SQLite is used
- concurrency is limited for write-heavy workloads
- multi-instance deployment becomes fragile without a dedicated database service

Future migration path:

- move to PostgreSQL or a managed hosted relational database
- keep the same application schema and migrate the data with a controlled ETL process
- continue using the same model/data flow, but store the operational DB outside the app container

## 6. Model artifact strategy

The recommendation model is serialized as a pickle file under the model directory and is loaded by the backend at startup. The model path is now configurable via `MODEL_DIR` and the runtime loads `recommender.pkl` from that configured directory.

Current model strategy:

- local directory `backend/models`
- file-based persistence used for champion model state
- model promotion path remains the same as the retraining pipeline

Production requirement:

- artifact storage must remain persistent across app restarts or container replacements
- a managed file volume or object storage backend should be used in a real deployment
- do not rely on ephemeral container filesystem for the champion model

## 7. DVC strategy

DVC remains part of the project lifecycle for data and model pipeline management. It is used for reproducibility and lifecycle tracking, but it is not required for runtime model serving in a minimal deployment.

Important distinction:

- DVC is for MLOps lifecycle/data governance
- runtime serving still depends on an actual persisted model artifact on disk or managed storage

No DVC remote was verified in this repo state, so the project still requires explicit production storage configuration before a production-grade pipeline is claimed to be complete.

## 8. MLflow strategy

MLflow remains enabled and configured in the project for experiment tracking. It is not exposed publicly by default and should stay internal to the operational environment.

Current local behavior:

- tracking URI defaults to a local SQLite file
- artifact root defaults to local file storage in `backend/mlruns`
- experiment name remains `OTT Recommendation System`

For a production-grade setup, MLflow would need:

- persistent backend storage in a managed database or remote service
- durable artifact storage such as S3, Azure Blob Storage, or equivalent
- restricted network access, not public exposure

The project remains suitable for an internal deployment demo, but not as a production public-facing MLflow endpoint.

## 9. Prometheus strategy

Prometheus remains in the stack for operational monitoring. It should serve as an internal service that scrapes the backend `/metrics` endpoint and should not be public by default.

Current behavior:

- scrape target is the backend service address inside the internal Docker network
- metrics endpoint is served through FastAPI `/metrics`

Production treatment:

- keep Prometheus internal only
- allow access only to ops personnel or internal VPC/private network

## 10. Grafana strategy

Grafana continues to be part of the monitoring stack and should remain internal-only. The project was updated to avoid hard-coded credentials by setting admin credential values from environment variables.

Current behavior:

- dashboards are provisioned from the `monitoring/grafana` folder
- Grafana stores data in the `grafana-storage` volume
- credentials are now environment-driven using `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD`

This is still not a production-grade public user interface; production deployments should keep Grafana behind private access controls.

## 11. Retraining strategy

The existing retraining pipeline remains intact and is still available at `/api/retrain`.

Current state:

- API-triggered retraining is enabled
- retraining runs in the backend process as a background task
- there is a duplicate-protection check to avoid multiple concurrent retraining jobs
- the champion model is protected until candidate evaluation passes the quality gate

Important limitation:

- this is not a fully production-grade scheduler
- a real deployment should use an external cron/scheduler/worker service for periodic retraining, or a dedicated control plane

## 12. Environment variables

The project now includes a safe environment example file:

- `.env.example`

This file contains variable names and safe placeholders only. It does not contain real secrets.

Variables are limited to the project’s actual runtime configuration:

- `DATABASE_PATH`
- `MODEL_DIR`
- `CORS_ORIGINS`
- `MLFLOW_TRACKING_URI`
- `MLFLOW_ARTIFACT_ROOT`
- `MLFLOW_EXPERIMENT_NAME`
- `GRAFANA_ADMIN_USER`
- `GRAFANA_ADMIN_PASSWORD`

## 13. Docker changes

The Docker configuration was updated to better support deployment-safe runtime settings.

Key updates:

- backend environment includes `DATABASE_PATH`, `MODEL_DIR`, `CORS_ORIGINS`, and MLflow settings
- production startup uses the standard `uvicorn app.main:app --host 0.0.0.0 --port 8000` command rather than a dev reload variant
- model and data paths are safer and consistent with environment values
- Grafana credentials are now sourced from environment variables

## 14. Security changes

The following production-related security issues were addressed to the extent appropriate for this phase without altering the MLOps design:

- frontend no longer depends on a hard-coded localhost API source
- backend CORS is no longer wildcard-based by default
- Grafana password is no longer a fixed `admin` value in Compose
- only environment-safe placeholders are documented in `.env.example`

This does not mean the project is fully hardened for public production yet. It only means the minimal deployment blockers were reduced without changing the core system architecture.

## 15. Local validation

Validation was performed with the project’s existing checks:

- `python -m compileall backend/app`
- `python -m pytest backend/tests -v`
- `docker compose config`

The project remains compatible with its existing code and tests, and the improvements were kept minimal and non-disruptive.

## 16. Remaining deployment requirements

The system is still not ready for a public Render deployment because the following items still require an explicit production setup outside this minimal Phase 8 fix set:

1. managed persistent storage for SQLite/model/MLflow artifacts
2. private-only ingress for operational services
3. production-grade secret management for Grafana and runtime configuration
4. a real production deployment environment and network topology
5. separate managed model artifact storage if the app is scaled beyond a single instance
6. potential migration from SQLite to PostgreSQL if the project grows beyond single-instance prototype scale

This phase only prepared the app for a more deployment-aware configuration, not a full production rollout.

## Final status

PHASE 8 PREPARATION INCOMPLETE

The project is safer and closer to deployment, but it is not yet ready for a live Render deployment because the required managed persistence and operational isolation decisions are still unresolved.
