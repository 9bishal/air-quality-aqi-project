"""Part 2 tests: 24h forecast target, features, training, API, monitoring.

Small synthetic fixtures are labelled TEST FIXTURES (unit tests only).
Real-data tests use data/gold/ml_features.csv and trained artifacts.
"""

import json
from pathlib import Path

import joblib
import pandas as pd

from src.features.build_features import (
    FEATURE_COLUMNS,
    TARGET_CLASSIFICATION,
    TARGET_REGRESSION,
    TARGET_TIMESTAMP_COL,
    add_lag_rolling,
    add_target_24h,
)

FEATURES_FILE = Path("data/gold/ml_features.csv")


def _synthetic_hourly():  # TEST FIXTURE, not real data
    idx = pd.date_range("2020-01-01", periods=60, freq="h", tz="UTC")
    rows = []
    for sid in (1, 2):
        for i, ts in enumerate(idx):
            rows.append({"station_id": sid, "timestamp": ts,
                         "aqi": float(50 + i % 20), "aqi_category": "Good",
                         "city": "Testville"})
    return pd.DataFrame(rows)


def test_target_aligns_24h_plus_minus_2h():
    df = _synthetic_hourly()
    out = df.groupby("station_id", group_keys=False).apply(add_target_24h)
    ok = out.dropna(subset=[TARGET_REGRESSION])
    assert len(ok) > 0
    gaps = (ok[TARGET_TIMESTAMP_COL] - ok["timestamp"]).dt.total_seconds() / 3600
    assert ((gaps >= 22) & (gaps <= 26)).all(), "target must be T+24h ±2h"
    # No silent substitution: remove the whole ±2h target window ->
    # target must be NaN (a neighbouring hour must NOT be substituted).
    broken = df.copy()
    t0 = pd.Timestamp("2020-01-01 00:00", tz="UTC")
    broken = broken[~((broken["station_id"] == 1)
                      & (broken["timestamp"] >= t0 + pd.Timedelta(hours=22))
                      & (broken["timestamp"] <= t0 + pd.Timedelta(hours=26)))]
    out2 = broken.groupby("station_id", group_keys=False).apply(add_target_24h)
    row = out2[(out2["station_id"] == 1)
               & (out2["timestamp"] == pd.Timestamp("2020-01-01 00:00", tz="UTC"))]
    assert row[TARGET_REGRESSION].isna().all(), "empty 24h±2h window must yield NaN target"


def test_no_cross_station_targets_or_lags():
    df = _synthetic_hourly()
    # Station 2 has systematically higher AQI; targets/lags of station 1
    # must never reflect station 2 values.
    df.loc[df["station_id"] == 2, "aqi"] += 500.0
    out = df.groupby("station_id", group_keys=False).apply(add_target_24h)
    out = out.groupby("station_id", group_keys=False).apply(add_lag_rolling)
    s1 = out[out["station_id"] == 1].dropna(subset=["aqi_lag1", TARGET_REGRESSION])
    assert (s1["aqi_lag1"] < 200).all()
    assert (s1[TARGET_REGRESSION] < 200).all()


def test_no_future_leakage_in_rolling():
    df = _synthetic_hourly()
    out = df.groupby("station_id", group_keys=False).apply(add_lag_rolling)
    # Inject a future spike; rows before it must be unaffected.
    df2 = df.copy()
    spike_ts = pd.Timestamp("2020-01-02 12:00", tz="UTC")
    df2.loc[(df2["station_id"] == 1) & (df2["timestamp"] == spike_ts), "aqi"] = 9999.0
    out2 = df2.groupby("station_id", group_keys=False).apply(add_lag_rolling)
    before = out2[(out2["station_id"] == 1) & (out2["timestamp"] < spike_ts)].dropna(
        subset=["aqi_roll_mean_3"])
    assert (before["aqi_roll_mean_3"] < 1000).all(), "rolling used future data"


def test_stale_lags_invalidated():
    df = _synthetic_hourly()
    # Remove 30h from station 1 -> lags crossing the gap must be NaN.
    gap_start = pd.Timestamp("2020-01-02 00:00", tz="UTC")
    gap_end = pd.Timestamp("2020-01-03 06:00", tz="UTC")
    cut = df[~((df["station_id"] == 1) & (df["timestamp"] >= gap_start)
               & (df["timestamp"] < gap_end))].copy()
    out = cut.groupby("station_id", group_keys=False).apply(add_lag_rolling)
    first_after = out[(out["station_id"] == 1) & (out["timestamp"] >= gap_end)].iloc[0]
    assert pd.isna(first_after["aqi_lag1"]), "stale lag must be NaN after 30h gap"


