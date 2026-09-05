import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier

from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import (
    record_notification_metric,
    record_notification_duration,
    record_acknowledgement_metric,
    record_resolution_metric
)
from app.models.incident import Incident
from app.models.canonical_alert import CanonicalAlert
from app.models.decision_record import DecisionRecord


def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitizes payload dictionary before storing in database to guarantee no secrets,
    webhook tokens, or sensitive authorization credentials are ever persisted.
    """
    sanitized = {}
    for k, v in payload.items():
        if isinstance(v, str):
            v_clean = re.sub(r'(https://hooks\.slack\.com/services/)[A-Za-z0-9/]+', r'\1REDACTED', v)
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


def build_incident_blocks(
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
    incident_id: Optional[str] = None,
    decision_id: Optional[str] = None,
    decision: Optional[str] = None,
    risk_score: Optional[int] = None,
    risk_level: Optional[str] = None,
    dedup_count: Optional[int] = None,
    unique_fingerprints: Optional[int] = None,
    probable_cause: Optional[str] = None,
    resolution_steps: Optional[List[str]] = None,
    dashboard_base_url: Optional[str] = None,
    escalation_level: int = 0
) -> Dict[str, Any]:
    """
    Builds clean, structured, and interactive Slack Block Kit message payload.
    Adheres to official Slack Block Kit guidelines with Header, Key Metadata,
    Correlation Context, Explainability, Remediation, and Interactive Action Buttons.
    """
    base_url = (dashboard_base_url or settings.DASHBOARD_BASE_URL).rstrip("/")
    inc_str = str(incident_id or "")
    dec_str = str(decision_id or "")
    eff_decision = decision or ("ESCALATE" if notification_type == "ESCALATION" else "NOTIFY")

    # 1. Header with contextual severity indicator
    if notification_type == "ESCALATION":
        header_text = f"🔥 [CRITICAL ESCALATION] Incident {incident_number}"
    elif notification_type == "RESOLUTION":
        header_text = f"✅ [RESOLVED] Incident {incident_number}"
    elif priority == "CRITICAL" or severity == "CRITICAL":
        header_text = f"🚨 CRITICAL INCIDENT DETECTED: {incident_number}"
    else:
        header_text = f"⚠️ [{severity}] Incident {incident_number}: {alert_name}"

    # 2. Key Metadata section
    risk_display = f"*{risk_score}/100* ({risk_level})" if risk_score is not None else f"*{priority}*"
    fields = [
        {"type": "mrkdwn", "text": f"*Incident ID:*\n`{incident_number}`"},
        {"type": "mrkdwn", "text": f"*Service:*\n`{service}`"},
        {"type": "mrkdwn", "text": f"*Risk Score:*\n{risk_display}"},
        {"type": "mrkdwn", "text": f"*Decision:*\n*{eff_decision}*"},
        {"type": "mrkdwn", "text": f"*Environment:*\n`{environment}`"},
        {"type": "mrkdwn", "text": f"*Occurrences:*\n*{occurrence_count} raw alerts*"}
    ]

    blocks: List[Dict[str, Any]] = [
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
            "fields": fields
        }
    ]

    # 3. Correlation & Telemetry Noise reduction context
    coalesced = dedup_count if dedup_count is not None else max(0, occurrence_count - 1)
    fps = unique_fingerprints if unique_fingerprints is not None else 1
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"*Correlation & Noise Reduction:*\n"
                f"• Raw Alerts Ingested: *{occurrence_count}*\n"
                f"• Deduplicated Noise Suppressed: *{coalesced}*\n"
                f"• Correlated Problem Groups: *1 Core Incident* (`{fps}` unique fingerprint)"
            )
        }
    })

    # 4. Explainability & Decision Rationale
    reason_bullets = "\n".join([f"• `{code}`" for code in (reason_codes or [])])
    if not reason_bullets:
        reason_bullets = "• `CRITICAL_INCIDENT`"
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*Why you are seeing this:*\n{reason_bullets}\n_{reason}_"
        }
    })

    # 5. Diagnostic & Recommended Remediation Action
    if probable_cause or resolution_steps:
        res_lines = ["*Diagnostic & Recommended Remediation:*"]
        if probable_cause:
            res_lines.append(f"• *Probable Root Cause:* {probable_cause}")
        if resolution_steps:
            res_lines.append("• *Recommended Action Steps:*")
            for idx, step in enumerate(resolution_steps[:4], 1):
                res_lines.append(f"   {idx}. {step}")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "\n".join(res_lines)
            }
        })

    # 6. Interactive Action Buttons
    action_elements = []
    if inc_str:
        action_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "Acknowledge", "emoji": True},
            "style": "primary",
            "action_id": "incident_acknowledge",
            "value": inc_str
        })
        action_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "Resolve", "emoji": True},
            "style": "danger",
            "action_id": "incident_resolve",
            "value": inc_str
        })
        action_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "View Incident", "emoji": True},
            "action_id": "view_incident",
            "url": f"{base_url}/frontend/index.html?incident={inc_str}"
        })

    if dec_str:
        action_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "View Explanation", "emoji": True},
            "action_id": "view_explanation",
            "url": f"{base_url}/api/v1/dashboard/explain/{dec_str}"
        })

    if action_elements:
        blocks.append({
            "type": "actions",
            "elements": action_elements
        })

    # 7. Context Footer
    now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    target_channel = settings.SLACK_CHANNEL_ID or settings.SLACK_CHANNEL
    blocks.extend([
        {"type": "divider"},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Detected At: `{now_utc_str}` | Target: `{target_channel}` | Engine: *Alert Fatigue Buster*"
                }
            ]
        }
    ])

    return {
        "channel": target_channel,
        "text": f"Alert Fatigue Buster: {header_text}",
        "blocks": blocks
    }


def classify_slack_error(exc: Any) -> tuple[bool, Optional[int]]:
    """
    Classifies a Slack exception/error into:
    - is_transient (bool): True if error is temporary (rate limit, timeout, 5xx, network glitch)
    - retry_after (int | None): Seconds to wait before retry if provided by Slack (e.g. 429 Retry-After)
    """
    if exc is None:
        return False, None

    # 1. Official SlackApiError
    if isinstance(exc, SlackApiError):
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None) if response else None
        headers = getattr(response, "headers", {}) if response else {}
        error_code = ""
        if response and hasattr(response, "get"):
            error_code = str(response.get("error") or "")
        elif response and hasattr(response, "data") and isinstance(response.data, dict):
            error_code = str(response.data.get("error") or "")

        # HTTP 429 Rate limiting
        if status_code == 429 or error_code == "ratelimited":
            retry_after = None
            raw_retry = headers.get("Retry-After") or headers.get("retry-after")
            if raw_retry:
                try:
                    retry_after = int(raw_retry)
                except (ValueError, TypeError):
                    retry_after = None
            return True, retry_after

        # HTTP 5xx Server errors
        if status_code and status_code >= 500:
            return True, None

        if error_code in {"service_unavailable", "request_timeout", "internal_error", "fatal_error"}:
            return True, None

        # Definite permanent Slack API error codes
        permanent_codes = {
            "invalid_auth", "not_authed", "account_inactive", "token_revoked", "invalid_token",
            "channel_not_found", "is_archived", "not_in_channel", "missing_scope",
            "invalid_blocks", "invalid_json", "msg_too_long", "user_not_found", "no_text"
        }
        if error_code in permanent_codes or (status_code and 400 <= status_code < 500 and status_code != 429):
            return False, None

    # 2. String & Exception Type Inspection
    err_str = str(exc).lower()
    exc_type = type(exc).__name__.lower()

    # Transient indicators
    transient_keywords = [
        "timeout", "timed out", "connect", "connectionerror", "connectionreset",
        "connectionrefused", "name resolution", "temporary failure", "dns",
        "500", "502", "503", "504", "server error", "rate limit", "429", "ratelimited"
    ]
    if any(kw in err_str or kw in exc_type for kw in transient_keywords):
        match = re.search(r'retry-after[:\s=]+(\d+)', err_str)
        retry_after = int(match.group(1)) if match else None
        return True, retry_after

    # Permanent indicators
    permanent_keywords = [
        "invalid_auth", "invalid token", "missing_scope", "channel_not_found",
        "is_archived", "not_in_channel", "invalid_blocks", "401", "403", "404"
    ]
    if any(kw in err_str for kw in permanent_keywords):
        return False, None

    # Socket / Connection fallback
    import socket
    if isinstance(exc, (socket.timeout, socket.error, TimeoutError, ConnectionError)):
        return True, None

    return False, None


def send_incident_notification(
    payload: Dict[str, Any],
    channel_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    Dispatches Slack notification via official Slack SDK (slack_sdk.WebClient).
    Treats Slack strictly as an external dependency.
    Returns structured delivery metadata:
    - status: "DELIVERED" (or "SENT") on success, "FAILED" on failure
    - is_transient: bool indicating whether failure is temporary
    - retry_after: int | None respecting Slack rate limiting
    - ts: message timestamp for deduplication
    - duration_sec: latency measurement
    """
    target_channel = channel_override or payload.get("channel") or settings.SLACK_CHANNEL_ID or settings.SLACK_CHANNEL
    start_time = time.perf_counter()

    # 1. Disabled Mode
    if not settings.SLACK_ENABLED:
        logger.info(f"[Mock Slack Notifier] SLACK_ENABLED is false. Simulated notification to {target_channel}")
        return {
            "status": "SENT",
            "simulated": True,
            "error": None,
            "channel": target_channel,
            "ts": None,
            "is_transient": False,
            "retry_after": None,
            "duration_sec": 0.001
        }

    # 2. Check if Bot Token is provided / placeholder
    bot_token = settings.SLACK_BOT_TOKEN
    if not bot_token or "xoxb-your-bot" in bot_token or "PLACEHOLDER" in bot_token:
        logger.info(f"[Mock Slack Notifier] No valid SLACK_BOT_TOKEN provided. Simulated delivery to {target_channel}")
        return {
            "status": "SENT",
            "simulated": True,
            "error": None,
            "channel": target_channel,
            "ts": None,
            "is_transient": False,
            "retry_after": None,
            "duration_sec": 0.001
        }

    # 3. Real Slack Web API Dispatch with configurable timeout
    timeout_sec = getattr(settings, "SLACK_NOTIFICATION_TIMEOUT_SECONDS", 10)
    try:
        client = WebClient(token=bot_token, timeout=timeout_sec)
        blocks = payload.get("blocks")
        text = payload.get("text", "Alert Fatigue Buster Incident Notification")

        response = client.chat_postMessage(
            channel=target_channel,
            text=text,
            blocks=blocks
        )
        duration = time.perf_counter() - start_time
        ts = response.get("ts")
        logger.info(f"Successfully posted Slack message to {target_channel} (ts={ts}) in {duration:.3f}s")
        return {
            "status": "DELIVERED",
            "simulated": False,
            "error": None,
            "channel": target_channel,
            "ts": ts,
            "is_transient": False,
            "retry_after": None,
            "duration_sec": duration
        }
    except SlackApiError as exc:
        duration = time.perf_counter() - start_time
        is_transient, retry_after = classify_slack_error(exc)
        err_msg = exc.response.get("error", str(exc)) if getattr(exc, "response", None) else str(exc)
        logger.error(
            f"Slack API error delivering notification (transient={is_transient}, retry_after={retry_after}): {err_msg}"
        )
        return {
            "status": "FAILED",
            "simulated": False,
            "error": f"SlackApiError: {err_msg}",
            "channel": target_channel,
            "ts": None,
            "is_transient": is_transient,
            "retry_after": retry_after,
            "duration_sec": duration
        }
    except Exception as exc:
        duration = time.perf_counter() - start_time
        is_transient, retry_after = classify_slack_error(exc)
        logger.error(
            f"Failed to deliver Slack notification (transient={is_transient}, retry_after={retry_after}): {exc}",
            exc_info=False
        )
        return {
            "status": "FAILED",
            "simulated": False,
            "error": str(exc),
            "channel": target_channel,
            "ts": None,
            "is_transient": is_transient,
            "retry_after": retry_after,
            "duration_sec": duration
        }


