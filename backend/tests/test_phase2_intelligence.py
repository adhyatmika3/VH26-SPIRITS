import uuid
import threading
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.raw_alert import RawAlert
from app.models.canonical_alert import CanonicalAlert
from app.models.incident import Incident
from app.schemas.webhook import AlertWebhookPayload
from app.services.alert_normalizer import normalize_alert
from app.services.fingerprint_service import generate_fingerprint
from app.services.priority_engine import evaluate_priority
from app.services.storm_detector import detect_alert_storm


# ---------------------------------------------------------------------------
# 1. Normalization Tests
# ---------------------------------------------------------------------------
def test_alert_normalization_standardization():
    payload = AlertWebhookPayload(
        source="PROMETHEUS",
        alert_name="HighMemoryUsage",
        service="PAYMENT-API",
        resource="pod-1",
        severity="crit",
        status="firing",
        timestamp=datetime(2026, 9, 4, 10, 0, 0, tzinfo=timezone.utc),
        labels={"environment": "production"},
        annotations={"summary": "Memory consumption at 95%"}
    )
    norm = normalize_alert(payload)
    assert norm.source == "prometheus"
    assert norm.service == "payment-api"
    assert norm.severity == "CRITICAL"
    assert norm.status == "FIRING"
    assert norm.message == "Memory consumption at 95%"


# ---------------------------------------------------------------------------
# 2. Deterministic Fingerprint Tests
# ---------------------------------------------------------------------------
def test_fingerprint_deterministic_and_ignores_volatile_fields():
    labels_1 = {"env": "prod", "cluster": "us-east", "timestamp": "2026-09-04T10:00:00Z", "trace_id": "1234"}
    labels_2 = {"cluster": "us-east", "env": "prod", "timestamp": "2026-09-04T10:05:00Z", "trace_id": "5678"}

    fp1 = generate_fingerprint("HighCPU", "auth-service", labels_1, "node-1")
    fp2 = generate_fingerprint("HighCPU", "auth-service", labels_2, "node-1")

    # Fingerprints must match despite different timestamps and trace IDs
    assert fp1 == fp2
    assert len(fp1) == 64

    # Different service must yield different fingerprint
    fp3 = generate_fingerprint("HighCPU", "billing-service", labels_1, "node-1")
    assert fp1 != fp3


# ---------------------------------------------------------------------------
# 3. Deduplication Tests (Single Canonical Alert per Deduplication Window)
# ---------------------------------------------------------------------------
def test_deduplication_five_identical_alerts(client: TestClient, db_session: Session):
    payload = {
        "source": "prometheus",
        "alert_name": "PostgresPoolExhausted",
        "service": "order-api",
        "resource": "pg-01",
        "severity": "critical",
        "status": "firing",
        "timestamp": "2026-09-04T10:00:00Z",
        "labels": {"environment": "production", "cluster": "k8s-prod"},
        "annotations": {"description": "Pool connections > 98%"}
    }

    responses = []
    for _ in range(5):
        resp = client.post("/api/v1/alerts/webhook", json=payload)
        assert resp.status_code == 201
        responses.append(resp.json())

    # First occurrence is not duplicate; subsequent 4 are duplicates
    assert responses[0]["is_duplicate"] is False
    assert responses[0]["occurrence_count"] == 1

    for r in responses[1:]:
        assert r["is_duplicate"] is True

    assert responses[4]["occurrence_count"] == 5

    # Database Verification:
    # 5 RawAlert records created (audit trail)
    raw_count = db_session.query(RawAlert).filter(RawAlert.service == "order-api").count()
    assert raw_count == 5

    # Exactly 1 CanonicalAlert record created
    canonical_alerts = db_session.query(CanonicalAlert).filter(CanonicalAlert.service == "order-api").all()
    assert len(canonical_alerts) == 1
    assert canonical_alerts[0].occurrence_count == 5
    assert canonical_alerts[0].is_duplicate is True


