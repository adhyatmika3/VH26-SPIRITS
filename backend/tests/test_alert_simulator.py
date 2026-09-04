import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.raw_alert import RawAlert
from app.models.canonical_alert import CanonicalAlert
from app.models.incident import Incident
from app.services.fingerprint_service import generate_fingerprint
from app.services.alert_simulator import generate_alert_message_variation


def test_fingerprint_variations_consistent_for_same_alert_type():
    """Verify that different wording variations map to the exact same fingerprint."""
    var1 = generate_alert_message_variation("payment-api", "CPU_HIGH", 0)
    var2 = generate_alert_message_variation("payment-api", "CPU_HIGH", 1)
    var3 = generate_alert_message_variation("payment-api", "CPU_HIGH", 2)

    assert var1 != var2
    assert var2 != var3

    labels = {"environment": "production", "alert_type": "CPU_HIGH"}
    fp1 = generate_fingerprint(var1, "payment-api", labels)
    fp2 = generate_fingerprint(var2, "payment-api", labels)
    fp3 = generate_fingerprint(var3, "payment-api", labels)

    assert fp1 == fp2 == fp3
    assert len(fp1) == 64


def test_simulate_alert_variations_single_incident(client: TestClient, db_session: Session):
    """
    Test simulating alerts through the real webhook pipeline:
    N raw alerts -> Webhook Ingestion -> PostgreSQL (N raw rows) -> 1 Core Incident
    """
    initial_raw = db_session.query(RawAlert).filter(RawAlert.service == "sim-auth").count()

    sim_payload = {
        "count": 25,
        "service": "sim-auth",
        "alert_type": "CPU_HIGH",
        "severity": "critical",
        "environment": "production",
        "delay_ms": 0
    }
    resp = client.post("/api/v1/alerts/simulate", json=sim_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["requested"] == 25
    assert data["generated"] == 25
    assert data["status"] == "completed"
    assert data["core_incidents_created"] == 1
    assert data["raw_alerts_count"] == 25
    assert data["alert_reduction_percent"] == 96.0  # (25 - 1) / 25 * 100 = 96.0%

    # Verify PostgreSQL raw alerts: all 25 raw alert records stored (audit trail intact)
    final_raw = db_session.query(RawAlert).filter(RawAlert.service == "sim-auth").count()
    assert final_raw - initial_raw == 25

    # Verify Canonical Alert: exactly 1 canonical alert with occurrence_count = 25
    canonicals = db_session.query(CanonicalAlert).filter(CanonicalAlert.service == "sim-auth").all()
    assert len(canonicals) == 1
    assert canonicals[0].occurrence_count == 25

    # Verify Incident: exactly 1 incident with alert_count = 25
    inc = db_session.query(Incident).filter(Incident.service == "sim-auth").first()
    assert inc is not None
    assert inc.alert_count == 25


def test_simulate_multiple_incidents_distinction(client: TestClient, db_session: Session):
    """
    Requirement 10: System must distinguish different problems.
    300 CPU alerts -> Incident A
    200 DB alerts -> Incident B
    """
    sim_payload = {
        "count": 500,
        "scenario": "multiple",
        "service": "multi-service",
        "severity": "critical",
        "environment": "production",
        "delay_ms": 0
    }
    resp = client.post("/alerts/simulate", json=sim_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["requested"] == 500
    assert data["generated"] == 500
    assert data["core_incidents_created"] == 2
    assert data["raw_alerts_count"] == 500
    assert data["alert_reduction_percent"] == 99.6  # (500 - 2) / 500 * 100 = 99.6%

    # Verify 2 distinct incidents exist for multi-service in DB
    incidents = db_session.query(Incident).filter(Incident.service == "multi-service").all()
    assert len(incidents) == 2

    counts = sorted([inc.alert_count for inc in incidents])
    assert counts == [200, 300]


def test_get_raw_alerts_audit_endpoint(client: TestClient):
    """Test the GET /alerts/raw endpoint to inspect PostgreSQL raw alert rows."""
    resp = client.get("/api/v1/alerts/raw?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data
    assert len(data["items"]) <= 10
    if data["items"]:
        first = data["items"][0]
        assert "raw_payload" in first
        assert "timestamp" in first
        assert "service" in first