def verify_slack_signature(body: bytes, headers: Dict[str, str]) -> bool:
    """
    Verifies authentic Slack HTTP signature using SLACK_SIGNING_SECRET.
    Guards against tampering, spoofing, and replay attacks (> 300 seconds).
    """
    signing_secret = settings.SLACK_SIGNING_SECRET
    if not signing_secret:
        logger.warning("SLACK_SIGNING_SECRET is not configured; rejecting interaction request.")
        return False

    timestamp = headers.get("x-slack-request-timestamp") or headers.get("X-Slack-Request-Timestamp")
    signature = headers.get("x-slack-signature") or headers.get("X-Slack-Signature")

    if not timestamp or not signature:
        logger.warning("Missing Slack signature or timestamp headers.")
        return False

    # Prevent replay attacks older than 5 minutes
    try:
        req_ts = int(timestamp)
        now_ts = int(time.time())
        if abs(now_ts - req_ts) > 300:
            logger.warning(f"Slack request timestamp out of bounds (diff: {abs(now_ts - req_ts)}s).")
            return False
    except ValueError:
        logger.warning(f"Invalid Slack timestamp header: {timestamp}")
        return False

    verifier = SignatureVerifier(signing_secret)
    return verifier.is_valid(body=body, timestamp=timestamp, signature=signature)


