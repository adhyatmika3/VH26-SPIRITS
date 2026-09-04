from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

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

# Active Incidents Gauge
ACTIVE_INCIDENTS_GAUGE = Gauge(
    "active_incidents_count",
    "Current count of open or in-progress incidents"
)


def record_decision_metric(decision: str, severity: str, environment: str, service: str, reason_codes: list[str]) -> None:
    ALERTS_DECIDED_TOTAL.labels(
        decision=decision.upper(),
        severity=severity.upper(),
        environment=environment.lower(),
        service=service.lower()
    ).inc()

    if decision.upper() == "SUPPRESS":
        primary_reason = reason_codes[0] if reason_codes else "UNKNOWN"
        ALERTS_SUPPRESSED_TOTAL.labels(
            reason_code=primary_reason,
            service=service.lower()
        ).inc()


def record_notification_metric(channel: str, success: bool, priority: str = "MEDIUM", service: str = "unknown") -> None:
    if success:
        NOTIFICATION_SUCCESS_TOTAL.labels(channel=channel.lower()).inc()
        ALERTS_NOTIFIED_TOTAL.labels(
            priority=priority.upper(),
            channel=channel.lower(),
            service=service.lower()
        ).inc()
    else:
        NOTIFICATION_FAILURE_TOTAL.labels(channel=channel.lower()).inc()


def record_escalation_metric(severity: str, service: str) -> None:
    ALERTS_ESCALATED_TOTAL.labels(
        severity=severity.upper(),
        service=service.lower()
    ).inc()


def record_acknowledgement_metric(service: str) -> None:
    ALERT_ACKNOWLEDGEMENTS_TOTAL.labels(service=service.lower()).inc()


def record_resolution_metric(service: str) -> None:
    ALERT_RESOLUTIONS_TOTAL.labels(service=service.lower()).inc()
