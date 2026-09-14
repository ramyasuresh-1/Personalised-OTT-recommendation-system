"""
Tests for Phase 1 baseline evaluation module.
"""

import os
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from ml.evaluate_baseline import BaselineEvaluator
from ml.split_data import split_ratings_by_interaction
from app.database import init_db, get_ratings_data


class TestBaselineEvaluator:
    """Test BaselineEvaluator class."""
    
    @pytest.fixture(scope="module", autouse=True)
    def setup(self):
        """Initialize database before tests."""
        init_db()
    
    @pytest.fixture
    def evaluator(self):
        """Create evaluator instance."""
        return BaselineEvaluator()
    
    @pytest.fixture
    def sample_splits(self):
        """Get sample train/test splits."""
        ratings = get_ratings_data()
        
        # Filter valid ratings
        valid_ratings = []
        for r in ratings:
            if r['user_id'] and r['movie_id'] and r['rating']:
                if 1.0 <= r['rating'] <= 5.0:
                    valid_ratings.append(r)
        
        train, val, test = split_ratings_by_interaction(
            valid_ratings,
            train_ratio=0.70,
            validation_ratio=0.15,
            test_ratio=0.15,
            random_state=42
        )
        
        return train, test
    
    def test_evaluator_initializes(self, evaluator):
        """Test that evaluator can be instantiated."""
        assert evaluator is not None
    
    def test_evaluate_on_testset_returns_dict(self, evaluator, sample_splits):
        """Test that evaluate_on_testset returns a dictionary."""
        train, test = sample_splits
        results = evaluator.evaluate_on_testset(train, test, k_values=[5, 10])
        assert isinstance(results, dict)
    
    def test_results_have_required_metrics(self, evaluator, sample_splits):
        """Test that results contain all required metrics."""
        train, test = sample_splits
        results = evaluator.evaluate_on_testset(train, test, k_values=[5, 10])
        
        # Rating prediction metrics
        assert 'rmse' in results
        assert 'mae' in results
        
        # Recommendation metrics
        assert 'precision' in results
        assert 'recall' in results
        assert 'hit_rate' in results
        assert 'ndcg' in results
        
        # Coverage and diversity
        assert 'catalog_coverage' in results
        assert 'recommendation_diversity' in results
    
    def test_precision_in_valid_range(self, evaluator, sample_splits):
        """Test that precision values are between 0 and 1."""
        train, test = sample_splits
        results = evaluator.evaluate_on_testset(train, test, k_values=[5, 10])
        
        for k_str, value in results['precision'].items():
            assert 0.0 <= value <= 1.0, f"Precision {k_str}={value} out of range"
    
    def test_recall_in_valid_range(self, evaluator, sample_splits):
        """Test that recall values are between 0 and 1."""
        train, test = sample_splits
        results = evaluator.evaluate_on_testset(train, test, k_values=[5, 10])
        
        for k_str, value in results['recall'].items():
            assert 0.0 <= value <= 1.0, f"Recall {k_str}={value} out of range"
    
    def test_hit_rate_in_valid_range(self, evaluator, sample_splits):
        """Test that hit rate values are between 0 and 1."""
        train, test = sample_splits
        results = evaluator.evaluate_on_testset(train, test, k_values=[5, 10])
        
        for k_str, value in results['hit_rate'].items():
            assert 0.0 <= value <= 1.0, f"Hit rate {k_str}={value} out of range"
    
    def test_ndcg_in_valid_range(self, evaluator, sample_splits):
        """Test that NDCG values are between 0 and 1."""
        train, test = sample_splits
        results = evaluator.evaluate_on_testset(train, test, k_values=[5, 10])
        
        for k_str, value in results['ndcg'].items():
            assert 0.0 <= value <= 1.0, f"NDCG {k_str}={value} out of range"
    
    def test_rmse_is_positive(self, evaluator, sample_splits):
        """Test that RMSE is non-negative."""
        train, test = sample_splits
        results = evaluator.evaluate_on_testset(train, test, k_values=[5, 10])
        assert results['rmse'] >= 0.0, "RMSE should be non-negative"
    
    def test_mae_is_positive(self, evaluator, sample_splits):
        """Test that MAE is non-negative."""
        train, test = sample_splits
        results = evaluator.evaluate_on_testset(train, test, k_values=[5, 10])
        assert results['mae'] >= 0.0, "MAE should be non-negative"
    
    def test_coverage_in_valid_range(self, evaluator, sample_splits):
        """Test that coverage is between 0 and 1."""
        train, test = sample_splits
        results = evaluator.evaluate_on_testset(train, test, k_values=[5, 10])
        assert 0.0 <= results['catalog_coverage'] <= 1.0
    
    def test_diversity_in_valid_range(self, evaluator, sample_splits):
        """Test that diversity is between 0 and 1."""
        train, test = sample_splits
        results = evaluator.evaluate_on_testset(train, test, k_values=[5, 10])
        assert 0.0 <= results['recommendation_diversity'] <= 1.0
    
    def test_evaluation_setup_logged(self, evaluator, sample_splits):
        """Test that evaluation setup is logged."""
        train, test = sample_splits
        results = evaluator.evaluate_on_testset(train, test, k_values=[5, 10])
        
        assert 'evaluation_setup' in results
        setup = results['evaluation_setup']
        assert 'num_test_users' in setup
        assert 'num_test_ratings' in setup
        assert 'model_params' in setup
    
    def test_results_serializable_to_json(self, evaluator, sample_splits):
        """Test that results can be serialized to JSON."""
        train, test = sample_splits
        results = evaluator.evaluate_on_testset(train, test, k_values=[5, 10])
        
        # Should not raise exception
        json_str = json.dumps(results)
        loaded = json.loads(json_str)
        
        assert loaded['rmse'] == results['rmse']


class TestTrainFunkSVD:
    """Test Funk SVD training specifically."""
    
    @pytest.fixture(scope="module", autouse=True)
    def setup(self):
        """Initialize database before tests."""
        init_db()
    
    @pytest.fixture
    def evaluator(self):
        """Create evaluator instance."""
        return BaselineEvaluator()
    
    @pytest.fixture
    def train_ratings(self):
        """Get training ratings."""
        ratings = get_ratings_data()
        
        # Filter valid ratings
        valid_ratings = []
        for r in ratings:
            if r['user_id'] and r['movie_id'] and r['rating']:
                if 1.0 <= r['rating'] <= 5.0:
                    valid_ratings.append(r)
        
        train, _, _ = split_ratings_by_interaction(
            valid_ratings,
            train_ratio=0.70,
            validation_ratio=0.15,
            test_ratio=0.15,
            random_state=42
        )
        
        return train
    
    def test_funk_svd_training_succeeds(self, evaluator, train_ratings):
        """Test that Funk SVD training completes without error."""
        P, Q, reconstructed_df, model_data = evaluator.train_funk_svd_from_ratings(
            train_ratings,
            k=6,
            epochs=35,
            lr=0.05,
            reg=0.02,
            random_state=42
        )
        
        assert P is not None
        assert Q is not None
        assert reconstructed_df is not None
        assert 'training_mse' in model_data
    
    def test_funk_svd_training_mse_is_valid(self, evaluator, train_ratings):
        """Test that training MSE is a valid number."""
        P, Q, reconstructed_df, model_data = evaluator.train_funk_svd_from_ratings(
            train_ratings,
            k=6,
            epochs=35,
            lr=0.05,
            reg=0.02,
            random_state=42
        )
        
        mse = model_data['training_mse']
        assert mse >= 0.0
        assert mse < 10.0  # Reasonable upper bound


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
