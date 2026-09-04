# Alert Fatigue Buster - Frontend Web Application

A precision-engineered SRE observability and alert noise reduction platform built with standard HTML5, CSS3, Tailwind CSS, and Vanilla JavaScript.

## Features
- **Operations Overview Dashboard**: Real-time KPI deck, interactive sparklines, noise reduction telemetry stream.
- **Live Alerts Stream**: Live updating telemetry stream with severity badges, acknowledge / suppress quick actions, and simulated burst engine.
- **Alert Groups & Deduplication**: Dynamic fingerprint grouping and noise suppression clusters within sliding temporal windows.
- **Incident Details & Runbooks**: Full triage console with correlated root causes, postgres telemetry graphs, and interactive 5-step runbook execution.
- **Interactive Global ⌘K Search**: Instant search across all alerts, incidents, services, and fingerprints.
- **Incident Creator Modal**: Declare new SRE incidents and route them to on-call teams.
- **Export Telemetry**: Export full telemetry snapshots as JSON.

## How to Run

### Option 1: Live HTTP Server (Recommended)
```bash
# Inside the frontend/ directory:
npx serve -p 3000 .
# or with Python
python -m http.server 3000
```
Then open `http://localhost:3000` in your web browser.

### Option 2: Direct Browser Open
Simply double-click `frontend/index.html` or open it directly in Google Chrome, Microsoft Edge, or Firefox.
