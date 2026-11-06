# Profitability-oriented improvements (non-breaking)

These changes stay inside the existing architecture:

- Same challenger / promotion gates
- Same truth gates and no-leakage walk-forward design
- Same production-approved model requirement
- No new hard dependencies

## What was wrong

1. Structured programs already contain **jockey, trainer, gains, performance, weight/draw (when present)**.
2. `build_dataset.py` dropped those fields, so the clean training set had **zero** jockey/trainer/weight/draw values.
3. Features and historical profiles therefore could not use the strongest available signals.
4. Live selection was not aggressive enough about rejecting thin-evidence races.

With only ~455 races / ~7k horse-rows, every useful pre-race signal matters.

## Files changed

| Path | Change |
|---|---|
| `src/dataset/build_dataset.py` | Carry jockey, trainer, weight, draw, age, sex, gains, performance into training rows |
| `src/model/historical_profile.py` | Walk-forward jockey and trainer form |
| `src/model/v3_features.py` | Richer feature set including jockey/trainer rates and relatives |
| `src/model/selection_filters.py` | Strict live play filters (prefer NO_BET when evidence is thin) |

## Required rebuild sequence

```bash
# 1. Rebuild dataset so jockey/trainer/weight/draw flow into training rows
python -m src.dataset.build_dataset

# 2. Re-validate and produce training_dataset_clean.json
python -m src.dataset.dataset_validator

# 3. Train a new challenger (old models are incompatible with the longer feature vector)
python -m src.model.train_model

# 4. Run existing backtests + promotion gates
python -m src.model.backtest
python -m src.model.order_backtest
python -m src.model.promote_model <candidate_version>
```

Or run the full learning cycle:

```bash
python -m src.main --mode full
```

## Optional: wire stricter live selection

In `src/model/predict_v3.py`, after ranking horses:

```python
from src.model.selection_filters import decide_live_play

play = decide_live_play(
    ranked=ranked,
    profiled_rows=current_profile,
    runners_count=int((_meta(program)["runners_count"] or 0)),
)
# Use play["decision"], play["recommended_numbers"], play["gate_reasons"]
# alongside the existing autopilot_guard.
```

## Compatibility notes

- Old models trained on the previous shorter feature vector are incompatible with the new `FEATURE_NAMES` length. Force a new challenger train + promotion cycle.
- Press ranks/odds remain excluded from production features (policy unchanged).
- If a program lacks jockey/trainer, those rates stay at zero (neutral).

## Honest expectation

Better ranking from jockey/trainer form and fewer low-information plays. Still no guarantee of profit. Confirm via walk-forward and the profitability report before relying on live bets.
