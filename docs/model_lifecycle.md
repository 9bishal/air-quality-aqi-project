# Model Lifecycle, Monitoring and Retraining (Part 2)

## 1. Problem framing

- **Regression:** predict the next observation's AQI (`next_aqi`) per station.
- **Classification:** predict the next observation's AQI category
  (`next_category`: Good / Satisfactory / Moderate / Poor / Very Poor / Severe).
- **Grain:** one row per `(station_id, timestamp)` in `data/gold/aqi_data.csv`.
  The target is the next row for the same station (`shift(-1)`). This is the
  closest available proxy for "next-day AQI": the historic OpenAQ record is
  sparse (1,641 hourly rows over 2016–2025 with multi-month gaps), so strict
  calendar-day lags would be almost entirely empty.

## 2. Pipeline

```text
data/gold/aqi_data.csv
        |  src/features/build_features.py (lag 1/2/3, rolling 3/7, calendar)
        v
data/gold/ml_features.csv (1,584 rows) + ml_feature_metadata.json
        |  src/models/train.py (chronological 70/15/15 split, MLflow)
        v
models/best_regressor.joblib + models/best_classifier.joblib
models/model_metadata.json + MLflow registry (aqi_regressor, aqi_classifier)
        |  api/main.py (FastAPI) / dashboard/app.py (Streamlit)
        v
predictions → src/monitoring/monitor.py → logs/monitoring_report.json
```

## 3. Models compared

| Task | Models | Selection metric (validation) | Winner |
|------|--------|-------------------------------|--------|
| Regression | DummyMean, LinearRegression, RandomForest (200 trees) | RMSE | LinearRegression (val RMSE 32.5) |
| Classification | DummyMostFrequent, LogisticRegression, RandomForest (balanced) | F1-macro | RandomForest (val F1-macro 0.63) |

Validation is chronological (train ≤ 2018, val/test later), so metrics reflect
forward-in-time generalization. Note the val/test shift: RandomForest regresses
better on the test window (RMSE 12.9 vs 17.8) — recorded in MLflow for review.

## 4. Experiment tracking and registry

- Tracking backend: `sqlite:///mlflow.db`, experiment `aqi_prediction`.
- Each model logs params, val/test RMSE–MAE–R² or precision–recall–F1, and the
  sklearn artifact. Best models are also registered as `aqi_regressor` and
  `aqi_classifier` (versioned).
- Local artifacts: `models/*.joblib` + `models/model_metadata.json`.

## 5. Deployment

- `api/main.py`: `GET /health`, `GET /model-info`, `POST /predict`.
- `Dockerfile`: `docker build -t aqi-api . && docker run -p 8000:8000 aqi-api`.
- Streamlit dashboard (`dashboard/app.py`, "AQI Prediction" section) loads the
  same joblib artifacts for interactive forecasting.

## 6. Monitoring (`src/monitoring/monitor.py`)

| Check | Signal | Alert threshold |
|-------|--------|-----------------|
| Missing data | NaN rate over feature columns | > 5% |
| Feature drift | max relative mean shift, recent 20% vs first 70% | > 30% |
| Forecasting error | RMSE / F1-macro on most recent 239 rows | RMSE > 40, F1 < 0.50 |
| Inference health | sample prediction latency / failures | > 500 ms or any failure |

Current baseline: drift alert fires on `station_id` (0.80) because the station
mix changes over the years (early stations 412/594 vs later 5607/5574) — this
is a known data property, not necessarily model decay. AQI-level drift is small
(< 9% on lag/rolling means).

## 7. Retraining criteria

Retrain (`python3 src/models/train.py`) when ANY of these hold:

1. `recent_rmse > 40` or `recent_f1_macro < 0.50` on the rolling recent window.
2. Non-identifier feature drift > 30% sustained over two consecutive checks.
3. New gold data grows by ≥ 20% or a new station/city is added.
4. Monthly scheduled refresh (aligns with the Airflow `@daily` ETL).

Retraining is append-only: new MLflow run + new registry version; the previous
version is retained for rollback. Promote a new version only if its validation
RMSE/F1 beats the production version.

## 8. Known limitations

- Weather features are unavailable: the Open-Meteo fetch window (2026) does
  not overlap the historic OpenAQ window, so `temperature/humidity/...` are
  NaN after the join. The model uses AQI history + calendar features only.
  Once overlapping live data accumulates, add weather lags to the feature
  pipeline.
- Severe/Very Poor classes are rare (11/54 of 1,584 rows); classification
  recall on extremes is limited. `class_weight="balanced"` mitigates this.
- Targets are next-observation, not strict next-calendar-day, due to gaps.
