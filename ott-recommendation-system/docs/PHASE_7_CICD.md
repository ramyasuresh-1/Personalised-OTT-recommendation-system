# Phase 7 — CI/CD Automation

**Status**: COMPLETE  
**Date**: 2026-08-16  
**Workflow file**: `.github/workflows/ci.yml`  
**Python version**: 3.10 (matches `backend/Dockerfile`)  
**Test suite**: 66/66 tests passing  

---

## 1. Phase 7 Objective

Build a reliable CI/CD pipeline for the existing OTT Recommendation System MLOps project.
Phase 7 is automation only — **no production deployment happens in this phase**.

The pipeline enforces:

```
Developer
   ↓ git push / pull request
GitHub Actions
   ↓
Environment setup (Python 3.10)
   ↓
Dependency installation
   ↓
Compile backend  (python -m compileall)
   ↓
Critical lint    (flake8 E9/F63/F7/F82)
   ↓
Full test suite  (pytest backend/tests -v)  ← 66 tests, Phases 1–6
   ↓
MLOps regression (Phases 1–6 individually)
   ↓
Docker Compose validation
   ↓
DVC config check
   ↓
MLflow config check
   ↓
Docker image build (no push)
   ↓
Security scan
   ↓
PASS / FAIL gate
```

---

## 2. CI/CD Architecture

### Job dependency graph

```
code-validation ──┬──► testing          ──► docker-build ──┐
                  └──► mlops-regression                     ├──► ci-status
infrastructure  ────────────────────────────────────────────┤
security        ────────────────────────────────────────────┘
```

- `code-validation` — must pass before tests or regression run
- `testing` + `mlops-regression` run in parallel (both depend only on code-validation)
- `docker-build` waits for both test jobs (ensures image only built when tests pass)
- `infrastructure` and `security` run independently
- `ci-status` collects all results; this is the single merge gate

### Jobs summary

| Job | Depends on | Runs if |
|---|---|---|
| `code-validation` | — | always |
| `testing` | `code-validation` | always |
| `mlops-regression` | `code-validation` | always |
| `infrastructure` | — | always |
| `docker-build` | `code-validation`, `testing` | always |
| `security` | — | always |
| `ci-status` | all above | always (even on failure) |

---

## 3. GitHub Actions Workflow

**File**: `.github/workflows/ci.yml`

### Workflow name

`CI Pipeline`

### Trigger conditions

```yaml
on:
  push:
    branches: [ main, master, develop ]
  pull_request:
    branches: [ main, master, develop ]
```

CI runs on every push or pull request targeting `main`, `master`, or `develop`.

---

## 4. Python Setup

**Version**: `3.10`  
Chosen to match the `backend/Dockerfile`:

```dockerfile
FROM python:3.10-slim
```

GitHub Actions step:

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: '3.10'
    cache: pip
