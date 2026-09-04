import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.core.logging import logger


def build_email_content(
    incident_number: str,
    incident_id: str,
    service: str,
    alert_type: str,
    severity: str,
    priority: str,
    environment: str,
    occurrence_count: int,
    risk_score: Optional[int] = None,
    risk_level: Optional[str] = None,
    first_seen: Optional[datetime] = None,
    last_seen: Optional[datetime] = None,
    duration_str: Optional[str] = None,
    reason: Optional[str] = None,
    reason_codes: Optional[List[str]] = None,
    probable_cause: Optional[str] = None,
    resolution_steps: Optional[List[str]] = None
) -> Dict[str, str]:
    """
    Constructs both plain-text and HTML email bodies containing all vital incident telemetry.
    """
    first_str = first_seen.strftime("%Y-%m-%d %H:%M:%S UTC") if first_seen else "N/A"
    last_str = last_seen.strftime("%Y-%m-%d %H:%M:%S UTC") if last_seen else "N/A"
    dur_str = duration_str or "N/A"
    score_display = f"{risk_score} / 100 ({risk_level})" if risk_score is not None else "N/A"
    reasons_display = ", ".join(reason_codes or [])

    steps_text = ""
    steps_html = ""
    if resolution_steps:
        steps_text = "\n".join([f"  {idx+1}. {step}" for idx, step in enumerate(resolution_steps)])
        steps_html = "".join([f"<li style='margin-bottom:6px;'>{step}</li>" for step in resolution_steps])
    else:
        steps_text = "  None available"
        steps_html = "<li>No specific resolution steps recorded.</li>"

    subject = f"CRITICAL ESCALATION: [{incident_number}] {service} - {alert_type} in {environment}"

    text_body = f"""======================================================================
CRITICAL INCIDENT ESCALATION - SRE ALERT INTELLIGENCE
======================================================================

Incident:      {incident_number} (ID: {incident_id})
Service:       {service}
Alert Type:    {alert_type}
Severity:      {severity} (Priority: {priority})
Environment:   {environment}
Occurrences:   {occurrence_count} raw alerts consolidated
Risk Score:    {score_display}
First Seen:    {first_str}
Last Seen:     {last_str}
Duration:      {dur_str}

Decision / Escalation:
  Reason:      {reason or 'Threshold exceeded'}
  Codes:       {reasons_display}

Probable Cause:
  {probable_cause or 'Under active investigation by telemetry correlation engine.'}

Recommended Remediation Steps:
{steps_text}

======================================================================
Generated automatically by Alert Fatigue Buster Engine
======================================================================
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 24px; }}
  .card {{ background-color: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; max-width: 640px; margin: 0 auto; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
  .header {{ background-color: #b91c1c; color: #ffffff; padding: 20px 24px; }}
  .header h1 {{ margin: 0; font-size: 20px; font-weight: 700; }}
  .content {{ padding: 24px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }}
  .field {{ background-color: #f1f5f9; padding: 10px 14px; border-radius: 6px; }}
  .field-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 600; margin-bottom: 2px; }}
  .field-val {{ font-size: 14px; font-weight: 600; color: #0f172a; }}
  .section-title {{ font-size: 14px; font-weight: 700; color: #0f172a; margin-top: 18px; margin-bottom: 8px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }}
  .callout {{ background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 12px 16px; border-radius: 4px; font-size: 13px; color: #991b1b; margin-bottom: 16px; }}
  ol {{ margin: 0; padding-left: 20px; font-size: 13px; color: #334155; }}
  .footer {{ background-color: #f8fafc; padding: 14px 24px; font-size: 11px; color: #94a3b8; border-top: 1px solid #e2e8f0; text-align: center; }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <h1>🚨 Critical Incident Escalation</h1>
    <div style="font-size: 13px; opacity: 0.9; margin-top: 4px;">{incident_number} &bull; {service} &bull; {environment}</div>
  </div>
  <div class="content">
    <div class="callout">
      <strong>Escalation Reason:</strong> {reason or 'Incident reached critical threshold and requires immediate on-call response.'}
    </div>

    <div class="grid">
      <div class="field"><div class="field-label">Service</div><div class="field-val">{service}</div></div>
      <div class="field"><div class="field-label">Environment</div><div class="field-val">{environment}</div></div>
      <div class="field"><div class="field-label">Alert Type</div><div class="field-val">{alert_type}</div></div>
      <div class="field"><div class="field-label">Risk Assessment</div><div class="field-val" style="color: #b91c1c;">{score_display}</div></div>
      <div class="field"><div class="field-label">Raw Alerts Consolidated</div><div class="field-val">{occurrence_count}</div></div>
      <div class="field"><div class="field-label">Duration</div><div class="field-val">{dur_str}</div></div>
      <div class="field"><div class="field-label">First Seen</div><div class="field-val">{first_str}</div></div>
      <div class="field"><div class="field-label">Last Seen</div><div class="field-val">{last_str}</div></div>
    </div>

    <div class="section-title">Probable Cause</div>
    <p style="font-size: 13px; color: #334155; line-height: 1.5; margin-top: 4px;">
      {probable_cause or 'Telemetry intelligence indicates rapid alert velocity on core production workload.'}
    </p>

    <div class="section-title">Recommended Remediation Steps</div>
    <ol style="margin-top: 6px;">
      {steps_html}
    </ol>
  </div>
  <div class="footer">
    Alert Fatigue Buster SRE Engine &bull; Incident ID: {incident_id}
  </div>
</div>
</body>
</html>
"""
    return {
        "subject": subject,
        "text": text_body,
        "html": html_body
    }


