import hashlib
import json
from typing import Any, Dict, Optional

# Volatile keys to ignore in fingerprint generation
VOLATILE_KEYS = {
    "timestamp", "time", "date", "received_at", "run_id", "job_id",
    "request_id", "trace_id", "span_id", "uuid", "id", "created_at"
}


def generate_fingerprint(
    alert_name: str,
    service: str,
    labels: Optional[Dict[str, Any]] = None,
    resource: Optional[str] = None
) -> str:
    """
    Generate a deterministic SHA-256 fingerprint for alert identification and deduplication.
    Uses only stable identifiers, ignoring timestamps and ephemeral runtime IDs.
    """
    labels = labels or {}
    stable_labels = {
        k: v for k, v in sorted(labels.items())
        if k.lower() not in VOLATILE_KEYS and v is not None
    }

    fingerprint_payload = {
        "alert_name": alert_name.strip(),
        "service": service.strip().lower(),
        "resource": resource.strip() if resource else "",
        "labels": stable_labels
    }

    serialized = json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
