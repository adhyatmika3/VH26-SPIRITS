import uuid
import time
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
    classify_slack_error,
    send_incident_notification,
    check_slack_health
)
from app.services.slack_retry_service import (
    calculate_backoff_delay,
    schedule_next_retry,
    process_pending_slack_retries,
    get_pending_slack_notifications
)
from app.services.notification_service import dispatch_notification
from app.services.alert_processor import process_alert_pipeline


# ---------------------------------------------------------------------------
# Test 1 — Slack Success: CRITICAL incident -> Slack succeeds -> DELIVERED
# ---------------------------------------------------------------------------
def test_slack_success_notification_delivered(monkeypatch, db_session: Session, client: TestClient):
    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-real-test-token")
    monkeypatch.setattr(settings, "SLACK_CHANNEL_ID", "C12345678")

    mock_client = MagicMock()
    mock_client.chat_postMessage.return_value = {"ok": True, "ts": "1725500000.000100"}

    with patch("app.services.slack_service.WebClient", return_value=mock_client):
        payload = {
            "source": "prometheus",
            "alert_name": f"SlackSuccessTest-{uuid.uuid4().hex[:6]}",
            "service": "checkout-service",
            "resource": "api-gateway",
            "severity": "critical",
            "status": "firing",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "labels": {"environment": "production"},
            "annotations": {"summary": "Payment gateway latency critical"}
        }
        resp = client.post("/api/v1/alerts/webhook", json=payload)
        assert resp.status_code == 201
        data = resp.json()

        # Verify incident exists
        incident_id = uuid.UUID(data["incident_id"])
        incident = db_session.query(Incident).filter(Incident.id == incident_id).first()
        assert incident is not None

        # Verify Slack notification record exists with status SENT / DELIVERED
        notif = (
            db_session.query(NotificationRecord)
            .filter(
                NotificationRecord.incident_id == incident.id,
                NotificationRecord.channel == "slack"
            )
            .first()
        )
        assert notif is not None
        assert notif.status in ("DELIVERED", "SENT")
        assert notif.slack_message_ts == "1725500000.000100"
        assert notif.delivered_at is not None
        assert notif.attempt_count == 1


# ---------------------------------------------------------------------------
# Test 2 — Slack Timeout: Preserves incident and marks RETRYING
# ---------------------------------------------------------------------------
def test_slack_timeout_preserves_incident_and_schedules_retry(monkeypatch, db_session: Session, client: TestClient):
    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-real-test-token")
    monkeypatch.setattr(settings, "SLACK_CHANNEL_ID", "C12345678")

    mock_client = MagicMock()
    mock_client.chat_postMessage.side_effect = TimeoutError("Slack API network connection timed out")

    with patch("app.services.slack_service.WebClient", return_value=mock_client):
        payload = {
            "source": "datadog",
            "alert_name": f"TimeoutResilienceTest-{uuid.uuid4().hex[:6]}",
            "service": "order-service",
            "resource": "order-db",
            "severity": "critical",
            "status": "firing",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "labels": {"environment": "production"},
            "annotations": {"summary": "High query timeout"}
        }
        resp = client.post("/api/v1/alerts/webhook", json=payload)
        # Pipeline must NOT fail; HTTP 201 returned
        assert resp.status_code == 201
        data = resp.json()

        # Core incident was committed and preserved
        incident_id = uuid.UUID(data["incident_id"])
        incident = db_session.query(Incident).filter(Incident.id == incident_id).first()
        assert incident is not None

        # Slack notification marked RETRYING with next_retry_at scheduled
        notif = (
            db_session.query(NotificationRecord)
            .filter(
                NotificationRecord.incident_id == incident.id,
                NotificationRecord.channel == "slack"
            )
            .first()
        )
        assert notif is not None
        assert notif.status == "RETRYING"
        assert notif.is_transient is True
        assert notif.next_retry_at is not None
        assert notif.last_error is not None
        assert "timed out" in notif.last_error.lower()


