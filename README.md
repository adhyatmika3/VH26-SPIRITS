# Alert Fatigue Buster - SRE Intelligence & Telemetry Reduction Web Platform

Alert Fatigue Buster is a state-of-the-art SRE telemetry reduction and alert grouping platform designed to mitigate cognitive fatigue during high-volume system incidents.

## Project Structure

```
├── frontend/                     # Interactive Web Application
│   ├── index.html                # Unified multi-screen SRE Web Console
│   ├── css/
│   │   └── style.css             # Design tokens & micro-animations
│   ├── js/
│   │   ├── app.js                # Router, state store, streaming & triage actions
│   │   └── mockData.js           # SRE Telemetry & incident dataset
│   ├── package.json              # Web server script configuration
│   └── README.md
│
├── backend/                      # API Backend Server
│   ├── app.py                    # Python FastAPI server
│   ├── requirements.txt          # Python dependencies
│   ├── server.js                 # Node.js Express server
│   ├── package.json              # Node dependencies
│   └── README.md
│
├── alert_groups_deduplication_light/  # Screen 1 source reference
├── incident_details_light/            # Screen 2 source reference
├── live_alerts_stream_light/          # Screen 3 source reference
├── operations_overview_light/         # Screen 4 source reference
└── alert_fatigue_buster/              # Design specification
```

## Architecture & Pipeline

```text
External Monitoring (Prometheus / Alertmanager)
                  ↓
          Webhook Ingestion
                  ↓
Stage 1: Raw Audit Trail (`raw_alerts`)
                  ↓
Stage 2: Alert Intelligence & Correlation
         (Normalize → Fingerprint → Deduplicate → Storm Velocity → Correlate → Priority)
                  ↓
Stage 3: Decision Engine, Suppression & Escalation
         ├── State & Identity Evaluation
         ├── NOTIFY   → Dispatch Slack Block Kit Message (INITIAL / RESOLUTION)
         ├── SUPPRESS → Audit in `decision_records` (DUPLICATE_ALERT / COOLDOWN_ACTIVE)
         └── ESCALATE → Escalate to Level 1, Record `escalation_records`, Dispatch Slack Alert
                  ↓
         PostgreSQL 16 Storage
                  ↓
         Prometheus Metrics Exporter (`/metrics`)
                  ↓
         Grafana Telemetry Dashboards
```

---

## Phase 3: Decision, Suppression, Escalation & Slack Notification Layer

### 1. Deterministic Decision Engine
- Evaluates Phase 2 output in strict order:
  1. **New Incident**: Initial alert on a new incident produces `NOTIFY` with structured reason codes (e.g. `["NEW_INCIDENT", "PRODUCTION_ENVIRONMENT"]`).
  2. **Incident-Level Resolution**: Individual alert resolution does *not* prematurely close multi-alert incidents. When *all* active alerts resolve or an operator resolves the incident, it transitions to `RESOLVED` and dispatches an `INCIDENT_RESOLVED` notification.
  3. **Severity / Priority Escalation**: Re-notifies when priority jumps (e.g. MEDIUM -> CRITICAL).
  4. **Active Cooldown Suppression**: Duplicate webhooks within `ALERT_COOLDOWN_SECONDS` are marked `SUPPRESS` (`["DUPLICATE_ALERT", "COOLDOWN_ACTIVE"]`), preventing notification spam.
  5. **Escalation Threshold**: Unresolved critical incidents exceeding `ESCALATION_THRESHOLD_SECONDS` or burst counts trigger `ESCALATE` (Level 1). Database unique constraints on `(incident_id, escalation_level)` prevent redundant re-escalations at the same level.
  6. **Default In-Flight Fatigue Suppression**: Correlated alerts joining active open incidents are audited in `decision_records` as `SUPPRESS` (`["CORRELATED_INCIDENT_ACTIVE"]`).

### 2. Slack Notification Service & Payload Sanitization
- Formats rich Slack Block Kit notifications with severity indicators (`🚨 CRITICAL`, `🔥 ESCALATION`, `✅ RESOLVED`), contextual incident details, and "Why you are seeing this" bulleted rationale.
- **Security**: Sensitive bot tokens, webhook secrets, and authorization credentials are fully redacted before audit storage in `notification_records.payload`.
- **Resilience**: If Slack API fails or network drops, core alert processing and database transactions succeed, saving `status = FAILED` and incrementing Prometheus failure counters.

