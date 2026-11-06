# Feature importance (challenger 48-feature model, 2026-11-06)

Trained after carrying jockey/trainer fields into the dataset. Model is **not** production-approved (`winner_hit_rate_at_3 ≈ 0.20`, lift vs random ≈ 0.006).

## Winner head — largest |coefficients|

| Coef | Feature |
|------|---------|
| +0.061 | trainer_starts_norm |
| -0.056 | draw_norm |
| +0.052 | days_since_last_run_norm |
| +0.050 | jockey_starts_norm |
| +0.049 | jockey_top3_rate / recent / relative |
| +0.047 | jockey_win_rate |
| +0.044 | trainer_top3_rate / recent / relative |
| -0.039 | age_norm |
| +0.036 | trainer_win_rate |
| -0.026 | field_size_norm |

## Top-3 head — largest |coefficients|

| Coef | Feature |
|------|---------|
| -0.034 | draw_norm |
| +0.025 | days_since_last_run_norm |
| +0.024 | trainer_starts_norm |
| +0.023 | trainer_top3 rates |
| -0.022 | age_norm |
| +0.020 | jockey_starts_norm |
| -0.020 | field_size_norm |
| +0.014 | jockey_top3 rates |

## Takeaways

1. **Jockey and trainer form dominate** once available — validating the dataset fix.
2. **Draw** and **rest (days since last run)** are strong; **age** has a negative coefficient (younger tends to score higher in this sample).
3. Larger fields hurt (negative `field_size_norm`) — supports stricter max field size in selection.
4. Horse-only history rates matter less than person form in this fit.

## Selection defaults tightened accordingly

`selection_filters.decide_live_play` now defaults to:

- min_top_prob 0.20
- min_separation 0.05
- min_history_coverage 0.40
- min_mean_history_starts 2.0
- **min_jockey_coverage 0.25** (new)
- max_field_size **14**
- edge_vs_uniform 0.04

## Files

- `data/model/v3_models_challenger_48f.json` — challenger artifact (do not promote until gates pass)
- Production remains `data/model/v3_models.json` (36-feature, previously approved on richer historical backtest)
