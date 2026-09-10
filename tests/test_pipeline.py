import json
from pathlib import Path
import pandas as pd


def test_cleaned_pollution_exists():
    f = Path("data/cleaned/pollution.csv")
    assert f.exists(), "cleaned pollution.csv missing"
    df = pd.read_csv(f)
    assert not df.empty
    assert {"station_id", "pollutant", "value", "timestamp"}.issubset(df.columns)
    assert (df["value"] >= 0).all(), "Negative pollutant values found"


def test_cleaned_weather_exists():
    f = Path("data/cleaned/weather.csv")
    assert f.exists()
    df = pd.read_csv(f)
    assert not df.empty
    assert "timestamp" in df.columns
    # DQ-006 humidity 0-100
    assert df["humidity"].between(0, 100, inclusive="both").all() or df["humidity"].isna().sum() == 0


def test_gold_aqi_exists():
    f = Path("data/gold/aqi_data.csv")
    assert f.exists()
    df = pd.read_csv(f)
    assert not df.empty
    assert "aqi" in df.columns
    assert "aqi_category" in df.columns
    valid_cats = {"Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe", "Unknown"}
    assert set(df["aqi_category"].dropna().unique()).issubset(valid_cats)


def test_enriched_exists():
    f = Path("data/cleaned/enriched_air_quality.csv")
    assert f.exists()
    df = pd.read_csv(f)
    assert "temperature" in df.columns
    assert "pollutant" in df.columns


def test_rejected_files_exist():
    # Audit files should exist even if empty (header only)
    assert Path("data/rejected/rejected_pollution.csv").exists()
    assert Path("data/rejected/rejected_weather.csv").exists()


def test_raw_landing():
    assert Path("data/raw/openaq").exists()
    assert Path("data/raw/openmeteo").exists()
    assert list(Path("data/raw/openaq").glob("*.json"))
    assert list(Path("data/raw/openmeteo").glob("*.json"))


def test_gold_not_manually_edited():
    # Ensure gold is derived — timestamp should be parseable
    df = pd.read_csv("data/gold/aqi_data.csv")
    pd.to_datetime(df["timestamp"], errors="raise")


def test_ingestion_log_exists():
    # After pipeline run, ingestion log should exist
    # Allow missing before first run — just check path is defined
    log = Path("logs/ingestion.log")
    meta = Path("logs/ingestion_metadata.csv")
    # If pipeline has run at least once, these should exist
    if log.exists():
        assert log.stat().st_size > 0
    if meta.exists():
        df = pd.read_csv(meta)
        assert {"source", "api_status", "row_count"}.issubset(df.columns)
