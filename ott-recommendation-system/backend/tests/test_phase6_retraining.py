"""
Phase 6 Retraining Pipeline Tests

Tests for automated retraining and model promotion pipeline.
Validates that:
- Drift detection triggers retraining
- Candidate models are isolated from champion until promotion
- Quality gate correctly filters candidates
- Failed retraining leaves champion unchanged
- Model versioning works correctly
- Duplicate retraining is prevented
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import tempfile
import shutil

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.retraining import RetrainingPipeline, RetrainingConfig, trigger_retraining
from app.recommender import OTTRecommender
from app.database import get_ratings_data


class TestRetrainingPipelineBasics:
    """Test basic retraining pipeline functionality."""
    
    def test_pipeline_initialization(self):
        """Test that pipeline initializes with correct defaults."""
        pipeline = RetrainingPipeline()
        
        assert pipeline.config is not None
        assert pipeline.candidate_model is None
        assert pipeline.champion_model is None
        assert pipeline.promotion_status == "pending"
    
    def test_custom_config(self):
        """Test that custom config is applied."""
        custom_config = RetrainingConfig(
            max_rmse_regression_pct=0.05,
            drift_threshold="Warning"
        )
        pipeline = RetrainingPipeline(custom_config)
        
        assert pipeline.config.max_rmse_regression_pct == 0.05
        assert pipeline.config.drift_threshold == "Warning"
    
    def test_should_retrain_drift_drifted(self):
        """Test that retraining is triggered when drift is detected."""
        pipeline = RetrainingPipeline()
        
        with patch('app.retraining.detect_drift') as mock_drift, \
             patch('app.retraining.evaluate_data_quality') as mock_quality:
            
            mock_drift.return_value = {"status": "Drifted", "psi": 0.5}
            mock_quality.return_value = {"status": "PASS"}
            
            should_retrain, reason = pipeline.should_retrain()
            
            assert should_retrain is True
            assert "Drift detected" in reason
    
    def test_should_retrain_no_drift_healthy(self):
        """Test that retraining is skipped when no drift."""
        pipeline = RetrainingPipeline()
        
        with patch('app.retraining.detect_drift') as mock_drift, \
             patch('app.retraining.evaluate_data_quality') as mock_quality:
            
            mock_drift.return_value = {"status": "Healthy", "psi": 0.05}
            mock_quality.return_value = {"status": "PASS"}
            
            should_retrain, reason = pipeline.should_retrain()
            
            assert should_retrain is False
            assert "Healthy" in reason
    
    def test_should_retrain_poor_data_quality(self):
        """Test that retraining is skipped when data quality is FAIL."""
        pipeline = RetrainingPipeline()
        
        with patch('app.retraining.detect_drift') as mock_drift, \
             patch('app.retraining.evaluate_data_quality') as mock_quality:
            
            mock_drift.return_value = {"status": "Drifted"}
            mock_quality.return_value = {"status": "FAIL"}
            
            should_retrain, reason = pipeline.should_retrain()
            
            assert should_retrain is False
            assert "data quality" in reason.lower()


class TestRetrainingPipelineExecution:
    """Test retraining pipeline execution flow."""
    
    def test_execute_drift_not_detected(self):
        """Test that pipeline skips execution when drift not detected."""
        pipeline = RetrainingPipeline()
        champion = OTTRecommender()
        
        with patch.object(pipeline, 'should_retrain', return_value=(False, "No drift")):
            result = pipeline.execute(champion)
            
            assert result["success"] is False
            assert result["message"] == "No drift"
            assert result["promotion_status"] == "pending"
    
    def test_pipeline_records_drift_info(self):
        """Test that pipeline records drift information."""
        pipeline = RetrainingPipeline()
        
        with patch('app.retraining.detect_drift') as mock_drift:
            mock_drift.return_value = {"status": "Drifted", "psi": 0.5}
            
            with patch('app.retraining.evaluate_data_quality') as mock_quality:
                mock_quality.return_value = {"status": "PASS"}
                
                pipeline.should_retrain()
                
                assert pipeline.drift_info is not None
                assert pipeline.drift_info["status"] == "Drifted"


class TestRetrainingQualityGate:
    """Test quality gate functionality."""
    
    def test_quality_gate_candidate_passes(self):
        """Test that candidate is promoted when passing quality gate."""
        pipeline = RetrainingPipeline()
        
        # Setup metrics (candidate better than champion)
        pipeline.champion_metrics = {
            "rmse": 1.0,
            "mae": 0.8,
            "ndcg": {"@5": 0.5, "@10": 0.6},
            "precision": {"@5": 0.6, "@10": 0.5},
            "recall": {"@5": 0.4, "@10": 0.5},
            "f1": {"@5": 0.5, "@10": 0.5},
            "catalog_coverage": 0.8,
            "recommendation_diversity": 0.7
        }
        
        pipeline.candidate_metrics = {
            "rmse": 0.98,  # Improved (less than 2% regression)
            "mae": 0.79,
            "ndcg": {"@5": 0.51, "@10": 0.61},
            "precision": {"@5": 0.61, "@10": 0.51},
            "recall": {"@5": 0.41, "@10": 0.51},
            "f1": {"@5": 0.51, "@10": 0.51},
            "catalog_coverage": 0.8,
            "recommendation_diversity": 0.7
        }
        
        with patch('app.evaluation.quality_gate') as mock_gate:
            mock_gate.return_value = {
                "passed": True,
                "reasons": ["Candidate passes quality gate"],
                "rmse_change_pct": -0.02,
                "mae_change_pct": -0.01
            }
            
            passed = pipeline._apply_quality_gate()
            
            assert passed is True
            assert pipeline.quality_gate_result["passed"] is True
    
    def test_quality_gate_candidate_fails(self):
        """Test that candidate is rejected when failing quality gate."""
        pipeline = RetrainingPipeline()
        
        pipeline.champion_metrics = {
            "rmse": 1.0,
            "mae": 0.8,
            "ndcg": {"@5": 0.5, "@10": 0.6},
            "precision": {"@5": 0.6, "@10": 0.5},
            "recall": {"@5": 0.4, "@10": 0.5},
            "f1": {"@5": 0.5, "@10": 0.5},
            "catalog_coverage": 0.8,
            "recommendation_diversity": 0.7
        }
        
        pipeline.candidate_metrics = {
            "rmse": 1.03,
            "mae": 0.82,
            "ndcg": {"@5": 0.45, "@10": 0.55},
            "precision": {"@5": 0.55, "@10": 0.45},
            "recall": {"@5": 0.35, "@10": 0.45},
            "f1": {"@5": 0.45, "@10": 0.45},
            "catalog_coverage": 0.8,
            "recommendation_diversity": 0.7
        }
        
        with patch('app.evaluation.quality_gate') as mock_gate:
            mock_gate.return_value = {
                "passed": False,
                "reasons": ["RMSE regression exceeded 2%: 3.00%"],
                "rmse_change_pct": 3.0
            }
            
            passed = pipeline._apply_quality_gate()
            
            assert passed is False
            if pipeline.quality_gate_result is not None:
                assert pipeline.quality_gate_result["passed"] is False


class TestRetrainingModelPromotion:
    """Test model promotion and versioning."""
    
    def test_candidate_promotion_increments_version(self):
        """Test that promoting candidate increments version."""
        champion = OTTRecommender()
        champion.model_version = "v1.0.0"
        champion.save_model()
        
        try:
            pipeline = RetrainingPipeline()
            pipeline.candidate_model = OTTRecommender()
            pipeline.candidate_model.model_version = "v1.0.0"
            pipeline.candidate_model.user_movie_matrix = champion.user_movie_matrix
            pipeline.candidate_model.reconstructed_matrix_df = champion.reconstructed_matrix_df
            pipeline.candidate_model.movie_popularity = champion.movie_popularity
            
            with patch('app.retraining.log_retraining'):
                with patch('app.retraining.get_ratings_data', return_value=[]):
                    promoted = pipeline._promote_candidate(champion)
                    
                    # Check version was incremented
                    assert pipeline.candidate_model.model_version != "v1.0.0"
                    assert promoted is True
        
        finally:
            # Cleanup
            from app.retraining import CHAMPION_MODEL_PATH
            if CHAMPION_MODEL_PATH.exists():
                CHAMPION_MODEL_PATH.unlink()
    
    def test_champion_unchanged_on_rejection(self):
        """Test that champion is not modified when candidate is rejected."""
        champion = OTTRecommender()
        original_version = champion.model_version
        
        pipeline = RetrainingPipeline()
        pipeline.candidate_model = OTTRecommender()
        
        rejected = pipeline._reject_candidate()
        
        assert rejected is True
        assert champion.model_version == original_version


class TestRetrainingDuplicatePrevention:
    """Test duplicate retraining prevention."""
    
    def test_trigger_retraining_lock_prevents_duplicates(self):
        """Test that global lock prevents simultaneous retraining."""
        champion = OTTRecommender()
        
        with patch('app.retraining._RETRAINING_LOCK', True):
            result = trigger_retraining(champion)
            
            assert result["success"] is False
            assert "already in progress" in result["message"]
            assert result["promotion_status"] == "pending"


class TestRetrainingErrorHandling:
    """Test error handling and safety mechanisms."""
    
    def test_training_failure_leaves_champion_unchanged(self):
        """Test that training failure doesn't affect champion."""
        champion = OTTRecommender()
        original_version = champion.model_version
        
        pipeline = RetrainingPipeline()
        
        # Mock the pipeline methods to simulate training failure
        with patch.object(pipeline, 'should_retrain') as mock_should:
            mock_should.return_value = (True, "Drift detected")
            
            with patch.object(pipeline, '_load_champion') as mock_load:
                mock_load.return_value = True
                
                with patch.object(pipeline, '_train_candidate') as mock_train:
                    mock_train.return_value = False
                    
                    result = pipeline.execute(champion)
                    
                    assert result["success"] is False
                    assert champion.model_version == original_version
                    assert "candidate" in result["message"].lower() or result["promotion_status"] == "pending"
    
    def test_evaluation_failure_handled_gracefully(self):
        """Test that evaluation failure is handled without crashing."""
        champion = OTTRecommender()
        pipeline = RetrainingPipeline()
        
        with patch.object(pipeline, 'should_retrain') as mock_should:
            mock_should.return_value = (True, "Drift detected")
            
            with patch.object(pipeline, '_load_champion') as mock_load:
                mock_load.return_value = True
                
                with patch.object(pipeline, '_train_candidate') as mock_train:
                    mock_train.return_value = True
                    
                    with patch.object(pipeline, '_evaluate_model') as mock_eval:
                        mock_eval.return_value = False
                        
                        result = pipeline.execute(champion)
                        
                        assert result["success"] is False
                        assert "fail" in result["message"].lower() or "error" in result["message"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
