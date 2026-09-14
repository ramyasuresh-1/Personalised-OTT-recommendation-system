"""
Data quality validation module for OTT recommendation dataset.

Phase 1: Validates dataset against explicit business rules.
"""

import json
import os
import sys
from typing import Dict, Any, List, Tuple
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_ratings_data, get_all_movies


class DataValidator:
    """Validates recommendation dataset against explicit rules."""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.statistics: Dict[str, Any] = {}
        self.validation_timestamp = datetime.utcnow().isoformat()
    
    def validate(self) -> Dict[str, Any]:
        """
        Execute all validation rules.
        
        Returns:
            Validation report dictionary
        """
        ratings = get_ratings_data()
        movies = get_all_movies()
        
        # RULE 9: Detect empty dataset
        if not ratings:
            self.errors.append("RULE_9_EMPTY_DATASET: No ratings found in database.")
            return self._report(ratings, movies)
        
        if not movies:
            self.errors.append("RULE_9_EMPTY_DATASET: No movies found in database.")
            return self._report(ratings, movies)
        
        # RULE 1: user_id must not be null
        null_user_ids = [i for i, r in enumerate(ratings) if r['user_id'] is None]
        if null_user_ids:
            self.errors.append(f"RULE_1_NULL_USER_ID: {len(null_user_ids)} ratings have null user_id.")
        
        # RULE 2: movie_id must not be null
        null_movie_ids = [i for i, r in enumerate(ratings) if r['movie_id'] is None]
        if null_movie_ids:
            self.errors.append(f"RULE_2_NULL_MOVIE_ID: {len(null_movie_ids)} ratings have null movie_id.")
        
        # RULE 3: rating must not be null
        null_ratings = [i for i, r in enumerate(ratings) if r['rating'] is None]
        if null_ratings:
            self.errors.append(f"RULE_3_NULL_RATING: {len(null_ratings)} ratings have null rating value.")
        
        # RULE 4: rating must be within valid range (1.0 - 5.0)
        invalid_range_ratings = [
            (i, r) for i, r in enumerate(ratings) 
            if r['rating'] is not None and (r['rating'] < 1.0 or r['rating'] > 5.0)
        ]
        if invalid_range_ratings:
            self.errors.append(
                f"RULE_4_INVALID_RATING_RANGE: {len(invalid_range_ratings)} ratings outside range [1.0, 5.0]. "
                f"Examples: {invalid_range_ratings[:3]}"
            )
        
        # RULE 8: Detect invalid data types
        invalid_types = []
        for i, r in enumerate(ratings):
            try:
                uid = int(r['user_id']) if r['user_id'] is not None else None
                mid = int(r['movie_id']) if r['movie_id'] is not None else None
                rat = float(r['rating']) if r['rating'] is not None else None
            except (ValueError, TypeError) as e:
                invalid_types.append((i, r, str(e)))
        
        if invalid_types:
            self.errors.append(
                f"RULE_8_INVALID_DATA_TYPES: {len(invalid_types)} ratings have invalid data types. "
                f"Examples: {invalid_types[:2]}"
            )
        
        # RULE 5: user_id must reference valid user (check uniqueness)
        unique_user_ids = set(r['user_id'] for r in ratings if r['user_id'] is not None)
        if not unique_user_ids:
            self.errors.append("RULE_5_NO_VALID_USERS: No valid user IDs found.")
        
        # RULE 6: movie_id must reference an existing movie
        valid_movie_ids = set(m['id'] for m in movies)
        invalid_movie_refs = []
        for i, r in enumerate(ratings):
            if r['movie_id'] is not None and r['movie_id'] not in valid_movie_ids:
                invalid_movie_refs.append((i, r))
        
        if invalid_movie_refs:
            self.errors.append(
                f"RULE_6_INVALID_MOVIE_REFERENCE: {len(invalid_movie_refs)} ratings reference non-existent movies. "
                f"Examples: {invalid_movie_refs[:3]}"
            )
        
        # RULE 7: Detect duplicate user/movie interactions
        interaction_pairs = {}
        duplicates = []
        for i, r in enumerate(ratings):
            if r['user_id'] is not None and r['movie_id'] is not None:
                pair = (r['user_id'], r['movie_id'])
                if pair in interaction_pairs:
                    duplicates.append((interaction_pairs[pair], i, pair))
                else:
                    interaction_pairs[pair] = i
        
        if duplicates:
            self.warnings.append(
                f"RULE_7_DUPLICATE_INTERACTIONS: {len(duplicates)} duplicate user-movie interactions detected. "
                f"Examples: {duplicates[:3]}"
            )
        
        # RULE 11: Detect unexpected rating values (edges)
        rating_values = set(r['rating'] for r in ratings if r['rating'] is not None)
        expected_values = {1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0}
        unexpected_values = rating_values - expected_values
        if unexpected_values:
            self.warnings.append(
                f"RULE_11_UNEXPECTED_RATING_VALUES: Found unexpected rating values: {sorted(unexpected_values)}"
            )
        
        # RULE 10: Report extreme sparsity
        num_ratings = len(ratings)
        num_users = len(unique_user_ids)
        num_movies = len(valid_movie_ids)
        max_interactions = num_users * num_movies
        sparsity = (1 - (num_ratings / max_interactions)) * 100 if max_interactions > 0 else 0
        
        if sparsity > 95:
            self.warnings.append(
                f"RULE_10_EXTREME_SPARSITY: Dataset is {sparsity:.2f}% sparse "
                f"({num_ratings} ratings out of {max_interactions} possible interactions)."
            )
        
        # RULE 12: Detect data distribution anomalies
        from collections import Counter
        rating_counts = Counter(r['rating'] for r in ratings if r['rating'] is not None)
        rating_dist = {r: c/num_ratings for r, c in rating_counts.items()}
        
        # Check for heavily skewed distributions
        max_freq = max(rating_dist.values()) if rating_dist else 0
        if max_freq > 0.5:  # One rating value represents >50% of data
            self.warnings.append(
                f"RULE_12_SKEWED_DISTRIBUTION: Rating distribution is heavily skewed. "
                f"Most common rating {max(rating_dist, key=rating_dist.get)} appears {max_freq*100:.2f}% of the time."
            )
        
        return self._report(ratings, movies)
    
    def _report(self, ratings: List[Dict], movies: List[Dict]) -> Dict[str, Any]:
        """Generate validation report."""
        
        # Calculate statistics
        num_ratings = len(ratings)
        unique_users = len(set(r['user_id'] for r in ratings if r['user_id'] is not None))
        unique_movies = len(set(r['movie_id'] for r in ratings if r['movie_id'] is not None))
        
        rating_values = [r['rating'] for r in ratings if r['rating'] is not None]
        
        self.statistics = {
            "total_ratings": num_ratings,
            "unique_users": unique_users,
            "unique_movies": unique_movies,
            "total_movies_in_catalog": len(movies),
            "rating_range": {
                "min": min(rating_values) if rating_values else None,
                "max": max(rating_values) if rating_values else None
            },
            "rows_checked": num_ratings
        }
        
        report = {
            "status": "PASS" if not self.errors else "FAIL",
            "validation_timestamp": self.validation_timestamp,
            "errors": self.errors,
            "warnings": self.warnings,
            "statistics": self.statistics,
            "summary": {
                "total_errors": len(self.errors),
                "total_warnings": len(self.warnings),
                "critical": "Yes" if self.errors else "No"
            }
        }
        
        return report


def validate_dataset() -> Dict[str, Any]:
    """
    Run data validation.
    
    Returns:
        Validation report
    """
    validator = DataValidator()
    report = validator.validate()
    return report


def save_validation_report(report: Dict[str, Any], output_dir: str = "docs") -> str:
    """
    Save validation report to JSON.
    
    Args:
        report: Validation report dictionary
        output_dir: Output directory path
    
    Returns:
        Path to saved report file
    """
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, "data_quality_report.json")
    
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"Saved data quality report to {output_path}")
    
    # Also print summary
    print(f"\nValidation Status: {report.get('status', 'UNKNOWN')}")
    print(f"Errors: {report.get('summary', {}).get('total_errors', 0)}")
    print(f"Warnings: {report.get('summary', {}).get('total_warnings', 0)}")
    
    if report.get('errors'):
        print("\nErrors:")
        for error in report.get('errors', []):
            print(f"  - {error}")
    
    if report.get('warnings'):
        print("\nWarnings:")
        for warning in report.get('warnings', []):
            print(f"  - {warning}")
    
    return output_path


if __name__ == "__main__":
    print("Validating dataset...")
    report = validate_dataset()
    save_validation_report(report)
    print("Data validation complete!")
