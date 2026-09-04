import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BeforeAfterMetrics(BaseModel):
    """
    Before vs After comparison. All values are computed from actual database records.
    No hardcoded performance numbers.
    """
    without_platform_interruptions: int = Field(
        default=0,
        description="Raw alerts received (without the platform, every raw alert would be a pager interruption)"
    )
    with_platform_notifications: int = Field(
        default=0,
        description="Actionable notifications actually sent to human responders via Slack"
    )
    noise_reduction_percent: float = Field(
        default=0.0,
        description="Percentage of alert noise eliminated: (suppressed / total) * 100"
    )
    estimated_attention_avoided_hours: float = Field(
        default=0.0,
        description="ESTIMATE: suppressed_alerts * configurable_handling_time_minutes / 60. Labeled as an estimate."
    )
    handling_time_assumption_minutes: float = Field(
        default=10.0,
        description="Configurable assumed average handling time per alert in minutes. Used for estimated_attention_avoided_hours."
    )
    mtta_seconds: float = Field(
        default=0.0,
        description="Actual average time to acknowledge from database records (seconds)"
    )
    has_sufficient_data: bool = Field(
        default=False,
        description="True if sufficient alert data exists to render meaningful Before/After metrics"
    )


class DashboardSummaryResponse(BaseModel):
    """
    Dashboard summary with clearly defined metric calculations.
    Every value comes from actual PostgreSQL queries with zero fabrication.

    Metric Definitions:
    - total_alerts: COUNT of rows in raw_alerts table (every incoming webhook event)
    - unique_canonical_alerts: COUNT of rows in canonical_alerts table (unique fingerprints)
    - repeated_alert_occurrences: SUM(occurrence_count - 1) across canonical alerts where count > 1
    - related_alerts_grouped: COUNT of canonical alerts that have been linked to an incident
    - suppressed_alerts: COUNT of decision records where decision = 'SUPPRESS'
    - notified_alerts: COUNT of decision records where decision = 'NOTIFY'
    - noise_reduction_rate: (suppressed_alerts / total_alerts) * 100 if total_alerts > 0, else 0
    - active_incidents: COUNT of incidents where status IN ('OPEN', 'ACKNOWLEDGED')
    - active_dedupe_pool: COUNT of DISTINCT fingerprints across non-resolved canonical alerts
    - mtta_seconds: AVG(acknowledged_at - first_seen) across incidents with acknowledgement
    - mttr_seconds: AVG(resolved_at - first_seen) across resolved incidents
    """
    total_alerts: int = Field(..., description="Raw Alerts Received: Total incoming webhook events stored")
    unique_canonical_alerts: int = Field(..., description="Unique Alerts: Distinct fingerprints after deduplication")
    repeated_alert_occurrences: int = Field(..., description="Repeated Alert Occurrences: Extra duplicate events coalesced into existing fingerprints")
    related_alerts_grouped: int = Field(..., description="Alerts Grouped: Canonical alerts correlated and linked to incidents")
    suppressed_alerts: int = Field(..., description="Alerts Suppressed: Decision records where decision was SUPPRESS")
    notified_alerts: int = Field(..., description="Notifications Sent: Decision records where decision was NOTIFY")
    active_incidents: int = Field(..., description="Incidents Created: Currently open or acknowledged incidents")
    noise_reduction_rate: float = Field(..., description="Noise reduction: (suppressed / total_alerts) * 100")
    mtta_seconds: float = Field(..., description="Average Time to Acknowledge from actual incident data (seconds)")
    mtta_formatted: str = Field(..., description="Human-friendly formatted MTTA (e.g. '3m 20s') or 'Awaiting data'")
    mttr_seconds: float = Field(..., description="Average Time to Resolve from actual incident data (seconds)")
    mttr_formatted: str = Field(..., description="Human-friendly formatted MTTR or 'Awaiting data'")
    active_dedupe_pool: int = Field(default=0, description="Active unique fingerprints in deduplication window")
    has_sufficient_data: bool = Field(default=False, description="True if there is at least 1 processed alert in the database")
    before_after: BeforeAfterMetrics = Field(default_factory=BeforeAfterMetrics)