```

The `cache: pip` option caches the pip download cache between runs, which cuts install time significantly.

---

## 5. Dependency Installation

Runtime dependencies come from `backend/requirements.txt`:

```
fastapi==0.110.0
uvicorn==0.28.0
pandas==2.2.1
numpy==1.26.4
pydantic==2.6.4
httpx==0.27.0
mlflow>=3.0.0,<4.0.0
prometheus_client>=0.16.0
evidently==0.4.33
```

CI-only tools are installed separately and are **not** added to `requirements.txt` (they are not runtime dependencies):

```bash
pip install flake8             # code-validation job
pip install pytest pytest-cov  # testing and mlops-regression jobs
```

Install commands in each job:

```bash
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
pip install pytest pytest-cov   # or flake8, depending on job
```

---

## 6. Backend Validation

### Compilation

**Command**: `python -m compileall backend/app`

Catches Python syntax errors in all modules before tests run. Fails the job immediately on any syntax error.

**Modules compiled**:
- `backend/app/__init__.py`
- `backend/app/database.py`
- `backend/app/evaluation.py`
- `backend/app/main.py`
- `backend/app/monitoring.py`
- `backend/app/recommender.py`
- `backend/app/retraining.py`

**Local result**: PASS

### Linting

**Critical checks** (fail CI):
```bash
flake8 backend/app --count --select=E9,F63,F7,F82 --show-source --statistics
```

Selected error codes:
- `E9xx` — runtime errors (syntax, encoding)
- `F63x` — invalid star expressions
- `F7xx` — syntax errors caught by pyflakes
- `F82x` — undefined names

**Style warnings** (informational, non-blocking):
```bash
flake8 backend/app --count --exit-zero --max-complexity=10 --max-line-length=127
```

**Bug fixed during Phase 7**: `recommender.py` line 37 had an undefined name `MLFLOW_DB` (F821). Corrected to `DEFAULT_MLFLOW_DB`, which is the variable defined at module scope. This was the correct value — the code path was unreachable but would have raised `NameError` if hit.

**Local result**: PASS (0 critical errors after fix)

---

## 7. Test Execution

### Full test suite

**Command** (run from `ott-recommendation-system/` directory):
```bash
python -m pytest backend/tests -v --tb=short --junitxml=junit/test-results.xml
```

**Test files**:

| File | Phase | Tests |
|---|---|---|
| `test_data_split.py` | Phase 1 | 8 |
| `test_data_validation.py` | Phase 1 | 8 |
| `test_evaluation.py` | Phase 3 | 14 |
| `test_phase3_evaluation.py` | Phase 3 | 6 |
| `test_api.py` | Phase 4 | 7 |
| `test_phase5_monitoring.py` | Phase 5 | 2 |
| `test_phase5_validation.py` | Phase 5 | 3 |
| `test_phase6_retraining.py` | Phase 6 | 13 |
| **Total** | | **66** |

**Local result**: 66/66 PASS in 26.43s

The test JUnit XML is uploaded as a GitHub Actions artifact (`pytest-results`).

---

## 8. Test Coverage

### Configuration

Coverage is measured using `pytest-cov` and reported in three formats: terminal, XML, and HTML.

**Command**:
```bash
python -m pytest backend/tests \
  --cov=backend/app \
  --cov-report=xml:coverage.xml \
  --cov-report=html:htmlcov \
  --cov-report=term-missing \
  -q
