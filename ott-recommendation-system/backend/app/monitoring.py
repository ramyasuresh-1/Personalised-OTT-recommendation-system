import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from evidently.metric_preset import DataQualityPreset, DataDriftPreset
from evidently.report import Report
from .database import get_ratings_data, get_all_movies

# Prometheus registry for this FastAPI app
registry = CollectorRegistry()

# HTTP metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "http_status"],
    registry=registry
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    registry=registry,
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)
http_request_errors_total = Counter(
    "http_request_errors_total",
    "Total HTTP requests resulting in client or server errors",
    ["endpoint", "http_status"],
    registry=registry
)

# Recommendation metrics
recommendation_requests_total = Counter(
    "recommendation_requests_total",
    "Total recommendation requests received",
    ["status"],
    registry=registry
)
recommendation_errors_total = Counter(
    "recommendation_errors_total",
    "Total recommendation request failures",
    registry=registry
)
recommendation_latency_seconds = Histogram(
    "recommendation_latency_seconds",
    "Recommendation endpoint latency in seconds",
    registry=registry,
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5]
)
recommendations_generated_total = Counter(
    "recommendations_generated_total",
    "Total number of recommendations generated",
    registry=registry
)
cold_start_recommendations_total = Counter(
    "cold_start_recommendations_total",
    "Total cold-start recommendation requests",
    registry=registry
)
known_user_recommendations_total = Counter(
    "known_user_recommendations_total",
    "Total known-user recommendation requests",
    registry=registry
)

# Model and training metrics
model_info = Gauge(
    "model_info",
    "Active model version information",
    ["version", "stage"],
    registry=registry
)
model_training_runs_total = Counter(
    "model_training_runs_total",
    "Total model training runs executed",
    registry=registry
)
model_training_failures_total = Counter(
    "model_training_failures_total",
    "Total failed model training runs",
    registry=registry
)
model_training_duration_seconds = Histogram(
    "model_training_duration_seconds",
    "Duration of model training in seconds",
    registry=registry,
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]
)
model_training_samples = Gauge(
    "model_training_samples",
    "Number of training samples used in latest training run",
    registry=registry
)
model_training_mse = Gauge(
    "model_training_mse",
    "Training MSE from the latest model training run",
    registry=registry
)

# Dataset metrics
dataset_ratings_total = Gauge(
    "dataset_ratings_total",
    "Total number of ratings in the dataset",
    registry=registry
)
dataset_movies_total = Gauge(
    "dataset_movies_total",
    "Total number of movies in the dataset",
    registry=registry
)
dataset_users_total = Gauge(
    "dataset_users_total",
    "Total number of users in the dataset",
    registry=registry
)

# Model quality metrics
model_rmse = Gauge(
    "model_rmse",
    "Latest model root mean squared error",
    registry=registry
)
model_mae = Gauge(
    "model_mae",
    "Latest model mean absolute error",
    registry=registry
)
model_precision_at_k = Gauge(
    "model_precision_at_k",
    "Latest model precision at K",
    ["k"],
    registry=registry
)
model_recall_at_k = Gauge(
    "model_recall_at_k",
    "Latest model recall at K",
    ["k"],
    registry=registry
)
model_f1_at_k = Gauge(
    "model_f1_at_k",
    "Latest model F1 score at K",
    ["k"],
    registry=registry
)
model_ndcg_at_k = Gauge(
    "model_ndcg_at_k",
    "Latest model NDCG at K",
    ["k"],
    registry=registry
)
model_hit_rate_at_k = Gauge(
    "model_hit_rate_at_k",
    "Latest model hit rate at K",
    ["k"],
    registry=registry
)
model_coverage = Gauge(
    "model_coverage",
    "Latest recommendation coverage",
    registry=registry
)
model_diversity = Gauge(
    "model_diversity",
    "Latest recommendation diversity",
    registry=registry
)

