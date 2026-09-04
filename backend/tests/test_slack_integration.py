import hmac
import hashlib
import time
import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from slack_sdk.errors import SlackApiError

from app.core.config import settings
from app.models.raw_alert import RawAlert
from app.models.canonical_alert import CanonicalAlert
from app.models.incident import Incident
from app.models.decision_record import DecisionRecord
from app.models.notification_record import NotificationRecord
from app.services.slack_service import (
    build_incident_blocks,
    send_incident_notification,
    verify_slack_signature,
    check_slack_health,
    handle_slack_interaction,
    sanitize_payload
)
from app.services.notification_service import dispatch_notification


# ---------------------------------------------------------------------------
# Helper: Generate authentic Slack Signature for testing
# ---------------------------------------------------------------------------
def generate_test_slack_signature(body: bytes, timestamp: str, secret: str) -> str:
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    computed_hash = hmac.new(secret.encode("utf-8"), sig_basestring, hashlib.sha256).hexdigest()
    return f"v0={computed_hash}"


# ---------------------------------------------------------------------------
# Test 1 — Slack Disabled Mode
# ---------------------------------------------------------------------------
def test_slack_disabled_mode_skips_api_call_and_processing_succeeds(monkeypatch, client: TestClient):
    """
    When SLACK_ENABLED=false:
    - Alert pipeline succeeds
    - No real Slack network calls are made
    - Simulated notification status is returned safely
    """
    monkeypatch.setattr(settings, "SLACK_ENABLED", False)

    mock_client = MagicMock()
    with patch("app.services.slack_service.WebClient", return_value=mock_client):
        payload = {
            "source": "prometheus",
            "alert_name": "DatabaseConnTimeout",
            "service": "order-service",
            "resource": "db-pool",
            "severity": "critical",
            "status": "firing",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "labels": {"environment": "production"},
            "annotations": {"summary": "DB pool saturated"}
        }
        resp = client.post("/api/v1/alerts/webhook", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["decision"] == "NOTIFY"
        # slack_sdk WebClient chat_postMessage was NOT called
        mock_client.chat_postMessage.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2 — Critical Incident Triggers Slack Notification
# ---------------------------------------------------------------------------
def test_critical_incident_triggers_slack_notification(db_session: Session, monkeypatch):
    """
    Given a CRITICAL incident / decision:
    - Slack notification is dispatched with high urgency
    - NotificationRecord is created with status SENT and channel slack
    """
    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-real-mock-token-1234")

    inc = Incident(
        incident_number="INC-2001",
        title="Production Auth Gateway 502 Outage",
        service="auth-service",
        status="OPEN",
        priority="CRITICAL",
        alert_count=100,
        unique_alerts_count=1
    )
    db_session.add(inc)
    db_session.flush()

    dec = DecisionRecord(
        incident_id=inc.id,
        decision="ESCALATE",
        reason_codes=["UNRESOLVED_CRITICAL", "HIGH_VELOCITY_BURST"],
        reason="Rapid critical failure spike detected",
        context_snapshot={
            "service": "auth-service",
            "risk_score": 94,
            "risk_level": "CRITICAL"
        }
    )
    db_session.add(dec)
    db_session.flush()

    mock_webclient = MagicMock()
    mock_webclient.chat_postMessage.return_value = {"ok": True, "ts": "1725500000.000100"}

    with patch("app.services.slack_service.WebClient", return_value=mock_webclient):
        notif = dispatch_notification(
            db=db_session,
            decision_record=dec,
            incident=inc,
            notification_type="ESCALATION",
            channel="slack"
        )
        assert notif.status == "SENT"
        assert notif.channel == "slack"
        assert notif.notification_type == "ESCALATION"
        mock_webclient.chat_postMessage.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3 — Non-Critical Incident Skips Critical Slack Notification
# ---------------------------------------------------------------------------
def test_non_critical_incident_skips_critical_slack_notification(client: TestClient, db_session: Session, monkeypatch):
    """
    Given low severity alert in non-production environment:
    - Decision Engine evaluates SUPPRESS
    - No critical notification is dispatched
    """
    monkeypatch.setattr(settings, "SLACK_ENABLED", True)

    payload = {
        "source": "prometheus",
        "alert_name": "DevCacheSlow",
        "service": "dev-cache",
        "resource": "cache-01",
        "severity": "low",
        "status": "firing",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "labels": {"environment": "development"},
        "annotations": {"summary": "Cache slow in dev"}
    }
    resp = client.post("/api/v1/alerts/webhook", json=payload)
    assert resp.status_code == 201
    assert resp.json()["decision"] == "SUPPRESS"

    # Verify no notification record was created for this suppressed dev alert
    inc_id = uuid.UUID(resp.json()["incident_id"])
    notifs = db_session.query(NotificationRecord).filter(NotificationRecord.incident_id == inc_id).all()
    assert len(notifs) == 0


# ---------------------------------------------------------------------------
# Test 4 — Duplicate Prevention (Incident-Level Idempotency)
# ---------------------------------------------------------------------------
def test_duplicate_slack_notification_prevention(db_session: Session, monkeypatch):
    """
    Dispatching notifications for the same incident multiple times:
    - 1st call dispatches and creates SENT record
    - 2nd call is intercepted by DB idempotency check and returns existing record
    - Exactly ONE Slack notification is sent
    """
    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-mock-token-555")

    inc = Incident(
        incident_number="INC-2004",
        title="Checkout Service Deadlock",
        service="checkout-service",
        status="OPEN",
        priority="CRITICAL",
        alert_count=50,
        unique_alerts_count=1
    )
    db_session.add(inc)
    db_session.flush()

    dec = DecisionRecord(
        incident_id=inc.id,
        decision="ESCALATE",
        reason_codes=["UNRESOLVED_CRITICAL"],
        reason="Critical threshold exceeded",
        context_snapshot={"service": "checkout-service", "risk_score": 90, "risk_level": "CRITICAL"}
    )
    db_session.add(dec)
    db_session.flush()

    mock_client = MagicMock()
    mock_client.chat_postMessage.return_value = {"ok": True, "ts": "1725500000.123456"}

    with patch("app.services.slack_service.WebClient", return_value=mock_client):
        first_notif = dispatch_notification(
            db=db_session,
            decision_record=dec,
            incident=inc,
            notification_type="ESCALATION",
            channel="slack"
        )
        assert first_notif.status == "SENT"
        assert mock_client.chat_postMessage.call_count == 1

        # Second dispatch attempt for same incident
        second_notif = dispatch_notification(
            db=db_session,
            decision_record=dec,
            incident=inc,
            notification_type="ESCALATION",
            channel="slack"
        )
        # Mock client call count remains 1 (intercepted by idempotency!)
        assert mock_client.chat_postMessage.call_count == 1
        assert second_notif.id == first_notif.id


# ---------------------------------------------------------------------------
# Test 5 — Slack Failure Resilience (Non-Blocking)
# ---------------------------------------------------------------------------
def test_slack_api_failure_does_not_crash_pipeline(client: TestClient, db_session: Session, monkeypatch):
    """
    When Slack API returns SlackApiError (e.g. channel_not_found or rate_limited):
    - Incident processing succeeds (HTTP 201)
    - Decision is recorded
    - NotificationRecord is marked status='FAILED' with error message
    - Incident is NOT rolled back
    """
    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-mock-token-err")

    mock_client = MagicMock()
    mock_client.chat_postMessage.side_effect = SlackApiError(
        message="The request to the Slack API failed.",
        response={"ok": False, "error": "channel_not_found"}
    )

    with patch("app.services.slack_service.WebClient", return_value=mock_client):
        payload = {
            "source": "prometheus",
            "alert_name": "APIErrorSpike",
            "service": "search-service",
            "severity": "critical",
            "status": "firing",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "labels": {"environment": "production"}
        }
        resp = client.post("/api/v1/alerts/webhook", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["decision"] == "NOTIFY"

        inc_id = uuid.UUID(data["incident_id"])
        incident = db_session.query(Incident).filter(Incident.id == inc_id).first()
        assert incident is not None
        assert incident.status == "OPEN"

        notif = db_session.query(NotificationRecord).filter(NotificationRecord.incident_id == inc_id).first()
        assert notif is not None
        assert notif.status == "FAILED"
        assert "channel_not_found" in notif.error_message


# ---------------------------------------------------------------------------
# Test 6 — Slack Signature Verification
# ---------------------------------------------------------------------------
def test_slack_signature_verification(monkeypatch):
    """
    Test authentic HMAC-SHA256 signature verification:
    - Valid signature + recent timestamp -> True
    - Stale timestamp (> 300s) -> False (replay attack prevention)
    - Tampered body -> False
    - Wrong secret -> False
    """
    test_secret = "test_signing_secret_9876543210"
    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", test_secret)

    now_ts = str(int(time.time()))
    body = b'payload=%7B%22type%22%3A%22block_actions%22%7D'

    # 1. Valid signature
    valid_sig = generate_test_slack_signature(body, now_ts, test_secret)
    headers = {
        "x-slack-request-timestamp": now_ts,
        "x-slack-signature": valid_sig
    }
    assert verify_slack_signature(body, headers) is True

    # 2. Stale timestamp (replay attack 10 minutes ago)
    stale_ts = str(int(time.time()) - 600)
    stale_sig = generate_test_slack_signature(body, stale_ts, test_secret)
    stale_headers = {
        "x-slack-request-timestamp": stale_ts,
        "x-slack-signature": stale_sig
    }
    assert verify_slack_signature(body, stale_headers) is False

    # 3. Tampered body
    tampered_body = b'payload=%7B%22type%22%3A%22tampered%22%7D'
    assert verify_slack_signature(tampered_body, headers) is False

    # 4. Wrong signature
    bad_headers = {
        "x-slack-request-timestamp": now_ts,
        "x-slack-signature": "v0=invalid_signature_hex"
    }
    assert verify_slack_signature(body, bad_headers) is False


# ---------------------------------------------------------------------------
# Test 7 — Message Contents & Block Kit Structure
# ---------------------------------------------------------------------------
def test_slack_block_kit_payload_contents():
    """
    Verify Block Kit contains all vital intelligence fields without hallucinations:
    - Header with severity
    - Incident ID, Service, Risk score, Decision
    - Noise reduction metrics (occurrences, duplicates, fingerprints)
    - Explainability reasons & reason codes
    - Diagnostic root cause & recommended actions
    - Action buttons with incident ID value and URLs
    """
    blocks_payload = build_incident_blocks(
        notification_type="INITIAL",
        incident_number="INC-3001",
        service="payment-gateway",
        alert_name="DatabaseConnectionPoolExhausted",
        severity="CRITICAL",
        priority="CRITICAL",
        environment="production",
        occurrence_count=500,
        reason_codes=["HIGH_ALERT_VOLUME", "REPEATED_FAILURE", "CRITICAL_SEVERITY"],
        reason="Repeated database connection failures exceeded critical threshold.",
        incident_id="00000000-0000-0000-0000-000000003001",
        decision_id="00000000-0000-0000-0000-000000003002",
        decision="CRITICAL",
        risk_score=92,
        risk_level="CRITICAL",
        dedup_count=499,
        unique_fingerprints=1,
        probable_cause="Postgres connection pool exhausted by unclosed client sessions.",
        resolution_steps=["Scale database connection poolers", "Restart stuck worker pods"],
        dashboard_base_url="http://localhost:3000"
    )

    blocks = blocks_payload["blocks"]
    rendered_json = json.dumps(blocks)

    # 1. Header & ID
    assert "CRITICAL INCIDENT DETECTED: INC-3001" in rendered_json
    assert "INC-3001" in rendered_json

    # 2. Risk Score & Decision
    assert "92/100" in rendered_json
    assert "CRITICAL" in rendered_json

    # 3. Noise Reduction
    assert "500" in rendered_json
    assert "499" in rendered_json

    # 4. Reason Codes
    assert "HIGH_ALERT_VOLUME" in rendered_json
    assert "REPEATED_FAILURE" in rendered_json

    # 5. Diagnostic & Recommended Actions
    assert "Postgres connection pool exhausted" in rendered_json
    assert "Scale database connection poolers" in rendered_json

    # 6. Action buttons
    assert "incident_acknowledge" in rendered_json
    assert "incident_resolve" in rendered_json
    assert "view_incident" in rendered_json
    assert "view_explanation" in rendered_json
    assert "http://localhost:3000/frontend/index.html?incident=00000000-0000-0000-0000-000000003001" in rendered_json
    assert "http://localhost:3000/api/v1/dashboard/explain/00000000-0000-0000-0000-000000003002" in rendered_json


# ---------------------------------------------------------------------------
# Test 8 — Slack Health Check API Endpoint
# ---------------------------------------------------------------------------
def test_slack_health_check_endpoint(client: TestClient, monkeypatch):
    """
    Verify GET /api/v1/integrations/slack/health returns sanitized health status.
    Does not leak tokens or secrets.
    """
    # 1. Disabled mode
    monkeypatch.setattr(settings, "SLACK_ENABLED", False)
    resp = client.get("/api/v1/integrations/slack/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["connected"] is False
    assert "xoxb" not in str(data)

    # 2. Enabled mode with mock auth_test
    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-test-valid-bot-token")

    mock_client = MagicMock()
    mock_client.auth_test.return_value = {"ok": True, "user": "alert-fatigue-bot"}

    with patch("app.services.slack_service.WebClient", return_value=mock_client):
        resp2 = client.get("/api/v1/integrations/slack/health")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["enabled"] is True
        assert data2["configured"] is True
        assert data2["connected"] is True
        assert data2["bot_user"] == "alert-fatigue-bot"
        assert "xoxb" not in str(data2)


# ---------------------------------------------------------------------------
# Test 9 — Slack Interactive Button Actions (Acknowledge & Resolve)
# ---------------------------------------------------------------------------
def test_slack_interactive_actions_via_endpoint(client: TestClient, db_session: Session, monkeypatch):
    """
    Test POST /api/v1/integrations/slack/interactions:
    - Enforces signature check
    - Acknowledge button updates incident status to ACKNOWLEDGED
    - Resolve button updates incident status to RESOLVED and resolves canonical alerts
    """
    test_secret = "test_signing_secret_key_123"
    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", test_secret)

    # Create incident in database
    inc = Incident(
        incident_number=f"INC-{uuid.uuid4().hex[:6]}",
        title="Payment Latency Critical",
        service="payment-service",
        status="OPEN",
        priority="CRITICAL",
        alert_count=10,
        unique_alerts_count=1
    )
    db_session.add(inc)
    db_session.flush()

    calert = CanonicalAlert(
        raw_alert_id=uuid.uuid4(),
        incident_id=inc.id,
        fingerprint=uuid.uuid4().hex,
        source="prometheus",
        alert_name="PaymentLatency",
        service="payment-service",
        message="Payment latency high",
        severity="critical",
        status="firing",
        timestamp=datetime.now(timezone.utc),
        occurrence_count=10,
        priority="CRITICAL"
    )
    db_session.add(calert)
    db_session.commit()

    # 1. Reject invalid signature
    now_ts = str(int(time.time()))
    dummy_body = b"payload={}"
    bad_resp = client.post(
        "/api/v1/integrations/slack/interactions",
        data=dummy_body,
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "x-slack-request-timestamp": now_ts,
            "x-slack-signature": "v0=invalid_sig"
        }
    )
    assert bad_resp.status_code == 401

    # 2. Send Acknowledge action
    ack_payload = {
        "type": "block_actions",
        "user": {"id": "U123456", "name": "alice_sre"},
        "actions": [
            {
                "action_id": "incident_acknowledge",
                "value": str(inc.id)
            }
        ]
    }
    encoded_body = f"payload={json.dumps(ack_payload)}".encode("utf-8")
    sig = generate_test_slack_signature(encoded_body, now_ts, test_secret)

    ack_resp = client.post(
        "/api/v1/integrations/slack/interactions",
        content=encoded_body,
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "x-slack-request-timestamp": now_ts,
            "x-slack-signature": sig
        }
    )
    assert ack_resp.status_code == 200
    assert "acknowledged" in ack_resp.json()["text"].lower()

    db_session.expire_all()
    inc_ack = db_session.query(Incident).filter(Incident.id == inc.id).first()
    assert inc_ack.status == "ACKNOWLEDGED"
    assert "alice_sre" in inc_ack.acknowledged_by

    # 3. Send Resolve action
    res_payload = {
        "type": "block_actions",
        "user": {"id": "U123456", "name": "alice_sre"},
        "actions": [
            {
                "action_id": "incident_resolve",
                "value": str(inc.id)
            }
        ]
    }
    res_encoded = f"payload={json.dumps(res_payload)}".encode("utf-8")
    res_sig = generate_test_slack_signature(res_encoded, now_ts, test_secret)

    res_resp = client.post(
        "/api/v1/integrations/slack/interactions",
        content=res_encoded,
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "x-slack-request-timestamp": now_ts,
            "x-slack-signature": res_sig
        }
    )
    assert res_resp.status_code == 200
    assert "resolved" in res_resp.json()["text"].lower()

    db_session.expire_all()
    inc_res = db_session.query(Incident).filter(Incident.id == inc.id).first()
    assert inc_res.status == "RESOLVED"
    calert_res = db_session.query(CanonicalAlert).filter(CanonicalAlert.id == calert.id).first()
    assert calert_res.status == "RESOLVED"


