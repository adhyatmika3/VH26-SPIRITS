"""
Alert Fatigue Buster - SRE Intelligence Backend API (FastAPI)
"""

import time
import asyncio
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(
    title="Alert Fatigue Buster API",
    description="Algorithmic telemetry reduction and SRE incident correlation engine.",
    version="1.0.0"
)

# Enable CORS for frontend web application
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-Memory Database / State Store
stats_store = {
    "incomingAlerts": 2481,
    "actionableAlerts": 37,
    "noiseReductionPercent": 98.5,
    "activeIncidentsCount": 2,
    "criticalAlertsCount": 2,
    "mttrSeconds": 252,
    "ingressVelocity": 142.8,
    "fatigueAbsorptionPercent": 91.4,
    "droppedAlerts": 2267,
    "decisionLatencyMs": 11.8,
    "activeDedupePool": 63
}

alerts_db = [
    {
        "id": "ALT-9042",
        "fingerprint": "e4f8a91c",
        "timestamp": "10:34:12",
        "service": "payment-gateway",
        "cluster": "us-east-prod-k8s",
        "severity": "CRITICAL",
        "title": "PostgresConnectionPoolExhausted",
        "message": "Connection pool utilization > 98% for 45s across 8 poolers.",
        "status": "TRIGGERED",
        "group": "GRP-DB-POOL-01",
        "occurrences": 142,
        "suppressed": False,
        "actionable": True
    },
    {
        "id": "ALT-9041",
        "fingerprint": "b21a78ff",
        "timestamp": "10:34:05",
        "service": "checkout-api",
        "cluster": "us-east-prod-k8s",
        "severity": "HIGH",
        "title": "HTTP5xxRateSpike",
        "message": "HTTP 502 Bad Gateway response rate exceeded 4.5% threshold.",
        "status": "TRIGGERED",
        "group": "GRP-DB-POOL-01",
        "occurrences": 89,
        "suppressed": False,
        "actionable": True
    }
]

incidents_db = [
    {
        "id": "INC-1042",
        "title": "Database Connection Cascade on postgres-primary",
        "severity": "CRITICAL",
        "status": "INVESTIGATING",
        "startTime": "14:32:08 UTC",
        "duration": "18m ago",
        "owner": "Alex Rivera (Lead SRE)",
        "leadService": "payment-gateway",
        "description": "Cascading connection pool failure on postgres-primary impacting downstream checkout.",
        "alertsCount": 429,
        "actionableCount": 1
    }
]

# Pydantic Models
class IngestAlertRequest(BaseModel):
    service: str
    cluster: Optional[str] = "us-east-prod-k8s"
    severity: str
    title: str
    message: str
    fingerprint: Optional[str] = None

class CreateIncidentRequest(BaseModel):
    title: str
    severity: str
    leadService: str
    description: str

@app.get("/api/health")
def get_health():
    return {"status": "ok", "engine": "Buster Engine v1.0", "timestamp": time.time()}

@app.get("/api/stats")
def get_stats():
    return stats_store

@app.get("/api/alerts")
def get_alerts(service: Optional[str] = None, severity: Optional[str] = None):
    res = alerts_db
    if service:
        res = [a for a in res if a["service"] == service]
    if severity:
        res = [a for a in res if a["severity"] == severity]
    return res

@app.post("/api/alerts")
def ingest_alert(alert: IngestAlertRequest):
    stats_store["incomingAlerts"] += 1
    
    # Deduplication Logic
    fp = alert.fingerprint or f"fp-{hash(alert.title + alert.service) % 1000000:x}"
    existing = next((a for a in alerts_db if a.get("fingerprint") == fp), None)
    
    if existing:
        existing["occurrences"] += 1
        stats_store["droppedAlerts"] += 1
        return {"action": "deduplicated", "alertId": existing["id"], "occurrences": existing["occurrences"]}
    
    new_alert = {
        "id": f"ALT-{int(time.time() * 1000) % 10000}",
        "fingerprint": fp,
        "timestamp": time.strftime("%H:%M:%S"),
        "service": alert.service,
        "cluster": alert.cluster,
        "severity": alert.severity,
        "title": alert.title,
        "message": alert.message,
        "status": "TRIGGERED",
        "group": "GRP-DYNAMIC",
        "occurrences": 1,
        "suppressed": False,
        "actionable": True if alert.severity in ["CRITICAL", "HIGH"] else False
    }
    alerts_db.insert(0, new_alert)
    if new_alert["actionable"]:
        stats_store["actionableAlerts"] += 1
    return {"action": "created", "alert": new_alert}

@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str):
    for a in alerts_db:
        if a["id"] == alert_id:
            a["status"] = "ACKNOWLEDGED"
            return {"status": "success", "alertId": alert_id}
    raise HTTPException(status_code=404, detail="Alert not found")

@app.post("/api/alerts/{alert_id}/suppress")
def suppress_alert(alert_id: str):
    for a in alerts_db:
        if a["id"] == alert_id:
            a["suppressed"] = True
            a["actionable"] = False
            a["status"] = "SUPPRESSED_MANUAL"
            stats_store["droppedAlerts"] += 1
            return {"status": "success", "alertId": alert_id}
    raise HTTPException(status_code=404, detail="Alert not found")

@app.get("/api/incidents")
def get_incidents():
    return incidents_db

@app.post("/api/incidents")
def create_incident(inc: CreateIncidentRequest):
    new_inc = {
        "id": f"INC-{int(time.time() * 1000) % 10000}",
        "title": inc.title,
        "severity": inc.severity,
        "status": "INVESTIGATING",
        "startTime": time.strftime("%H:%M:%S UTC"),
        "duration": "0m ago",
        "owner": "Alex Rivera (Lead SRE)",
        "leadService": inc.leadService,
        "description": inc.description,
        "alertsCount": 1,
        "actionableCount": 1
    }
    incidents_db.insert(0, new_inc)
    stats_store["activeIncidentsCount"] += 1
    return new_inc

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