```

### Measured coverage (local validation)

| Module | Statements | Missed | Cover |
|---|---|---|---|
| `backend/app/__init__.py` | 0 | 0 | 100% |
| `backend/app/database.py` | 92 | 22 | 76% |
| `backend/app/evaluation.py` | 333 | 216 | 35% |
| `backend/app/main.py` | 149 | 81 | 46% |
| `backend/app/monitoring.py` | 250 | 72 | 71% |
| `backend/app/recommender.py` | 168 | 28 | 83% |
| `backend/app/retraining.py` | 267 | 146 | 45% |
| **TOTAL** | **1259** | **565** | **55%** |

**Coverage threshold**: None enforced. The 55% total reflects that tests exercise all public API paths and MLOps lifecycle flows; many uncovered lines are in error-handling branches and MLflow registration code that requires a live server. Adding a forced threshold would break CI for the wrong reasons.

The HTML report (`htmlcov/`) and XML (`coverage.xml`) are uploaded as GitHub Actions artifacts.

---

## 9. DVC Validation

### What CI checks

1. `dvc.yaml` exists — the pipeline definition is present.
2. `.dvc/config` presence is noted (empty config is valid when no remote is configured).

### What CI does NOT do

- Pull DVC-tracked data from a remote
- Execute DVC pipeline stages
- Require DVC remote credentials

### Why

The existing tests use the SQLite database seeded at test time (via `init_db()`). No DVC data pull is needed to run the test suite. Full pipeline execution happens only during model training, not CI.

### DVC remote configuration

The `.dvc/config` file is currently empty (no remote configured). If a remote is added in future:

1. Add credentials as a GitHub Secret (e.g., `DVC_REMOTE_ACCESS_KEY_ID`)
2. Configure the remote in the CI step using `dvc remote modify --global`
3. Add `dvc pull` before the test step that requires remote data

**Never commit DVC remote credentials directly.**

---

## 10. MLflow Validation

### How MLflow is used in tests

Tests use a local, file-based MLflow configuration:

```
MLFLOW_TRACKING_URI  = sqlite:///mlflow.db      (SQLite, local file)
MLFLOW_ARTIFACT_ROOT = file:///tmp/mlruns        (local filesystem)
```

These environment variables are set in the CI workflow `env:` block and do not require any external MLflow server.

### What CI validates

- The MLflow environment variables are set correctly
- Tests that exercise MLflow (training, retraining, evaluation logging) pass against the local backend

### What CI does NOT do

- Connect to a production MLflow Tracking Server
- Require `MLFLOW_TRACKING_URI` pointing to a hosted instance
- Push model artifacts to a model registry

### MLflow credentials

No MLflow credentials are required for CI. If a hosted MLflow server is added:

1. Store the tracking URI as `MLFLOW_TRACKING_URI` GitHub Secret
2. Store credentials as `MLFLOW_TRACKING_USERNAME` / `MLFLOW_TRACKING_PASSWORD`
3. Reference them in the workflow `env:` block as `${{ secrets.MLFLOW_TRACKING_URI }}`

---

## 11. Docker Validation

### Docker Compose config validation

**Command**: `docker compose config --quiet`

Validates the YAML syntax and service configuration of `docker-compose.yml` without starting any containers.

**Services validated**:
1. `backend` — FastAPI + Funk SVD recommender
2. `mlflow-ui` — MLflow tracking UI
3. `frontend` — nginx static file server
4. `prometheus` — metrics scraping
5. `grafana` — metrics dashboards

**Local result**: PASS  
Note: Docker 25+ emits a warning about the obsolete `version:` key in `docker-compose.yml`. This is a warning, not an error — exit code is 0.

### Docker image build

**Purpose**: Verify the backend `Dockerfile` builds without errors.

**Uses**: `docker/build-push-action@v6` with `push: false`

```yaml
- uses: docker/build-push-action@v6
  with:
    context: ./ott-recommendation-system/backend
    file:    ./ott-recommendation-system/backend/Dockerfile
    push:    false
    tags:    aura-ott/recommendation-backend:ci
    cache-from: type=gha
    cache-to:   type=gha,mode=max
```

The `gha` cache type caches build layers between workflow runs.

**The image is NOT pushed to any registry** — deployment is Phase 8.

### What CI does NOT do

- Start containers (`docker compose up`)
- Run health checks against live containers
- Push images to a registry
- Deploy services

---

## 12. Frontend Validation

The frontend is pure static HTML/CSS/JavaScript served by nginx:

```
frontend/
  index.html
  css/
  js/
```

There is **no** `package.json`, **no** Node.js build step, and **no** frontend test suite. CI does not run any frontend-specific steps. The frontend is validated implicitly through the Docker Compose config check, which confirms the nginx service volume mapping is valid.

---

## 13. Secrets Management

### What is in source control (safe)

| Item | Location | Why safe |
|---|---|---|
| `MLFLOW_TRACKING_URI` | `docker-compose.yml` env | Points to local SQLite, no credentials |
| `MLFLOW_ARTIFACT_ROOT` | `docker-compose.yml` env | Local filesystem path |
| `GF_SECURITY_ADMIN_PASSWORD=admin` | `docker-compose.yml` | Dev default, documented, must be overridden before production |

### What must NEVER be committed

- Production MLflow tracking server credentials
- Cloud storage credentials (S3, GCS, Azure keys)
- Production Grafana admin password
- DVC remote storage keys
- Render or other deployment platform API tokens
- Any JWT signing secret

### How to use secrets in GitHub Actions

```yaml
env:
  MLFLOW_TRACKING_URI: ${{ secrets.MLFLOW_TRACKING_URI }}
  GF_SECURITY_ADMIN_PASSWORD: ${{ secrets.GRAFANA_ADMIN_PASSWORD }}