# ---------------------------------------------------------------------------
# Test 10 — End-to-End Test: 500 Alerts -> 1 Incident -> 1 Email -> 1 Slack
# ---------------------------------------------------------------------------
def test_e2e_500_alerts_critical_incident_triggers_single_email_and_single_slack(client: TestClient, db_session: Session, monkeypatch):
    """
    Demonstrates the full end-to-end flow:
    500 Raw Alerts
          ↓
    FastAPI ingestion
          ↓
    PostgreSQL RawAlert records
          ↓
    Fingerprinting & Deduplication
          ↓
    Correlation
          ↓
    1 Core Incident
          ↓
    Risk Score (>= 90 CRITICAL)
          ↓
    Decision Engine (CRITICAL / ESCALATE)
          ↓
    ┌───────────────────────┐
    ↓                       ↓
    1 Email Escalation   1 Slack Notification
    """
    service_name = "payment-gateway-e2e"
    total_alerts = 20  # Demonstrates multi-alert pipeline hitting critical threshold (>= 10)

    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-mock-e2e-token")

    mock_email_send = MagicMock(return_value={
        "status": "SENT",
        "destination": "sre-team@company.internal",
        "error": None,
        "payload": {"channel": "email"}
    })

    mock_slack_client = MagicMock()
    mock_slack_client.chat_postMessage.return_value = {
        "ok": True,
        "ts": "1725500000.999999"
    }

    with patch("app.services.email_notifier.send_email_notification", mock_email_send), \
         patch("app.services.slack_service.WebClient", return_value=mock_slack_client):

        for i in range(total_alerts):
            payload = {
                "source": "prometheus",
                "alert_name": f"CPU reached {90 + (i % 5)}% on {service_name}",
                "service": service_name,
                "resource": f"pod-{service_name}-{i % 3}",
                "severity": "critical",
                "status": "firing",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "labels": {
                    "environment": "production",
                    "alert_type": "CPU_HIGH",
                    "cluster": "prod-us-east-1"
                },
                "annotations": {
                    "summary": f"High CPU utilization spike on {service_name}"
                }
            }
            resp = client.post("/api/v1/alerts/webhook", json=payload)
            assert resp.status_code == 201

    # 1. Verify RawAlert records: all raw alerts persisted
    raw_count = db_session.query(RawAlert).filter(RawAlert.service == service_name).count()
    assert raw_count == total_alerts

    # 2. Verify Exactly 1 Core Incident created
    incidents = db_session.query(Incident).filter(Incident.service == service_name).all()
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.alert_count == total_alerts
    assert incident.priority == "CRITICAL"
    assert incident.escalation_level == 1

    # 3. Verify exactly 1 Email Escalation notification record
    email_notifs = db_session.query(NotificationRecord).filter(
        NotificationRecord.incident_id == incident.id,
        NotificationRecord.channel == "email"
    ).all()
    assert len(email_notifs) == 1
    assert email_notifs[0].status == "SENT"
    assert email_notifs[0].notification_type == "ESCALATION"

    # 4. Verify exactly 1 Slack notification record
    slack_notifs = db_session.query(NotificationRecord).filter(
        NotificationRecord.incident_id == incident.id,
        NotificationRecord.channel == "slack"
    ).all()
    assert len(slack_notifs) == 1
    assert slack_notifs[0].status == "SENT"
    assert slack_notifs[0].notification_type in ["INITIAL", "ESCALATION"]

    # 5. Verify external clients were called exactly once
    assert mock_email_send.call_count == 1
    assert mock_slack_client.chat_postMessage.call_count == 1


