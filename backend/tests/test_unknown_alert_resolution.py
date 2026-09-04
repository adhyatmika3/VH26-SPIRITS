import time
import pytest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.incident import Incident
from app.models.decision_record import DecisionRecord
from app.models.resolution_knowledge import ResolutionKnowledge
from app.services.ai_resolution_service import (
    AIResolutionPayload,
    validate_resolution_payload,
    extract_json_from_response
)
from app.services.resolution_service import resolve_unknown_alert_sync, get_resolution_for_incident


MOCK_DIAGNOSIS_DICT = {
    "probable_cause": "Upstream acquirer gateway timeout during peak TLS renegotiation handshake",
    "resolution": [
        "Inspect connection pool metrics for payment-api",
        "Enable payment gateway circuit-breaker failover",
        "Verify upstream acquirer status dashboard"
    ],
    "confidence": 0.94
}

VALID_PAYLOAD = {
    "source": "prometheus",
    "alert_name": "PaymentGatewayResponseAnomaly",
    "service": "payment-api",
    "resource": "pod-payment-1",
    "severity": "critical",
    "status": "firing",
    "timestamp": "2026-09-04T10:00:00Z",
    "labels": {
        "environment": "production",
        "cluster": "prod-us-east-1"
    },
    "annotations": {
        "description": "Upstream acquirer response signature mismatch"
    }
}


def test_unknown_alert_generates_ai_resolution_and_persists(client: TestClient, db_session: Session):
    """
    Verify that an unknown alert type triggers AI analysis, persists ResolutionKnowledge,
    and enriches DecisionRecord and Incident.
    """
    mock_diagnosis = AIResolutionPayload(**MOCK_DIAGNOSIS_DICT)

    with patch("app.services.resolution_service.generate_resolution_sync", return_value=mock_diagnosis) as mock_ai:
        resp = client.post("/api/v1/alerts/webhook", json=VALID_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert data["accepted"] is True

        # Verify AI service was invoked exactly once
        assert mock_ai.call_count == 1

    # Verify Knowledge Base persistence
    kb = db_session.execute(
        select(ResolutionKnowledge).where(ResolutionKnowledge.alert_type == "PaymentGatewayResponseAnomaly")
    ).scalars().first()
    assert kb is not None
    assert kb.probable_cause == MOCK_DIAGNOSIS_DICT["probable_cause"]
    assert len(kb.resolution_steps) == 3
    assert kb.confidence == 0.94
    assert kb.source == "automated_analysis"

    # Verify Incident state
    inc = db_session.execute(select(Incident)).scalars().first()
    assert inc is not None
    assert inc.resolution_status in ["RESOLVED", "KNOWN"]

    # Verify DecisionRecord context snapshot
    dr = db_session.execute(select(DecisionRecord)).scalars().first()
    assert dr is not None
    assert dr.context_snapshot.get("resolution_source") == "automated_analysis"
    assert dr.context_snapshot.get("ai_called") is True
    assert dr.context_snapshot.get("probable_cause") == MOCK_DIAGNOSIS_DICT["probable_cause"]


def test_subsequent_identical_alert_uses_knowledge_base_cache(client: TestClient, db_session: Session):
    """
    Verify that receiving a duplicate or subsequent alert with the same fingerprint
    reuses the stored ResolutionKnowledge without invoking the AI model again.
    """
    mock_diagnosis = AIResolutionPayload(**MOCK_DIAGNOSIS_DICT)

    # First alert: AI called
    with patch("app.services.resolution_service.generate_resolution_sync", return_value=mock_diagnosis) as mock_ai:
        resp1 = client.post("/api/v1/alerts/webhook", json=VALID_PAYLOAD)
        assert resp1.status_code == 201
        assert mock_ai.call_count == 1

    # Second alert: Knowledge Base should be used, AI must NOT be called
    with patch("app.services.resolution_service.generate_resolution_sync", return_value=mock_diagnosis) as mock_ai_second:
        resp2 = client.post("/api/v1/alerts/webhook", json=VALID_PAYLOAD)
        assert resp2.status_code == 201
        assert mock_ai_second.call_count == 0

    # Knowledge entry is retained
    kb = db_session.execute(
        select(ResolutionKnowledge).where(ResolutionKnowledge.alert_type == "PaymentGatewayResponseAnomaly")
    ).scalars().first()
    assert kb is not None


def test_concurrency_anti_throttling_guard(db_session: Session):
    """
    Verify concurrency protection: Multiple concurrent threads resolving
    the same fingerprint execute AI analysis at most once.
    """
    ai_call_counter = {"count": 0}

    def fake_ai_call(*args, **kwargs):
        time.sleep(0.05)  # Simulate API latency
        ai_call_counter["count"] += 1
        return AIResolutionPayload(**MOCK_DIAGNOSIS_DICT)

    fingerprint = "test_concurrent_fp_12345"

    with patch("app.services.resolution_service.generate_resolution_sync", side_effect=fake_ai_call):
        def worker():
            return resolve_unknown_alert_sync(
                db=db_session,
                fingerprint=fingerprint,
                alert_type="PaymentGatewayResponseAnomaly",
                service="payment-api",
                severity="critical",
                environment="production",
                message="Concurrent test burst",
                labels={"env": "prod"}
            )

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(worker) for _ in range(5)]
            results = [f.result() for f in futures]

    # All threads received resolution
    assert len(results) == 5
    for r in results:
        assert r.probable_cause == MOCK_DIAGNOSIS_DICT["probable_cause"]

    # Concurrency guard ensured AI was invoked exactly 1 time
    assert ai_call_counter["count"] == 1