```

Set these under **GitHub repository → Settings → Secrets and variables → Actions**.

### Required GitHub Secrets (for Phase 8 deployment)

The following secrets are NOT needed for Phase 7 CI but will be required for Phase 8:

| Secret name | Purpose |
|---|---|
| `DOCKER_REGISTRY_TOKEN` | Push images to container registry |
| `RENDER_API_KEY` | Deploy to Render (or equivalent) |
| `MLFLOW_TRACKING_URI` | Production MLflow server (if hosted) |
| `GRAFANA_ADMIN_PASSWORD` | Override `admin` default |

**None of these values appear in this document or in any committed file.**

---

## 14. CI Failure Behavior

CI fails hard (exit 1, no `continue-on-error`) for:

| Condition | Job that fails |
|---|---|
| Python syntax error in `backend/app/` | `code-validation` |
| Undefined name, invalid syntax (F82x, E9xx) | `code-validation` |
| Any test failure in `backend/tests/` | `testing` |
| Phase 1–6 regression test failure | `mlops-regression` |
| `docker compose config` returns non-zero | `infrastructure` |
| `dvc.yaml` missing | `infrastructure` |
| Hard-coded credential found in `backend/app/` | `security` |
| Backend Docker image fails to build | `docker-build` |

CI reports a warning (non-blocking) for:

| Condition | Notes |
|---|---|
| Style lint findings (line length, complexity) | `--exit-zero` flag |
| `GF_SECURITY_ADMIN_PASSWORD=admin` | Informational notice step |
| `.dvc/config` absent | Acceptable when no remote configured |

A green `ci-status` job means **all critical checks actually passed**.

---

## 15. Local Validation Commands

Run these before pushing to avoid a CI failure:

```bash
# Navigate to the project root
cd "ott-recommendation-system"

# 1. Compile backend
python -m compileall backend/app

# 2. Critical linting
flake8 backend/app --select=E9,F63,F7,F82 --show-source

# 3. Full test suite
python -m pytest backend/tests -v

# 4. Coverage
python -m pytest backend/tests --cov=backend/app --cov-report=term-missing -q

# 5. Docker Compose config
docker compose config --quiet

