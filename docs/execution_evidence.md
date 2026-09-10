# Execution Evidence — Part 1 End-to-End Run

## 1. Pipeline Execution Order (as per `airflow/dags/aqi_pipeline.py:9`)

```bash
python src/ingestion/openaq_collector.py
python src/ingestion/weather_collector.py
python src/transformation/clean_pollution.py
python src/transformation/clean_weather.py
python src/validation/quality_checks.py
python src/transformation/join_data.py
python src/transformation/calculate_aqi.py
python src/database/load_data.py
python src/database/run_analytics.py
streamlit run dashboard/app.py
```

## 2. Latest Execution Logs (example)

Capture output after running — paste below:

```text
# python src/ingestion/openaq_collector.py
Starting OpenAQ measurement collection...
Locations found: 26
...
Total measurements collected: 8687
Raw measurements saved to: data/raw/openaq/measurements_20260908_215030.json

# python src/ingestion/weather_collector.py
Starting weather data collection...
Weather data collected successfully.
Raw weather data saved to: data/raw/openmeteo/weather_20260908_213759.json

# python src/transformation/clean_pollution.py
Raw records: 8687
Cleaned records: 8687
Staging data saved to: data/staging/pollution.csv

# python src/validation/quality_checks.py
Validating pollution data...
Total pollution records: 8687
Rejected pollution records: 0
Validating weather data...
Total weather records: 168
Logs in logs/ingestion.log + logs/ingestion_metadata.csv + logs/validation_summary.log
```

## 3. Row Counts (verified 2026-09-08)

| Layer | File | Rows |
|---|---|---|
| Raw | `data/raw/openaq/measurements_*.json` | 8687 |
| Raw | `data/raw/openmeteo/weather_*.json` | 168 |
| Staging | `data/staging/pollution.csv` | 8687 |
| Cleaned | `data/cleaned/pollution.csv` | 8687 |
| Cleaned | `data/cleaned/weather.csv` | 168 |
| Enriched | `data/cleaned/enriched_air_quality.csv` | 8687 |
| Gold | `data/gold/aqi_data.csv` | 1682 |
| Rejected | `data/rejected/rejected_pollution.csv` | 0 + header |
| Stations | `data/cleaned/stations.csv` | 26 (Bengaluru) |

## 4. Metadata Log

`logs/ingestion_metadata.csv` contains `extraction_date,source,file,api_status,row_count` per `assignment.md:44`.
`logs/ingestion.log` contains per-task status and row counts.

## 5. Screenshots Placeholder

Add screenshots under `docs/screenshots/`:

- `01_airflow_dag.png` — DAG `aqi_pipeline` success in Airflow UI
- `02_postgres_tables.png` — `\dt` showing pollution/weather/aqi_data + marts
- `03_dashboard_overview.png`
- `04_dashboard_trend.png`
- `05_dashboard_pollutant.png`
- `06_dashboard_weather_impact.png`

## 6. Database Verification

```sql
-- sql/schema.sql creates pollution, weather, aqi_data
-- sql/analytics.sql creates mart_aqi_daily, mart_pollutant_summary
SELECT COUNT(*) FROM pollution; -- 8687
SELECT COUNT(*) FROM aqi_data; -- 1682
SELECT * FROM mart_aqi_daily LIMIT 5;
SELECT * FROM mart_pollutant_summary;
```

## 7. Dashboard

```bash
streamlit run dashboard/app.py
# Views: AQI Trend, Category Distribution, By Station, Distribution, Pollutant Contribution, Weather Impact, Hourly/Monthly patterns
```

## 8. Tests

```bash
pytest tests/test_pipeline.py -v
```
