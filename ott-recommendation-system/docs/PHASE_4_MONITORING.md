# Phase 4 — Prometheus & Grafana Monitoring

## 1. Phase 4 objective

The Phase 4 objective was to validate the monitoring stack end-to-end for the existing FastAPI backend:

- FastAPI exposes Prometheus metrics at `/metrics`
- Prometheus scrapes the backend and stores metrics
- Grafana uses Prometheus as a datasource and loads a provisioned dashboard
- The dashboard uses only metrics that are actually exported by the backend monitoring module

## 2. Existing architecture

This project already contains the original architecture and did not need a restructuring:

- `backend/app/main.py` hosts the FastAPI service
- `backend/app/monitoring.py` defines the Prometheus metrics
- `docker-compose.yml` brings up the backend, frontend, MLflow UI, Prometheus, and Grafana
- `monitoring/prometheus/prometheus.yml` defines the scrape job
- `monitoring/grafana/provisioning/...` configures Grafana data sources and dashboards

## 3. Prometheus architecture

Prometheus is configured to scrape the FastAPI service over the Docker Compose network:

- target: `backend:8000`
- metrics path: `/metrics`
- scrape interval: `15s`

This matches the existing backend service name in the compose file and does not introduce any duplicate backend service or alternate port mapping.

## 4. Grafana architecture

Grafana is provisioned rather than configured manually:

- datasource provisioning file: `monitoring/grafana/provisioning/datasources/datasource.yml`
- dashboard provisioning file: `monitoring/grafana/provisioning/dashboards/dashboards.yml`
- dashboard file: `monitoring/grafana/dashboards/ott_recommendation_dashboard.json`

Grafana is configured to use the Prometheus service at `http://prometheus:9090` from inside the Docker network.

## 5. Metrics implemented

The backend monitoring module exports the following metrics:

- `http_requests_total` with labels `method`, `endpoint`, `http_status`
- `http_request_duration_seconds` with `method`, `endpoint`
- `http_request_errors_total` with `endpoint`, `http_status`
- `recommendation_requests_total` with label `status`
- `recommendation_errors_total`
- `recommendation_latency_seconds`
- `recommendations_generated_total`
- `cold_start_recommendations_total`
- `known_user_recommendations_total`
- `model_info` with labels `version`, `stage`
- `model_training_runs_total`
- `model_training_failures_total`
- `model_training_duration_seconds`
- `model_training_samples`
- `model_training_mse`
- `dataset_ratings_total`
- `dataset_movies_total`
- `dataset_users_total`
- `model_rmse`
- `model_mae`
- `model_precision_at_k` with `k`
- `model_recall_at_k` with `k`
- `model_f1_at_k` with `k`
- `model_ndcg_at_k` with `k`
- `model_hit_rate_at_k` with `k`
- `model_coverage`
- `model_diversity`

## 6. Dashboard panels

The dashboard includes panels for the metrics that are genuinely present and valid in the backend exporter.

Supported panels:
- API request rate
- API latency
- HTTP errors
- recommendation requests
- recommendation failures
- recommendation latency
- cold-start recommendations
- recommendations generated
- RMSE
- MAE
- Precision@K
- Recall@K
- F1@K
- NDCG@K
- Hit Rate@K
- Coverage
- Diversity
- current model version
- training runs
- training failures
- training duration
- training samples
- training MSE
- users
- movies
- ratings

Not implemented because no matching metric exists in `backend/app/monitoring.py`:
- service health panel keyed to a dedicated backend health counter or gauge

## 7. Docker Compose services

The compose file contains the existing services:

- `backend`
- `mlflow-ui`
- `frontend`
- `prometheus`
- `grafana`

The monitoring additions are limited to the Prometheus and Grafana services and do not replace or restructure the application architecture.

## 8. Prometheus scrape configuration

Prometheus configuration uses:

```yaml
scrape_configs:
  - job_name: 'ott_backend'
    metrics_path: /metrics
    static_configs:
      - targets: ['backend:8000']
```

