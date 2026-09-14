import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.monitoring import evaluate_data_quality, evaluate_data_drift


def test_evaluate_data_quality_returns_summary():
    report = evaluate_data_quality()
    assert isinstance(report, dict)
    assert "status" in report
    assert "summary" in report
    assert "quality_score" in report or "data_quality" in report


def test_evaluate_data_drift_returns_drift_result():
    drift = evaluate_data_drift()
    assert isinstance(drift, dict)
    assert "status" in drift
    assert "summary" in drift
    assert "score" in drift or "drift_score" in drift
