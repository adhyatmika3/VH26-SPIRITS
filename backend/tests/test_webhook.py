import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.raw_alert import RawAlert
from app.models.canonical_alert import CanonicalAlert


def test_webhook_valid_payload_success(client: TestClient, db_session: Session):
    payload = {
        "source": "prometheus",
        "alert_name": "HighCPUUsage",
        "service": "payment-api",
        "resource": "pod-17",
        "severity": "high",
        "status": "firing",
        "timestamp": "2026-09-04T10:00:00Z",
        "labels": {"environment": "production", "region": "us-east-1"},
        "annotations": {"description": "CPU usage exceeded threshold", "runbook": "http://runbooks/cpu"}
    }

    response = client.post("/api/v1/alerts/webhook", json=payload)
    assert response.status_code == 201
    
    data = response.json()
    assert data["accepted"] is True
    assert data["status"] == "received"
    assert "alert_id" in data
    
    # Validate UUID format
    alert_uuid = uuid.UUID(data["alert_id"])
    assert str(alert_uuid) == data["alert_id"]

    # Verify database persistence
    persisted = db_session.query(RawAlert).filter(RawAlert.id == alert_uuid).first()
    assert persisted is not None
    assert persisted.source == "prometheus"
    assert persisted.alert_name == "HighCPUUsage"
    assert persisted.service == "payment-api"
    assert persisted.resource == "pod-17"
    assert persisted.severity == "high"
    assert persisted.status == "firing"
    assert persisted.labels == {"environment": "production", "region": "us-east-1"}
    assert persisted.annotations == {"description": "CPU usage exceeded threshold", "runbook": "http://runbooks/cpu"}
    assert persisted.raw_payload["alert_name"] == "HighCPUUsage"
    assert persisted.received_at is not None


def test_webhook_invalid_payload_missing_required_fields(client: TestClient):
    # Missing required 'service' and 'status'
    invalid_payload = {
        "source": "prometheus",
        "alert_name": "HighCPUUsage",
        "severity": "critical",
        "timestamp": "2026-09-04T10:00:00Z"
    }

    response = client.post("/api/v1/alerts/webhook", json=invalid_payload)
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


def test_multiple_identical_alerts_preserve_raw_occurrences_and_deduplicate_canonical_alert(
    client: TestClient, db_session: Session
):
    """
    Verifies that:
    1. Every webhook occurrence is recorded separately in raw_alerts for audit integrity.
    2. Phase 2 deduplication absorbs duplicate alerts within the deduplication window,
       resulting in exactly 1 CanonicalAlert record with occurrence_count = 5.
    3. The first response indicates is_duplicate = False, and subsequent responses return is_duplicate = True.
    """
    payload = {
        "source": "prometheus",
        "alert_name": "HighMemoryUsage",
        "service": "checkout-api",
        "resource": "node-42",
        "severity": "critical",
        "status": "firing",
        "timestamp": "2026-09-04T10:05:00Z",
        "labels": {"cluster": "prod-k8s"},
        "annotations": {"summary": "OOM killer risk"}
    }

    alert_ids = []
    responses = []
    for _ in range(5):
        resp = client.post("/api/v1/alerts/webhook", json=payload)
        assert resp.status_code == 201
        res_data = resp.json()
        alert_ids.append(res_data["alert_id"])
        responses.append(res_data)

    # 1. Verify 5 distinct raw alert UUIDs were returned
    assert len(set(alert_ids)) == 5

    # 2. Verify exactly 5 distinct records exist in raw_alerts (Audit trail preserved)
    raw_count = db_session.query(RawAlert).filter(
        RawAlert.service == "checkout-api",
        RawAlert.alert_name == "HighMemoryUsage"
    ).count()
    assert raw_count == 5

    # 3. Verify exactly 1 CanonicalAlert record exists with occurrence_count = 5
    canonical_alerts = db_session.query(CanonicalAlert).filter(
        CanonicalAlert.service == "checkout-api",
        CanonicalAlert.alert_name == "HighMemoryUsage"
    ).all()
    assert len(canonical_alerts) == 1
    assert canonical_alerts[0].occurrence_count == 5
    assert canonical_alerts[0].is_duplicate is True

    # 4. Verify duplicate responses contract
    assert responses[0]["is_duplicate"] is False
    assert responses[0]["occurrence_count"] == 1
    for r in responses[1:]:
        assert r["is_duplicate"] is True
    assert responses[4]["occurrence_count"] == 5
