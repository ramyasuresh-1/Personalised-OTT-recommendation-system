import json
import os
import pickle
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import mlflow
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient

# Ensure backend root is importable when running as a module
ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
DOCS_DIR = ROOT_DIR / "docs"
DATA_DIR = BACKEND_DIR / "data"
MODELS_DIR = BACKEND_DIR / "models"
MODEL_PATH = MODELS_DIR / "recommender.pkl"
BASELINE_EVALUATION_PATH = DOCS_DIR / "baseline_evaluation.json"
PHASE_3_EVALUATION_JSON = DOCS_DIR / "phase_3_evaluation.json"
PHASE_3_REPORT_MD = DOCS_DIR / "PHASE_3_MODEL_EVALUATION.md"
DEFAULT_MODEL_NAME = "OTT-Recommender"
EXPERIMENT_NAME = "OTT Recommendation System"

sys.path.insert(0, str(BACKEND_DIR))

from app.recommender import EXPERIMENT_NAME as RECOMMENDER_EXPERIMENT_NAME  # noqa: E402
from app.database import get_all_movies  # noqa: E402
from ml.evaluate_baseline import BaselineEvaluator  # noqa: E402
from ml.split_data import load_processed_ratings  # noqa: E402


@dataclass
class QualityGateConfig:
    max_rmse_regression_pct: float = 0.02
    max_mae_regression_pct: float = 0.02
    max_ndcg_degradation_pct: float = 0.01
    min_ndcg_at_10_improvement_pct: float = 0.005
    min_recall_at_10_improvement_pct: float = 0.005
    min_precision_at_5_improvement_pct: float = 0.005
    min_f1_at_5_improvement_pct: float = 0.005
    min_hit_rate_at_5_improvement_pct: float = 0.0
    require_rank_improvement: bool = True
    dataset_version: str = "phase_1"


@dataclass
class ReproducibilityInfo:
    git_commit: str
    dvc_version: str
    python_version: str
    mlflow_version: str
    numpy_version: str
    pandas_version: str
    dataset_size: int
    num_users: int
    num_movies: int
    training_timestamp: str


def ensure_dirs() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)


def load_model_state(model_path: Path) -> Dict[str, Any]:
    if not model_path.exists():
        raise FileNotFoundError(f"Model artifact not found: {model_path}")

    with open(model_path, "rb") as f:
        state = pickle.load(f)

    if not isinstance(state, dict):
        raise ValueError(f"Model artifact is not a valid state dictionary: {model_path}")

    required_keys = {"model_version", "reconstructed_matrix_df", "user_movie_matrix", "movie_popularity"}
    if not required_keys.issubset(set(state.keys())):
        raise ValueError(
            f"Model artifact is missing required keys: {required_keys - set(state.keys())}"
        )

    return state


def load_phase1_splits() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    train_file = DATA_DIR / "splits" / "train.csv"
    validation_file = DATA_DIR / "splits" / "validation.csv"
    test_file = DATA_DIR / "splits" / "test.csv"

    if not all([train_file.exists(), validation_file.exists(), test_file.exists()]):
        raise FileNotFoundError("Phase 1 split files are missing. Ensure Phase 1 has completed successfully.")

    train = load_processed_ratings(str(train_file))
    validation = load_processed_ratings(str(validation_file))
    test = load_processed_ratings(str(test_file))
    return train, validation, test


def get_reproducibility_info(ratings: List[Dict[str, Any]]) -> ReproducibilityInfo:
    def safe_run(command: List[str], cwd: Path) -> str:
        try:
            return subprocess.check_output(command, cwd=cwd, stderr=subprocess.DEVNULL, text=True).strip()
        except Exception:
            return "unknown"

    ratings_df = pd.DataFrame(ratings)
    return ReproducibilityInfo(
        git_commit=safe_run(["git", "rev-parse", "HEAD"], ROOT_DIR),
        dvc_version=safe_run(["dvc", "version"], ROOT_DIR),
        python_version=platform.python_version(),
        mlflow_version=mlflow.__version__,
        numpy_version=np.__version__,
        pandas_version=pd.__version__,
        dataset_size=len(ratings),
        num_users=int(ratings_df["user_id"].nunique()) if not ratings_df.empty else 0,
        num_movies=int(ratings_df["movie_id"].nunique()) if not ratings_df.empty else 0,
        training_timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
    )


