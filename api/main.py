"""FastAPI inference service for AQI prediction (Part 2).

Serves the best regression (next-AQI value) and classification
(next-AQI category) models trained by src/models/train.py.

Run:
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "models"
METADATA_FILE = MODELS_DIR / "model_metadata.json"

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


def get_aqi_category(aqi: float) -> str:
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


class PredictionRequest(BaseModel):
    station_id: float = Field(examples=[412])
    aqi: float = Field(ge=0, le=1000, examples=[62.0])
    aqi_lag1: float = Field(ge=0, le=1000, examples=[58.0])
    aqi_lag2: float = Field(ge=0, le=1000, examples=[55.0])
    aqi_lag3: float = Field(ge=0, le=1000, examples=[60.0])
    aqi_roll_mean_3: float = Field(examples=[57.0])
    aqi_roll_std_3: float = Field(ge=0, examples=[2.5])
    aqi_roll_mean_7: float = Field(examples=[59.0])
    aqi_roll_max_7: float = Field(examples=[70.0])
    aqi_diff_1: float = Field(examples=[4.0])
    hour: int = Field(ge=0, le=23, examples=[10])
    dayofweek: int = Field(ge=0, le=6, examples=[1])
    month: int = Field(ge=1, le=12, examples=[3])


class PredictionResponse(BaseModel):
    predicted_aqi: float
    regressed_category: str
    predicted_category: str
    latency_ms: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_artifacts()
    yield


app = FastAPI(title="AQI Prediction API", version="1.0.0", lifespan=lifespan)

_regressor = None
_classifier = None
_metadata: dict = {}


def _load_artifacts() -> None:
    global _regressor, _classifier, _metadata
    reg_path = MODELS_DIR / "best_regressor.joblib"
    clf_path = MODELS_DIR / "best_classifier.joblib"
    if not reg_path.exists() or not clf_path.exists():
        raise FileNotFoundError(
            f"Model artifacts not found in {MODELS_DIR}. "
            "Run `python3 src/models/train.py` first."
        )
    _regressor = joblib.load(reg_path)
    _classifier = joblib.load(clf_path)
    if METADATA_FILE.exists():
        _metadata = json.loads(METADATA_FILE.read_text())


def _ensure_loaded() -> None:
    if _regressor is None or _classifier is None:
        _load_artifacts()


@app.get("/health")
def health() -> dict:
    _ensure_loaded()
    return {"status": "ok"}


@app.get("/model-info")
def model_info() -> dict:
    _ensure_loaded()
    return {
        "best_regressor": _metadata.get("best_regressor"),
        "best_classifier": _metadata.get("best_classifier"),
        "feature_columns": FEATURE_COLUMNS,
        "results": _metadata.get("results", {}),
        "trained_at": _metadata.get("trained_at"),
    }


@app.post("/predict", response_model=PredictionResponse)
def predict(payload: PredictionRequest) -> PredictionResponse:
    _ensure_loaded()
    start = time.perf_counter()
    try:
        row = pd.DataFrame([[getattr(payload, c) for c in FEATURE_COLUMNS]],
                           columns=FEATURE_COLUMNS)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if row.isna().any().any():
        raise HTTPException(status_code=422, detail="Missing feature values.")
    predicted_aqi = float(_regressor.predict(row)[0])
    predicted_category = str(_classifier.predict(row)[0])
    latency_ms = (time.perf_counter() - start) * 1000.0
    return PredictionResponse(
        predicted_aqi=round(predicted_aqi, 2),
        regressed_category=get_aqi_category(predicted_aqi),
        predicted_category=predicted_category,
        latency_ms=round(latency_ms, 2),
    )
