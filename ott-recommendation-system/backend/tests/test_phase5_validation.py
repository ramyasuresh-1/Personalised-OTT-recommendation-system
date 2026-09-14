#!/usr/bin/env python
"""
Phase 5 Final Validation Test Script

Tests:
1. No-drift scenario (stable ratings)
2. Drift scenario (injected bias)
3. Evidently report generation
4. Data quality checks
5. Drift detection results
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import init_db, get_ratings_data, insert_rating, get_all_movies
from app.monitoring import (
    evaluate_data_quality,
    evaluate_data_drift,
    detect_drift,
    _build_monitoring_frame,
    _get_evidently_reference_current,
)
import json
import pandas as pd

def test_no_drift_scenario():
    """Test with natural ratings (baseline drift measurement)."""
    print("\n" + "="*80)
    print("TEST 1: BASELINE DRIFT SCENARIO (Standard seeded data)")
    print("="*80)
    
    init_db()
    
    # Get ratings data
    ratings = get_ratings_data()
    print(f"✓ Loaded {len(ratings)} ratings")
    
    # Build monitoring frame
    df = _build_monitoring_frame()
    print(f"✓ Built monitoring frame with shape {df.shape}")
    print(f"  Columns: {list(df.columns)}")
    print(f"  Sample:\n{df.head()}")
    
    # Get reference and current
    reference, current = _get_evidently_reference_current()
    print(f"✓ Reference data: {reference.shape[0]} rows")
    print(f"✓ Current data: {current.shape[0]} rows")
    
    # Test data quality
    quality = evaluate_data_quality()
    print(f"\n✓ Data Quality Report:")
    print(f"  Status: {quality['status']}")
    print(f"  Quality Score: {quality['quality_score']}")
    print(f"  Summary: {json.dumps(quality['summary'], indent=2)}")
    
    # Test drift detection
    drift = evaluate_data_drift()
    print(f"\n✓ Evidently Drift Report:")
    print(f"  Status: {drift['status']}")
    print(f"  Drift Score: {drift['drift_score']}")
    print(f"  Summary: {json.dumps(drift['summary'], indent=2)}")
    
    # Test backward-compatible detect_drift
    psi_drift = detect_drift()
    print(f"\n✓ PSI-based Drift Report (Phase 4 compat):")
    print(f"  PSI: {psi_drift['psi']}")
    print(f"  Status: {psi_drift['status']}")
    print(f"  Message: {psi_drift['message']}")
    print(f"  Evidently Status: {psi_drift.get('evidently_status', 'N/A')}")
    
    # Verify structure
    assert 'status' in drift, "Missing status in drift report"
    assert 'drift_score' in drift, "Missing drift_score"
    assert 'summary' in drift, "Missing summary"
    assert isinstance(drift['drift_score'], (int, float)), "drift_score must be numeric"
    print("\n✓ BASELINE SCENARIO TEST PASSED - Evidently integration working")



def test_drift_scenario():
    """Test with injected extreme bias (clear drift)."""
    print("\n" + "="*80)
    print("TEST 2: INJECTED DRIFT SCENARIO (Extreme bias)")
    print("="*80)
    
    init_db()
    
    # Inject EXTREME skewed ratings for users 300-320 (all 5-star only)
    movies = get_all_movies()
    print(f"✓ Injecting extreme drift: All 5-star ratings for users 300-320")
    for user_id in range(300, 321):
        for movie in movies:
            insert_rating(user_id, movie["id"], 5.0)
    
    print(f"✓ Extreme drift injection complete")
    
    # Get updated ratings
    ratings = get_ratings_data()
    print(f"✓ Total ratings now: {len(ratings)}")
    
    # Rebuild monitoring frame
    df = _build_monitoring_frame()
    print(f"✓ Monitoring frame shape: {df.shape}")
    
    # Get reference and current
    reference, current = _get_evidently_reference_current()
    print(f"✓ Reference: {reference.shape[0]} rows")
    print(f"✓ Current: {current.shape[0]} rows")
    print(f"  Current rating distribution:\n{current['rating'].value_counts().sort_index()}")
    
    # Test drift detection
    drift = evaluate_data_drift()
    print(f"\n✓ Evidently Drift Report:")
    print(f"  Status: {drift['status']}")
    print(f"  Drift Score: {drift['drift_score']}")
    print(f"  Summary: {json.dumps(drift['summary'], indent=2)}")
    
    # Test backward-compatible detect_drift
    psi_drift = detect_drift()
    print(f"\n✓ PSI-based Drift Report (Phase 4 compat):")
    print(f"  PSI: {psi_drift['psi']}")
    print(f"  Status: {psi_drift['status']}")
    print(f"  Message: {psi_drift['message']}")
    print(f"  Evidently Status: {psi_drift.get('evidently_status', 'N/A')}")
    print(f"  Baseline dist: {psi_drift.get('baseline_dist', [])}")
    print(f"  Recent dist: {psi_drift.get('recent_dist', [])}")
    
    # Verify drift structure and it detects drift
    assert 'status' in drift, "Missing status in drift report"
    assert 'drift_score' in drift, "Missing drift_score"
    assert 'summary' in drift, "Missing summary"
    assert isinstance(drift['drift_score'], (int, float)), "drift_score must be numeric"
    # With extreme bias, drift should be detected
    assert drift['status'] in ['Warning', 'Drifted'], f"Expected drift to be detected, got status={drift['status']}"
    print("\n✓ INJECTED DRIFT TEST PASSED - Drift detected as expected")



def test_evidently_report_structure():
    """Verify Evidently report structure."""
    print("\n" + "="*80)
    print("TEST 3: EVIDENTLY REPORT STRUCTURE")
    print("="*80)
    
    init_db()
    
    quality = evaluate_data_quality()
    print(f"✓ Data Quality Report Keys: {list(quality.keys())}")
    assert "status" in quality
    assert "quality_score" in quality
    assert "summary" in quality
    assert "details" in quality
    
    drift = evaluate_data_drift()
    print(f"✓ Drift Report Keys: {list(drift.keys())}")
    assert "status" in drift
    assert "drift_score" in drift or "score" in drift
    assert "summary" in drift
    assert "details" in drift
    
    print("\n✓ EVIDENTLY REPORT STRUCTURE VALIDATED")


if __name__ == "__main__":
    try:
        test_no_drift_scenario()
        test_drift_scenario()
        test_evidently_report_structure()
        print("\n" + "="*80)
        print("ALL PHASE 5 TESTS PASSED ✓")
        print("="*80)
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
