import uuid
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.incident import Incident
from app.models.canonical_alert import CanonicalAlert
from app.models.decision_record import DecisionRecord
from app.models.notification_record import NotificationRecord
from app.schemas.webhook import AlertWebhookPayload
from app.services.alert_processor import process_alert_pipeline


def test_dashboard_summary_empty(client: TestClient):
    """Verify dashboard summary returns valid zero-state metrics without errors."""
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_alerts"] == 0
    assert data["unique_canonical_alerts"] == 0
    assert data["repeated_alert_occurrences"] == 0
    assert data["suppressed_alerts"] == 0
    assert data["notified_alerts"] == 0
    assert data["noise_reduction_rate"] == 0.0
    assert data["has_sufficient_data"] is False
    assert data["mtta_formatted"] == "Awaiting data"
    assert data["mttr_formatted"] == "Awaiting data"
    assert "before_after" in data
    ba = data["before_after"]
    assert ba["has_sufficient_data"] is False
    assert ba["estimated_attention_avoided_hours"] == 0.0


def test_dashboard_summary_with_real_pipeline(client: TestClient, db_session: Session):
    """
    Ingest a sequence of alerts through the real pipeline:
    - 1 critical alert (Notified, Incident created)
    - 2 duplicate occurrences of the same alert (Coalesced via deduplication)
    - 1 low priority alert (Suppressed)
    Verify dashboard summary aggregates match database state exactly.
    """
    now = datetime.now(timezone.utc)

    # 1. Critical alert
    res1 = process_alert_pipeline(
        db=db_session,
        payload=AlertWebhookPayload(
            source="datadog",
            alert_name="Payment DB CPU High",
            service="payment-api",
            severity="CRITICAL",
            status="firing",
            timestamp=now,
            labels={"environment": "production", "cluster": "us-east-prod-k8s"},
            annotations={"summary": "Payment DB CPU at 96%"}
        )
    )
    assert res1.decision == "NOTIFY"

    # 2 & 3. Two duplicates (should be SUPPRESSED under active cooldown on same service)
    res2 = process_alert_pipeline(
        db=db_session,
        payload=AlertWebhookPayload(
            source="datadog",
            alert_name="Payment DB CPU High",
            service="payment-api",
            severity="CRITICAL",
            status="firing",
            timestamp=now,
            labels={"environment": "production", "cluster": "us-east-prod-k8s"},
            annotations={"summary": "Payment DB CPU at 97%"}
        )
    )
    assert res2.is_duplicate is True
    assert res2.decision == "SUPPRESS"

    res3 = process_alert_pipeline(
        db=db_session,
        payload=AlertWebhookPayload(
            source="datadog",
            alert_name="Payment DB CPU High",
            service="payment-api",
            severity="CRITICAL",
            status="firing",
            timestamp=now,
            labels={"environment": "production", "cluster": "us-east-prod-k8s"},
            annotations={"summary": "Payment DB CPU at 98%"}
        )
    )
    assert res3.is_duplicate is True
    assert res3.decision == "SUPPRESS"

    # 4. Low priority alert in dev/staging (non-prod) -> Suppressed
    res4 = process_alert_pipeline(
        db=db_session,
        payload=AlertWebhookPayload(
            source="cloudwatch",
            alert_name="Log Rotation Notice",
            service="worker-service",
            severity="LOW",
            status="firing",
            timestamp=now,
            labels={"environment": "staging", "cluster": "us-east-stage-k8s"},
            annotations={"summary": "Routine log rotation executed"}
        )
    )
    assert res4.decision == "SUPPRESS"

    # Fetch summary
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    summary = resp.json()

    assert summary["total_alerts"] == 4
    assert summary["repeated_alert_occurrences"] == 2
    assert summary["suppressed_alerts"] == 3
    assert summary["notified_alerts"] == 1
    assert summary["active_incidents"] >= 1
    assert summary["noise_reduction_rate"] == 75.0
    assert summary["has_sufficient_data"] is True

    # Verify Before vs After uses actual data, not fabricated
    ba = summary["before_after"]
    assert ba["without_platform_interruptions"] == 4
    assert ba["with_platform_notifications"] == 1
    assert ba["noise_reduction_percent"] == 75.0
    assert ba["has_sufficient_data"] is True


