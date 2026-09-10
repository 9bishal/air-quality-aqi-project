import logging
import pandas as pd
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "ingestion.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Input files from the staging layer
POLLUTION_FILE = Path("data/staging/pollution.csv")
WEATHER_FILE = Path("data/staging/weather.csv")

# Output folders
CLEANED_DIR = Path("data/cleaned")
REJECTED_DIR = Path("data/rejected")


def validate_pollution_data():
    logger.info("Validating pollution data...")

    # Load staging pollution data
    df = pd.read_csv(POLLUTION_FILE)

    # Normalize pollutant names and units (DQ-010)
    if "pollutant" in df.columns:
        df["pollutant"] = df["pollutant"].astype(str).str.lower().str.strip()
    if "unit" in df.columns:
        # Standardize to µg/m³ expected; keep original if unknown
        df["unit"] = df["unit"].astype(str).str.replace("Âµg", "µg", regex=False).str.strip()

    # Validate timestamp parseable (DQ-001)
    df["timestamp_parsed"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)

    # Store rejected records
    rejected_records = []

    # Check missing required fields
    missing_fields = (
        df["station_id"].isna()
        | df["station_name"].isna()
        | df["pollutant"].isna()
        | df["timestamp"].isna()
        | df["timestamp_parsed"].isna()
        | df["value"].isna()
    )

    rejected = df[missing_fields].copy()

    if not rejected.empty:
        rejected["error_reason"] = "Missing required field / invalid timestamp (DQ-001/DQ-002)"
        rejected_records.append(rejected)

    # Check for negative pollutant values (DQ-005)
    invalid_values = pd.to_numeric(df["value"], errors="coerce") < 0

    rejected = df[invalid_values].copy()

    if not rejected.empty:
        rejected["error_reason"] = "Negative pollutant value (DQ-005)"
        rejected_records.append(rejected)

    # Check pollutant valid range (upper bound sanity, e.g., PM2.5 > 1000 likely error)
    # Flag extreme outliers beyond CPCB max breakpoint + 20%
    extreme = pd.to_numeric(df["value"], errors="coerce") > 1000
    rejected_extreme = df[extreme].copy()
    if not rejected_extreme.empty:
        rejected_extreme["error_reason"] = "Extreme outlier value >1000 (DQ-005)"
        rejected_records.append(rejected_extreme)

    # Combine all rejected records
    if rejected_records:
        rejected_df = pd.concat(
            rejected_records
        ).drop_duplicates()

        valid_df = df.drop(
            rejected_df.index,
            errors="ignore"
        )
    else:
        rejected_df = pd.DataFrame()
        valid_df = df

    # Remove duplicate observations
    valid_df = valid_df.drop_duplicates(
        subset=[
            "station_id",
            "sensor_id",
            "pollutant",
            "timestamp"
        ]
    )

    # Drop helper column before saving
    if "timestamp_parsed" in df.columns:
        df = df.drop(columns=["timestamp_parsed"])
        if not rejected_df.empty and "timestamp_parsed" in rejected_df.columns:
            rejected_df = rejected_df.drop(columns=["timestamp_parsed"])
        valid_df = valid_df.drop(columns=["timestamp_parsed"], errors="ignore") if "timestamp_parsed" in valid_df.columns else valid_df

    logger.info("Total pollution records: %s", len(df))
    logger.info("Valid pollution records: %s", len(valid_df))
    logger.info("Rejected pollution records: %s", len(rejected_df))

    return valid_df, rejected_df


