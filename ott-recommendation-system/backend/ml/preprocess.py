"""
Data preprocessing module for OTT recommendation dataset.

Phase 1: Loads, validates, and preprocesses raw data deterministically.
"""

import csv
import os
import sys
from typing import List, Dict, Any, Tuple
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_ratings_data, get_all_movies


def preprocess_ratings(
    remove_duplicates: bool = False,
    output_dir: str = "data"
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Preprocess ratings dataset.
    
    Steps:
    1. Load raw data
    2. Validate schema
    3. Optionally remove exact duplicates
    4. Sort deterministically
    5. Save to CSV
    
    Args:
        remove_duplicates: Whether to remove exact duplicate interactions
        output_dir: Output directory for processed data
    
    Returns:
        Tuple of (processed ratings list, output file path)
    """
    
    # Load raw data
    ratings = get_ratings_data()
    movies = get_all_movies()
    
    print(f"Loaded {len(ratings)} raw ratings from database")
    print(f"Loaded {len(movies)} movies from database")
    
    if not ratings:
        raise ValueError("No ratings data found in database.")
    
    # Validate schema
    required_fields = {'user_id', 'movie_id', 'rating'}
    sample_rating = ratings[0] if ratings else {}
    missing_fields = required_fields - set(sample_rating.keys())
    
    if missing_fields:
        raise ValueError(f"Missing required fields in ratings: {missing_fields}")
    
    # Get valid movie IDs
    valid_movie_ids = set(m['id'] for m in movies)
    
    # Filter and validate records
    processed_ratings = []
    invalid_count = 0
    
    for r in ratings:
        try:
            user_id = int(r['user_id'])
            movie_id = int(r['movie_id'])
            rating = float(r['rating'])
            
            # Validate values
            if user_id <= 0:
                invalid_count += 1
                continue
            
            if movie_id not in valid_movie_ids:
                invalid_count += 1
                continue
            
            if not (1.0 <= rating <= 5.0):
                invalid_count += 1
                continue
            
            processed_ratings.append({
                'user_id': user_id,
                'movie_id': movie_id,
                'rating': rating
            })
        
        except (ValueError, TypeError):
            invalid_count += 1
            continue
    
    print(f"Removed {invalid_count} invalid records")
    print(f"Valid ratings: {len(processed_ratings)}")
    
    # Remove duplicates if requested (keep first occurrence)
    if remove_duplicates:
        seen = set()
        unique_ratings = []
        dup_count = 0
        
        for r in processed_ratings:
            pair = (r['user_id'], r['movie_id'])
            if pair not in seen:
                unique_ratings.append(r)
                seen.add(pair)
            else:
                dup_count += 1
        
        print(f"Removed {dup_count} duplicate interactions")
        processed_ratings = unique_ratings
    
    # Sort deterministically by user_id then movie_id
    processed_ratings.sort(key=lambda x: (x['user_id'], x['movie_id']))
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    processed_dir = os.path.join(output_dir, 'processed')
    os.makedirs(processed_dir, exist_ok=True)
    
    # Save to CSV
    output_file = os.path.join(processed_dir, 'ratings_processed.csv')
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['user_id', 'movie_id', 'rating'])
        writer.writeheader()
        writer.writerows(processed_ratings)
    
    print(f"Saved {len(processed_ratings)} processed ratings to {output_file}")
    
    return processed_ratings, output_file


def load_processed_ratings(filepath: str) -> List[Dict[str, Any]]:
    """
    Load preprocessed ratings from CSV.
    
    Args:
        filepath: Path to processed ratings CSV
    
    Returns:
        List of rating dictionaries
    """
    ratings = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ratings.append({
                'user_id': int(row['user_id']),
                'movie_id': int(row['movie_id']),
                'rating': float(row['rating'])
            })
    
    return ratings


if __name__ == "__main__":
    print("Preprocessing dataset...")
    ratings, output_file = preprocess_ratings(remove_duplicates=False)
    print(f"Preprocessing complete! Output: {output_file}")
