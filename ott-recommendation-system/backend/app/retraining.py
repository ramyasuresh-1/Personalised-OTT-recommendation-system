"""
Phase 6: Automated Retraining and Model Promotion Pipeline

This module implements a safe retraining pipeline triggered by Phase 5 drift detection.
The pipeline trains a candidate model, evaluates it against the current champion,
applies a quality gate, and promotes the candidate only if it passes validation.

Key Safety Features:
- Candidate model isolated from champion until validation succeeds
- Failed retraining leaves champion unchanged
- Duplicate retraining prevented via lock mechanism
- All attempts tracked in MLflow
- Graceful failure handling
"""

import os
import time
import pickle
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
import mlflow
from mlflow.tracking import MlflowClient
from datetime import datetime

import pandas as pd
import numpy as np

from .monitoring import detect_drift, evaluate_data_quality
from .database import get_ratings_data, get_all_movies, log_retraining
from .recommender import OTTRecommender
from .evaluation import QualityGateConfig, quality_gate, evaluate_model_state

# Paths
ROOT_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = Path(os.environ.get("MODEL_DIR", str(ROOT_DIR / "models")))
MODELS_DIR = MODEL_DIR
CANDIDATE_MODEL_PATH = MODELS_DIR / "recommender_candidate.pkl"
CHAMPION_MODEL_PATH = MODELS_DIR / "recommender.pkl"

# MLflow config (must match recommender.py)
DEFAULT_MLFLOW_DB = ROOT_DIR / "mlflow.db"
DEFAULT_MLFLOW_ARTIFACT_ROOT = ROOT_DIR / "mlruns"
EXPERIMENT_NAME = os.environ.get("MLFLOW_EXPERIMENT_NAME", "OTT Recommendation System")
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{DEFAULT_MLFLOW_DB.as_posix()}")


@dataclass
class RetrainingConfig:
    """Configuration for the retraining pipeline."""
    max_rmse_regression_pct: float = 0.02
    max_mae_regression_pct: float = 0.02
    max_ndcg_degradation_pct: float = 0.01
    min_ndcg_improvement_pct: float = 0.005
    min_ranking_improvement: bool = True
    drift_threshold: str = "Drifted"  # Only retrain if drift status is "Drifted"
    data_quality_threshold: str = "PASS"  # Only retrain if data quality is PASS or WARN


