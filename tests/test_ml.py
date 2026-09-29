"""Part 2 tests: feature pipeline, training, FastAPI serving, monitoring."""

import json
from pathlib import Path

import joblib
import pandas as pd


FEATURES_FILE = Path("data/gold/ml_features.csv")
FEATURE_COLUMNS = [
    "station_id", "aqi", "aqi_lag1", "aqi_lag2", "aqi_lag3",
    "aqi_roll_mean_3", "aqi_roll_std_3", "aqi_roll_mean_7",
    "aqi_roll_max_7", "aqi_diff_1", "hour", "dayofweek", "month",
]


def test_ml_features_exist():
    assert FEATURES_FILE.exists(), "ml_features.csv missing"
    df = pd.read_csv(FEATURES_FILE)
    assert len(df) > 500, "too few feature rows"
    assert set(FEATURE_COLUMNS).issubset(df.columns)
    assert {"next_aqi", "next_category"}.issubset(df.columns)
    assert not df[FEATURE_COLUMNS + ["next_aqi"]].isna().any().any()


def test_chronological_split_order():
    from src.models.train import chronological_split

    df = pd.read_csv(FEATURES_FILE, parse_dates=["timestamp"])
    train, val, test = chronological_split(df)
    assert train["timestamp"].max() <= val["timestamp"].min()
    assert val["timestamp"].max() <= test["timestamp"].min()
    assert len(train) > len(val) and len(train) > len(test)


def test_models_exist_and_predict():
    from sklearn.metrics import f1_score, mean_squared_error

    reg = joblib.load("models/best_regressor.joblib")
    clf = joblib.load("models/best_classifier.joblib")
    df = pd.read_csv(FEATURES_FILE).tail(50)
    X = df[FEATURE_COLUMNS]
    rmse = mean_squared_error(df["next_aqi"], reg.predict(X)) ** 0.5
    f1 = f1_score(df["next_category"], clf.predict(X),
                  average="macro", zero_division=0)
    assert rmse < 60, f"RMSE too high: {rmse}"
    assert f1 > 0.30, f"F1 too low: {f1}"
    meta = json.loads(Path("models/model_metadata.json").read_text())
    assert meta["best_regressor"] and meta["best_classifier"]


def test_api_predict():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    payload = {
        "station_id": 412, "aqi": 62.0, "aqi_lag1": 58.0, "aqi_lag2": 55.0,
        "aqi_lag3": 60.0, "aqi_roll_mean_3": 57.0, "aqi_roll_std_3": 2.5,
        "aqi_roll_mean_7": 59.0, "aqi_roll_max_7": 70.0, "aqi_diff_1": 4.0,
        "hour": 10, "dayofweek": 1, "month": 3,
    }
    resp = client.post("/predict", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["predicted_aqi"] >= 0
    assert body["predicted_category"] in {
        "Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe",
    }


def test_monitoring_report():
    from src.monitoring.monitor import run_monitoring

    report = run_monitoring()
    assert Path("logs/monitoring_report.json").exists()
    assert "forecasting_error" in report
    assert "feature_drift" in report
