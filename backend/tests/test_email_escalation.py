import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.raw_alert import RawAlert
from app.models.canonical_alert import CanonicalAlert
from app.models.incident import Incident
from app.models.decision_record import DecisionRecord
from app.models.notification_record import NotificationRecord
from app.services.risk_scoring import calculate_risk
from app.services.email_notifier import send_email_notification, build_email_content
from app.services.notification_service import dispatch_notification


# ---------------------------------------------------------------------------
# 1. Test Risk Scoring Breakdown for 500-Alert Critical Scenario
# ---------------------------------------------------------------------------
def test_risk_scoring_500_critical_payment_api():
    """
    Verify the 6-factor deterministic risk calculation for:
    service=payment-api, environment=production, severity=critical, occurrences=500.
    """
    now = datetime.now(timezone.utc)
    risk = calculate_risk(
        severity="critical",
        service="payment-api",
        occurrence_count=500,
        environment="production",
        first_seen=now,
        last_seen=now + timedelta(seconds=2)
    )

    # 1. Severity: critical = 30 pts
    assert risk.severity_score == 30
    # 2. Frequency: 500 / 0.1 min = 5000/min >= 10/min = 20 pts
    assert risk.frequency_score == 20
    # 3. Occurrences: 500 >= 500 = 15 pts
    assert risk.occurrence_score == 15
    # 4. Service Criticality: payment-api = 20 pts
    assert risk.service_score == 20
    # 5. Environment: production = 10 pts
    assert risk.environment_score == 10
    # 6. Duration: 2s < 60s = 1 pt
    assert risk.duration_score == 1

    # Total: 30 + 20 + 15 + 20 + 10 + 1 = 96 pts
    assert risk.score == 96
    assert risk.level == "CRITICAL"

    breakdown = risk.to_dict()["breakdown"]
    assert breakdown["severity"] == 30
    assert breakdown["frequency"] == 20
    assert breakdown["occurrences"] == 15
    assert breakdown["service"] == 20
    assert breakdown["environment"] == 10
    assert breakdown["duration"] == 1
    assert breakdown["total"] == 96


# ---------------------------------------------------------------------------
# 2. Test Email Notifier Content Construction
# ---------------------------------------------------------------------------
def test_build_email_content_contains_all_vital_fields():
    """Verify email builder populates all required telemetry and context."""
    now = datetime.now(timezone.utc)
    content = build_email_content(
        incident_number="INC-1050",
        incident_id="test-uuid-1234",
        service="payment-api",
        alert_type="CPU_HIGH",
        severity="critical",
        priority="CRITICAL",
        environment="production",
        occurrence_count=500,
        risk_score=96,
        risk_level="CRITICAL",
        first_seen=now,
        last_seen=now + timedelta(seconds=15),
        duration_str="15s",
        reason="Critical incident reached threshold (occurrences=10 >= 10). Escalating to Level 1.",
        reason_codes=["UNRESOLVED_CRITICAL", "HIGH_VELOCITY_BURST"],
        probable_cause="Upstream payment gateway timeout",
        resolution_steps=["Check payment-api pod metrics", "Scale replicas horizontally"]
    )

    assert "CRITICAL ESCALATION: [INC-1050]" in content["subject"]
    assert "INC-1050" in content["text"]
    assert "payment-api" in content["text"]
    assert "96 / 100 (CRITICAL)" in content["text"]
    assert "500 raw alerts consolidated" in content["text"]
    assert "Check payment-api pod metrics" in content["text"]
    assert "INC-1050" in content["html"]
    assert "payment-api" in content["html"]


# ---------------------------------------------------------------------------
# 3. Test Email Failure Handling when SMTP is unconfigured
# ---------------------------------------------------------------------------
def test_email_notifier_unconfigured_fails_gracefully():
    """Verify unconfigured SMTP returns FAILED status without crashing or faking success."""
    result = send_email_notification(
        incident_number="INC-1099",
        incident_id="test-id",
        service="payment-api",
        alert_type="CPU_HIGH",
        severity="critical",
        priority="CRITICAL",
        environment="production",
        occurrence_count=500,
        smtp_host=None,
        from_email=None,
        to_email=None
    )

    assert result["status"] == "FAILED"
    assert "SMTP configuration missing" in result["error"]
    assert "SMTP_HOST" in result["error"]


# ---------------------------------------------------------------------------
# 4. Test Email Sending Failure Handling (Socket / Connection Error)
# ---------------------------------------------------------------------------
def test_email_notifier_connection_error_handling():
    """Verify connection errors are caught, logged, and marked FAILED without raising."""
    with patch("smtplib.SMTP", side_effect=ConnectionRefusedError("Connection refused")):
        result = send_email_notification(
            incident_number="INC-1099",
            incident_id="test-id",
            service="payment-api",
            alert_type="CPU_HIGH",
            severity="critical",
            priority="CRITICAL",
            environment="production",
            occurrence_count=500,
            smtp_host="127.0.0.1",
            smtp_port=2525,
            from_email="alerts@company.internal",
            to_email="sre-oncall@company.internal"
        )

        assert result["status"] == "FAILED"
        assert "ConnectionRefusedError" in result["error"]


