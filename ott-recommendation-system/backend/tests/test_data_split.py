"""
Tests for Phase 1 data splitting module.
"""

import os
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from ml.split_data import (
    split_ratings_by_interaction,
    verify_no_overlap,
    create_splits
)
from ml.preprocess import preprocess_ratings
from app.database import init_db, get_ratings_data


class TestDataSplit:
    """Test data splitting module."""
    
    @pytest.fixture(scope="module", autouse=True)
    def setup(self):
        """Initialize database and preprocess data before tests."""
        init_db()
    
    @pytest.fixture
    def sample_ratings(self):
        """Get sample ratings from database."""
        ratings = get_ratings_data()
        # Preprocess to ensure valid data
        valid_ratings = []
        for r in ratings:
            if r['user_id'] and r['movie_id'] and r['rating']:
                if 1.0 <= r['rating'] <= 5.0:
                    valid_ratings.append(r)
        return valid_ratings
    
    def test_split_creates_three_sets(self, sample_ratings):
        """Test that split creates three distinct sets."""
        train, val, test = split_ratings_by_interaction(
            sample_ratings,
            train_ratio=0.70,
            validation_ratio=0.15,
            test_ratio=0.15,
            random_state=42
        )
        
        assert len(train) > 0
        assert len(val) > 0
        assert len(test) > 0
    
    def test_split_ratios_approximate(self, sample_ratings):
        """Test that split ratios are approximately correct."""
        train, val, test = split_ratings_by_interaction(
            sample_ratings,
            train_ratio=0.70,
            validation_ratio=0.15,
            test_ratio=0.15,
            random_state=42
        )
        
        total = len(train) + len(val) + len(test)
        train_pct = len(train) / total
        val_pct = len(val) / total
        test_pct = len(test) / total
        
        # Allow ±5% variance due to rounding
        assert 0.65 <= train_pct <= 0.75, f"Train ratio {train_pct} out of range"
        assert 0.10 <= val_pct <= 0.20, f"Val ratio {val_pct} out of range"
        assert 0.10 <= test_pct <= 0.20, f"Test ratio {test_pct} out of range"
    
    def test_split_is_deterministic(self, sample_ratings):
        """Test that same random_state produces same split."""
        train1, val1, test1 = split_ratings_by_interaction(
            sample_ratings,
            random_state=42
        )
        
        train2, val2, test2 = split_ratings_by_interaction(
            sample_ratings,
            random_state=42
        )
        
        # Compare first few elements (order should be identical)
        assert train1[:5] == train2[:5]
        assert val1[:5] == val2[:5]
        assert test1[:5] == test2[:5]
    
    def test_no_overlap_between_splits(self, sample_ratings):
        """Test that there is no overlap between splits."""
        train, val, test = split_ratings_by_interaction(
            sample_ratings,
            train_ratio=0.70,
            validation_ratio=0.15,
            test_ratio=0.15,
            random_state=42
        )
        
        # Verify no overlap
        result = verify_no_overlap(train, val, test)
        assert result is True, "Overlapping interactions detected"
    
    def test_all_data_accounted_for(self, sample_ratings):
        """Test that all data is accounted for in splits."""
        train, val, test = split_ratings_by_interaction(
            sample_ratings,
            train_ratio=0.70,
            validation_ratio=0.15,
            test_ratio=0.15,
            random_state=42
        )
        
        total_split = len(train) + len(val) + len(test)
        assert total_split == len(sample_ratings), "Data loss in split"
    
    def test_split_ratios_validation(self):
        """Test that invalid split ratios raise error."""
        sample_ratings = [
            {'user_id': 1, 'movie_id': 1, 'rating': 5.0},
            {'user_id': 2, 'movie_id': 2, 'rating': 4.0}
        ]
        
        # Ratios sum to > 1.0
        with pytest.raises(ValueError):
            split_ratings_by_interaction(
                sample_ratings,
                train_ratio=0.7,
                validation_ratio=0.2,
                test_ratio=0.2
            )


class TestSplitData:
    """Test complete split_data pipeline."""
    
    @pytest.fixture(scope="module", autouse=True)
    def setup(self):
        """Initialize database and preprocess before tests."""
        init_db()
        # Preprocess data
        preprocess_ratings(remove_duplicates=False)
    
    def test_create_splits_succeeds(self):
        """Test that create_splits completes successfully."""
        result = create_splits(
            train_ratio=0.70,
            validation_ratio=0.15,
            test_ratio=0.15,
            random_state=42
        )
        
        assert result['status'] == 'success'
        assert result['train_count'] > 0
        assert result['validation_count'] > 0
        assert result['test_count'] > 0
    
    def test_split_files_created(self, tmp_path):
        """Test that split files are created."""
        output_dir = str(tmp_path / "splits")
        
        result = create_splits(
            train_ratio=0.70,
            validation_ratio=0.15,
            test_ratio=0.15,
            random_state=42
        )
        
        assert 'files' in result
        assert 'train' in result['files']
        assert 'validation' in result['files']
        assert 'test' in result['files']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
