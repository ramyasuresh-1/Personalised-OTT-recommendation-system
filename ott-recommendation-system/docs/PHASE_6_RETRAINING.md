# Phase 6: Automated Retraining Pipeline

## Overview

Phase 6 implements an automated retraining pipeline triggered by drift detection from Phase 5. When the system detects data drift and data quality is acceptable, the pipeline automatically:

1. Trains a candidate model
2. Evaluates candidate against champion
3. Applies quality gate to ensure no performance regression
4. Promotes candidate to champion if it passes all checks
5. Logs all metrics to MLflow and Prometheus

This ensures the recommendation engine stays up-to-date with evolving user preferences while maintaining model quality.

## Architecture

### Champion vs Candidate Pattern

The pipeline uses a dual-model architecture:

- **Champion Model**: Current production model serving recommendations
- **Candidate Model**: Newly trained model awaiting approval

Key advantages:
- Safe isolation: Candidate cannot affect production until explicitly promoted
- Easy rollback: Champion remains unchanged if candidate fails quality gate
- Versioning: Each promotion increments model version

### Retraining Trigger

The pipeline executes when **both** conditions are met:

```
should_retrain = (drift_status == "Drifted") AND (data_quality_status != "FAIL")
```

### Component Architecture

```
Drift Detection (Phase 5)
      ↓
  should_retrain()
      ↓
  ├─→ Load Champion
  │
  ├─→ Train Candidate (OTTRecommender)
  │
  ├─→ Evaluate Both Models
  │
  ├─→ Apply Quality Gate
  │      ↓
  │      ├─→ Pass → Promote Candidate
  │      └─→ Fail  → Reject Candidate (Champion unchanged)
  │
  ├─→ Log to MLflow
  │
  └─→ Update Prometheus Metrics
```

## Implementation Details

### Core Module: `backend/app/retraining.py`

#### RetrainingConfig

Configuration dataclass with thresholds:

```python
@dataclass
class RetrainingConfig:
    max_rmse_regression_pct: float = 0.02        # Max 2% RMSE regression allowed
    max_mae_regression_pct: float = 0.02         # Max 2% MAE regression allowed
    max_ndcg_degradation_pct: float = 0.01       # Max 1% NDCG degradation
    min_ndcg_improvement_pct: float = 0.005      # Min 0.5% NDCG improvement
    min_ranking_improvement: bool = True         # Require improved ranking
    drift_threshold: str = "Drifted"             # Trigger drift status
    data_quality_threshold: str = "PASS"         # Minimum quality status
```

#### RetrainingPipeline Class

Main orchestrator with methods:

- `should_retrain() → (bool, str)`: Check if retraining should execute
- `_load_champion() → bool`: Load current champion model
- `_train_candidate() → bool`: Train new candidate model using OTTRecommender
- `_evaluate_model(model, name) → bool`: Compute metrics for given model
- `_apply_quality_gate() → bool`: Compare candidate vs champion metrics
- `_promote_candidate(champion) → bool`: Save candidate as new champion
- `_reject_candidate() → bool`: Clean up candidate and keep champion
- `_log_to_mlflow() → None`: Log run, parameters, metrics to MLflow
- `execute(champion_model) → dict`: Orchestrate full pipeline

#### trigger_retraining() Entry Point

```python
def trigger_retraining(champion_model: OTTRecommender) -> dict:
    """
    Trigger retraining pipeline with duplicate prevention.
    
    Returns:
    {
        "success": bool,
        "promotion_status": "pending" | "accepted" | "rejected",
        "message": str,
        "mlflow_run_id": str | None,
        "candidate_version": str | None,
        "champion_version": str | None
    }
    """
```

## Retraining Workflow

### Step 1: Trigger Condition Check

```python
# API endpoint: POST /api/retrain
if not detect_drift():
    return {"status": "skipped", "message": "Drift status: Healthy..."}

if evaluate_data_quality() == "FAIL":
    return {"status": "skipped", "message": "Data quality is FAIL..."}

# Conditions met - initiate retraining
return {"status": "initiated", "drift_status": "Drifted", ...}
```

### Step 2: Candidate Training

```python
candidate_model = OTTRecommender()
ratings = get_ratings_data()
result = candidate_model.train_model(ratings)
# Returns: {"status": "success", "model_version": "v1.1.0", "mse": 0.95}
```

### Step 3: Model Evaluation

Both models evaluated on test set (last 20% of ratings):

```python
champion_metrics = evaluate_model_state(champion, test_ratings)
candidate_metrics = evaluate_model_state(candidate, test_ratings)

# Metrics include: RMSE, MAE, Precision@5/@10, Recall@5/@10, NDCG@5/@10, etc.
```