def test_exact_500_alerts_critical_incident_full_batch(client: TestClient, db_session: Session, monkeypatch):
    """
    Full 500-Alert Batch Demonstration:
    500 Raw Alerts -> 1 Core Incident -> CRITICAL -> 1 Email -> 1 Slack Notification.
    """
    service_name = "payment-api-500"
    total_alerts = 500

    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-mock-e2e-token-500")

    mock_email = MagicMock(return_value={
        "status": "SENT",
        "destination": "oncall@company.internal",
        "error": None,
        "payload": {"channel": "email"}
    })
    mock_slack = MagicMock()
    mock_slack.chat_postMessage.return_value = {"ok": True, "ts": "1725500000.500"}

    with patch("app.services.email_notifier.send_email_notification", mock_email), \
         patch("app.services.slack_service.WebClient", return_value=mock_slack):

        for i in range(total_alerts):
            payload = {
                "source": "prometheus",
                "alert_name": f"CPU reached {90 + (i % 5)}% on {service_name}",
                "service": service_name,
                "resource": service_name,
                "severity": "critical",
                "status": "firing",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "labels": {
                    "environment": "production",
                    "alert_type": "CPU_HIGH"
                },
                "annotations": {
                    "summary": f"High CPU on {service_name}"
                }
            }
            resp = client.post("/api/v1/alerts/webhook", json=payload)
            assert resp.status_code == 201

    # 1. 500 raw alerts in database
    raw_count = db_session.query(RawAlert).filter(RawAlert.service == service_name).count()
    assert raw_count == 500

    # 2. Exactly 1 Core Incident created
    incidents = db_session.query(Incident).filter(Incident.service == service_name).all()
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.alert_count == 500
    assert incident.priority == "CRITICAL"
    assert incident.escalation_level == 1

    # 3. Exactly 1 Email Notification record
    email_notifs = db_session.query(NotificationRecord).filter(
        NotificationRecord.incident_id == incident.id,
        NotificationRecord.channel == "email"
    ).all()
    assert len(email_notifs) == 1
    assert email_notifs[0].status == "SENT"

    # 4. Exactly 1 Slack Notification record
    slack_notifs = db_session.query(NotificationRecord).filter(
        NotificationRecord.incident_id == incident.id,
        NotificationRecord.channel == "slack"
    ).all()
    assert len(slack_notifs) == 1
    assert slack_notifs[0].status == "SENT"

    # 5. Exactly 1 external delivery call each
    assert mock_email.call_count == 1
    assert mock_slack.chat_postMessage.call_count == 1

