## Step 20 — `README.md`

````markdown id="8m42kx"
# Air Quality Index Analysis and Prediction

## Project Overview

This project develops a data engineering pipeline for collecting, cleaning,
validating, storing, and analyzing air-quality and weather data.

The project uses public air-quality data from OpenAQ and weather data from
Open-Meteo. The processed data is stored in PostgreSQL and visualized using
a Streamlit dashboard.

## Objectives

- Collect air-quality data from a public API.
- Collect weather data for the selected location.
- Build a reproducible ETL pipeline.
- Maintain raw, staging, cleaned, and gold data layers.
- Perform data-quality checks.
- Store processed data in PostgreSQL.
- Create analytical data marts.
- Build an interactive Streamlit dashboard.

## Technology Stack

- Python
- Pandas
- Requests
- Apache Airflow
- PostgreSQL
- SQLAlchemy
- Streamlit
- Plotly

## Data Sources

### OpenAQ

OpenAQ is used as the primary source for air-quality and monitoring-station
data.

### Open-Meteo

Open-Meteo is used to obtain weather information such as:

- Temperature
- Relative humidity
- Rainfall
- Wind speed

## Data Pipeline

```text
OpenAQ + Open-Meteo
        |
        v
   Python Ingestion
        |
        v
     Raw Layer
        |
        v
   Staging Layer
        |
        v
 Cleaning + Validation
        |
        +------> Rejected Records
        |
        v
   Cleaned Layer
        |
        v
    PostgreSQL
        |
        v
   Gold / Analytics
        |
        v
 Streamlit Dashboard
```
````

## Project Structure

```text
air-quality-aqi-project/
|
├── airflow/
│   └── dags/
|
├── data/
│   ├── raw/
│   ├── staging/
│   ├── cleaned/
│   ├── gold/
│   └── rejected/
|
├── src/
│   ├── ingestion/
│   ├── transformation/
│   ├── validation/
│   └── database/
|
├── dashboard/
├── sql/
├── docs/
├── tests/
|
├── requirements.txt
├── .env
└── README.md
```

## Installation

Create a Python virtual environment:

```bash
python -m venv venv
```

Activate the environment.

### macOS / Linux

```bash
source venv/bin/activate
```

### Windows (PowerShell)

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=air_quality_db
DB_USER=postgres
DB_PASSWORD=your_password
```

Do not commit the `.env` file to GitHub.

## Running the Pipeline

The individual pipeline stages can be executed in order:

```bash
python src/ingestion/openaq_collector.py

python src/ingestion/weather_collector.py

python src/transformation/clean_pollution.py

python src/transformation/clean_weather.py

python src/validation/quality_checks.py

python src/transformation/join_data.py

python src/transformation/calculate_aqi.py
```

### Running via Apache Airflow (DAG `aqi_pipeline`)

Do not run the DAG as a script (`python airflow/dags/aqi_pipeline.py` only defines the DAG - see `airflow/dags/aqi_pipeline.py:9`). The DAG is parsed by the Airflow scheduler.

DAG file: `airflow/dags/aqi_pipeline.py` (`dag_id="aqi_pipeline"`, `schedule="@daily"`) uses `BashOperator(cwd=PROJECT_ROOT, bash_command="python3 src/...")` so tasks run from project root regardless of Airflow's temp working dir.

Point Airflow to the project DAGs (default `AIRFLOW_HOME` is `~/airflow`):

```bash
# Option A: set env var (per-command or export)
export AIRFLOW__CORE__DAGS_FOLDER=/Users/bishalkumarshah/Downloads/air-quality-aqi-project/airflow/dags
# Option B: symlink
mkdir -p ~/airflow/dags && ln -sf /Users/bishalkumarshah/Downloads/air-quality-aqi-project/airflow/dags/aqi_pipeline.py ~/airflow/dags/
```

Initialize DB (first time) and verify DAG parses:

```bash
airflow db migrate
airflow dags list | grep aqi_pipeline
airflow dags list-import-errors
```

Quick test without scheduler (recommended for development):

```bash
airflow dags test aqi_pipeline 2026-09-01
# or single task:
airflow tasks test aqi_pipeline collect_weather 2026-09-01
```

Full scheduler run:

```bash
# Terminal 1: start Airflow (Airflow 3.x)
airflow standalone
# or: airflow scheduler & airflow api-server