def test_ai_graceful_fallback_on_api_failure(client: TestClient, db_session: Session):
    """
    Verify that if the AI service fails (network timeout, invalid key, 500 error),
    the core alert pipeline continues without interruption and records ANALYSIS_PENDING.
    """
    payload = {
        "source": "prometheus",
        "alert_name": "MysteriousKernelFault",
        "service": "checkout-service",
        "resource": "node-worker-9",
        "severity": "critical",
        "status": "firing",
        "timestamp": "2026-09-04T10:00:00Z",
        "labels": {"environment": "production"},
        "annotations": {"description": "Unknown kernel page fault panic"}
    }

    # Simulate AI returning None (failure / timeout)
    with patch("app.services.resolution_service.generate_resolution_sync", return_value=None):
        resp = client.post("/api/v1/alerts/webhook", json=payload)
        assert resp.status_code == 201

    # Incident created safely with ANALYSIS_PENDING status
    inc = db_session.execute(select(Incident).where(Incident.service == "checkout-service")).scalars().first()
    assert inc is not None
    assert inc.resolution_status == "ANALYSIS_PENDING"


def test_malformed_ai_payload_resilience():
    """
    Verify validation and parsing resilience
    when handling imperfect responses.
    """
    # Missing optional fields handled safely
    raw = {
        "probable_cause": "Database deadlocks in catalog table",
        "resolution": ["Kill long running transactions", "Restart connection pool"],
        "confidence": 0.88
    }
    diag = validate_resolution_payload(raw)
    assert diag is not None
    assert diag.confidence == 0.88
    assert len(diag.resolution) == 2

    # Malformed text parsing fallback
    text_content = '```json\n{"probable_cause": "Redis OOM", "resolution": ["Scale cluster", "Flush cache"], "confidence": 0.95}\n```'
    parsed = extract_json_from_response(text_content)
    assert parsed is not None
    assert parsed["probable_cause"] == "Redis OOM"
    assert len(parsed["resolution"]) == 2


def test_get_incident_resolution_api_endpoint(client: TestClient, db_session: Session):
    """
    Verify GET /api/v1/incidents/{incident_id}/resolution returns
    structured resolution diagnostics.
    """
    mock_diagnosis = AIResolutionPayload(**MOCK_DIAGNOSIS_DICT)

    with patch("app.services.resolution_service.generate_resolution_sync", return_value=mock_diagnosis):
        post_resp = client.post("/api/v1/alerts/webhook", json=VALID_PAYLOAD)
        assert post_resp.status_code == 201

    inc = db_session.execute(select(Incident)).scalars().first()
    assert inc is not None

    # Query resolution endpoint
    res_resp = client.get(f"/api/v1/incidents/{inc.id}/resolution")
    assert res_resp.status_code == 200
    res_data = res_resp.json()

    assert res_data["incident_id"] == str(inc.id)
    assert res_data["status"] in ["RESOLVED", "KNOWN"]
    assert res_data["probable_cause"] == MOCK_DIAGNOSIS_DICT["probable_cause"]
    assert len(res_data["resolution"]) == 3
    assert res_data["confidence"] == 0.94
    assert res_data["source"] in ["automated_analysis", "knowledge_base"]


def test_get_incident_resolution_not_found(client: TestClient):
    """
    Verify GET /api/v1/incidents/{incident_id}/resolution returns 404
    when an unknown UUID is supplied.
    """
    import uuid
    rand_id = uuid.uuid4()
    resp = client.get(f"/api/v1/incidents/{rand_id}/resolution")
    assert resp.status_code == 404
