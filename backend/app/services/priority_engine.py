from typing import Any, Dict, Optional

# Priority tier order for deterministic escalation
PRIORITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def evaluate_priority(
    severity: str,
    labels: Optional[Dict[str, Any]] = None,
    occurrence_count: int = 1,
    is_storm: bool = False
) -> str:
    """
    Deterministic rule-based priority engine with storm escalation modifier.
    
    Baseline rules:
    - CRITICAL + production        -> CRITICAL
    - CRITICAL (non-prod)          -> HIGH
    - ERROR + production           -> HIGH
    - ERROR (non-prod)             -> MEDIUM
    - WARNING + frequency >= 10    -> HIGH
    - WARNING                      -> MEDIUM
    - INFO                         -> LOW

    Storm Adjustment:
    - If participating in an alert storm: increase priority by one tier (unless already CRITICAL).
    """
    labels = labels or {}
    env = str(labels.get("environment") or labels.get("env") or "").strip().lower()
    is_prod = env in {"prod", "production", "live"}

    sev = severity.upper()

    # Determine baseline priority
    if sev == "CRITICAL":
        baseline = "CRITICAL" if is_prod else "HIGH"
    elif sev == "ERROR":
        baseline = "HIGH" if is_prod else "MEDIUM"
    elif sev == "WARNING":
        baseline = "HIGH" if occurrence_count >= 10 else "MEDIUM"
    else:  # INFO or other
        baseline = "LOW"

    # Apply storm escalation modifier
    if is_storm:
        current_index = PRIORITY_ORDER.index(baseline)
        if current_index < len(PRIORITY_ORDER) - 1:
            return PRIORITY_ORDER[current_index + 1]

    return baseline
