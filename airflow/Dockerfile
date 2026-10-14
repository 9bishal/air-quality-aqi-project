FROM apache/airflow:2.9.3-python3.11

USER airflow

# Only install what the Airflow DAG tasks actually run (data collection, cleaning, AQI calc, and postgres)
COPY airflow/requirements-airflow.txt /requirements-airflow.txt
RUN pip install --no-cache-dir -r /requirements-airflow.txt
