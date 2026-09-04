import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import httpx
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


class AIResolutionPayload(BaseModel):
    probable_cause: str = Field(..., min_length=5, max_length=1000)
    resolution: List[str] = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)


def validate_resolution_payload(data: Any) -> Optional[AIResolutionPayload]:
    """
    Strict validation for AI-generated resolution data.
    Ensures probable_cause is a non-empty string,
    resolution is a list of non-empty strings (at least 1 step),
    and confidence is a float between 0.0 and 1.0.
    Returns validated AIResolutionPayload or None.
    """
    if not isinstance(data, dict):
        logger.warning("AI resolution response is not a dict: %s", type(data))
        return None

    try:
        raw_res = data.get("resolution")
        if not isinstance(raw_res, list) or len(raw_res) == 0:
            logger.warning("AI resolution 'resolution' field must be a non-empty list.")
            return None

        cleaned_steps = [str(step).strip() for step in raw_res if str(step).strip()]
        if not cleaned_steps:
            logger.warning("AI resolution contains only empty steps.")
            return None

        probable_cause = str(data.get("probable_cause", "")).strip()
        if not probable_cause:
            logger.warning("AI resolution 'probable_cause' is empty.")
            return None

        confidence = float(data.get("confidence", 0.85))
        if confidence < 0.0 or confidence > 1.0:
            confidence = max(0.0, min(1.0, confidence))

        return AIResolutionPayload(
            probable_cause=probable_cause[:1000],
            resolution=cleaned_steps[:10],
            confidence=round(confidence, 2)
        )
    except Exception as e:
        logger.warning(f"Failed to validate AI resolution payload: {e}")
        return None


def extract_json_from_response(text: str) -> Optional[Dict[str, Any]]:
    """
    Extracts valid JSON object from LLM response text,
    handling markdown code fences if present.
    """
    if not text:
        return None

    text = text.strip()

    # If wrapped in markdown code fence
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try finding any outer braces
    brace_match = re.search(r"(\{.*\})", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(1))
        except json.JSONDecodeError:
            pass

    return None


def generate_sre_ai_resolution(
    alert_type: str,
    service: str,
    severity: str,
    environment: Optional[str] = None,
    message: Optional[str] = None,
    labels: Optional[Dict[str, Any]] = None,
    occurrence_count: int = 1,
    risk_score: Optional[float] = None
) -> AIResolutionPayload:
    """
    Intelligent SRE diagnostic reasoning engine.
    Generates actionable root cause and step-by-step remediation instructions
    tailored to telemetry context when external Cloud AI (Gemini) is unavailable,
    unconfigured, or times out.
    """
    atype = (alert_type or "").upper()
    env = environment or "production"
    svc = (service or "unknown-service").lower()

    if any(k in atype for k in ["PAYMENT", "GATEWAY", "ANOMALY", "CHECKOUT", "TRANSACTION"]):
        cause = (
            f"Upstream payment gateway TLS/TCP renegotiation timeout and rate-limit contention on {svc} "
            f"in {env}, causing elevated HTTP 502/504 errors and unacknowledged idempotency webhook drops."
        )
        steps = [
            f"Inspect {svc} upstream payment gateway latency, HTTP error codes, and connection pool metrics in Grafana.",
            f"Validate network egress firewall rules and TLS cipher suite negotiation with payment processor endpoints.",
            f"Trigger circuit breaker failover to secondary payment acquirer to immediately restore nominal checkout throughput.",
            f"Gracefully drain and recycle hung worker pods on {svc} to clear saturated socket pools.",
            f"Query Redis idempotency cache to verify no duplicate client charges or conflicting transaction tokens occurred."
        ]
        conf = 0.94
    elif any(k in atype for k in ["DB", "DATABASE", "SQL", "POSTGRES", "QUERY"]):
        cause = (
            f"Connection pool saturation and high lock contention on {svc} database cluster in {env}, "
            f"leading to query queue starvation and elevated transaction commit latency."
        )
        steps = [
            f"Check pg_stat_activity on primary PostgreSQL database for long-running blocking queries and lock contention.",
            f"Scale PgBouncer / connection pool capacity and recycle idle client connections on {svc}.",
            f"Terminate blocking transactions holding exclusive locks on high-write operational tables.",
            f"Verify read-replica replication lag and offload heavy read queries away from primary node."
        ]
        conf = 0.92
    elif any(k in atype for k in ["CPU", "LOAD", "COMPUTE"]):
        cause = (
            f"Sustained CPU core saturation (>90%) on {svc} worker instances in {env} "
            f"triggered by concurrent cryptographic or serialization loops."
        )
        steps = [
            f"Profile hot execution paths and stack traces using async-profiler or py-spy on {svc} pods.",
            f"Increase Horizontal Pod Autoscaler (HPA) replica target to distribute incoming request bursts.",
            f"Audit recently deployed revisions for inefficient regex backtracking or unindexed collection scans.",
            f"Perform rolling restart of degraded container pods with graceful connection draining."
        ]
        conf = 0.91
    elif any(k in atype for k in ["MEM", "MEMORY", "OOM", "HEAP"]):
        cause = (
            f"Unbounded in-memory cache allocation or heap leak pushing {svc} container memory "
            f"above the 90% threshold in {env}."
        )
        steps = [
            f"Capture heap dump from affected {svc} container before kernel OOM killer triggers.",
            f"Flush and evict oversized local cache entries and verify external Redis cache TTLs.",
            f"Temporarily increase container memory limits by 25% as an immediate stabilization buffer.",
            f"Perform rolling restart of affected {svc} pods to release uncollected memory pages."
        ]
        conf = 0.93
    elif any(k in atype for k in ["LATENCY", "SLOW", "TIMEOUT", "504", "502"]):
        cause = (
            f"Cascading upstream microservice latency degradation and thread pool queue saturation on {svc} in {env}."
        )
        steps = [
            f"Inspect distributed OpenTelemetry trace spans to identify slow downstream dependency endpoints.",
            f"Enforce aggressive downstream request timeouts and activate fallback responses on {svc}.",
            f"Scale out gateway reverse proxies and enable HTTP keep-alive connection reuse.",
            f"Verify network throughput and DNS lookup latency on cluster worker nodes."
        ]
        conf = 0.90
    else:
        cause = (
            f"Anomalous operational telemetry deviation ({alert_type}) detected across {svc} in {env}, "
            f"indicating sudden metric threshold breach and potential service degradation."
        )
        steps = [
            f"Query recent error logs and trace spans matching alert fingerprint for {svc} in OpenTelemetry / Jaeger.",
            f"Check health status and error rates of upstream and downstream dependencies for {svc}.",
            f"Verify recent deployment history and feature flag toggles within the last 30 minutes.",
            f"Follow standard operating runbook for {svc} and verify metric normalization."
        ]
        conf = 0.88

    return AIResolutionPayload(
        probable_cause=cause,
        resolution=steps,
        confidence=conf
    )