class DecisionExplanationResponse(BaseModel):
    """
    Explainable decision. Confidence is QUALITATIVE (High/Medium/Low)
    unless derived from actual deterministic evidence.
    """
    decision_id: uuid.UUID
    canonical_alert_id: Optional[uuid.UUID] = None
    incident_id: Optional[uuid.UUID] = None
    decision: str
    what_happened: str = Field(..., description="Plain-English verdict of what the system did")
    why: str = Field(..., description="Context-aware reasoning in plain English")
    confidence: Optional[float] = Field(None, description="Confidence score (null for deterministic rule evaluation, no fabricated numbers)")
    confidence_label: Optional[str] = Field(None, description="Qualitative confidence indicator")
    evidence: List[str] = Field(default_factory=list, description="Specific evidence behind the decision")
    technical_details: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TimelineEventItem(BaseModel):
    id: str
    timestamp: datetime
    formatted_time: str
    stage: str
    label: str
    description: str
    status: str
    actor: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IncidentTimelineResponse(BaseModel):
    incident_id: uuid.UUID
    incident_number: str
    title: str
    service: str
    priority: str
    status: str
    total_alerts_count: int
    created_at: datetime
    events: List[TimelineEventItem]


# =====================================================
# PHASE 7: DECISION INTELLIGENCE SCHEMAS
# =====================================================

class DecisionBreakdownItem(BaseModel):
    """Count and percentage for a single decision type."""
    decision_type: str = Field(..., description="NOTIFY, SUPPRESS, ESCALATE, or other")
    human_label: str = Field(..., description="Human-friendly label e.g. 'Unnecessary Notification Prevented'")
    count: int = Field(..., description="Actual count from decision_records table")
    percentage: Optional[float] = Field(None, description="Percentage of total decisions. Null if total is 0.")


class ReasonCountItem(BaseModel):
    """A single reason_code and its occurrence count."""
    reason_code: str = Field(..., description="Raw technical reason code from decision engine")
    human_label: str = Field(..., description="Plain-English translation of the reason code")
    count: int = Field(..., description="Number of decisions with this reason code")


class DecisionExplorerItem(BaseModel):
    """A single row in the Decision Explorer table."""
    decision_record_id: uuid.UUID
    timestamp: datetime
    alert_id: Optional[uuid.UUID] = None
    alert_name: Optional[str] = None
    service: Optional[str] = None
    severity: Optional[str] = None
    decision: str
    human_decision: str = Field(..., description="Human-friendly decision label")
    reason_summary: str = Field(..., description="Short human-readable reason")
    incident_id: Optional[uuid.UUID] = None


class ProcessingPerformanceMetrics(BaseModel):
    """Decision processing time statistics from real processing_time_ms values."""
    total_decisions_with_timing: int = Field(0, description="Count of decisions that have processing_time_ms recorded")
    avg_processing_ms: Optional[float] = Field(None, description="Average processing time in milliseconds. Null if no data.")
    min_processing_ms: Optional[float] = Field(None, description="Fastest decision in milliseconds. Null if no data.")
    max_processing_ms: Optional[float] = Field(None, description="Slowest decision in milliseconds. Null if no data.")


class OutcomeMetrics(BaseModel):
    """Decision quality / outcome metrics from real incident data."""
    total_incidents: int = 0
    acknowledged_incidents: int = 0
    resolved_incidents: int = 0
    unresolved_incidents: int = 0
    mtta_seconds: Optional[float] = Field(None, description="Avg time to acknowledge. Null if no acknowledged incidents.")
    mtta_formatted: Optional[str] = Field(None, description="Human-friendly MTTA or null.")
    mttr_seconds: Optional[float] = Field(None, description="Avg time to resolve. Null if no resolved incidents.")
    mttr_formatted: Optional[str] = Field(None, description="Human-friendly MTTR or null.")


class DecisionIntelligenceResponse(BaseModel):
    """
    Phase 7: Complete decision intelligence payload.
    Every value is derived from actual PostgreSQL data.
    No fabricated metrics, percentages, or confidence scores.
    """
    has_data: bool = Field(False, description="True if at least 1 decision record exists")
    total_decisions: int = Field(0, description="Total decision records in database")

    # Decision breakdown
    breakdown: List[DecisionBreakdownItem] = Field(default_factory=list)

    # Top reasons alerts were suppressed
    top_suppression_reasons: List[ReasonCountItem] = Field(default_factory=list)

    # Why alerts reached responders
    top_notification_reasons: List[ReasonCountItem] = Field(default_factory=list)

    # Recent decisions for explorer table
    recent_decisions: List[DecisionExplorerItem] = Field(default_factory=list)

    # Processing performance
    processing_performance: ProcessingPerformanceMetrics = Field(default_factory=ProcessingPerformanceMetrics)

    # Outcome metrics
    outcomes: OutcomeMetrics = Field(default_factory=OutcomeMetrics)
