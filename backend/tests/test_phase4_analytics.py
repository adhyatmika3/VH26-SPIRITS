import time
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.decision_record import DecisionRecord


def test_empty_database_analytics_overview(client: TestClient):
    """
    Ensures analytics endpoints gracefully handle zero-data states
    with safe division by zero and valid schema response.
    """
    for route in ["/api/v1/analytics/overview", "/api/analytics/overview"]:
        resp = client.get(route)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_alerts"] == 0
        assert data["processed_alerts"] == 0
        assert data["suppressed_alerts"] == 0
        assert data["notified_alerts"] == 0
        assert data["escalated_alerts"] == 0
        assert data["suppression_rate"] == 0.0
        assert data["notification_rate"] == 0.0
        assert data["escalation_rate"] == 0.0
        assert data["average_processing_time_ms"] == 0.0


def test_alert_processing_increments_prometheus_metrics(client: TestClient):
    """
    Verifies that raw alert ingestion and pipeline processing
    increment Prometheus counters and observe duration histograms.
    """
    alert_payload = {
        "source": "prometheus",
        "alert_name": "HighMemoryUsage",
        "severity": "high",
        "status": "firing",
        "service": "billing-service",
        "message": "Node memory utilization is 92%",
        "labels": {"environment": "production"},
        "annotations": {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    resp = client.post("/api/v1/alerts/webhook", json=alert_payload)
    assert resp.status_code == 201

    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    content = metrics_resp.text

    assert "alerts_received_total" in content
    assert "alerts_processed_total" in content
    assert "alert_processing_duration_seconds" in content
    assert "alerts_in_processing" in content


def test_analytics_overview_calculation_and_rates(client: TestClient, db_session: Session):
    """
    Ingests a mix of distinct alerts and duplicates to test
    suppression rate, notification count, and average processing latency.
    """
    base_time = datetime.now(timezone.utc)

    # Ingest initial alert -> NOTIFY
    payload_1 = {
        "source": "prometheus",
        "alert_name": "APIHighLatency",
        "severity": "critical",
        "status": "firing",
        "service": "api-gateway",
        "message": "Latency breached 800ms",
        "labels": {"environment": "production"},
        "annotations": {},
        "timestamp": base_time.isoformat()
    }
    r1 = client.post("/api/v1/alerts/webhook", json=payload_1)
    assert r1.status_code == 201

    # Ingest duplicate within cooldown -> SUPPRESS (deduplication / cooldown)
    payload_2 = {
        "source": "prometheus",
        "alert_name": "APIHighLatency",
        "severity": "critical",
        "status": "firing",
        "service": "api-gateway",
        "message": "Latency breached 800ms",
        "labels": {"environment": "production"},
        "annotations": {},
        "timestamp": (base_time + timedelta(seconds=10)).isoformat()
    }
    r2 = client.post("/api/v1/alerts/webhook", json=payload_2)
    assert r2.status_code == 201

    # Ingest distinct low severity alert
    payload_3 = {
        "source": "cloudwatch",
        "alert_name": "DiskUsageWarning",
        "severity": "low",
        "status": "firing",
        "service": "cache-service",
        "message": "Disk usage is 71%",
        "labels": {"environment": "production"},
        "annotations": {},
        "timestamp": base_time.isoformat()
    }
    r3 = client.post("/api/v1/alerts/webhook", json=payload_3)
    assert r3.status_code == 201

    resp = client.get("/api/v1/analytics/overview")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_alerts"] >= 3
    assert data["processed_alerts"] >= 3
    assert data["suppressed_alerts"] >= 1
    assert data["notified_alerts"] >= 1
    assert data["suppression_rate"] > 0.0
    assert data["notification_rate"] > 0.0
    assert data["average_processing_time_ms"] >= 0.0
    assert "active_dedupe_pool" in data
    assert data["active_dedupe_pool"] >= 1


def test_analytics_severity_distribution(client: TestClient):
    """
    Tests grouping and percentage calculation across severity levels.
    """
    for sev in ["critical", "high", "low"]:
        r = client.post("/api/v1/alerts/webhook", json={
            "source": "prometheus",
            "alert_name": f"TestAlert_{sev}",
            "severity": sev,
            "status": "firing",
            "service": "worker-pool",
            "message": f"Test alert for {sev}",
            "labels": {"environment": "staging"},
            "annotations": {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        assert r.status_code == 201

    resp = client.get("/api/v1/analytics/alerts-by-severity")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 3

    severities = {item["severity"].upper() for item in items}
    assert "CRITICAL" in severities
    assert "ERROR" in severities
    assert "INFO" in severities

    for item in items:
        assert item["count"] >= 1
        assert 0.0 <= item["percentage"] <= 100.0


def test_analytics_source_distribution(client: TestClient):
    """
    Tests grouping and percentage calculation across alert sources.
    """
    for src in ["datadog", "grafana"]:
        r = client.post("/api/v1/alerts/webhook", json={
            "source": src,
            "alert_name": f"SourceAlert_{src}",
            "severity": "medium",
            "status": "firing",
            "service": "auth-service",
            "message": "Source test message",
            "labels": {"environment": "production"},
            "annotations": {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        assert r.status_code == 201

    resp = client.get("/api/v1/analytics/alerts-by-source")
    assert resp.status_code == 200
    sources = resp.json()
    source_names = {s["source"] for s in sources}
    assert "datadog" in source_names or "grafana" in source_names


def test_analytics_noisy_services_ranking(client: TestClient):
    """
    Verifies that top noisy services are ranked by total alert volume
    and accurately compute per-service suppression rates.
    """
    # Send 3 alerts for payment-service
    for i in range(3):
        r = client.post("/api/v1/alerts/webhook", json={
            "source": "prometheus",
            "alert_name": f"PaymentTimeout_{i}",
            "severity": "high",
            "status": "firing",
            "service": "payment-service",
            "message": f"Payment failure {i}",
            "labels": {"environment": "production"},
            "annotations": {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        assert r.status_code == 201

    # Send 1 alert for notification-service
    r = client.post("/api/v1/alerts/webhook", json={
        "source": "prometheus",
        "alert_name": "EmailQueueLag",
        "severity": "medium",
        "status": "firing",
        "service": "email-service",
        "message": "Email queue lag",
        "labels": {"environment": "production"},
        "annotations": {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    assert r.status_code == 201

    resp = client.get("/api/v1/analytics/noisy-services?limit=5")
    assert resp.status_code == 200
    services = resp.json()
    assert len(services) >= 1

    # Payment service should have higher volume
    payment_entry = next((s for s in services if s["service"] == "payment-service"), None)
    assert payment_entry is not None
    assert payment_entry["total_alerts"] >= 3
    assert payment_entry["suppression_rate"] >= 0.0


def test_analytics_timeline_and_intervals(client: TestClient):
    """
    Tests time-series bucketed aggregation across intervals.
    """
    r = client.post("/api/v1/alerts/webhook", json={
        "source": "prometheus",
        "alert_name": "TimelineTestAlert",
        "severity": "medium",
        "status": "firing",
        "service": "order-service",
        "message": "Timeline test",
        "labels": {"environment": "production"},
        "annotations": {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    assert r.status_code == 201

    # Hourly interval
    resp_hour = client.get("/api/v1/analytics/timeline?interval=hour")
    assert resp_hour.status_code == 200
    points_hour = resp_hour.json()
    assert len(points_hour) >= 1
    assert "timestamp" in points_hour[0]
    assert "received" in points_hour[0]

    # Minute interval
    resp_min = client.get("/api/v1/analytics/timeline?interval=minute")
    assert resp_min.status_code == 200
    points_min = resp_min.json()
    assert len(points_min) >= 1


def test_analytics_decisions_endpoint(client: TestClient):
    """
    Tests /api/v1/analytics/decisions aggregation.
    """
    r = client.post("/api/v1/alerts/webhook", json={
        "source": "prometheus",
        "alert_name": "DecisionTestAlert",
        "severity": "critical",
        "status": "firing",
        "service": "database-proxy",
        "message": "Connection count high",
        "labels": {"environment": "production"},
        "annotations": {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    assert r.status_code == 201

    resp = client.get("/api/v1/analytics/decisions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert (data["suppressed"] + data["notified"] + data["escalated"]) == data["total"]


def test_analytics_time_range_presets(client: TestClient):
    """
    Tests time_range query parameter presets (1h, 24h, 7d, 30d).
    """
    for tr in ["1h", "24h", "7d", "30d"]:
        resp = client.get(f"/api/v1/analytics/overview?time_range={tr}")
        assert resp.status_code == 200
        assert "total_alerts" in resp.json()


def test_decision_record_stores_latency(client: TestClient, db_session: Session):
    """
    Verifies that DecisionRecord persists processing_time_ms in milliseconds.
    """
    r = client.post("/api/v1/alerts/webhook", json={
        "source": "prometheus",
        "alert_name": "LatencyValidationAlert",
        "severity": "high",
        "status": "firing",
        "service": "search-indexer",
        "message": "Indexing lagging behind",
        "labels": {"environment": "production"},
        "annotations": {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    assert r.status_code == 201

    rec = db_session.query(DecisionRecord).order_by(DecisionRecord.created_at.desc()).first()
    assert rec is not None
    assert rec.processing_time_ms is not None
    assert rec.processing_time_ms >= 0.0


def test_prometheus_metrics_audit_and_bounded_labels(client: TestClient):
    """
    Audits all 12 required Prometheus metrics and verifies bounded label sanitization.
    """
    # Ingest alert with long arbitrary service name
    long_service = "order-checkout-payment-microservice-instance-very-long-99999"
    r = client.post("/api/v1/alerts/webhook", json={
        "source": "prometheus",
        "alert_name": "LabelAuditAlert",
        "severity": "critical",
        "status": "firing",
        "service": long_service,
        "message": "Testing bounded labels",
        "labels": {"environment": "production"},
        "annotations": {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    assert r.status_code == 201

    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    content = metrics_resp.text

    # All 12 required metrics must exist
    required_metrics = [
        "alerts_received_total",
        "alerts_processed_total",
        "alerts_decided_total",
        "alerts_suppressed_total",
        "alerts_notified_total",
        "alerts_escalated_total",
        "notification_success_total",
        "notification_failures_total",
        "alert_processing_failures_total",
        "alerts_in_processing",
        "alert_processing_duration_seconds",
        "notification_duration_seconds"
    ]
    for metric_name in required_metrics:
        assert metric_name in content, f"Expected metric '{metric_name}' in /metrics"

    # Verify that long service label was safely bounded to <= 32 characters
    assert long_service not in content
    bounded_service = long_service[:32]
    assert bounded_service in content