### Step 4: Quality Gate

Candidate compared against champion using configured thresholds:

```python
quality_gate_result = quality_gate(
    baseline=champion_metrics,
    candidate=candidate_metrics,
    config=RetrainingConfig()
)

# Returns:
{
    "passed": bool,
    "reasons": [...],
    "rmse_change_pct": float,
    "mae_change_pct": float,
    "ndcg10_change_pct": float,
    ...
}
```

**Quality Gate Criteria**:

- ✓ RMSE regression ≤ 2%
- ✓ MAE regression ≤ 2%
- ✓ NDCG degradation ≤ 1%
- ✓ NDCG improvement ≥ 0.5%
- ✓ Ranking metrics improved

### Step 5: Model Promotion or Rejection

**If Quality Gate Passes**:
```python
# Save candidate as new champion
candidate_model.save_model()  # → backend/models/recommender.pkl
candidate_model.model_version = "v2.0.0"  # Increment version
log_retraining(data_points, mse, "v2.0.0")  # Update retraining history
# → Table: retraining_history with timestamp, version, metrics
```

**If Quality Gate Fails**:
```python
# Delete candidate, keep champion unchanged
candidate_model = None
# Champion remains at v1.0.0
```

## Monitoring & Observability

### MLflow Tracking

Each retraining run logged to MLflow experiment "OTT Recommendation System":

```python
mlflow.start_run(tags={
    "phase": "6",
    "pipeline": "retraining",
    "model_stage": "Champion|Candidate"
})

mlflow.log_params({
    "max_rmse_regression_pct": 0.02,
    "max_mae_regression_pct": 0.02,
    ...
})

mlflow.log_metrics({
    "candidate_rmse": 0.95,
    "champion_rmse": 0.96,
    "rmse_improvement_pct": 1.04,
    ...
})

mlflow.log_tags({
    "drift_status": "Drifted",
    "promotion_status": "accepted",
    "quality_gate_passed": True
})
```

### Prometheus Metrics

12 new Phase 6 metrics exposed at `/metrics`:

**Counters**:
- `retraining_runs_total`: Total retraining attempts
- `retraining_success_total`: Successful retraining runs
- `retraining_failure_total`: Failed retraining runs
- `model_promotion_total`: Successful promotions to champion
- `model_rejection_total`: Rejected candidates

**Gauges**:
- `retraining_in_progress`: 0 (idle) or 1 (training)
- `candidate_model_rmse`: Latest candidate RMSE
- `champion_model_rmse`: Latest champion RMSE
- `current_model_version`: Numeric version of champion
- `drift_detected`: 0 (Healthy) or 1 (Drifted)
- `last_retraining_timestamp`: Unix timestamp of last attempt

**Histograms**:
- `retraining_duration_seconds`: Time taken for full pipeline

### Grafana Dashboards

New "Retraining Pipeline (Phase 6)" section with panels:

- **Retraining Runs**: Counter stat showing total attempts
- **Successful Promotions**: Counter stat showing approved candidates
- **Model Rejections**: Counter stat showing rejected candidates
- **Retraining Success Rate (%)**: Calculated success percentage
- **Retraining Duration**: Time series of pipeline execution times
- **Champion vs Candidate RMSE**: Side-by-side RMSE comparison
- **Current Model Version**: Gauge showing active version
- **Drift Status**: Indicator of current drift condition
- **Last Retraining Time**: Timestamp of most recent attempt

Access at: `http://localhost:3000/d/ott-reco-001`

## Failure Safety Mechanisms

### Champion Protection

1. **Isolation**: Candidate model stored separately (`backend/models/candidate.pkl`)
2. **Atomic Promotion**: Only saved if quality gate passes
3. **Version Control**: Each promotion increments version in MLflow and retraining_history table
4. **Immediate Rollback**: Failed retraining leaves champion untouched

### Error Handling

```python
try:
    # Each step validates success
    if not _load_champion():
        return {"success": False, "promotion_status": "rejected", ...}
    
    if not _train_candidate():
        return {"success": False, "promotion_status": "rejected", ...}
    
    if not _apply_quality_gate():
        # Champion remains unchanged
        _reject_candidate()
        return {"success": True, "promotion_status": "rejected", ...}
    
    # Only promote if all checks pass
    _promote_candidate(champion)
    
except Exception as e:
    # Log error and return failure
    log_error(e)
    return {"success": False, ...}
```

### Duplicate Prevention

Global lock prevents simultaneous retraining:

```python
_RETRAINING_LOCK = False

def trigger_retraining(model):
    global _RETRAINING_LOCK
    if _RETRAINING_LOCK:
        return {"success": False, "message": "Retraining already in progress"}
    
    _RETRAINING_LOCK = True
    try:
        return RetrainingPipeline().execute(model)
    finally:
        _RETRAINING_LOCK = False
```

## API Endpoints

### POST /api/retrain

Manually trigger retraining (or auto-trigger from background task):

**Request**:
```json
{}
```

**Response (No Drift)**:
```json
{
    "status": "skipped",
    "message": "Drift status: Healthy (expected: Drifted)",
    "drift_status": "Healthy",
    "data_quality_status": "PASS"
}
```

**Response (Poor Quality)**:
```json
{
    "status": "skipped",
    "message": "Data quality is FAIL. Cannot retrain with degraded data.",
    "drift_status": "Drifted",
    "data_quality_status": "FAIL"
}
```

**Response (Retraining Initiated)**:
```json
{
    "status": "initiated",
    "message": "Retraining initiated",
    "drift_status": "Drifted",
    "data_quality_status": "PASS"
}
```

### GET /api/monitoring/metrics

Enhanced with Phase 6 status:

```
# HELP retraining_runs_total Total retraining runs attempted
# TYPE retraining_runs_total counter
retraining_runs_total 5

# HELP model_promotion_total Successful model promotions
# TYPE model_promotion_total counter
model_promotion_total 3

# HELP retraining_in_progress Indicates if retraining is in progress
# TYPE retraining_in_progress gauge
retraining_in_progress 0

# HELP current_model_version Current champion model version
# TYPE current_model_version gauge
current_model_version 1.1

# HELP drift_detected Current drift status
# TYPE drift_detected gauge
drift_detected 0

# Plus 6 more Phase 6 metrics...
```

## Testing

### Unit Tests (14 scenarios in `backend/tests/test_phase6_retraining.py`)

**Trigger Logic**:
- ✓ Retraining triggered when drift="Drifted" and quality="PASS"
- ✓ Retraining skipped when drift="Healthy"
- ✓ Retraining skipped when quality="FAIL"

**Pipeline Execution**:
- ✓ Pipeline skips when no drift detected
- ✓ Drift information recorded in pipeline state

**Quality Gate**:
- ✓ Candidate promoted when passing quality gate
- ✓ Candidate rejected when failing quality gate

**Model Promotion**:
- ✓ Model version incremented on promotion
- ✓ Champion unchanged on rejection

**Safety**:
- ✓ Duplicate retraining prevented by lock
- ✓ Training failure leaves champion unchanged
- ✓ Evaluation failure handled gracefully

**Test Suite Status**: 14/14 passing ✓

### Integration Testing

Manual E2E flow:

```bash
# 1. Inject drift signal
curl -X POST http://localhost:8000/api/simulate-drift

# 2. Trigger retraining
curl -X POST http://localhost:8000/api/retrain

# 3. Verify in Prometheus
curl http://localhost:9090/api/v1/query?query=retraining_runs_total

# 4. Check Grafana dashboard
# http://localhost:3000/d/ott-reco-001?refresh=5s

# 5. Inspect MLflow runs
# http://localhost:5000/
```

## Deployment

### Docker Compose

Updated service configuration:

```yaml
backend:
  # No changes - Phase 6 runs within existing FastAPI service
  environment:
    - MLFLOW_TRACKING_URI=http://mlflow-ui:5000
    - PROMETHEUS_ENABLED=true

prometheus:
  # Updated prometheus.yml to scrape Phase 6 metrics
  # No changes to port or configuration

grafana:
  # Updated dashboard JSON with Phase 6 panels
  # No changes to configuration

mlflow-ui:
  # Existing MLflow tracking unchanged
```

### Health Check

Verify Phase 6 operational:

```bash
# 1. Check backend health
curl http://localhost:8000/api/health
# → {"status": "healthy", "timestamp": "..."}

# 2. Check retraining endpoint
curl http://localhost:8000/api/retrain
# → {"status": "skipped"|"initiated", ...}

# 3. Check Prometheus metrics
curl http://localhost:9090/api/v1/query?query=retraining_runs_total
# → Should return metric value >= 0

# 4. Check Grafana dashboard loads
# http://localhost:3000/d/ott-reco-001
```

## Constraints & Assumptions

### Fixed Per Specification

