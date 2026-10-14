"""Reusable feature pipeline for AQI forecasting (Part 2).

Forecasting target (documented, UTC):
    For each station and each hourly observation timestamp T (floored to the
    hour, UTC), the regression target is the AQI observed at approximately
    T + 24 hours (within +/- TARGET_TOLERANCE_HOURS). The classification
    target is the CPCB category of that AQI value. Rows without an
    observation in the target window are dropped and counted -- the pipeline
    never silently substitutes the next available observation.

Location generalisation:
    Raw ``station_id`` values and exact coordinates are NOT model features
    (they do not transfer to new stations and caused drift alerts). Each
    station maps to a coarse grid cell ``lat_gen / lon_gen`` obtained by
    rounding its OpenAQ coordinates to 1 decimal (~11 km). Every cell holds
    >= 2 stations in the current 10-station Bengaluru sample.

Leakage rules:
    * Rows are sorted per station; all lags/rolling use past rows only.
    * A lag value is kept only if its source timestamp is recent
      (gap <= LAG_MAX_AGE_HOURS); otherwise it is NaN and the row is dropped.
    * Rolling statistics use shift(1) series only (never the current row).
    * Weather features are omitted: the Open-Meteo fetch window (2026)
      does not overlap the historic OpenAQ window (2016-2025), so no
      valid prediction-time weather join exists. See docs/data_dictionary.md.

Usage:
    python3 src/features/build_features.py
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pandas as pd

GOLD_FILE = Path("data/gold/aqi_data.csv")
OUTPUT_FILE = Path("data/gold/ml_features.csv")
METADATA_FILE = Path("data/gold/ml_feature_metadata.json")

# --- Documented forecasting contract (single source of truth) ---
TIMEZONE = "UTC"
TARGET_HORIZON_HOURS = 24
TARGET_TOLERANCE_HOURS = 2
LAG_STEPS = [1, 2, 3]
LAG_MAX_AGE_HOURS = 24  # lag source must be within 24h of current row
ROLLING_WINDOWS = [3, 7]

FEATURE_COLUMNS = [
    "lat_gen",
    "lon_gen",
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
TARGET_TIMESTAMP_COL = "target_timestamp"

# Fallback public station coordinates (OpenAQ locations_*.json, Bengaluru).
# Used when the git-ignored raw landing zone is absent (e.g. fresh clone).
# Values are rounded to the generalised grid at load time.
STATION_COORDS_FALLBACK = {
    # Project Bengaluru stations (BTM Layout, Hebbal, Silk Board)
    101: (12.9128, 77.6092),
    102: (13.0339, 77.5913),
    103: (12.9172, 77.6227),
    # OpenAQ Bengaluru location IDs
    412: (13.0339, 77.51321111),
    594: (12.91281111, 77.60921944),
    797: (12.9773472, 77.57069722),
    2589: (12.9916694, 77.54583056),
    2592: (12.93890556, 77.69727222),
    5547: (12.9352049, 77.6814488),
    5548: (12.9135218, 77.5950804),
    5574: (12.9756843, 77.5660749),
    5607: (13.0270199, 77.494094),
    5644: (12.990328, 77.5431385),
}


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


def load_station_lookup() -> pd.DataFrame:
    """Return station_id -> (lat_gen, lon_gen) generalised grid.

    Prefers the raw OpenAQ locations file; falls back to the tracked
    STATION_COORDS_FALLBACK constant so fresh clones stay reproducible.
    """
    coords: dict[int, tuple[float, float]] = dict(STATION_COORDS_FALLBACK)
    files = sorted(glob.glob("data/raw/openaq/locations_*.json"))
    if files:
        try:
            recs = json.load(open(files[-1]))
            for r in recs:
                c = r.get("coordinates", {}) or {}
                if "latitude" in c and "longitude" in c:
                    coords[int(r["id"])] = (
                        float(c["latitude"]),
                        float(c["longitude"]),
                    )
        except Exception as exc:  # raw landing zone stays immutable; warn only
            print(f"WARNING: could not read {files[-1]}: {exc}; using fallback.")
    rows = [
        {
            "station_id": sid,
            "lat_gen": round(lat, 1),
            "lon_gen": round(lon, 1),
        }
        for sid, (lat, lon) in coords.items()
    ]
    return pd.DataFrame(rows)


def load_gold(path: Path = GOLD_FILE) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    # Standardise to UTC and floor to the hour (documented timezone).
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.floor("h")
    df = df.dropna(subset=["aqi"]).copy()
    df["aqi"] = pd.to_numeric(df["aqi"], errors="coerce")
    df = df.dropna(subset=["aqi"])
    df = df[df["aqi_category"] != "Unknown"]
    # One row per station+hour: average duplicates (none observed; guard anyway).
    df = df.groupby(["station_id", "timestamp"], as_index=False).agg(
        aqi=("aqi", "mean"),
        aqi_category=("aqi_category", "first"),
        city=("city", "first"),
    )
    df = df.sort_values(["station_id", "timestamp"]).reset_index(drop=True)
    return df


def add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp"], utc=True)
    df["hour"] = ts.dt.hour
    df["dayofweek"] = ts.dt.dayofweek
    df["month"] = ts.dt.month
    return df


def add_target_24h(group: pd.DataFrame) -> pd.DataFrame:
    """Set target = AQI at T+24h (+/- tolerance), nearest match only."""
    sid = group["station_id"].iloc[0] if "station_id" in group.columns else getattr(group, "name", None)
    group = group.sort_values("timestamp").copy().reset_index(drop=True)
    if sid is not None and "station_id" not in group.columns:
        group["station_id"] = sid
    lookup = group.set_index("timestamp")["aqi"]
    horizon = pd.Timedelta(hours=TARGET_HORIZON_HOURS)
    tol = pd.Timedelta(hours=TARGET_TOLERANCE_HOURS)
    tgt_aqi, tgt_ts = [], []
    for ts in group["timestamp"]:
        window = lookup.loc[ts + horizon - tol : ts + horizon + tol]
        if len(window) == 0:
            tgt_aqi.append(float("nan"))
            tgt_ts.append(pd.NaT)
        else:  # nearest to exactly +24h; never crosses stations (per-group)
            nearest = min(window.index, key=lambda t: abs((t - ts) - horizon))
            tgt_aqi.append(float(window.loc[nearest]))
            tgt_ts.append(nearest)
    group[TARGET_REGRESSION] = tgt_aqi
    group[TARGET_TIMESTAMP_COL] = pd.to_datetime(tgt_ts, utc=True)
    group[TARGET_CLASSIFICATION] = group[TARGET_REGRESSION].apply(get_aqi_category)
    return group


def add_lag_rolling(group: pd.DataFrame) -> pd.DataFrame:
    """Past-only lags/rolling with staleness guards (no future leakage)."""
    sid = group["station_id"].iloc[0] if "station_id" in group.columns else getattr(group, "name", None)
    group = group.sort_values("timestamp").copy().reset_index(drop=True)
    if sid is not None and "station_id" not in group.columns:
        group["station_id"] = sid
    for lag in LAG_STEPS:
        src_ts = group["timestamp"].shift(lag)
        group[f"aqi_lag{lag}"] = group["aqi"].shift(lag)
        gap_h = (group["timestamp"] - src_ts).dt.total_seconds() / 3600.0
        # Stale source -> unusable at prediction time.
        group.loc[gap_h > LAG_MAX_AGE_HOURS, f"aqi_lag{lag}"] = float("nan")
    shifted = group["aqi"].shift(1)
    group["aqi_roll_mean_3"] = shifted.rolling(3, min_periods=3).mean()
    group["aqi_roll_std_3"] = shifted.rolling(3, min_periods=3).std().fillna(0.0)
    group["aqi_roll_mean_7"] = shifted.rolling(7, min_periods=3).mean()
    group["aqi_roll_max_7"] = shifted.rolling(7, min_periods=3).max()
    # Rolling over sparse history is only valid when the window is compact.
    span_3 = (group["timestamp"] - group["timestamp"].shift(3)).dt.total_seconds() / 3600.0
    span_7 = (group["timestamp"] - group["timestamp"].shift(7)).dt.total_seconds() / 3600.0
    group.loc[span_3 > 3 * 24, ["aqi_roll_mean_3", "aqi_roll_std_3"]] = float("nan")
    group.loc[span_7 > 10 * 24, ["aqi_roll_mean_7", "aqi_roll_max_7"]] = float("nan")
    group["aqi_diff_1"] = group["aqi"] - group["aqi_lag1"]
    return group


def build_features(
    input_path: Path = GOLD_FILE,
    output_path: Path = OUTPUT_FILE,
    metadata_path: Path = METADATA_FILE,
) -> pd.DataFrame:
    print(f"Loading gold data from {input_path} ...")
    df = load_gold(input_path)
    n_gold = len(df)
    print(f"Gold rows (valid AQI, hourly, UTC): {n_gold}")

    df = add_calendar(df)
    df = df.groupby("station_id", group_keys=False).apply(
        add_target_24h, include_groups=False
    )
    # groupby.apply may drop grouping cols; restore them.
    if "station_id" not in df.columns or "timestamp" not in df.columns:
        base = load_gold(input_path)
        base = add_calendar(base)
        base = base.sort_values(["station_id", "timestamp"]).reset_index(drop=True)
        for col in ("station_id", "timestamp", "aqi", "aqi_category", "city",
                    "hour", "dayofweek", "month"):
            if col not in df.columns and col in base.columns:
                df[col] = base[col].values[: len(df)]
    n_no_target = int(df[TARGET_REGRESSION].isna().sum())

    df = df.groupby("station_id", group_keys=False).apply(
        add_lag_rolling, include_groups=False
    )
    if "station_id" not in df.columns or "timestamp" not in df.columns:
        base = load_gold(input_path)
        base = add_calendar(base)
        base = base.sort_values(["station_id", "timestamp"]).reset_index(drop=True)
        for col in ("station_id", "timestamp", "aqi", "aqi_category", "city",
                    "hour", "dayofweek", "month",
                    TARGET_REGRESSION, TARGET_CLASSIFICATION, TARGET_TIMESTAMP_COL):
            if col not in df.columns and col in base.columns:
                df[col] = base[col].values[: len(df)]
            elif col not in df.columns and col in df.columns:
                pass

    # Generalised location join (no exact coords / station_id as feature).
    lookup = load_station_lookup()
    df = df.merge(lookup, on="station_id", how="left")
    n_unknown_station = int(df["lat_gen"].isna().sum())

    required = FEATURE_COLUMNS + [TARGET_REGRESSION]
    before = len(df)
    df = df.dropna(subset=required).reset_index(drop=True)
    n_dropped_features = before - len(df) - 0  # rows lacking lags/rolling/location

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    metadata = {
        "input_file": str(input_path),
        "output_file": str(output_path),
        "timezone": TIMEZONE,
        "target_definition": (
            f"AQI at T+{TARGET_HORIZON_HOURS}h +/-{TARGET_TOLERANCE_HOURS}h "
            f"(nearest, UTC, per station); missing targets dropped, never substituted"
        ),
        "target_timestamp_column": TARGET_TIMESTAMP_COL,
        "location_definition": "lat_gen/lon_gen = round(OpenAQ coords, 1 decimal, ~11km); station_id not a feature",
        "lag_policy": (
            f"shift(1,2,3) per station, past-only; source must be within "
            f"{LAG_MAX_AGE_HOURS}h else NaN"
        ),
        "rolling_policy": "shift(1)-based, min_periods=3; invalidated when window span too large",
        "weather_policy": "omitted — Open-Meteo 2026 window does not overlap OpenAQ 2016-2025",
        "n_gold_rows": int(n_gold),
        "n_rows_missing_target": int(n_no_target),
        "n_rows_unknown_station": int(n_unknown_station),
        "n_rows_dropped_incomplete": int(before - len(df)),
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
    }
    metadata_path.write_text(json.dumps(metadata, indent=2))
    print(f"ML features saved to {output_path} ({len(df)} rows)")
    print(f"  gold={n_gold}, no-target={n_no_target}, "
          f"unknown-station={n_unknown_station}, dropped-incomplete={before - len(df)}")
    print("Next-24h category distribution:")
    print(df[TARGET_CLASSIFICATION].value_counts())
    return df


if __name__ == "__main__":
    build_features()