This is the actual backend container service name and port defined by the existing Docker Compose stack.

## 9. Grafana datasource provisioning

Datasource provisioning points to the Prometheus service inside Docker:

```yaml
url: http://prometheus:9090
```

This is configured with provisioning so Grafana loads the datasource automatically.

## 10. Grafana dashboard provisioning

Dashboard provisioning points to the mounted dashboard directory:

```yaml
options:
  path: /var/lib/grafana/dashboards
```

The dashboard JSON is auto-loaded by Grafana.

## 11. Startup commands

```powershell
cd "C:\Users\Ramya\Downloads\ott-recommendation-system mlops\ott-recommendation-system"
docker compose up -d
```

To rebuild after changes:

```powershell
docker compose up -d --build
```

## 12. Shutdown commands

```powershell
docker compose down
```

To remove volumes as well:

```powershell
docker compose down -v
```

## 13. Health-check commands

Backend health:

```powershell
curl http://localhost:8000/api/health
```

Backend metrics:

```powershell
curl http://localhost:8000/metrics
```

Prometheus health:

```powershell
curl http://localhost:9090/-/healthy
```

Grafana health:

```powershell
curl http://localhost:3000/api/health
```

## 14. Prometheus URL

- http://localhost:9090

## 15. Grafana URL

- http://localhost:3000

## 16. Troubleshooting

If docker compose does not start, the first thing to verify is Docker Desktop or WSL runtime health. In this environment, the CLI is installed but the Docker engine is not reachable, and `docker info` returns a server-side 500 error.

Common checks:

```powershell
docker info
docker compose config
docker compose ps
docker compose logs --tail=100 backend
docker compose logs --tail=100 prometheus
docker compose logs --tail=100 grafana
```

If Prometheus does not show an `UP` target, verify:

- backend service name is still `backend`
- backend port is still `8000`
- `/metrics` is being served by FastAPI

If Grafana does not load the dashboard, verify:

- provisioning files are mounted correctly
- the dashboard file is present under `monitoring/grafana/dashboards`
- the datasource is set to `http://prometheus:9090`

## 17. Validation results

The monitoring configuration was validated to the extent allowed by the current environment:

- `docker compose config` succeeded after correcting the Grafana provisioning path mismatch
- `python -m compileall backend/app` succeeded
- `python -m pytest backend/tests -v` succeeded with 47 passing tests
- Docker runtime validation remains blocked because the Docker daemon is unavailable in this environment:
  - `docker compose logs grafana --tail=200` failed with `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`
  - `docker ps` failed with the same Docker daemon error

## 18. Final Phase 4 status

Phase 4 is not complete in this environment because the Docker engine is not reachable, so the live container stack could not be started and the end-to-end Prometheus/Grafana checks could not be executed.

What was confirmed:

- the Grafana dashboard mount/provisioning conflict was corrected in [docker-compose.yml](../docker-compose.yml) and [monitoring/grafana/provisioning/dashboards/dashboards.yml](../monitoring/grafana/provisioning/dashboards/dashboards.yml)
- the backend Prometheus exporter in [backend/app/monitoring.py](../backend/app/monitoring.py) matches the dashboard query set
- the application code compiles and the backend tests pass

What remains blocked:

- `docker compose up -d`
- `docker compose ps`
- backend health validation on `http://localhost:8000/api/health`
- backend metrics validation on `http://localhost:8000/metrics`
- Prometheus target health and Grafana datasource/dashboard validation

Once Docker Desktop/WSL is running and the Docker engine is reachable again, the same Phase 4 configuration should be re-tested without changing the existing architecture.
- the dashboard references only metrics that actually exist in the backend exporter

The only runtime issues that needed correction were genuine configuration/runtime blockers, not changes to the recommender logic or the MLflow/DVC pipeline:

- duplicate Grafana datasource default provisioning caused startup failure in Grafana
- the backend image was missing `curl`, which prevented the healthcheck command from succeeding

These issues were fixed without altering the project architecture, model logic, or monitoring design.
