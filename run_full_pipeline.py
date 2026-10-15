"""Master Orchestrator for the Complete Bengaluru AQI Data and ML Pipeline.

Executes the complete workflow in strict dependency order:
1. Determine incremental ingestion window using checkpoints (or CLI range).
2. Fetch new pollution observations (OpenAQ v3) and weather data (Open-Meteo).
3. Validate and persist raw data (idempotent, deduplicated).
4. Run cleaning and quality checks (clean_pollution, clean_weather, quality_checks).
5. Run AQI and analytics transformations (join_data, calculate_aqi).
6. Rebuild ML feature dataset (build_features) with target/gap validation.
7. Validate feature and target integrity.
8. Train and evaluate regression and classification models (train).
9. Log parameters, metrics, and artifacts to MLflow.
10. Register / promote model versions only if validation criteria pass.
11. Run regression tests and produce concise execution summary.

CLI Flags:
  --dry-run          Inspect planned ingestion window and pipeline actions without writing or training.
  --start DATE       Explicit historical start date (YYYY-MM-DD) for backfill.
  --end DATE         Explicit historical end date (YYYY-MM-DD) for backfill.
  --skip-ingestion   Process existing data and train only.
  --skip-training    Update data, transformations, and features without retraining or promoting models.

Usage:
  python run_full_pipeline.py
  python run_full_pipeline.py --dry-run
  python run_full_pipeline.py --start 2026-09-01 --end 2026-10-14
  python run_full_pipeline.py --skip-ingestion
  python run_full_pipeline.py --skip-training
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

# -----------------------------------------------------------------------------
# Configuration & Constants
# -----------------------------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINT_FILE = LOG_DIR / "ingestion_checkpoint.json"
ORCHESTRATOR_LOG = LOG_DIR / "orchestrator.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(ORCHESTRATOR_LOG, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("run_full_pipeline")

RAW_OPENAQ_DIR = Path("data/raw/openaq")
RAW_WEATHER_DIR = Path("data/raw/openmeteo")
RAW_OPENAQ_DIR.mkdir(parents=True, exist_ok=True)
RAW_WEATHER_DIR.mkdir(parents=True, exist_ok=True)

OPENAQ_API_KEY = os.getenv("OPENAQ_API_KEY")
OPENAQ_HEADERS = {"X-API-Key": OPENAQ_API_KEY} if OPENAQ_API_KEY else {}

# Key Bengaluru stations with active sensors
ELIGIBLE_STATIONS = [
    {"id": 5548, "name": "BTM Layout, Bengaluru - CPCB", "lat": 12.9135, "lon": 77.5951},
    {"id": 5607, "name": "Peenya, Bengaluru - CPCB", "lat": 13.0270, "lon": 77.4941},
    {"id": 5644, "name": "Sanegurava Halli, Bengaluru - KSPCB", "lat": 12.9903, "lon": 77.5431},
    {"id": 6973, "name": "Jayanagar 5th Block, Bengaluru - KSPCB", "lat": 12.9210, "lon": 77.5849},
]
POLLUTANTS_OF_INTEREST = {"pm25", "pm10", "no2", "so2", "co", "o3"}

# Overlap buffer to capture delayed or corrected sensor transmissions
LOOKBACK_HOURS = 2


# -----------------------------------------------------------------------------
# Checkpoint Management
# -----------------------------------------------------------------------------
def load_checkpoint() -> Dict[str, Any]:
    """Load ingestion checkpoint metadata, or return default empty state."""
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            logger.warning("Could not read checkpoint file %s: %s", CHECKPOINT_FILE, exc)
    return {}


def determine_initial_checkpoint_from_raw() -> Dict[str, Any]:
    """Scan existing raw files to establish the last successfully ingested timestamps."""
    station_max: Dict[str, str] = {}
    weather_max: Optional[str] = None

    # Scan OpenAQ raw files
    raw_p_files = glob.glob(str(RAW_OPENAQ_DIR / "measurements_*.json"))
    for pf in raw_p_files:
        try:
            with open(pf, "r", encoding="utf-8") as f:
                records = json.load(f)
                if isinstance(records, list):
                    for rec in records:
                        sid = str(rec.get("location_id") or "")
                        dt_str = rec.get("period", {}).get("datetimeFrom", {}).get("utc")
                        if sid and dt_str:
                            if sid not in station_max or dt_str > station_max[sid]:
                                station_max[sid] = dt_str
        except Exception:
            pass

    # Scan Open-Meteo raw files
    raw_w_files = glob.glob(str(RAW_WEATHER_DIR / "weather_*.json"))
    for wf in raw_w_files:
        try:
            with open(wf, "r", encoding="utf-8") as f:
                wdata = json.load(f)
                times = wdata.get("hourly", {}).get("time", [])
                for t in times:
                    # open-meteo hourly format: YYYY-MM-DDTHH:MM (local Asia/Kolkata)
                    if weather_max is None or t > weather_max:
                        weather_max = t
        except Exception:
            pass

    overall_max = max(station_max.values()) if station_max else None
    return {
        "last_success_utc": overall_max,
        "stations": station_max,
        "weather_last_time": weather_max,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "initialized_from_raw": True,
    }


def get_effective_checkpoint() -> Dict[str, Any]:
    """Return stored checkpoint, or initialize from raw data if missing."""
    cp = load_checkpoint()
    if not cp or not cp.get("last_success_utc"):
        logger.info("No checkpoint file found; initializing baseline from existing raw files...")
        cp = determine_initial_checkpoint_from_raw()
    return cp


def save_checkpoint(
    checkpoint: Dict[str, Any],
    new_measurements: Optional[List[Dict[str, Any]]] = None,
    new_weather: Optional[Dict[str, Any]] = None,
) -> None:
    """Safely update and persist ingestion checkpoint."""
    updated = dict(checkpoint)
    updated["updated_at"] = datetime.now(timezone.utc).isoformat()
    if "stations" not in updated:
        updated["stations"] = {}

    if new_measurements:
        for m in new_measurements:
            sid = str(m.get("location_id") or "")
            dt_str = m.get("period", {}).get("datetimeFrom", {}).get("utc")
            if sid and dt_str:
                if sid not in updated["stations"] or dt_str > updated["stations"][sid]:
                    updated["stations"][sid] = dt_str
        if updated["stations"]:
            updated["last_success_utc"] = max(updated["stations"].values())

    if new_weather and "hourly" in new_weather:
        times = new_weather.get("hourly", {}).get("time", [])
        if times:
            max_w = max(times)
            if not updated.get("weather_last_time") or max_w > updated["weather_last_time"]:
                updated["weather_last_time"] = max_w

    temp_path = CHECKPOINT_FILE.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2)
    os.replace(temp_path, CHECKPOINT_FILE)
    logger.info("Persisted ingestion checkpoint: last_success_utc=%s", updated.get("last_success_utc"))


# -----------------------------------------------------------------------------
# Ingestion Logic (Incremental & Range-Based)
# -----------------------------------------------------------------------------
def request_openaq_with_retry(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
    timeout: int = 30,
) -> Optional[requests.Response]:
    """OpenAQ v3 GET with exponential backoff on HTTP 429 / transient network error."""
    for attempt in range(1, max_retries + 1):
        try:
            res = requests.get(url, headers=OPENAQ_HEADERS, params=params, timeout=timeout)
            if res.status_code == 200:
                return res
            if res.status_code == 429:
                wait_sec = attempt * 3
                logger.warning("OpenAQ rate limit hit (429) on %s. Backing off %ss...", url, wait_sec)
                time.sleep(wait_sec)
            else:
                logger.warning("OpenAQ HTTP %s on %s: %s", res.status_code, url, res.text[:100])
                time.sleep(attempt)
        except requests.RequestException as exc:
            logger.warning("OpenAQ network error (attempt %s) for %s: %s", attempt, url, exc)
            time.sleep(attempt * 2)
    return None


def fetch_openaq_for_station(
    station_id: int,
    station_name: str,
    date_from_iso: str,
    date_to_iso: str,
    max_pages_per_sensor: int = 25,
) -> List[Dict[str, Any]]:
    """Retrieve measurements for all active target sensors at a station."""
    sensors_url = f"https://api.openaq.org/v3/locations/{station_id}/sensors"
    res = request_openaq_with_retry(sensors_url)
    if not res:
        logger.error("Failed to fetch sensors for station %s (%s)", station_name, station_id)
        return []

    sensors = res.json().get("results", [])
    measurements: List[Dict[str, Any]] = []

    for s in sensors:
        sensor_id = s.get("id")
        param_info = s.get("parameter", {})
        param = param_info.get("name") if isinstance(param_info, dict) else str(param_info)

        if param not in POLLUTANTS_OF_INTEREST:
            continue

        page = 1
        while page <= max_pages_per_sensor:
            m_url = f"https://api.openaq.org/v3/sensors/{sensor_id}/measurements"
            params = {
                "datetime_from": date_from_iso,
                "datetime_to": date_to_iso,
                "limit": 100,
                "page": page,
            }
            m_res = request_openaq_with_retry(m_url, params=params)
            if not m_res:
                break
            batch = m_res.json().get("results", [])
            if not batch:
                break

            for rec in batch:
                rec["location_id"] = station_id
                rec["location_name"] = station_name
                rec["sensor_id"] = sensor_id
                measurements.append(rec)

            if len(batch) < 100:
                break
            page += 1
            time.sleep(0.05)

    return measurements


def fetch_openmeteo_weather(
    start_date_str: str,
    end_date_str: str,
    use_archive: bool = False,
) -> Optional[Dict[str, Any]]:
    """Fetch hourly weather for Bengaluru via Open-Meteo."""
    if use_archive:
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": 12.9716,
            "longitude": 77.5946,
            "start_date": start_date_str,
            "end_date": end_date_str,
            "hourly": "temperature_2m,relative_humidity_2m,rain,wind_speed_10m",
            "timezone": "Asia/Kolkata",
        }
    else:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": 12.9716,
            "longitude": 77.5946,
            "past_days": 3,
            "forecast_days": 1,
            "hourly": "temperature_2m,relative_humidity_2m,rain,wind_speed_10m",
            "timezone": "Asia/Kolkata",
        }

    for attempt in range(1, 4):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            logger.warning("Open-Meteo HTTP %s: %s", r.status_code, r.text[:120])
            time.sleep(attempt)
        except requests.RequestException as exc:
            logger.warning("Open-Meteo error on attempt %s: %s", attempt, exc)
            time.sleep(attempt * 2)
    return None


def execute_ingestion(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Execute ingestion window calculation, fetch, raw persistence, and checkpointing."""
    now_utc = datetime.now(timezone.utc)
    checkpoint = get_effective_checkpoint()

    # Determine window
    if start_date and end_date:
        is_backfill = True
        fetch_from_iso = f"{start_date}T00:00:00Z"
        fetch_to_iso = f"{end_date}T23:59:59Z"
        logger.info("Explicit ingestion window requested: %s to %s", fetch_from_iso, fetch_to_iso)
    else:
        is_backfill = False
        last_success = checkpoint.get("last_success_utc")
        if last_success:
            # Parse last success and apply small lookback buffer for delayed records
            try:
                last_dt = datetime.fromisoformat(last_success.replace("Z", "+00:00"))
                buffered_start = max(last_dt - timedelta(hours=LOOKBACK_HOURS), last_dt - timedelta(days=7))
                fetch_from_iso = buffered_start.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                fetch_from_iso = (now_utc - timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z")
        else:
            fetch_from_iso = (now_utc - timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z")
        fetch_to_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.info("Incremental ingestion window determined: %s to %s (Lookback: %sh)",
                    fetch_from_iso, fetch_to_iso, LOOKBACK_HOURS)

    if dry_run:
        logger.info("[DRY RUN] Ingestion planned: window=[%s -> %s], stations=%s",
                    fetch_from_iso, fetch_to_iso, [s["id"] for s in ELIGIBLE_STATIONS])
        return {
            "status": "SKIPPED_DRY_RUN",
            "window": [fetch_from_iso, fetch_to_iso],
            "new_pollution_records": 0,
            "new_weather_records": 0,
            "is_backfill": is_backfill,
        }

    # Fetch OpenAQ measurements
    all_measurements: List[Dict[str, Any]] = []
    station_stats: Dict[int, int] = {}
    for st in ELIGIBLE_STATIONS:
        logger.info("Fetching OpenAQ observations for %s (%s)...", st["name"], st["id"])
        m = fetch_openaq_for_station(st["id"], st["name"], fetch_from_iso, fetch_to_iso)
        station_stats[st["id"]] = len(m)
        all_measurements.extend(m)
        logger.info("Received %s records for %s", len(m), st["name"])

    # Persist raw OpenAQ
    ts_tag = now_utc.strftime("%Y%m%d_%H%M%S")
    pollution_file = None
    if all_measurements:
        prefix = "measurements_backfill" if is_backfill else "measurements_incremental"
        pollution_file = RAW_OPENAQ_DIR / f"{prefix}_{ts_tag}.json"
        with open(pollution_file, "w", encoding="utf-8") as f:
            json.dump(all_measurements, f, indent=2)
        logger.info("Persisted %s raw measurements to %s", len(all_measurements), pollution_file)
    else:
        logger.info("No new pollution records returned by OpenAQ for the requested window.")

    # Fetch weather
    weather_start = fetch_from_iso[:10]
    weather_end = fetch_to_iso[:10]
    use_archive = is_backfill or (now_utc.date() - datetime.fromisoformat(fetch_from_iso.replace("Z", "+00:00")).date()).days > 2
    weather_data = fetch_openmeteo_weather(weather_start, weather_end, use_archive=use_archive)
    weather_file = None
    weather_hours_count = 0

    if weather_data and "hourly" in weather_data:
        weather_hours_count = len(weather_data.get("hourly", {}).get("time", []))
        prefix = "weather_archive_backfill" if is_backfill else "weather_incremental"
        weather_file = RAW_WEATHER_DIR / f"{prefix}_{ts_tag}.json"
        with open(weather_file, "w", encoding="utf-8") as f:
            json.dump(weather_data, f, indent=2)
        logger.info("Persisted %s weather hourly rows to %s", weather_hours_count, weather_file)

    # Persist checkpoint ONLY after successful disk write
    save_checkpoint(checkpoint, new_measurements=all_measurements, new_weather=weather_data)

    return {
        "status": "SUCCESS",
        "window": [fetch_from_iso, fetch_to_iso],
        "new_pollution_records": len(all_measurements),
        "new_weather_records": weather_hours_count,
        "station_stats": station_stats,
        "pollution_file": str(pollution_file) if pollution_file else None,
        "weather_file": str(weather_file) if weather_file else None,
        "is_backfill": is_backfill,
    }


# -----------------------------------------------------------------------------
# Pipeline Execution Helpers
# -----------------------------------------------------------------------------
def run_command_stage(step_name: str, cmd: List[str]) -> Tuple[bool, float, str]:
    """Execute a python subprocess stage, stream output, and verify exit code."""
    logger.info("==================================================")
    logger.info("STAGE: %s | STARTED", step_name)
    logger.info("Executing: %s", " ".join(cmd))
    start_time = time.time()

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    elapsed = round(time.time() - start_time, 2)

    if proc.returncode != 0:
        logger.error("STAGE: %s | FAILED (elapsed: %ss)", step_name, elapsed)
        logger.error("Standard Output:\n%s", proc.stdout)
        logger.error("Standard Error:\n%s", proc.stderr)
        return False, elapsed, proc.stderr

    logger.info("STAGE: %s | PASSED (elapsed: %ss)", step_name, elapsed)
    if proc.stdout:
        for line in proc.stdout.strip().split("\n")[-10:]:
            logger.info("  [%s] %s", step_name, line)
    return True, elapsed, proc.stdout


def trigger_airflow_dag(dag_id: str = "aqi_pipeline") -> Tuple[bool, str]:
    """Trigger the DAG in the Airflow docker container if available."""
    try:
        proc = subprocess.run(
            ["docker", "exec", "aqi_airflow", "airflow", "dags", "trigger", dag_id],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            logger.info("Airflow DAG '%s' triggered successfully via Docker container.", dag_id)
            return True, proc.stdout
        logger.warning("Failed to trigger Airflow DAG '%s': %s", dag_id, proc.stderr or proc.stdout)
        return False, proc.stderr or proc.stdout
    except Exception as exc:
        logger.warning("Could not reach Docker Airflow container: %s", exc)
        return False, str(exc)


# -----------------------------------------------------------------------------
# Main Orchestrator Workflow
# -----------------------------------------------------------------------------
def run_full_pipeline(
    dry_run: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    skip_ingestion: bool = False,
    skip_training: bool = False,
    skip_tests: bool = False,
    trigger_airflow: bool = True,
) -> Dict[str, Any]:
    """Master pipeline runner executing all stages end-to-end with fail-fast safety."""
    pipeline_start = time.time()
    py = sys.executable

    stage_timings: Dict[str, float] = {}
    summary: Dict[str, Any] = {
        "start_time": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "skip_ingestion": skip_ingestion,
        "skip_training": skip_training,
        "skip_tests": skip_tests,
        "stages": {},
    }

    print("\n" + "=" * 70)
    print("   BENGALURU AQI PIPELINE MASTER ORCHESTRATION")
    print(f"   Mode: {'DRY RUN' if dry_run else 'REAL EXECUTION'}")
    print(f"   Flags: skip_ingestion={skip_ingestion}, skip_training={skip_training}")
    print("=" * 70 + "\n")

    # -------------------------------------------------------------------------
    # Stage 1: Ingestion Window & Fetching
    # -------------------------------------------------------------------------
    if skip_ingestion:
        logger.info("STAGE: Ingestion | SKIPPED (--skip-ingestion requested)")
        summary["stages"]["ingestion"] = {"status": "SKIPPED"}
    else:
        logger.info("STAGE: Ingestion | STARTED")
        t0 = time.time()
        try:
            ingestion_res = execute_ingestion(start_date, end_date, dry_run=dry_run)
            t_elapsed = round(time.time() - t0, 2)
            stage_timings["ingestion"] = t_elapsed
            summary["stages"]["ingestion"] = {
                "status": "PASSED" if not dry_run else "SKIPPED_DRY_RUN",
                "duration_sec": t_elapsed,
                **ingestion_res,
            }
            logger.info("STAGE: Ingestion | %s (elapsed: %ss)",
                        summary["stages"]["ingestion"]["status"], t_elapsed)
        except Exception as exc:
            logger.error("STAGE: Ingestion | FAILED: %s", exc)
            summary["stages"]["ingestion"] = {"status": "FAILED", "error": str(exc)}
            raise RuntimeError(f"Ingestion failed: {exc}") from exc

    if dry_run:
        logger.info("[DRY RUN] Halting pipeline execution after planning stage.")
        summary["pipeline_status"] = "DRY_RUN_COMPLETED"
        return summary

    # -------------------------------------------------------------------------
    # Stage 2: Preprocessing & Data Cleaning
    # -------------------------------------------------------------------------
    for stage_name, script_path in [
        ("Clean Pollution", "src/transformation/clean_pollution.py"),
        ("Clean Weather", "src/transformation/clean_weather.py"),
        ("Quality Checks & Audit", "src/validation/quality_checks.py"),
    ]:
        ok, elapsed, out = run_command_stage(stage_name, [py, script_path])
        stage_timings[stage_name] = elapsed
        summary["stages"][stage_name] = {"status": "PASSED" if ok else "FAILED", "duration_sec": elapsed}
        if not ok:
            raise RuntimeError(f"Pipeline halted: Stage '{stage_name}' failed.")

    # -------------------------------------------------------------------------
    # Stage 3: Transformation & AQI Calculation
    # -------------------------------------------------------------------------
    for stage_name, script_path in [
        ("Join Pollution and Weather", "src/transformation/join_data.py"),
        ("Calculate CPCB AQI", "src/transformation/calculate_aqi.py"),
    ]:
        ok, elapsed, out = run_command_stage(stage_name, [py, script_path])
        stage_timings[stage_name] = elapsed
        summary["stages"][stage_name] = {"status": "PASSED" if ok else "FAILED", "duration_sec": elapsed}
        if not ok:
            raise RuntimeError(f"Pipeline halted: Stage '{stage_name}' failed.")

    # -------------------------------------------------------------------------
    # Stage 4: Feature Engineering
    # -------------------------------------------------------------------------
    ok, elapsed, out = run_command_stage("Rebuild ML Features", [py, "src/features/build_features.py"])
    stage_timings["build_features"] = elapsed
    summary["stages"]["build_features"] = {"status": "PASSED" if ok else "FAILED", "duration_sec": elapsed}
    if not ok:
        raise RuntimeError("Pipeline halted: Feature engineering failed.")

    # Verify feature integrity
    features_path = Path("data/gold/ml_features.csv")
    if not features_path.exists() or features_path.stat().st_size == 0:
        raise RuntimeError("Validation failure: data/gold/ml_features.csv is empty or missing.")

    feat_df = pd.read_csv(features_path)
    summary["feature_dataset_rows"] = len(feat_df)
    summary["feature_stations"] = [int(s) for s in feat_df["station_id"].unique()]
    summary["feature_date_range"] = [str(feat_df["timestamp"].min()), str(feat_df["timestamp"].max())]
    logger.info("ML Feature dataset verified: %s rows, stations=%s, range=%s",
                len(feat_df), summary["feature_stations"], summary["feature_date_range"])

    # -------------------------------------------------------------------------
    # Stage 5: Model Training & MLflow Logging
    # -------------------------------------------------------------------------
    if skip_training:
        logger.info("STAGE: Model Training | SKIPPED (--skip-training requested)")
        summary["stages"]["model_training"] = {"status": "SKIPPED"}
    else:
        ok, elapsed, out = run_command_stage("Model Training & MLflow", [py, "src/models/train.py"])
        stage_timings["model_training"] = elapsed
        summary["stages"]["model_training"] = {"status": "PASSED" if ok else "FAILED", "duration_sec": elapsed}
        if not ok:
            raise RuntimeError("Pipeline halted: Model training and validation failed.")

        # Read model metadata
        meta_file = Path("models/model_metadata.json")
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as mf:
                    meta_data = json.load(mf)
                    summary["models"] = {
                        "best_regressor": meta_data.get("best_regressor"),
                        "best_classifier": meta_data.get("best_classifier"),
                        "model_versions": meta_data.get("model_versions"),
                        "split": meta_data.get("split"),
                    }
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Stage 6: Regression Test Suite Verification
    # -------------------------------------------------------------------------
    if skip_tests:
        logger.info("STAGE: Automated Test Suite | SKIPPED (--skip-tests requested)")
        summary["stages"]["tests"] = {"status": "SKIPPED"}
    else:
        ok, elapsed, out = run_command_stage("Automated Test Suite", [py, "-m", "pytest", "tests/"])
        stage_timings["tests"] = elapsed
        summary["stages"]["tests"] = {"status": "PASSED" if ok else "FAILED", "duration_sec": elapsed}
        if not ok:
            raise RuntimeError("Pipeline halted: Automated tests failed.")

    total_pipeline_time = round(time.time() - pipeline_start, 2)
    summary["total_pipeline_duration_sec"] = total_pipeline_time
    summary["pipeline_status"] = "SUCCESS"

    try:
        summary["data_metrics"] = {
            "cleaned_pollution_rows": len(pd.read_csv("data/cleaned/pollution.csv", low_memory=False)),
            "cleaned_weather_rows": len(pd.read_csv("data/cleaned/weather.csv", low_memory=False)),
            "enriched_air_quality_rows": len(pd.read_csv("data/cleaned/enriched_air_quality.csv", low_memory=False)),
            "gold_aqi_rows": len(pd.read_csv("data/gold/aqi_data.csv", low_memory=False)),
            "ml_features_rows": len(pd.read_csv("data/gold/ml_features.csv", low_memory=False)),
        }
    except Exception:
        pass

    # Optional Stage 7: Trigger Apache Airflow DAG
    if trigger_airflow:
        logger.info("Triggering Apache Airflow DAG ('aqi_pipeline')...")
        dag_ok, dag_out = trigger_airflow_dag("aqi_pipeline")
        summary["stages"]["airflow_trigger"] = {
            "status": "PASSED" if dag_ok else "WARNING",
            "message": dag_out.strip() if dag_out else "",
        }

    print_final_summary(summary)
    return summary


def print_final_summary(summary: Dict[str, Any]) -> None:
    """Print clean executive summary table to stdout."""
    print("\n" + "=" * 70)
    print("           BENGALURU AQI PIPELINE EXECUTION SUMMARY")
    print("=" * 70)
    print(f"Overall Status:     {summary.get('pipeline_status')}")
    print(f"Total Duration:     {summary.get('total_pipeline_duration_sec')}s")
    print("-" * 70)
    print("STAGES:")
    for st_name, st_info in summary.get("stages", {}).items():
        status = st_info.get("status")
        dur = f"{st_info.get('duration_sec', 0.0)}s" if "duration_sec" in st_info else "N/A"
        print(f"  * {st_name:<30} [{status:<10}] in {dur}")

    if "data_metrics" in summary:
        print("-" * 70)
        print("DATASET ROW COUNTS:")
        for ds, count in summary["data_metrics"].items():
            print(f"  * {ds:<30}: {count:>8} rows")

    if "models" in summary:
        print("-" * 70)
        print("MODEL REGISTRY:")
        m = summary["models"]
        print(f"  * Best Regressor:   {m.get('best_regressor')}")
        print(f"  * Best Classifier:  {m.get('best_classifier')}")
        for reg_name, vinfo in m.get("model_versions", {}).items():
            print(f"  * Registered Model: {reg_name} (Version {vinfo.get('version')}, Status: {vinfo.get('status')})")

    print("=" * 70 + "\n")


# -----------------------------------------------------------------------------
# CLI Entry Point
# -----------------------------------------------------------------------------
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Master Orchestration Script for Bengaluru AQI Pipeline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect the planned ingestion window and pipeline actions without writing or training.",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Historical ingestion start date (YYYY-MM-DD). Must be paired with --end.",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="Historical ingestion end date (YYYY-MM-DD). Must be paired with --start.",
    )
    parser.add_argument(
        "--skip-ingestion",
        action="store_true",
        help="Process existing data and train only; skip network API ingestion.",
    )
    parser.add_argument(
        "--skip-training",
        action="store_true",
        help="Update data, transformations, and features without training or promoting models.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip running pytest regression test suite at the end of the pipeline.",
    )
    parser.add_argument(
        "--no-airflow",
        action="store_true",
        help="Do not trigger the Docker Airflow DAG upon pipeline completion.",
    )
    args = parser.parse_args()

    # Validate option combinations
    if (args.start and not args.end) or (args.end and not args.start):
        parser.error("Both --start and --end must be specified together for historical backfill.")

    if args.start and args.end:
        try:
            d_start = datetime.strptime(args.start, "%Y-%m-%d")
            d_end = datetime.strptime(args.end, "%Y-%m-%d")
            if d_start > d_end:
                parser.error(f"--start ({args.start}) cannot be after --end ({args.end}).")
        except ValueError as exc:
            parser.error(f"Invalid date format for --start/--end: {exc}. Use YYYY-MM-DD.")

    if args.skip_ingestion and (args.start or args.end):
        parser.error("Cannot combine --skip-ingestion with --start / --end.")

    return args


def main():
    args = parse_arguments()
    try:
        run_full_pipeline(
            dry_run=args.dry_run,
            start_date=args.start,
            end_date=args.end,
            skip_ingestion=args.skip_ingestion,
            skip_training=args.skip_training,
            skip_tests=args.skip_tests,
            trigger_airflow=not args.no_airflow,
        )
    except Exception as exc:
        logger.fatal("Full pipeline execution failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
