import re
from typing import Optional
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

# Bounded label dictionaries and sanitizers to prevent high-cardinality label explosion
CONTROLLED_REASON_CODES = {
    "NEW_INCIDENT", "CRITICAL_SEVERITY", "ERROR_SEVERITY", "HIGH_SEVERITY",
    "WARNING_SEVERITY", "INFO_SEVERITY", "PRODUCTION_ENVIRONMENT", "ALERT_STORM_ACTIVE",
    "LOW_SEVERITY_NON_PROD", "INCIDENT_RESOLVED", "ALERT_RESOLVED_INCIDENT_ACTIVE",
    "SEVERITY_INCREASED", "CRITICAL_PRIORITY", "COOLDOWN_ACTIVE", "DUPLICATE_ALERT",
    "CORRELATED_INCIDENT_ACTIVE", "UNRESOLVED_CRITICAL", "ESCALATION_THRESHOLD_REACHED",
    "HIGH_VELOCITY_BURST", "ALREADY_ESCALATED", "ESCALATION_IDEMPOTENT_SKIP", "UNKNOWN"
}


def sanitize_service_label(service: Optional[str]) -> str:
    """
    Ensures bounded cardinality for service label in Prometheus.
    Cleans, strips non-identifier chars, and bounds length to prevent metric explosion.
    """
    if not service:
        return "unknown"
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "", str(service).lower().strip())
    if len(clean) > 32:
        return clean[:32]
    return clean or "unknown"


def sanitize_reason_code_label(reason: Optional[str]) -> str:
    """
    Ensures bounded cardinality for reason_code label in Prometheus.
    Only allows recognized structured decision reason codes, mapping arbitrary values to OTHER.
    """
    if not reason:
        return "UNKNOWN"
    clean = str(reason).upper().strip()
    return clean if clean in CONTROLLED_REASON_CODES else "OTHER"


# Ingestion & Processing Counters
ALERTS_RECEIVED_TOTAL = Counter(
    "alerts_received_total",
    "Total count of raw alerts ingested into the platform",
    ["source", "severity"]
)

ALERTS_PROCESSED_TOTAL = Counter(
    "alerts_processed_total",
    "Total count of alerts processed through the intelligence pipeline",
    ["source", "severity", "decision"]
)

ALERT_PROCESSING_FAILURES_TOTAL = Counter(
    "alert_processing_failures_total",
    "Total count of failures encountered during alert processing pipeline",
    ["stage"]
)

# Decision Metrics
ALERTS_DECIDED_TOTAL = Counter(
    "alerts_decided_total",
    "Total count of alert decisions evaluated by Decision Engine",
    ["decision", "severity", "environment", "service"]
)

ALERTS_SUPPRESSED_TOTAL = Counter(
    "alerts_suppressed_total",
    "Total count of alerts suppressed by Decision Engine",
    ["reason_code", "service"]
)

ALERTS_NOTIFIED_TOTAL = Counter(
    "alerts_notified_total",
    "Total count of alerts approved for notification",
    ["priority", "channel", "service"]
)

ALERTS_ESCALATED_TOTAL = Counter(
    "alerts_escalated_total",
    "Total count of alerts escalated to higher urgency",
    ["severity", "service"]
)

# Notification Delivery Metrics
NOTIFICATION_SUCCESS_TOTAL = Counter(
    "notification_success_total",
    "Total successful notification deliveries",
    ["channel"]
)

NOTIFICATION_FAILURE_TOTAL = Counter(
    "notification_failure_total",
    "Total failed notification delivery attempts",
    ["channel"]
)

NOTIFICATION_FAILURES_TOTAL = Counter(
    "notification_failures_total",
    "Total notification delivery failure count",
    ["channel"]
)

# Processing Latency Histograms
ALERT_PROCESSING_DURATION_SECONDS = Histogram(
    "alert_processing_duration_seconds",
    "Time required to process an alert through the intelligence pipeline",
    ["stage"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0)
)

NOTIFICATION_DURATION_SECONDS = Histogram(
    "notification_duration_seconds",
    "Time taken to deliver notification to downstream channel",
    ["channel"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)
)

# Active State Gauges
ALERTS_IN_PROCESSING = Gauge(
    "alerts_in_processing",
    "Current count of alerts actively undergoing processing in pipeline"
)

ACTIVE_INCIDENTS_GAUGE = Gauge(
    "active_incidents_count",
    "Current count of open or in-progress incidents"
)

# Lifecycle Metrics
ALERT_ACKNOWLEDGEMENTS_TOTAL = Counter(
    "alert_acknowledgements_total",
    "Total incidents or alerts acknowledged by operators",
    ["service"]
)