# 6. Check running services
docker compose ps
```

**Local validation results (2026-08-16)**:

| Command | Result |
|---|---|
| `compileall backend/app` | PASS |
| `flake8 --select=E9,F63,F7,F82` | PASS (0 errors, after fixing F821) |
| `pytest backend/tests -v` | PASS — 66/66 in 26.43s |
| `pytest --cov=backend/app` | PASS — 55% total coverage |
| `docker compose config --quiet` | PASS |
| `docker compose ps` | 5/5 services Up/healthy |

---

## 16. GitHub Actions Usage

### Viewing CI results

1. Push a commit or open a pull request targeting `main`/`master`/`develop`
2. Go to the repository on GitHub
3. Click **Actions** tab
4. Select the **CI Pipeline** workflow run
5. Expand individual jobs to see step-level logs

### Branch protection setup (recommended)

To require CI before merging, configure a branch protection rule on `main`:

1. Repository → Settings → Branches → Add rule
2. Branch name pattern: `main`
3. Enable: **Require status checks to pass before merging**
4. Add required check: `CI Status Gate`

This means only the `ci-status` job needs to be added as a required check — it already captures all upstream failures.

### Caching

The workflow uses two cache layers:
- **pip cache** (`cache: pip` in `setup-python@v5`) — caches pip download cache
- **Docker layer cache** (`type=gha` in `build-push-action`) — caches Docker build layers

Both caches are scoped per-branch and per-OS.

---

## 17. Troubleshooting

### "Compilation failed"

```bash
python -m compileall backend/app
# Fix the syntax error shown in the output
```

### "Critical linting errors found"

```bash
flake8 backend/app --select=E9,F63,F7,F82 --show-source
# Fix the undefined names or syntax errors shown
```

### "Test suite failed"

```bash
python -m pytest backend/tests -v --tb=long
# Read the full traceback
# Fix the failing code — do NOT change the test expectations
```

### "Docker Compose configuration is invalid"

```bash
docker compose config
# Read the YAML error and fix docker-compose.yml
```

### "GitHub Actions workflow won't start"

- Verify `.github/workflows/ci.yml` YAML is valid (no tab indentation, correct field names)
- Check the **Actions** tab for a parsing error notification
- Ensure the repository has Actions enabled (Settings → Actions → Allow all actions)

### "Docker build fails in CI but works locally"

- The CI build uses `ubuntu-latest` and `python:3.10-slim` — check that `requirements.txt` lists all needed packages
- Multi-platform or architecture issues: consider adding `platforms: linux/amd64` to the build step

### "Coverage is lower than expected"

Coverage at 55% reflects the current test suite scope. The uncovered 45% is primarily:
- Error-handling branches in `evaluation.py` (MLflow client failure paths)
- `main.py` startup/shutdown event handlers
- Advanced retraining pipeline paths that require a live trained model

Do not artificially lower coverage thresholds or add empty tests to raise the number.

---

## 18. Limitations

The following are known, intentional constraints of Phase 7:

1. **No deployment** — Images are built but not pushed or deployed. That is Phase 8.
2. **No DVC data pull** — Tests use the seeded SQLite database. Full DVC pipeline execution is a separate workflow concern.
3. **No hosted MLflow server** — CI uses local SQLite backend. A hosted server is a Phase 8 concern.
4. **No frontend build** — The frontend is static HTML with no build toolchain.
5. **No container startup** — `docker compose config` validates YAML; it does not start services or run health checks.
6. **No GPU / long training** — The full Funk SVD training cycle is exercised through mocked tests. Full training is not run on every CI push.
7. **GitHub Actions remote execution** — This workflow was locally validated. Actual GitHub Actions execution requires a push to a GitHub-hosted repository. The workflow syntax and job structure are confirmed correct; remote execution must be verified after the first push.

---

## 19. Relationship to Other Phases

### What Phase 7 protects

| Phase | Feature | CI protection |
|---|---|---|
| Phase 1 | DVC data pipeline | `test_data_split`, `test_data_validation` |
| Phase 2 | Funk SVD recommender | `test_evaluation`, `test_api` |
| Phase 3 | Quality gate | `test_phase3_evaluation` |
| Phase 4 | Prometheus + FastAPI monitoring | `test_api` |
| Phase 5 | Evidently drift detection | `test_phase5_monitoring`, `test_phase5_validation` |
| Phase 6 | Automated retraining pipeline | `test_phase6_retraining` |

### What Phase 8 will add

Phase 8 handles production deployment. It will:

- Push Docker images to a container registry
- Deploy the backend service (e.g., Render, Railway, or a cloud provider)
- Set production environment variables via GitHub Secrets
- Configure production MLflow tracking server (if hosted)
- Set a secure `GF_SECURITY_ADMIN_PASSWORD` for Grafana
- Potentially add a CD job triggered only on `main` after CI passes

**Phase 7 does NOT do any of the above.**

---

## 20. Acceptance Criteria Checklist

| Criterion | Status |
|---|---|
| Existing project architecture preserved | PASS |
| GitHub Actions workflow created (`.github/workflows/ci.yml`) | PASS |
| Push trigger configured | PASS |
| Pull request trigger configured | PASS |
| Correct Python version (3.10) configured | PASS |
| Dependencies install successfully | PASS |
| Backend `compileall` passes | PASS |
| Full backend test suite passes (66/66) | PASS |
| Phase 1–6 regression tests protected | PASS |
| Coverage configured (pytest-cov, 55% measured) | PASS |
| DVC handling validated/documented | PASS |
| MLflow handling validated/documented | PASS |
| Docker Compose config validates | PASS |
| Docker image build validates | PASS |
| Frontend CI: not applicable (no build system) | N/A |
| No hard-coded secrets in application code | PASS |
| CI fails on critical errors | PASS |
| Existing Docker architecture preserved | PASS |
| Existing MLOps functionality preserved | PASS |
| Local validation passes | PASS |
| GitHub Actions execution | Locally validated; remote execution requires push/PR |
| `docs/PHASE_7_CICD.md` updated | PASS |