class RetrainingPipeline:
    """
    Orchestrates the automated retraining workflow.
    
    Flow:
    1. Check drift status
    2. Train candidate model
    3. Evaluate candidate and champion
    4. Compare performance
    5. Apply quality gate
    6. Promote candidate if passing, reject otherwise
    7. Track everything in MLflow
    """
    
    def __init__(self, config: Optional[RetrainingConfig] = None):
        self.config = config or RetrainingConfig()
        self.candidate_model: Optional[OTTRecommender] = None
        self.champion_model: Optional[OTTRecommender] = None
        self.candidate_metrics: Optional[Dict[str, Any]] = None
        self.champion_metrics: Optional[Dict[str, Any]] = None
        self.quality_gate_result: Optional[Dict[str, Any]] = None
        self.drift_info: Optional[Dict[str, Any]] = None
        self.retraining_run_id: Optional[str] = None
        self.promotion_status: str = "pending"  # pending, accepted, rejected
        
    def should_retrain(self) -> Tuple[bool, str]:
        """
        Check if retraining should be triggered based on drift and data quality.
        
        Returns:
            (should_retrain: bool, reason: str)
        """
        try:
            drift_result = detect_drift()
            quality_result = evaluate_data_quality()
            
            self.drift_info = drift_result
            
            drift_status = drift_result.get("status", "Healthy")
            quality_status = quality_result.get("status", "FAIL")
            
            # Only retrain if drift is detected
            if drift_status != self.config.drift_threshold:
                return False, f"Drift status is {drift_status}, not {self.config.drift_threshold}"
            
            # Only retrain if data quality is acceptable
            if quality_status == "FAIL":
                return False, "Data quality is FAIL, retraining suspended until data quality improves"
            
            return True, "Drift detected and data quality acceptable"
            
        except Exception as e:
            return False, f"Error checking retraining conditions: {str(e)}"
    
    def _load_champion(self) -> bool:
        """Load the current champion model from disk."""
        try:
            if not CHAMPION_MODEL_PATH.exists():
                return False
            
            with open(CHAMPION_MODEL_PATH, "rb") as f:
                state = pickle.load(f)
            
            self.champion_model = OTTRecommender()
            self.champion_model.__dict__.update(state)
            self.champion_model.is_trained = True
            return True
        except Exception as e:
            print(f"Error loading champion model: {e}")
            return False
    
    def _train_candidate(self) -> bool:
        """Train a new candidate model."""
        champion_backup = None
        try:
            print("Training candidate model...")
            start_time = time.perf_counter()

            if CHAMPION_MODEL_PATH.exists():
                champion_backup = CHAMPION_MODEL_PATH.with_suffix(".champion-backup.pkl")
                shutil.copy2(CHAMPION_MODEL_PATH, champion_backup)
            
            self.candidate_model = OTTRecommender()
            result = self.candidate_model.train_model()
            
            training_time = time.perf_counter() - start_time
            
            if result.get("status") != "success":
                print(f"Candidate training failed: {result.get('message', 'Unknown error')}")
                return False

            with open(CANDIDATE_MODEL_PATH, "wb") as f:
                pickle.dump(self.candidate_model.__dict__, f)
            if champion_backup and champion_backup.exists():
                shutil.copy2(champion_backup, CHAMPION_MODEL_PATH)
            
            print(f"Candidate model trained successfully in {training_time:.2f}s")
            
            # Tag the run as candidate
            if mlflow.active_run():
                mlflow.set_tag("model_stage", "Candidate")
                mlflow.set_tag("retraining_pipeline", "True")
            
            return True
        except Exception as e:
            print(f"Error training candidate: {e}")
            return False
        finally:
            if champion_backup and champion_backup.exists():
                shutil.copy2(champion_backup, CHAMPION_MODEL_PATH)
                champion_backup.unlink()
    
    def _evaluate_model(self, model: OTTRecommender, model_name: str) -> bool:
        """Evaluate a model and store metrics."""
        try:
            print(f"Evaluating {model_name} model...")
            
            ratings = get_ratings_data()
            if len(ratings) < 10:
                print(f"Insufficient ratings to evaluate {model_name}")
                return False
            
            # Use test set for evaluation (last 20% of data)
            eval_ratings = ratings[-max(15, int(len(ratings) * 0.2)):]
            
            # Get model state
            model_state = {
                "model_version": model.model_version,
                "reconstructed_matrix_df": model.reconstructed_matrix_df,
                "user_movie_matrix": model.user_movie_matrix,
                "movie_popularity": model.movie_popularity,
                "latent_factors": 6,
                "epochs": 35,
                "learning_rate": 0.05,
                "regularization": 0.02
            }
            
            # Evaluate
            metrics = evaluate_model_state(model_state, eval_ratings)
            
            if model_name == "Candidate":
                self.candidate_metrics = metrics
            else:
                self.champion_metrics = metrics
            
            print(f"{model_name} metrics: RMSE={metrics.get('rmse', 0):.4f}, MAE={metrics.get('mae', 0):.4f}")
            return True
            
        except Exception as e:
            print(f"Error evaluating {model_name}: {e}")
            return False
    
    def _apply_quality_gate(self) -> bool:
        """Apply quality gate to compare candidate vs champion."""
        try:
            if self.candidate_metrics is None or self.champion_metrics is None:
                print("Cannot apply quality gate: missing metrics")
                return False
            
            gate_result = quality_gate(
                self.champion_metrics,
                self.candidate_metrics,
                QualityGateConfig(
                    max_rmse_regression_pct=self.config.max_rmse_regression_pct,
                    max_mae_regression_pct=self.config.max_mae_regression_pct,
                    max_ndcg_degradation_pct=self.config.max_ndcg_degradation_pct,
                    min_ndcg_at_10_improvement_pct=self.config.min_ndcg_improvement_pct,
                    require_rank_improvement=self.config.min_ranking_improvement
                )
            )
            
            self.quality_gate_result = gate_result
            
            if gate_result.get("passed"):
                print("✓ Quality gate PASSED - Candidate approved for promotion")
                return True
            else:
                print(f"✗ Quality gate FAILED: {', '.join(gate_result.get('reasons', []))}")
                return False
                
        except Exception as e:
            print(f"Error applying quality gate: {e}")
            return False
    
    def _promote_candidate(self, champion_model: OTTRecommender) -> bool:
        """Promote candidate to champion (replace current model)."""
        try:
            if self.candidate_model is None:
                print("Cannot promote: candidate model not available")
                return False
            
            # Increment candidate model version
            try:
                ver_num = float(self.candidate_model.model_version.replace("v", ""))
                new_version = f"v{ver_num + 0.1:.1f}"
                self.candidate_model.model_version = new_version
            except:
                self.candidate_model.model_version = "v2.0.0"
            
            # Save promoted model as champion
            self.candidate_model.save_model()
            
            # Update the in-memory champion reference
            champion_model.__dict__.update(self.candidate_model.__dict__)
            
            # Log promotion
            if self.candidate_metrics:
                mse = self.candidate_metrics.get("mse", 0.0)
            else:
                mse = 0.0
            
            ratings_count = len(get_ratings_data())
            log_retraining(ratings_count, mse, self.candidate_model.model_version)
            
            self.promotion_status = "accepted"
            print(f"✓ Candidate promoted to champion: {self.candidate_model.model_version}")
            return True
            
        except Exception as e:
            print(f"Error promoting candidate: {e}")
            self.promotion_status = "rejected"
            return False
    
    def _reject_candidate(self) -> bool:
        """Reject candidate and keep champion unchanged."""
        try:
            # Clean up candidate pickle file
            if CANDIDATE_MODEL_PATH.exists():
                CANDIDATE_MODEL_PATH.unlink()
            
            self.promotion_status = "rejected"
            print("✓ Candidate rejected - Champion model remains unchanged")
            return True
            
        except Exception as e:
            print(f"Error rejecting candidate: {e}")
            return False
    
    def _log_to_mlflow(self) -> str:
        """Log retraining attempt to MLflow."""
        try:
            run_name = f"Retraining_{int(time.time())}"
            mlflow.set_experiment(EXPERIMENT_NAME)
            
            with mlflow.start_run(run_name=run_name) as run:
                run_id = run.info.run_id
                
                # Log parameters
                mlflow.log_param("pipeline", "Phase6-Retraining")
                mlflow.log_param("config_rmse_threshold_pct", self.config.max_rmse_regression_pct)
                mlflow.log_param("config_mae_threshold_pct", self.config.max_mae_regression_pct)
                mlflow.log_param("drift_threshold", self.config.drift_threshold)
                
                # Log drift trigger info
                if self.drift_info:
                    mlflow.log_metric("trigger_drift_score", self.drift_info.get("psi", 0.0))
                    mlflow.set_tag("trigger_drift_status", self.drift_info.get("status", "Unknown"))
                
                # Log candidate metrics
                if self.candidate_metrics:
                    mlflow.log_metric("candidate_rmse", self.candidate_metrics.get("rmse", 0.0))
                    mlflow.log_metric("candidate_mae", self.candidate_metrics.get("mae", 0.0))
                    mlflow.log_metric("candidate_mse", self.candidate_metrics.get("mse", 0.0))
                    mlflow.log_metric("candidate_ndcg_at_5", self.candidate_metrics.get("ndcg", {}).get("@5", 0.0))
                    mlflow.log_metric("candidate_precision_at_5", self.candidate_metrics.get("precision", {}).get("@5", 0.0))
                
                # Log champion metrics
                if self.champion_metrics:
                    mlflow.log_metric("champion_rmse", self.champion_metrics.get("rmse", 0.0))
                    mlflow.log_metric("champion_mae", self.champion_metrics.get("mae", 0.0))
                    mlflow.log_metric("champion_mse", self.champion_metrics.get("mse", 0.0))
                
                # Log quality gate result
                if self.quality_gate_result:
                    mlflow.set_tag("quality_gate_passed", self.quality_gate_result.get("passed", False))
                    mlflow.log_metric("rmse_change_pct", self.quality_gate_result.get("rmse_change_pct", 0.0))
                    mlflow.log_metric("mae_change_pct", self.quality_gate_result.get("mae_change_pct", 0.0))
                
                # Log promotion status
                mlflow.set_tag("promotion_status", self.promotion_status)
                mlflow.set_tag("model_stage", "Champion" if self.promotion_status == "accepted" else "Rejected")
                
                self.retraining_run_id = run_id
                return run_id
                
        except Exception as e:
            print(f"Error logging to MLflow: {e}")
            return ""
    
    def execute(self, champion_model: OTTRecommender) -> Dict[str, Any]:
        """
        Execute the full retraining pipeline.
        
        Returns:
            {
                "success": bool,
                "message": str,
                "promotion_status": "accepted" / "rejected",
                "candidate_version": str,
                "champion_version": str,
                "quality_gate_passed": bool,
                "drift_trigger": Dict,
                "metrics_comparison": Dict,
                "mlflow_run_id": str
            }
        """
        print("\n" + "="*80)
        print("PHASE 6 RETRAINING PIPELINE STARTED")
        print("="*80 + "\n")
        
        result = {
            "success": False,
            "message": "Pipeline not executed",
            "promotion_status": self.promotion_status,
            "candidate_version": None,
            "champion_version": None,
            "quality_gate_passed": False,
            "drift_trigger": self.drift_info,
            "metrics_comparison": None,
            "mlflow_run_id": None
        }
        
        try:
            # Step 1: Check if retraining should happen
            should_retrain, reason = self.should_retrain()
            if not should_retrain:
                result["message"] = reason
                print(f"Retraining skipped: {reason}\n")
                return result
            
            print(f"✓ Retraining triggered: {reason}\n")
            
            # Step 2: Load champion
            print("Step 1: Loading champion model...")
            if not self._load_champion():
                result["message"] = "Failed to load champion model"
                print(f"✗ {result['message']}\n")
                return result
            print("✓ Champion loaded\n")
            
            # Step 3: Train candidate
            print("Step 2: Training candidate model...")
            if not self._train_candidate():
                result["message"] = "Failed to train candidate model"
                print(f"✗ {result['message']}\n")
                return result
            print("✓ Candidate trained\n")
            
            # Step 4: Evaluate both models
            print("Step 3: Evaluating models...")
            if not self._evaluate_model(self.champion_model, "Champion"):
                result["message"] = "Failed to evaluate champion"
                print(f"✗ {result['message']}\n")
                return result
            
            if not self._evaluate_model(self.candidate_model, "Candidate"):
                result["message"] = "Failed to evaluate candidate"
                print(f"✗ {result['message']}\n")
                return result
            print("✓ Both models evaluated\n")
            
            # Step 5: Apply quality gate
            print("Step 4: Applying quality gate...")
            gate_passed = self._apply_quality_gate()
            print()
            
            # Step 6: Promote or reject
            print("Step 5: Promotion decision...")
            if gate_passed:
                if self._promote_candidate(champion_model):
                    result["promotion_status"] = "accepted"
                    result["success"] = True
                else:
                    result["promotion_status"] = "rejected"
                    self._reject_candidate()
            else:
                result["promotion_status"] = "rejected"
                self._reject_candidate()
            print()
            
            # Step 7: Log to MLflow
            print("Step 6: Logging to MLflow...")
            run_id = self._log_to_mlflow()
            result["mlflow_run_id"] = run_id
            print(f"✓ Logged MLflow run: {run_id}\n")
            
            # Populate results
            result["candidate_version"] = self.candidate_model.model_version if self.candidate_model else None
            result["champion_version"] = champion_model.model_version
            result["quality_gate_passed"] = gate_passed
            
            if self.candidate_metrics and self.champion_metrics:
                result["metrics_comparison"] = {
                    "candidate_rmse": self.candidate_metrics.get("rmse"),
                    "champion_rmse": self.champion_metrics.get("rmse"),
                    "rmse_delta": self.candidate_metrics.get("rmse", 0) - self.champion_metrics.get("rmse", 0)
                }
            
            result["message"] = f"Retraining completed - Status: {result['promotion_status']}"
            
            print("="*80)
            print(f"PIPELINE COMPLETE - {result['promotion_status'].upper()}")
            print("="*80 + "\n")
            
            return result
            
        except Exception as e:
            print(f"\n✗ Pipeline error: {e}\n")
            result["message"] = f"Pipeline error: {str(e)}"
            self.promotion_status = "rejected"
            result["promotion_status"] = "rejected"
            self._reject_candidate()
            return result


# Global retraining lock
_RETRAINING_LOCK = False


def trigger_retraining(champion_model: OTTRecommender, config: Optional[RetrainingConfig] = None) -> Dict[str, Any]:
    """
    Safely trigger retraining with duplicate prevention.
    
    Args:
        champion_model: The current production model to potentially replace
        config: Optional custom retraining configuration
    
    Returns:
        Result dict from the pipeline
    """
    global _RETRAINING_LOCK
    
    if _RETRAINING_LOCK:
        return {
            "success": False,
            "message": "Retraining already in progress",
            "promotion_status": "pending",
            "candidate_version": None,
            "champion_version": champion_model.model_version,
            "quality_gate_passed": False,
            "drift_trigger": None,
            "metrics_comparison": None,
            "mlflow_run_id": None
        }
    
    try:
        _RETRAINING_LOCK = True
        pipeline = RetrainingPipeline(config)
        return pipeline.execute(champion_model)
    finally:
        _RETRAINING_LOCK = False
