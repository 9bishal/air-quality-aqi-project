"""Reusable feature pipeline for AQI forecasting (Part 2).

Reads the Part-1 gold layer (data/gold/aqi_data.csv), builds lag and
rolling features per station, and writes an ML-ready table plus metadata.

Grain: one row per (station_id, timestamp) observation from the gold layer.
Target: next observation's AQI for the same station (shift(-1)), which is
the closest available proxy for "next-day AQI" given the sparse historic
record (see docs/model_lifecycle.md for the limitation).

Usage:
    python3 src/features/build_features.py
    python3 -c "from src.features.build_features import build_features; build_features()"
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

GOLD_FILE = Path("data/gold/aqi_data.csv")
OUTPUT_FILE = Path("data/gold/ml_features.csv")
METADATA_FILE = Path("data/gold/ml_feature_metadata.json")

LAG_STEPS = [1, 2, 3]
ROLLING_WINDOWS = [3, 7]

FEATURE_COLUMNS = [
    "station_id",
    "aqi",
    "aqi_lag1",
    "aqi_lag2",
    "aqi_lag3",
    "aqi_roll_mean_3",
    "aqi_roll_std_3",
    "aqi_roll_mean_7",
    "aqi_roll_max_7",
    "aqi_diff_1",
    "hour",
    "dayofweek",
    "month",
]

TARGET_REGRESSION = "next_aqi"
TARGET_CLASSIFICATION = "next_category"


def get_aqi_category(aqi: float) -> str:
    if pd.isna(aqi):
        return "Unknown"
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Satisfactory"
    if aqi <= 200:
        return "Moderate"
    if aqi <= 300:
        return "Poor"
    if aqi <= 400:
        return "Very Poor"
    return "Severe"


def load_gold(path: Path = GOLD_FILE) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.dropna(subset=["aqi"]).copy()
    df["aqi"] = pd.to_numeric(df["aqi"], errors="coerce")
    df = df.dropna(subset=["aqi"])
    # Drop rows with unusable category but keep valid AQI values
    df = df[df["aqi_category"] != "Unknown"]
    df = df.sort_values(["station_id", "timestamp"]).reset_index(drop=True)
    return df


def add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp"], utc=True)
    df["hour"] = ts.dt.hour
    df["dayofweek"] = ts.dt.dayofweek
    df["month"] = ts.dt.month
    return df


def add_lag_rolling(group: pd.DataFrame) -> pd.DataFrame:
    group = group.sort_values("timestamp").copy()
    for lag in LAG_STEPS:
        group[f"aqi_lag{lag}"] = group["aqi"].shift(lag)
    group["aqi_roll_mean_3"] = group["aqi"].shift(1).rolling(3, min_periods=3).mean()
    group["aqi_roll_std_3"] = (
        group["aqi"].shift(1).rolling(3, min_periods=3).std().fillna(0.0)
    )
    group["aqi_roll_mean_7"] = group["aqi"].shift(1).rolling(7, min_periods=3).mean()
    group["aqi_roll_max_7"] = group["aqi"].shift(1).rolling(7, min_periods=3).max()
    group["aqi_diff_1"] = group["aqi"] - group["aqi_lag1"]
    # Targets: next observation for the same station
    group[TARGET_REGRESSION] = group["aqi"].shift(-1)
    group[TARGET_CLASSIFICATION] = group[TARGET_REGRESSION].apply(get_aqi_category)
    return group


def build_features(
    input_path: Path = GOLD_FILE,
    output_path: Path = OUTPUT_FILE,
    metadata_path: Path = METADATA_FILE,
) -> pd.DataFrame:
    print(f"Loading gold data from {input_path} ...")
    df = load_gold(input_path)
    print(f"Gold rows (valid AQI): {len(df)}")

    df = add_calendar(df)
    df = (
        df.groupby("station_id", group_keys=False)
        .apply(add_lag_rolling, include_groups=False)
        .reset_index(drop=True)
    )
    # groupby.apply drops grouping cols when include_groups=False in some
    # pandas versions; restore station_id/timestamp/aqi if missing.
    if "station_id" not in df.columns or "timestamp" not in df.columns:
        base = load_gold(input_path)
        base = add_calendar(base)
        base = base.sort_values(["station_id", "timestamp"]).reset_index(drop=True)
        for col in ("station_id", "timestamp", "aqi", "aqi_category", "city",
                    "hour", "dayofweek", "month"):
            if col not in df.columns and col in base.columns:
                df[col] = base[col]

    before = len(df)
    df = df.dropna(
        subset=[
            "aqi_lag1", "aqi_lag2", "aqi_lag3",
            "aqi_roll_mean_3", "aqi_roll_mean_7", "aqi_roll_max_7",
            TARGET_REGRESSION,
        ]
    ).reset_index(drop=True)
    print(f"Dropped {before - len(df)} rows with incomplete lags/targets.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    metadata = {
        "input_file": str(input_path),
        "output_file": str(output_path),
        "n_rows": int(len(df)),
        "n_stations": int(df["station_id"].nunique()),
        "feature_columns": FEATURE_COLUMNS,
        "target_regression": TARGET_REGRESSION,
        "target_classification": TARGET_CLASSIFICATION,
        "lag_steps": LAG_STEPS,
        "rolling_windows": ROLLING_WINDOWS,
        "category_distribution": df[TARGET_CLASSIFICATION].value_counts().to_dict(),
        "timestamp_min": str(df["timestamp"].min()),
        "timestamp_max": str(df["timestamp"].max()),
        "note": "Targets are the next observation per station (shift(-1)); "
        "weather features unavailable because Open-Meteo fetch window "
        "(2026) does not overlap historic OpenAQ window.",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2))
    print(f"ML features saved to {output_path} ({len(df)} rows)")
    print(f"Metadata saved to {metadata_path}")
    print("Next-category distribution:")
    print(df[TARGET_CLASSIFICATION].value_counts())
    return df


if __name__ == "__main__":
    build_features()
