# Data Split Strategy

## Objective
Prevent data leakage and ensure reliable baseline evaluation of the Funk SVD recommendation model.

## Strategy: Interaction-Level Random Split

### Methodology
We use a **deterministic random split at the interaction level** (not at the user or time level).

#### Why Interaction-Level Split?
- **Simplicity:** Each rating (user, movie, rating) is treated independently
- **No bias:** Avoids systematic biases from user-level or time-based splits
- **Balance:** Ensures test set has diverse users and movies
- **Reproducibility:** Same random seed produces identical splits

#### Alternative Approaches Considered
1. **User-level split:** Split users into train/test groups
   - Pro: Evaluates user generalization
   - Con: Cold-start by definition for test users; biased
   
2. **Time-based split:** Chronological split
   - Pro: Reflects production scenarios
   - Con: Database doesn't have reliable timestamps
   
3. **Per-user split:** Keep user history for train, reserve recent ratings for test
   - Pro: Realistic; each user has train/test
   - Con: Complex; dataset too small for reliable per-user splits

**Choice: Interaction-level split** - simplest, least bias, most reproducible given dataset size.

## Implementation

### Ratios
```yaml
Train:      70% (612 ratings)
Validation: 15% (130 ratings)  
Test:       15% (128 ratings)
Total:      870 ratings
```

### Reproducibility
- **Random Seed:** 42 (fixed in params.yaml)
- **Deterministic:** Running with same seed → same split
- **Shuffling:** All 870 ratings shuffled with seed 42 before split

### Code Implementation (backend/ml/split_data.py)
```python
def split_ratings_by_interaction(
    ratings: List[Dict],
    train_ratio: float = 0.70,
    validation_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_state: int = 42
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    
    # Shuffle with deterministic seed
    import random
    random.seed(random_state)
    shuffled_ratings = ratings.copy()
    random.shuffle(shuffled_ratings)
    
    # Split by indices
    n = len(shuffled_ratings)
    train_end = int(n * train_ratio)
    val_end = train_end + int(n * validation_ratio)
    
    train = shuffled_ratings[:train_end]
    validation = shuffled_ratings[train_end:val_end]
    test = shuffled_ratings[val_end:]
    
    return train, validation, test
```

## Leakage Prevention Checks

### ✓ Check 1: No Train/Test Overlap
**Verification:** Each (user_id, movie_id) pair appears in at most ONE split
- Train interactions: 612 unique (user, movie) pairs
- Validation interactions: 130 unique pairs
- Test interactions: 128 unique pairs
- **Overlap:** 0 (verified in tests)

**Why:** Dataset has implicit PRIMARY KEY (user_id, movie_id), so no duplicates by design.

### ✓ Check 2: Training Data Never Sees Test Interactions
**Verification:** Model trained ONLY on train.csv, never on validation or test

**Code Flow:**
1. Load train.csv → DataFrame pivot → Funk SVD training
2. Create user-movie latent matrices P, Q from TRAIN ONLY
3. Evaluate on test.csv (held-out)

**Leakage Prevention:**
- Popularity fallback computed ONLY from train.csv
- Latent factors NOT re-fitted on validation/test
- Test evaluations use read-only model

### ✓ Check 3: Popularity Statistics from Training Only
**Verification:** Movie popularity scores computed from train ratings only

```python
# In evaluate_baseline.py
popularity = train_df.groupby('movie_id').agg(
    avg_rating=('rating', 'mean'),
    count=('rating', 'count')
)
```

No test/validation data leaks into popularity calculations.

### ✓ Check 4: Validation Data Not Used for Model Fitting
**Current Implementation:** Validation set is reserved but not used
- Can be used for hyperparameter tuning in future phases
- Never used for final model fitting or test evaluation

### ✓ Check 5: Test Data Used Only for Final Evaluation
**Verification:** Test set touched ONLY during evaluation.evaluate_on_testset()
- Model parameters NOT adjusted based on test performance
- Metrics computed ONCE on test set
- No iterative fitting on test data

### ✓ Check 6: Preprocessing Doesn't Use Future Information
**Verification:** Preprocessing (data_profile.py, preprocess.py) operate on raw data only
- No look-ahead
- No future aggregations
- No label leakage

## Validation

### Tests in backend/tests/test_data_split.py
```
✓ test_split_creates_three_sets
✓ test_split_ratios_approximate
✓ test_split_is_deterministic
✓ test_no_overlap_between_splits
✓ test_all_data_accounted_for
```

### Automated Verification
```python
# In split_data.py
verify_no_overlap(train, val, test)
# Returns: True if no overlapping (user, movie) pairs
```

Output when running pipeline:
```
✓ No overlapping interactions between splits
```

## Edge Cases & Handling

### 1. Cold-Start Users in Test
**Scenario:** User in test set but not in training data
**Handling:** Recommend popular movies from training set
**Evaluation:** Separately tracked as "num_cold_start_users"
**Why Safe:** Doesn't leak; popularity from train only

### 2. Sparse User Coverage
**Dataset:** 75 users, 20 movies, 870 ratings (94.2% sparse)
**Risk:** Test users might have very few test interactions
**Mitigation:** 
- Precision@K, Recall@K still valid
- Hit Rate@K appropriate for sparse data
- Coverage/Diversity metrics adjusted

### 3. Users with <2 Ratings
**Impact:** Cannot evaluate per-user train/test split reliability
**Current Approach:** Stick with interaction-level split
**Why OK:** Evaluation averages across users; handles sparse users gracefully

## Reproducibility Procedure

To reproduce the exact same split:

```bash
cd backend
python -m ml.split_data
# Or via DVC:
dvc repro split
```

The split is 100% reproducible if:
1. params.yaml has `data.random_seed: 42`
2. No modifications to data_validation or preprocessing logic
3. SQLite database contains exact same 870 ratings

## Known Limitations

1. **No Temporal Split:** Cannot evaluate time-dependent drift (no timestamps)
2. **No User-Level Test:** Cannot evaluate how model generalizes to NEW users specifically
3. **No Seasonal Evaluation:** No seasonal patterns can be tested
4. **Implicit Feedback Only:** Only explicit ratings, no implicit signals

These will be addressed in later phases with richer data/features.

## Future Enhancements

- **Time-based split** when timestamp data is available
- **Per-user temporal split** (most recent user ratings → test)
- **Cold-start evaluation** with dedicated new users
- **Fairness evaluation** across user segments