_UNSET = object()


def send_email_notification(
    incident_number: str,
    incident_id: str,
    service: str,
    alert_type: str,
    severity: str,
    priority: str,
    environment: str,
    occurrence_count: int,
    risk_score: Optional[int] = None,
    risk_level: Optional[str] = None,
    first_seen: Optional[datetime] = None,
    last_seen: Optional[datetime] = None,
    duration_str: Optional[str] = None,
    reason: Optional[str] = None,
    reason_codes: Optional[List[str]] = None,
    probable_cause: Optional[str] = None,
    resolution_steps: Optional[List[str]] = None,
    smtp_host: Any = _UNSET,
    smtp_port: Any = _UNSET,
    smtp_username: Any = _UNSET,
    smtp_password: Any = _UNSET,
    smtp_use_tls: Any = _UNSET,
    from_email: Any = _UNSET,
    to_email: Any = _UNSET
) -> Dict[str, Any]:
    """
    Sends real SMTP email escalation.
    Validates configuration; returns clear FAILED status if SMTP is unconfigured or if delivery fails.
    Never exposes passwords or sensitive credentials in logs or returned payload.
    """
    host = smtp_host if smtp_host is not _UNSET else (os.environ.get("SMTP_HOST") or settings.SMTP_HOST)
    port = smtp_port if smtp_port is not _UNSET else int(os.environ.get("SMTP_PORT") or settings.SMTP_PORT or 587)
    username = smtp_username if smtp_username is not _UNSET else (os.environ.get("SMTP_USERNAME") or settings.SMTP_USERNAME)
    password = smtp_password if smtp_password is not _UNSET else (os.environ.get("SMTP_PASSWORD") or settings.SMTP_PASSWORD)
    use_tls = smtp_use_tls if smtp_use_tls is not _UNSET else settings.SMTP_USE_TLS
    sender = from_email if from_email is not _UNSET else (os.environ.get("ALERT_EMAIL_FROM") or settings.ALERT_EMAIL_FROM)
    recipient = to_email if to_email is not _UNSET else (os.environ.get("ALERT_EMAIL_TO") or settings.ALERT_EMAIL_TO)

    # Build email body
    content = build_email_content(
        incident_number=incident_number,
        incident_id=incident_id,
        service=service,
        alert_type=alert_type,
        severity=severity,
        priority=priority,
        environment=environment,
        occurrence_count=occurrence_count,
        risk_score=risk_score,
        risk_level=risk_level,
        first_seen=first_seen,
        last_seen=last_seen,
        duration_str=duration_str,
        reason=reason,
        reason_codes=reason_codes,
        probable_cause=probable_cause,
        resolution_steps=resolution_steps
    )

    sanitized_payload = {
        "channel": "email",
        "destination": recipient or "unconfigured",
        "sender": sender or "unconfigured",
        "subject": content["subject"],
        "incident_number": incident_number,
        "service": service,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "occurrence_count": occurrence_count
    }

    # Verify SMTP configuration
    missing_fields = []
    if not host:
        missing_fields.append("SMTP_HOST")
    if not sender:
        missing_fields.append("ALERT_EMAIL_FROM")
    if not recipient:
        missing_fields.append("ALERT_EMAIL_TO")

    if missing_fields:
        err_msg = f"SMTP configuration missing: {', '.join(missing_fields)} not configured."
        logger.warning(f"[Email Notifier] Delivery skipped for incident [{incident_number}]: {err_msg}")
        return {
            "status": "FAILED",
            "destination": recipient or "unconfigured",
            "error": err_msg,
            "payload": sanitized_payload
        }

    # Dispatch email via SMTP
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = content["subject"]
        msg["From"] = sender
        msg["To"] = recipient

        msg.attach(MIMEText(content["text"], "plain"))
        msg.attach(MIMEText(content["html"], "html"))

        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=10.0)
        else:
            server = smtplib.SMTP(host, port, timeout=10.0)

        with server:
            if port != 465 and use_tls:
                server.starttls()
            if username and password:
                server.login(username, password)
            server.send_message(msg)

        logger.info(f"[Email Notifier] Successfully delivered escalation email for incident [{incident_number}] to [{recipient}] via [{host}:{port}]")
        return {
            "status": "SENT",
            "destination": recipient,
            "error": None,
            "payload": sanitized_payload
        }

    except Exception as exc:
        err_msg = f"SMTP delivery failed: {type(exc).__name__}: {str(exc)}"
        logger.error(f"[Email Notifier] Failed to deliver escalation email for [{incident_number}] to [{recipient}]: {err_msg}")
        return {
            "status": "FAILED",
            "destination": recipient,
            "error": err_msg,
            "payload": sanitized_payload
        }
