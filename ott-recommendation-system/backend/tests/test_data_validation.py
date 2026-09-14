"""
Tests for Phase 1 data validation module.
"""

import os
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from ml.data_validation import validate_dataset, DataValidator
from app.database import init_db


class TestDataValidation:
    """Test data validation module."""
    
    @pytest.fixture(scope="module", autouse=True)
    def setup(self):
        """Initialize database before tests."""
        init_db()
    
    def test_validate_dataset_returns_dict(self):
        """Test that validate_dataset returns a dictionary."""
        report = validate_dataset()
        assert isinstance(report, dict)
    
    def test_report_has_required_fields(self):
        """Test that report contains required fields."""
        report = validate_dataset()
        assert 'status' in report
        assert 'errors' in report
        assert 'warnings' in report
        assert 'statistics' in report
        assert 'validation_timestamp' in report
        assert 'summary' in report
    
    def test_report_status_is_pass_or_fail(self):
        """Test that status is either PASS or FAIL."""
        report = validate_dataset()
        assert report['status'] in ['PASS', 'FAIL']
    
    def test_errors_is_list(self):
        """Test that errors is a list."""
        report = validate_dataset()
        assert isinstance(report['errors'], list)
    
    def test_warnings_is_list(self):
        """Test that warnings is a list."""
        report = validate_dataset()
        assert isinstance(report['warnings'], list)
    
    def test_statistics_has_data(self):
        """Test that statistics contains expected fields."""
        report = validate_dataset()
        stats = report['statistics']
        assert 'total_ratings' in stats
        assert 'unique_users' in stats
        assert 'unique_movies' in stats
        assert 'rows_checked' in stats
        
        # Check that values are reasonable
        assert stats['total_ratings'] > 0
        assert stats['unique_users'] > 0
        assert stats['unique_movies'] > 0
    
    def test_no_critical_errors(self):
        """Test that there are no critical validation errors."""
        report = validate_dataset()
        # With seeded data, should have no critical errors
        # (but may have warnings about distribution)
        critical_errors = [e for e in report['errors'] if 'NULL' in e or 'INVALID' in e]
        assert len(critical_errors) == 0, f"Found critical errors: {critical_errors}"
    
    def test_summary_counts_match(self):
        """Test that summary error/warning counts match actual lists."""
        report = validate_dataset()
        summary = report['summary']
        assert summary['total_errors'] == len(report['errors'])
        assert summary['total_warnings'] == len(report['warnings'])


class TestDataValidator:
    """Test DataValidator class directly."""
    
    @pytest.fixture(scope="module", autouse=True)
    def setup(self):
        """Initialize database before tests."""
        init_db()
    
    def test_validator_initializes(self):
        """Test that validator can be instantiated."""
        validator = DataValidator()
        assert validator.errors == []
        assert validator.warnings == []
    
    def test_validate_method_returns_dict(self):
        """Test that validate method returns a dict."""
        validator = DataValidator()
        report = validator.validate()
        assert isinstance(report, dict)


class TestDataQualityReport:
    """Test that data quality report can be saved."""
    
    @pytest.fixture(scope="module", autouse=True)
    def setup(self):
        """Initialize database before tests."""
        init_db()
    
    def test_report_can_be_saved_as_json(self, tmp_path):
        """Test that report can be saved as JSON."""
        report = validate_dataset()
        
        # Save to temp directory
        output_file = str(tmp_path / "test_report.json")
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Verify file exists
        assert os.path.exists(output_file)
        
        # Verify can be read back
        with open(output_file, 'r') as f:
            loaded = json.load(f)
        
        assert loaded['status'] == report['status']
        assert len(loaded['errors']) == len(report['errors'])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