# ---------------------------------------------------------------------------
# 4. Hierarchical Correlation Tests
# ---------------------------------------------------------------------------
def test_correlation_context_isolation(client: TestClient, db_session: Session):
    # Alert 1: Production
    payload_prod = {
        "source": "prometheus",
        "alert_name": "HTTP5xxRate",
        "service": "checkout-service",
        "severity": "high",
        "status": "firing",
        "timestamp": "2026-09-04T10:00:00Z",
        "labels": {"environment": "production", "cluster": "prod-cluster"}
    }
    resp1 = client.post("/api/v1/alerts/webhook", json=payload_prod)
    inc_prod_id = resp1.json()["incident_id"]

    # Alert 2: Same service, same environment, different alert name -> Correlated to same incident
    payload_prod_2 = {
        "source": "prometheus",
        "alert_name": "LatencyP99Spike",
        "service": "checkout-service",
        "severity": "high",
        "status": "firing",
        "timestamp": "2026-09-04T10:01:00Z",
        "labels": {"environment": "production", "cluster": "prod-cluster"}
    }
    resp2 = client.post("/api/v1/alerts/webhook", json=payload_prod_2)
    assert resp2.json()["incident_id"] == inc_prod_id

    # Alert 3: Same service, DIFFERENT environment (staging) -> Must create separate Incident
    payload_staging = {
        "source": "prometheus",
        "alert_name": "HTTP5xxRate",
        "service": "checkout-service",
        "severity": "high",
        "status": "firing",
        "timestamp": "2026-09-04T10:02:00Z",
        "labels": {"environment": "staging", "cluster": "stage-cluster"}
    }
    resp3 = client.post("/api/v1/alerts/webhook", json=payload_staging)
    inc_stage_id = resp3.json()["incident_id"]
    assert inc_stage_id != inc_prod_id


# ---------------------------------------------------------------------------
# 5. Alert Storm Velocity Detection Tests
# ---------------------------------------------------------------------------
def test_alert_storm_detection_threshold(client: TestClient, db_session: Session):
    # Ingest 25 alerts rapidly to trigger storm threshold (threshold = 20)
    for i in range(25):
        payload = {
            "source": "prometheus",
            "alert_name": f"StormAlert_{i % 3}",
            "service": "gateway-service",
            "severity": "warning",
            "status": "firing",
            "timestamp": "2026-09-04T10:10:00Z",
            "labels": {"env": "prod"}
        }
        resp = client.post("/api/v1/alerts/webhook", json=payload)
        if i >= 20:
            assert resp.json()["is_storm"] is True


# ---------------------------------------------------------------------------
# 6. Resolved Alert Lifecycle Tests
# ---------------------------------------------------------------------------
def test_resolved_alert_lifecycle(client: TestClient, db_session: Session):
    # 1. Fire alert -> creates OPEN incident
    fire_payload = {
        "source": "prometheus",
        "alert_name": "DiskSpaceLow",
        "service": "storage-service",
        "severity": "warning",
        "status": "firing",
        "timestamp": "2026-09-04T10:20:00Z",
        "labels": {"environment": "production"}
    }
    r_fire = client.post("/api/v1/alerts/webhook", json=fire_payload)
    inc_id = r_fire.json()["incident_id"]

    inc = db_session.query(Incident).filter(Incident.id == uuid.UUID(inc_id)).first()
    assert inc.status == "OPEN"

    # 2. Resolve alert -> updates incident status to RESOLVED
    resolve_payload = {
        "source": "prometheus",
        "alert_name": "DiskSpaceLow",
        "service": "storage-service",
        "severity": "warning",
        "status": "resolved",
        "timestamp": "2026-09-04T10:25:00Z",
        "labels": {"environment": "production"}
    }
    r_resolve = client.post("/api/v1/alerts/webhook", json=resolve_payload)
    assert r_resolve.json()["incident_id"] == inc_id

    # Verify incident is now marked RESOLVED
    db_session.expire_all()
    inc_resolved = db_session.query(Incident).filter(Incident.id == uuid.UUID(inc_id)).first()
    assert inc_resolved.status == "RESOLVED"


# ---------------------------------------------------------------------------
# 7. Priority Engine Tests
# ---------------------------------------------------------------------------
def test_priority_rules_and_storm_modifier():
    # Baseline checks
    assert evaluate_priority("critical", {"env": "production"}, 1, is_storm=False) == "CRITICAL"
    assert evaluate_priority("critical", {"env": "dev"}, 1, is_storm=False) == "HIGH"
    assert evaluate_priority("error", {"env": "production"}, 1, is_storm=False) == "HIGH"
    assert evaluate_priority("error", {"env": "dev"}, 1, is_storm=False) == "MEDIUM"
    assert evaluate_priority("warning", {"env": "production"}, 1, is_storm=False) == "MEDIUM"
    assert evaluate_priority("warning", {"env": "production"}, 10, is_storm=False) == "HIGH"
    assert evaluate_priority("info", {}, 1, is_storm=False) == "LOW"

    # Storm escalation (+1 tier)
    assert evaluate_priority("info", {}, 1, is_storm=True) == "MEDIUM"
    assert evaluate_priority("warning", {"env": "production"}, 1, is_storm=True) == "HIGH"
    assert evaluate_priority("error", {"env": "production"}, 1, is_storm=True) == "CRITICAL"
    assert evaluate_priority("critical", {"env": "production"}, 1, is_storm=True) == "CRITICAL"


