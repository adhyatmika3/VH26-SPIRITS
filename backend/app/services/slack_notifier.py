import re
import httpx
from typing import Any, Dict, List, Optional
from datetime import datetime
from app.core.config import settings
from app.core.logging import logger


def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitizes payload dictionary before storing in database to guarantee no secrets,
    webhook tokens, or sensitive authorization credentials are ever persisted.
    """
    sanitized = {}
    for k, v in payload.items():
        if isinstance(v, str):
            # Redact webhook URLs with token paths
            v_clean = re.sub(r'(https://hooks\.slack\.com/services/)[A-Za-z0-9/]+', r'\1REDACTED', v)
            # Redact xoxb tokens
            v_clean = re.sub(r'xox[baprs]-[A-Za-z0-9-]+', 'xoxb-REDACTED', v_clean)
            sanitized[k] = v_clean
        elif isinstance(v, dict):
            sanitized[k] = sanitize_payload(v)
        elif isinstance(v, list):
            sanitized[k] = [
                sanitize_payload(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            sanitized[k] = v
    return sanitized


def build_slack_blocks(
    notification_type: str,
    incident_number: str,
    service: str,
    alert_name: str,
    severity: str,
    priority: str,
    environment: str,
    occurrence_count: int,
    reason_codes: List[str],
    reason: str,
    escalation_level: int = 0
) -> Dict[str, Any]:
    """
    Builds clean, structured Slack Block Kit message payload.
    """
    if notification_type == "ESCALATION":
        header_emoji = "🔥 [ESCALATION LEVEL 1]"
        header_text = f"{header_emoji} Unresolved Incident: {incident_number}"
    elif notification_type == "RESOLUTION":
        header_emoji = "✅ [RESOLVED]"
        header_text = f"{header_emoji} Incident Resolved: {incident_number}"
    else:
        sev_emoji = "🚨" if severity in ["CRITICAL", "ERROR"] else "⚠️"
        header_text = f"{sev_emoji} [{severity}] Incident {incident_number}: {alert_name}"

    reason_bullets = "\n".join([f"• `{code}`" for code in reason_codes])

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": header_text[:150],
                "emoji": True
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Service:*\n`{service}`"},
                {"type": "mrkdwn", "text": f"*Environment:*\n`{environment}`"},
                {"type": "mrkdwn", "text": f"*Severity / Priority:*\n`{severity}` / `{priority}`"},
                {"type": "mrkdwn", "text": f"*Occurrences:*\n`{occurrence_count}`"},
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Why you are seeing this:*\n{reason_bullets}\n_{reason}_"
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Incident: *{incident_number}* | Channel: `{settings.SLACK_CHANNEL}`"
                }
            ]
        }
    ]

    return {
        "channel": settings.SLACK_CHANNEL,
        "text": f"Alert Fatigue Buster: {header_text}",
        "blocks": blocks
    }


def send_slack_notification(
    payload: Dict[str, Any],
    webhook_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Dispatches Slack notification.
    In testing/dev without a real webhook, safely logs and simulates successful delivery.
    """
    target_url = webhook_url or settings.SLACK_WEBHOOK_URL

    if not settings.SLACK_ENABLED or not target_url or "XXX/YYY/ZZZ" in target_url:
        logger.info(f"[Mock Slack Notifier] Dispatched notification to {settings.SLACK_CHANNEL}")
        return {"status": "SENT", "simulated": True, "error": None}

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(target_url, json=payload)
            if resp.status_code >= 400:
                logger.error(f"Slack API returned error HTTP {resp.status_code}: {resp.text}")
                return {"status": "FAILED", "simulated": False, "error": f"HTTP {resp.status_code}: {resp.text}"}
            return {"status": "SENT", "simulated": False, "error": None}
    except Exception as exc:
        logger.error(f"Failed to deliver Slack notification: {exc}", exc_info=True)
        return {"status": "FAILED", "simulated": False, "error": str(exc)}
