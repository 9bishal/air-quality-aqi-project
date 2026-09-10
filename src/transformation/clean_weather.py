import json
import pandas as pd
from pathlib import Path


# Location of raw Open-Meteo data
RAW_DIR = Path("data/raw/openmeteo")

# Location for staging weather data
STAGING_DIR = Path("data/staging")


def load_latest_raw_file():
    # Find the latest weather JSON file
    files = list(RAW_DIR.glob("weather_*.json"))

    if not files:
        raise FileNotFoundError(
            "No Open-Meteo raw data found."
        )

    return max(
        files,
        key=lambda file: file.stat().st_mtime
    )


def clean_weather_data():
    print("Starting weather data transformation...")

    # Load the latest raw weather file
    raw_file = load_latest_raw_file()

    with open(raw_file, "r") as file:
        data = json.load(file)

    # Extract hourly weather information
    hourly_data = data["hourly"]

    # Convert weather data into a DataFrame
    df = pd.DataFrame(hourly_data)

    # Rename columns to simpler names
    df = df.rename(columns={
        "time": "timestamp",
        "temperature_2m": "temperature",
        "relative_humidity_2m": "humidity",
        "rain": "rainfall",
        "wind_speed_10m": "wind_speed"
    })

    # Convert timestamp to datetime
    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce"
    )

    # Convert numeric columns
    numeric_columns = [
        "temperature",
        "humidity",
        "rainfall",
        "wind_speed"
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # Remove duplicate timestamps
    df = df.drop_duplicates(
        subset=["timestamp"]
    )

    # Remove records without timestamps
    df = df.dropna(
        subset=["timestamp"]
    )

    # Create staging directory
    STAGING_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # Save cleaned weather data
    output_file = STAGING_DIR / "weather.csv"

    df.to_csv(
        output_file,
        index=False
    )

    print("Weather records:", len(df))
    print("Staging weather data saved to:", output_file)


if __name__ == "__main__":
    clean_weather_data()