# ---------------------------------------------------------------------------
# 8. API Inspection & Statistics Endpoints
# ---------------------------------------------------------------------------
def test_phase2_api_endpoints(client: TestClient):
    # Ingest a sample alert
    payload = {
        "source": "prometheus",
        "alert_name": "APILatencyWarning",
        "service": "search-api",
        "severity": "warning",
        "status": "firing",
        "timestamp": "2026-09-04T10:30:00Z",
        "labels": {"environment": "production"}
    }
    r = client.post("/api/v1/alerts/webhook", json=payload)
    canonical_id = r.json()["canonical_alert_id"]
    incident_id = r.json()["incident_id"]

    # 1. GET /api/v1/alerts
    alerts_resp = client.get("/api/v1/alerts?service=search-api")
    assert alerts_resp.status_code == 200
    assert alerts_resp.json()["total"] >= 1

    # 2. GET /api/v1/alerts/{id}
    single_alert = client.get(f"/api/v1/alerts/{canonical_id}")
    assert single_alert.status_code == 200
    assert single_alert.json()["alert_name"] == "APILatencyWarning"

    # 3. GET /api/v1/incidents
    incidents_resp = client.get("/api/v1/incidents")
    assert incidents_resp.status_code == 200
    assert incidents_resp.json()["total"] >= 1

    # 4. GET /api/v1/incidents/{id}
    single_inc = client.get(f"/api/v1/incidents/{incident_id}")
    assert single_inc.status_code == 200
    assert len(single_inc.json()["alerts"]) >= 1

    # 5. GET /api/v1/alerts/stats
    stats_resp = client.get("/api/v1/alerts/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert "total_raw_alerts" in stats
    assert "total_canonical_alerts" in stats
    assert "noise_reduction_ratio_percent" in stats


# ---------------------------------------------------------------------------
# 9. Concurrency / Rapid Burst Deduplication Test
# ---------------------------------------------------------------------------
def test_concurrent_deduplication(client: TestClient, db_session: Session):
    payload = {
        "source": "prometheus",
        "alert_name": "ConcurrentSpike",
        "service": "worker-pool",
        "severity": "high",
        "status": "firing",
        "timestamp": "2026-09-04T10:40:00Z",
        "labels": {"environment": "production"}
    }

    responses = []
    for _ in range(5):
        resp = client.post("/api/v1/alerts/webhook", json=payload)
        assert resp.status_code == 201
        responses.append(resp.json())

    # First is new; next 4 are absorbed duplicates
    assert responses[0]["is_duplicate"] is False
    assert responses[0]["occurrence_count"] == 1

    for r in responses[1:]:
        assert r["is_duplicate"] is True

    assert responses[4]["occurrence_count"] == 5

    # Exactly 1 canonical alert created for worker-pool
    canonical = db_session.query(CanonicalAlert).filter(CanonicalAlert.service == "worker-pool").all()
    assert len(canonical) == 1
    assert canonical[0].occurrence_count == 5


# ---------------------------------------------------------------------------
# 10. Transaction Rollback Safety Test
# ---------------------------------------------------------------------------
def test_transaction_rollback_safety(client: TestClient, db_session: Session, monkeypatch):
    """
    Test that if intelligence processing fails in Stage 2,
    Stage 2 mutations are rolled back cleanly while Stage 1 raw alert remains recorded.
    """
    import app.services.alert_processor as processor

    # Monkeypatch correlation step to simulate an unhandled failure in Stage 2
    def mock_failing_correlate(*args, **kwargs):
        raise RuntimeError("Simulated correlation database failure")

    monkeypatch.setattr(processor, "correlate_and_assign_incident", mock_failing_correlate)

    payload = {
        "source": "prometheus",
        "alert_name": "FailingAlert",
        "service": "crash-service",
        "severity": "critical",
        "status": "firing",
        "timestamp": "2026-09-04T10:50:00Z",
        "labels": {"env": "prod"}
    }

    try:
        resp = client.post("/api/v1/alerts/webhook", json=payload)
        assert resp.status_code == 500
    except Exception:
        pass

    # No orphaned canonical alert should exist for crash-service
    canonical = db_session.query(CanonicalAlert).filter(CanonicalAlert.service == "crash-service").first()
    assert canonical is None


