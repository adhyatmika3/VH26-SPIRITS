import sys
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.raw_alert import RawAlert
from app.models.canonical_alert import CanonicalAlert
from app.models.incident import Incident
from app.models.decision_record import DecisionRecord
from app.models.notification_record import NotificationRecord
from app.schemas.webhook import AlertWebhookPayload
from app.services.alert_processor import process_alert_pipeline
from app.services.slack_retry_service import process_pending_slack_retries, get_pending_slack_notifications


def run_demonstration():
    print("=" * 80)
    print("PHASE 7: SLACK FAILURE FALLBACK & NOTIFICATION RESILIENCE DEMONSTRATION")
    print("=" * 80)

    db = SessionLocal()

    # -------------------------------------------------------------------------
    # SCENARIO A: SLACK HEALTHY
    # -------------------------------------------------------------------------
    print("\n" + "#" * 70)
    print(">>> SCENARIO A: SLACK HEALTHY (500 Alerts -> 1 Incident -> Critical)")
    print("#" * 70)

    svc_a = f"checkout-gateway-{uuid.uuid4().hex[:6]}"
    batch_size = 500
    now = datetime.now(timezone.utc)

    # Mock real email & healthy Slack delivery
    mock_email = {"status": "SENT", "destination": "sre-core@example.com", "payload": {}}
    mock_slack_client = MagicMock()
    mock_slack_client.chat_postMessage.return_value = {
        "ok": True,
        "ts": f"172550{int(time.time())}.000100"
    }

    print(f"[*] Ingesting {batch_size} critical alerts for service: [{svc_a}]...")
    start_a = time.perf_counter()

    with patch("app.services.email_notifier.send_email_notification", return_value=mock_email), \
         patch("app.services.slack_service.WebClient", return_value=mock_slack_client):

        last_result = None
        for i in range(batch_size):
            payload = AlertWebhookPayload(
                source="prometheus",
                alert_name=f"HighLatencySpike-{svc_a}",
                service=svc_a,
                resource="api-proxy",
                severity="critical",
                status="firing",
                timestamp=now,
                labels={"environment": "production", "alert_type": "LATENCY_CRITICAL"},
                annotations={"summary": f"High latency spike on {svc_a}"}
            )
            last_result = process_alert_pipeline(db=db, payload=payload)

    elapsed_a = time.perf_counter() - start_a
    inc_a = last_result.incident
    print(f"[+] 500 alerts processed in {elapsed_a:.2f}s (throughput: {batch_size/elapsed_a:.1f} alerts/sec)")

    # Verifications for Scenario A
    raw_alerts_a = db.query(RawAlert).filter(RawAlert.service == svc_a).count()
    incidents_a = db.query(Incident).filter(Incident.service == svc_a).all()
    assert len(incidents_a) == 1, f"Expected exactly 1 incident, found {len(incidents_a)}"
    incident_a = incidents_a[0]

    email_notifs_a = (
        db.query(NotificationRecord)
        .filter(NotificationRecord.incident_id == incident_a.id, NotificationRecord.channel == "email")
        .all()
    )
    slack_notifs_a = (
        db.query(NotificationRecord)
        .filter(NotificationRecord.incident_id == incident_a.id, NotificationRecord.channel == "slack")
        .all()
    )

    print(f"    - RawAlerts in DB:           {raw_alerts_a} (Expected: 500)")
    print(f"    - Correlated Incidents:     {len(incidents_a)} (ID: {incident_a.incident_number}, Priority: {incident_a.priority})")
    print(f"    - Email Notifications:      {len(email_notifs_a)} (Status: {email_notifs_a[0].status if email_notifs_a else 'NONE'})")
    print(f"    - Slack Notifications:      {len(slack_notifs_a)} (Status: {slack_notifs_a[0].status if slack_notifs_a else 'NONE'}, TS: {slack_notifs_a[0].slack_message_ts if slack_notifs_a else 'NONE'})")

    assert raw_alerts_a == 500
    assert incident_a.priority == "CRITICAL"
    assert len(email_notifs_a) == 1 and email_notifs_a[0].status in ("SENT", "DELIVERED")
    assert len(slack_notifs_a) == 1 and slack_notifs_a[0].status in ("SENT", "DELIVERED")
    print("[PASS] Scenario A completed successfully: Incident created, Email delivered, Slack delivered.")

    # -------------------------------------------------------------------------
    # SCENARIO B: SLACK DOWN
    # -------------------------------------------------------------------------
    print("\n" + "#" * 70)
    print(">>> SCENARIO B: SLACK DOWN (500 Alerts -> 1 Incident -> Slack Timeout/Outage)")
    print("#" * 70)

    svc_b = f"inventory-db-{uuid.uuid4().hex[:6]}"
    now_b = datetime.now(timezone.utc)

    # Slack is down: mock connection timeout
    mock_slack_down = MagicMock()
    mock_slack_down.chat_postMessage.side_effect = TimeoutError("Slack API connection timed out (endpoint down)")

    print(f"[*] Ingesting {batch_size} critical alerts for service: [{svc_b}] with SLACK UNREACHABLE...")
    start_b = time.perf_counter()

    with patch("app.services.email_notifier.send_email_notification", return_value=mock_email), \
         patch("app.services.slack_service.WebClient", return_value=mock_slack_down):

        last_result_b = None
        for i in range(batch_size):
            payload = AlertWebhookPayload(
                source="datadog",
                alert_name=f"DatabaseDeadlockStorm-{svc_b}",
                service=svc_b,
                resource="postgres-cluster",
                severity="critical",
                status="firing",
                timestamp=now_b,
                labels={"environment": "production", "alert_type": "DEADLOCK_CRITICAL"},
                annotations={"summary": f"Deadlock storm on {svc_b}"}
            )
            last_result_b = process_alert_pipeline(db=db, payload=payload)

    elapsed_b = time.perf_counter() - start_b
    print(f"[+] 500 alerts processed in {elapsed_b:.2f}s despite Slack outage")

    # Verifications for Scenario B
    raw_alerts_b = db.query(RawAlert).filter(RawAlert.service == svc_b).count()
    incidents_b = db.query(Incident).filter(Incident.service == svc_b).all()
    assert len(incidents_b) == 1, f"CRITICAL REQUIREMENT: Exactly 1 incident must exist, found {len(incidents_b)}"
    incident_b = incidents_b[0]

    email_notifs_b = (
        db.query(NotificationRecord)
        .filter(NotificationRecord.incident_id == incident_b.id, NotificationRecord.channel == "email")
        .all()
    )
    slack_notifs_b = (
        db.query(NotificationRecord)
        .filter(NotificationRecord.incident_id == incident_b.id, NotificationRecord.channel == "slack")
        .all()
    )

    print(f"    - RawAlerts in DB:           {raw_alerts_b} (Expected: 500)")
    print(f"    - Correlated Incidents:     {len(incidents_b)} (ID: {incident_b.incident_number}, Status: {incident_b.status}, Priority: {incident_b.priority})")
    print(f"    - Email Notifications:      {len(email_notifs_b)} (Status: {email_notifs_b[0].status if email_notifs_b else 'NONE'})")
    print(f"    - Slack Notifications:      {len(slack_notifs_b)} (Status: {slack_notifs_b[0].status if slack_notifs_b else 'NONE'}, Next Retry: {slack_notifs_b[0].next_retry_at.isoformat() if slack_notifs_b and slack_notifs_b[0].next_retry_at else 'NONE'})")
    print(f"    - Slack Error Captured:     {slack_notifs_b[0].last_error if slack_notifs_b else 'NONE'}")

    assert raw_alerts_b == 500
    assert incident_b is not None
    assert incident_b.priority == "CRITICAL"
    assert len(email_notifs_b) == 1 and email_notifs_b[0].status in ("SENT", "DELIVERED")
    assert len(slack_notifs_b) >= 1
    # Verify Slack notification was queued for retry
    retrying_slack_notif = slack_notifs_b[0]
    assert retrying_slack_notif.status == "RETRYING"
    assert retrying_slack_notif.is_transient is True
    assert retrying_slack_notif.next_retry_at is not None
    print("[PASS] Scenario B completed successfully: Incident is 100% DURABLE, Email delivered, Slack queued in RETRYING.")

    # -------------------------------------------------------------------------
    # SCENARIO C: SLACK RECOVERY
    # -------------------------------------------------------------------------
    print("\n" + "#" * 70)
    print(">>> SCENARIO C: SLACK RECOVERY (Slack Restored -> Retry Worker Executes -> DELIVERED)")
    print("#" * 70)

    # Advance next_retry_at to past so it triggers immediately
    retrying_slack_notif.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.add(retrying_slack_notif)
    db.commit()

    print(f"[*] Slack restored. Executing process_pending_slack_retries()...")

    mock_recovered_client = MagicMock()
    recovery_ts = f"172550{int(time.time())}.000250"
    mock_recovered_client.chat_postMessage.return_value = {
        "ok": True,
        "ts": recovery_ts
    }

    with patch("app.services.slack_service.WebClient", return_value=mock_recovered_client):
        retry_summary = process_pending_slack_retries(db=db, max_records=10)

    print(f"[+] Retry Worker Result: {retry_summary}")

    db.refresh(retrying_slack_notif)
    print(f"    - Notification ID:          {retrying_slack_notif.id}")
    print(f"    - Final Delivery Status:    {retrying_slack_notif.status}")
    print(f"    - Delivered At:             {retrying_slack_notif.delivered_at.isoformat() if retrying_slack_notif.delivered_at else 'NONE'}")
    print(f"    - Slack Message TS:         {retrying_slack_notif.slack_message_ts}")
    print(f"    - Next Retry At:            {retrying_slack_notif.next_retry_at}")
    print(f"    - Attempt Count:            {retrying_slack_notif.attempt_count}")

    assert retrying_slack_notif.status in ("SENT", "DELIVERED")
    assert retrying_slack_notif.delivered_at is not None
    assert retrying_slack_notif.slack_message_ts == recovery_ts
    assert retrying_slack_notif.next_retry_at is None
    print("[PASS] Scenario C completed successfully: Notification transitioned to DELIVERED with message ts recorded.")

    print("\n" + "=" * 80)
    print("ALL THREE PHASE 7 SCENARIOS VERIFIED END-TO-END:")
    print("  Scenario A: Slack Healthy     -> SUCCESS (Email & Slack delivered, 1 Incident)")
    print("  Scenario B: Slack Unavailable -> INCIDENT PRESERVED (Email delivered, Slack RETRYING)")
    print("  Scenario C: Slack Recovered   -> NOTIFICATION DELIVERED (Retry worker processed)")
    print("=" * 80)

    db.close()


if __name__ == "__main__":
    run_demonstration()
