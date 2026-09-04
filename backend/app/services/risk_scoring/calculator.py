"""
Risk Scoring Calculator
=======================
Implements the 6-factor deterministic risk scoring algorithm:
1. Alert Severity        (0–30 pts)
2. Alert Frequency       (0–20 pts)
3. Occurrence Count      (0–15 pts)
4. Service Importance    (0–20 pts)
5. Environment           (0–10 pts)
6. Incident Duration     (0–5  pts)

Total Score: 0–100 pts
Classification:
  0–30   → LOW
  31–60  → MEDIUM
  61–80  → HIGH
  81–100 → CRITICAL
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.models.incident import Incident
from app.services.risk_scoring.config import (
    SEVERITY_SCORES,
    FREQUENCY_SCORES,
    OCCURRENCE_SCORES,
    SERVICE_CRITICALITY,
    DEFAULT_SERVICE_SCORE,
    ENVIRONMENT_SCORES,
    DEFAULT_ENVIRONMENT_SCORE,
    DURATION_SCORES,
    RISK_CLASSIFICATIONS,
    MAX_RISK_SCORE,
)


@dataclass
class RiskResult:
    score: int
    level: str
    severity_score: int
    frequency_score: int
    occurrence_score: int
    service_score: int
    environment_score: int
    duration_score: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level,
            "breakdown": {
                "severity": self.severity_score,
                "frequency": self.frequency_score,
                "occurrences": self.occurrence_score,
                "service": self.service_score,
                "environment": self.environment_score,
                "duration": self.duration_score,
                "total": self.score
            }
        }


def calculate_risk(
    severity: str,
    service: str,
    occurrence_count: int = 1,
    environment: Optional[str] = None,
    first_seen: Optional[datetime] = None,
    last_seen: Optional[datetime] = None
) -> RiskResult:
    """
    Computes exact deterministic risk score and breakdown from telemetry parameters.
    """
    # 1. Severity (0–30 pts)
    sev_key = (severity or "unknown").strip().lower()
    sev_score = SEVERITY_SCORES.get(sev_key, SEVERITY_SCORES.get("unknown", 5))

    # Calculate duration
    now = datetime.now(timezone.utc)
    def _to_utc(dt: Optional[datetime]) -> datetime:
        if dt is None:
            return now
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    start = _to_utc(first_seen)
    end = _to_utc(last_seen)
    duration_sec = max(0.0, (end - start).total_seconds())

    # 2. Frequency (0–20 pts)
    duration_min = max(0.1, duration_sec / 60.0)
    alerts_per_min = occurrence_count / duration_min
    freq_score = 5
    for thresh, pts in FREQUENCY_SCORES:
        if alerts_per_min >= thresh:
            freq_score = pts
            break

    # 3. Occurrences (0–15 pts)
    occ_score = 2
    for min_occ, pts in OCCURRENCE_SCORES:
        if occurrence_count >= min_occ:
            occ_score = pts
            break

    # 4. Service Criticality (0–20 pts)
    svc_key = (service or "").strip().lower()
    svc_score = SERVICE_CRITICALITY.get(svc_key, DEFAULT_SERVICE_SCORE)

    # 5. Environment (0–10 pts)
    env_key = (environment or "production").strip().lower()
    env_score = ENVIRONMENT_SCORES.get(env_key, DEFAULT_ENVIRONMENT_SCORE)

    # 6. Duration (0–5 pts)
    dur_score = 1
    for min_dur, pts in DURATION_SCORES:
        if duration_sec >= min_dur:
            dur_score = pts
            break

    total_score = min(
        MAX_RISK_SCORE,
        sev_score + freq_score + occ_score + svc_score + env_score + dur_score
    )

    # Determine classification
    level = "LOW"
    for min_score, classification in RISK_CLASSIFICATIONS:
        if total_score >= min_score:
            level = classification
            break

    return RiskResult(
        score=total_score,
        level=level,
        severity_score=sev_score,
        frequency_score=freq_score,
        occurrence_score=occ_score,
        service_score=svc_score,
        environment_score=env_score,
        duration_score=dur_score
    )


def calculate_and_store_risk(incident: Incident, db: Optional[Session] = None) -> RiskResult:
    """
    Calculates risk for an incident and optionally updates priority if necessary.
    """
    result = calculate_risk(
        severity=incident.priority,
        service=incident.service,
        occurrence_count=incident.alert_count,
        environment="production",
        first_seen=incident.first_seen,
        last_seen=incident.last_seen
    )
    return result
