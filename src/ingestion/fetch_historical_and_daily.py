"""Automated ingestion of historical and daily AQI & Weather data.

Supports:
1. Batch fetch of historical periods (e.g., September & October 2026).
2. Incremental daily sync (fetches past 2 days up to present and updates gold dataset).

Usage:
    python src/ingestion/fetch_historical_and_daily.py --mode historical --start 2026-09-01 --end 2026-10-14
    python src/ingestion/fetch_historical_and_daily.py --mode daily
"""

import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "ingestion.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("fetch_historical_and_daily")

OPENAQ_API_KEY = os.getenv("OPENAQ_API_KEY")
OPENAQ_HEADERS = {"X-API-Key": OPENAQ_API_KEY} if OPENAQ_API_KEY else {}

# Key Bengaluru stations actively recording data
STATIONS = [
    {"id": 5548, "name": "BTM Layout, Bengaluru - CPCB", "lat": 12.9135, "lon": 77.5951},
    {"id": 5607, "name": "Peenya, Bengaluru - CPCB", "lat": 13.0270, "lon": 77.4941},
    {"id": 5644, "name": "Sanegurava Halli, Bengaluru - KSPCB", "lat": 12.9903, "lon": 77.5431},
    {"id": 6973, "name": "Jayanagar 5th Block, Bengaluru - KSPCB", "lat": 12.9210, "lon": 77.5849},
    {"id": 6974, "name": "Bapuji Nagar, Bengaluru - KSPCB", "lat": 12.9519, "lon": 77.5398},
    {"id": 6975, "name": "Silk Board, Bengaluru - KSPCB", "lat": 12.9173, "lon": 77.6228},
    {"id": 6983, "name": "Hombegowda Nagar, Bengaluru - KSPCB", "lat": 12.9385, "lon": 77.5901},
    {"id": 6984, "name": "Hebbal, Bengaluru - KSPCB", "lat": 13.0292, "lon": 77.5859},
]

RAW_OPENAQ_DIR = Path("data/raw/openaq")
RAW_WEATHER_DIR = Path("data/raw/openmeteo")
RAW_OPENAQ_DIR.mkdir(parents=True, exist_ok=True)
RAW_WEATHER_DIR.mkdir(parents=True, exist_ok=True)


def fetch_openaq_measurements_for_station(location_id, location_name, date_from, date_to):
    """Fetch all measurements across all sensors for a location between date_from and date_to."""
    sensors_url = f"https://api.openaq.org/v3/locations/{location_id}/sensors"
    try:
        res = requests.get(sensors_url, headers=OPENAQ_HEADERS, timeout=30)
        if res.status_code != 200:
            logger.warning("Could not fetch sensors for %s (%s): %s", location_name, location_id, res.status_code)
            return []
        sensors = res.json().get("results", [])
    except Exception as exc:
        logger.error("Error fetching sensors for %s: %s", location_id, exc)
        return []

    measurements = []
    for sensor in sensors:
        sensor_id = sensor.get("id")
        param_info = sensor.get("parameter", {})
        param_name = param_info.get("name") if isinstance(param_info, dict) else str(param_info)

        # Only fetch relevant AQI pollutants to be fast and respectful of rate limits
        if param_name not in {"pm25", "pm10", "no2", "so2", "co", "o3"}:
            continue

        page = 1
        while page <= 30:  # Paginate up to 3,000 records per sensor to cover full period
            m_url = f"https://api.openaq.org/v3/sensors/{sensor_id}/measurements"
            params = {
                "datetime_from": date_from,
                "datetime_to": date_to,
                "limit": 100,
                "page": page,
            }
            try:
                m_res = requests.get(m_url, headers=OPENAQ_HEADERS, params=params, timeout=30)
                if m_res.status_code != 200:
                    break
                batch = m_res.json().get("results", [])
                if not batch:
                    break
                for m in batch:
                    m["location_id"] = location_id
                    m["location_name"] = location_name
                    m["sensor_id"] = sensor_id
                    measurements.append(m)
                if len(batch) < 100:
                    break
                page += 1
            except Exception as e:
                logger.error("Error fetching measurements for sensor %s: %s", sensor_id, e)
                break
    return measurements