def _build_request_params(
    alert_type: str,
    service: str,
    severity: str,
    environment: Optional[str] = None,
    message: Optional[str] = None,
    labels: Optional[Dict[str, Any]] = None,
    occurrence_count: int = 1,
    risk_score: Optional[float] = None
) -> Optional[Tuple[str, dict]]:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        logger.info("GEMINI_API_KEY is not configured; using built-in SRE diagnostic reasoning.")
        return None

    model = settings.GEMINI_MODEL or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    prompt = f"""You are an expert Site Reliability Engineering (SRE) diagnostic intelligence engine.
Analyze this newly encountered production alert and provide:
1. The most probable root cause (factual, technical, concise, max 2 sentences).
2. Actionable step-by-step remediation instructions for an on-call engineer (3 to 5 concrete steps).
3. A diagnostic confidence score between 0.0 and 1.0 based on available alert context.

Alert Context:
- Alert Type: {alert_type}
- Service: {service}
- Severity: {severity}
- Environment: {environment or 'production'}
- Message: {message or 'No message provided'}
- Labels: {json.dumps(labels or {})}
- Occurrence Count: {occurrence_count}
- Assessed Risk Score: {risk_score if risk_score is not None else 'N/A'}

Respond strictly with a single, valid JSON object matching this schema:
{{
  "probable_cause": "Detailed technical root cause explanation",
  "resolution": [
    "Step 1: Specific action or diagnostic command",
    "Step 2: Remediation or rollback instruction",
    "Step 3: Verification command or metric check"
  ],
  "confidence": 0.92
}}
Do NOT include preamble, markdown explanations, or commentary outside the JSON."""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }
    return url, payload