def validate_weather_data():
    logger.info("Validating weather data...")

    # Load staging weather data
    df = pd.read_csv(WEATHER_FILE)

    rejected_records = []

    # Check missing timestamps
    missing_timestamp = df["timestamp"].isna()

    rejected = df[missing_timestamp].copy()

    if not rejected.empty:
        rejected["error_reason"] = "Missing timestamp"
        rejected_records.append(rejected)

    # Check humidity range DQ-006
    invalid_humidity = ~pd.to_numeric(df["humidity"], errors="coerce").between(0, 100)

    rejected = df[invalid_humidity].copy()

    if not rejected.empty:
        rejected["error_reason"] = "Invalid humidity (DQ-006: 0-100)"
        rejected_records.append(rejected)

    # Check rainfall DQ-007
    invalid_rainfall = pd.to_numeric(df["rainfall"], errors="coerce") < 0

    rejected = df[invalid_rainfall].copy()

    if not rejected.empty:
        rejected["error_reason"] = "Negative rainfall (DQ-007)"
        rejected_records.append(rejected)

    # Check wind speed DQ-008
    invalid_wind = pd.to_numeric(df["wind_speed"], errors="coerce") < 0

    rejected = df[invalid_wind].copy()

    if not rejected.empty:
        rejected["error_reason"] = "Negative wind speed (DQ-008)"
        rejected_records.append(rejected)

    # Check temperature sanity (-50 to 60 Celsius)
    invalid_temp = ~pd.to_numeric(df["temperature"], errors="coerce").between(-50, 60)
    rejected = df[invalid_temp].copy()
    if not rejected.empty:
        rejected["error_reason"] = "Invalid temperature (-50 to 60)"
        rejected_records.append(rejected)

    # Combine rejected records
    if rejected_records:
        rejected_df = pd.concat(
            rejected_records
        ).drop_duplicates()

        valid_df = df.drop(
            rejected_df.index,
            errors="ignore"
        )
    else:
        rejected_df = pd.DataFrame()
        valid_df = df

    # Remove duplicate timestamps
    valid_df = valid_df.drop_duplicates(
        subset=["timestamp"]
    )

    logger.info("Total weather records: %s", len(df))
    logger.info("Valid weather records: %s", len(valid_df))
    logger.info("Rejected weather records: %s", len(rejected_df))

    return valid_df, rejected_df


def run_quality_checks():
    # Create output directories
    CLEANED_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    REJECTED_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # Validate pollution data
    pollution_df, rejected_pollution = (
        validate_pollution_data()
    )

    # Save valid pollution data
    pollution_df.to_csv(
        CLEANED_DIR / "pollution.csv",
        index=False
    )

    # Save rejected pollution records (always write header for audit)
    if not rejected_pollution.empty:
        rejected_pollution.to_csv(
            REJECTED_DIR / "rejected_pollution.csv",
            index=False
        )
    else:
        # Write empty file with header to prove check ran
        pd.DataFrame(columns=list(pollution_df.columns) + ["error_reason"]).to_csv(
            REJECTED_DIR / "rejected_pollution.csv", index=False
        )
        logger.info("No rejected pollution records — empty audit file created")

    # Validate weather data
    weather_df, rejected_weather = (
        validate_weather_data()
    )

    # Save valid weather data
    weather_df.to_csv(
        CLEANED_DIR / "weather.csv",
        index=False
    )

    # Save rejected weather records
    if not rejected_weather.empty:
        rejected_weather.to_csv(
            REJECTED_DIR / "rejected_weather.csv",
            index=False
        )
    else:
        pd.DataFrame(columns=list(weather_df.columns) + ["error_reason"]).to_csv(
            REJECTED_DIR / "rejected_weather.csv", index=False
        )
        logger.info("No rejected weather records — empty audit file created")

    logger.info("Data quality checks completed.")

    # Write summary to logs for execution evidence
    summary_file = Path("logs") / "validation_summary.log"
    with open(summary_file, "w") as f:
        f.write(f"Pollution: total validated, valid={len(pollution_df)}, rejected={len(rejected_pollution)}\n")
        f.write(f"Weather: total validated, valid={len(weather_df)}, rejected={len(rejected_weather)}\n")
        f.write(f"Run at: {pd.Timestamp.now().isoformat()}\n")


if __name__ == "__main__":
    run_quality_checks()