def check_slack_health() -> Dict[str, Any]:
    """
    Evaluates Slack integration health without leaking bot tokens or signing secrets.
    Distinguishes application health from Slack dependency status:
    status: 'healthy' | 'degraded' | 'disabled'
    """
    configured = bool(settings.SLACK_BOT_TOKEN and "xoxb-your-bot" not in settings.SLACK_BOT_TOKEN)
    channel = settings.SLACK_CHANNEL_ID or settings.SLACK_CHANNEL

    if not settings.SLACK_ENABLED:
        return {
            "status": "disabled",
            "enabled": False,
            "configured": configured,
            "connected": False,
            "channel": channel,
            "bot_user": None
        }

    if not configured:
        return {
            "status": "degraded",
            "enabled": True,
            "configured": False,
            "connected": False,
            "channel": channel,
            "bot_user": None,
            "error": "Slack bot token unconfigured"
        }

    try:
        timeout_sec = min(settings.SLACK_NOTIFICATION_TIMEOUT_SECONDS, 5)
        client = WebClient(token=settings.SLACK_BOT_TOKEN, timeout=timeout_sec)
        auth_resp = client.auth_test()
        return {
            "status": "healthy",
            "enabled": True,
            "configured": True,
            "connected": True,
            "channel": channel,
            "channel_configured": bool(channel and "C0123456789" not in channel),
            "bot_user": auth_resp.get("user")
        }
    except Exception as exc:
        logger.warning(f"Slack health connection test failed: {exc}")
        return {
            "status": "degraded",
            "enabled": True,
            "configured": True,
            "connected": False,
            "channel": channel,
            "bot_user": None,
            "error": re.sub(r'xox[baprs]-[A-Za-z0-9-]+', 'xoxb-REDACTED', str(exc))
        }


