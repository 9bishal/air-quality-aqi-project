from datetime import datetime

from airflow import DAG
# pyrefly: ignore [missing-import]
from airflow.operators.bash import BashOperator


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
        bash_command="python src/ingestion/openaq_collector.py"
    )

    # Step 2: Collect weather data from Open-Meteo
    collect_weather = BashOperator(
        task_id="collect_weather",
        bash_command="python src/ingestion/weather_collector.py"
    )

    # Step 3: Transform pollution data
    clean_pollution = BashOperator(
        task_id="clean_pollution",
        bash_command="python src/transformation/clean_pollution.py"
    )

    # Step 4: Transform weather data
    clean_weather = BashOperator(
        task_id="clean_weather",
        bash_command="python src/transformation/clean_weather.py"
    )

    # Step 5: Run data-quality checks
    quality_checks = BashOperator(
        task_id="quality_checks",
        bash_command="python src/validation/quality_checks.py"
    )

    # Step 6: Join pollution and weather data
    join_data = BashOperator(
        task_id="join_data",
        bash_command="python src/transformation/join_data.py"
    )

    # Step 7: Calculate AQI
    calculate_aqi = BashOperator(
        task_id="calculate_aqi",
        bash_command="python src/transformation/calculate_aqi.py"
    )

    # Define the order in which tasks should run
    collect_openaq >> clean_pollution
    collect_weather >> clean_weather

    [clean_pollution, clean_weather] >> quality_checks
    quality_checks >> join_data
    join_data >> calculate_aqi