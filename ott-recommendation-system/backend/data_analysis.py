import sqlite3
import pandas as pd
import numpy as np
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ott_recommendation.db")

def run_analysis():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}. Please run the project at least once to seed the database.")
        return

    conn = sqlite3.connect(DB_PATH)
    
    print("--- OTT Dataset Summary & Parameters ---")
    
    # 1. General Stats
    df_movies = pd.read_sql_query("SELECT * FROM movies", conn)
    df_ratings = pd.read_sql_query("SELECT * FROM ratings", conn)
    df_inference = pd.read_sql_query("SELECT * FROM inference_logs", conn)
    df_retrain = pd.read_sql_query("SELECT * FROM retraining_history", conn)
    
    num_users = df_ratings['user_id'].nunique()
    num_movies = df_movies['id'].nunique()
    num_ratings = len(df_ratings)
    sparsity = (1 - (num_ratings / (num_users * num_movies))) * 100
    
    print(f"Unique Users: {num_users}")
    print(f"Unique Movies: {num_movies}")
    print(f"Total Ratings Logged: {num_ratings}")
    print(f"User-Item Interaction Matrix Sparsity: {sparsity:.2f}%")
    print(f"Average Rating in System: {df_ratings['rating'].mean():.2f} / 5.0")
    print()
    
    # 2. Rating Distribution Analysis
    print("--- Rating Value Frequency Distribution ---")
    rating_counts = df_ratings['rating'].value_counts().sort_index()
    for val, count in rating_counts.items():
        pct = (count / num_ratings) * 100
        bar = "#" * int(pct // 3)
        print(f" {val} stars: {count:3d} ({pct:5.1f}%) {bar}")

    print()
    
    # 3. Genre Popularity and Performance Analysis
    print("--- Genre Distribution & Average Ratings ---")
    df_merged = pd.merge(df_ratings, df_movies, left_on='movie_id', right_on='id')
    genre_stats = df_merged.groupby('genre').agg(
        total_interactions=('rating', 'count'),
        avg_rating=('rating_x', 'mean')
    ).reset_index()
    
    for _, row in genre_stats.iterrows():
        print(f" Genre: {row['genre']:10s} | Interactions: {row['total_interactions']:3d} | Avg User Rating: {row['avg_rating']:.2f}")
    print()
    
    # 4. Model Telemetry & Pipeline Parameters
    print("--- MLOps Telemetry & Retraining Parameters ---")
    if not df_inference.empty:
        print(f"Total Inference Requests Logged: {len(df_inference)}")
        print(f"Mean Latency: {df_inference['latency_ms'].mean():.2f} ms")
        print(f"P95 Latency: {df_inference['latency_ms'].quantile(0.95):.2f} ms")
    else:
        print("No inferences logged yet.")
        
    if not df_retrain.empty:
        print(f"Total Retraining Runs: {len(df_retrain)}")
        print(f"Last Active Model Version: {df_retrain.iloc[-1]['model_version']}")
        print(f"Last Training MSE: {df_retrain.iloc[-1]['mse']:.5f}")
    else:
        print("No retraining runs logged yet.")
    
    conn.close()

if __name__ == "__main__":
    run_analysis()
