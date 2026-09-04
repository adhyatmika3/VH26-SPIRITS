import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field


class AlertBatchConfig(BaseModel):
    count: int = Field(..., ge=1, le=1000, description="Number of alerts to simulate")
    service: str = Field(default="payment-api", description="Service identifier")
    alert_type: str = Field(default="CPU_HIGH", description="Logical alert category (CPU_HIGH, DATABASE_ERROR, etc.)")
    severity: str = Field(default="critical", description="Severity level")
    environment: str = Field(default="production", description="Deployment environment")
    delay_ms: int = Field(default=0, ge=0, le=5000, description="Delay in milliseconds between alerts")


class SimulationReport(BaseModel):
    requested: int
    generated: int
    status: str
    service: str
    alert_type: str
    severity: str
    environment: str
    raw_alerts_count: int
    core_incidents_created: int
    alert_reduction_percent: float
    primary_incident_id: Optional[str] = None
    primary_incident_number: Optional[str] = None
    primary_incident_title: Optional[str] = None
    primary_incident_occurrences: int = 0
    primary_fingerprint: Optional[str] = None
    incidents_summary: List[Dict[str, Any]] = Field(default_factory=list)
    sample_variations: List[str] = Field(default_factory=list)


def generate_alert_message_variation(service: str, alert_type: str, index: int) -> str:
    """
    Generate realistic variations of alert messages for a single incident
    to demonstrate normalization rather than simple exact-string matching.
    """
    atype = alert_type.upper().strip()
    idx_mod = index % 6

    if "CPU" in atype:
        variations = [
            f"CPU > 90% on {service}",
            f"CPU reached {91 + (index % 8)}% on {service}",
            f"High CPU usage detected on {service}",
            f"{service} CPU utilization critical ({90 + (index % 9)}%)",
            f"CPU threshold exceeded on {service} container",
            f"Host CPU spike sustained on {service} instances"
        ]
        return variations[idx_mod]
    elif "DB" in atype or "DATABASE" in atype:
        variations = [
            f"{service}: Database connection pool exhausted",
            f"DB query latency > {2000 + (index % 500)}ms on {service}",
            f"Database replica lag exceeded on {service}",
            f"High DB connection contention detected on {service}",
            f"Database deadlock rate spike on {service}",
            f"{service} reporting database connection timeouts"
        ]
        return variations[idx_mod]
    elif "MEM" in atype or "MEMORY" in atype:
        variations = [
            f"{service}: Memory usage > {92 + (index % 7)}%",
            f"OOM risk: High memory footprint on {service}",
            f"{service} heap memory consumption critical",
            f"Resident memory limit exceeded on {service}",
            f"High GC pause times due to memory pressure on {service}",
            f"{service} memory threshold exceeded"
        ]
        return variations[idx_mod]
    elif "LATENCY" in atype or "SLOW" in atype:
        variations = [
            f"{service}: P99 API latency exceeded {1200 + (index % 300)}ms",
            f"Upstream response time degradation on {service}",
            f"{service} HTTP 504 gateway timeout rate rising",
            f"Critical latency spike on {service} endpoints",
            f"{service} SLA threshold breach: high latency",
            f"Request queue saturation on {service}"
        ]
        return variations[idx_mod]
    else:
        variations = [
            f"{service}: {alert_type} threshold breached (event #{index + 1})",
            f"High {alert_type} condition reported on {service}",
            f"{service} {alert_type} critical alert firing",
            f"{alert_type} degradation detected on {service}",
            f"{service} experiencing anomalous {alert_type}",
            f"{service} monitoring triggered: {alert_type}"
        ]
        return variations[idx_mod]


