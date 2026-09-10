import pandas as pd
from pathlib import Path


# Input files
POLLUTION_FILE = Path("data/cleaned/pollution.csv")
WEATHER_FILE = Path("data/cleaned/weather.csv")

# Output directory
OUTPUT_DIR = Path("data/cleaned")


def join_pollution_weather():
    print("Starting pollution and weather data join...")

    # Load cleaned pollution data
    pollution_df = pd.read_csv(POLLUTION_FILE)

    # Load cleaned weather data
    weather_df = pd.read_csv(WEATHER_FILE)

    # Convert timestamps to datetime
    pollution_df["timestamp"] = pd.to_datetime(
        pollution_df["timestamp"],
        utc=True
    )

    weather_df["timestamp"] = pd.to_datetime(
        weather_df["timestamp"]
    )

    # Convert weather time from Bengaluru time to UTC
    weather_df["timestamp"] = (
        weather_df["timestamp"]
        .dt.tz_localize("Asia/Kolkata")
        .dt.tz_convert("UTC")
    )

    # Round pollution timestamps to the nearest hour
    pollution_df["timestamp"] = (
        pollution_df["timestamp"]
        .dt.floor("h")
    )

    # Round weather timestamps to the hour
    weather_df["timestamp"] = (
        weather_df["timestamp"]
        .dt.floor("h")
    )

    # Join pollution and weather using timestamp
    enriched_df = pollution_df.merge(
        weather_df,
        on="timestamp",
        how="left"
    )

    # Add city information
    enriched_df["city"] = "Bengaluru"

    # Create output directory
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # Save enriched data
    output_file = (
        OUTPUT_DIR / "enriched_air_quality.csv"
    )

    enriched_df.to_csv(
        output_file,
        index=False
    )

    print("Pollution records:", len(pollution_df))
    print("Weather records:", len(weather_df))
    print("Enriched records:", len(enriched_df))
    print("Enriched data saved to:", output_file)


if __name__ == "__main__":
    join_pollution_weather()