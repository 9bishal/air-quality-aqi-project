# Data Dictionary

## Station Data (`data/cleaned/stations.csv` from `data/raw/openaq/locations_*.json`)

| Column       | Data Type | Description                       | Source |
| ------------ | --------- | --------------------------------- | ------ |
| station_id   | Integer   | Unique monitoring station ID (`id`) | OpenAQ `locations.id` |
| station_name | String    | Name of the monitoring station    | OpenAQ `locations.name` |
| latitude     | Float     | Latitude of the station (validated -90..90 DQ-003) | OpenAQ `coordinates.latitude` |
| longitude    | Float     | Longitude of the station (validated -180..180 DQ-004) | OpenAQ `coordinates.longitude` |
| city         | String    | City where the station is located | Enriched as `Bengaluru` |

## Air Quality Data

| Column       | Data Type | Description                         | Table |
| ------------ | --------- | ----------------------------------- | ----- |
| station_id   | Integer   | FK to stations                      | `pollution` / `aqi_data` |
| station_name | String    | Name of the monitoring station      | `pollution` |
| sensor_id    | Integer   | Sensor ID from OpenAQ               | `pollution` |
| timestamp    | Timestamp | Time of observation (UTC, `period.datetimeFrom.utc`) | `pollution` `aqi_data` |
| pollutant    | String    | Name (`pm25`, `pm10`, `no2`, `so2`, `co`, `o3` lowercased) | `pollution` |
| value        | Float     | Measured concentration (DQ-005 >=0, <1000) | `pollution` |
| unit         | String    | Standardized to µg/m³ (DQ-010)     | `pollution` |
| city         | String    | `Bengaluru`                        | `pollution` / `aqi_data` |
| aqi          | Integer   | Calculated via CPCB breakpoints max sub-index | `aqi_data` |
| aqi_category | String    | Good / Satisfactory / Moderate / Poor / Very Poor / Severe | `aqi_data` |

## Weather Data (`data/cleaned/weather.csv`)

| Column      | Data Type | Description                     | Validation |
| ----------- | --------- | ------------------------------- | ---------- |
| timestamp   | Timestamp | Hourly observation (Asia/Kolkata → UTC) | DQ-001 not null |
| temperature | Float     | °C (-50..60) | sanity check |
| humidity    | Float     | % (0..100 DQ-006) | DQ-006 |
| rainfall    | Float     | mm (>=0 DQ-007) | DQ-007 |
| wind_speed  | Float     | m/s (>=0 DQ-008) | DQ-008 |

## Gold / Analytics

| Table | Columns | Description |
|-------|---------|-------------|
| `aqi_data` | `station_id, timestamp, aqi, aqi_category, city` | Gold: max sub-index per station+timestamp |
| `mart_aqi_daily` | `date, city, average_aqi, maximum_aqi, minimum_aqi, record_count` | Daily aggregation `sql/analytics.sql:2` |
| `mart_pollutant_summary` | `city, pollutant, average_value, maximum_value, minimum_value, record_count` | Pollutant averages |

## Data Sources

### OpenAQ (`src/ingestion/openaq_collector.py:12`)

Primary pollution source. Bengaluru radius 25km, 10 locations, 100 measurements/sensor. Raw: `data/raw/openaq/measurements_*.json` + `locations_*.json`. Access: `OPENAQ_API_KEY` from https://explore.openaq.org/.

### Open-Meteo (`src/ingestion/weather_collector.py:14`)

Weather: `https://api.open-meteo.com/v1/forecast?latitude=12.9716&longitude=77.5946&hourly=temperature_2m,relative_humidity_2m,rain,wind_speed_10m`. No key. Raw: `data/raw/openmeteo/weather_*.json`. Limitation: forecast API returns recent period only (~7 days); historic pollution (2016-2018) has limited overlap — documented in `docs/architecture.md`.

## Lineage

`raw JSON → staging CSV (clean_pollution/weather) → cleaned (quality_checks DQ-001..010) → enriched (join_data) → gold (calculate_aqi) → PostgreSQL (load_data) → marts (analytics.sql) → dashboard`
