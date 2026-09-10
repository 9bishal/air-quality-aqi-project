import csv
import json
import logging
import requests
from datetime import datetime
from pathlib import Path


# Bengaluru coordinates
LATITUDE = 12.9716
LONGITUDE = 77.5946

# Open-Meteo API endpoint
API_URL = "https://api.open-meteo.com/v1/forecast"

# Logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
INGESTION_LOG = LOG_DIR / "ingestion.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(INGESTION_LOG),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
METADATA_LOG = LOG_DIR / "ingestion_metadata.csv"


def log_metadata(source, status, row_count, file_path=""):
    header = ["extraction_date", "source", "file", "api_status", "row_count"]
    exists = METADATA_LOG.exists()
    with open(METADATA_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(header)
        writer.writerow([
            datetime.now().isoformat(),
            source,
            str(file_path),
            status,
            row_count
        ])


def collect_weather_data():
    logger.info("Starting weather data collection...")

    # Request hourly weather data for Bengaluru
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": "temperature_2m,relative_humidity_2m,rain,wind_speed_10m",
        "timezone": "Asia/Kolkata"
    }

    try:
        response = requests.get(API_URL, params=params, timeout=30)

        # Stop if the API request fails
        if response.status_code != 200:
            logger.error("Failed to collect weather data. Status code: %s", response.status_code)
            log_metadata("open-meteo", f"FAILED: {response.status_code}", 0)
            return

        # Convert the API response to a Python dictionary
        data = response.json()

        logger.info("Weather data collected successfully.")

        # Create the raw weather data directory
        output_dir = Path("data/raw/openmeteo")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create a timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"weather_{timestamp}.json"

        # Save the original API response as raw data
        with open(output_file, "w") as file:
            json.dump(data, file, indent=4)

        row_count = len(data.get("hourly", {}).get("time", []))
        logger.info("Raw weather data saved to: %s (%s rows)", output_file, row_count)
        log_metadata("open-meteo", "SUCCESS", row_count, output_file)

    except requests.RequestException as error:
        logger.error("Weather API request failed. Error: %s", error)
        log_metadata("open-meteo", f"FAILED: {error}", 0)


if __name__ == "__main__":
    collect_weather_data()
