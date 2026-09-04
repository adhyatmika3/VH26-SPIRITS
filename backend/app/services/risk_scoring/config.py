"""
Risk Scoring Configuration
===========================
Centralised, configurable mappings for the risk scoring engine.
Update this file to change service criticality or environment weights
WITHOUT touching any business logic.
"""

# ---------------------------------------------------------------------------
# A. Severity Scores  (max 30 pts)
# ---------------------------------------------------------------------------
SEVERITY_SCORES: dict[str, int] = {
    "critical": 30,
    "error":    25,
    "high":     20,
    "warning":  15,
    "warn":     15,
    "info":      5,
    "low":       5,
    "unknown":   5,
}

# ---------------------------------------------------------------------------
# B. Frequency Thresholds  (max 20 pts)
#    Alerts-per-minute bucket → score
# ---------------------------------------------------------------------------
FREQUENCY_SCORES: list[tuple[float, int]] = [
    # (alerts_per_minute_threshold, score)
    # Evaluated from highest to lowest — first match wins
    (10.0, 20),   # ≥ 10 alerts/min → Very High
    (3.0,  15),   # ≥ 3  alerts/min → High
    (1.0,  10),   # ≥ 1  alerts/min → Medium
    (0.0,   5),   # anything else   → Low
]

# ---------------------------------------------------------------------------
# C. Occurrence Count Buckets  (max 15 pts)
# ---------------------------------------------------------------------------
OCCURRENCE_SCORES: list[tuple[int, int]] = [
    # (min_count_inclusive, score)
    # Evaluated from highest to lowest — first match wins
    (500, 15),
    (101, 13),
    (51,  11),
    (21,   8),
    (6,    5),
    (1,    2),
]

# ---------------------------------------------------------------------------
# D. Service Criticality Map  (max 20 pts)
#    Add / modify services here — no other file needs to change.
# ---------------------------------------------------------------------------
SERVICE_CRITICALITY: dict[str, int] = {
    # Core revenue & identity services
    "payment-api":          20,
    "payment":              20,
    "authentication":       20,
    "auth-service":         20,
    "auth":                 20,
    "checkout":             20,
    "checkout-service":     20,

    # Data & persistence
    "database":             18,
    "db":                   18,
    "postgres":             18,
    "redis":                16,
    "kafka":                16,

    # Downstream business services
    "order-service":        15,
    "orders":               15,
    "inventory":            14,
    "shipping":             13,
    "user-service":         13,
    "users":                13,
    "api-gateway":          16,
    "gateway":              16,

    # Support / secondary services
    "notification":         10,
    "email-service":        10,
    "sms-service":          10,
    "analytics":             5,
    "reporting":             5,
    "monitoring":            5,

    # Test / non-critical
    "test-service":          2,
    "sandbox":               2,
    "demo":                  2,
}

# Default score for services NOT in the map
DEFAULT_SERVICE_SCORE: int = 8

# ---------------------------------------------------------------------------
# E. Environment Scores  (max 10 pts)
# ---------------------------------------------------------------------------
ENVIRONMENT_SCORES: dict[str, int] = {
    "production":   10,
    "prod":         10,
    "staging":       5,
    "stage":         5,
    "development":   2,
    "dev":           2,
    "testing":       1,
    "test":          1,
    "local":         1,
}

# Default for unknown environments
DEFAULT_ENVIRONMENT_SCORE: int = 5

# ---------------------------------------------------------------------------
# F. Duration Buckets  (max 5 pts)
#    Seconds thresholds → score
# ---------------------------------------------------------------------------
DURATION_SCORES: list[tuple[int, int]] = [
    # (min_duration_seconds, score) — highest first
    (1800, 5),   # ≥ 30 min
    (600,  4),   # ≥ 10 min
    (300,  3),   # ≥ 5 min
    (60,   2),   # ≥ 1 min
    (0,    1),   # < 1 min
]

# ---------------------------------------------------------------------------
# G. Classification Thresholds
# ---------------------------------------------------------------------------
RISK_CLASSIFICATIONS: list[tuple[int, str]] = [
    # (min_score_inclusive, label) — highest first
    (81, "CRITICAL"),
    (61, "HIGH"),
    (31, "MEDIUM"),
    (0,  "LOW"),
]

# Maximum achievable score (used for clamping)
MAX_RISK_SCORE: int = 100