# ---------------------------------------------------------------------------
# Test 3 — Slack 500: HTTP 500 preserves incident and schedules retry
# ---------------------------------------------------------------------------
def test_slack_500_server_error_schedules_retry(monkeypatch, db_session: Session, client: TestClient):
    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-real-test-token")
    monkeypatch.setattr(settings, "SLACK_CHANNEL_ID", "C12345678")

    class MockSlack500Response:
        status_code = 500
        headers = {}
        data = {"ok": False, "error": "service_unavailable"}
        def get(self, key, default=None):
            return self.data.get(key, default)

    mock_client = MagicMock()
    mock_client.chat_postMessage.side_effect = SlackApiError(
        message="The request to the Slack API failed.",
        response=MockSlack500Response()
    )

    with patch("app.services.slack_service.WebClient", return_value=mock_client):
        payload = {
            "source": "cloudwatch",
            "alert_name": f"Slack500Test-{uuid.uuid4().hex[:6]}",
            "service": "auth-service",
            "resource": "jwt-issuer",
            "severity": "critical",
            "status": "firing",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "labels": {"environment": "production"},
            "annotations": {"summary": "Auth token issue"}
        }
        resp = client.post("/api/v1/alerts/webhook", json=payload)
        assert resp.status_code == 201

        notif = (
            db_session.query(NotificationRecord)
            .filter(
                NotificationRecord.destination == "C12345678",
                NotificationRecord.channel == "slack"
            )
            .order_by(NotificationRecord.created_at.desc())
            .first()
        )
        assert notif is not None
        assert notif.status == "RETRYING"
        assert notif.is_transient is True
        assert notif.next_retry_at is not None


# ---------------------------------------------------------------------------
# Test 4 — Slack 429: HTTP 429 rate limit respects Retry-After
# ---------------------------------------------------------------------------
def test_slack_429_rate_limit_respects_retry_after(monkeypatch, db_session: Session, client: TestClient):
    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-real-test-token")
    monkeypatch.setattr(settings, "SLACK_CHANNEL_ID", "C12345678")

    class MockSlack429Response:
        status_code = 429
        headers = {"Retry-After": "25"}
        data = {"ok": False, "error": "ratelimited"}
        def get(self, key, default=None):
            return self.data.get(key, default)

    mock_client = MagicMock()
    mock_client.chat_postMessage.side_effect = SlackApiError(
        message="Rate limit exceeded",
        response=MockSlack429Response()
    )

    with patch("app.services.slack_service.WebClient", return_value=mock_client):
        payload = {
            "source": "prometheus",
            "alert_name": f"Slack429RateLimitTest-{uuid.uuid4().hex[:6]}",
            "service": "payment-service",
            "resource": "stripe-connector",
            "severity": "critical",
            "status": "firing",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "labels": {"environment": "production"},
            "annotations": {"summary": "Payment webhook delay"}
        }
        resp = client.post("/api/v1/alerts/webhook", json=payload)
        assert resp.status_code == 201

        notif = (
            db_session.query(NotificationRecord)
            .filter(
                NotificationRecord.destination == "C12345678",
                NotificationRecord.channel == "slack"
            )
            .order_by(NotificationRecord.created_at.desc())
            .first()
        )
        assert notif is not None
        assert notif.status == "RETRYING"
        assert notif.is_transient is True
        # Verify Retry-After: delay should be ~25s in future
        delta = (notif.next_retry_at - notif.created_at).total_seconds()
        assert 20 <= delta <= 30