### 3. API Endpoints
- `POST /api/v1/alerts/webhook` — Ingest, normalize, correlate, decide, and dispatch alert.
- `GET /api/v1/alerts` — Query canonical alerts with filtering and pagination.
- `GET /api/v1/alerts/stats` — Noise reduction statistics and storm velocity status.
- `GET /api/v1/incidents` — Query correlated incidents.
- `GET /api/v1/incidents/{id}` — Incident details with attached canonical alerts.
- `POST /api/v1/incidents/{id}/acknowledge` — Acknowledge incident with operator attribution.
- `POST /api/v1/incidents/{id}/resolve` — Resolve incident and all attached alerts.
- `POST /api/v1/incidents/{id}/notify` — Manually trigger notification.
- `GET /api/v1/decisions` — List audit history of decisions and reason codes.
- `GET /api/v1/decisions/{id}` — Single decision detail.
- `GET /api/v1/notifications` — Notification dispatch logs.
- `GET /api/v1/escalations` — Escalation history and levels.
- `GET /metrics` — Prometheus metrics exposition.

### 4. Prometheus Metrics Exporter
- `alerts_decided_total{decision, severity, environment, service}`
- `alerts_suppressed_total{reason_code, service}`
- `alerts_notified_total{priority, channel, service}`
- `alerts_escalated_total{severity, service}`
- `notification_success_total{channel}`
- `notification_failure_total{channel}`
- `alert_acknowledgements_total{service}`
- `alert_resolutions_total{service}`

---

## Phase 4: Observability, Analytics & Dashboard Integration

Phase 4 introduces a complete operational observability and persistent analytics layer, seamlessly integrated with the intelligence and decision pipeline.

### 1. Observability vs. Analytics Architecture

```
                ┌──────────────────┐
                │  Alert Sources   │ (Prometheus, Datadog, CloudWatch, Grafana)
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │ FastAPI Webhook  │ POST /api/v1/alerts/webhook
                │    Ingestion     │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │   PostgreSQL 16  │ Tables: raw_alerts, canonical_alerts, incidents,
                │ Alert Persistence│         decision_records, notification_records
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │ Intelligence     │ Normalize → Fingerprint → Deduplicate →
                │    Pipeline      │ Storm Detector → Correlate → Priority
                └────────┬─────────┘
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
         SUPPRESS     NOTIFY      ESCALATE
                         │
                         ▼
                   ┌──────────┐
                   │  Slack   │ (Rich Block Kit with payload sanitization)
                   └──────────┘

    ┌────────────────────────────────────────────────────────┐
    │              OPERATIONAL OBSERVABILITY LAYER           │
    │                                                        │
    │  FastAPI (app/core/metrics.py)                         │
    │     ├── GET /metrics (Prometheus Python Client)        │
    │     ▼                                                  │
    │  Prometheus (scrapes backend:8000/metrics every 5s)    │
    │     ▼                                                  │
    │  Grafana (http://localhost:3001)                       │
    │     └── 10-Panel Alert Fatigue Buster Dashboard        │
    └────────────────────────────────────────────────────────┘

    ┌────────────────────────────────────────────────────────┐
    │             PERSISTENT HISTORICAL ANALYTICS LAYER      │
    │                                                        │
    │  PostgreSQL (indexed aggregation & latency metadata)   │
    │     ▼                                                  │
    │  Analytics Service (services/analytics_service.py)     │
    │     ▼                                                  │
    │  FastAPI REST APIs (/api/v1/analytics/*)               │
    │     ▼                                                  │
    │  Frontend SRE Console (auto-refresh live telemetry)    │
    └────────────────────────────────────────────────────────┘
```

### 2. Prometheus Operational Metrics (`GET /metrics`)

Exposed with strictly bounded, low-cardinality labels to guarantee optimal Prometheus performance:

| Metric Name | Type | Labels | Description |
|---|---|---|---|
| `alerts_received_total` | Counter | `source`, `severity` | Total count of raw alerts ingested |
| `alerts_processed_total` | Counter | `source`, `severity`, `decision` | Total alerts processed through intelligence pipeline |
| `alerts_suppressed_total` | Counter | `reason_code`, `service` | Total count of alerts suppressed by decision engine |
| `alerts_notified_total` | Counter | `priority`, `channel`, `service` | Total count of alerts approved for notification |
| `alerts_escalated_total` | Counter | `severity`, `service` | Total count of alerts escalated to higher urgency |
| `alert_processing_failures_total` | Counter | `stage` | Failures encountered during intelligence processing |
| `notification_failures_total` | Counter | `channel` | Notification delivery failure count |
| `alert_processing_duration_seconds` | Histogram | `stage` | Latency distribution of alert processing (buckets: 5ms to 10s) |
| `notification_duration_seconds` | Histogram | `channel` | Time taken to deliver notification to Slack |
| `alerts_in_processing` | Gauge | — | Current count of alerts actively being processed |