ALERT_RESOLUTIONS_TOTAL = Counter(
    "alert_resolutions_total",
    "Total incidents or alerts resolved",
    ["service"]
)


def record_received_metric(source: str, severity: str) -> None:
    ALERTS_RECEIVED_TOTAL.labels(
        source=(source or "unknown").lower(),
        severity=(severity or "medium").upper()
    ).inc()


def record_processed_metric(source: str, severity: str, decision: str) -> None:
    ALERTS_PROCESSED_TOTAL.labels(
        source=(source or "unknown").lower(),
        severity=(severity or "medium").upper(),
        decision=(decision or "unknown").upper()
    ).inc()


def record_processing_failure_metric(stage: str) -> None:
    ALERTS_IN_PROCESSING._value.set(max(0, ALERTS_IN_PROCESSING._value.get() - 1)) if hasattr(ALERTS_IN_PROCESSING, "_value") else None
    ALERT_PROCESSING_FAILURES_TOTAL.labels(
        stage=(stage or "unknown").lower()
    ).inc()


def record_processing_duration(stage: str, duration: float) -> None:
    ALERT_PROCESSING_DURATION_SECONDS.labels(
        stage=(stage or "pipeline").lower()
    ).observe(duration)


def record_notification_duration(channel: str, duration: float) -> None:
    NOTIFICATION_DURATION_SECONDS.labels(
        channel=(channel or "slack").lower()
    ).observe(duration)


def record_decision_metric(decision: str, severity: str, environment: str, service: str, reason_codes: list[str]) -> None:
    clean_svc = sanitize_service_label(service)
    ALERTS_DECIDED_TOTAL.labels(
        decision=decision.upper(),
        severity=severity.upper(),
        environment=environment.lower(),
        service=clean_svc
    ).inc()

    if decision.upper() == "SUPPRESS":
        raw_reason = reason_codes[0] if reason_codes else "UNKNOWN"
        bounded_reason = sanitize_reason_code_label(raw_reason)
        ALERTS_SUPPRESSED_TOTAL.labels(
            reason_code=bounded_reason,
            service=clean_svc
        ).inc()


def record_notification_metric(channel: str, success: bool, priority: str = "MEDIUM", service: str = "unknown") -> None:
    ch = (channel or "slack").lower()
    clean_svc = sanitize_service_label(service)
    if success:
        NOTIFICATION_SUCCESS_TOTAL.labels(channel=ch).inc()
        ALERTS_NOTIFIED_TOTAL.labels(
            priority=(priority or "MEDIUM").upper(),
            channel=ch,
            service=clean_svc
        ).inc()
    else:
        NOTIFICATION_FAILURE_TOTAL.labels(channel=ch).inc()
        NOTIFICATION_FAILURES_TOTAL.labels(channel=ch).inc()


def record_escalation_metric(severity: str, service: str) -> None:
    clean_svc = sanitize_service_label(service)
    ALERTS_ESCALATED_TOTAL.labels(
        severity=(severity or "HIGH").upper(),
        service=clean_svc
    ).inc()


def record_acknowledgement_metric(service: str) -> None:
    clean_svc = sanitize_service_label(service)
    ALERT_ACKNOWLEDGEMENTS_TOTAL.labels(service=clean_svc).inc()


def record_resolution_metric(service: str) -> None:
    clean_svc = sanitize_service_label(service)
    ALERT_RESOLUTIONS_TOTAL.labels(service=clean_svc).inc()


# Slack-specific Observability Metrics
SLACK_NOTIFICATIONS_TOTAL = Counter(
    "slack_notifications_total",
    "Total count of Slack notification attempts",
    ["status"]  # "sent", "failed", "duplicate", "skipped"
)
SLACK_NOTIFICATIONS_SUCCESS_TOTAL = Counter(
    "slack_notifications_success_total",
    "Total count of successful Slack notifications"
)
SLACK_NOTIFICATIONS_FAILED_TOTAL = Counter(
    "slack_notifications_failed_total",
    "Total count of failed Slack notifications"
)
SLACK_NOTIFICATION_LATENCY_SECONDS = Histogram(
    "slack_notification_latency_seconds",
    "Latency of Slack notification delivery in seconds",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)
)


def record_slack_metric(status: str, duration_sec: Optional[float] = None) -> None:
    st = status.lower()
    SLACK_NOTIFICATIONS_TOTAL.labels(status=st).inc()
    if st == "sent":
        SLACK_NOTIFICATIONS_SUCCESS_TOTAL.inc()
    elif st == "failed":
        SLACK_NOTIFICATIONS_FAILED_TOTAL.inc()
    if duration_sec is not None:
        SLACK_NOTIFICATION_LATENCY_SECONDS.observe(duration_sec)