def safe_percent_change(base: float, candidate: float) -> float:
    if base == 0.0:
        return float("inf") if candidate != 0.0 else 0.0
    return (candidate - base) / base


def compute_f1(precision: float, recall: float) -> float:
    if precision + recall == 0.0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def enrich_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    result = metrics.copy()
    for k in [5, 10]:
        precision = metrics["precision"].get(f"@{k}", 0.0)
        recall = metrics["recall"].get(f"@{k}", 0.0)
        result.setdefault("f1", {})[f"@{k}"] = round(compute_f1(precision, recall), 4)
    result["mse"] = round(metrics["rmse"] ** 2, 4)
    return result


def evaluate_model_state(
    model_state: Dict[str, Any],
    ratings: List[Dict[str, Any]],
    k_values: List[int] = [5, 10],
    dataset_version: str = "phase_1"
) -> Dict[str, Any]:
    evaluator = BaselineEvaluator()
    results = evaluator.evaluate_model(
        reconstructed_df=model_state["reconstructed_matrix_df"],
        user_movie_matrix=model_state["user_movie_matrix"],
        movie_popularity=model_state["movie_popularity"],
        ratings=ratings,
        k_values=k_values,
        model_params={
            "algorithm": "Funk SVD",
            "latent_factors": int(model_state.get("latent_factors", 6)),
            "epochs": int(model_state.get("epochs", 35)),
            "learning_rate": float(model_state.get("learning_rate", 0.05)),
            "regularization": float(model_state.get("regularization", 0.02)),
            "model_version": model_state.get("model_version", "unknown"),
            "dataset_version": dataset_version
        }
    )
    enriched = enrich_metrics(results)
    enriched["model_version"] = model_state.get("model_version", "unknown")
    enriched["evaluation_timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return enriched


def compare_models(
    baseline_metrics: Dict[str, Any],
    candidate_metrics: Dict[str, Any]
) -> Dict[str, Any]:
    comparison = {
        "metrics": {},
        "summary": {},
    }

    metric_keys = [
        "mse", "rmse", "mae",
        "precision", "recall", "f1", "ndcg", "hit_rate",
        "catalog_coverage", "recommendation_diversity"
    ]

    for metric in metric_keys:
        if metric in ["precision", "recall", "f1", "ndcg", "hit_rate"]:
            comparison["metrics"][metric] = {}
            for k in [5, 10]:
                base_val = baseline_metrics.get(metric, {}).get(f"@{k}", 0.0)
                cand_val = candidate_metrics.get(metric, {}).get(f"@{k}", 0.0)
                comparison["metrics"][metric][f"@{k}"] = {
                    "baseline": base_val,
                    "candidate": cand_val,
                    "delta": round(cand_val - base_val, 4),
                    "percent_change": round(safe_percent_change(base_val, cand_val) * 100.0, 4)
                }
        else:
            base_val = baseline_metrics.get(metric, 0.0)
            cand_val = candidate_metrics.get(metric, 0.0)
            comparison["metrics"][metric] = {
                "baseline": base_val,
                "candidate": cand_val,
                "delta": round(cand_val - base_val, 4),
                "percent_change": round(safe_percent_change(base_val, cand_val) * 100.0, 4)
            }

    comparison["summary"]["primary"] = {
        "rmse": comparison["metrics"]["rmse"],
        "mae": comparison["metrics"]["mae"],
        "precision@5": comparison["metrics"]["precision"]["@5"],
        "recall@5": comparison["metrics"]["recall"]["@5"],
        "ndcg@5": comparison["metrics"]["ndcg"]["@5"],
        "coverage": comparison["metrics"]["catalog_coverage"],
        "diversity": comparison["metrics"]["recommendation_diversity"]
    }
    return comparison


def quality_gate(
    baseline_metrics: Dict[str, Any],
    candidate_metrics: Dict[str, Any],
    config: QualityGateConfig
) -> Dict[str, Any]:
    reasons: List[str] = []
    passed = True

    rmse_change = safe_percent_change(baseline_metrics["rmse"], candidate_metrics["rmse"])
    mae_change = safe_percent_change(baseline_metrics["mae"], candidate_metrics["mae"])
    ndcg10_change = safe_percent_change(baseline_metrics["ndcg"]["@10"], candidate_metrics["ndcg"]["@10"])
    ndcg5_change = safe_percent_change(baseline_metrics["ndcg"]["@5"], candidate_metrics["ndcg"]["@5"])
    precision5_change = safe_percent_change(baseline_metrics["precision"]["@5"], candidate_metrics["precision"]["@5"])
    recall5_change = safe_percent_change(baseline_metrics["recall"]["@5"], candidate_metrics["recall"]["@5"])
    f1_5_change = safe_percent_change(baseline_metrics["f1"]["@5"], candidate_metrics["f1"]["@5"])

    if rmse_change > config.max_rmse_regression_pct:
        passed = False
        reasons.append(
            f"RMSE regression exceeded {config.max_rmse_regression_pct*100:.1f}%: {rmse_change*100:.2f}%"
        )

    if mae_change > config.max_mae_regression_pct:
        passed = False
        reasons.append(
            f"MAE regression exceeded {config.max_mae_regression_pct*100:.1f}%: {mae_change*100:.2f}%"
        )

    if ndcg10_change < -config.max_ndcg_degradation_pct:
        passed = False
        reasons.append(
            f"NDCG@10 degraded by more than {config.max_ndcg_degradation_pct*100:.1f}%: {ndcg10_change*100:.2f}%"
        )

    if config.require_rank_improvement:
        improved_rank_metric = (
            ndcg10_change >= config.min_ndcg_at_10_improvement_pct
            or recall5_change >= config.min_recall_at_10_improvement_pct
            or precision5_change >= config.min_precision_at_5_improvement_pct
            or f1_5_change >= config.min_f1_at_5_improvement_pct
        )
        if not improved_rank_metric and rmse_change >= 0.0:
            passed = False
            reasons.append(
                "Candidate did not improve primary ranking metrics and did not reduce RMSE."
            )

    if baseline_metrics["catalog_coverage"] > 0:
        coverage_change = safe_percent_change(
            baseline_metrics["catalog_coverage"],
            candidate_metrics["catalog_coverage"]
        )
        if coverage_change < -0.05:
            passed = False
            reasons.append(
                f"Coverage regressed by more than 5%: {coverage_change*100:.2f}%"
            )

    if baseline_metrics["recommendation_diversity"] > 0:
        diversity_change = safe_percent_change(
            baseline_metrics["recommendation_diversity"],
            candidate_metrics["recommendation_diversity"]
        )
        if diversity_change < -0.05:
            passed = False
            reasons.append(
                f"Diversity regressed by more than 5%: {diversity_change*100:.2f}%"
            )

    if not reasons:
        reasons.append("Candidate passes quality gate under configured thresholds.")

    return {
        "passed": passed,
        "reasons": reasons,
        "rmse_change_pct": round(rmse_change * 100.0, 4),
        "mae_change_pct": round(mae_change * 100.0, 4),
        "ndcg10_change_pct": round(ndcg10_change * 100.0, 4),
        "precision5_change_pct": round(precision5_change * 100.0, 4),
        "recall5_change_pct": round(recall5_change * 100.0, 4),
        "f1_5_change_pct": round(f1_5_change * 100.0, 4)
    }


def safe_mlflow_run(
    run_name: str,
    model_state: Dict[str, Any],
    evaluation_report: Dict[str, Any],
    model_artifact_path: Optional[Path] = None,
    model_stage: str = "Candidate"
) -> Optional[str]:
    mlflow.set_experiment(EXPERIMENT_NAME)
    run_id = None
    try:
        with mlflow.start_run(run_name=run_name) as run:
            run_id = run.info.run_id
            mlflow.set_tag("model_stage", model_stage)
            mlflow.set_tag("evaluation_type", "model_evaluation")
            mlflow.set_tag("dataset_version", evaluation_report["reproducibility"]["dataset_version"])
            mlflow.set_tag("model_version", model_state.get("model_version", "unknown"))
            mlflow.set_tag("quality_gate", evaluation_report["quality_gate"]["passed"])
            mlflow.log_param("algorithm", "Funk SVD")
            mlflow.log_param("latent_factors", int(model_state.get("latent_factors", 6)))
            mlflow.log_param("epochs", int(model_state.get("epochs", 35)))
            mlflow.log_param("learning_rate", float(model_state.get("learning_rate", 0.05)))
            mlflow.log_param("regularization", float(model_state.get("regularization", 0.02)))
            mlflow.log_param("dataset_version", evaluation_report["reproducibility"]["dataset_version"])
            mlflow.log_param("git_commit", evaluation_report["reproducibility"]["git_commit"])
            mlflow.log_param("dvc_version", evaluation_report["reproducibility"]["dvc_version"])
            mlflow.log_param("python_version", evaluation_report["reproducibility"]["python_version"])
            mlflow.log_param("mlflow_version", evaluation_report["reproducibility"]["mlflow_version"])
            mlflow.log_param("numpy_version", evaluation_report["reproducibility"]["numpy_version"])
            mlflow.log_param("pandas_version", evaluation_report["reproducibility"]["pandas_version"])
            mlflow.log_metric("evaluation_time", evaluation_report.get("evaluation_time_seconds", 0.0))

            # Log metrics for candidate model
            metrics = evaluation_report["candidate_metrics"]
            mlflow.log_metric("MSE", metrics["mse"])
            mlflow.log_metric("RMSE", metrics["rmse"])
            mlflow.log_metric("MAE", metrics["mae"])
            mlflow.log_metric("Precision@5", metrics["precision"]["@5"])
            mlflow.log_metric("Recall@5", metrics["recall"]["@5"])
            mlflow.log_metric("F1@5", metrics["f1"]["@5"])
            mlflow.log_metric("NDCG@5", metrics["ndcg"]["@5"])
            mlflow.log_metric("HitRate@5", metrics["hit_rate"]["@5"])
            mlflow.log_metric("Coverage", metrics["catalog_coverage"])
            mlflow.log_metric("Diversity", metrics["recommendation_diversity"])

            ensure_dirs()
            with open(PHASE_3_EVALUATION_JSON, "w", encoding="utf-8") as f:
                json.dump(evaluation_report, f, indent=2)
            mlflow.log_artifact(str(PHASE_3_EVALUATION_JSON), artifact_path="evaluation")

            if model_artifact_path is not None and model_artifact_path.exists():
                mlflow.log_artifact(str(model_artifact_path), artifact_path="model_artifact")

            try:
                client = MlflowClient()
                try:
                    client.get_registered_model(DEFAULT_MODEL_NAME)
                except Exception:
                    client.create_registered_model(DEFAULT_MODEL_NAME)

                artifact_path = f"model_artifact/{model_artifact_path.name}" if model_artifact_path is not None else ""
                if model_artifact_path is not None:
                    source = f"runs:/{run_id}/{artifact_path}"
                    mv = client.create_model_version(
                        name=DEFAULT_MODEL_NAME,
                        source=source,
                        run_id=run_id
                    )
                    try:
                        client.transition_model_version_stage(
                            name=DEFAULT_MODEL_NAME,
                            version=mv.version,
                            stage=model_stage,
                            archive_existing_versions=False
                        )
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception as exc:
        raise RuntimeError(f"MLflow evaluation logging failed: {exc}")

    return run_id


def promote_candidate_model(candidate_path: Path, champion_path: Path, backup_path: Path) -> None:
    if not candidate_path.exists():
        raise FileNotFoundError(f"Candidate model not found: {candidate_path}")

    if champion_path.exists():
        champion_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(champion_path, backup_path)

    shutil.copy2(candidate_path, champion_path)


def rollback_to_previous_champion(champion_path: Path, backup_path: Path) -> None:
    if not backup_path.exists():
        raise FileNotFoundError("No previous champion backup available to rollback.")
    shutil.copy2(backup_path, champion_path)


def create_evaluation_report(
    baseline_model_path: Path,
    candidate_model_path: Path,
    config: Optional[QualityGateConfig] = None,
    promote_if_pass: bool = False
) -> Dict[str, Any]:
    if config is None:
        config = QualityGateConfig()

    ensure_dirs()
    _, _, test_ratings = load_phase1_splits()
    reproducibility = get_reproducibility_info(test_ratings)
    baseline_state = load_model_state(baseline_model_path)
    candidate_state = load_model_state(candidate_model_path)

    start_time = time.time()
    baseline_metrics = evaluate_model_state(baseline_state, test_ratings, dataset_version=config.dataset_version)
    candidate_metrics = evaluate_model_state(candidate_state, test_ratings, dataset_version=config.dataset_version)
    comparison = compare_models(baseline_metrics, candidate_metrics)
    quality_gate_result = quality_gate(baseline_metrics, candidate_metrics, config)
    evaluation_time_seconds = round(time.time() - start_time, 4)

    report = {
        "status": "PASS" if quality_gate_result["passed"] else "FAIL",
        "baseline_model_path": str(baseline_model_path),
        "candidate_model_path": str(candidate_model_path),
        "baseline_model_version": baseline_state.get("model_version", "unknown"),
        "candidate_model_version": candidate_state.get("model_version", "unknown"),
        "baseline_metrics": baseline_metrics,
        "candidate_metrics": candidate_metrics,
        "comparison": comparison,
        "quality_gate": quality_gate_result,
        "reproducibility": {
            **asdict(reproducibility),
            "dataset_version": config.dataset_version
        },
        "evaluation_time_seconds": evaluation_time_seconds
    }

    if promote_if_pass and quality_gate_result["passed"]:
        from shutil import copy2
        previous_champion_path = MODELS_DIR / "recommender_previous.pkl"
        promote_candidate_model(candidate_model_path, MODEL_PATH, previous_champion_path)
        report["promotion"] = {
            "promoted": True,
            "champion_path": str(MODEL_PATH),
            "backup_path": str(previous_champion_path)
        }
    else:
        report["promotion"] = {
            "promoted": False,
            "reason": "Candidate did not pass quality gate." if not quality_gate_result["passed"] else "Promotion not requested."
        }

    return report


def save_report(report: Dict[str, Any]) -> None:
    ensure_dirs()
    with open(PHASE_3_EVALUATION_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def save_markdown_report(report: Dict[str, Any]) -> None:
    ensure_dirs()
    lines: List[str] = []
    lines.append("# Phase 3 Model Evaluation Report")
    lines.append("")
    lines.append("## Objective")
    lines.append("Evaluate a candidate Funk SVD model against the current champion and apply a quality gate before promotion.")
    lines.append("")
    lines.append("## Baseline")
    lines.append(f"- Baseline model version: {report['baseline_model_version']}")
    lines.append(f"- Baseline model path: {report['baseline_model_path']}")
    lines.append("")
    lines.append("## Candidate")
    lines.append(f"- Candidate model version: {report['candidate_model_version']}")
    lines.append(f"- Candidate model path: {report['candidate_model_path']}")
    lines.append("")
    lines.append("## Quality Gate")
    lines.append(f"- Result: {report['status']}")
    for reason in report['quality_gate']['reasons']:
        lines.append(f"  - {reason}")
    lines.append("")
    lines.append("## Promotion")
    lines.append(f"- Promoted: {report['promotion']['promoted']}")
    lines.append(f"- Reason: {report['promotion']['reason']}")
    lines.append("")
    lines.append("## Baseline vs Candidate Metrics")
    for metric, value in report['comparison']['metrics'].items():
        if isinstance(value, dict) and all(k.startswith("@") for k in value.keys()):
            lines.append(f"### {metric}")
            for k, sub in value.items():
                lines.append(f"- {k}: baseline={sub['baseline']}, candidate={sub['candidate']}, delta={sub['delta']}, pct={sub['percent_change']}%")
        else:
            lines.append(f"- {metric}: baseline={value['baseline']}, candidate={value['candidate']}, delta={value['delta']}, pct={value['percent_change']}%")
    lines.append("")
    lines.append("## Reproducibility")
    for key, value in report['reproducibility'].items():
        lines.append(f"- {key}: {value}")

    with open(PHASE_3_REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run_evaluation(
    candidate_model_path: Optional[str] = None,
    baseline_model_path: Optional[str] = None,
    promote_if_pass: bool = False,
    config: Optional[QualityGateConfig] = None
) -> Dict[str, Any]:
    if candidate_model_path is None:
        raise ValueError("A candidate model path is required.")

    baseline_path = Path(baseline_model_path) if baseline_model_path else MODEL_PATH
    candidate_path = Path(candidate_model_path)

    report = create_evaluation_report(
        baseline_model_path=baseline_path,
        candidate_model_path=candidate_path,
        config=config,
        promote_if_pass=promote_if_pass
    )
    save_report(report)
    save_markdown_report(report)
    safe_mlflow_run(
        run_name=f"Phase_3_Evaluation_{Path(candidate_model_path).stem}",
        model_state=load_model_state(candidate_path),
        evaluation_report=report,
        model_artifact_path=candidate_path,
        model_stage="Production" if report["promotion"]["promoted"] else "Candidate"
    )
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 3 model evaluation and promotion.")
    parser.add_argument("--candidate-model", type=str, required=True, help="Path to the candidate model artifact pickle file.")
    parser.add_argument("--baseline-model", type=str, default=str(MODEL_PATH), help="Path to the champion model artifact pickle file.")
    parser.add_argument("--promote-if-pass", action="store_true", help="Promote the candidate to champion if it passes the quality gate.")
    parser.add_argument("--dataset-version", type=str, default="phase_1", help="Dataset version tag for reproducibility.")
    parser.add_argument("--max-rmse-regression-pct", type=float, default=0.02, help="Maximum allowed RMSE regression fraction.")
    parser.add_argument("--max-mae-regression-pct", type=float, default=0.02, help="Maximum allowed MAE regression fraction.")
    parser.add_argument("--max-ndcg-degradation-pct", type=float, default=0.01, help="Maximum allowed NDCG@10 degradation fraction.")
    parser.add_argument("--min-ndcg-at-10-improvement-pct", type=float, default=0.005, help="Minimum NDCG@10 improvement fraction for automatic pass.")
    args = parser.parse_args()

    config = QualityGateConfig(
        max_rmse_regression_pct=args.max_rmse_regression_pct,
        max_mae_regression_pct=args.max_mae_regression_pct,
        max_ndcg_degradation_pct=args.max_ndcg_degradation_pct,
        min_ndcg_at_10_improvement_pct=args.min_ndcg_at_10_improvement_pct,
        dataset_version=args.dataset_version
    )

    try:
        report = run_evaluation(
            candidate_model_path=args.candidate_model,
            baseline_model_path=args.baseline_model,
            promote_if_pass=args.promote_if_pass,
            config=config
        )
        status = report["status"]
        print(f"QUALITY GATE: {status}")
        for reason in report["quality_gate"]["reasons"]:
            print(f"- {reason}")
        if report["promotion"]["promoted"]:
            print("Candidate promoted to champion model.")
        else:
            print("Candidate not promoted.")
        sys.exit(0 if report["status"] == "PASS" else 2)
    except Exception as exc:
        print(f"Evaluation failed: {exc}")
        raise
