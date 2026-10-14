"""Monitoring for the AQI MLOps pipeline (Part 2).

Checks:
  1. Missing data rate and invalid values in the latest feature table.
  2. Feature drift: shift in recent feature means vs. training baseline
     (robust to zero baselines via a floored denominator).
  3. Recent-holdout proxy error: RMSE / F1 of the registered models on the
     most recent chronological slice. NOTE: this evaluates a historical
     holdout, NOT live production performance -- it is labelled as such.
  4. Inference latency and failure rate via a sample prediction.
  5. Data coverage: row counts and station availability vs. baseline.

All failure modes (missing files, missing columns, missing artifacts)
produce a structured report with an error field instead of crashing.

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

from src.features.build_features import FEATURE_COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURES_FILE = PROJECT_ROOT / "data/gold/ml_features.csv"
GOLD_FILE = PROJECT_ROOT / "data/gold/aqi_data.csv"
MODELS_DIR = PROJECT_ROOT / "models"
REPORT_FILE = PROJECT_ROOT / "logs/monitoring_report.json"

# Alert thresholds (documented in docs/model_lifecycle.md)
MISSING_THRESHOLD = 0.05
DRIFT_THRESHOLD = 0.30  # relative mean shift (floored denominator)
RMSE_ALERT = 40.0
F1_ALERT = 0.50
LATENCY_ALERT_MS = 500.0
MIN_ROWS = 10


def check_missing(df: pd.DataFrame) -> dict:
    cols = [c for c in FEATURE_COLUMNS if c in df.columns]
    missing_cols = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if not cols:
        return {"error": "no feature columns present", "alert": True,
                "overall_missing_rate": 1.0, "per_feature": {},
                "missing_columns": missing_cols}
    rates = df[cols].isna().mean().to_dict()
    overall = float(df[cols].isna().mean().mean())
    out = {
        "overall_missing_rate": overall,
        "per_feature": {k: float(v) for k, v in rates.items()},
        "alert": overall > MISSING_THRESHOLD,
    }
    if missing_cols:
        out["missing_columns"] = missing_cols
        out["alert"] = True
    return out


def check_drift(df: pd.DataFrame) -> dict:
    """Recent 20% vs first 70% baseline; floored denominator for ~0 means."""
    cols = [c for c in FEATURE_COLUMNS if c in df.columns]
    n = len(df)
    if n < MIN_ROWS or not cols:
        return {"error": "insufficient rows/columns for drift",
                "worst_shift": 0.0, "alert": False,
                "relative_mean_shift": {}}
    baseline = df.iloc[: int(n * 0.7)][cols].mean(numeric_only=True)
    recent = df.iloc[int(n * 0.8):][cols].mean(numeric_only=True)
    drift = {}
    for col in cols:
        base = float(baseline[col])
        rec = float(recent[col])
        # Robust when baseline mean is zero/near-zero: floor + scale term.
        denom = max(abs(base), 0.1 * (abs(rec) + 1e-9), 1e-9)
        drift[col] = abs(rec - base) / denom
    worst = max(drift.values()) if drift else 0.0
    return {
        "relative_mean_shift": {k: float(v) for k, v in drift.items()},
        "worst_shift": float(worst),
        "alert": bool(worst > DRIFT_THRESHOLD),
        "note": "distribution shift within stored history; not live traffic",
    }


def check_holdout_proxy(df: pd.DataFrame) -> dict:
    """Historical-holdout proxy (NOT live production performance)."""
    from sklearn.metrics import f1_score, mean_squared_error

    for f in ("best_regressor.joblib", "best_classifier.joblib"):
        if not (MODELS_DIR / f).exists():
            return {"error": f"model artifact missing: {f}",
                    "recent_rmse": None, "recent_f1_macro": None,
                    "rmse_alert": False, "f1_alert": True, "n_evaluated": 0}
    if "next_aqi" not in df.columns or "next_category" not in df.columns:
        return {"error": "target columns missing", "recent_rmse": None,
                "recent_f1_macro": None, "rmse_alert": False,
                "f1_alert": True, "n_evaluated": 0}
    recent = df.sort_values("timestamp").iloc[-92:]  # ~= test-split size
    cols = [c for c in FEATURE_COLUMNS if c in recent.columns]
    X = recent[cols]
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
        "kind": "historical_holdout_proxy_not_live",
    }


def check_coverage(df: pd.DataFrame) -> dict:
    n = len(df)
    stations = sorted(df["station_id"].unique().tolist()) if "station_id" in df.columns else []
    return {
        "n_rows": n,
        "n_stations": len(stations),
        "stations": stations,
        "alert": bool(n < MIN_ROWS),
    }


def check_latency() -> dict:
    try:
        from api.main import FEATURE_COLUMNS as API_COLS
    except Exception as exc:
        return {"error": f"API schema import failed: {exc}",
                "latency_ms": None, "failures": 1, "latency_alert": True}
    reg_path = MODELS_DIR / "best_regressor.joblib"
    if not reg_path.exists():
        return {"error": "model artifact missing", "latency_ms": None,
                "failures": 1, "latency_alert": True}
    import numpy as np

    reg = joblib.load(reg_path)
    sample = pd.DataFrame([np.ones(len(API_COLS)) * 50.0], columns=API_COLS)
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
    checked_at = datetime.now(timezone.utc).isoformat()
    if not FEATURES_FILE.exists():
        report = {"checked_at": checked_at,
                  "error": f"features file missing: {FEATURES_FILE}",
                  "alerts": ["features_missing"],
                  "retraining_recommended": False}
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return report
    df = pd.read_csv(FEATURES_FILE, parse_dates=["timestamp"])
    if df.empty or len(df) < MIN_ROWS:
        report = {"checked_at": checked_at, "n_rows": int(len(df)),
                  "error": "insufficient rows for monitoring",
                  "alerts": ["insufficient_data"],
                  "retraining_recommended": False}
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return report
    missing = check_missing(df)
    drift = check_drift(df)
    holdout = check_holdout_proxy(df)
    coverage = check_coverage(df)
    inference = check_latency()
    report = {
        "checked_at": checked_at,
        "n_rows": int(len(df)),
        "missing_data": missing,
        "feature_drift": drift,
        "recent_holdout_proxy": holdout,
        "coverage": coverage,
        "inference": inference,
    }
    # Back-compat alias (older dashboard/tests read "forecasting_error").
    report["forecasting_error"] = holdout
    alerts = []
    for name in ("missing_data", "feature_drift", "recent_holdout_proxy",
                 "coverage", "inference"):
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
        holdout.get("rmse_alert")
        or holdout.get("f1_alert")
        or drift.get("alert")
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