# ---------------------------------------------------------------------------
# 5. Test Duplicate Email Prevention (Idempotency)
# ---------------------------------------------------------------------------
def test_duplicate_email_prevention_idempotency(db_session: Session):
    """Verify that a second email dispatch for the same incident is prevented."""
    inc = Incident(
        incident_number=f"INC-{uuid.uuid4().hex[:6]}",
        title="Payment Api High CPU",
        service="payment-api",
        status="OPEN",
        priority="CRITICAL",
        alert_count=500,
        unique_alerts_count=1
    )
    db_session.add(inc)
    db_session.flush()

    dec = DecisionRecord(
        incident_id=inc.id,
        decision="ESCALATE",
        reason_codes=["UNRESOLVED_CRITICAL"],
        reason="Escalation threshold reached",
        context_snapshot={"service": "payment-api", "risk_score": 96, "risk_level": "CRITICAL"}
    )
    db_session.add(dec)
    db_session.flush()

    # Simulate first email was sent successfully
    with patch("app.services.email_notifier.send_email_notification", return_value={
        "status": "SENT",
        "destination": "sre@company.com",
        "error": None,
        "payload": {"channel": "email"}
    }):
        first_notif = dispatch_notification(
            db=db_session,
            decision_record=dec,
            incident=inc,
            notification_type="ESCALATION",
            channel="email"
        )
        assert first_notif.status == "SENT"
        assert first_notif.channel == "email"

    # Attempt second dispatch for same incident
    mock_send = MagicMock()
    with patch("app.services.email_notifier.send_email_notification", mock_send):
        second_notif = dispatch_notification(
            db=db_session,
            decision_record=dec,
            incident=inc,
            notification_type="ESCALATION",
            channel="email"
        )
        # Mock send was NEVER called because idempotency intercepted it
        mock_send.assert_not_called()
        # Returns the already existing record
        assert second_notif.id == first_notif.id
        assert second_notif.status == "SENT"


# ---------------------------------------------------------------------------
# 6. End-to-End Batch Test: 25 Alerts -> 1 Incident -> Risk & Escalation Record
# ---------------------------------------------------------------------------
def test_e2e_critical_alert_flow_preserves_raw_and_deduplicates(client: TestClient, db_session: Session):
    """
    Test alert webhook pipeline with multiple critical alerts:
    - Raw alerts preserved
    - 1 Core Incident created
    - Risk score computed and stored in DecisionRecord context_snapshot
    - Escalation record and exactly 1 email notification record created
    """
    service_name = "payment-api"
    total_alerts = 15

    with patch("app.services.email_notifier.send_email_notification", return_value={
        "status": "SENT",
        "destination": "oncall@company.com",
        "error": None,
        "payload": {"channel": "email"}
    }):
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
                    "alert_type": "CPU_HIGH",
                    "cluster": "prod-us-east"
                },
                "annotations": {
                    "summary": f"High CPU on {service_name}"
                }
            }
            resp = client.post("/api/v1/alerts/webhook", json=payload)
            assert resp.status_code == 201

    # 1. Exactly 15 raw alerts persisted in PostgreSQL
    raw_count = db_session.query(RawAlert).filter(RawAlert.service == service_name).count()
    assert raw_count == total_alerts

    # 2. Exactly 1 Core Incident created
    incidents = db_session.query(Incident).filter(Incident.service == service_name).all()
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.alert_count == total_alerts
    assert incident.priority == "CRITICAL"
    assert incident.escalation_level == 1

    # 3. DecisionRecord snapshot contains risk_score and risk_breakdown
    decisions = db_session.query(DecisionRecord).filter(DecisionRecord.incident_id == incident.id).all()
    assert len(decisions) == total_alerts

    escalate_dec = [d for d in decisions if d.decision == "ESCALATE"]
    assert len(escalate_dec) == 1
    assert "risk_score" in escalate_dec[0].context_snapshot
    # For payment-api at 10 occurrences: severity 30 + freq 20 + occ 5 + svc 20 + env 10 + dur 1 = 86 (CRITICAL)
    assert escalate_dec[0].context_snapshot["risk_score"] >= 81
    assert escalate_dec[0].context_snapshot["risk_level"] == "CRITICAL"

    # 4. Exactly 1 email notification record created for this incident
    email_notifs = db_session.query(NotificationRecord).filter(
        NotificationRecord.incident_id == incident.id,
        NotificationRecord.channel == "email"
    ).all()
    assert len(email_notifs) == 1
    assert email_notifs[0].status == "SENT"
    assert email_notifs[0].notification_type == "ESCALATION"