def fetch_weather_for_period(date_from_str, date_to_str, is_archive=True):
    """Fetch hourly weather for Bengaluru."""
    if is_archive:
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": 12.9716,
            "longitude": 77.5946,
            "start_date": date_from_str,
            "end_date": date_to_str,
            "hourly": "temperature_2m,relative_humidity_2m,rain,wind_speed_10m",
            "timezone": "Asia/Kolkata",
        }
    else:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": 12.9716,
            "longitude": 77.5946,
            "past_days": 3,
            "forecast_days": 1,
            "hourly": "temperature_2m,relative_humidity_2m,rain,wind_speed_10m",
            "timezone": "Asia/Kolkata",
        }

    try:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        logger.error("Weather fetch failed (%s): %s", r.status_code, r.text[:200])
    except Exception as exc:
        logger.error("Weather request exception: %s", exc)
    return None


def run_pipeline():
    """Execute cleaning, validation, join, and AQI calculation stages."""
    import subprocess
    import sys

    py = sys.executable
    steps = [
        [py, "src/transformation/clean_pollution.py"],
        [py, "src/transformation/clean_weather.py"],
        [py, "src/validation/quality_checks.py"],
        [py, "src/transformation/join_data.py"],
        [py, "src/transformation/calculate_aqi.py"],
        [py, "src/features/build_features.py"],
    ]
    for step in steps:
        logger.info("Executing: %s", " ".join(step))
        res = subprocess.run(step, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error("Failed executing %s: %s", step, res.stderr)
            raise RuntimeError(f"Step failed: {res.stderr}")
        logger.info("Step completed successfully.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["historical", "daily"], default="historical")
    parser.add_argument("--start", default="2026-09-01")
    parser.add_argument("--end", default="2026-10-14")
    args = parser.parse_args()

    now_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.mode == "historical":
        logger.info("Starting historical ingestion for %s to %s", args.start, args.end)
        date_from_iso = f"{args.start}T00:00:00Z"
        date_to_iso = f"{args.end}T23:59:59Z"

        all_measurements = []
        for station in STATIONS[:4]:  # Top 4 representative stations for speed & quota
            logger.info("Collecting OpenAQ for %s ...", station["name"])
            m = fetch_openaq_measurements_for_station(
                station["id"], station["name"], date_from_iso, date_to_iso
            )
            logger.info("Collected %s records for %s", len(m), station["name"])
            all_measurements.extend(m)

        if all_measurements:
            out_pollution = RAW_OPENAQ_DIR / f"measurements_sep_oct_{now_ts}.json"
            with open(out_pollution, "w") as f:
                json.dump(all_measurements, f, indent=2)
            logger.info("Saved %s measurements to %s", len(all_measurements), out_pollution)

        weather_data = fetch_weather_for_period(args.start, args.end, is_archive=True)
        if weather_data:
            out_weather = RAW_WEATHER_DIR / f"weather_archive_sep_oct_{now_ts}.json"
            with open(out_weather, "w") as f:
                json.dump(weather_data, f, indent=2)
            logger.info("Saved weather data to %s", out_weather)

    else:
        # Daily incremental mode
        logger.info("Running daily incremental ingestion...")
        today = datetime.now(timezone.utc)
        yesterday = today - timedelta(days=2)
        date_from_iso = yesterday.strftime("%Y-%m-%dT00:00:00Z")
        date_to_iso = today.strftime("%Y-%m-%dT23:59:59Z")

        all_measurements = []
        for station in STATIONS[:4]:
            m = fetch_openaq_measurements_for_station(
                station["id"], station["name"], date_from_iso, date_to_iso
            )
            all_measurements.extend(m)

        if all_measurements:
            out_pollution = RAW_OPENAQ_DIR / f"measurements_daily_{now_ts}.json"
            with open(out_pollution, "w") as f:
                json.dump(all_measurements, f, indent=2)
            logger.info("Saved %s daily measurements to %s", len(all_measurements), out_pollution)

        weather_data = fetch_weather_for_period(
            yesterday.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), is_archive=False
        )
        if weather_data:
            out_weather = RAW_WEATHER_DIR / f"weather_daily_{now_ts}.json"
            with open(out_weather, "w") as f:
                json.dump(weather_data, f, indent=2)
            logger.info("Saved daily weather to %s", out_weather)

    # Re-run pipeline end-to-end to update staging, cleaned, gold, and ml_features
    logger.info("Running complete transformation pipeline...")
    run_pipeline()
    logger.info("Pipeline update complete!")


if __name__ == "__main__":
    main()
