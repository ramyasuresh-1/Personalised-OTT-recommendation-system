import os
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.evaluation import (
    QualityGateConfig,
    compute_f1,
    safe_percent_change,
    load_model_state,
    evaluate_model_state,
    compare_models,
    quality_gate,
    run_evaluation,
    MODEL_PATH,
    BASELINE_EVALUATION_PATH
)
from app.database import init_db, get_ratings_data


def test_compute_f1_zero_precision_recall():
    assert compute_f1(0.0, 0.0) == 0.0


def test_safe_percent_change_zero_base():
    assert safe_percent_change(0.0, 0.0) == 0.0
    assert safe_percent_change(0.0, 1.0) == float('inf')


def test_load_model_state_existing():
    model_path = MODEL_PATH
    if not model_path.exists():
        raise AssertionError("Production model artifact is missing for test.")
    state = load_model_state(model_path)
    assert 'model_version' in state
    assert 'reconstructed_matrix_df' in state
    assert 'user_movie_matrix' in state
    assert 'movie_popularity' in state


def test_quality_gate_pass_on_improved_candidate():
    baseline = {
        'rmse': 2.5,
        'mae': 1.8,
        'precision': {'@5': 0.2},
        'recall': {'@5': 0.4},
        'ndcg': {'@10': 0.45, '@5': 0.35},
        'f1': {'@5': 0.27},
        'catalog_coverage': 1.0,
        'recommendation_diversity': 0.03
    }
    candidate = {
        'rmse': 2.4,
        'mae': 1.75,
        'precision': {'@5': 0.21},
        'recall': {'@5': 0.41},
        'ndcg': {'@10': 0.46, '@5': 0.36},
        'f1': {'@5': 0.28},
        'catalog_coverage': 1.0,
        'recommendation_diversity': 0.031
    }
    config = QualityGateConfig()
    result = quality_gate(baseline, candidate, config)
    assert result['passed'] is True


def test_quality_gate_fail_on_rmse_regression():
    baseline = {
        'rmse': 2.5,
        'mae': 1.8,
        'precision': {'@5': 0.2},
        'recall': {'@5': 0.4},
        'ndcg': {'@10': 0.45, '@5': 0.35},
        'f1': {'@5': 0.27},
        'catalog_coverage': 1.0,
        'recommendation_diversity': 0.03
    }
    candidate = {
        'rmse': 2.55,
        'mae': 1.82,
        'precision': {'@5': 0.19},
        'recall': {'@5': 0.39},
        'ndcg': {'@10': 0.44, '@5': 0.34},
        'f1': {'@5': 0.26},
        'catalog_coverage': 0.98,
        'recommendation_diversity': 0.029
    }
    config = QualityGateConfig()
    result = quality_gate(baseline, candidate, config)
    assert result['passed'] is False
    assert any('RMSE regression' in reason or 'NDCG@10 degraded' in reason for reason in result['reasons'])


def test_small_evaluation_flow():
    init_db()
    ratings = get_ratings_data()
    assert len(ratings) > 0
    config = QualityGateConfig()
    assert config.dataset_version == 'phase_1'
    # This test ensures the quality gate object can be instantiated and used.


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-q'])