def test_mtta_and_mttr_calculation(client: TestClient, db_session: Session):
    """Verify MTTA and MTTR calculations accurately reflect incident acknowledgment and resolution durations."""
    t0 = datetime(2026, 9, 4, 10, 0, 0, tzinfo=timezone.utc)
    t_ack = t0 + timedelta(minutes=4, seconds=30)
    t_res = t0 + timedelta(minutes=25, seconds=0)

    inc = Incident(
        incident_number="INC-TEST-MTTA",
        title="Test Latency Incident",
        service="order-service",
        priority="HIGH",
        status="RESOLVED",
        first_seen=t0,
        last_seen=t_res,
        acknowledged_at=t_ack,
        acknowledged_by="alice@company.com",
        resolved_at=t_res,
        resolved_by="bob@company.com",
        created_at=t0
    )
    db_session.add(inc)
    db_session.commit()

    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()

    # 4m 30s = 270 seconds
    assert data["mtta_seconds"] == 270.0
    assert data["mtta_formatted"] == "4m 30s"

    # 25m = 1500 seconds
    assert data["mttr_seconds"] == 1500.0
    assert data["mttr_formatted"] == "25m"


def test_explain_decision(client: TestClient, db_session: Session):
    """
    Verify explainable decision endpoint produces:
    - Plain-English what/why
    - Qualitative confidence label (High/Medium/Low) not fabricated percentages
    - Evidence list
    """
    dec_id = uuid.uuid4()
    dec = DecisionRecord(
        id=dec_id,
        decision="SUPPRESS",
        reason_codes=["DUPLICATE_ALERT", "COOLDOWN_ACTIVE"],
        reason="Duplicate alert within sliding window",
        context_snapshot={"service": "checkout-api", "priority": "HIGH"},
        processing_time_ms=1.45,
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(dec)
    db_session.commit()

    resp = client.get(f"/api/v1/dashboard/explain/{dec_id}")
    assert resp.status_code == 200
    exp = resp.json()

    assert exp["decision"] == "SUPPRESS"
    assert "Notification Prevented" in exp["what_happened"]
    assert "checkout-api" in exp["why"]
    # Qualitative confidence, not arbitrary percentages
    assert exp["confidence_label"] in ("High", "Medium", "Low")
    assert isinstance(exp["evidence"], list)
    assert len(exp["evidence"]) > 0
    assert "reason_codes" in exp["technical_details"]


def test_incident_timeline(client: TestClient, db_session: Session):
    """Verify incident timeline synthesizes chronological stages properly."""
    t0 = datetime.now(timezone.utc) - timedelta(minutes=10)
    inc = Incident(
        incident_number="INC-TIMELINE-1",
        title="Payment Service Degradation",
        service="payment-api",
        priority="CRITICAL",
        status="ACKNOWLEDGED",
        alert_count=5,
        unique_alerts_count=2,
        first_seen=t0,
        last_seen=t0 + timedelta(minutes=2),
        acknowledged_at=t0 + timedelta(minutes=4),
        acknowledged_by="oncall-engineer",
        created_at=t0
    )
    db_session.add(inc)
    db_session.commit()

    # Add a decision
    dec = DecisionRecord(
        incident_id=inc.id,
        decision="NOTIFY",
        reason_codes=["CRITICAL_SERVICE_DEGRADATION"],
        reason="P99 latency threshold breached",
        created_at=t0 + timedelta(seconds=1)
    )
    db_session.add(dec)

    # Add a notification
    notif = NotificationRecord(
        incident_id=inc.id,
        channel="sre-alerts",
        destination="#sre-alerts",
        status="SENT",
        sent_at=t0 + timedelta(seconds=2)
    )
    db_session.add(notif)
    db_session.commit()


    resp = client.get(f"/api/v1/dashboard/timeline/{inc.id}")
    assert resp.status_code == 200
    timeline = resp.json()

    assert timeline["incident_number"] == "INC-TIMELINE-1"
    events = timeline["events"]
    assert len(events) >= 5

    stages = [e["stage"] for e in events]
    assert "INGESTION" in stages
    assert "DEDUPLICATION" in stages
    assert "CORRELATION" in stages
    assert "DECISION" in stages
    assert "NOTIFICATION" in stages
    assert "ACKNOWLEDGEMENT" in stages

    # Check chronological ordering
    timestamps = [e["timestamp"] for e in events]
    assert timestamps == sorted(timestamps)



