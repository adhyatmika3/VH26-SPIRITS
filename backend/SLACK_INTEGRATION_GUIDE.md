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
- `slack_notifications_total{status="sent|failed|skipped"}`
- `slack_notifications_success_total`
- `slack_notifications_failed_total`
- `slack_notification_latency_seconds`
