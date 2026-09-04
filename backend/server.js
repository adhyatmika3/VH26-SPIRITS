/**
 * Alert Fatigue Buster - Node.js Express Backend API
 */

const http = require('http');
const url = require('url');

const PORT = process.env.PORT || 8000;

// State Store
const statsStore = {
  incomingAlerts: 2481,
  actionableAlerts: 37,
  noiseReductionPercent: 98.5,
  activeIncidentsCount: 2,
  criticalAlertsCount: 2,
  mttrSeconds: 252,
  ingressVelocity: 142.8,
  fatigueAbsorptionPercent: 91.4,
  droppedAlerts: 2267,
  decisionLatencyMs: 11.8,
  activeDedupePool: 63
};

const alertsDb = [
  {
    id: "ALT-9042",
    fingerprint: "e4f8a91c",
    timestamp: "10:34:12",
    service: "payment-gateway",
    cluster: "us-east-prod-k8s",
    severity: "CRITICAL",
    title: "PostgresConnectionPoolExhausted",
    message: "Connection pool utilization > 98% for 45s across 8 poolers.",
    status: "TRIGGERED",
    group: "GRP-DB-POOL-01",
    occurrences: 142,
    suppressed: false,
    actionable: true
  },
  {
    id: "ALT-9041",
    fingerprint: "b21a78ff",
    timestamp: "10:34:05",
    service: "checkout-api",
    cluster: "us-east-prod-k8s",
    severity: "HIGH",
    title: "HTTP5xxRateSpike",
    message: "HTTP 502 Bad Gateway response rate exceeded 4.5% threshold.",
    status: "TRIGGERED",
    group: "GRP-DB-POOL-01",
    occurrences: 89,
    suppressed: false,
    actionable: true
  }
];

const incidentsDb = [
  {
    id: "INC-1042",
    title: "Database Connection Cascade on postgres-primary",
    severity: "CRITICAL",
    status: "INVESTIGATING",
    startTime: "14:32:08 UTC",
    duration: "18m ago",
    owner: "Alex Rivera (Lead SRE)",
    leadService: "payment-gateway",
    description: "Cascading connection pool failure on postgres-primary impacting downstream checkout.",
    alertsCount: 429,
    actionableCount: 1
  }
];

const server = http.createServer((req, res) => {
  // CORS Headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  const parsedUrl = url.parse(req.url, true);
  const pathname = parsedUrl.pathname;

  // JSON helper
  const sendJson = (statusCode, data) => {
    res.writeHead(statusCode, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(data));
  };

  if (req.method === 'GET' && pathname === '/api/health') {
    return sendJson(200, { status: 'ok', engine: 'Buster Node Engine v1.0', timestamp: Date.now() });
  }

  if (req.method === 'GET' && pathname === '/api/stats') {
    return sendJson(200, statsStore);
  }

  if (req.method === 'GET' && pathname === '/api/alerts') {
    return sendJson(200, alertsDb);
  }

  if (req.method === 'GET' && pathname === '/api/incidents') {
    return sendJson(200, incidentsDb);
  }

  // Handle POST body
  if (req.method === 'POST') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      let data = {};
      try {
        if (body) data = JSON.parse(body);
      } catch (e) {}

      if (pathname === '/api/alerts') {
        statsStore.incomingAlerts += 1;
        const fp = data.fingerprint || `fp-${Math.random().toString(16).substring(2, 8)}`;
        const existing = alertsDb.find(a => a.fingerprint === fp);
        if (existing) {
          existing.occurrences += 1;
          statsStore.droppedAlerts += 1;
          return sendJson(200, { action: 'deduplicated', alertId: existing.id, occurrences: existing.occurrences });
        }

        const newAlert = {
          id: `ALT-${Math.floor(1000 + Math.random() * 9000)}`,
          fingerprint: fp,
          timestamp: new Date().toLocaleTimeString(),
          service: data.service || 'unknown-service',
          cluster: data.cluster || 'us-east-prod-k8s',
          severity: data.severity || 'HIGH',
          title: data.title || 'Service Metric Anomaly',
          message: data.message || 'Automated telemetry ingestion event.',
          status: 'TRIGGERED',
          group: 'GRP-DYNAMIC',
          occurrences: 1,
          suppressed: false,
          actionable: ['CRITICAL', 'HIGH'].includes(data.severity)
        };
        alertsDb.unshift(newAlert);
        if (newAlert.actionable) statsStore.actionableAlerts += 1;
        return sendJson(201, { action: 'created', alert: newAlert });
      }

      if (pathname === '/api/incidents') {
        const newInc = {
          id: `INC-${Math.floor(1000 + Math.random() * 9000)}`,
          title: data.title || 'Incident',
          severity: data.severity || 'HIGH',
          status: 'INVESTIGATING',
          startTime: 'Just now',
          duration: '0m ago',
          owner: 'Alex Rivera (Lead SRE)',
          leadService: data.leadService || 'gateway',
          description: data.description || '',
          alertsCount: 1,
          actionableCount: 1
        };
        incidentsDb.unshift(newInc);
        statsStore.activeIncidentsCount += 1;
        return sendJson(201, newInc);
      }

      return sendJson(404, { error: 'Route not found' });
    });
    return;
  }

  return sendJson(404, { error: 'Not Found' });
});

server.listen(PORT, () => {
  console.log(`Alert Fatigue Buster API Server listening on http://localhost:${PORT}`);
});
