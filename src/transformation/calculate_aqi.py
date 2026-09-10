import pandas as pd
from pathlib import Path


# Input file
INPUT_FILE = Path("data/cleaned/enriched_air_quality.csv")

# Output directory
GOLD_DIR = Path("data/gold")


# Indian AQI breakpoints
# Format:
# (concentration_low, concentration_high, AQI_low, AQI_high)
BREAKPOINTS = {
    "pm25": [
        (0, 30, 0, 50),
        (31, 60, 51, 100),
        (61, 90, 101, 200),
        (91, 120, 201, 300),
        (121, 250, 301, 400),
        (251, 500, 401, 500)
    ],
    "pm10": [
        (0, 50, 0, 50),
        (51, 100, 51, 100),
        (101, 250, 101, 200),
        (251, 350, 201, 300),
        (351, 430, 301, 400),
        (431, 500, 401, 500)
    ],
    "no2": [
        (0, 40, 0, 50),
        (41, 80, 51, 100),
        (81, 180, 101, 200),
        (181, 280, 201, 300),
        (281, 400, 301, 400),
        (401, 800, 401, 500)
    ],
    "so2": [
        (0, 40, 0, 50),
        (41, 80, 51, 100),
        (81, 380, 101, 200),
        (381, 800, 201, 300),
        (801, 1600, 301, 400),
        (1601, 2400, 401, 500)
    ],
    "co": [
        (0, 1, 0, 50),
        (1.1, 2, 51, 100),
        (2.1, 10, 101, 200),
        (10.1, 17, 201, 300),
        (17.1, 34, 301, 400),
        (34.1, 50, 401, 500)
    ],
    "o3": [
        (0, 50, 0, 50),
        (51, 100, 51, 100),
        (101, 168, 101, 200),
        (169, 208, 201, 300),
        (209, 748, 301, 400),
        (749, 1000, 401, 500)
    ]
}


def calculate_sub_index(concentration, breakpoints):
    # Find the breakpoint containing the concentration
    for c_low, c_high, i_low, i_high in breakpoints:

        if c_low <= concentration <= c_high:

            # Linear interpolation formula
            sub_index = (
                (i_high - i_low)
                / (c_high - c_low)
            ) * (concentration - c_low) + i_low

            return round(sub_index)

    # Return missing value if concentration
    # is outside the supported range
    return None


def get_aqi_category(aqi):
    # Convert AQI value into an Indian AQI category
    if aqi <= 50:
        return "Good"
    elif aqi <= 100:
        return "Satisfactory"
    elif aqi <= 200:
        return "Moderate"
    elif aqi <= 300:
        return "Poor"
    elif aqi <= 400:
        return "Very Poor"
    else:
        return "Severe"


def calculate_aqi():
    print("Starting AQI calculation...")

    # Load enriched data
    df = pd.read_csv(INPUT_FILE)

    # Convert pollutant values to numbers
    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce"
    )

    # Store calculated sub-indices
    sub_indices = []

    # Process each pollutant
    for pollutant, breakpoints in BREAKPOINTS.items():

        # Select records for this pollutant
        pollutant_df = df[
            df["pollutant"] == pollutant
        ].copy()

        if pollutant_df.empty:
            continue

        # Calculate pollutant sub-index
        pollutant_df["sub_index"] = pollutant_df[
            "value"
        ].apply(
            lambda value: calculate_sub_index(
                value,
                breakpoints
            )
            if pd.notna(value)
            else None
        )

        sub_indices.append(
            pollutant_df[
                ["timestamp", "station_id", "pollutant", "sub_index"]
            ]
        )

    # Stop if no AQI pollutants are available
    if not sub_indices:
        print("No AQI pollutants found.")
        return

    # Combine pollutant sub-indices
    sub_index_df = pd.concat(
        sub_indices,
        ignore_index=True
    )

    # Find the highest sub-index for each timestamp and station
    aqi_df = (
        sub_index_df
        .groupby(
            ["station_id", "timestamp"],
            as_index=False
        )["sub_index"]
        .max()
    )

    # Rename sub-index to AQI
    aqi_df = aqi_df.rename(
        columns={"sub_index": "aqi"}
    )

    # Convert AQI to integer
    aqi_df["aqi"] = aqi_df["aqi"].round().astype("Int64")

    # Add AQI category
    aqi_df["aqi_category"] = aqi_df["aqi"].apply(
        lambda value: (
            get_aqi_category(value)
            if pd.notna(value)
            else "Unknown"
        )
    )

    # Add city information
    aqi_df["city"] = "Bengaluru"

    # Create gold directory
    GOLD_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # Save final AQI data
    output_file = GOLD_DIR / "aqi_data.csv"

    aqi_df.to_csv(
        output_file,
        index=False
    )

    print("AQI records created:", len(aqi_df))
    print("Gold data saved to:", output_file)

    print("\nAQI category distribution:")
    print(aqi_df["aqi_category"].value_counts())


if __name__ == "__main__":
    calculate_aqi()