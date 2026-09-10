import sys
from pathlib import Path

import pandas as pd


# Add the project root directory to Python's path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.database.connection import get_engine


# Input files
POLLUTION_FILE = PROJECT_ROOT / "data/cleaned/pollution.csv"
WEATHER_FILE = PROJECT_ROOT / "data/cleaned/weather.csv"
AQI_FILE = PROJECT_ROOT / "data/gold/aqi_data.csv"


def load_data():
    print("Starting database loading...")

    # Load cleaned pollution data
    pollution_df = pd.read_csv(POLLUTION_FILE)

    # Load cleaned weather data
    weather_df = pd.read_csv(WEATHER_FILE)

    # Load final AQI data
    aqi_df = pd.read_csv(AQI_FILE)

    # Create PostgreSQL connection
    engine = get_engine()

    try:
        # Load pollution data
        pollution_df.to_sql(
            "pollution",
            engine,
            if_exists="replace",
            index=False
        )

        # Load weather data
        weather_df.to_sql(
            "weather",
            engine,
            if_exists="replace",
            index=False
        )

        # Load AQI data
        aqi_df.to_sql(
            "aqi_data",
            engine,
            if_exists="replace",
            index=False
        )

        print("Pollution data loaded:", len(pollution_df))
        print("Weather data loaded:", len(weather_df))
        print("AQI data loaded:", len(aqi_df))

        print("Data loaded successfully into PostgreSQL.")

    except Exception as error:
        print("Failed to load data.")
        print("Error:", error)


if __name__ == "__main__":
    load_data()