- ✓ **Funk SVD Unchanged**: Does NOT replace recommender.py algorithm
- ✓ **MLflow Preserved**: Phase 6 logs to same MLflow instance as Phase 3-5
- ✓ **DVC Preserved**: Model versioning tracked in Git/DVC
- ✓ **Prometheus/Grafana**: Phase 4-5 metrics remain unchanged
- ✓ **Quality Gate**: Uses Phase 3 evaluation thresholds exactly

### Data Schema

- **Model Storage**: `backend/models/recommender.pkl` (champion)
- **Candidate Storage**: `backend/models/candidate.pkl` (temporary)
- **Retraining History**: SQLite `retraining_history` table with:
  - `timestamp`: Attempt time
  - `data_points`: Samples used for training
  - `mse`: Training MSE
  - `model_version`: Promoted version (if successful)
  - `promotion_status`: "accepted" or "rejected"

### Phase Interaction

- **Phase 5 → Phase 6**: Drift signal triggers pipeline
- **Phase 6 → Phase 4**: Prometheus metrics updated
- **Phase 6 → MLflow**: All runs logged to existing experiment
- **Phase 3 ↔ Phase 6**: Quality gate logic reused without modification

## Usage Examples

### Automated Retraining (Production)

```python
# In bg_retrain_task() called by FastAPI startup
while True:
    result = trigger_retraining(recommender)
    print(f"Retraining result: {result['promotion_status']}")
    # Logs to MLflow, updates Prometheus, checks drift from Phase 5
    time.sleep(3600)  # Check hourly
```

### Manual Triggering (Operations)

```bash
# Check if drift detected and quality acceptable
curl http://localhost:8000/api/monitoring/metrics | grep drift_detected

# If drift_detected=1 and quality=PASS, trigger retraining
curl -X POST http://localhost:8000/api/retrain

# Monitor progress in Grafana
# http://localhost:3000/d/ott-reco-001?refresh=5s
```

### Inspection (Debugging)

```bash
# View all retraining runs in MLflow
mlflow run ls --experiment-name "OTT Recommendation System" --tags phase=6

# Check model versions
sqlite3 backend/data/ott_recommendation.db \
  "SELECT * FROM retraining_history ORDER BY timestamp DESC LIMIT 5;"

# Inspect Prometheus metrics
curl http://localhost:9090/api/v1/query_range?query=retraining_duration_seconds
```

## Troubleshooting

### Retraining Not Triggering

1. Check drift status:
   ```bash
   curl http://localhost:8000/api/monitoring/metrics | grep drift_detected
   ```

2. Check data quality:
   ```bash
   curl http://localhost:8000/api/monitoring/metrics | grep data_quality
   ```

3. Check for lock:
   ```
   # If stuck: restart backend service
   docker-compose restart backend
   ```

### Quality Gate Always Failing

1. Verify Phase 3 thresholds in `backend/app/evaluation.py`:
   - max_rmse_regression_pct = 0.02 (2%)
   - max_mae_regression_pct = 0.02 (2%)

2. Check if candidate training producing worse metrics:
   ```bash
   # View candidate metrics in MLflow UI
   http://localhost:5000/
   ```

3. May need to adjust thresholds or retrain with more data

### Champion Model Stuck at Old Version

1. Check retraining history:
   ```bash
   sqlite3 backend/data/ott_recommendation.db \
     "SELECT * FROM retraining_history WHERE promotion_status='rejected';"
   ```

2. If too many rejections, data quality or training may have issues
3. Manually review Phase 5 drift detection for false positives

## Success Criteria

Phase 6 COMPLETE when:

✓ Tasks 1-16 all implemented
✓ All 66 unit/integration tests passing (52 Phase 4-5 + 14 Phase 6)
✓ Docker Compose validates (5 services healthy)
✓ E2E test executes drift → train → evaluate → gate → promote/reject workflow
✓ Grafana dashboard displays all Phase 6 retraining panels
✓ MLflow experiment contains retraining runs with tags and metrics
✓ Prometheus exposes 12 new Phase 6 metrics
✓ Champion model protection verified (no changes on rejection)
✓ Duplicate retraining prevented by lock mechanism
✓ PHASE_6_RETRAINING.md documents all architecture and usage

## References

- [Phase 3: Model Evaluation & Quality Gate](docs/PHASE_3_MODEL_EVALUATION.md)
- [Phase 4: Prometheus Monitoring](docs/PHASE_4_MONITORING.md)
- [Phase 5: Drift Detection](docs/PHASE_5_DRIFT_DETECTION.md)
- [MLflow Docs](https://mlflow.org/docs/latest/)
- [Evidently AI Drift Detection](https://docs.evidentlyai.com/)