# Phase 6 Retraining metrics
retraining_runs_total = Counter(
    "retraining_runs_total",
    "Total retraining pipeline executions",
    registry=registry
)
retraining_success_total = Counter(
    "retraining_success_total",
    "Total successful retraining runs (model promoted)",
    registry=registry
)
retraining_failure_total = Counter(
    "retraining_failure_total",
    "Total failed retraining runs (candidate rejected or error)",
    registry=registry
)
retraining_duration_seconds = Histogram(
    "retraining_duration_seconds",
    "Duration of retraining pipeline execution",
    registry=registry,
    buckets=[5, 10, 30, 60, 120, 300, 600, 1200]
)
retraining_in_progress = Gauge(
    "retraining_in_progress",
    "Flag indicating if retraining is currently running (1=yes, 0=no)",
    registry=registry
)
candidate_model_rmse = Gauge(
    "candidate_model_rmse",
    "Candidate model RMSE from latest retraining attempt",
    registry=registry
)
champion_model_rmse = Gauge(
    "champion_model_rmse",
    "Current champion model RMSE",
    registry=registry
)
model_promotion_total = Counter(
    "model_promotion_total",
    "Total successful model promotions (candidate → champion)",
    registry=registry
)
model_rejection_total = Counter(
    "model_rejection_total",
    "Total rejected candidates (quality gate failure)",
    registry=registry
)
current_model_version = Gauge(
    "current_model_version_info",
    "Information about current deployed model version",
    ["version", "stage"],
    registry=registry
)
last_retraining_timestamp = Gauge(
    "last_retraining_timestamp",
    "Timestamp of last retraining attempt (Unix time)",
    registry=registry
)
drift_detected = Gauge(
    "drift_detected",
    "Flag indicating if drift was detected in latest check (1=drifted, 0=healthy)",
    registry=registry
)

_current_model_version = None
_current_model_stage = None


def generate_latest_metrics() -> bytes:
    return generate_latest(registry)


def instrument_http_request(method: str, endpoint: str, status_code: int, duration_seconds: float) -> None:
    endpoint_label = endpoint or "unknown"
    http_requests_total.labels(method=method, endpoint=endpoint_label, http_status=str(status_code)).inc()
    http_request_duration_seconds.labels(method=method, endpoint=endpoint_label).observe(duration_seconds)
    if status_code >= 400:
        http_request_errors_total.labels(endpoint=endpoint_label, http_status=str(status_code)).inc()


def record_recommendation_success(latency_seconds: float, recommendations_count: int, cold_start: bool) -> None:
    recommendation_requests_total.labels(status="success").inc()
    recommendation_latency_seconds.observe(latency_seconds)
    recommendations_generated_total.inc(recommendations_count)
    if cold_start:
        cold_start_recommendations_total.inc()
    else:
        known_user_recommendations_total.inc()


def record_recommendation_error() -> None:
    recommendation_requests_total.labels(status="failure").inc()
    recommendation_errors_total.inc()


def record_training_run(duration_seconds: float, samples: int, mse: float) -> None:
    model_training_runs_total.inc()
    model_training_duration_seconds.observe(duration_seconds)
    model_training_samples.set(samples)
    model_training_mse.set(mse)


def record_training_failure() -> None:
    model_training_failures_total.inc()


# Phase 6 Retraining Metrics Functions

def record_retraining_start() -> None:
    """Record start of retraining pipeline."""
    retraining_runs_total.inc()
    retraining_in_progress.set(1)
    last_retraining_timestamp.set(time.time() if hasattr(time, 'time') else 0)


def record_retraining_end(success: bool, duration_seconds: float) -> None:
    """Record end of retraining pipeline."""
    retraining_in_progress.set(0)
    retraining_duration_seconds.observe(duration_seconds)
    if success:
        retraining_success_total.inc()
    else:
        retraining_failure_total.inc()


def record_model_promotion(candidate_version: str, champion_version: str) -> None:
    """Record successful model promotion."""
    model_promotion_total.inc()
    current_model_version.labels(version=candidate_version, stage="champion").set(1)


def record_model_rejection() -> None:
    """Record rejected candidate model."""
    model_rejection_total.inc()


def update_candidate_champion_metrics(candidate_rmse: float, champion_rmse: float) -> None:
    """Update RMSE metrics for candidate vs champion comparison."""
    candidate_model_rmse.set(candidate_rmse)
    champion_model_rmse.set(champion_rmse)


def update_drift_metric(drift_status: str) -> None:
    """Update drift detection metric."""
    drift_detected.set(1 if drift_status == "Drifted" else 0)


# Import time for retraining timestamp
import time


def update_model_info(version: str, stage: str = "active") -> None:
    global _current_model_version, _current_model_stage
    if _current_model_version is not None and _current_model_stage is not None:
        try:
            model_info.remove(version=_current_model_version, stage=_current_model_stage)
        except KeyError:
            pass
    model_info.labels(version=version, stage=stage).set(1)
    _current_model_version = version
    _current_model_stage = stage


def refresh_dataset_metrics() -> None:
    ratings = get_ratings_data()
    movies = get_all_movies()
    dataset_ratings_total.set(len(ratings))
    dataset_movies_total.set(len(movies))
    dataset_users_total.set(len({rating["user_id"] for rating in ratings}))