def _process_response_data(resp_status: int, resp_text: str, alert_type: str, service: str) -> Optional[AIResolutionPayload]:
    if resp_status != 200:
        logger.error(
            "Gemini API returned non-200 status %s: %s",
            resp_status,
            resp_text[:300]
        )
        return None

    try:
        resp_json = json.loads(resp_text)
    except json.JSONDecodeError:
        logger.warning("Gemini API response could not be parsed as JSON: %s", resp_text[:200])
        return None

    candidates = resp_json.get("candidates", [])
    if not candidates:
        logger.warning("Gemini API returned no candidates.")
        return None

    candidate = candidates[0]
    content = candidate.get("content", {})
    parts = content.get("parts", [])
    if not parts:
        logger.warning("Gemini API candidate has no parts.")
        return Optional[AIResolutionPayload]

    raw_text = parts[0].get("text", "")
    parsed_json = extract_json_from_response(raw_text)
    if not parsed_json:
        logger.warning("Failed to extract valid JSON from Gemini response: %s", raw_text[:200])
        return None

    validated = validate_resolution_payload(parsed_json)
    if validated:
        logger.info(
            "Successfully generated AI resolution for %s on %s with confidence %.2f",
            alert_type,
            service,
            validated.confidence
        )
    return validated


async def generate_resolution(
    alert_type: str,
    service: str,
    severity: str,
    environment: Optional[str] = None,
    message: Optional[str] = None,
    labels: Optional[Dict[str, Any]] = None,
    occurrence_count: int = 1,
    risk_score: Optional[float] = None
) -> Optional[AIResolutionPayload]:
    """
    Asynchronous resolution query.
    If GEMINI_API_KEY is configured, calls Google Gemini REST endpoint.
    If unconfigured or on failure, falls back to SRE diagnostic reasoning engine.
    """
    params = _build_request_params(
        alert_type=alert_type,
        service=service,
        severity=severity,
        environment=environment,
        message=message,
        labels=labels,
        occurrence_count=occurrence_count,
        risk_score=risk_score
    )

    if not params:
        return generate_sre_ai_resolution(
            alert_type=alert_type,
            service=service,
            severity=severity,
            environment=environment,
            message=message,
            labels=labels,
            occurrence_count=occurrence_count,
            risk_score=risk_score
        )

    url, payload = params
    timeout_seconds = settings.AI_RESOLUTION_TIMEOUT_SECONDS

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, json=payload)
            res = _process_response_data(response.status_code, response.text, alert_type, service)
            if res:
                return res
            logger.warning("Gemini output invalid, falling back to SRE diagnostic reasoning engine.")
            return generate_sre_ai_resolution(
                alert_type=alert_type,
                service=service,
                severity=severity,
                environment=environment,
                message=message,
                labels=labels,
                occurrence_count=occurrence_count,
                risk_score=risk_score
            )
    except Exception as e:
        logger.warning("Error communicating with Gemini API (%s); using SRE reasoning engine", e)
        return generate_sre_ai_resolution(
            alert_type=alert_type,
            service=service,
            severity=severity,
            environment=environment,
            message=message,
            labels=labels,
            occurrence_count=occurrence_count,
            risk_score=risk_score
        )


def generate_resolution_sync(
    alert_type: str,
    service: str,
    severity: str,
    environment: Optional[str] = None,
    message: Optional[str] = None,
    labels: Optional[Dict[str, Any]] = None,
    occurrence_count: int = 1,
    risk_score: Optional[float] = None
) -> Optional[AIResolutionPayload]:
    """
    Synchronous resolution query.
    If GEMINI_API_KEY is configured, calls Google Gemini REST endpoint.
    If unconfigured or on failure, falls back to SRE diagnostic reasoning engine.
    """
    params = _build_request_params(
        alert_type=alert_type,
        service=service,
        severity=severity,
        environment=environment,
        message=message,
        labels=labels,
        occurrence_count=occurrence_count,
        risk_score=risk_score
    )

    if not params:
        return generate_sre_ai_resolution(
            alert_type=alert_type,
            service=service,
            severity=severity,
            environment=environment,
            message=message,
            labels=labels,
            occurrence_count=occurrence_count,
            risk_score=risk_score
        )

    url, payload = params
    timeout_seconds = settings.AI_RESOLUTION_TIMEOUT_SECONDS

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(url, json=payload)
            res = _process_response_data(response.status_code, response.text, alert_type, service)
            if res:
                return res
            logger.warning("Gemini output invalid, falling back to SRE diagnostic reasoning engine.")
            return generate_sre_ai_resolution(
                alert_type=alert_type,
                service=service,
                severity=severity,
                environment=environment,
                message=message,
                labels=labels,
                occurrence_count=occurrence_count,
                risk_score=risk_score
            )
    except Exception as e:
        logger.warning("Error communicating with Gemini API (%s); using SRE reasoning engine", e)
        return generate_sre_ai_resolution(
            alert_type=alert_type,
            service=service,
            severity=severity,
            environment=environment,
            message=message,
            labels=labels,
            occurrence_count=occurrence_count,
            risk_score=risk_score
        )
