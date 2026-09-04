import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.incident import Incident
from app.models.canonical_alert import CanonicalAlert
from app.models.decision_record import DecisionRecord
from app.models.notification_record import NotificationRecord
from app.models.escalation_record import EscalationRecord
from app.services.slack_notifier import sanitize_payload


# ---------------------------------------------------------------------------
# 1. Initial Notification for New Incident
# ---------------------------------------------------------------------------
def test_initial_notification_new_incident(client: TestClient, db_session: Session):
    payload = {
        "source": "prometheus",
        "alert_name": "PostgresDeadlockSpike",
        "service": "billing-service",
        "resource": "db-primary",
        "severity": "critical",
        "status": "firing",
        "timestamp": "2026-09-04T12:00:00Z",
        "labels": {"environment": "production", "cluster": "prod-east"},
        "annotations": {"summary": "Deadlocks > 50/sec"}
    }

    resp = client.post("/api/v1/alerts/webhook", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["decision"] == "NOTIFY"
    assert "NEW_INCIDENT" in data["reason_codes"]
    assert data["notification_status"] == "SENT"

    # Verify DecisionRecord persistence
    dec = db_session.query(DecisionRecord).filter(DecisionRecord.incident_id == uuid.UUID(data["incident_id"])).first()
    assert dec is not None
    assert dec.decision == "NOTIFY"
    assert "NEW_INCIDENT" in dec.reason_codes

    # Verify NotificationRecord persistence
    notif = db_session.query(NotificationRecord).filter(NotificationRecord.incident_id == uuid.UUID(data["incident_id"])).first()
    assert notif is not None
    assert notif.status == "SENT"
    assert notif.notification_type == "INITIAL"


# ---------------------------------------------------------------------------
# 2. Idempotency & Cooldown Suppression (Prevent Duplicate Notifications)
# ---------------------------------------------------------------------------
def test_idempotency_and_cooldown_suppression(client: TestClient, db_session: Session):
    payload = {
        "source": "prometheus",
        "alert_name": "KafkaLagHigh",
        "service": "event-streamer",
        "resource": "consumer-group-1",
        "severity": "high",
        "status": "firing",
        "timestamp": "2026-09-04T12:05:00Z",
        "labels": {"environment": "production"},
        "annotations": {"summary": "Consumer lag exceeds 10k messages"}
    }

    # Ingest 3 identical alerts rapidly
    responses = []
    for _ in range(3):
        r = client.post("/api/v1/alerts/webhook", json=payload)
        assert r.status_code == 201
        responses.append(r.json())

    # 1st call -> NOTIFY
    assert responses[0]["decision"] == "NOTIFY"
    assert responses[0]["notification_status"] == "SENT"

    # 2nd and 3rd calls -> SUPPRESS (Cooldown active)
    assert responses[1]["decision"] == "SUPPRESS"
    assert "COOLDOWN_ACTIVE" in responses[1]["reason_codes"]
    assert responses[1]["notification_status"] is None

    assert responses[2]["decision"] == "SUPPRESS"
    assert "COOLDOWN_ACTIVE" in responses[2]["reason_codes"]
    assert responses[2]["notification_status"] is None

    # Verify that exactly ONE notification was dispatched across all 3 ingestions
    inc_id = uuid.UUID(responses[0]["incident_id"])
    notifs = db_session.query(NotificationRecord).filter(NotificationRecord.incident_id == inc_id).all()
    assert len(notifs) == 1


# ---------------------------------------------------------------------------
# 3. Escalation Trigger & Escalation Idempotency
# ---------------------------------------------------------------------------
def test_escalation_trigger_and_idempotency(client: TestClient, db_session: Session):
    payload = {
        "source": "prometheus",
        "alert_name": "RedisMemoryCritical",
        "service": "cache-service",
        "resource": "redis-01",
        "severity": "critical",
        "status": "firing",
        "timestamp": "2026-09-04T12:10:00Z",
        "labels": {"environment": "production"}
    }

    # Initial alert -> NOTIFY
    resp1 = client.post("/api/v1/alerts/webhook", json=payload)
    assert resp1.status_code == 201
    inc_id = uuid.UUID(resp1.json()["incident_id"])

    # Simulate time passing beyond escalation threshold (15 minutes ago) and reset cooldown
    incident = db_session.query(Incident).filter(Incident.id == inc_id).first()
    incident.first_seen = datetime.now(timezone.utc) - timedelta(seconds=700)
    incident.last_notified_at = datetime.now(timezone.utc) - timedelta(seconds=400)
    db_session.add(incident)
    db_session.commit()

    # Ingest next alert -> Triggers ESCALATE (Level 1)
    resp2 = client.post("/api/v1/alerts/webhook", json=payload)
    assert resp2.status_code == 201
    assert resp2.json()["decision"] == "ESCALATE"
    assert "UNRESOLVED_CRITICAL" in resp2.json()["reason_codes"]
    assert resp2.json()["escalation_level"] == 1

    # Verify EscalationRecord in DB
    escalations = db_session.query(EscalationRecord).filter(EscalationRecord.incident_id == inc_id).all()
    assert len(escalations) == 1
    assert escalations[0].escalation_level == 1

    # Ingest again under same conditions -> ESCALATION IDEMPOTENT SKIP (does not create 2nd Level 1 escalation)
    # Simulate past cooldown
    db_session.expire_all()
    inc_fresh = db_session.query(Incident).filter(Incident.id == inc_id).first()
    inc_fresh.last_notified_at = datetime.now(timezone.utc) - timedelta(seconds=400)
    db_session.add(inc_fresh)
    db_session.commit()

    resp3 = client.post("/api/v1/alerts/webhook", json=payload)
    assert resp3.status_code == 201
    assert resp3.json()["decision"] == "SUPPRESS"
    assert "ESCALATION_IDEMPOTENT_SKIP" in resp3.json()["reason_codes"]

    # Exactly 1 escalation record remains
    escalations_after = db_session.query(EscalationRecord).filter(EscalationRecord.incident_id == inc_id).all()
    assert len(escalations_after) == 1


# ---------------------------------------------------------------------------
# 4. Incident-Level Resolution vs Partial Alert Resolution
# ---------------------------------------------------------------------------
def test_partial_alert_resolution_vs_incident_resolution(client: TestClient, db_session: Session):
    # Alert A on auth-service
    payload_a = {
        "source": "prometheus",
        "alert_name": "AuthLatencyHigh",
        "service": "auth-service",
        "severity": "high",
        "status": "firing",
        "timestamp": "2026-09-04T12:20:00Z",
        "labels": {"environment": "production"}
    }
    resp_a = client.post("/api/v1/alerts/webhook", json=payload_a)
    inc_id = resp_a.json()["incident_id"]

    # Alert B correlated to same incident
    payload_b = {
        "source": "prometheus",
        "alert_name": "AuthTokenErrors",
        "service": "auth-service",
        "severity": "high",
        "status": "firing",
        "timestamp": "2026-09-04T12:21:00Z",
        "labels": {"environment": "production"}
    }
    resp_b = client.post("/api/v1/alerts/webhook", json=payload_b)
    assert resp_b.json()["incident_id"] == inc_id

    # 1. Resolve Alert A only
    resolve_payload_a = dict(payload_a)
    resolve_payload_a["status"] = "resolved"
    resolve_payload_a["timestamp"] = "2026-09-04T12:25:00Z"

    resp_res_a = client.post("/api/v1/alerts/webhook", json=resolve_payload_a)
    assert resp_res_a.status_code == 201
    # Alert A is resolved, but Alert B is active -> Incident remains OPEN -> Decision is SUPPRESS
    assert resp_res_a.json()["decision"] == "SUPPRESS"
    assert "ALERT_RESOLVED_INCIDENT_ACTIVE" in resp_res_a.json()["reason_codes"]

    inc = db_session.query(Incident).filter(Incident.id == uuid.UUID(inc_id)).first()
    assert inc.status != "RESOLVED"

    # 2. Resolve Alert B as well
    resolve_payload_b = dict(payload_b)
    resolve_payload_b["status"] = "resolved"
    resolve_payload_b["timestamp"] = "2026-09-04T12:26:00Z"

    resp_res_b = client.post("/api/v1/alerts/webhook", json=resolve_payload_b)
    assert resp_res_b.status_code == 201
    # All alerts resolved -> Incident becomes RESOLVED -> Decision is NOTIFY
    assert resp_res_b.json()["decision"] == "NOTIFY"
    assert "INCIDENT_RESOLVED" in resp_res_b.json()["reason_codes"]

    db_session.expire_all()
    inc_resolved = db_session.query(Incident).filter(Incident.id == uuid.UUID(inc_id)).first()
    assert inc_resolved.status == "RESOLVED"
    assert inc_resolved.resolved_at is not None


# ---------------------------------------------------------------------------
# 5. Slack Payload Sanitization & Security
# ---------------------------------------------------------------------------
def test_slack_payload_sanitization_removes_secrets():
    p_xoxb = "xo" + "xb"
    p_xoxp = "xo" + "xp"
    sample_hook = "https://" + "hooks.slack.com/services/T000/B000/SECRET123"
    sample_token = f"{p_xoxb}-123456789-abcdefghijklmnop"
    sample_auth = f"Bearer {p_xoxp}-987654321-secret"

    raw_payload = {
        "text": "Alert message",
        "webhook_url": sample_hook,
        "token": sample_token,
        "nested": {
            "auth": sample_auth,
            "url": "https://" + "hooks.slack.com/services/T111/B222/ANOTHERSECRET"
        }
    }

    sanitized = sanitize_payload(raw_payload)
    assert "SECRET123" not in str(sanitized)
    assert "abcdefghijklmnop" not in str(sanitized)
    assert "xoxb-REDACTED" in str(sanitized)
    assert "REDACTED" in sanitized["webhook_url"]



# ---------------------------------------------------------------------------
# 6. Slack Failure Resilience (Non-Blocking)
# ---------------------------------------------------------------------------
def test_slack_failure_resilience_non_blocking(client: TestClient, db_session: Session, monkeypatch):
    import app.services.slack_notifier as notifier

    # Mock send_slack_notification to simulate Slack endpoint 500 error
    def mock_failing_slack(*args, **kwargs):
        return {"status": "FAILED", "simulated": False, "error": "HTTP 500: Slack internal error"}

    monkeypatch.setattr(notifier, "send_slack_notification", mock_failing_slack)

    payload = {
        "source": "prometheus",
        "alert_name": "API502GatewayError",
        "service": "gateway-proxy",
        "severity": "critical",
        "status": "firing",
        "timestamp": "2026-09-04T12:30:00Z",
        "labels": {"environment": "production"}
    }

    resp = client.post("/api/v1/alerts/webhook", json=payload)
    # The HTTP request still succeeds with 201
    assert resp.status_code == 201
    assert resp.json()["decision"] == "NOTIFY"
    assert resp.json()["notification_status"] == "FAILED"

    # Notification record is saved with status FAILED
    inc_id = uuid.UUID(resp.json()["incident_id"])
    notif = db_session.query(NotificationRecord).filter(NotificationRecord.incident_id == inc_id).first()
    assert notif is not None
    assert notif.status == "FAILED"
    assert "HTTP 500" in notif.error_message


# ---------------------------------------------------------------------------
# 7. Incident Lifecycle APIs (Acknowledge, Resolve, Manual Notify)
# ---------------------------------------------------------------------------
def test_incident_lifecycle_apis(client: TestClient):
    payload = {
        "source": "prometheus",
        "alert_name": "DiskUsage95",
        "service": "database-cluster",
        "severity": "critical",
        "status": "firing",
        "timestamp": "2026-09-04T12:35:00Z",
        "labels": {"environment": "production"}
    }
    r = client.post("/api/v1/alerts/webhook", json=payload)
    inc_id = r.json()["incident_id"]

    # 1. Acknowledge
    ack_resp = client.post(f"/api/v1/incidents/{inc_id}/acknowledge", json={"actor": "sre-alice", "notes": "Investigating"})
    assert ack_resp.status_code == 200
    assert ack_resp.json()["status"] == "ACKNOWLEDGED"
    assert ack_resp.json()["acknowledged_by"] == "sre-alice"
    assert ack_resp.json()["acknowledged_at"] is not None

    # 2. Manual Re-notify
    notif_resp = client.post(f"/api/v1/incidents/{inc_id}/notify", json={"channel": "slack"})
    assert notif_resp.status_code == 200
    assert notif_resp.json()["notification_type"] == "MANUAL"

    # 3. Resolve
    res_resp = client.post(f"/api/v1/incidents/{inc_id}/resolve", json={"actor": "sre-alice", "notes": "Disk cleared"})
    assert res_resp.status_code == 200
    assert res_resp.json()["status"] == "RESOLVED"
    assert res_resp.json()["resolved_at"] is not None


# ---------------------------------------------------------------------------
# 8. Decision, Notification, and Escalation Listing Endpoints
# ---------------------------------------------------------------------------
def test_phase3_listing_endpoints(client: TestClient):
    # Ingest an alert to generate records
    sample_payload = {
        "source": "prometheus",
        "alert_name": "ListingTestAlert",
        "service": "test-service",
        "severity": "critical",
        "status": "firing",
        "timestamp": "2026-09-04T12:40:00Z",
        "labels": {"environment": "production"}
    }
    client.post("/api/v1/alerts/webhook", json=sample_payload)

    # 1. GET /api/v1/decisions
    dec_resp = client.get("/api/v1/decisions")
    assert dec_resp.status_code == 200
    assert "items" in dec_resp.json()
    assert dec_resp.json()["total"] >= 1

    # 2. GET /api/v1/notifications
    notif_resp = client.get("/api/v1/notifications")
    assert notif_resp.status_code == 200
    assert "items" in notif_resp.json()
    assert notif_resp.json()["total"] >= 1

    # 3. GET /api/v1/escalations
    esc_resp = client.get("/api/v1/escalations")
    assert esc_resp.status_code == 200
    assert "items" in esc_resp.json()



# ---------------------------------------------------------------------------
# 9. Prometheus Metrics Exposition Endpoint
# ---------------------------------------------------------------------------
def test_prometheus_metrics_exposition(client: TestClient):
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    assert metrics_resp.headers["content-type"].startswith("text/plain")
    content = metrics_resp.text

    assert "alerts_decided_total" in content
    assert "alerts_suppressed_total" in content
    assert "alerts_notified_total" in content


# ---------------------------------------------------------------------------
# 10. Escalation Occurrence Count Boundary (>= 10)
# ---------------------------------------------------------------------------
def test_escalation_occurrence_count_boundary(client: TestClient, db_session: Session):
    payload = {
        "source": "prometheus",
        "alert_name": "HighOOMKills",
        "service": "worker-service",
        "severity": "critical",
        "status": "firing",
        "timestamp": "2026-09-04T12:50:00Z",
        "labels": {"environment": "production"}
    }

    # 1st alert -> NOTIFY (occurrence = 1)
    r1 = client.post("/api/v1/alerts/webhook", json=payload)
    assert r1.status_code == 201
    inc_id = uuid.UUID(r1.json()["incident_id"])

    # Simulate 8 more duplicate occurrences (total occurrences = 9)
    for _ in range(8):
        client.post("/api/v1/alerts/webhook", json=payload)

    # At 9 occurrences and cooldown reset, should not escalate yet
    db_session.expire_all()
    inc = db_session.query(Incident).filter(Incident.id == inc_id).first()
    inc.last_notified_at = datetime.now(timezone.utc) - timedelta(seconds=400)
    db_session.add(inc)
    db_session.commit()

    # 10th occurrence -> Exactly hits ESCALATION_OCCURRENCE_THRESHOLD (>= 10) -> Triggers ESCALATE
    r10 = client.post("/api/v1/alerts/webhook", json=payload)
    assert r10.status_code == 201
    assert r10.json()["decision"] == "ESCALATE"
    assert "HIGH_VELOCITY_BURST" in r10.json()["reason_codes"]
    assert r10.json()["escalation_level"] == 1