# Terminal 2: trigger
airflow dags trigger aqi_pipeline
airflow dags state aqi_pipeline 2026-09-01
airflow tasks states-for-dag-run aqi_pipeline <run_id>
```

Ensure `python3` used by `BashOperator` has dependencies (`pandas`, `requests`, etc. from `requirements.txt:1-18`): use `python3 -m pip install -r requirements.txt` in the same env that runs Airflow.

## Dashboard

Run the Streamlit dashboard using:

```bash
streamlit run dashboard/app.py
```

The dashboard provides:

- AQI overview
- AQI trends
- Pollutant analysis
- Station comparison
- Weather and AQI relationship
- AQI category distribution

## Data Quality

The pipeline checks for:

- Missing values
- Invalid coordinates
- Negative pollutant values
- Invalid weather values
- Duplicate observations
- Invalid timestamps

Rejected records are stored separately instead of being included in the
analytical dataset.

## Database

PostgreSQL is used to store the processed air-quality and weather data.

The analytical layer contains daily AQI summaries and other data marts
used by the dashboard.

## Part 2

The second phase extends the pipeline with 24h-ahead AQI prediction (implemented
and verified 2026-10-14, 21/21 tests passing):

- Target: AQI at T+24h (±2h, UTC, per station); missing windows dropped and
  counted, never substituted (`src/features/build_features.py`)
- Features: gap-aware lags/rolling (past-only), UTC calendar, generalised
  grid `lat_gen/lon_gen` (~11km; `station_id` not a feature)
- Data: 1624 gold rows → 609 ML rows (809 missing +24h window); weather
  omitted (Open-Meteo 2026 does not overlap OpenAQ 2016-2025)
- Models: Dummy/Linear/RF regressors + Dummy/Logistic/RF classifiers,
  chronological 70/15/15 split, val-selected (RF-reg val RMSE 47.5,
  LR-clf val F1 0.72); test shows regime-shift degradation (honest limitation)
- MLflow (`sqlite:///mlflow.db`, experiment `aqi_prediction`; registry
  `aqi_regressor`/`aqi_classifier` v2 READY) — `mlflow ui --backend-store-uri sqlite:///mlflow.db`
- FastAPI (`api/main.py`: `GET /health`, `GET /model-info`, `POST /predict`,
  horizon `+24h` in responses) — `uvicorn api.main:app --host 0.0.0.0 --port 8000`
- Docker — see **Run with Docker (Windows)** below. Short version: run
  `python src/models/train.py` first (models/ is git-ignored and must exist
  before the image is built), then `docker build -t aqi-api .` and
  `docker run -p 8000:8000 aqi-api`.
- Monitoring (`src/monitoring/monitor.py` → `logs/monitoring_report.json`;
  holdout proxy labelled, not live) + retraining rules (`docs/model_lifecycle.md`)
- Dashboard Part-2 section prefers FastAPI, labels horizon/versions/limitations

```bash
python3 src/features/build_features.py
python3 src/models/train.py
python3 src/monitoring/monitor.py
uvicorn api.main:app --host 0.0.0.0 --port 8000
python3 -m pytest tests/ -q
```

## Run with Docker (Windows)

Prerequisites: [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
(WSL 2 backend enabled), Python 3.10+, Git. All commands in PowerShell
from the project root.

```powershell
# 1. Clone and enter the project
git clone https://github.com/9bishal/air-quality-aqi-project.git
cd air-quality-aqi-project

# 2. (Build models first — models/ is git-ignored, so the image
#     needs these files to exist before `docker build`)
py -m venv venv; .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src/features/build_features.py
python src/models/train.py

# 3. Build the image (run once; rebuild after retraining)
docker build -t aqi-api .

# 4. Run the API on port 8000
docker run -d --name aqi-api -p 8000:8000 aqi-api

# 5. Check health (expect {"status":"ok"})
curl.exe http://localhost:8000/health

# 6. Check loaded models and 24h target
curl.exe http://localhost:8000/model-info
```

Predict AQI +24h (PowerShell). Note: use `curl.exe`, not bare `curl`
(PowerShell aliases `curl` to `Invoke-WebRequest`):

```powershell
$body = @{
  lat_gen = 13.0; lon_gen = 77.5; aqi = 62.0
  aqi_lag1 = 58.0; aqi_lag2 = 55.0; aqi_lag3 = 60.0
  aqi_roll_mean_3 = 57.0; aqi_roll_std_3 = 2.5
  aqi_roll_mean_7 = 59.0; aqi_roll_max_7 = 70.0
  aqi_diff_1 = 4.0; hour = 10; dayofweek = 1; month = 3
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8000/predict `
  -Method Post -ContentType "application/json" -Body $body
# Expect: predicted_aqi, predicted_category, horizon "+24h", model names
```

Stop / restart / remove:

```powershell
docker stop aqi-api
docker start aqi-api
docker rm -f aqi-api
docker images | Select-String "aqi-api"
```

Troubleshooting:

| Symptom | Fix |
|---|---|
| `COPY models/ ... not found` at build | Run step 2 first (`python src/models/train.py`) |
| `/health` returns 503 | Container started without model files — rebuild after step 2 |
| `port is already allocated` | `docker stop aqi-api`, or use `-p 8001:8000` and call `localhost:8001` |
| `curl` gives odd errors in PowerShell | Use `curl.exe` (with `.exe`) |
| Dashboard can't reach API | Start the container first; the dashboard falls back to local joblib files otherwise |

## Project Status

Part 1 focuses on data ingestion, ETL, data quality, analytical storage,
and visualization.

## Author

Bishal Kumar Shah

```

```
Verify on GitHub with git show --stat HEAD or git log origin/main -1 --stat.