### 3. Grafana 10-Panel Dashboard (Provisioned as Code)

Provisioned automatically via YAML configurations without manual intervention:
- **Datasource**: Automatic Prometheus datasource pointing to `http://prometheus:9090`.
- **Dashboard File**: `monitoring/grafana/dashboards/alert_fatigue_buster.json`.
- **Panels**:
  1. **Panel 1 — Total Alert Volume**: Ingress rate (`rate(alerts_received_total[1m])`) and 5-minute volume.
  2. **Panel 2 — Suppression Rate**: Real-time percentage of noise absorbed (`alerts_decided_total{decision="SUPPRESS"}`).
  3. **Panel 3 — Notification Rate**: Percentage of alerts forwarded to operators.
  4. **Panel 4 — Escalation Rate**: Percentage of incidents escalated due to severity or repeat counts.
  5. **Panel 5 — Alert Decisions**: Stacked timeseries visualizing `SUPPRESS`, `NOTIFY`, and `ESCALATE` streams.
  6. **Panel 6 — Severity Distribution**: Pie chart across normalized severities (`CRITICAL`, `ERROR`, `WARNING`, `INFO`).
  7. **Panel 7 — Top Noisy Services**: Bar chart ranking microservices by raw alert volume.
  8. **Panel 8 — Processing Latency**: Average, P95, and P99 latency calculated from histogram buckets.
  9. **Panel 9 — Processing Failures**: Pipeline failure trends over time.
  10. **Panel 10 — Notification Failures**: Slack delivery failures over time.

### 4. Database Schema Extensions & Migration

- **Migration**: `004_phase4_analytics_metadata` (`backend/alembic/versions/004_phase4_analytics_metadata.py`).
- **Schema Modification**:
  - `decision_records.processing_time_ms`: Precision float recording the end-to-end intelligence duration in milliseconds.
  - Reversible upgrade and downgrade routines.

### 5. Analytics REST APIs (`/api/v1/analytics/*` and `/api/analytics/*`)

Optimized with PostgreSQL database-level aggregations (`func.count`, `func.sum(case(...))`, `func.avg`, `func.date_trunc`):

- `GET /api/v1/analytics/overview` — Overview metrics: `total_alerts`, `processed_alerts`, `suppressed_alerts`, `notified_alerts`, `escalated_alerts`, `suppression_rate`, `notification_rate`, `escalation_rate`, `alert_reduction`, `average_processing_time_ms`.
- `GET /api/v1/analytics/alerts-by-severity` — Severity breakdown and percentage distribution.
- `GET /api/v1/analytics/alerts-by-source` — Monitoring tool distribution (Prometheus, Datadog, Grafana, CloudWatch).
- `GET /api/v1/analytics/alerts-by-service` — Service volume distribution.
- `GET /api/v1/analytics/noisy-services?limit=10` — Top noisy services ranked by total alerts, with per-service suppression rates.
- `GET /api/v1/analytics/timeline?interval=hour` — Time-series bucketed volume (`minute`, `hour`, `day`).
- `GET /api/v1/analytics/decisions` — Counts of `suppressed`, `notified`, and `escalated` decisions.

### 6. Frontend Integration

- The SRE Web Console dynamically polls `/api/v1/analytics/overview` to update live KPI cards (`Incoming Alerts`, `Actionable Alerts`, `Suppression %`, `Active Dedupe Pool`).
- Added dedicated **Observability Stack** navigation group in the sidebar with direct links to:
  - **Grafana Dashboard** (`http://localhost:3001`)
  - **Prometheus Metrics** (`http://localhost:8000/metrics`)
  - **Analytics API** (`http://localhost:8000/api/v1/analytics/overview`)

---

## Running the Platform Locally

### Docker Compose (Full Production Stack)

```bash
docker compose up -d
```

This automatically boots:
1. **PostgreSQL 16**: `localhost:5432`
2. **FastAPI Backend**: `http://localhost:8000`
3. **Prometheus**: `http://localhost:9090` (scraping `backend:8000/metrics` every 5s)
4. **Grafana**: `http://localhost:3001` (pre-provisioned with Prometheus datasource & 10-panel dashboard)

### Standalone Backend (FastAPI + PostgreSQL)

```bash
cd backend
# 1. Run migrations
alembic upgrade head

# 2. Start server
python -m uvicorn app.main:app --port 8000
```

### Standalone Frontend (SRE Console)

```bash
cd frontend
python -m http.server 3000
```
Open **`http://localhost:3000`** in your browser.

### Running Automated Test Suite

```bash
cd backend
python -m pytest tests/ -v
```
All **35/35 tests passing** covering Phases 0, 1, 2, 3, and 4.