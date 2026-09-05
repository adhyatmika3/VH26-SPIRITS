import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.raw_alert import RawAlert
from app.models.incident import Incident
from app.services.load_test_service import load_test_manager


@pytest.fixture(autouse=True)
def clean_load_test_manager():
    """Ensure load_test_manager is reset before and after each test."""
    if load_test_manager.status == "PROCESSING":
        # Force stop
        load_test_manager.status = "STOPPED"
    load_test_manager.reset()
    yield
    if load_test_manager.status == "PROCESSING":
        load_test_manager.status = "STOPPED"
    load_test_manager.reset()


def test_load_test_initial_status(client: TestClient):
    response = client.get("/api/v1/load-test/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "IDLE"
    assert data["alerts_submitted"] == 0
    assert data["alerts_accepted"] == 0
    assert data["alerts_processed"] == 0
    assert data["alerts_failed"] == 0
    assert data["active_workers"] == 0


def test_load_test_start_and_completion(client: TestClient, db_session: Session):
    config = {
        "count": 25,
        "rate": 200,
        "scenario": "duplicate_storm",
        "concurrency": 1
    }
    start_resp = client.post("/api/v1/load-test/start", json=config)
    assert start_resp.status_code == 200
    start_data = start_resp.json()
    assert start_data["status"] == "PROCESSING"

    # Poll until completed (max 10 seconds)
    max_wait = 10.0
    start_wait = time.time()
    final_data = None

    while time.time() - start_wait < max_wait:
        status_resp = client.get("/api/v1/load-test/status")
        assert status_resp.status_code == 200
        final_data = status_resp.json()
        if final_data["status"] == "COMPLETED":
            break
        time.sleep(0.1)

    assert final_data is not None
    assert final_data["status"] == "COMPLETED"
    assert final_data["alerts_submitted"] == 25
    assert final_data["alerts_accepted"] == 25
    assert final_data["alerts_processed"] == 25
    assert final_data["alerts_failed"] == 0
    assert final_data["total_requested"] == 25

    # Check metrics history
    metrics_resp = client.get("/api/v1/load-test/metrics")
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert isinstance(metrics, list)


def test_load_test_stop(client: TestClient):
    # Start a test with low rate and high count so we can stop it
    config = {
        "count": 200,
        "rate": 10,
        "scenario": "alert_spike",
        "concurrency": 2
    }
    start_resp = client.post("/api/v1/load-test/start", json=config)
    assert start_resp.status_code == 200

    time.sleep(0.3)
    stop_resp = client.post("/api/v1/load-test/stop")
    assert stop_resp.status_code == 200
    stop_data = stop_resp.json()
    assert stop_data["status"] == "STOPPED"
    assert stop_data["active_workers"] == 0
    assert stop_data["alerts_processed"] < 200


def test_load_test_conflict_when_already_running(client: TestClient):
    config = {
        "count": 200,
        "rate": 10,
        "scenario": "duplicate_storm",
        "concurrency": 2
    }
    start_resp = client.post("/api/v1/load-test/start", json=config)
    assert start_resp.status_code == 200

    # Attempt to start second run while first is active
    second_resp = client.post("/api/v1/load-test/start", json=config)
    assert second_resp.status_code == 409
    assert "already actively running" in second_resp.json()["detail"]

    # Clean up
    client.post("/api/v1/load-test/stop")


def test_load_test_reset(client: TestClient):
    # Completed or stopped test can be reset
    config = {
        "count": 10,
        "rate": 200,
        "scenario": "duplicate_storm",
        "concurrency": 2
    }
    client.post("/api/v1/load-test/start", json=config)
    
    # Wait for completion
    for _ in range(50):
        s = client.get("/api/v1/load-test/status").json()
        if s["status"] == "COMPLETED":
            break
        time.sleep(0.1)

    # Reset
    reset_resp = client.post("/api/v1/load-test/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "IDLE"

    status_resp = client.get("/api/v1/load-test/status")
    assert status_resp.json()["status"] == "IDLE"
    assert status_resp.json()["alerts_processed"] == 0


def test_load_test_duplicate_storm_consolidation(client: TestClient, db_session: Session):
    config = {
        "count": 30,
        "rate": 300,
        "scenario": "duplicate_storm",
        "concurrency": 1
    }
    client.post("/api/v1/load-test/start", json=config)

    for _ in range(50):
        s = client.get("/api/v1/load-test/status").json()
        if s["status"] == "COMPLETED":
            break
        time.sleep(0.1)

    # In SQLite test db, verify RawAlerts exist
    raw_alerts = db_session.query(RawAlert).all()
    assert len(raw_alerts) >= 30

    # Verify incidents
    incidents = db_session.query(Incident).all()
    assert len(incidents) >= 1
