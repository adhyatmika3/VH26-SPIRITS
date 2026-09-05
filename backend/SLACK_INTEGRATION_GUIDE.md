# Phase 8 — Slackbot Incident Notification & Interaction Guide

This guide details how to configure a real Slack App with the Alert Fatigue Buster SRE Intelligence Platform to receive rich Block Kit incident alerts and interact with incidents directly from Slack.

---

## Architecture Overview

```text
Raw Alerts (500)
       ↓
FastAPI Ingestion
       ↓
PostgreSQL Persistence
       ↓
Fingerprinting & Deduplication (499 repeats suppressed)
       ↓
Correlation Engine
       ↓
1 Core Incident (INC-XXX)
       ↓
Risk Scoring Engine (Score: 96/100)
       ↓
Decision Engine (CRITICAL / Level 1)
       ↓
 ┌───────────────────────────┴───────────────────────────┐
 ↓                                                       ↓
Email Escalation Service                           Slackbot Service
(1 Email dispatched)                              (1 Block Kit Message dispatched)
                                                         ↓
                                                PostgreSQL Idempotency Check
                                                (1-to-1 per incident enforced)
                                                         ↓
                                                Interactive Buttons:
                                                [Acknowledge] [Resolve]
                                                [View Incident] [View Explanation]
```

---

## Step-by-Step Setup for a Real Slack App

### 1. Create a Slack App
1. Go to [Slack API: Your Apps](https://api.slack.com/apps).
2. Click **Create New App** > **From scratch**.
3. Name your app (e.g. `Alert Fatigue Buster`) and select your target workspace.
4. Click **Create App**.

### 2. Enable Bot Functionality & Bot Scopes
1. In the left navigation menu, go to **OAuth & Permissions**.
2. Scroll down to **Scopes** > **Bot Token Scopes**.
3. Add the following scopes:
   - `chat:write` — Allows the bot to post incident alerts into public/private channels.
   - `chat:write.public` — Allows posting to public channels without being explicitly invited (optional).
   - `incoming-webhook` — (Optional) For incoming webhook access.

### 3. Install App to Workspace & Obtain Bot Token
1. On the **OAuth & Permissions** page, scroll to the top.
2. Click **Install to Workspace** and authorize the application.
3. Under **OAuth Tokens for Your Workspace**, copy the **Bot User OAuth Token** (starts with `xoxb-...`).
   > ⚠️ **Security Warning**: Never commit this token to Git or share it publicly.

### 4. Obtain Signing Secret
1. In the left menu, go to **Basic Information**.
2. Scroll down to **App Credentials**.
3. Click **Show** next to **Signing Secret** and copy the secret string.

### 5. Invite Bot to Target Channel
1. Open your Slack client and navigate to the channel where you want critical alerts delivered (e.g., `#sre-incidents` or `#alerts`).
2. Type `/invite @Alert Fatigue Buster` (or your chosen bot name) and press Enter.
3. Right-click the channel name in Slack > **View channel details** > copy the **Channel ID** (e.g., `C0123456789`) at the bottom of the dialog.

### 6. Configure Interactive Actions Endpoint (Optional for Slack Buttons)
If you want the `Acknowledge` and `Resolve` buttons in Slack to update backend incident status in real-time:
1. In the left menu of your Slack App settings, go to **Interactivity & Shortcuts**.
2. Toggle **Interactivity** to **On**.
3. In the **Request URL** input, enter your backend's public HTTPS URL (e.g. using ngrok or production domain):
   ```text
   https://your-domain.com/api/v1/integrations/slack/interactions
   ```
4. Click **Save Changes**.

---

## Environment Configuration

Update your `backend/.env` file with your credentials:

```env
# ==============================================================================
# Phase 8: Slack Integration Settings
# ==============================================================================
SLACK_ENABLED=true
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_SIGNING_SECRET=your-signing-secret-here
SLACK_CHANNEL_ID=C0123456789

# Dashboard Base URL (used in Block Kit action buttons)
DASHBOARD_BASE_URL=http://localhost:3000
```

> 💡 **Note**: When `SLACK_ENABLED=false`, the platform operates in local/offline mode. Alert ingestion, correlation, and decision making succeed without attempting Slack API calls.

---

## Verifying the Integration

### 1. Start or Restart the Backend
```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. Verify Slack Health Endpoint
Run:
```bash
curl http://localhost:8000/api/v1/integrations/slack/health
```

Expected output:
```json
{
  "enabled": true,
  "configured": true,
  "connected": true,
  "channel": "#alerts",
  "bot_user": "alert-fatigue-buster"
}
```

### 3. Trigger a Real Critical Incident
You can trigger a real critical incident via the Alert Simulator on the dashboard (select **500 Major** preset) or via the API:
```bash
curl -X POST http://localhost:8000/api/v1/alerts/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "database_storm",
    "alert_count": 500,
    "service": "payment-api",
    "severity": "critical"
  }'
