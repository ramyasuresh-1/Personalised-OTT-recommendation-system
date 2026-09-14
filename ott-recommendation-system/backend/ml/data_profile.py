"""
Data profiling module for OTT recommendation dataset.

Phase 1: Analyzes dataset characteristics without modification.
"""

import json
import os
import sys
from typing import Dict, Any, List
from pathlib import Path
from collections import Counter

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_db_connection, get_ratings_data, get_all_movies


def profile_dataset() -> Dict[str, Any]:
    """
    Comprehensive dataset profiling.
    
    Returns:
        Dictionary containing all dataset statistics
    """
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get raw data
    ratings = get_ratings_data()
    movies = get_all_movies()
    
    # Basic counts
    num_ratings = len(ratings)
    num_unique_users = len(set(r['user_id'] for r in ratings))
    num_unique_movies = len(set(r['movie_id'] for r in ratings))
    num_total_movies = len(movies)
    
    # Rating statistics
    ratings_list = [r['rating'] for r in ratings]
    ratings_sorted = sorted(ratings_list)
    
    # Calculate percentiles manually
    def percentile(data, p):
        if not data:
            return None
        k = (len(data) - 1) * p / 100
        f = int(k)
        c = k - f
        if f + 1 < len(data):
            return data[f] * (1 - c) + data[f + 1] * c
        return data[f]
    
    mean_rating = sum(ratings_list) / len(ratings_list) if ratings_list else 0
    median_rating = percentile(ratings_sorted, 50)
    
    # Standard deviation
    variance = sum((r - mean_rating) ** 2 for r in ratings_list) / len(ratings_list) if ratings_list else 0
    std_dev = variance ** 0.5
    
    # Rating distribution
    rating_counts = Counter(ratings_list)
    rating_distribution = {
        float(rating): count for rating, count in sorted(rating_counts.items())
    }
    
    # User activity distribution
    user_ratings = {}
    for r in ratings:
        uid = r['user_id']
        user_ratings[uid] = user_ratings.get(uid, 0) + 1
    
    user_activity = list(user_ratings.values())
    user_activity_sorted = sorted(user_activity)
    
    # Movie popularity distribution
    movie_ratings = {}
    for r in ratings:
        mid = r['movie_id']
        movie_ratings[mid] = movie_ratings.get(mid, 0) + 1
    
    movie_popularity = list(movie_ratings.values())
    movie_popularity_sorted = sorted(movie_popularity)
    
    # Missing values check
    missing_user_ids = sum(1 for r in ratings if r['user_id'] is None)
    missing_movie_ids = sum(1 for r in ratings if r['movie_id'] is None)
    missing_ratings = sum(1 for r in ratings if r['rating'] is None)
    
    # Duplicate check (same user, same movie)
    interaction_pairs = set()
    duplicate_count = 0
    for r in ratings:
        pair = (r['user_id'], r['movie_id'])
        if pair in interaction_pairs:
            duplicate_count += 1
        interaction_pairs.add(pair)
    
    # Movie metadata check
    movie_ids_in_ratings = set(r['movie_id'] for r in ratings)
    movie_ids_in_catalog = set(m['id'] for m in movies)
    invalid_movie_refs = len(movie_ids_in_ratings - movie_ids_in_catalog)
    
    # Sparsity
    max_possible_interactions = num_unique_users * num_total_movies
    sparsity = (1 - (num_ratings / max_possible_interactions)) * 100 if max_possible_interactions > 0 else 0
    
    # Genre distribution from movies
    genre_counts = Counter(m['genre'] for m in movies if 'genre' in m)
    
    # Year distribution
    year_counts = Counter(m['year'] for m in movies if 'year' in m)
    
    profile = {
        "timestamp": "2026-08-11",
        "dataset_name": "OTT Recommendation System",
        "data_source": "backend/data/ott_recommendation.db",
        
        # Size metrics
        "size": {
            "total_ratings": num_ratings,
            "unique_users": num_unique_users,
            "unique_movies_in_ratings": num_unique_movies,
            "total_movies_in_catalog": num_total_movies,
            "max_possible_interactions": max_possible_interactions,
            "sparsity_percentage": round(sparsity, 2)
        },
        
        # Rating statistics
        "rating_statistics": {
            "min": float(min(ratings_list)) if ratings_list else None,
            "max": float(max(ratings_list)) if ratings_list else None,
            "mean": round(mean_rating, 4),
            "median": float(median_rating) if median_rating else None,
            "std_dev": round(std_dev, 4),
            "p25": float(percentile(ratings_sorted, 25)) if ratings_sorted else None,
            "p75": float(percentile(ratings_sorted, 75)) if ratings_sorted else None
        },
        
        # Rating distribution
        "rating_distribution": {
            "counts": rating_distribution,
            "percentages": {
                float(rating): round((count / num_ratings) * 100, 2) 
                for rating, count in rating_counts.items()
            }
        },
        
        # User activity
        "user_activity": {
            "min_ratings_per_user": min(user_activity) if user_activity else None,
            "max_ratings_per_user": max(user_activity) if user_activity else None,
            "mean_ratings_per_user": round(sum(user_activity) / len(user_activity), 2) if user_activity else None,
            "median_ratings_per_user": float(percentile(user_activity_sorted, 50)) if user_activity_sorted else None,
            "p25_ratings_per_user": float(percentile(user_activity_sorted, 25)) if user_activity_sorted else None,
            "p75_ratings_per_user": float(percentile(user_activity_sorted, 75)) if user_activity_sorted else None
        },
        
        # Movie popularity
        "movie_popularity": {
            "min_ratings_per_movie": min(movie_popularity) if movie_popularity else None,
            "max_ratings_per_movie": max(movie_popularity) if movie_popularity else None,
            "mean_ratings_per_movie": round(sum(movie_popularity) / len(movie_popularity), 2) if movie_popularity else None,
            "median_ratings_per_movie": float(percentile(movie_popularity_sorted, 50)) if movie_popularity_sorted else None,
            "p25_ratings_per_movie": float(percentile(movie_popularity_sorted, 25)) if movie_popularity_sorted else None,
            "p75_ratings_per_movie": float(percentile(movie_popularity_sorted, 75)) if movie_popularity_sorted else None
        },
        
        # Data quality
        "data_quality": {
            "missing_user_ids": missing_user_ids,
            "missing_movie_ids": missing_movie_ids,
            "missing_ratings": missing_ratings,
            "duplicate_interactions": duplicate_count,
            "invalid_movie_references": invalid_movie_refs
        },
        
        # Movie metadata
        "movie_metadata": {
            "total_movies": num_total_movies,
            "genres": dict(genre_counts),
            "year_range": {
                "min": min(m['year'] for m in movies if 'year' in m) if movies else None,
                "max": max(m['year'] for m in movies if 'year' in m) if movies else None
            }
        },
        
        # Cardinality
        "cardinality": {
            "unique_user_ids": num_unique_users,
            "unique_movie_ids": num_unique_movies,
            "unique_ratings": len(rating_counts)
        }
    }
    
    conn.close()
    return profile


