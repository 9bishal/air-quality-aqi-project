import json
import pandas as pd
from pathlib import Path


# Location of raw Open-Meteo data
RAW_DIR = Path("data/raw/openmeteo")

# Location for staging weather data
STAGING_DIR = Path("data/staging")


def load_all_weather_data():
    files = sorted(list(RAW_DIR.glob("weather_*.json")))
    if not files:
        raise FileNotFoundError("No Open-Meteo raw data found.")
    dfs = []
    for f in files:
        with open(f, "r") as fl:
            try:
                data = json.load(fl)
                if "hourly" in data and "time" in data["hourly"]:
                    dfs.append(pd.DataFrame(data["hourly"]))
            except Exception as e:
                print(f"Warning: could not read {f}: {e}")
    if not dfs:
        raise ValueError("No valid hourly weather data found in raw files.")
    return pd.concat(dfs, ignore_index=True)


def clean_weather_data():
    print("Starting weather data transformation...")
    df = load_all_weather_data()

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