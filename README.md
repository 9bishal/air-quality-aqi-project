# Air Quality Index Analysis and Prediction (DE & MLOps Pipeline)

A complete end-to-end Data Engineering (Part 1) and MLOps (Part 2) solution for air quality analysis and 24-hour ahead AQI forecasting in Bengaluru, India.

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Single-Command Full Pipeline Orchestration](#single-command-full-pipeline-orchestration)
3. [Architecture & Pipeline Flow](#architecture--pipeline-flow)
4. [Technology Stack](#technology-stack)
5. [Project Structure](#project-structure)
6. [Installation & Setup (Cross-Platform)](#installation--setup-cross-platform)
7. [Part 1: Data Engineering Pipeline](#part-1-data-engineering-pipeline)
8. [Part 2: MLOps Pipeline (Features, Models, Registry, API, Docker, Monitoring)](#part-2-mlops-pipeline)
9. [Run with Docker (Cross-Platform)](#run-with-docker-cross-platform)
10. [Interactive Dashboard](#interactive-dashboard)
11. [Automated Testing](#automated-testing)
12. [Model Lifecycle & Monitoring Policy](#model-lifecycle--monitoring-policy)
13. [Author & License](#author--license)

---

## Project Overview

This project provides:
- **Data Engineering (Part 1)**: Automated API ingestion from OpenAQ (air quality) and Open-Meteo (meteorological parameters), data quality validation with rejected record logging, multi-layer transformations (raw → staging → cleaned → gold), PostgreSQL loading, and daily orchestration via Apache Airflow.
- **MLOps Extension (Part 2)**: Reusable feature pipeline with strictly gap-aware lags, non-leaking rolling statistics, and generalized spatial grid features; chronological train/val/test evaluation comparing regression and classification models against naive baselines; experiment tracking and model registration via SQLite-backed MLflow; containerized REST inference via FastAPI and Docker; distribution drift and error monitoring; and interactive 24h forecasting in Streamlit.
- **Master Pipeline Orchestration (`run_full_pipeline.py`)**: A single unified command executing incremental ingestion, cleaning, AQI calculation, ML feature engineering, model training, MLflow logging, and automated test suite verification in one command.

---

## Single-Command Full Pipeline Orchestration

To run the complete end-to-end pipeline from data ingestion to model training and verification with a single command:

```bash
python run_full_pipeline.py
```

### Supported CLI Options:

| Command | Action |
|---|---|
| `python run_full_pipeline.py` | **Default**: Incremental ingestion through current time, end-to-end preprocessing, AQI calculation, ML feature engineering, model retraining, MLflow logging, and automated testing. |
| `python run_full_pipeline.py --dry-run` | **Dry Run**: Inspects the planned ingestion window, target stations, and execution order without writing data or training models. |
| `python run_full_pipeline.py --start 2026-09-01 --end 2026-10-14` | **Historical Backfill**: Fetches a specific historical date range and runs downstream stages. |
| `python run_full_pipeline.py --skip-ingestion` | **Local Pipeline Rebuild**: Skips network API ingestion; re-cleans and trains on existing raw data. |
| `python run_full_pipeline.py --skip-training` | **Data & Feature Sync**: Ingests new data and rebuilds cleaned, gold, and ML feature datasets without retraining models. |

### Key Guarantees:
- **Idempotent Checkpointing**: State is maintained in `logs/ingestion_checkpoint.json` with a 2-hour lookback buffer for delayed observations. Checkpoints are updated only after raw data is successfully written to disk.
- **Fail-Fast Safety**: Downstream execution (including feature building and model promotion) immediately halts if any upstream stage fails.
- **Full Backward Compatibility**: Part 1 and Part 2 entry points, database schemas, and FastAPI contracts remain completely intact. Detailed report available in [`reports/full_pipeline_orchestration.md`](file:///f:/air-quality-aqi-project/reports/full_pipeline_orchestration.md).

---

## Architecture & Pipeline Flow

```text
[OpenAQ API] (Air Quality)      [Open-Meteo API] (Weather: Temp, Humidity, Wind)
           \                          /
            \                        /
             v                      v
           Ingestion Layer: data/raw/
                      |
                      v
          Staging Layer: data/staging/
                      |
                      v
      Validation & Data Quality Checks (quality_checks.py)
         /                            \
        v                              v
[data/rejected/]                 [data/cleaned/] (Cleaned & Enriched)
                                       |
                                       v
                                PostgreSQL DB
                                       |
                                       v
                             Gold Layer (calculate_aqi.py)
                                [data/gold/aqi_data.csv]
                                       |
       +-------------------------------+-------------------------------+
       |                                                               |
       v                                                               v
[Part 1: Analytical Layer]                                  [Part 2: MLOps Pipeline]
  - Streamlit BI Views                                        - Feature Pipeline (build_features.py)
  - Daily Patterns & Pollution Breakdown                      - Chronological MLflow Train (train.py)
  - Station Comparison & Weather Impact                       - FastAPI REST Service (api/main.py)
                                                              - Docker Container (aqi-api)
                                                              - Drift & Error Monitor (monitor.py)
                                                              - Streamlit 24h Predictor Tab
```

---

## Technology Stack

- **Data Processing**: Python 3.10+, Pandas, NumPy
- **Orchestration**: Apache Airflow (`@daily` DAG: `aqi_pipeline`)
- **Database & Storage**: PostgreSQL, SQLAlchemy, JSON, CSV
- **Machine Learning**: Scikit-Learn, Joblib
- **Experiment Tracking & Registry**: MLflow (SQLite backend `sqlite:///mlflow.db`)
- **Inference Service**: FastAPI, Uvicorn, Pydantic v2
- **Containerization**: Docker, Docker Compose
- **Monitoring**: Custom statistical drift (relative mean shift) & holdout proxy evaluation
- **Visualization**: Streamlit, Plotly Express
- **Testing**: Pytest

---

## Project Structure

```text
air-quality-aqi-project/
├── airflow/
│   └── dags/
│       └── aqi_pipeline.py       # Airflow DAG for daily ETL automation
├── api/
│   └── main.py                   # FastAPI REST application (GET /health, GET /model-info, POST /predict)
├── dashboard/
│   └── app.py                    # Streamlit dashboard (Part 1 Analytics + Part 2 Forecasting)
├── data/
│   ├── raw/                      # Raw immutable API dumps (OpenAQ, Open-Meteo)
│   ├── staging/                  # Normalized staging tables
│   ├── cleaned/                  # Validated, deduplicated & joined data
│   ├── gold/                     # Analytical AQI data & ML features
│   └── rejected/                 # Data quality rejection logs
├── docs/
│   ├── architecture.md           # Pipeline architecture document
│   ├── data_dictionary.md        # Column definitions, units, and boundaries
│   ├── model_lifecycle.md        # Part 2 Model lifecycle, metrics & retraining rules
│   └── validation_rules.md       # Data quality constraints
├── models/                       # Git-ignored serialized models & metadata (generated by train.py)
│   ├── best_regressor.joblib
│   ├── best_classifier.joblib
│   └── model_metadata.json
├── logs/                         # Ingestion, validation, and monitoring reports
├── sql/                          # Table schemas, analytics marts, DB setup
├── src/
│   ├── database/                 # PostgreSQL connection & data loaders
│   ├── features/
│   │   └── build_features.py     # Reusable feature engineering (24h target, lags, rolling)
│   ├── ingestion/                # OpenAQ & Open-Meteo API extractors
│   ├── models/
│   │   └── train.py              # Chronological train, MLflow evaluation & model registry
│   ├── monitoring/
│   │   └── monitor.py            # Quality, drift, error, and latency monitoring
│   ├── transformation/           # Data cleaning, weather/pollution joins, AQI calculation
│   └── validation/               # Rule-based data quality checks
├── tests/
│   ├── test_pipeline.py          # Part 1 data pipeline tests
│   ├── test_ml.py                # Part 2 MLOps, features, MLflow, API, and monitoring tests
│   └── test_orchestrator.py      # Master orchestrator regression & checkpoint tests
├── Dockerfile                    # Container definition for inference service
├── docker-compose.yml            # Docker Compose orchestration
├── requirements.txt              # Project dependencies
├── run_full_pipeline.py          # Unified master pipeline orchestrator
└── README.md                     # Complete project documentation
```

---

## Installation & Setup (Cross-Platform)

### 1. Clone the Repository
```bash
git clone https://github.com/9bishal/air-quality-aqi-project.git
cd air-quality-aqi-project
```

### 2. Create and Activate Virtual Environment

#### On Linux / macOS (bash / zsh):
```bash
python3 -m venv .venv
source .venv/bin/activate
export PYTHONPATH="."
```

#### On Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="."
```

#### On Windows (Command Prompt):
```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
set PYTHONPATH=.
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the project root:
```env
# PostgreSQL Configuration (Part 1)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=air_quality_db
DB_USER=postgres
DB_PASSWORD=your_password

# OpenAQ API Key (Optional for cached data)
OPENAQ_API_KEY=your_openaq_api_key
```

---

## Quick Start — start commands

Build the Part 2 artifacts once, then start each service in its own
terminal (project root, venv activated). Windows uses `python`,
macOS/Linux uses `python3`.

```bash
# One-time build (creates data/gold/ml_features.csv + models/*.joblib)
python src/features/build_features.py
python src/models/train.py
```

```bash
# Terminal 1 — prediction API (http://localhost:8000/health)
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

```bash
# Terminal 2 — dashboard (connects to the API when it is running)
streamlit run dashboard/app.py
```

```bash
# Terminal 3 — MLflow UI (http://127.0.0.1:5000), no Docker needed
mlflow ui --backend-store-uri sqlite:///mlflow.db
# Tip: start this BEFORE training to watch runs appear live —
# the UI reads mlflow.db while training writes to it (refresh the page).
```

```bash
# Anytime checks
python src/monitoring/monitor.py   # writes logs/monitoring_report.json
python -m pytest tests/ -q         # expect: 21 passed
```

## Part 1: Data Engineering Pipeline

Execute the Part 1 data stages in sequence:

#### On Linux / macOS:
```bash
python3 src/ingestion/openaq_collector.py
python3 src/ingestion/weather_collector.py
python3 src/transformation/clean_pollution.py
python3 src/transformation/clean_weather.py
python3 src/validation/quality_checks.py
python3 src/transformation/join_data.py
python3 src/transformation/calculate_aqi.py
```

#### On Windows (PowerShell):
```powershell
python src/ingestion/openaq_collector.py
python src/ingestion/weather_collector.py
python src/transformation/clean_pollution.py
python src/transformation/clean_weather.py
python src/validation/quality_checks.py
python src/transformation/join_data.py
python src/transformation/calculate_aqi.py
```

### Running via Apache Airflow

The project includes an Apache Airflow DAG located at `airflow/dags/aqi_pipeline.py` (`dag_id="aqi_pipeline"`, scheduled `@daily`).

Each task in the DAG executes the pipeline stages sequentially (`collect` → `clean` → `quality_checks` → `join` → `calculate_aqi`).

#### Option 1: Run Airflow with Docker (Recommended for Windows / Mac / Linux)

Run Airflow and its PostgreSQL backend via Docker Compose:

1. **Start Airflow and PostgreSQL**:
   ```bash
   docker compose up -d
   ```

2. **Trigger and Test the DAG End-to-End Inside the Container**:
   ```bash
   docker exec -it aqi_airflow airflow dags test aqi_pipeline 2026-09-01
   ```

3. **Test an Individual Task Inside the Container**:
   ```bash
   docker exec -it aqi_airflow airflow tasks test aqi_pipeline collect_openaq 2026-09-01
   docker exec -it aqi_airflow airflow tasks test aqi_pipeline calculate_aqi 2026-09-01
   ```

4. **Access the Airflow Web UI**:
   - Open [http://localhost:8080](http://localhost:8080)
   - To retrieve the auto-generated standalone admin password:
     ```bash
     docker exec -it aqi_airflow cat /opt/airflow/standalone_admin_password.txt
     ```

5. **Stop Airflow Containers**:
   ```bash
   docker compose down
   ```

---

#### Option 2: Run Without Docker / Locally (Linux / macOS / WSL)
If you have Airflow installed locally:
```bash
export AIRFLOW_HOME="$(pwd)/airflow"
export PYTHONPATH="."
airflow db init
airflow dags test aqi_pipeline 2026-09-01
```

#### Option 3: Run Without Airflow on Native Windows
```powershell
python run_full_pipeline.py
```

---

## Part 2: MLOps Pipeline

Part 2 delivers an end-to-end ML lifecycle for 24-hour ahead AQI forecasting.

### 1. Feature Engineering
- **Script**: `src/features/build_features.py`
- **Contract**:
  - Target: Observation at $T+24\text{h} \pm 2\text{h}$ UTC for the same station. Missing windows are dropped (never silently forward-filled).
  - Lags: `aqi_lag1`, `aqi_lag2`, `aqi_lag3` (invalidated if timestamp gap exceeds 24h).
  - Rolling Statistics: `roll_mean_3`, `roll_std_3`, `roll_mean_7`, `roll_max_7` using `shift(1)` (strictly past data; zero future leakage).
  - Location Generalization: Stations mapped to coarse coordinates `lat_gen`, `lon_gen` (~11 km grid) to prevent label memorization.

#### Execute:
```bash
# Linux / macOS
python3 src/features/build_features.py

# Windows
python src/features/build_features.py
```
*Output*: Generates `data/gold/ml_features.csv` (2,085 rows) and `data/gold/ml_feature_metadata.json`.

---

### 2. Model Training & MLflow Registry
- **Script**: `src/models/train.py`
- **Methodology**:
  - Chronological 70% / 15% / 15% split without random shuffling.
    - **Train**: 1,459 samples (Aug 01, 2026 – Aug 21, 2026)
    - **Validation**: 312 samples (Aug 21, 2026 – Aug 25, 2026)
    - **Held-out Test**: 314 samples (Aug 25, 2026 – Aug 30, 2026)
  - Regression Models: `dummy_mean`, `linear_regression` (StandardScaler pipeline), `random_forest_regressor` (200 trees).
  - Classification Models: `dummy_most_frequent`, `logistic_regression` (balanced), `random_forest_classifier` (balanced).
  - Selection: Selected strictly on **validation** metrics, then evaluated once on the **test** set.
  - Tracking & Registry: SQLite MLflow store (`sqlite:///mlflow.db`), logging hyperparameters, validation/test metrics, confusion matrices, and registering `aqi_regressor` and `aqi_classifier` with status `READY`.

#### Execute:
```bash
# Linux / macOS
python3 src/models/train.py

# Windows
python src/models/train.py
```

#### Actual Verified Metrics:
| Task | Model | Validation Metric | Test Performance | Selection Status |
|---|---|---|---|:---:|
| **Regression** | `dummy_mean` | **RMSE: 40.78** | RMSE: 41.20, MAE: 31.18, $R^2$: -0.002 | **Selected (Winner)** |
| Regression | `linear_regression` | RMSE: 42.45 | **RMSE: 39.62, MAE: 30.09, $R^2$: 0.073** | Evaluated |
| Regression | `random_forest_regressor` | RMSE: 49.25 | RMSE: 41.70, MAE: 31.78, $R^2$: -0.026 | Evaluated |
| **Classification** | `dummy_most_frequent`| Macro-F1: 0.202 | Macro-F1: 0.197, Accuracy: 65.0% | Baseline |
| Classification | `logistic_regression` | Macro-F1: 0.094 | Macro-F1: 0.125, Accuracy: 17.5% | Evaluated |
| Classification | `random_forest_classifier` | **Macro-F1: 0.244** | **Macro-F1: 0.310, Accuracy: 60.5%** | **Selected (Winner)** |

#### Launch MLflow UI:
```bash
mlflow ui --backend-store-uri sqlite:///mlflow.db
```
Open [http://localhost:5000](http://localhost:5000) to inspect experiment runs and registered models.

---

### 3. Drift & Operational Monitoring
- **Script**: `src/monitoring/monitor.py`
- Monitors missing feature rates, distribution drift (relative mean shift comparing recent 20% against baseline 70%), holdout proxy RMSE/F1, and prediction latency.

#### Execute:
```bash
# Linux / macOS
python3 src/monitoring/monitor.py

# Windows
python src/monitoring/monitor.py
```
*Output*: Generates detailed report in `logs/monitoring_report.json`.

---

### 4. FastAPI Inference Service
- **Script**: `api/main.py`
- **Endpoints**:
  - `GET /health`: Model artifact and service health check (503 if models missing, 200 OK when ready).
  - `GET /model-info`: Returns loaded model metadata, feature schema, and registered versions.
  - `POST /predict`: Predicts 24h numerical AQI, CPCB AQI category, and returns latency.

#### Start API Locally:
```bash
# Linux / macOS
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Windows
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

#### Test Endpoints:

##### Linux / macOS (curl):
```bash
# Health check
curl -s http://localhost:8000/health

# Model info
curl -s http://localhost:8000/model-info

# 24h Prediction
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "lat_gen": 12.9, "lon_gen": 77.6, "aqi": 75.0,
    "aqi_lag1": 70.0, "aqi_lag2": 68.0, "aqi_lag3": 72.0,
    "aqi_roll_mean_3": 71.0, "aqi_roll_std_3": 3.0,
    "aqi_roll_mean_7": 69.0, "aqi_roll_max_7": 85.0,
    "aqi_diff_1": 5.0, "hour": 14, "dayofweek": 2, "month": 8
  }'
```

##### Windows (PowerShell):
```powershell
# Health check
curl.exe -s http://localhost:8000/health

# Model info
curl.exe -s http://localhost:8000/model-info

# 24h Prediction
$body = @{
  lat_gen = 12.9; lon_gen = 77.6; aqi = 75.0
  aqi_lag1 = 70.0; aqi_lag2 = 68.0; aqi_lag3 = 72.0
  aqi_roll_mean_3 = 71.0; aqi_roll_std_3 = 3.0
  aqi_roll_mean_7 = 69.0; aqi_roll_max_7 = 85.0
  aqi_diff_1 = 5.0; hour = 14; dayofweek = 2; month = 8
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8000/predict `
  -Method Post -ContentType "application/json" -Body $body
```

---

## Run with Docker (Cross-Platform)

The inference service is fully containerized. Because `models/` is git-ignored, ensure models are trained locally first (`python src/models/train.py`).

### 1. Build the Docker Image
```bash
docker build -t aqi-api .
```

### 2. Run the Container
```bash
docker run -d --name aqi-api -p 8000:8000 aqi-api
```

### 3. Verify Container Status & Endpoints
```bash
docker ps --filter "name=aqi-api"
```

#### Test Container Health & Prediction:
- **Linux/macOS**:
  ```bash
  curl -s http://localhost:8000/health
  ```
- **Windows (PowerShell)**:
  ```powershell
  curl.exe -s http://localhost:8000/health
  ```

### 4. Stop and Remove Container
```bash
docker stop aqi-api
docker rm aqi-api
```

---

## Interactive Dashboard

The Streamlit dashboard contains both Part 1 analytics and the Part 2 forecasting module:
- **Part 1**: Average AQI trends, pollutant contribution analysis, station comparison, weather correlations, and raw data viewer.
- **Part 2**: Dedicated **"AQI Prediction — 24h ahead (Part 2)"** interface that submits real-time requests to the FastAPI endpoint with an automatic local Joblib fallback if the API is offline.

```bash
# Linux / macOS / Windows
streamlit run dashboard/app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Automated Testing

The repository includes a comprehensive 26-test suite validating the data pipeline, feature engineering, leakage prevention, temporal ordering, model training, MLflow versioning, API validation, monitoring reports, and master orchestrator checkpoint/execution safety.

### Run All Tests:

#### Linux / macOS:
```bash
export PYTHONPATH="."
pytest -v
```

#### Windows (PowerShell):
```powershell
$env:PYTHONPATH="."
pytest -v
```

#### Windows (Command Prompt):
```cmd
set PYTHONPATH=.
pytest -v
```

**Verification Status**: `26 passed in 33.21s` (100% passing).

---

## Model Lifecycle & Monitoring Policy

As documented in [`docs/model_lifecycle.md`](file:///f:/air-quality-aqi-project/docs/model_lifecycle.md):
1. **Retraining Criteria**:
   - Sustained feature drift $> 30\%$ over non-calendar features across consecutive checks.
   - Recent holdout RMSE $> 40.0$ or macro-F1 $< 0.50$.
   - Arrival of new continuous sensor data expanding the dataset by $\ge 20\%$.
2. **Promotion Policy**:
   - Candidate models must beat currently deployed models on the validation set.
   - Model versioning is append-only in MLflow (`v1`, `v2`, ... `v5`). Previous versions are retained in SQLite for immediate rollback.

---

## Author & License

- **Author**: Bishal Kumar Shah
- **Course**: Data Engineering and MLOps Individual Project Assignment
- **License**: MIT