def handle_slack_interaction(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processes Slack interactive button clicks (Acknowledge / Resolve) through
    existing backend database models and business logic without bypassing the state engine.
    """
    actions = payload.get("actions", [])
    if not actions:
        return {"text": "No action received"}

    action = actions[0]
    action_id = action.get("action_id")
    raw_val = action.get("value")

    if not raw_val:
        return {"text": "No incident identifier attached to action"}

    try:
        incident_id = uuid.UUID(raw_val)
    except ValueError:
        return {"text": f"Invalid incident UUID format: {raw_val}"}

    stmt = select(Incident).where(Incident.id == incident_id)
    incident = db.execute(stmt).scalar_one_or_none()
    if not incident:
        return {"text": f"Incident {raw_val} not found in database"}

    user_info = payload.get("user", {})
    user_name = user_info.get("username") or user_info.get("name") or "slack-operator"
    now = datetime.now(timezone.utc)

    # 1. Action: Acknowledge Incident
    if action_id == "incident_acknowledge":
        incident.status = "ACKNOWLEDGED"
        incident.acknowledged_at = now
        incident.acknowledged_by = f"slack:{user_name}"
        db.add(incident)
        db.commit()
        db.refresh(incident)

        record_acknowledgement_metric(service=incident.service)
        logger.info(f"Incident [{incident.incident_number}] ACKNOWLEDGED via Slack button by {user_name}")

        return {
            "response_type": "in_channel",
            "replace_original": False,
            "text": f"✅ Incident *{incident.incident_number}* was acknowledged by <@{user_info.get('id')}> (`{user_name}`) at {now.strftime('%H:%M:%S UTC')}."
        }

    # 2. Action: Resolve Incident
    elif action_id == "incident_resolve":
        incident.status = "RESOLVED"
        incident.resolved_at = now
        incident.resolved_by = f"slack:{user_name}"

        # Resolve all canonical alerts
        for alert in incident.alerts:
            alert.status = "RESOLVED"
            db.add(alert)

        # Audit decision record
        dec_record = DecisionRecord(
            incident_id=incident.id,
            decision="NOTIFY",
            reason_codes=["INCIDENT_SLACK_RESOLVED"],
            reason=f"Incident [{incident.incident_number}] was manually resolved via Slack button by {user_name}.",
            context_snapshot={"service": incident.service, "priority": incident.priority, "status": "RESOLVED", "actor": f"slack:{user_name}"},
            created_at=now
        )
        db.add(dec_record)
        db.add(incident)
        db.commit()
        db.refresh(incident)

        record_resolution_metric(service=incident.service)
        logger.info(f"Incident [{incident.incident_number}] RESOLVED via Slack button by {user_name}")

        return {
            "response_type": "in_channel",
            "replace_original": False,
            "text": f"🎉 Incident *{incident.incident_number}* was resolved by <@{user_info.get('id')}> (`{user_name}`) at {now.strftime('%H:%M:%S UTC')}."
        }

    return {"text": f"Action '{action_id}' processed"}
