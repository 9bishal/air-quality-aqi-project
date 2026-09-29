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

The second phase extends the pipeline with AQI prediction (implemented):

- AQI prediction (next-observation AQI value + category)
- Machine-learning models (LinearRegression / RandomForest + comparison)
- Feature engineering (`src/features/build_features.py`: lag 1/2/3, rolling 3/7, calendar)
- MLflow experiment tracking (`sqlite:///mlflow.db`, experiment `aqi_prediction`)
- Model registry (`aqi_regressor`, `aqi_classifier` + `models/model_metadata.json`)
- FastAPI (`api/main.py`: `GET /health`, `GET /model-info`, `POST /predict`)
- Docker (`Dockerfile`: `docker build -t aqi-api . && docker run -p 8000:8000 aqi-api`)
- Model monitoring (`src/monitoring/monitor.py` → `logs/monitoring_report.json`)
- Retraining strategy (`docs/model_lifecycle.md`)

```bash
python3 src/features/build_features.py
python3 src/models/train.py
python3 src/monitoring/monitor.py
uvicorn api.main:app --host 0.0.0.0 --port 8000
python3 -m pytest tests/ -q
```

## Project Status

Part 1 focuses on data ingestion, ETL, data quality, analytical storage,
and visualization.

## Author

Bishal Kumar Shah

```

```
