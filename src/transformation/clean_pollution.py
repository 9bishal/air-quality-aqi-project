import json
import pandas as pd
from pathlib import Path


# Location of raw OpenAQ measurement data
RAW_DIR = Path("data/raw/openaq")

# Location for staging data
STAGING_DIR = Path("data/staging")


def load_latest_measurements():
    # Find the latest measurements JSON file
    files = list(RAW_DIR.glob("measurements_*.json"))

    if not files:
        raise FileNotFoundError(
            "No OpenAQ measurement data found."
        )

    return max(
        files,
        key=lambda file: file.stat().st_mtime
    )


def clean_pollution_data():
    print("Starting pollution data transformation...")

    # Load the latest raw measurement file
    raw_file = load_latest_measurements()

    with open(raw_file, "r") as file:
        data = json.load(file)

    # Convert measurements into a DataFrame
    df = pd.json_normalize(data)

    print("Raw records:", len(df))

    # Select the columns needed for our project
    columns = [
        "location_id",
        "location_name",
        "sensor_id",
        "parameter.name",
        "value",
        "unit",
        "period.datetimeFrom.utc"
    ]

    # Keep only columns available in the API response
    available_columns = [
        column for column in columns
        if column in df.columns
    ]

    df = df[available_columns]

    # Rename columns to simpler names
    df = df.rename(columns={
        "location_id": "station_id",
        "location_name": "station_name",
        "sensor_id": "sensor_id",
        "parameter.name": "pollutant",
        "period.datetimeFrom.utc": "timestamp"
    })

    # Convert timestamp to datetime
    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
        utc=True
    )

    # Convert pollutant values to numeric
    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce"
    )

    # Remove exact duplicate observations
    df = df.drop_duplicates()

    # Remove records with missing essential fields
    df = df.dropna(
        subset=[
            "station_id",
            "station_name",
            "pollutant",
            "value",
            "timestamp"
        ]
    )

    # Remove negative pollutant measurements
    df = df[df["value"] >= 0]

    # Add city information
    df["city"] = "Bengaluru"

    # Create staging directory
    STAGING_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # Save staging data
    output_file = STAGING_DIR / "pollution.csv"

    df.to_csv(
        output_file,
        index=False
    )

    print("Cleaned records:", len(df))
    print("Staging data saved to:", output_file)

    # Show pollutants found in the data
    print("\nPollutants found:")
    print(df["pollutant"].unique())


if __name__ == "__main__":
    clean_pollution_data()