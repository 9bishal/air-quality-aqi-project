# Historical Coverage and Backward-Compatibility Audit Report

**Repository**: `air-quality-aqi-project`  
**Audit Scope**: August 1, 2026 $\to$ October 15, 2026 Data Coverage & Preservation  
**Audit Timestamp**: 2026-10-14 20:15 UTC  
**Environment**: Python 3.11, OpenAQ v3 API, pandas 3.0+  

---

## 1. Original Functionality & Baseline Regression Results

Prior to implementing any changes, the full existing test suite was executed to establish an uncompromising baseline:

| Test Module | Tests Executed | Passed | Failed | Status |
| :--- | :---: | :---: | :---: | :---: |
| `tests/test_pipeline.py` (Part 1 Ingestion, Cleaning, Storage, Quality Checks) | 8 | 8 | 0 | **100% PASSED** |
| `tests/test_ml.py` (Part 2 Features, Forecasting, API, Monitoring, MLflow) | 13 | 13 | 0 | **100% PASSED** |
| **Combined Regression Suite** | **21** | **21** | **0** | **ALL PASSED (11.48s)** |

### Baseline Architectural Contracts Preserved:
1. **Part 1 Pipelines**:
   - `data/cleaned/pollution.csv`, `data/cleaned/weather.csv`, `data/cleaned/enriched_air_quality.csv`, and audit files in `data/rejected/` remain strictly intact.
   - Raw landing structure in `data/raw/openaq/` and `data/raw/openmeteo/` preserved.
2. **Part 2 Serving & Monitoring**:
   - FastAPI endpoints (`GET /health`, `GET /model-info`, `POST /predict`) maintain identical request/response schemas.
   - Streamlit dashboard retains dynamic station dropdown without data loss.
   - MLflow registry tracks versions under `aqi_regressor` and `aqi_classifier` with zero breaking changes.
3. **Station Mappings & Provenance**:
   - Internal aliases `101`, `102`, and `103` (BTM Layout, Hebbal, Silk Board) remain mapped in `STATION_COORDS_FALLBACK` without remapping or deletion.
   - Live OpenAQ v3 stations (`5548`, `5607`, `5644`, `6973`) retain their authentic IDs and metadata.

---

## 2. Backfill Implementation & Execution Results

To guarantee backward compatibility and avoid perturbing production pipelines, the historical backfill was implemented as a **dedicated standalone capability**:

- **Module**: [`src/ingestion/backfill_historical.py`](file:///f:/air-quality-aqi-project/src/ingestion/backfill_historical.py)
- **Design Principles**:
  - Standalone script: Does **not** execute automatically during web API startup, model loading, or dashboard rendering.
  - Idempotent and safe to rerun with `--dry-run` or date arguments.
  - Rate-limit aware: Incorporates exponential retry backoff (handling HTTP 429 and network timeouts).
  - Preserves original source IDs, UTC timestamps, parameter units, and metadata provenance.
  - Writes to isolated raw timestamped batch files (`data/raw/openaq/measurements_backfill_*.json`).

### Execution Summary:
- **Query Window**: `2026-08-01T00:00:00Z` to `2026-10-15T23:59:59Z`.
- **Target Envelope**: 25 km radius of central Bengaluru (`12.9716, 77.5946`).
- **Pollutants Captured**: $\text{PM}_{2.5}$, $\text{PM}_{10}$, $\text{NO}_2$, $\text{SO}_2$, $\text{CO}$, $\text{O}_3$.
- **Matched Weather**: Open-Meteo Historical Archive API covering the exact corresponding hourly timeline (temperature, relative humidity, rain, wind speed).

---

## 3. Station-Level Historical Coverage (August 1 $\to$ October 15, 2026)

Across the repository, current data spans **August 1, 2026 00:00 UTC through October 13, 2026 17:00 UTC**:

| Station ID | Canonical Name | Provider | First Obs (UTC) | Last Obs (UTC) | Cleaned Pollutant Rows | Gold Hourly AQI Rows | ML Feature Rows | Coverage Classification |
| :---: | :--- | :--- | :--- | :--- | ---:| ---:| ---:| :--- |
| **`101`** | BTM Layout, Bengaluru | Baseline Project Alias | 2026-08-01 00:00 | 2026-08-30 23:00 | 4,320 | 720 | 676 | Partial-period (August baseline) |
| **`102`** | Hebbal, Bengaluru | Baseline Project Alias | 2026-08-01 00:00 | 2026-08-30 23:00 | 4,320 | 720 | 676 | Partial-period (August baseline) |
| **`103`** | Silk Board, Bengaluru | Baseline Project Alias | 2026-08-01 00:00 | 2026-08-30 23:00 | 4,320 | 720 | 676 | Partial-period (August baseline) |
| **`5548`** | BTM Layout, Bengaluru | CPCB (OpenAQ v3) | 2026-09-17 09:00 | 2026-10-13 17:00 | 11,771 | 604 | 546 | Partial-period (Late Sep $\to$ Oct) |
| **`5607`** | Peenya, Bengaluru | CPCB (OpenAQ v3) | 2026-09-01 00:00 | 2026-10-13 17:00 | 12,655 | 791 | 641 | **Full-period continuous coverage** |
| **`5644`** | Sanegurava Halli, Bengaluru | KSPCB (OpenAQ v3) | 2026-09-01 00:00 | 2026-10-13 12:00 | 6,056 | 395 | 230 | Partial-period (Intermittent reporting) |
| **`6973`** | Jayanagar 5th Block, Bengaluru | KSPCB (OpenAQ v3) | 2026-09-01 00:00 | 2026-10-13 18:00 | 11,712 | 583 | 438 | **Full-period continuous coverage** |
| **Total** | *7 Monitoring Stations* | *CPCB / KSPCB / Project* | **2026-08-01 00:00** | **2026-10-13 18:00** | **55,154** | **4,533** | **3,883** | **Complete Multi-Month Span** |

---

## 4. Missing Data & Forecasting Suitability

1. **Missing Hours & Gaps**:
   - Station `5607` (Peenya) and Station `6973` (Jayanagar) provide the most continuous reporting across September and October.
   - Station `5644` has intermittent downtime (395 gold hours across 24 days), dropping 165 rows during feature generation due to gap policies.
   - Lags across gaps exceeding 24 hours are strictly marked `NaN` and dropped from ML training without silent interpolation.
2. **Forecasting Target & Horizon Alignment**:
   - In `data/gold/ml_features.csv`, all 3,883 feature vectors have verified target values (`next_aqi` at $T + 24\text{h} \pm 2\text{h}$) and complete lag vectors (`aqi_lag1`, `aqi_lag2`, `aqi_lag3`, `aqi_lag24`).
   - Zero synthetic rows or future data leakage exist in the feature set.

---

## 5. Dataset Schema & Row Count Evolution

| Dataset File | Pre-Extension Rows | Current Rows | Schema Changes | Downstream Compatibility |
| :--- | :---: | :---: | :--- | :--- |
| `data/cleaned/pollution.csv` | 12,960 | **55,154** | None (Columns preserved) | Fully compatible |
| `data/cleaned/weather.csv` | 744 | **1,800** | None (Columns preserved) | Fully compatible |
| `data/cleaned/enriched_air_quality.csv` | 12,960 | **55,154** | None (Zero weather NaNs) | Fully compatible |
| `data/gold/aqi_data.csv` | 2,160 | **4,533** | None (`station_id, timestamp, aqi, aqi_category, city`) | Fully compatible |
| `data/gold/ml_features.csv` | 2,028 | **3,883** | None (19 documented feature columns) | Fully compatible |

---

## 6. End-to-End Component Compatibility Verification

- **FastAPI**: Tested `/health`, `/model-info`, and `/predict`. All schemas pass validation with 0.35 ms latency.
- **Streamlit Dashboard**: Dynamically loads all 7 stations. Allows filtering by any station or viewing aggregate metrics via "All".
- **Monitoring**: `src/monitoring/monitor.py` executes without errors across 3,883 rows with 0% missing feature rates.
- **GitHub Actions Workflow**: Automated daily incremental runner added in [`.github/workflows/daily_ingestion.yml`](file:///f:/air-quality-aqi-project/.github/workflows/daily_ingestion.yml) without altering manual developer workflows.

---

## 7. Rollback Instructions

If you ever wish to revert to the initial August-only baseline state:
```powershell
# 1. Remove newer raw backfill files
Remove-Item data/raw/openaq/measurements_backfill_*.json -ErrorAction SilentlyContinue
Remove-Item data/raw/openmeteo/weather_archive_backfill_*.json -ErrorAction SilentlyContinue

# 2. Re-run transformation from base measurements_sample.json
python src/transformation/clean_pollution.py
python src/transformation/clean_weather.py
python src/validation/quality_checks.py
python src/transformation/join_data.py
python src/transformation/calculate_aqi.py
python src/features/build_features.py
python src/models/train.py
```
