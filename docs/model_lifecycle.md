# Model Lifecycle, Monitoring and Retraining (Part 2)

## 1. Problem framing

- **Regression:** predict AQI at **T+24h (±2h, UTC)** per grid cell
  (`next_aqi`), with the matched `target_timestamp` stored per row.
- **Classification:** predict the CPCB category of that AQI value
  (`next_category`: Good / Satisfactory / Moderate / Poor / Very Poor / Severe).
- **Grain:** one row per `(station_id, timestamp)` in `data/gold/aqi_data.csv`
  (floored to the hour, UTC). Rows whose +24h±2h window contains no
  observation for the same station are **dropped and counted** — never
  silently replaced by the next available row.
- **Location:** raw `station_id` and exact coordinates are NOT features.
  Each station maps to a generalised cell `lat_gen/lon_gen =
  round(coords, 1)` (~11 km; every cell holds ≥2 of the 10 Bengaluru stations).

## 2. Pipeline

```text
data/gold/aqi_data.csv (1624 valid hourly rows, 2016-2025, UTC)
        |  src/features/build_features.py (24h target, gap-aware lags/rolling, calendar)
        v
data/gold/ml_features.csv (609 rows) + ml_feature_metadata.json
        |  src/models/train.py (chronological 70/15/15 split, MLflow)
        v
models/best_regressor.joblib + models/best_classifier.joblib
models/model_metadata.json + MLflow registry (aqi_regressor v2, aqi_classifier v2)
        |  api/main.py (FastAPI) / dashboard/app.py (Streamlit, prefers FastAPI)
        v
predictions → src/monitoring/monitor.py → logs/monitoring_report.json
```

Feature/drop audit (current run): gold=1624, no-target=809 (sparse +24h
window), dropped-incomplete=1015 total incl. stale lags/rolling, final=609.
Next-24h mix: Good 221 / Moderate 170 / Satisfactory 136 / Poor 43 /
Very Poor 33 / Severe 6.

## 3. Models compared (verified run, 2026-10-14)

Split: train 426 (2016-03 → 2018-03), val 91 (2018-03 → 2018-04),
test 92 (2018-04 → 2021-09). Selection on **validation** only.

| Task | Models | Selection metric (val) | Winner (val) | Held-out test |
|------|--------|------------------------|--------------|---------------|
| Regression | DummyMean, LinearRegression (scaled pipe), RandomForest-200 | RMSE | RandomForest (47.5; Linear 47.8; Dummy 114.0) | Linear RMSE 21.1 / RF 25.6 / Dummy 61.1; R² negative (regime shift) |
| Classification | DummyMostFreq, LogisticRegression (scaled, balanced), RandomForest (balanced) | F1-macro | LogisticRegression (0.72; RF 0.71; Dummy ~0.00) | Dummy 0.44 / RF 0.42 / LR 0.29 — test holds only Good (73) + Satisfactory (19) |

Honest reading: the val window (Mar–Apr 2018) contains pollution episodes
while the test window is mostly clean, so val-selected models degrade on
test — the dataset (609 sparse rows, 6 Severe) is too small for stable
temporal generalisation. Confusion matrices per run are logged to MLflow
(`confusion_matrix_test.json`) and stored in `models/model_metadata.json`.
Recommended next data: continuous CPCB hourly history for Bengaluru (or
12+ months of scheduled OpenAQ pulls) so the +24h target has ≥5k samples.

## 4. Experiment tracking and registry

- Tracking: `sqlite:///mlflow.db`, experiment `aqi_prediction`.
- Runs: `reg_*` / `clf_*` log params, val+test metrics, `split_info.json`;
  classification runs also log the test confusion matrix. Best runs
  register `aqi_regressor` / `aqi_classifier` (verified **version 2, READY**).
- Inspect: `mlflow ui --backend-store-uri sqlite:///mlflow.db` → Experiments
  (`aqi_prediction`), Models → `aqi_regressor`, `aqi_classifier` → version 2.
- Local artifacts: `models/*.joblib` + `models/model_metadata.json`
  (feature schema, target, split periods, per-station test counts, versions).
- Registry failures are caught and recorded in metadata (`model_versions.*.error`)
  instead of falsely claiming success.

## 5. Deployment

- `api/main.py` (schema = `src/features/build_features.py:FEATURE_COLUMNS`,
  single source of truth): `GET /health` (503 when artifacts missing),
  `GET /model-info` (target, versions, schema, split), `POST /predict`
  (422 on invalid/missing, 500 on implausible output; response carries
  `horizon: +24h` and model names).
- `Dockerfile` (+ `.dockerignore`, `HEALTHCHECK /health`): prerequisite —
  `python3 src/models/train.py` first since `models/` is git-ignored
  (placeholder `models/.gitkeep` keeps `COPY` working on fresh clones):
  `docker build -t aqi-api . && docker run -p 8000:8000 aqi-api`.
  Docker build/run **not executed** here (daemon unavailable) — reported,
  not claimed.
- Streamlit (`dashboard/app.py`, "AQI Prediction — 24h ahead") prefers
  `POST localhost:8000/predict`, falls back to local joblib, and labels
  horizon, grid cell, model versions, and limitations distinctly from
  historical values.

## 6. Monitoring (`src/monitoring/monitor.py`)

| Check | Signal | Alert threshold |
|-------|--------|-----------------|
| Missing data | NaN rate over feature columns (+missing-column guard) | > 5% |
| Feature drift | relative mean shift, recent 20% vs first 70% (floored denominator, zero-safe) | > 30% |
| Recent-holdout proxy | RMSE / F1-macro on most recent 92 rows — **historical holdout, not live** | RMSE > 40, F1 < 0.50 |
| Coverage | row/station counts | < 10 rows |
| Inference health | sample prediction latency / failures | > 500 ms or any failure |

Current report: location drift negligible (`lat_gen` 0.005, `lon_gen`
0.001 — generalisation works; old `station_id` feature drifted 0.80),
AQI-level drift ~0.5 reflects the genuine 2016-18→2018-21 regime shift;
holdout proxy RMSE 25.6 ok / F1 0.29 alerts → **retraining recommended**
flag is set (see §7 — flag only, no auto-retrain).

## 7. Retraining criteria

Retrain (`python3 src/models/train.py`) when ANY hold; retraining is
manual (no automatic workflow) and append-only (new MLflow run + new
registry version; previous version retained for rollback; promote only
if validation RMSE/F1 beats production):

1. `recent_rmse > 40` or `recent_f1_macro < 0.50` on the holdout proxy.
2. Non-identifier feature drift > 30% sustained over two consecutive checks.
3. New gold data grows by ≥ 20% or a new station/city is added.
4. Monthly scheduled refresh (aligns with the Airflow `@daily` ETL).

## 8. Known limitations

- Sparse history: 1641 gold rows over 2016–2025 with multi-month gaps
  (median gap 1–2h, max up to ~60kh); only 609 rows support a true +24h
  target — too few for robust claims.
- Weather unavailable: Open-Meteo 2026 window does not overlap OpenAQ
  history, so no valid prediction-time weather join exists; features are
  AQI-history + calendar + generalised location only.
- Severe/Very Poor rare (6/33 of 609); recall on extremes is limited
  (`class_weight="balanced"` mitigates).
- Test regime differs from train/val (clean vs polluted) — expect
  degraded held-out metrics until continuous recent data accumulates.