def update_model_quality_metrics(metrics: Dict[str, Any]) -> None:
    model_rmse.set(metrics.get("rmse", 0.0))
    model_mae.set(metrics.get("mae", 0.0))
    model_coverage.set(metrics.get("catalog_coverage", 0.0))
    model_diversity.set(metrics.get("recommendation_diversity", 0.0))

    for k, value in metrics.get("precision", {}).items():
        model_precision_at_k.labels(k=k).set(value)
    for k, value in metrics.get("recall", {}).items():
        model_recall_at_k.labels(k=k).set(value)
    for k, value in metrics.get("f1", {}).items():
        model_f1_at_k.labels(k=k).set(value)
    for k, value in metrics.get("ndcg", {}).items():
        model_ndcg_at_k.labels(k=k).set(value)
    for k, value in metrics.get("hit_rate", {}).items():
        model_hit_rate_at_k.labels(k=k).set(value)


def refresh_model_quality_metrics_from_state(model_state: Dict[str, Any], ratings: Optional[list] = None) -> Optional[Dict[str, Any]]:
    try:
        if ratings is None:
            ratings = get_ratings_data()
        from .evaluation import evaluate_model_state

        metrics = evaluate_model_state(model_state, ratings)
        update_model_quality_metrics(metrics)
        return metrics
    except Exception:
        return None


def _build_monitoring_frame() -> pd.DataFrame:
    ratings = get_ratings_data()
    movies = get_all_movies()
    movie_lookup = {
        movie["id"]: {"genre": movie.get("genre"), "year": movie.get("year")}
        for movie in movies
    }

    df = pd.DataFrame(ratings)
    if df.empty:
        return pd.DataFrame(columns=["user_id", "movie_id", "rating", "genre", "year"])

    df["genre"] = df["movie_id"].map(lambda mid: movie_lookup.get(mid, {}).get("genre"))
    df["year"] = df["movie_id"].map(lambda mid: movie_lookup.get(mid, {}).get("year"))
    return df[["user_id", "movie_id", "rating", "genre", "year"]].copy()


def _get_evidently_reference_current() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = _build_monitoring_frame()
    if df.empty:
        return df.copy(), df.copy()

    split_idx = max(1, int(len(df) * 0.7))
    reference = df.iloc[:split_idx].copy()
    current = df.iloc[split_idx:].copy()
    if current.empty:
        current = df.copy()
    return reference, current


def evaluate_data_quality() -> Dict[str, Any]:
    """
    Runs an Evidently data quality check against a reference slice of historical ratings
    and the current live rating data. This is a monitoring-only signal and does not trigger
    retraining or change the recommendation pipeline.
    """
    reference, current = _get_evidently_reference_current()
    if reference.empty or current.empty:
        return {
            "status": "PASS",
            "quality_score": 100.0,
            "summary": {"message": "No live ratings available for quality analysis."},
            "details": {}
        }

    report = Report(metrics=[DataQualityPreset()])
    report.run(reference_data=reference, current_data=current)
    metrics = report.as_dict().get("metrics", [])

    dataset_summary = {}
    for metric in metrics:
        if metric.get("metric") == "DatasetSummaryMetric":
            dataset_summary = metric.get("result", {}).get("current", {})
            break

    nans_by_columns = dataset_summary.get("nans_by_columns", {})
    missing_values = sum(int(v) for v in nans_by_columns.values()) if isinstance(nans_by_columns, dict) else 0
    duplicate_rows = int(dataset_summary.get("number_of_duplicated_rows", 0))
    number_of_rows = int(dataset_summary.get("number_of_rows", 0) or 0)

    quality_score = 100.0
    if number_of_rows:
        quality_score = max(0.0, 100.0 - (missing_values * 5.0) - (duplicate_rows * 10.0))

    quality_status = "PASS" if quality_score >= 90.0 else "WARN" if quality_score >= 60.0 else "FAIL"
    return {
        "status": quality_status,
        "quality_score": round(quality_score, 2),
        "summary": {
            "rows": number_of_rows,
            "missing_values": missing_values,
            "duplicate_rows": duplicate_rows,
            "nans_by_columns": nans_by_columns,
        },
        "details": dataset_summary,
    }