# ---------------------------------------------------------------------------
# Test 5 — Permanent Slack Failure: invalid_auth marks FAILED without retry loop
# ---------------------------------------------------------------------------
def test_slack_permanent_failure_marks_failed(monkeypatch, db_session: Session, client: TestClient):
    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-invalid-token")
    monkeypatch.setattr(settings, "SLACK_CHANNEL_ID", "C12345678")

    class MockSlackAuthErrorResponse:
        status_code = 401
        headers = {}
        data = {"ok": False, "error": "invalid_auth"}
        def get(self, key, default=None):
            return self.data.get(key, default)

    mock_client = MagicMock()
    mock_client.chat_postMessage.side_effect = SlackApiError(
        message="Invalid token",
        response=MockSlackAuthErrorResponse()
    )

    with patch("app.services.slack_service.WebClient", return_value=mock_client):
        payload = {
            "source": "prometheus",
            "alert_name": f"PermanentFailTest-{uuid.uuid4().hex[:6]}",
            "service": "billing-service",
            "resource": "invoice-gen",
            "severity": "critical",
            "status": "firing",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "labels": {"environment": "production"},
            "annotations": {"summary": "Invoice generation stalled"}
        }
        resp = client.post("/api/v1/alerts/webhook", json=payload)
        assert resp.status_code == 201

        notif = (
            db_session.query(NotificationRecord)
            .filter(
                NotificationRecord.destination == "C12345678",
                NotificationRecord.channel == "slack"
            )
            .order_by(NotificationRecord.created_at.desc())
            .first()
        )
        assert notif is not None
        assert notif.status == "FAILED"
        assert notif.is_transient is False
        assert notif.next_retry_at is None  # No retry scheduled for permanent failure


# ---------------------------------------------------------------------------
# Test 6 — Slack Completely Down: Incident succeeds and Email still delivered
# ---------------------------------------------------------------------------
def test_slack_completely_down_preserves_incident_and_email(monkeypatch, db_session: Session, client: TestClient):
    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-real-test-token")
    monkeypatch.setattr(settings, "SLACK_CHANNEL_ID", "C12345678")
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "ALERT_EMAIL_TO", "sre-resilience@example.com")

    # Slack is completely unreachable (ConnectionRefusedError)
    mock_slack = MagicMock()
    mock_slack.chat_postMessage.side_effect = ConnectionRefusedError("Slack servers unreachable")

    # Email succeeds
    mock_email_result = {
        "status": "SENT",
        "error": None,
        "destination": "sre-resilience@example.com",
        "payload": {"subject": "Critical Alert"}
    }

    with patch("app.services.slack_service.WebClient", return_value=mock_slack), \
         patch("app.services.email_notifier.send_email_notification", return_value=mock_email_result):

        svc_name = f"k8s-ingress-{uuid.uuid4().hex[:6]}"
        incident_id = None
        for i in range(12):
            payload = {
                "source": "prometheus",
                "alert_name": f"HighCpuLoad-{svc_name}",
                "service": svc_name,
                "resource": "ingress-pod-1",
                "severity": "critical",
                "status": "firing",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "labels": {"environment": "production", "alert_type": "CPU_HIGH"},
                "annotations": {"summary": f"Connection storm on {svc_name}"}
            }
            resp = client.post("/api/v1/alerts/webhook", json=payload)
            assert resp.status_code == 201
            data = resp.json()
            incident_id = uuid.UUID(data["incident_id"])

        # Core incident was committed and preserved!
        incident = db_session.query(Incident).filter(Incident.id == incident_id).first()
        assert incident is not None

        # Email was delivered!
        email_notif = (
            db_session.query(NotificationRecord)
            .filter(
                NotificationRecord.incident_id == incident.id,
                NotificationRecord.channel == "email"
            )
            .first()
        )
        assert email_notif is not None
        assert email_notif.status in ("SENT", "DELIVERED")

        # Slack failed independently and is in RETRYING state
        slack_notif = (
            db_session.query(NotificationRecord)
            .filter(
                NotificationRecord.incident_id == incident.id,
                NotificationRecord.channel == "slack"
            )
            .first()
        )
        assert slack_notif is not None
        assert slack_notif.status == "RETRYING"


