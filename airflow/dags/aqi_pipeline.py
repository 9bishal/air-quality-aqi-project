from datetime import datetime
from pathlib import Path

from airflow import DAG
# pyrefly: ignore [missing-import]
from airflow.operators.bash import BashOperator

# Project root so BashOperator works regardless of Airflow's temp cwd
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])


# Create the Airflow DAG
with DAG(
    dag_id="aqi_pipeline",
    start_date=datetime(2026, 9, 1),
    schedule="@daily",
    catchup=False,
    tags=["air-quality", "etl"]
) as dag:

    # Step 1: Collect pollution data from OpenAQ
    collect_openaq = BashOperator(
        task_id="collect_openaq",
        bash_command="python3 src/ingestion/openaq_collector.py",
        cwd=PROJECT_ROOT
    )

    # Step 2: Collect weather data from Open-Meteo
    collect_weather = BashOperator(
        task_id="collect_weather",
        bash_command="python3 src/ingestion/weather_collector.py",
        cwd=PROJECT_ROOT
    )

    # Step 3: Transform pollution data
    clean_pollution = BashOperator(
        task_id="clean_pollution",
        bash_command="python3 src/transformation/clean_pollution.py",
        cwd=PROJECT_ROOT
    )

    # Step 4: Transform weather data
    clean_weather = BashOperator(
        task_id="clean_weather",
        bash_command="python3 src/transformation/clean_weather.py",
        cwd=PROJECT_ROOT
    )

    # Step 5: Run data-quality checks
    quality_checks = BashOperator(
        task_id="quality_checks",
        bash_command="python3 src/validation/quality_checks.py",
        cwd=PROJECT_ROOT
    )

    # Step 6: Join pollution and weather data
    join_data = BashOperator(
        task_id="join_data",
        bash_command="python3 src/transformation/join_data.py",
        cwd=PROJECT_ROOT
    )

    # Step 7: Calculate AQI
    calculate_aqi = BashOperator(
        task_id="calculate_aqi",
        bash_command="python3 src/transformation/calculate_aqi.py",
        cwd=PROJECT_ROOT
    )

    # Define the order in which tasks should run
    collect_openaq >> clean_pollution
    collect_weather >> clean_weather

    [clean_pollution, clean_weather] >> quality_checks
    quality_checks >> join_data
    join_data >> calculate_aqi