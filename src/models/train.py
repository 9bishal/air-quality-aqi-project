"""Model training pipeline for AQI prediction (Part 2).

Compares regression (next-AQI value) and classification (next-AQI category)
models using a chronological train/validation/test split and tracks
experiments with MLflow.

Usage:
    python3 src/models/train.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import joblib
import pandas as pd
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)

try:
    import mlflow
    import mlflow.sklearn

    MLFLOW_AVAILABLE = True
except ImportError:  # pragma: no cover
    MLFLOW_AVAILABLE = False

FEATURES_FILE = Path("data/gold/ml_features.csv")
MODELS_DIR = Path("models")
EXPERIMENT_NAME = "aqi_prediction"

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
TARGET_REG = "next_aqi"
TARGET_CLF = "next_category"


def _log_sklearn_model(model, name, registered_model_name=None):
    """MLflow 3.x uses skops for sklearn models; trust tree types we trained."""
    kwargs = {"skops_trusted_types": ["sklearn.tree._tree.Tree"]}
    if registered_model_name:
        kwargs["registered_model_name"] = registered_model_name
    mlflow.sklearn.log_model(model, name=name, **kwargs)


def chronological_split(
    df: pd.DataFrame, train_frac: float = 0.70, val_frac: float = 0.15
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split sorted-by-time dataframe chronologically (no shuffling)."""
    df = df.sort_values("timestamp").reset_index(drop=True)
    n = len(df)
    n_train = int(n * train_frac)
    n_val = int(n * val_frac)
    train = df.iloc[:n_train]
    val = df.iloc[n_train : n_train + n_val]
    test = df.iloc[n_train + n_val :]
    return train, val, test


def regression_metrics(y_true, y_pred) -> dict:
    rmse = float(mean_squared_error(y_true, y_pred) ** 0.5)
    return {
        "rmse": rmse,
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
    }


def classification_metrics(y_true, y_pred) -> dict:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(
            precision_score(y_true, y_pred, average="macro", zero_division=0)
        ),
        "recall_macro": float(
            recall_score(y_true, y_pred, average="macro", zero_division=0)
        ),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_weighted": float(
            f1_score(y_true, y_pred, average="weighted", zero_division=0)
        ),
    }


