"""FastAPI inference service for 24h-ahead AQI prediction (Part 2).

Serves the best regression (AQI value @T+24h) and classification
(AQI category @T+24h) models trained by src/models/train.py.

Feature schema is imported from src.features.build_features (single
source of truth) -- no second feature implementation lives here.

Run:
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features.build_features import (  # noqa: E402  single source of truth
    FEATURE_COLUMNS,
    TARGET_HORIZON_HOURS,
)

MODELS_DIR = PROJECT_ROOT / "models"
METADATA_FILE = MODELS_DIR / "model_metadata.json"

AQI_MIN, AQI_MAX = 0.0, 1000.0
CATEGORIES = {"Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"}


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


import math

class PredictionRequest(BaseModel):
    # Generalised grid cell (~11km), NOT exact coords / station_id.
    lat_gen: float = Field(ge=-90, le=90, examples=[13.0])
    lon_gen: float = Field(ge=-180, le=180, examples=[77.5])
    aqi: float = Field(ge=AQI_MIN, le=AQI_MAX, examples=[62.0])
    aqi_lag1: float = Field(ge=AQI_MIN, le=AQI_MAX, examples=[58.0])
    aqi_lag2: float = Field(ge=AQI_MIN, le=AQI_MAX, examples=[55.0])
    aqi_lag3: float = Field(ge=AQI_MIN, le=AQI_MAX, examples=[60.0])
    aqi_lag24: float = Field(ge=AQI_MIN, le=AQI_MAX, examples=[65.0])
    aqi_roll_mean_3: float = Field(examples=[57.0])
    aqi_roll_std_3: float = Field(ge=0, examples=[2.5])
    aqi_roll_mean_7: float = Field(examples=[59.0])
    aqi_roll_max_7: float = Field(examples=[70.0])
    aqi_diff_1: float = Field(examples=[4.0])
    hour: int = Field(ge=0, le=23, examples=[10])
    dayofweek: int = Field(ge=0, le=6, examples=[1])
    month: int = Field(ge=1, le=12, examples=[3])
    # Cyclical representations (optional in payload; calculated automatically if omitted)
    hour_sin: float | None = Field(default=None, examples=[-0.5])
    hour_cos: float | None = Field(default=None, examples=[-0.866])
    dayofweek_sin: float | None = Field(default=None, examples=[0.782])
    dayofweek_cos: float | None = Field(default=None, examples=[0.623])


class PredictionResponse(BaseModel):
    predicted_aqi: float
    regressed_category: str
    predicted_category: str
    horizon: str
    model_regressor: str | None
    model_classifier: str | None
    latency_ms: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_artifacts()
    yield


app = FastAPI(title="AQI Prediction API", version="2.0.0", lifespan=lifespan)

_regressor = None
_classifier = None
_metadata: dict = {}


def _load_artifacts() -> None:
    global _regressor, _classifier, _metadata
    reg_path = MODELS_DIR / "best_regressor.joblib"
    clf_path = MODELS_DIR / "best_classifier.joblib"
    missing = [p.name for p in (reg_path, clf_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Model artifacts missing in {MODELS_DIR}: {missing}. "
            "Run `python3 src/models/train.py` first (models/ is git-ignored "
            "and must be built before serving)."
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
    try:
        _ensure_loaded()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok"}


@app.get("/model-info")
def model_info() -> dict:
    try:
        _ensure_loaded()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "target": f"AQI @T+{TARGET_HORIZON_HOURS}h (+/-2h, UTC, per station)",
        "best_regressor": _metadata.get("best_regressor"),
        "best_classifier": _metadata.get("best_classifier"),
        "model_versions": _metadata.get("model_versions", {}),
        "feature_columns": FEATURE_COLUMNS,
        "trained_at": _metadata.get("trained_at"),
        "split": _metadata.get("split", {}),
    }


@app.post("/predict", response_model=PredictionResponse)
def predict(payload: PredictionRequest) -> PredictionResponse:
    try:
        _ensure_loaded()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    start = time.perf_counter()
    # Build dictionary of features conforming to FEATURE_COLUMNS
    feature_dict = {c: getattr(payload, c, None) for c in FEATURE_COLUMNS}
    # Auto-derive cyclical features if not explicitly provided
    if feature_dict.get("hour_sin") is None:
        feature_dict["hour_sin"] = math.sin(2.0 * math.pi * payload.hour / 24.0)
    if feature_dict.get("hour_cos") is None:
        feature_dict["hour_cos"] = math.cos(2.0 * math.pi * payload.hour / 24.0)
    if feature_dict.get("dayofweek_sin") is None:
        feature_dict["dayofweek_sin"] = math.sin(2.0 * math.pi * payload.dayofweek / 7.0)
    if feature_dict.get("dayofweek_cos") is None:
        feature_dict["dayofweek_cos"] = math.cos(2.0 * math.pi * payload.dayofweek / 7.0)

    row = pd.DataFrame([[feature_dict[c] for c in FEATURE_COLUMNS]], columns=FEATURE_COLUMNS)
    if row.isna().any().any():
        raise HTTPException(status_code=422, detail="Missing feature values.")
    predicted_aqi = float(_regressor.predict(row)[0])
    if not (AQI_MIN - 1e-6 <= predicted_aqi <= AQI_MAX + 500):
        raise HTTPException(status_code=500, detail="Model returned invalid AQI.")
    predicted_aqi = max(AQI_MIN, predicted_aqi)  # clip small negatives to 0
    predicted_category = str(_classifier.predict(row)[0])
    if predicted_category not in CATEGORIES:
        raise HTTPException(status_code=500, detail="Model returned invalid category.")
    latency_ms = (time.perf_counter() - start) * 1000.0
    return PredictionResponse(
        predicted_aqi=round(predicted_aqi, 2),
        regressed_category=get_aqi_category(predicted_aqi),
        predicted_category=predicted_category,
        horizon=f"+{TARGET_HORIZON_HOURS}h",
        model_regressor=_metadata.get("best_regressor"),
        model_classifier=_metadata.get("best_classifier"),
        latency_ms=round(latency_ms, 2),
    )