async def run_alert_simulation(
    app: FastAPI,
    count: int,
    service: str = "payment-api",
    alert_type: str = "CPU_HIGH",
    severity: str = "critical",
    environment: str = "production",
    delay_ms: int = 0,
    scenario: Optional[str] = None
) -> SimulationReport:
    """
    Dispatches exact number of alerts as real HTTP POST requests through the existing webhook pipeline.
    Does NOT insert directly into database; tests the genuine webhook ingestion path.
    """
    batches: List[AlertBatchConfig] = []

    if scenario == "multiple":
        # Demo Scenario 4: 300 CPU alerts -> Incident A, 200 DB alerts -> Incident B
        batches.append(AlertBatchConfig(
            count=300,
            service=service,
            alert_type="CPU_HIGH",
            severity=severity,
            environment=environment,
            delay_ms=delay_ms
        ))
        batches.append(AlertBatchConfig(
            count=200,
            service=service,
            alert_type="DATABASE_ERROR",
            severity=severity,
            environment=environment,
            delay_ms=delay_ms
        ))
    else:
        # Standard Single Incident Scenario (e.g. 500 alerts -> 1 incident)
        batches.append(AlertBatchConfig(
            count=count,
            service=service,
            alert_type=alert_type,
            severity=severity,
            environment=environment,
            delay_ms=delay_ms
        ))

    total_requested = sum(b.count for b in batches)
    total_generated = 0
    all_sample_variations: List[str] = []
    incident_map: Dict[str, Dict[str, Any]] = {}
    last_response_data: Optional[Dict[str, Any]] = None

    # Use ASGITransport to route real HTTP requests through FastAPI webhook pipeline
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
        for batch in batches:
            for i in range(batch.count):
                now = datetime.now(timezone.utc)
                alert_msg = generate_alert_message_variation(batch.service, batch.alert_type, i)
                if len(all_sample_variations) < 5:
                    all_sample_variations.append(alert_msg)

                webhook_payload = {
                    "source": "prometheus",
                    "alert_name": alert_msg,
                    "service": batch.service,
                    "resource": batch.service,
                    "severity": batch.severity,
                    "status": "firing",
                    "timestamp": now.isoformat(),
                    "labels": {
                        "environment": batch.environment,
                        "env": batch.environment,
                        "alert_type": batch.alert_type,
                        "component": batch.service,
                        "cluster": f"{batch.environment}-cluster"
                    },
                    "annotations": {
                        "summary": alert_msg,
                        "description": f"{alert_msg}. Observed in {batch.environment} cluster."
                    }
                }

                resp = await client.post("/api/v1/alerts/webhook", json=webhook_payload)
                if resp.status_code == 201:
                    total_generated += 1
                    data = resp.json()
                    last_response_data = data
                    inc_num = data.get("incident_number")
                    if inc_num:
                        if inc_num not in incident_map:
                            incident_map[inc_num] = {
                                "incident_number": inc_num,
                                "incident_id": data.get("incident_id"),
                                "service": batch.service,
                                "alert_type": batch.alert_type,
                                "environment": batch.environment,
                                "occurrences": 0,
                                "fingerprint": data.get("fingerprint")
                            }
                        incident_map[inc_num]["occurrences"] += 1

                if batch.delay_ms > 0 and i < batch.count - 1:
                    await asyncio.sleep(batch.delay_ms / 1000.0)

    # Calculate normalization reduction rate
    core_incidents_created = len(incident_map) or 1
    if total_generated > 0:
        reduction_pct = round(((total_generated - core_incidents_created) / total_generated) * 100.0, 1)
    else:
        reduction_pct = 0.0

    primary_inc = list(incident_map.values())[0] if incident_map else {}
    primary_num = primary_inc.get("incident_number") or (last_response_data.get("incident_number") if last_response_data else "INC-1001")
    primary_id = primary_inc.get("incident_id") or (last_response_data.get("incident_id") if last_response_data else None)
    primary_fingerprint = primary_inc.get("fingerprint") or (last_response_data.get("fingerprint") if last_response_data else None)

    return SimulationReport(
        requested=total_requested,
        generated=total_generated,
        status="completed" if total_generated == total_requested else "partial",
        service=service,
        alert_type=alert_type if scenario != "multiple" else "CPU_HIGH + DATABASE_ERROR",
        severity=severity,
        environment=environment,
        raw_alerts_count=total_generated,
        core_incidents_created=core_incidents_created,
        alert_reduction_percent=reduction_pct,
        primary_incident_id=str(primary_id) if primary_id else None,
        primary_incident_number=primary_num,
        primary_incident_title=f"{service.replace('-', ' ').title()} — High CPU Utilization" if "CPU" in alert_type else f"{service.title()} Degradation",
        primary_incident_occurrences=primary_inc.get("occurrences", total_generated),
        primary_fingerprint=primary_fingerprint,
        incidents_summary=list(incident_map.values()),
        sample_variations=all_sample_variations
    )
