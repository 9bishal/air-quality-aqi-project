"""Model training pipeline for 24h-ahead AQI prediction (Part 2).

Target (see src/features/build_features.py): AQI at T+24h (+/-2h, UTC,
per station). Compares regression (AQI value) and classification
(AQI category) models on a chronological split and tracks with MLflow.

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
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

try:
    import mlflow
    import mlflow.sklearn

    MLFLOW_AVAILABLE = True
except ImportError:  # pragma: no cover
    MLFLOW_AVAILABLE = False

from src.features.build_features import (
    FEATURE_COLUMNS,
    TARGET_CLASSIFICATION as TARGET_CLF,
    TARGET_REGRESSION as TARGET_REG,
    TARGET_TIMESTAMP_COL,
    TIMEZONE,
    build_features,
)

FEATURES_FILE = Path("data/gold/ml_features.csv")
MODELS_DIR = Path("models")
EXPERIMENT_NAME = "aqi_prediction"


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
    labels = sorted(pd.unique(pd.concat([pd.Series(y_true), pd.Series(y_pred)])))
    cm = confusion_matrix(y_true, y_pred, labels=labels).tolist()
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
        "labels": labels,
        "confusion_matrix": cm,
    }


def train() -> dict:
    if not FEATURES_FILE.exists():
        print("ML features not found — building them first...")
        build_features()

    df = pd.read_csv(FEATURES_FILE, parse_dates=["timestamp"])
    assert set(FEATURE_COLUMNS).issubset(df.columns), (
        f"Feature schema drift: missing {set(FEATURE_COLUMNS) - set(df.columns)}"
    )
    train_df, val_df, test_df = chronological_split(df)
    print(
        f"Chronological split (UTC, no shuffle): train={len(train_df)} "
        f"val={len(val_df)} test={len(test_df)}"
    )
    print(
        f"Train period: {train_df['timestamp'].min()} → {train_df['timestamp'].max()}"
    )
    print(f"Val   period: {val_df['timestamp'].min()} → {val_df['timestamp'].max()}")
    print(f"Test  period: {test_df['timestamp'].min()} → {test_df['timestamp'].max()}")
    print("Test samples per station:")
    print(test_df.groupby("station_id").size().to_string())
    print("Test class balance:")
    print(test_df[TARGET_CLF].value_counts().to_string())

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

    # Preprocessing is fit on train only: linear models use a
    # StandardScaler pipeline; tree/dummy models use raw features.
    # The fitted pipeline is what gets saved, so serving needs no
    # separate preprocessing step.
    regressors = {
        "dummy_mean": DummyRegressor(strategy="mean"),
        "linear_regression": make_pipeline(StandardScaler(), LinearRegression()),
        "random_forest_regressor": RandomForestRegressor(
            n_estimators=200, random_state=42, n_jobs=-1
        ),
    }
    classifiers = {
        "dummy_most_frequent": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced")
        ),
        "random_forest_classifier": RandomForestClassifier(
            n_estimators=200, random_state=42, n_jobs=-1, class_weight="balanced"
        ),
    }

    if MLFLOW_AVAILABLE:
        mlflow.set_tracking_uri("sqlite:///mlflow.db")
        mlflow.set_experiment(EXPERIMENT_NAME)
    else:
        print("WARNING: mlflow not installed — logging to JSON only.")

    split_info = {
        "strategy": "chronological 70/15/15, no shuffle",
        "timezone": TIMEZONE,
        "train_period": [str(train_df["timestamp"].min()), str(train_df["timestamp"].max())],
        "val_period": [str(val_df["timestamp"].min()), str(val_df["timestamp"].max())],
        "test_period": [str(test_df["timestamp"].min()), str(test_df["timestamp"].max())],
        "train_stations": sorted(train_df["station_id"].unique().tolist()),
        "test_samples_per_station": test_df.groupby("station_id").size().to_dict(),
    }

    results: dict = {"regression": {}, "classification": {}}
    best_reg = {"name": None, "rmse": float("inf"), "model": None}
    best_clf = {"name": None, "f1": -1.0, "model": None}

    # ---- Regression (select on VALIDATION rmse) ----
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
                mlflow.log_param("target", f"{TARGET_REG} @T+24h")
                mlflow.log_dict(split_info, "split_info.json")
                try:
                    mlflow.log_params(model.get_params())
                except Exception:
                    pass
                mlflow.log_metrics({f"val_{k}": v for k, v in val_m.items()
                                    if isinstance(v, (int, float))})
                mlflow.log_metrics({f"test_{k}": v for k, v in test_m.items()
                                     if isinstance(v, (int, float))})
                _log_sklearn_model(model, name=name)
        if val_m["rmse"] < best_reg["rmse"]:
            best_reg = {"name": name, "rmse": val_m["rmse"], "model": model}

    # ---- Classification (select on VALIDATION f1_macro) ----
    for name, model in classifiers.items():
        model.fit(X_train, y_clf_train)
        val_pred = model.predict(X_val)
        test_pred = model.predict(X_test)
        val_m = classification_metrics(y_clf_val, val_pred)
        test_m = classification_metrics(y_clf_test, test_pred)
        results["classification"][name] = {"val": val_m, "test": test_m}
        print(f"[CLF] {name}: val_f1={val_m['f1_macro']:.3f} "
              f"test_f1={test_m['f1_macro']:.3f} test_acc={test_m['accuracy']:.3f}")
        if MLFLOW_AVAILABLE:
            with mlflow.start_run(run_name=f"clf_{name}"):
                mlflow.log_param("model", name)
                mlflow.log_param("task", "classification")
                mlflow.log_param("target", f"{TARGET_CLF} @T+24h")
                mlflow.log_dict(split_info, "split_info.json")
                mlflow.log_dict(
                    {"labels": test_m["labels"], "confusion_matrix": test_m["confusion_matrix"]},
                    "confusion_matrix_test.json",
                )
                try:
                    mlflow.log_params(model.get_params())
                except Exception:
                    pass
                mlflow.log_metrics({f"val_{k}": v for k, v in val_m.items()
                                    if isinstance(v, (int, float))})
                mlflow.log_metrics({f"test_{k}": v for k, v in test_m.items()
                                     if isinstance(v, (int, float))})
                _log_sklearn_model(model, name=name)
        if val_m["f1_macro"] > best_clf["f1"]:
            best_clf = {"name": name, "f1": val_m["f1_macro"], "model": model}

    # ---- Persist best models + registry via MLflow ----
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "target": "AQI @T+24h (+/-2h, UTC, per station)",
        "target_timestamp_column": TARGET_TIMESTAMP_COL,
        "feature_columns": FEATURE_COLUMNS,
        "target_regression": TARGET_REG,
        "target_classification": TARGET_CLF,
        "split": {
            "train": len(train_df),
            "val": len(val_df),
            "test": len(test_df),
            **split_info,
        },
        "best_regressor": best_reg["name"],
        "best_classifier": best_clf["name"],
        "model_versions": {},
        "results": results,
    }
    joblib.dump(best_reg["model"], MODELS_DIR / "best_regressor.joblib")
    joblib.dump(best_clf["model"], MODELS_DIR / "best_classifier.joblib")

    if MLFLOW_AVAILABLE:
        for task, info, reg_name in [
            ("regression", best_reg, "aqi_regressor"),
            ("classification", best_clf, "aqi_classifier"),
        ]:
            try:
                with mlflow.start_run(run_name=f"best_{task}_{info['name']}"):
                    mlflow.log_param("model", info["name"])
                    mlflow.log_param("task", f"best_{task}")
                    mlflow.log_dict(split_info, "split_info.json")
                    _log_sklearn_model(
                        info["model"],
                        name="model",
                        registered_model_name=reg_name,
                    )
                versions = mlflow.search_model_versions(f"name='{reg_name}'")
                if versions:
                    def _vnum(v):
                        try:
                            return int(v.version)
                        except (TypeError, ValueError):
                            return -1
                    latest = max(versions, key=_vnum)
                    metadata["model_versions"][reg_name] = {
                        "version": str(latest.version),
                        "status": str(latest.status),
                    }
                    print(f"Registered {reg_name} version {latest.version} ({latest.status})")
                else:
                    metadata["model_versions"][reg_name] = {"error": "no versions found"}
            except Exception as exc:
                print(f"WARNING: registry for {reg_name} failed: {exc}")
                metadata["model_versions"][reg_name] = {"error": str(exc)}
    (MODELS_DIR / "model_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"Best regressor: {best_reg['name']} (val RMSE={best_reg['rmse']:.3f})")
    print(f"Best classifier: {best_clf['name']} (val F1-macro={best_clf['f1']:.3f})")
    print(f"Models saved to {MODELS_DIR}/")
    return metadata


if __name__ == "__main__":
    train()
