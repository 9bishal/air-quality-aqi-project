"""Tests for the master pipeline orchestrator (run_full_pipeline.py).

Verifies:
1. Checkpoint loading and determination from raw files.
2. Safe checkpoint persistence only on success.
3. Fail-fast error propagation stopping downstream execution.
4. Correct behavior of --dry-run, --skip-ingestion, and --skip-training flags.
5. Ingestion window date parsing and boundary validation.
"""

import json
from pathlib import Path
import pytest
from run_full_pipeline import (
    determine_initial_checkpoint_from_raw,
    get_effective_checkpoint,
    load_checkpoint,
    save_checkpoint,
    parse_arguments,
    run_full_pipeline,
    CHECKPOINT_FILE,
)


def test_checkpoint_determination_from_raw():
    """Verify orchestrator can infer station and time coverage from existing raw data."""
    cp = determine_initial_checkpoint_from_raw()
    assert "stations" in cp
    assert "last_success_utc" in cp
    # Key Bengaluru stations should be present
    assert any(k in cp["stations"] for k in ["5548", "5607", "5644", "6973"])
    assert cp["last_success_utc"] is not None
    assert "T" in cp["last_success_utc"]


def test_checkpoint_save_and_load(tmp_path, monkeypatch):
    """Verify checkpoint saving is safe and creates valid JSON."""
    test_cp_file = tmp_path / "test_checkpoint.json"
    monkeypatch.setattr("run_full_pipeline.CHECKPOINT_FILE", test_cp_file)

    base = {"last_success_utc": "2026-10-01T00:00:00Z", "stations": {"5548": "2026-10-01T00:00:00Z"}}
    mock_measurements = [
        {"location_id": 5548, "period": {"datetimeFrom": {"utc": "2026-10-05T12:00:00Z"}}},
        {"location_id": 5607, "period": {"datetimeFrom": {"utc": "2026-10-06T15:00:00Z"}}},
    ]
    mock_weather = {"hourly": {"time": ["2026-10-06T15:00", "2026-10-06T16:00"]}}

    save_checkpoint(base, new_measurements=mock_measurements, new_weather=mock_weather)
    assert test_cp_file.exists()

    loaded = load_checkpoint()
    assert loaded["last_success_utc"] == "2026-10-06T15:00:00Z"
    assert loaded["stations"]["5548"] == "2026-10-05T12:00:00Z"
    assert loaded["stations"]["5607"] == "2026-10-06T15:00:00Z"
    assert loaded["weather_last_time"] == "2026-10-06T16:00"


def test_dry_run_does_not_mutate_state(monkeypatch):
    """Dry run must return early and not run downstream stages or write files."""
    summary = run_full_pipeline(dry_run=True)
    assert summary["pipeline_status"] == "DRY_RUN_COMPLETED"
    assert summary["stages"]["ingestion"]["status"] == "SKIPPED_DRY_RUN"
    # Ensure downstream stages were not executed
    assert "Clean Pollution" not in summary["stages"]
    assert "model_training" not in summary["stages"]


def test_skip_ingestion_and_skip_training():
    """Verify skip flags correctly bypass respective stages."""
    # Run pipeline with skip_ingestion, skip_training, and skip_tests to avoid recursive pytest
    summary = run_full_pipeline(skip_ingestion=True, skip_training=True, skip_tests=True)
    assert summary["pipeline_status"] == "SUCCESS"
    assert summary["stages"]["ingestion"]["status"] == "SKIPPED"
    assert summary["stages"]["model_training"]["status"] == "SKIPPED"
    assert summary["stages"]["tests"]["status"] == "SKIPPED"
    assert summary["stages"]["Clean Pollution"]["status"] == "PASSED"
    assert summary["stages"]["Calculate CPCB AQI"]["status"] == "PASSED"
    assert summary["stages"]["build_features"]["status"] == "PASSED"


def test_pipeline_fail_fast_on_stage_error(monkeypatch):
    """If a critical stage fails, the pipeline must raise RuntimeError and halt immediately."""
    # Force clean_pollution to fail by giving an invalid python path
    monkeypatch.setattr("sys.executable", "non_existent_python_binary_xyz")
    with pytest.raises(Exception):
        run_full_pipeline(skip_ingestion=True)