```

### 4. Verify Slack Notification
1. Check your target Slack channel. Exactly **one** Block Kit message will arrive:
   - 🚨 Header: `🚨 CRITICAL INCIDENT DETECTED`
   - Fields: Incident ID, Service, Severity, Risk Score (`96/100 - CRITICAL`), Level 1 Escalation
   - Correlation Summary: Total alerts ingested vs unique fingerprints deduplicated
   - Explainability Reason & Codes (e.g. `HIGH_VOLUME_BURST`, `MULTI_HOST_ANOMALY`)
   - Recommended SRE Action
   - Interactive Buttons: `Acknowledge`, `Resolve`, `View Incident`, `View Explanation`
2. Idempotency Check: Even though 500 raw alerts were processed, exactly **1** Slack notification was sent.

---

## Observability & Prometheus Metrics

The Slackbot integration automatically exposes Prometheus metrics at `/metrics`:
- `slack_notifications_total{status="sent|delivered|failed|retrying|duplicate|skipped"}`
- `slack_notifications_delivered_total`
- `slack_notifications_failed_total{error_type="..."}`
- `slack_notifications_retry_total`
- `slack_notification_delivery_latency` (Histogram buckets)
- `slack_notification_pending` (Gauge of current pending/retrying records)

---

# Phase 7 — Slack Failure Fallback & Notification Resilience

## 1. Resilience Architecture

> 💡 **Core Principle**: Slack is strictly a notification and operator collaboration tool. The core alert intelligence pipeline (raw ingestion, deduplication, correlation, incident creation, risk scoring, Decision Engine evaluation, and email escalation) **NEVER** depends on Slack availability.

```text
Alert Ingestion
      ↓
Deduplication & Correlation
      ↓
Incident Created
      ↓
Risk Scoring & Decision Engine
      ↓
┌────────────────────────────────────────────────────────┐
│ Core Incident & Decision COMMITTED to PostgreSQL       │
│ (100% durable independent transaction boundary)        │
└────────────────────────────────────────────────────────┘
                           ↓
                   Notification Layer
             ┌─────────────┴─────────────┐
             ↓                           ↓
      Email Escalation          Slackbot Notification
   (Delivered / Failed)                  ↓
                                 Slack Available?
                                    ↙        ↘
                                  YES         NO
                                   ↓           ↓
                               Delivered   Persistent NotificationRecord
                                              (status: RETRYING)
                                               + next_retry_at
                                               + last_error
                                                   ↓
                                           Recovery Worker
                                        (Exponential Backoff)
