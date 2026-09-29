"""Monitoring for the AQI MLOps pipeline (Part 2).

Checks:
  1. Missing data rate in the latest gold / feature tables.
  2. Feature drift: shift in recent feature means vs. training baseline.
  3. Forecasting error: RMSE / F1 of the registered models on the most
     recent chronological slice (serves as a proxy for live performance).
  4. Inference latency and failure rate via a sample prediction.

Writes logs/monitoring_report.json and prints a summary.

Usage:
    python3 src/monitoring/monitor.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import joblib
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURES_FILE = PROJECT_ROOT / "data/gold/ml_features.csv"
GOLD_FILE = PROJECT_ROOT / "data/gold/aqi_data.csv"
MODELS_DIR = PROJECT_ROOT / "models"
REPORT_FILE = PROJECT_ROOT / "logs/monitoring_report.json"

FEATURE_COLUMNS = [
    "station_id", "aqi", "aqi_lag1", "aqi_lag2", "aqi_lag3",
    "aqi_roll_mean_3", "aqi_roll_std_3", "aqi_roll_mean_7",
    "aqi_roll_max_7", "aqi_diff_1", "hour", "dayofweek", "month",
]

# Alert thresholds (documented in docs/model_lifecycle.md)
MISSING_THRESHOLD = 0.05
DRIFT_THRESHOLD = 0.30  # relative mean shift
RMSE_ALERT = 40.0
F1_ALERT = 0.50
LATENCY_ALERT_MS = 500.0


def check_missing(df: pd.DataFrame) -> dict:
    rates = df[FEATURE_COLUMNS].isna().mean().to_dict()
    overall = float(df[FEATURE_COLUMNS].isna().mean().mean())
    return {
        "overall_missing_rate": overall,
        "per_feature": {k: float(v) for k, v in rates.items()},
        "alert": overall > MISSING_THRESHOLD,
    }


def check_drift(df: pd.DataFrame) -> dict:
    """Compare the most recent 20% of rows against the first 70% baseline."""
    n = len(df)
    baseline = df.iloc[: int(n * 0.7)][FEATURE_COLUMNS].mean(numeric_only=True)
    recent = df.iloc[int(n * 0.8):][FEATURE_COLUMNS].mean(numeric_only=True)
    drift = {}
    for col in FEATURE_COLUMNS:
        base = float(baseline[col])
        rec = float(recent[col])
        denom = abs(base) if abs(base) > 1e-9 else 1.0
        drift[col] = abs(rec - base) / denom
    worst = max(drift.values())
    return {
        "relative_mean_shift": {k: float(v) for k, v in drift.items()},
        "worst_shift": float(worst),
        "alert": bool(worst > DRIFT_THRESHOLD),
    }


def check_performance(df: pd.DataFrame) -> dict:
    from sklearn.metrics import f1_score, mean_squared_error

    recent = df.sort_values("timestamp").iloc[-239:]  # same size as test split
    X = recent[FEATURE_COLUMNS]
    reg = joblib.load(MODELS_DIR / "best_regressor.joblib")
    clf = joblib.load(MODELS_DIR / "best_classifier.joblib")
    rmse = float(mean_squared_error(recent["next_aqi"], reg.predict(X)) ** 0.5)
    f1 = float(
        f1_score(recent["next_category"], clf.predict(X),
                 average="macro", zero_division=0)
    )
    return {
        "recent_rmse": rmse,
        "recent_f1_macro": f1,
        "rmse_alert": bool(rmse > RMSE_ALERT),
        "f1_alert": bool(f1 < F1_ALERT),
        "n_evaluated": int(len(recent)),
    }


def check_latency() -> dict:
    from api.main import FEATURE_COLUMNS as API_COLS
    import numpy as np

    reg = joblib.load(MODELS_DIR / "best_regressor.joblib")
    sample = pd.DataFrame(
        [np.ones(len(API_COLS)) * 50.0], columns=API_COLS
    )
    start = time.perf_counter()
    failures = 0
    try:
        reg.predict(sample)
    except Exception:
        failures = 1
    latency_ms = (time.perf_counter() - start) * 1000.0
    return {
        "latency_ms": float(latency_ms),
        "failures": failures,
        "latency_alert": bool(latency_ms > LATENCY_ALERT_MS or failures > 0),
    }


def run_monitoring() -> dict:
    df = pd.read_csv(FEATURES_FILE, parse_dates=["timestamp"])
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "n_rows": int(len(df)),
        "missing_data": check_missing(df),
        "feature_drift": check_drift(df),
        "forecasting_error": check_performance(df),
        "inference": check_latency(),
    }
    alerts = []
    for name in ("missing_data", "feature_drift", "forecasting_error", "inference"):
        section = report[name]
        triggered = any(
            v is True
            for k, v in section.items()
            if k == "alert" or k.endswith("_alert")
        )
        if triggered:
            alerts.append(name)
    report["alerts"] = alerts
    report["retraining_recommended"] = bool(
        report["forecasting_error"]["rmse_alert"]
        or report["forecasting_error"]["f1_alert"]
        or report["feature_drift"]["alert"]
    )
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if report["retraining_recommended"]:
        print("RETRAINING RECOMMENDED — see docs/model_lifecycle.md")
    else:
        print("No retraining triggered.")
    return report


if __name__ == "__main__":
    run_monitoring()
