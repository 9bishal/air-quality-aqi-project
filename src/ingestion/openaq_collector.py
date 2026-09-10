import os
import csv
import json
import logging
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Ingestion logger
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

# CSV metadata log
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


# Load environment variables
load_dotenv()

# OpenAQ API endpoints
LOCATIONS_URL = "https://api.openaq.org/v3/locations"
SENSORS_URL = "https://api.openaq.org/v3/locations/{}/sensors"
MEASUREMENTS_URL = "https://api.openaq.org/v3/sensors/{}/measurements"

# Bengaluru coordinates
LATITUDE = 12.9716
LONGITUDE = 77.5946

# Search radius in meters
RADIUS = 25000

# Number of locations to process
LOCATION_LIMIT = 10

# API key from .env
API_KEY = os.getenv("OPENAQ_API_KEY")


def get_locations(headers):
    # Find monitoring locations around Bengaluru
    params = {
        "coordinates": f"{LATITUDE},{LONGITUDE}",
        "radius": RADIUS,
        "limit": LOCATION_LIMIT
    }

    response = requests.get(
        LOCATIONS_URL,
        headers=headers,
        params=params
    )

    response.raise_for_status()

    return response.json().get("results", [])


def get_sensors(location_id, headers):
    # Get sensors belonging to a monitoring location
    url = SENSORS_URL.format(location_id)

    response = requests.get(
        url,
        headers=headers
    )

    if response.status_code != 200:
        print(f"Could not get sensors for location {location_id}")
        return []

    return response.json().get("results", [])


def get_measurements(sensor_id, headers):
    # Get measurements recorded by a sensor
    url = MEASUREMENTS_URL.format(sensor_id)

    params = {
        "limit": 100
    }

    response = requests.get(
        url,
        headers=headers,
        params=params
    )

    if response.status_code != 200:
        print(f"Could not get measurements for sensor {sensor_id}")
        return []

    return response.json().get("results", [])


def collect_openaq_data():
    logger.info("Starting OpenAQ measurement collection...")

    # Check for API key
    if not API_KEY:
        logger.error("OpenAQ API key not found.")
        log_metadata("openaq", "FAILED: missing API key", 0)
        return

    headers = {
        "X-API-Key": API_KEY
    }

    try:
        # Step 1: Find Bengaluru locations
        locations = get_locations(headers)

        logger.info("Locations found: %s", len(locations))

        all_measurements = []

        # Step 2: Process each location
        for location in locations:

            location_id = location.get("id")
            location_name = location.get("name")

            logger.info(
                "Processing location: %s (%s)",
                location_name, location_id
            )

            # Get sensors for the location
            sensors = get_sensors(
                location_id,
                headers
            )

            logger.info("Sensors found: %s", len(sensors))

            # Step 3: Get measurements from each sensor
            for sensor in sensors:

                sensor_id = sensor.get("id")

                measurements = get_measurements(
                    sensor_id,
                    headers
                )

                # Add location information to measurements
                for measurement in measurements:
                    measurement["location_id"] = location_id
                    measurement["location_name"] = location_name
                    measurement["sensor_id"] = sensor_id

                    all_measurements.append(measurement)

                logger.info(
                    "Sensor %s: %s measurements",
                    sensor_id, len(measurements)
                )

        logger.info(
            "Total measurements collected: %s",
            len(all_measurements)
        )

        # Create raw data directory
        output_dir = Path("data/raw/openaq")
        output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        # Create timestamped filename
        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        output_file = (
            output_dir /
            f"measurements_{timestamp}.json"
        )

        # Save raw measurements
        with open(output_file, "w") as file:
            json.dump(
                all_measurements,
                file,
                indent=4
            )

        logger.info("Raw measurements saved to: %s", output_file)
        log_metadata("openaq", "SUCCESS", len(all_measurements), output_file)

        # Also save locations raw for stations.csv audit
        locations_file = output_dir / f"locations_{timestamp}.json"
        with open(locations_file, "w") as f:
            json.dump(locations, f, indent=4)
        logger.info("Raw locations saved to: %s", locations_file)

    except requests.RequestException as error:
        logger.error("OpenAQ API request failed. Error: %s", error)
        log_metadata("openaq", f"FAILED: {error}", 0)


if __name__ == "__main__":
    collect_openaq_data()