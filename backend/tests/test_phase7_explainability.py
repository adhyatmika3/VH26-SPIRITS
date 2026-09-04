import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.canonical_alert import CanonicalAlert
from app.models.decision_record import DecisionRecord
from app.models.incident import Incident
from app.services.dashboard_service import (
    _translate_reason_code,
    _human_decision_label,
    calculate_decision_intelligence,
    explain_decision,
    REASON_CODE_TRANSLATIONS,
    DECISION_HUMAN_LABELS,
)


def test_phase7_reason_code_translations():
    """Verify that only actual reason codes exist and translate to clean human labels."""
    # All translated codes must be genuine system codes
    expected_codes = [
        "COOLDOWN_ACTIVE",
        "DUPLICATE_ALERT",
        "CORRELATED_INCIDENT_ACTIVE",
        "LOW_SEVERITY_NON_PROD",
        "ALERT_RESOLVED_INCIDENT_ACTIVE",
        "NEW_INCIDENT",
        "PRODUCTION_ENVIRONMENT",
        "CRITICAL_SEVERITY",
        "HIGH_SEVERITY",
        "MEDIUM_SEVERITY",
        "LOW_SEVERITY",
        "ERROR_SEVERITY",
        "WARNING_SEVERITY",
        "INFO_SEVERITY",
        "SEVERITY_INCREASED",
        "CRITICAL_PRIORITY",
        "ALERT_STORM_ACTIVE",
        "INCIDENT_RESOLVED",
        "INCIDENT_MANUALLY_RESOLVED",
        "MANUAL_OPERATOR_DISPATCH",
        "UNRESOLVED_CRITICAL",
        "ESCALATION_THRESHOLD_REACHED",
        "HIGH_VELOCITY_BURST",
        "ALREADY_ESCALATED",
        "ESCALATION_IDEMPOTENT_SKIP",
    ]
    for code in expected_codes:
        assert code in REASON_CODE_TRANSLATIONS
        translated = _translate_reason_code(code)
        assert translated != code
        assert len(translated) > 5


def test_phase7_decision_human_labels():
    """Verify primary labels adhere to human-friendly terminology."""
    assert _human_decision_label("SUPPRESS") == "Unnecessary Notification Prevented"
    assert _human_decision_label("NOTIFY") == "Actionable Alert Sent to Responder"
    assert _human_decision_label("ESCALATE") == "Incident Escalated to Tier-2"


def test_phase7_explain_endpoint_and_confidence_null(client: TestClient, db_session: Session):
    """
    Verify /dashboard/explain/{decision_id} returns:
    - Honest confidence: null (no manufactured 95% or 98%)
    - Ground-truth why from decision.reason
    - Factual evidence
    - Decision -> Incident trace
    """
    now = datetime.now(timezone.utc)
    dec = DecisionRecord(
        decision="SUPPRESS",
        reason_codes=["DUPLICATE_ALERT", "COOLDOWN_ACTIVE"],
        reason="Alert suppressed under active cooldown (5s / 300s) for incident [INC-9999].",
        context_snapshot={
            "service": "checkout-service",
            "environment": "production",
            "severity": "CRITICAL",
            "priority": "HIGH",
            "is_duplicate": True,
            "incident_number": "INC-9999",
            "occurrence_count": 3
        },
        processing_time_ms=24.5,
        created_at=now
    )
    db_session.add(dec)
    db_session.commit()
    db_session.refresh(dec)

    resp = client.get(f"/api/v1/dashboard/explain/{dec.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["decision"] == "SUPPRESS"
    assert "Notification Prevented" in data["what_happened"]
    assert "INC-9999" in data["why"]
    # Confidence MUST be null
    assert data["confidence"] is None
    # Evidence must contain verified facts
    assert any("checkout-service" in ev for ev in data["evidence"])
    assert any("production" in ev for ev in data["evidence"])
    assert any("DUPLICATE_ALERT" in ev for ev in data["evidence"])
    # Technical details
    tech = data["technical_details"]
    assert tech["raw_reason"] == dec.reason
    assert tech["processing_time_ms"] == 24.5
    assert "decision_trace" in tech
    trace = tech["decision_trace"]
    assert trace["decision"] == "SUPPRESS"
    assert trace["human_decision"] == "Unnecessary Notification Prevented"
    assert trace["related_incident"] == "INC-9999"


def test_phase7_decision_intelligence_endpoint(client: TestClient, db_session: Session):
    """
    Verify /dashboard/decision-intelligence endpoint:
    - Real breakdown counts and percentages
    - Top suppression reasons
    - Top notification reasons
    - Decision processing performance
    - Clear separation of operational outcomes
    """
    resp = client.get("/api/v1/dashboard/decision-intelligence")
    assert resp.status_code == 200
    data = resp.json()

    assert "has_data" in data
    assert "total_decisions" in data
    assert "breakdown" in data
    assert "top_suppression_reasons" in data
    assert "top_notification_reasons" in data
    assert "recent_decisions" in data
    assert "processing_performance" in data
    assert "outcomes" in data

    # Percentages must sum to 100% (within rounding) if decisions exist
    if data["total_decisions"] > 0:
        total_pct = sum(item["percentage"] for item in data["breakdown"] if item["percentage"] is not None)
        assert 99.0 <= total_pct <= 101.0

    # Processing performance must be non-negative
    perf = data["processing_performance"]
    if perf["total_decisions_with_timing"] > 0:
        assert perf["avg_processing_ms"] > 0
        assert perf["min_processing_ms"] <= perf["max_processing_ms"]

    # Outcomes must contain operational response metrics
    outcomes = data["outcomes"]
    assert "total_incidents" in outcomes
    assert "acknowledged_incidents" in outcomes
    assert "resolved_incidents" in outcomes
    assert "unresolved_incidents" in outcomes


def test_phase7_evidence_not_recorded_fallback():
    """Verify that if context and reasons are missing, 'Evidence not recorded' is returned instead of fake evidence."""
    now = datetime.now(timezone.utc)
    dec = DecisionRecord(
        decision="NOTIFY",
        reason_codes=[],
        reason=None,
        context_snapshot={},
        created_at=now
    )
    exp = explain_decision(dec)
    assert exp.evidence == ["Evidence not recorded"]
