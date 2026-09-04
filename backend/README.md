# Alert Fatigue Buster - Backend API

The backend API for Alert Fatigue Buster provides real-time alert ingestion, deduplication engine, sliding temporal window grouping, and incident management.

## Options to Run

You can run either the **Node.js** backend (zero dependencies needed) or the **Python (FastAPI)** backend:

### Option 1: Node.js Backend (Recommended & Instant)
```bash
# Inside the backend/ directory:
npm start
# or
node server.js
```
The server will start on `http://localhost:8000`.

---

### Option 2: Python (FastAPI) Backend
```bash
# Inside the backend/ directory:
pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8000
```

---

## API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Healthcheck & engine status |
| `GET` | `/api/stats` | Operations KPIs (Ingress rate, Noise reduction %, MTTR) |
| `GET` | `/api/alerts` | Get list of live alerts |
| `POST` | `/api/alerts` | Ingest raw alert with automatic deduplication |
| `POST` | `/api/alerts/:id/acknowledge` | Acknowledge alert |
| `POST` | `/api/alerts/:id/suppress` | Suppress alert fingerprint |
| `GET` | `/api/incidents` | List active & past incidents |
| `POST` | `/api/incidents` | Declare new SRE incident |