def save_profile(profile: Dict[str, Any], output_dir: str = "docs") -> str:
    """
    Save profiling results to JSON.
    
    Args:
        profile: Profile dictionary
        output_dir: Output directory path
    
    Returns:
        Path to saved profile file
    """
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, "data_profile.json")
    
    with open(output_path, 'w') as f:
        json.dump(profile, f, indent=2)
    
    print(f"Saved data profile to {output_path}")
    return output_path


def generate_profile_report(profile: Dict[str, Any], output_dir: str = "docs") -> str:
    """
    Generate human-readable markdown report.
    
    Args:
        profile: Profile dictionary
        output_dir: Output directory path
    
    Returns:
        Path to saved report file
    """
    os.makedirs(output_dir, exist_ok=True)
    
    report_path = os.path.join(output_dir, "data_profile.md")
    
    with open(report_path, 'w') as f:
        f.write("# OTT Recommendation Dataset Profile\n\n")
        
        size = profile.get("size", {})
        f.write("## Dataset Size\n\n")
        f.write(f"- **Total Ratings:** {size.get('total_ratings', 'N/A')}\n")
        f.write(f"- **Unique Users:** {size.get('unique_users', 'N/A')}\n")
        f.write(f"- **Unique Movies (in ratings):** {size.get('unique_movies_in_ratings', 'N/A')}\n")
        f.write(f"- **Total Movies (in catalog):** {size.get('total_movies_in_catalog', 'N/A')}\n")
        f.write(f"- **Sparsity:** {size.get('sparsity_percentage', 'N/A')}%\n\n")
        
        ratings_stats = profile.get("rating_statistics", {})
        f.write("## Rating Statistics\n\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Min | {ratings_stats.get('min', 'N/A')} |\n")
        f.write(f"| Max | {ratings_stats.get('max', 'N/A')} |\n")
        f.write(f"| Mean | {ratings_stats.get('mean', 'N/A')} |\n")
        f.write(f"| Median | {ratings_stats.get('median', 'N/A')} |\n")
        f.write(f"| Std Dev | {ratings_stats.get('std_dev', 'N/A')} |\n\n")
        
        rating_dist = profile.get("rating_distribution", {})
        if rating_dist.get("counts"):
            f.write("## Rating Distribution\n\n")
            f.write(f"| Rating | Count | Percentage |\n")
            f.write(f"|--------|-------|------------|\n")
            percentages = rating_dist.get("percentages", {})
            for rating in sorted(rating_dist.get("counts", {}).keys()):
                count = rating_dist["counts"].get(rating, 0)
                pct = percentages.get(float(rating), 0)
                f.write(f"| {rating} | {count} | {pct}% |\n")
            f.write("\n")
        
        user_activity = profile.get("user_activity", {})
        f.write("## User Activity\n\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Min Ratings | {user_activity.get('min_ratings_per_user', 'N/A')} |\n")
        f.write(f"| Max Ratings | {user_activity.get('max_ratings_per_user', 'N/A')} |\n")
        f.write(f"| Mean Ratings | {user_activity.get('mean_ratings_per_user', 'N/A')} |\n")
        f.write(f"| Median Ratings | {user_activity.get('median_ratings_per_user', 'N/A')} |\n\n")
        
        movie_pop = profile.get("movie_popularity", {})
        f.write("## Movie Popularity\n\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Min Ratings | {movie_pop.get('min_ratings_per_movie', 'N/A')} |\n")
        f.write(f"| Max Ratings | {movie_pop.get('max_ratings_per_movie', 'N/A')} |\n")
        f.write(f"| Mean Ratings | {movie_pop.get('mean_ratings_per_movie', 'N/A')} |\n")
        f.write(f"| Median Ratings | {movie_pop.get('median_ratings_per_movie', 'N/A')} |\n\n")
        
        data_quality = profile.get("data_quality", {})
        f.write("## Data Quality\n\n")
        f.write(f"- Missing User IDs: {data_quality.get('missing_user_ids', 'N/A')}\n")
        f.write(f"- Missing Movie IDs: {data_quality.get('missing_movie_ids', 'N/A')}\n")
        f.write(f"- Missing Ratings: {data_quality.get('missing_ratings', 'N/A')}\n")
        f.write(f"- Duplicate Interactions: {data_quality.get('duplicate_interactions', 'N/A')}\n")
        f.write(f"- Invalid Movie References: {data_quality.get('invalid_movie_references', 'N/A')}\n")
    
    print(f"Saved data profile report to {report_path}")
    return report_path


if __name__ == "__main__":
    print("Generating data profile...")
    profile = profile_dataset()
    save_profile(profile)
    generate_profile_report(profile)
    print("Data profiling complete!")