# ---------------------------------------------------------------------------
# Test 7 — Recovery: Retry worker executes and delivers pending notification
# ---------------------------------------------------------------------------
def test_slack_recovery_worker_delivers_pending(monkeypatch, db_session: Session):
    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-real-test-token")
    monkeypatch.setattr(settings, "SLACK_CHANNEL_ID", "C12345678")

    # Create an incident and a RETRYING notification with next_retry_at in the past
    now = datetime.now(timezone.utc)
    inc = Incident(
        incident_number=f"INC-{uuid.uuid4().hex[:6].upper()}",
        service="recovery-test-service",
        title="Recovery Test Incident",
        priority="CRITICAL",
        status="TRIGGERED"
    )
    db_session.add(inc)
    db_session.flush()

    notif = NotificationRecord(
        incident_id=inc.id,
        channel="slack",
        destination="C12345678",
        notification_type="INITIAL",
        status="RETRYING",
        payload={"text": "Test Slack message payload"},
        attempt_count=1,
        created_at=now - timedelta(minutes=5),
        last_attempt_at=now - timedelta(minutes=5),
        next_retry_at=now - timedelta(minutes=1),  # Ready for retry!
        is_transient=True,
        last_error="Temporary Slack 503 outage"
    )
    db_session.add(notif)
    db_session.commit()

    # Slack is now recovered and returns success
    mock_client = MagicMock()
    mock_client.chat_postMessage.return_value = {"ok": True, "ts": "1725500999.000200"}

    with patch("app.services.slack_service.WebClient", return_value=mock_client):
        res = process_pending_slack_retries(db=db_session, max_records=10)
        assert res["delivered"] >= 1

        db_session.refresh(notif)
        assert notif.status in ("SENT", "DELIVERED")
        assert notif.slack_message_ts == "1725500999.000200"
        assert notif.delivered_at is not None
        assert notif.next_retry_at is None
        assert notif.last_error is None


# ---------------------------------------------------------------------------
# Test 8 — Duplicate Retry Protection: Delivered message is not resent
# ---------------------------------------------------------------------------
def test_duplicate_retry_protection(monkeypatch, db_session: Session):
    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-real-test-token")
    monkeypatch.setattr(settings, "SLACK_CHANNEL_ID", "C12345678")

    now = datetime.now(timezone.utc)
    inc = Incident(
        incident_number=f"INC-{uuid.uuid4().hex[:6].upper()}",
        service="dup-test-service",
        title="Duplicate Test Incident",
        priority="CRITICAL",
        status="TRIGGERED"
    )
    db_session.add(inc)
    db_session.flush()

    # Record that already has slack_message_ts and delivered_at but state was accidentally pending
    notif = NotificationRecord(
        incident_id=inc.id,
        channel="slack",
        destination="C12345678",
        notification_type="INITIAL",
        status="PENDING",
        payload={"text": "Test Duplicate Slack message"},
        attempt_count=1,
        created_at=now - timedelta(minutes=2),
        delivered_at=now - timedelta(minutes=1),
        slack_message_ts="1725500888.000300",
        next_retry_at=now - timedelta(seconds=10)
    )
    db_session.add(notif)
    db_session.commit()

    mock_client = MagicMock()
    with patch("app.services.slack_service.WebClient", return_value=mock_client):
        res = process_pending_slack_retries(db=db_session, max_records=10)
        # Verify duplicate protection skipped the send
        assert res["skipped_duplicate"] >= 1
        mock_client.chat_postMessage.assert_not_called()

        db_session.refresh(notif)
        assert notif.status in ("SENT", "DELIVERED")


# ---------------------------------------------------------------------------
# Test 9 — Health Check: Reports Slack Degraded without crashing application
# ---------------------------------------------------------------------------
def test_health_check_reports_slack_degraded(monkeypatch, client: TestClient):
    monkeypatch.setattr(settings, "SLACK_ENABLED", True)
    monkeypatch.setattr(settings, "SLACK_BOT_TOKEN", "xoxb-test-token")

    mock_client = MagicMock()
    mock_client.auth_test.side_effect = ConnectionError("Slack API down")

    with patch("app.services.slack_service.WebClient", return_value=mock_client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"  # Application is healthy!
        assert data["database"] == "healthy"
        assert data["slack"] == "degraded"  # Slack dependency is degraded
