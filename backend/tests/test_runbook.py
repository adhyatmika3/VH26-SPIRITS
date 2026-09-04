import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.incident import Incident
from app.models.canonical_alert import CanonicalAlert


def test_incident_acknowledge_resolve_and_runbook(client: TestClient, db_session: Session):
    """Verify acknowledge, resolve, and runbook SOP endpoints on real database incidents."""
    now = datetime.now(timezone.utc)
    inc = Incident(
        id=uuid.uuid4(),
        incident_number="INC-TEST-RUNBOOK",
        title="Payment API Latency Spike",
        service="payment-api",
        status="OPEN",
        priority="CRITICAL",
        alert_count=5,
        unique_alerts_count=1,
        is_storm=False,
        first_seen=now,
        last_seen=now,
        created_at=now,
        updated_at=now
    )
    db_session.add(inc)
    db_session.commit()

    # 1. Test GET Runbook
    rb_resp = client.get(f"/api/v1/incidents/{inc.id}/runbook")
    assert rb_resp.status_code == 200
    rb_data = rb_resp.json()
    assert rb_data["sop_code"] == "SOP-402"
    assert len(rb_data["steps"]) == 4
    assert len(rb_data["prechecks"]) >= 3

    # 2. Test POST Execute Runbook (Step 1)
    exec_resp = client.post(f"/api/v1/incidents/{inc.id}/runbook/execute", json={"step_index": 1, "actor": "sre-lead"})
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["status"] == "SUCCESS"
    assert len(exec_data["logs"]) >= 3
    assert 1 in exec_data["completed_steps"]

    # 3. Test POST Execute Full Runbook
    full_exec_resp = client.post(f"/api/v1/incidents/{inc.id}/runbook/execute", json={"actor": "sre-lead"})
    assert full_exec_resp.status_code == 200
    full_exec_data = full_exec_resp.json()
    assert full_exec_data["all_completed"] is True

    # 4. Test Acknowledge Incident (handles empty body or json)
    ack_resp = client.post(f"/api/v1/incidents/{inc.id}/acknowledge", json={"actor": "sre-operator"})
    assert ack_resp.status_code == 200
    ack_data = ack_resp.json()
    assert ack_data["status"] == "ACKNOWLEDGED"
    assert ack_data["acknowledged_by"] == "sre-operator"

    # 5. Test Resolve Incident
    res_resp = client.post(f"/api/v1/incidents/{inc.id}/resolve", json={"actor": "sre-operator"})
    assert res_resp.status_code == 200
    res_data = res_resp.json()
    assert res_data["status"] == "RESOLVED"
    assert res_data["resolved_by"] == "sre-operator"