def train() -> dict:
    from src.features.build_features import build_features

    if not FEATURES_FILE.exists():
        print("ML features not found — building them first...")
        build_features()

    df = pd.read_csv(FEATURES_FILE, parse_dates=["timestamp"])
    train_df, val_df, test_df = chronological_split(df)
    print(
        f"Chronological split: train={len(train_df)} "
        f"val={len(val_df)} test={len(test_df)}"
    )
    print(
        f"Train period: {train_df['timestamp'].min()} → {train_df['timestamp'].max()}"
    )
    print(f"Test  period: {test_df['timestamp'].min()} → {test_df['timestamp'].max()}")

    X_train, y_reg_train, y_clf_train = (
        train_df[FEATURE_COLUMNS],
        train_df[TARGET_REG],
        train_df[TARGET_CLF],
    )
    X_val, y_reg_val, y_clf_val = (
        val_df[FEATURE_COLUMNS],
        val_df[TARGET_REG],
        val_df[TARGET_CLF],
    )
    X_test, y_reg_test, y_clf_test = (
        test_df[FEATURE_COLUMNS],
        test_df[TARGET_REG],
        test_df[TARGET_CLF],
    )

    regressors = {
        "dummy_mean": DummyRegressor(strategy="mean"),
        "linear_regression": LinearRegression(),
        "random_forest_regressor": RandomForestRegressor(
            n_estimators=200, random_state=42, n_jobs=-1
        ),
    }
    classifiers = {
        "dummy_most_frequent": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": LogisticRegression(max_iter=1000),
        "random_forest_classifier": RandomForestClassifier(
            n_estimators=200, random_state=42, n_jobs=-1, class_weight="balanced"
        ),
    }

    if MLFLOW_AVAILABLE:
        mlflow.set_tracking_uri("sqlite:///mlflow.db")
        mlflow.set_experiment(EXPERIMENT_NAME)
    else:
        print("WARNING: mlflow not installed — logging to JSON only.")

    results: dict = {"regression": {}, "classification": {}}
    best_reg = {"name": None, "rmse": float("inf"), "model": None}
    best_clf = {"name": None, "f1": -1.0, "model": None}

    # ---- Regression ----
    for name, model in regressors.items():
        model.fit(X_train, y_reg_train)
        val_pred = model.predict(X_val)
        test_pred = model.predict(X_test)
        val_m = regression_metrics(y_reg_val, val_pred)
        test_m = regression_metrics(y_reg_test, test_pred)
        results["regression"][name] = {"val": val_m, "test": test_m}
        print(f"[REG] {name}: val={val_m} test={test_m}")
        if MLFLOW_AVAILABLE:
            with mlflow.start_run(run_name=f"reg_{name}"):
                mlflow.log_param("model", name)
                mlflow.log_param("task", "regression")
                mlflow.log_params(getattr(model, "get_params", lambda: {})())
                mlflow.log_metrics({f"val_{k}": v for k, v in val_m.items()})
                mlflow.log_metrics({f"test_{k}": v for k, v in test_m.items()})
                _log_sklearn_model(model, name=name)
        if val_m["rmse"] < best_reg["rmse"]:
            best_reg = {"name": name, "rmse": val_m["rmse"], "model": model}

    # ---- Classification ----
    for name, model in classifiers.items():
        model.fit(X_train, y_clf_train)
        val_pred = model.predict(X_val)
        test_pred = model.predict(X_test)
        val_m = classification_metrics(y_clf_val, val_pred)
        test_m = classification_metrics(y_clf_test, test_pred)
        results["classification"][name] = {"val": val_m, "test": test_m}
        print(f"[CLF] {name}: val={val_m} test={test_m}")
        if MLFLOW_AVAILABLE:
            with mlflow.start_run(run_name=f"clf_{name}"):
                mlflow.log_param("model", name)
                mlflow.log_param("task", "classification")
                try:
                    mlflow.log_params(model.get_params())
                except Exception:
                    pass
                mlflow.log_metrics({f"val_{k}": v for k, v in val_m.items()})
                mlflow.log_metrics({f"test_{k}": v for k, v in test_m.items()})
                _log_sklearn_model(model, name=name)
        if val_m["f1_macro"] > best_clf["f1"]:
            best_clf = {"name": name, "f1": val_m["f1_macro"], "model": model}

    # ---- Persist best models + registry via MLflow ----
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_columns": FEATURE_COLUMNS,
        "target_regression": TARGET_REG,
        "target_classification": TARGET_CLF,
        "split": {"train": len(train_df), "val": len(val_df), "test": len(test_df)},
        "best_regressor": best_reg["name"],
        "best_classifier": best_clf["name"],
        "results": results,
    }
    joblib.dump(best_reg["model"], MODELS_DIR / "best_regressor.joblib")
    joblib.dump(best_clf["model"], MODELS_DIR / "best_classifier.joblib")

    if MLFLOW_AVAILABLE:
        for task, info, reg_name in [
            ("regression", best_reg, "aqi_regressor"),
            ("classification", best_clf, "aqi_classifier"),
        ]:
            with mlflow.start_run(run_name=f"best_{task}_{info['name']}"):
                mlflow.log_param("model", info["name"])
                mlflow.log_param("task", f"best_{task}")
                _log_sklearn_model(
                    info["model"],
                    name="model",
                    registered_model_name=reg_name,
                )
    (MODELS_DIR / "model_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"Best regressor: {best_reg['name']} (val RMSE={best_reg['rmse']:.3f})")
    print(f"Best classifier: {best_clf['name']} (val F1-macro={best_clf['f1']:.3f})")
    print(f"Models saved to {MODELS_DIR}/")
    return metadata


if __name__ == "__main__":
    train()