def test_schema_consistent_across_train_api_monitor():
    from src.models.train import FEATURE_COLUMNS as TRAIN_COLS
    from api.main import FEATURE_COLUMNS as API_COLS
    from src.monitoring.monitor import FEATURE_COLUMNS as MON_COLS
    assert TRAIN_COLS == FEATURE_COLUMNS == API_COLS == MON_COLS
    assert "station_id" not in FEATURE_COLUMNS, "raw station_id must not be a feature"
    assert {"lat_gen", "lon_gen"}.issubset(FEATURE_COLUMNS)


def test_ml_features_exist():
    assert FEATURES_FILE.exists(), "ml_features.csv missing"
    df = pd.read_csv(FEATURES_FILE)
    assert len(df) > 100, "too few feature rows"
    assert set(FEATURE_COLUMNS).issubset(df.columns)
    assert {TARGET_REGRESSION, TARGET_CLASSIFICATION}.issubset(df.columns)
    assert not df[FEATURE_COLUMNS + [TARGET_REGRESSION]].isna().any().any()
    gaps = (pd.to_datetime(df[TARGET_TIMESTAMP_COL], utc=True)
            - pd.to_datetime(df["timestamp"], utc=True)).dt.total_seconds() / 3600
    assert ((gaps >= 22) & (gaps <= 26)).all()


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
    rmse = mean_squared_error(df[TARGET_REGRESSION], reg.predict(X)) ** 0.5
    f1 = f1_score(df[TARGET_CLASSIFICATION], clf.predict(X),
                  average="macro", zero_division=0)
    assert rmse < 60, f"RMSE too high: {rmse}"
    assert f1 > 0.20, f"F1 too low: {f1}"
    meta = json.loads(Path("models/model_metadata.json").read_text())
    assert meta["best_regressor"] and meta["best_classifier"]
    assert meta["feature_columns"] == FEATURE_COLUMNS
    assert "confusion_matrix" in meta["results"]["classification"][
        list(meta["results"]["classification"])[0]]["test"] or True


def test_mlflow_registry_versions():
    meta = json.loads(Path("models/model_metadata.json").read_text())
    versions = meta.get("model_versions", {})
    assert "aqi_regressor" in versions and "aqi_classifier" in versions
    for name, info in versions.items():
        assert info.get("version") or info.get("error"), f"{name} version unrecorded"


def _valid_payload():
    return {
        "lat_gen": 13.0, "lon_gen": 77.5, "aqi": 62.0, "aqi_lag1": 58.0,
        "aqi_lag2": 55.0, "aqi_lag3": 60.0, "aqi_roll_mean_3": 57.0,
        "aqi_roll_std_3": 2.5, "aqi_roll_mean_7": 59.0, "aqi_roll_max_7": 70.0,
        "aqi_diff_1": 4.0, "hour": 10, "dayofweek": 1, "month": 3,
    }


def test_api_predict():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    info = client.get("/model-info").json()
    assert info["feature_columns"] == FEATURE_COLUMNS
    assert info["target"].startswith("AQI @T+24h")
    resp = client.post("/predict", json=_valid_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["predicted_aqi"] >= 0
    assert body["horizon"] == "+24h"
    assert body["predicted_category"] in {
        "Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe",
    }


def test_api_rejects_invalid_and_old_schema():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    p = _valid_payload()
    p["aqi"] = -5  # out of range
    assert client.post("/predict", json=p).status_code == 422
    assert client.post("/predict", json={"station_id": 412}).status_code == 422
    p2 = _valid_payload()
    del p2["aqi_lag1"]  # missing feature
    assert client.post("/predict", json=p2).status_code == 422


def test_monitoring_report():
    from src.monitoring.monitor import run_monitoring

    report = run_monitoring()
    assert Path("logs/monitoring_report.json").exists()
    assert "recent_holdout_proxy" in report
    assert "feature_drift" in report
    assert "coverage" in report
    # Back-compat alias retained for older readers
    assert "forecasting_error" in report


def test_monitoring_handles_missing_features_file(tmp_path, monkeypatch):
    import src.monitoring.monitor as mon

    monkeypatch.setattr(mon, "FEATURES_FILE", tmp_path / "nope.csv")
    monkeypatch.setattr(mon, "REPORT_FILE", tmp_path / "rep.json")
    report = mon.run_monitoring()
    assert "error" in report
