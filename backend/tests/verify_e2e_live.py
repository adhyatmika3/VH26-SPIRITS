import urllib.request
import json
import time

services = ['payment-service', 'auth-service', 'inventory-service', 'billing-service']
severities = ['critical', 'high', 'medium', 'low']

print("--- Ingesting 20 live scenario alerts ---")
for i in range(20):
    svc = services[i % len(services)]
    sev = severities[i % len(severities)]
    payload = {
        "source": "prometheus" if i % 2 == 0 else "datadog",
        "alert_name": f"HighCPU_{svc}" if i % 3 != 0 else "DBConnectionSpike",
        "service": svc,
        "severity": sev,
        "status": "firing",
        "timestamp": "2026-09-04T12:00:00Z",
        "labels": {"environment": "production"},
        "annotations": {"runbook": "http://wiki/runbook"}
    }
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/alerts/webhook",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read())
        print(f"Alert {i+1}: Decision={res.get('decision')}, Incident={res.get('incident_number')}")
    time.sleep(0.05)

print("\n--- Querying Live Analytics Overview ---")
with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/analytics/overview") as resp:
    print(json.dumps(json.loads(resp.read()), indent=2))

print("\n--- Querying Noisy Services ---")
with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/analytics/noisy-services?limit=5") as resp:
    print(json.dumps(json.loads(resp.read()), indent=2))

print("\n--- Querying Severity Breakdown ---")
with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/analytics/alerts-by-severity") as resp:
    print(json.dumps(json.loads(resp.read()), indent=2))

print("\n--- Inspecting /metrics sample ---")
with urllib.request.urlopen("http://127.0.0.1:8000/metrics") as resp:
    lines = [l for l in resp.read().decode().splitlines() if "alerts_" in l or "alert_processing_" in l]
    print("\n".join(lines[:12]))