def evaluate_data_drift() -> Dict[str, Any]:
    """
    Runs an Evidently drift assessment comparing a reference data slice to the current live
    data. This is prepared for Phase 6 alerting and dashboarding without driving retraining.
    """
    reference, current = _get_evidently_reference_current()
    if reference.empty or current.empty:
        return {
            "status": "Healthy",
            "score": 0.0,
            "drift_score": 0.0,
            "summary": {"message": "No live ratings available for drift analysis."},
            "details": {},
        }

    report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=reference, current_data=current)
    metrics = report.as_dict().get("metrics", [])

    dataset_drift = {"dataset_drift": False, "share_of_drifted_columns": 0.0, "number_of_drifted_columns": 0}
    for metric in metrics:
        if metric.get("metric") == "DatasetDriftMetric":
            dataset_drift = metric.get("result", {})
            break

    drift_score = float(dataset_drift.get("share_of_drifted_columns", 0.0) or 0.0)
    if drift_score < 0.10:
        drift_status = "Healthy"
    elif drift_score < 0.30:
        drift_status = "Warning"
    else:
        drift_status = "Drifted"

    return {
        "status": drift_status,
        "score": round(drift_score, 4),
        "drift_score": round(drift_score, 4),
        "summary": {
            "dataset_drift": bool(dataset_drift.get("dataset_drift", False)),
            "number_of_drifted_columns": int(dataset_drift.get("number_of_drifted_columns", 0) or 0),
            "share_of_drifted_columns": round(float(dataset_drift.get("share_of_drifted_columns", 0.0) or 0.0), 4),
        },
        "details": dataset_drift,
    }


def get_metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST


def get_metrics_registry() -> CollectorRegistry:
    return registry


def get_model_info() -> Dict[str, Any]:
    return {
        "version": _current_model_version,
        "stage": _current_model_stage
    }


def calculate_psi(expected: np.ndarray, actual: np.ndarray, num_buckets: int = 5) -> float:
    """
    Computes Population Stability Index (PSI) between two distributions.
    This restores the original helper used by the project.
    """
    # Normalize to probabilities
    exp_sum = np.sum(expected)
    act_sum = np.sum(actual)
    exp_pct = expected / exp_sum if exp_sum > 0 else np.ones(num_buckets) / num_buckets
    act_pct = actual / act_sum if act_sum > 0 else np.ones(num_buckets) / num_buckets

    # Avoid zero division/log errors by adding a small constant epsilon
    eps = 1e-4
    exp_pct = np.clip(exp_pct, eps, 1 - eps)
    act_pct = np.clip(act_pct, eps, 1 - eps)

    # Re-normalize
    exp_pct /= np.sum(exp_pct)
    act_pct /= np.sum(act_pct)

    # Calculate PSI
    psi_value = np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct))
    return float(psi_value)


def detect_drift() -> Dict[str, Any]:
    """
    Backwards-compatible `detect_drift` function restored.
    Compares recent ratings vs baseline ratings and returns PSI and status.
    """
    ratings = get_ratings_data()

    if len(ratings) < 10:
        return {
            "psi": 0.0,
            "status": "Healthy",
            "message": "Insufficient rating logs to compute drift.",
            "phase5": evaluate_data_drift(),
            "evidently": evaluate_data_drift()
        }

    df = pd.DataFrame(ratings)

    # Baseline: first 70% of collected ratings
    split_idx = int(len(df) * 0.7)
    if split_idx < 5:
        split_idx = len(df)

    baseline_ratings = df.iloc[:split_idx]["rating"]
    recent_count = max(15, int(len(df) * 0.3))
    recent_ratings = df.iloc[-recent_count:]["rating"]

    def bucket_ratings(series: pd.Series) -> np.ndarray:
        counts = [0] * 5
        for val in series:
            if val <= 2.0:
                counts[0] += 1
            elif val <= 3.0:
                counts[1] += 1
            elif val <= 4.0:
                counts[2] += 1
            elif val < 5.0:
                counts[3] += 1
            else:
                counts[4] += 1
        return np.array(counts, dtype=float)

    expected_counts = bucket_ratings(baseline_ratings)
    actual_counts = bucket_ratings(recent_ratings)
    psi = calculate_psi(expected_counts, actual_counts)

    if psi < 0.1:
        status = "Healthy"
        message = "Model performance is stable. Ratings distribution matches training baseline."
    elif psi < 0.25:
        status = "Warning"
        message = "Moderate rating distribution shift detected. Monitoring recommended."
    else:
        status = "Drifted"
        message = "Significant data drift detected! Retraining recommended to realign recommendations."

    evidently_drift = evaluate_data_drift()
    return {
        "psi": round(psi, 4),
        "status": status,
        "message": message,
        "baseline_dist": expected_counts.tolist(),
        "recent_dist": actual_counts.tolist(),
        "phase5": evidently_drift,
        "evidently": evidently_drift,
        "evidently_status": evidently_drift.get("status"),
        "drift_score": round(psi, 4),
        "summary": evidently_drift.get("summary", {})
    }
