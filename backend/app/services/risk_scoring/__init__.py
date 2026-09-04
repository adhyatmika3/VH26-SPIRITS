"""
Risk Scoring & Severity Classification Service
==============================================

Calculates a 0–100 risk score for a correlated incident based on:
  A. Alert Severity        (0–30 pts)
  B. Alert Frequency       (0–20 pts)
  C. Occurrence Count      (0–15 pts)
  D. Service Importance    (0–20 pts)
  E. Environment           (0–10 pts)
  F. Incident Duration     (0–5  pts)

Classification:
  0–30   → LOW
  31–60  → MEDIUM
  61–80  → HIGH
  81–100 → CRITICAL
"""

from app.services.risk_scoring.calculator import (
    calculate_risk,
    calculate_and_store_risk,
    RiskResult,
)

__all__ = ["calculate_risk", "calculate_and_store_risk", "RiskResult"]