```

If Slack is completely down:
- `Incident Status`: **CREATED & DURABLE** (in database)
- `Email Escalation`: **DELIVERED** (isolated independent channel)
- `Slack Notification`: **RETRYING** (or **FAILED** if permanent)
- `GET /health`: **HTTP 200 OK** (`application: healthy`, `slack: degraded`)

---

## 2. Notification Delivery Lifecycle & Schema

Notification delivery states are tracked in PostgreSQL (`notification_records` table):

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `incident_id` | UUID | Associated Core Incident |
| `channel` | VARCHAR | `slack` or `email` |
| `status` | VARCHAR | `PENDING`, `SENDING`, `SENT` (delivered), `RETRYING`, `FAILED` |
| `attempt_count` | INTEGER | Number of delivery attempts |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `last_attempt_at` | TIMESTAMPTZ | Most recent dispatch attempt timestamp |
| `next_retry_at` | TIMESTAMPTZ | Scheduled next retry timestamp (indexed) |
| `delivered_at` | TIMESTAMPTZ | Timestamp when message was confirmed by Slack API |
| `slack_message_ts` | VARCHAR | Slack message timestamp (`ts`) for duplicate protection |
| `is_transient` | BOOLEAN | True for transient network/rate-limit errors |
| `last_error` | VARCHAR | Redacted diagnostic error message |

---

## 3. Transient vs Permanent Error Classification

| Category | Examples | System Action | Next Status |
|---|---|---|---|
| **Transient** | Socket timeout, Connection reset, DNS error, HTTP 500/502/503/504, Slack API `ratelimited` (HTTP 429), `service_unavailable`, `internal_error` | Schedule exponential backoff; respect Slack `Retry-After` header | `RETRYING` |
| **Permanent** | Invalid bot token (`invalid_auth`), channel not found (`channel_not_found`), bot not in channel (`not_in_channel`), missing permissions (`missing_scope`), bad payload (`invalid_blocks`), HTTP 400/401/403/404 | Abort retries immediately; log safely | `FAILED` |

---

## 4. Exponential Backoff & Retry Strategy

Configurable via environment variables:
```env
SLACK_MAX_RETRIES=5
SLACK_RETRY_BASE_SECONDS=5
SLACK_NOTIFICATION_TIMEOUT_SECONDS=10
```

Backoff schedule (base = 5s):
- **Attempt 1**: 5s delay
- **Attempt 2**: 15s delay
- **Attempt 3**: 45s delay
- **Attempt 4**: 120s delay
- **Attempt 5+**: Capped at 300s (5 minutes)
- **HTTP 429**: Directly respects Slack's `Retry-After` response header

---

## 5. Recovery Worker & Endpoints

When Slack recovers, queued notifications can be processed via API or background job:

### Trigger Retry Worker
```bash
curl -X POST http://localhost:8000/api/v1/integrations/slack/retry?limit=50
```
Response:
```json
{
  "status": "ok",
  "result": {
    "processed": 1,
    "delivered": 1,
    "failed": 0,
    "retrying": 0,
    "skipped_duplicate": 0,
    "remaining_pending": 0
  }
}
```

### Inspect Pending/Retrying Notifications
```bash
curl http://localhost:8000/api/v1/integrations/slack/pending
```

---

## 6. Health Check Behavior

The root `/health` endpoint distinguishes application health from external dependency health:

```bash
curl http://localhost:8000/health
```

Healthy Slack:
```json
{
  "status": "healthy",
  "database": "healthy",
  "slack": "healthy"
}
```

Slack Degraded / Down:
```json
{
  "status": "healthy",
  "database": "healthy",
  "slack": "degraded"
}
```

> ⚠️ **Key Guarantee**: The HTTP response code remains `200 OK` and core application status is `healthy` even if Slack is completely unreachable.

---

## 7. How to Simulate Slack Failure Locally

Run the automated 3-scenario end-to-end demonstration:
```bash
python scripts/demo_slack_resilience_scenarios.py
```

This verifies:
1. **Scenario A (Slack Healthy)**: 500 alerts -> 1 Incident -> CRITICAL -> Email delivered + Slack delivered.
2. **Scenario B (Slack Down)**: 500 alerts with Slack unreachable -> Incident 100% PRESERVED, Email delivered, Slack queued in RETRYING state.
3. **Scenario C (Slack Recovered)**: Slack restored -> Retry worker executes -> Slack notification DELIVERED with Slack message `ts` recorded.
