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

The complete workflow will later be executed using Apache Airflow.

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

The second phase of the project will extend the pipeline with:

- AQI prediction
- Machine-learning models
- Feature engineering
- MLflow experiment tracking
- Model registry
- FastAPI
- Docker
- Model monitoring
- Retraining strategy

## Project Status

Part 1 focuses on data ingestion, ETL, data quality, analytical storage,
and visualization.

## Author

Bishal Kumar Shah

```

```
