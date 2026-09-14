"""
Data splitting module for train/validation/test sets.

Phase 1: Creates reproducible train/validation/test splits for recommendation datasets.
"""

import csv
import json
import os
import sys
from typing import List, Dict, Any, Tuple
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ml.preprocess import load_processed_ratings


def split_ratings_by_interaction(
    ratings: List[Dict[str, Any]],
    train_ratio: float = 0.70,
    validation_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_state: int = 42
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Split ratings into train/validation/test sets at the interaction level.
    
    This approach:
    - Ensures no data leakage (same interaction never appears in multiple sets)
    - Is deterministic with random_state
    - Preserves user/movie relationships
    - Simple and reproducible
    
    Args:
        ratings: List of rating dictionaries
        train_ratio: Proportion for training (0.0-1.0)
        validation_ratio: Proportion for validation (0.0-1.0)
        test_ratio: Proportion for testing (0.0-1.0)
        random_state: Random seed for reproducibility
    
    Returns:
        Tuple of (train_ratings, validation_ratings, test_ratings)
    """
    
    # Validate ratios
    total_ratio = train_ratio + validation_ratio + test_ratio
    if abs(total_ratio - 1.0) > 0.001:
        raise ValueError(f"Split ratios must sum to 1.0, got {total_ratio}")
    
    # Shuffle with deterministic seed
    import random
    random.seed(random_state)
    
    shuffled_ratings = ratings.copy()
    random.shuffle(shuffled_ratings)
    
    # Calculate split indices
    n = len(shuffled_ratings)
    train_end = int(n * train_ratio)
    val_end = train_end + int(n * validation_ratio)
    
    # Split
    train_ratings = shuffled_ratings[:train_end]
    validation_ratings = shuffled_ratings[train_end:val_end]
    test_ratings = shuffled_ratings[val_end:]
    
    return train_ratings, validation_ratings, test_ratings


def save_splits(
    train_ratings: List[Dict[str, Any]],
    validation_ratings: List[Dict[str, Any]],
    test_ratings: List[Dict[str, Any]],
    output_dir: str = "data/splits"
) -> Dict[str, str]:
    """
    Save train/validation/test splits to CSV files.
    
    Args:
        train_ratings: Training set ratings
        validation_ratings: Validation set ratings
        test_ratings: Test set ratings
        output_dir: Output directory
    
    Returns:
        Dictionary with paths to created files
    """
    
    os.makedirs(output_dir, exist_ok=True)
    
    files = {}
    
    # Save training set
    train_file = os.path.join(output_dir, 'train.csv')
    with open(train_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['user_id', 'movie_id', 'rating'])
        writer.writeheader()
        writer.writerows(train_ratings)
    files['train'] = train_file
    print(f"Saved {len(train_ratings)} training ratings to {train_file}")
    
    # Save validation set
    val_file = os.path.join(output_dir, 'validation.csv')
    with open(val_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['user_id', 'movie_id', 'rating'])
        writer.writeheader()
        writer.writerows(validation_ratings)
    files['validation'] = val_file
    print(f"Saved {len(validation_ratings)} validation ratings to {val_file}")
    
    # Save test set
    test_file = os.path.join(output_dir, 'test.csv')
    with open(test_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['user_id', 'movie_id', 'rating'])
        writer.writeheader()
        writer.writerows(test_ratings)
    files['test'] = test_file
    print(f"Saved {len(test_ratings)} test ratings to {test_file}")
    
    # Save split metadata
    metadata = {
        "split_timestamp": "2026-08-11",
        "random_state": 42,
        "train_count": len(train_ratings),
        "validation_count": len(validation_ratings),
        "test_count": len(test_ratings),
        "total_count": len(train_ratings) + len(validation_ratings) + len(test_ratings),
        "train_ratio": len(train_ratings) / (len(train_ratings) + len(validation_ratings) + len(test_ratings)),
        "validation_ratio": len(validation_ratings) / (len(train_ratings) + len(validation_ratings) + len(test_ratings)),
        "test_ratio": len(test_ratings) / (len(train_ratings) + len(validation_ratings) + len(test_ratings)),
        "split_strategy": "interaction_level_shuffle",
        "train_file": train_file,
        "validation_file": val_file,
        "test_file": test_file
    }
    
    metadata_file = os.path.join(output_dir, 'split_metadata.json')
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Saved split metadata to {metadata_file}")
    
    return files


def verify_no_overlap(
    train_ratings: List[Dict[str, Any]],
    validation_ratings: List[Dict[str, Any]],
    test_ratings: List[Dict[str, Any]]
) -> bool:
    """
    Verify that there is no overlap between splits.
    
    Args:
        train_ratings: Training set ratings
        validation_ratings: Validation set ratings
        test_ratings: Test set ratings
    
    Returns:
        True if no overlap found
    """
    
    train_pairs = set((r['user_id'], r['movie_id']) for r in train_ratings)
    val_pairs = set((r['user_id'], r['movie_id']) for r in validation_ratings)
    test_pairs = set((r['user_id'], r['movie_id']) for r in test_ratings)
    
    # Check for overlaps
    train_val_overlap = train_pairs & val_pairs
    train_test_overlap = train_pairs & test_pairs
    val_test_overlap = val_pairs & test_pairs
    
    all_overlap = train_val_overlap | train_test_overlap | val_test_overlap
    
    if all_overlap:
        print(f"⚠️  WARNING: Found {len(all_overlap)} overlapping interactions!")
        print(f"   Train-Val: {len(train_val_overlap)}")
        print(f"   Train-Test: {len(train_test_overlap)}")
        print(f"   Val-Test: {len(val_test_overlap)}")
        return False
    
    print("✓ No overlapping interactions between splits")
    return True


def create_splits(
    processed_ratings_file: str = "data/processed/ratings_processed.csv",
    output_dir: str = "data/splits",
    train_ratio: float = 0.70,
    validation_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_state: int = 42
) -> Dict[str, Any]:
    """
    Load processed ratings and create train/validation/test splits.
    
    Args:
        processed_ratings_file: Path to processed ratings CSV
        output_dir: Output directory for splits
        train_ratio: Training proportion
        validation_ratio: Validation proportion
        test_ratio: Test proportion
        random_state: Random seed
    
    Returns:
        Dictionary with split statistics
    """
    
    print(f"Loading processed ratings from {processed_ratings_file}...")
    if not os.path.exists(processed_ratings_file):
        raise FileNotFoundError(f"Processed ratings file not found: {processed_ratings_file}")
    
    ratings = load_processed_ratings(processed_ratings_file)
    print(f"Loaded {len(ratings)} ratings")
    
    # Create splits
    print("\nSplitting data...")
    train, val, test = split_ratings_by_interaction(
        ratings,
        train_ratio=train_ratio,
        validation_ratio=validation_ratio,
        test_ratio=test_ratio,
        random_state=random_state
    )
    
    print(f"Train: {len(train)} ratings ({len(train)/len(ratings)*100:.1f}%)")
    print(f"Val:   {len(val)} ratings ({len(val)/len(ratings)*100:.1f}%)")
    print(f"Test:  {len(test)} ratings ({len(test)/len(ratings)*100:.1f}%)")
    
    # Verify no overlap
    print("\nVerifying no data leakage...")
    verify_no_overlap(train, val, test)
    
    # Save splits
    print("\nSaving splits...")
    files = save_splits(train, val, test, output_dir)
    
    # Return summary
    return {
        "status": "success",
        "total_ratings": len(ratings),
        "train_count": len(train),
        "validation_count": len(val),
        "test_count": len(test),
        "train_ratio": len(train) / len(ratings),
        "validation_ratio": len(val) / len(ratings),
        "test_ratio": len(test) / len(ratings),
        "files": files,
        "random_state": random_state
    }


if __name__ == "__main__":
    print("Creating train/validation/test splits...")
    result = create_splits()
    print(f"\nSplit creation complete!")
    print(f"Status: {result['status']}")
