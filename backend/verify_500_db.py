import psycopg2
import json

conn = psycopg2.connect('postgresql://postgres:postgres@localhost:5432/alert_buster')
cur = conn.cursor()

print('=== 1. RAW ALERTS COUNT ===')
cur.execute('SELECT count(*) FROM raw_alerts;')
raw_count = cur.fetchone()[0]
print(f'RawAlert count: {raw_count} (Expected: 500)')

print('\n=== 2. CORE INCIDENTS ===')
cur.execute('SELECT id, incident_number, title, service, status, priority, alert_count, unique_alerts_count, escalation_level FROM incidents;')
incidents = cur.fetchall()
print(f'Core Incident count: {len(incidents)} (Expected: 1)')
for inc in incidents:
    print('Incident details:', inc)

print('\n=== 3. CANONICAL ALERTS ===')
cur.execute('SELECT id, fingerprint, alert_name, service, severity, occurrence_count, is_duplicate, priority FROM canonical_alerts;')
canonicals = cur.fetchall()
print(f'Canonical Alerts count: {len(canonicals)} (Expected: 1)')
for c in canonicals:
    print('Canonical alert:', c)

print('\n=== 4. DECISIONS BREAKDOWN ===')
cur.execute('SELECT decision, count(*) FROM decision_records GROUP BY decision;')
for row in cur.fetchall():
    print(f'Decision [{row[0]}]: {row[1]}')

print('\n=== 5. ESCALATION DECISION RECORD ===')
cur.execute("SELECT id, decision, reason_codes, reason, context_snapshot FROM decision_records WHERE decision = 'ESCALATE' LIMIT 1;")
esc_dec = cur.fetchone()
if esc_dec:
    print(f'Decision ID: {esc_dec[0]}')
    print(f'Decision: {esc_dec[1]}')
    print(f'Reason Codes: {esc_dec[2]}')
    print(f'Reason: {esc_dec[3]}')
    print(f'Risk Score in context_snapshot: {esc_dec[4].get("risk_score")}')
    print(f'Risk Level in context_snapshot: {esc_dec[4].get("risk_level")}')
    print(f'Risk Breakdown in context_snapshot: {json.dumps(esc_dec[4].get("risk_breakdown"))}')

print('\n=== 6. NOTIFICATION RECORDS ===')
cur.execute('SELECT id, channel, destination, notification_type, status, error_message, sent_at FROM notification_records;')
notifs = cur.fetchall()
print(f'Notification records count: {len(notifs)}')
for n in notifs:
    print(f'Notification [{n[0]}]: channel={n[1]}, dest={n[2]}, type={n[3]}, status={n[4]}, err={n[5]}, sent_at={n[6]}')

print('\n=== 7. ESCALATION RECORDS ===')
cur.execute('SELECT id, escalation_level, reason_codes, reason, created_at FROM escalation_records;')
for e in cur.fetchall():
    print(f'Escalation [{e[0]}]: level={e[1]}, reasons={e[2]}, reason={e[3]}, at={e[4]}')
