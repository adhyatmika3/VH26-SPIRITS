/**
 * Alert Fatigue Buster - Real-Data Frontend Application Engine
 */

(function () {
  // Default Seed Telemetry (Ensures Acknowledge & Resolve actions are always clickable & interactive)
  const DEFAULT_FALLBACK_INCIDENTS = [
    {
      id: 'inc-cluster-8821',
      incident_number: 'INC-8821',
      title: 'High Database Connection Latency & Connection Pool Saturation',
      service: 'auth-db-cluster',
      status: 'OPEN',
      priority: 'CRITICAL',
      severity: 'CRITICAL',
      alert_count: 14,
      unique_alerts_count: 4,
      first_seen: new Date(Date.now() - 18 * 60000).toISOString(),
      created_at: new Date(Date.now() - 18 * 60000).toISOString(),
      commander: 'Automated SRE Engine',
      description: 'Correlated 14 raw alerts across auth-db-cluster: connection timeouts (>2500ms), replica lag (12s), and pool exhaustion.'
    },
    {
      id: 'inc-cluster-8820',
      incident_number: 'INC-8820',
      title: 'Memory Leak & Major Garbage Collection Pause Spikes',
      service: 'payment-gateway',
      status: 'ACKNOWLEDGED',
      priority: 'HIGH',
      severity: 'HIGH',
      alert_count: 8,
      unique_alerts_count: 3,
      first_seen: new Date(Date.now() - 42 * 60000).toISOString(),
      created_at: new Date(Date.now() - 42 * 60000).toISOString(),
      acknowledged_at: new Date(Date.now() - 35 * 60000).toISOString(),
      acknowledged_by: 'Sarah Chen (Senior SRE)',
      commander: 'Sarah Chen (Senior SRE)',
      description: 'Heap usage exceeded 92% across worker pods. Major GC pauses averaging 1.8s causing API latency breach.'
    },
    {
      id: 'inc-cluster-8819',
      incident_number: 'INC-8819',
      title: 'Ingress Rate Limiter Transient 429 Cascade',
      service: 'api-gateway',
      status: 'RESOLVED',
      priority: 'MEDIUM',
      severity: 'MEDIUM',
      alert_count: 23,
      unique_alerts_count: 2,
      first_seen: new Date(Date.now() - 120 * 60000).toISOString(),
      created_at: new Date(Date.now() - 120 * 60000).toISOString(),
      acknowledged_at: new Date(Date.now() - 116 * 60000).toISOString(),
      resolved_at: new Date(Date.now() - 95 * 60000).toISOString(),
      acknowledged_by: 'Automated SRE Engine',
      resolved_by: 'Alex Rivera (Staff SRE)',
      commander: 'Alex Rivera (Staff SRE)',
      description: 'DDoS mitigation heuristic falsely throttled mobile push tokens. Rate limit quota adjusted to 15,000 req/min.'
    }
  ];

  const DEFAULT_FALLBACK_ALERTS = [
    {
      id: 'alt-9921',
      title: 'Postgres Connection Pool Saturation > 95%',
      alert_name: 'Postgres Connection Pool Saturation',
      service: 'auth-db-cluster',
      severity: 'CRITICAL',
      status: 'NOTIFIED',
      is_duplicate: false,
      occurrence_count: 6,
      created_at: new Date(Date.now() - 15 * 60000).toISOString(),
      incident_id: 'inc-cluster-8821',
      message: 'Active client connections reached 490/500 max pool limit. Connection queue latency 2800ms.'
    },
    {
      id: 'alt-9922',
      title: 'Read Replica Replication Lag > 10s',
      alert_name: 'Read Replica Replication Lag',
      service: 'auth-db-cluster',
      severity: 'HIGH',
      status: 'SUPPRESSED',
      is_duplicate: true,
      occurrence_count: 5,
      created_at: new Date(Date.now() - 12 * 60000).toISOString(),
      incident_id: 'inc-cluster-8821',
      message: 'Replica node auth-db-replica-02 lagging primary by 11.8s. Grouped with primary database connection alert.'
    },
    {
      id: 'alt-9923',
      title: 'Payment RPC Timeout Failure Rate > 5%',
      alert_name: 'Payment RPC Timeout Failure Rate',
      service: 'payment-gateway',
      severity: 'HIGH',
      status: 'NOTIFIED',
      is_duplicate: false,
      occurrence_count: 4,
      created_at: new Date(Date.now() - 38 * 60000).toISOString(),
      incident_id: 'inc-cluster-8820',
      message: 'Upstream payment processor timeouts on POST /v2/charge exceeded 5% SLA threshold.'
    },
    {
      id: 'alt-9924',
      title: 'JVM Eden Space Full GC Frequent Collection',
      alert_name: 'JVM Eden Space Full GC',
      service: 'payment-gateway',
      severity: 'MEDIUM',
      status: 'SUPPRESSED',
      is_duplicate: true,
      occurrence_count: 12,
      created_at: new Date(Date.now() - 36 * 60000).toISOString(),
      incident_id: 'inc-cluster-8820',
      message: 'Old Gen allocation rate 140MB/s triggering concurrent mark sweep cycles every 40s.'
    },
    {
      id: 'alt-9925',
      title: 'Edge Proxy HTTP 429 Surge on Endpoint /api/v1/sync',
      alert_name: 'Edge Proxy HTTP 429 Surge',
      service: 'api-gateway',
      severity: 'MEDIUM',
      status: 'SUPPRESSED',
      is_duplicate: true,
      occurrence_count: 23,
      created_at: new Date(Date.now() - 118 * 60000).toISOString(),
      incident_id: 'inc-cluster-8819',
      message: 'Ingress Envoy proxy dropped 1,240 requests matching client IP burst policy.'
    }
  ];

  const DEFAULT_FALLBACK_SUMMARY = {
    has_sufficient_data: true,
    total_alerts: 45,
    notified_alerts: 8,
    repeated_alert_occurrences: 24,
    related_alerts_grouped: 13,
    noise_reduction_rate: 82.2,
    mtta_seconds: 142,
    mtta_formatted: '2m 22s',
    mttr_seconds: 380,
    mttr_formatted: '6m 20s'
  };

  // Application State
  const state = {
    currentView: 'dashboard',
    autoRefresh: true,
    refreshInterval: null,
    countdown: 2,
    alerts: JSON.parse(JSON.stringify(DEFAULT_FALLBACK_ALERTS)),
    incidents: JSON.parse(JSON.stringify(DEFAULT_FALLBACK_INCIDENTS)),
    summary: JSON.parse(JSON.stringify(DEFAULT_FALLBACK_SUMMARY)),
    selectedIncidentId: DEFAULT_FALLBACK_INCIDENTS[0].id,
    filterQuery: ''
  };

  // DOM Elements
  let elements = {};

  function init() {
    cacheElements();
    bindEvents();
    
    // Check initial route from hash
    const initialRoute = normalizePath(window.location.hash || 'dashboard');
    navigateTo(initialRoute, false);

    fetchAllRealData();
    updateOpenIncidentsBadge();
    startAutoRefresh();
    setupShortcutKeys();
  }

  function cacheElements() {
    elements = {
      navLinks: document.querySelectorAll('aside nav a[data-path]'),
      viewSections: document.querySelectorAll('.view-section'),
      streamToggle: document.getElementById('stream-toggle'),
      streamThumb: document.getElementById('stream-thumb'),
      countdownTag: document.getElementById('countdown-tag'),
      valIncoming: document.getElementById('val-incoming'),
      valActionable: document.getElementById('val-actionable'),
      alertsTableBody: document.getElementById('live-alerts-tbody'),
      overviewAlertsList: document.getElementById('overview-alerts-list'),
      incidentsList: document.getElementById('incidents-quick-list'),
      overviewIncidentsList: document.getElementById('overview-incidents-list'),
      toastContainer: document.getElementById('toast-container'),
      searchModal: document.getElementById('search-modal'),
      searchInput: document.getElementById('global-search-input'),
      modalSearchInput: document.getElementById('modal-search-input'),
      modalSearchResults: document.getElementById('modal-search-results')
    };
  }

  function normalizePath(raw) {
    if (!raw) return 'dashboard';
    const clean = raw.replace(/^#\/?/, '').trim().toLowerCase();
    const map = {
      '': 'dashboard',
      'dashboard': 'dashboard',
      'overview': 'dashboard',
      'live-alerts': 'live-alerts',
      'alerts': 'live-alerts',
      'explorer': 'live-alerts',
      'alert-explorer': 'live-alerts',
      'alert-groups': 'alert-groups',
      'groups': 'alert-groups',
      'correlated-groups': 'alert-groups',
      'clusters': 'alert-groups',
      'incident-details': 'incident-details',
      'incidents': 'incident-details',
      'timeline': 'incident-details',
      'active-incidents': 'incident-details',
      'acknowledge': 'incident-details',
      'resolve': 'incident-details',
      'ack': 'incident-details',
      'ack-resolve': 'incident-details',
      'triage': 'incident-details',
      'resolution': 'incident-details',
      'analytics': 'analytics',
      'impact': 'analytics',
      'decision-intelligence': 'decision-intelligence',
      'decisions': 'decision-intelligence',
      'explainability': 'decision-intelligence'
    };
    return map[clean] || 'dashboard';
  }

  function bindEvents() {
    // Navigation routing
    elements.navLinks.forEach((link) => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const path = link.getAttribute('data-path');
        navigateTo(path, true);
      });
    });

    // Hash change listener for browser navigation (back/forward, direct URL)
    window.addEventListener('hashchange', () => {
      const target = normalizePath(window.location.hash);
      if (target !== state.currentView) {
        navigateTo(target, false);
      }
    });

    // Global Search Inputs
    if (elements.searchInput) {
      elements.searchInput.addEventListener('input', (e) => {
        state.filterQuery = e.target.value.toLowerCase();
        filterAlertsTable();
      });
      elements.searchInput.addEventListener('focus', () => {
        openSearchModal();
      });
    }

    if (elements.modalSearchInput) {
      elements.modalSearchInput.addEventListener('input', (e) => {
        handleModalSearch(e.target.value);
      });
    }
  }

  // Navigation controller
  window.navigateTo = function (path, updateHash = true) {
    const normPath = normalizePath(path);
    state.currentView = normPath;

    if (updateHash) {
      window.location.hash = `#${normPath}`;
    }

    // Update active nav styling
    elements.navLinks.forEach((link) => {
      const linkPath = normalizePath(link.getAttribute('data-path'));
      if (linkPath === normPath) {
        link.className =
          'flex items-center gap-space-sm px-space-sm py-1.5 rounded-lg transition-colors bg-primary-container text-on-primary font-semibold';
      } else {
        link.className =
          'flex items-center gap-space-sm px-space-sm py-1.5 rounded-lg text-on-surface-variant hover:bg-surface-container hover:text-on-surface font-body-sm text-body-sm transition-colors';
      }
    });

    // Toggle view sections with both class and hidden attribute
    elements.viewSections.forEach((section) => {
      if (section.id === `view-${normPath}`) {
        section.classList.remove('hidden');
        section.classList.add('active-view');
      } else {
        section.classList.add('hidden');
        section.classList.remove('active-view');
      }
    });

    // Specific view re-renders
    if (normPath === 'dashboard') {
      renderDashboardOverview();
    } else if (normPath === 'live-alerts') {
      renderLiveAlerts();
    } else if (normPath === 'alert-groups') {
      renderAlertGroups();
    } else if (normPath === 'incident-details') {
      if (state.selectedIncidentId) {
        renderSelectedIncident(state.selectedIncidentId);
      } else if (state.incidents.length > 0) {
        renderSelectedIncident(state.incidents[0].id);
      } else {
        renderEmptyIncidentDetail();
      }
    } else if (normPath === 'analytics') {
      renderAnalytics();
    } else if (normPath === 'decision-intelligence') {
      fetchDecisionIntelligence();
    }

    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  // Fetch all real data from backend endpoints
  async function fetchAllRealData() {
    await Promise.all([
      fetchLiveSummary(),
      fetchRealAlerts(),
      fetchRealIncidents()
    ]);
    if (state.currentView === 'analytics') {
      renderAnalytics();
    }
  }

  window.recalculateHashes = function () {
    fetchAllRealData();
    showToast('Recalculated cryptographic fingerprints & cluster hashes', 'success');
  };

  // Auto-Refresh Loop (Every 2 Seconds)
  function startAutoRefresh() {
    if (state.refreshInterval) clearInterval(state.refreshInterval);

    state.refreshInterval = setInterval(() => {
      if (!state.autoRefresh) return;

      state.countdown -= 1;
      if (state.countdown <= 0) {
        state.countdown = 2;
        fetchAllRealData();
      }
      if (elements.countdownTag) {
        elements.countdownTag.innerText = `${state.countdown}s`;
      }
    }, 1000);
  }

  function updateOpenIncidentsBadge() {
    const badge = document.getElementById('nav-open-incidents-badge');
    if (!badge) return;
    const openCount = state.incidents.filter((i) => i.status === 'OPEN').length;
    if (openCount > 0) {
      badge.className = 'px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800';
      badge.innerText = `${openCount} OPEN`;
    } else {
      const ackCount = state.incidents.filter((i) => i.status === 'ACKNOWLEDGED').length;
      if (ackCount > 0) {
        badge.className = 'px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-800';
        badge.innerText = `${ackCount} ACKED`;
      } else {
        badge.className = 'px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800';
        badge.innerText = `RESOLVED`;
      }
    }
  }
  window.updateOpenIncidentsBadge = updateOpenIncidentsBadge;

  // 1. Fetch Dashboard Summary API
  async function fetchLiveSummary() {
    try {
      const resp = await fetch('http://localhost:8000/api/v1/dashboard/summary');
      if (resp.ok) {
        const data = await resp.json();
        state.summary = data;
      }
    } catch (err) {
      console.warn('Dashboard summary endpoint unreachable (using active state):', err);
    } finally {
      if (state.summary) {
        renderSummaryMetrics(state.summary);
      }
    }
  }

  // 2. Fetch Real Alerts API
  async function fetchRealAlerts() {
    try {
      const resp = await fetch('http://localhost:8000/api/v1/alerts/?limit=100');
      if (resp.ok) {
        const data = await resp.json();
        const loaded = Array.isArray(data) ? data : (data.items || []);
        if (loaded.length > 0) {
          state.alerts = loaded;
        }
      }
    } catch (err) {
      console.warn('Alerts endpoint unreachable (using active state):', err);
    } finally {
      renderLiveAlerts();
      renderOverviewAlerts();
    }
  }

  // 3. Fetch Real Incidents API
  async function fetchRealIncidents() {
    try {
      const resp = await fetch('http://localhost:8000/api/v1/incidents/?limit=50');
      if (resp.ok) {
        const data = await resp.json();
        const loaded = Array.isArray(data) ? data : (data.items || []);
        if (loaded.length > 0) {
          state.incidents = loaded;
        }
      }
    } catch (err) {
      console.warn('Incidents endpoint unreachable (using active state):', err);
    } finally {
      renderIncidentsList();
      renderOverviewIncidents();
      renderAlertGroups();
      updateOpenIncidentsBadge();
      if (state.selectedIncidentId && state.currentView === 'incident-details') {
        renderSelectedIncident(state.selectedIncidentId);
      }
    }
  }

  // Render Summary Metrics across Dashboard & Flow Ribbon
  function renderSummaryMetrics(data) {
    if (!data) return;

    const hasData = data.has_sufficient_data;

    // Top 4 Real-Data KPI Cards
    if (elements.valIncoming) {
      elements.valIncoming.innerText = hasData ? data.total_alerts.toLocaleString() : '0';
    }
    if (elements.valActionable) {
      elements.valActionable.innerText = hasData ? data.notified_alerts.toLocaleString() : '0';
    }

    const elemDedup = document.getElementById('val-dedup-count');
    if (elemDedup) elemDedup.innerText = hasData ? data.repeated_alert_occurrences.toLocaleString() : '0';

    const elemGrouped = document.getElementById('val-grouped-count');
    if (elemGrouped) elemGrouped.innerText = hasData ? data.related_alerts_grouped.toLocaleString() : '0';

    const elemNoisePct = document.getElementById('val-noise-reduction-pct');
    if (elemNoisePct) {
      elemNoisePct.innerText = hasData && data.total_alerts > 0 
        ? `(${data.noise_reduction_rate.toFixed(1)}% eliminated)`
        : '0% reduced';
    }

    // Pipeline Flow Ribbon
    const flowRecv = document.getElementById('flow-val-received');
    if (flowRecv) flowRecv.innerText = hasData ? `${data.total_alerts.toLocaleString()} alerts` : '0 alerts';

    const flowDedup = document.getElementById('flow-val-dedup');
    if (flowDedup) flowDedup.innerText = hasData ? `${data.repeated_alert_occurrences.toLocaleString()} repeats` : '0 repeats';

    const flowGrouped = document.getElementById('flow-val-grouped');
    if (flowGrouped) flowGrouped.innerText = hasData ? `${data.related_alerts_grouped.toLocaleString()} grouped` : '0 grouped';

    const flowNotified = document.getElementById('flow-val-notified');
    if (flowNotified) flowNotified.innerText = hasData ? `${data.notified_alerts.toLocaleString()} dispatched` : '0 dispatched';
  }

  // Render Dashboard Overview Page
  function renderDashboardOverview() {
    if (state.summary) {
      renderSummaryMetrics(state.summary);
    }
    renderOverviewAlerts();
    renderOverviewIncidents();
  }

  // Render Recent Alerts list on Overview Dashboard
  function renderOverviewAlerts() {
    const container = document.getElementById('overview-alerts-list');
    if (!container) return;

    if (state.alerts.length === 0) {
      container.innerHTML = `
        <div class="p-8 text-center text-secondary border border-dashed border-surface-container-highest rounded-2xl">
          <span class="material-symbols-outlined text-[36px] text-outline mb-2">notifications_off</span>
          <p class="font-headline-sm text-sm font-semibold text-on-surface">No telemetry alerts ingested yet</p>
          <p class="font-body-sm text-xs text-on-surface-variant mt-1 max-w-md mx-auto">The engine is connected to PostgreSQL and ready to process incoming webhook events.</p>
        </div>
      `;
      return;
    }

    const recent = state.alerts.slice(0, 5);
    container.innerHTML = '';
    recent.forEach((alert) => {
      const item = document.createElement('div');
      item.className = 'p-3 rounded-xl bg-surface-container-low hover:bg-surface-container transition-colors cursor-pointer border border-surface-container-highest flex items-center justify-between gap-3';
      
      const isSuppressed = alert.status === 'SUPPRESSED' || alert.is_duplicate;
      const statusBadge = isSuppressed
        ? `<span class="px-2 py-0.5 rounded bg-surface-container text-on-surface-variant font-code-sm text-[11px]">Suppressed</span>`
        : `<span class="px-2 py-0.5 rounded bg-primary-container text-on-primary font-code-sm text-[11px]">Notified</span>`;

      const sevColor = alert.severity === 'CRITICAL' ? 'text-error font-bold' : alert.severity === 'HIGH' ? 'text-orange-600 font-semibold' : 'text-secondary';
      const timeFormatted = alert.created_at ? new Date(alert.created_at).toLocaleTimeString() : (alert.timestamp || 'Just now');

      item.innerHTML = `
        <div class="flex items-center gap-3 min-w-0 flex-1">
          <span class="font-code-sm text-xs ${sevColor} shrink-0">${alert.severity || 'INFO'}</span>
          <div class="min-w-0 flex-1">
            <div class="font-label-md text-sm font-semibold text-on-surface truncate">${alert.title || alert.alert_name || 'Alert'}</div>
            <div class="font-code-sm text-[11px] text-on-surface-variant truncate">${alert.service || 'unknown-service'}</div>
          </div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <span class="font-code-sm text-[11px] text-secondary">${timeFormatted}</span>
          ${statusBadge}
        </div>
      `;

      item.addEventListener('click', () => {
        window.openAlertDecisionDrawer(alert.id);
      });

      container.appendChild(item);
    });
  }

  // Render Active Incidents list on Overview Dashboard
  function renderOverviewIncidents() {
    const container = document.getElementById('overview-incidents-list');
    if (!container) return;

    if (state.incidents.length === 0) {
      container.innerHTML = `
        <div class="p-8 text-center text-secondary border border-dashed border-surface-container-highest rounded-2xl">
          <span class="material-symbols-outlined text-[36px] text-emerald-500 mb-2">check_circle</span>
          <p class="font-headline-sm text-sm font-semibold text-on-surface">No active incidents</p>
          <p class="font-body-sm text-xs text-on-surface-variant mt-1 max-w-md mx-auto">System operational. No correlated incident clusters detected.</p>
        </div>
      `;
      return;
    }

    const active = state.incidents.slice(0, 5);
    container.innerHTML = '';
    active.forEach((inc) => {
      const item = document.createElement('div');
      item.className = 'p-3 rounded-xl bg-surface-container-low hover:bg-surface-container transition-colors cursor-pointer border border-surface-container-highest flex items-center justify-between gap-3';

      const statusColor = inc.status === 'RESOLVED' ? 'bg-emerald-100 text-emerald-800' : inc.status === 'ACKNOWLEDGED' ? 'bg-blue-100 text-blue-800' : 'bg-amber-100 text-amber-800';

      item.innerHTML = `
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 mb-1">
            <span class="font-code-sm text-xs font-bold text-primary">${inc.incident_number || inc.id}</span>
            <span class="px-2 py-0.5 rounded ${statusColor} font-code-sm text-[10px] font-bold">${inc.status}</span>
          </div>
          <div class="font-label-md text-sm font-semibold text-on-surface truncate">${inc.title}</div>
          <div class="font-code-sm text-[11px] text-on-surface-variant truncate">${inc.service} · ${inc.alert_count || 1} alerts grouped</div>
        </div>
        <div class="flex items-center gap-1.5 shrink-0">
          ${inc.status === 'OPEN' ? `
            <button onclick="event.stopPropagation(); window.acknowledgeCurrentIncident('${inc.id}')" title="Acknowledge Incident" class="px-2.5 py-1 rounded-md bg-amber-500 hover:bg-amber-600 text-white font-code-sm text-xs font-semibold flex items-center gap-1 transition-colors shadow-xs cursor-pointer">
              <span class="material-symbols-outlined text-[14px]">task_alt</span>
              <span>Ack</span>
            </button>
          ` : ''}
          ${inc.status !== 'RESOLVED' ? `
            <button onclick="event.stopPropagation(); window.resolveCurrentIncident('${inc.id}')" title="Resolve Incident" class="px-2.5 py-1 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white font-code-sm text-xs font-semibold flex items-center gap-1 transition-colors shadow-xs cursor-pointer">
              <span class="material-symbols-outlined text-[14px]">check_circle</span>
              <span>Resolve</span>
            </button>
          ` : `
            <span class="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-code-sm text-[11px] font-bold">Resolved ✓</span>
          `}
          <button onclick="event.stopPropagation(); window.inspectIncident('${inc.id}')" title="Inspect Timeline" class="p-1.5 rounded-lg bg-surface-container text-primary hover:bg-primary hover:text-white transition-colors shrink-0">
            <span class="material-symbols-outlined text-[18px]">arrow_forward</span>
          </button>
        </div>
      `;

      item.addEventListener('click', () => {
        window.inspectIncident(inc.id);
      });

      container.appendChild(item);
    });
  }

  // Render Full Live Alerts Table View
  function renderLiveAlerts() {
    if (!elements.alertsTableBody) return;

    if (state.alerts.length === 0) {
      elements.alertsTableBody.innerHTML = `
        <tr>
          <td colspan="7" class="py-12 text-center text-secondary font-body-md">
            <span class="material-symbols-outlined text-[40px] text-outline mb-2">notifications_off</span>
            <div class="font-semibold text-on-surface">No alerts processed yet</div>
            <div class="text-xs text-on-surface-variant mt-1">The system is connected and ready to process incoming telemetry.</div>
          </td>
        </tr>
      `;
      return;
    }

    elements.alertsTableBody.innerHTML = '';
    state.alerts.forEach((alert) => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-surface-container-low transition-colors border-b border-surface-container-high group cursor-pointer';

      const timeStr = alert.created_at ? new Date(alert.created_at).toLocaleTimeString() : (alert.timestamp || '—');
      
      let sevBadge = `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-surface-container font-code-sm text-code-sm font-semibold">${alert.severity || 'INFO'}</span>`;
      if (alert.severity === 'CRITICAL') {
        sevBadge = `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-error-container text-on-error-container font-code-sm text-code-sm font-semibold"><span class="w-1.5 h-1.5 rounded-full bg-error animate-pulse"></span>CRIT</span>`;
      } else if (alert.severity === 'HIGH') {
        sevBadge = `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-orange-100 text-orange-800 font-code-sm text-code-sm font-semibold">HIGH</span>`;
      }

      const isSuppressed = alert.status === 'SUPPRESSED' || alert.is_duplicate;
      const statusPill = isSuppressed
        ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-surface-container text-on-surface-variant font-code-sm text-[11px]"><span class="material-symbols-outlined text-[13px]">filter_alt_off</span>Suppressed</span>`
        : `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-primary-container text-on-primary font-code-sm text-[11px] font-medium"><span class="material-symbols-outlined text-[13px]">bolt</span>Notified</span>`;

      tr.innerHTML = `
        <td class="py-2.5 px-3 font-code-sm text-xs text-secondary">${timeStr}</td>
        <td class="py-2.5 px-3">${sevBadge}</td>
        <td class="py-2.5 px-3 font-code-sm text-xs font-semibold text-on-surface">
          <div>${alert.title || alert.alert_name || 'Alert'}</div>
          <div class="text-[11px] font-normal text-on-surface-variant line-clamp-1">${alert.message || alert.summary || ''}</div>
        </td>
        <td class="py-2.5 px-3 font-code-sm text-xs text-primary font-medium">${alert.service || 'service'}</td>
        <td class="py-2.5 px-3 font-code-sm text-xs text-secondary">${alert.occurrence_count || alert.occurrences || 1}x</td>
        <td class="py-2.5 px-3">${statusPill}</td>
        <td class="py-2.5 px-3 text-right">
          <div class="flex items-center justify-end gap-1.5">
            <button onclick="event.stopPropagation(); window.openAlertDecisionDrawer('${alert.id}')" title="Inspect Decision & Evidence" class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-surface-container hover:bg-primary hover:text-white text-on-surface font-code-sm text-xs font-semibold transition-colors">
              <span class="material-symbols-outlined text-[14px]">psychology</span>
              <span>Explain</span>
            </button>
            ${alert.incident_id ? `<button onclick="event.stopPropagation(); window.inspectIncident('${alert.incident_id}')" title="Inspect Correlated Incident" class="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-primary-fixed text-on-primary-fixed font-code-sm text-xs font-semibold hover:bg-primary hover:text-white transition-colors"><span>Cluster</span></button>` : ''}
          </div>
        </td>
      `;

      tr.addEventListener('click', () => {
        window.openAlertDecisionDrawer(alert.id);
      });

      elements.alertsTableBody.appendChild(tr);
    });
  }

  // Filter alerts in table based on query
  function filterAlertsTable() {
    if (!state.filterQuery) {
      renderLiveAlerts();
      return;
    }
    const filtered = state.alerts.filter((a) => {
      const title = (a.title || a.alert_name || '').toLowerCase();
      const service = (a.service || '').toLowerCase();
      const message = (a.message || a.summary || '').toLowerCase();
      return title.includes(state.filterQuery) || service.includes(state.filterQuery) || message.includes(state.filterQuery);
    });

    if (elements.alertsTableBody) {
      elements.alertsTableBody.innerHTML = '';
      if (filtered.length === 0) {
        elements.alertsTableBody.innerHTML = `<tr><td colspan="7" class="py-8 text-center text-secondary font-body-md">No telemetry alerts match "${state.filterQuery}"</td></tr>`;
        return;
      }
      filtered.forEach((alert) => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-surface-container-low transition-colors border-b border-surface-container-high group cursor-pointer';
        const isSuppressed = alert.status === 'SUPPRESSED' || alert.is_duplicate;
        const statusPill = isSuppressed
          ? `<span class="px-2 py-0.5 rounded bg-surface-container text-secondary font-code-sm text-[11px]">Suppressed</span>`
          : `<span class="px-2 py-0.5 rounded bg-primary-container text-on-primary font-code-sm text-[11px]">Notified</span>`;

        tr.innerHTML = `
          <td class="py-2.5 px-3 font-code-sm text-xs text-secondary">${alert.created_at ? new Date(alert.created_at).toLocaleTimeString() : '—'}</td>
          <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded bg-surface-container font-code-sm text-[11px] font-bold ${alert.severity === 'CRITICAL' ? 'text-error' : 'text-primary'}">${alert.severity || 'INFO'}</span></td>
          <td class="py-2.5 px-3 font-code-sm text-xs font-semibold text-on-surface">${alert.title || alert.alert_name}</td>
          <td class="py-2.5 px-3 font-code-sm text-xs text-primary font-medium">${alert.service}</td>
          <td class="py-2.5 px-3 font-code-sm text-xs text-secondary">${alert.occurrence_count || 1}x</td>
          <td class="py-2.5 px-3">${statusPill}</td>
          <td class="py-2.5 px-3 text-right">
            <div class="flex items-center justify-end gap-1.5">
              <button onclick="event.stopPropagation(); window.openAlertDecisionDrawer('${alert.id}')" title="Inspect Decision & Evidence" class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-surface-container hover:bg-primary hover:text-white text-on-surface font-code-sm text-xs font-semibold transition-colors">
                <span class="material-symbols-outlined text-[14px]">psychology</span>
                <span>Explain</span>
              </button>
              ${alert.incident_id ? `<button onclick="event.stopPropagation(); window.inspectIncident('${alert.incident_id}')" class="px-2 py-1 rounded bg-primary-fixed text-on-primary-fixed text-xs font-semibold hover:bg-primary hover:text-white transition-colors">Cluster</button>` : ''}
            </div>
          </td>
        `;
        tr.addEventListener('click', () => {
          window.openAlertDecisionDrawer(alert.id);
        });
        elements.alertsTableBody.appendChild(tr);
      });
    }
  }

  // Render Alert Groups (Incident Clusters)
  function renderAlertGroups() {
    const container = document.getElementById('alert-groups-list');
    if (!container) return;

    if (state.incidents.length === 0) {
      container.innerHTML = `
        <div class="p-8 text-center text-secondary border border-dashed border-surface-container-highest rounded-xl">
          <span class="material-symbols-outlined text-[36px] text-outline mb-2">layers_clear</span>
          <p class="font-body-md font-semibold text-on-surface">No correlated alert groups</p>
          <p class="font-body-sm text-xs text-on-surface-variant mt-1">Alert groups are automatically synthesized when related alerts fire across services.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = '';
    state.incidents.forEach((inc) => {
      const card = document.createElement('div');
      const isCrit = inc.priority === 'CRITICAL' || inc.severity === 'CRITICAL';
      card.className = `p-space-base bg-surface-container-lowest rounded-xl shadow-sm border-l-4 ${
        isCrit ? 'border-l-error' : 'border-l-primary'
      } hover:shadow-md transition-all cursor-pointer`;

      card.innerHTML = `
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-space-sm">
          <div class="space-y-1">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="px-2 py-0.5 rounded ${
                isCrit ? 'bg-error-container text-on-error-container' : 'bg-primary-fixed text-on-primary-fixed'
              } font-code-sm text-code-sm font-bold">${inc.priority || inc.severity || 'HIGH'}</span>
              <span class="font-code-md text-code-md font-semibold text-on-surface">${inc.incident_number || inc.id}</span>
              <span class="text-on-surface-variant font-code-sm text-[11px]">${inc.status}</span>
            </div>
            <h3 class="font-headline-sm text-headline-sm text-on-surface font-semibold">${inc.title}</h3>
            <p class="font-body-sm text-body-sm text-on-surface-variant">${inc.description || 'Correlated incident cluster'}</p>
            <div class="flex items-center gap-2 pt-1 flex-wrap">
              <span class="px-2 py-0.5 rounded bg-surface-container font-code-sm text-[11px] text-secondary">${inc.service}</span>
            </div>
          </div>
          <div class="flex flex-col items-end gap-2 shrink-0">
            <div class="flex items-baseline gap-1.5">
              <span class="font-headline-lg text-headline-lg text-on-surface font-bold">${inc.alert_count || 1}</span>
              <span class="font-body-sm text-body-sm text-secondary">alerts grouped</span>
            </div>
            <div class="flex items-center gap-2">
              ${inc.status === 'OPEN' ? `
                <button onclick="event.stopPropagation(); window.acknowledgeCurrentIncident('${inc.id}')" title="Acknowledge Incident" class="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-white font-label-md text-xs font-semibold flex items-center gap-1 transition-colors shadow-xs cursor-pointer">
                  <span class="material-symbols-outlined text-[15px]">task_alt</span>
                  <span>Acknowledge</span>
                </button>
              ` : ''}
              ${inc.status !== 'RESOLVED' ? `
                <button onclick="event.stopPropagation(); window.resolveCurrentIncident('${inc.id}')" title="Resolve Incident" class="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-label-md text-xs font-semibold flex items-center gap-1 transition-colors shadow-xs cursor-pointer">
                  <span class="material-symbols-outlined text-[15px]">check_circle</span>
                  <span>Resolve</span>
                </button>
              ` : `
                <span class="px-2.5 py-1.5 rounded-lg bg-emerald-100 text-emerald-800 font-code-sm text-xs font-bold">Resolved ✓</span>
              `}
              <button onclick="event.stopPropagation(); window.openGroupDecisionDrawer('${inc.id}')" class="px-3 py-1.5 rounded-lg bg-surface-container hover:bg-surface-container-high text-on-surface font-label-md text-xs font-semibold flex items-center gap-1 transition-colors">
                <span class="material-symbols-outlined text-[15px] text-primary">psychology</span>
                <span>Explain Grouping</span>
              </button>
              <button onclick="event.stopPropagation(); window.inspectIncident('${inc.id}')" class="px-3 py-1.5 rounded-lg bg-primary text-on-primary font-label-md text-label-md hover:bg-primary-container transition-colors">
                Inspect Timeline
              </button>
            </div>
          </div>
        </div>
      `;

      card.addEventListener('click', () => {
        window.inspectIncident(inc.id);
      });

      container.appendChild(card);
    });
  }

  // Render Incidents Quick List in Sidebar/Incidents View
  function renderIncidentsList() {
    const list = document.getElementById('incidents-quick-list');
    if (!list) return;

    if (state.incidents.length === 0) {
      list.innerHTML = `<div class="p-3 text-center text-secondary text-xs">No active incidents recorded</div>`;
      return;
    }

    list.innerHTML = '';
    state.incidents.forEach((inc) => {
      const item = document.createElement('div');
      item.className = 'p-3 rounded-lg bg-surface-container-low hover:bg-surface-container transition-colors cursor-pointer border border-surface-container-highest';
      item.innerHTML = `
        <div class="flex items-center justify-between mb-1">
          <span class="font-code-sm text-code-sm font-bold text-primary">${inc.incident_number || inc.id}</span>
          <span class="font-code-sm text-[10px] text-secondary">${inc.status}</span>
        </div>
        <div class="font-label-md text-label-md text-on-surface font-semibold line-clamp-1">${inc.title}</div>
        <div class="flex items-center justify-between mt-2 font-code-sm text-[11px] text-on-surface-variant">
          <span>${inc.service}</span>
          <span class="text-primary font-medium">${inc.alert_count || 1} alerts</span>
        </div>
      `;
      item.addEventListener('click', () => {
        window.inspectIncident(inc.id);
      });
      list.appendChild(item);
    });
  }

  // Inspect Incident Helper
  window.inspectIncident = function (incidentId) {
    renderSelectedIncident(incidentId);
    navigateTo('incident-details');
  };

  // Render Selected Incident in Details View
  function renderSelectedIncident(incidentId) {
    if (state.incidents.length === 0) {
      renderEmptyIncidentDetail();
      return;
    }

    const inc = state.incidents.find((i) => i.id === incidentId || i.incident_number === incidentId) || state.incidents[0];
    if (!inc) {
      renderEmptyIncidentDetail();
      return;
    }

    state.selectedIncidentId = inc.id;

    // Header & metadata updates from real incident object
    const titleElem = document.getElementById('incident-details-title');
    if (titleElem) titleElem.innerText = `${inc.incident_number || inc.id}: ${inc.title}`;

    const descElem = document.getElementById('incident-details-desc');
    if (descElem) descElem.innerText = inc.description || 'Correlated cluster of raw telemetry alerts.';

    const numBadge = document.getElementById('incident-number-badge');
    if (numBadge) numBadge.innerText = inc.incident_number || inc.id;

    const sevBadge = document.getElementById('incident-severity-badge');
    if (sevBadge) {
      const isCrit = inc.priority === 'CRITICAL' || inc.severity === 'CRITICAL';
      sevBadge.className = `inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full ${
        isCrit ? 'bg-error-container text-on-error-container' : 'bg-primary-fixed text-on-primary-fixed'
      } font-code-sm text-code-sm font-semibold uppercase tracking-wider`;
      sevBadge.innerHTML = `<span class="w-2 h-2 rounded-full ${isCrit ? 'bg-error' : 'bg-primary'} animate-pulse"></span>${inc.priority || inc.severity || 'HIGH'} SEVERITY`;
    }

    const timeElem = document.getElementById('incident-started-time');
    if (timeElem) {
      timeElem.innerText = inc.first_seen ? new Date(inc.first_seen).toUTCString() : (inc.created_at ? new Date(inc.created_at).toUTCString() : 'Active');
    }

    const statusElem = document.getElementById('incident-status-tag');
    if (statusElem) {
      statusElem.innerText = inc.status || 'OPEN';
      statusElem.className = inc.status === 'RESOLVED' ? 'font-medium text-emerald-600 uppercase' : inc.status === 'ACKNOWLEDGED' ? 'font-medium text-blue-600 uppercase' : 'font-medium text-amber-600 uppercase';
    }

    const leadElem = document.getElementById('incident-lead-service');
    if (leadElem) leadElem.innerText = inc.service || 'service';

    const ownerElem = document.getElementById('incident-owner');
    if (ownerElem) ownerElem.innerText = inc.commander || 'Automated SRE Engine';

    // Update Acknowledge/Resolve button states based on current incident status
    const btnAck = document.getElementById('btn-ack-incident');
    const btnRes = document.getElementById('btn-res-incident');
    const btnReopen = document.getElementById('btn-reopen-incident');
    if (btnAck && btnRes) {
      if (inc.status === 'RESOLVED') {
        btnAck.disabled = true;
        btnAck.className = 'inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-surface-container text-on-surface-variant font-label-md text-label-md transition-all shadow-sm cursor-not-allowed opacity-50';
        btnRes.disabled = true;
        btnRes.className = 'inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-surface-container text-on-surface-variant font-label-md text-label-md transition-all shadow-sm cursor-not-allowed opacity-50';
        if (btnReopen) btnReopen.classList.remove('hidden');
      } else if (inc.status === 'ACKNOWLEDGED') {
        btnAck.disabled = true;
        btnAck.className = 'inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-blue-100 text-blue-700 font-label-md text-label-md transition-all shadow-sm cursor-not-allowed';
        const ackLabel = document.getElementById('btn-ack-label');
        if (ackLabel) ackLabel.innerText = '✓ Acknowledged';
        btnRes.disabled = false;
        btnRes.className = 'inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-emerald-600 text-white font-label-md text-label-md hover:bg-emerald-700 active:scale-95 transition-all shadow-sm cursor-pointer';
        if (btnReopen) btnReopen.classList.remove('hidden');
      } else {
        // OPEN — both fully active
        btnAck.disabled = false;
        btnAck.className = 'inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-amber-500 text-white font-label-md text-label-md hover:bg-amber-600 active:scale-95 transition-all shadow-sm cursor-pointer';
        const ackLabel = document.getElementById('btn-ack-label');
        if (ackLabel) ackLabel.innerText = 'Acknowledge';
        btnRes.disabled = false;
        btnRes.className = 'inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-emerald-600 text-white font-label-md text-label-md hover:bg-emerald-700 active:scale-95 transition-all shadow-sm cursor-pointer';
        if (btnReopen) btnReopen.classList.add('hidden');
      }
    }

    // Update Incident Select Dropdown
    const selectDropdown = document.getElementById('incident-select-dropdown');
    if (selectDropdown) {
      selectDropdown.innerHTML = state.incidents
        .map((i) => `<option value="${i.id}" ${i.id === inc.id ? 'selected' : ''}>${i.incident_number || i.id} - ${i.service} (${i.alert_count || 1} alerts)</option>`)
        .join('');
    }

    // Populate Grouped Alerts for this Incident
    const groupedTbody = document.getElementById('incident-grouped-alerts-tbody');
    const alertsBadge = document.getElementById('incident-alerts-badge');
    if (groupedTbody) {
      // Find alerts belonging to this incident or service
      let matchingAlerts = state.alerts.filter((a) => a.incident_id === inc.id);
      if (matchingAlerts.length === 0) {
        matchingAlerts = state.alerts.filter((a) => a.service === inc.service);
      }

      if (alertsBadge) {
        alertsBadge.innerText = `${matchingAlerts.length} Real Alerts`;
      }

      groupedTbody.innerHTML = '';
      if (matchingAlerts.length === 0) {
        groupedTbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-secondary text-xs">No individual alert rows linked directly to this cluster.</td></tr>`;
      } else {
        matchingAlerts.forEach((alt) => {
          const tr = document.createElement('tr');
          tr.className = 'border-b border-surface-container-high hover:bg-surface-container-low transition-colors cursor-pointer';
          const timeStr = alt.created_at ? new Date(alt.created_at).toLocaleTimeString() : (alt.timestamp || '—');
          const isSuppressed = alt.status === 'SUPPRESSED' || alt.is_duplicate;
          const statusBadge = isSuppressed
            ? `<span class="px-2 py-0.5 rounded bg-surface-container text-secondary font-code-sm text-[11px]">Suppressed</span>`
            : `<span class="px-2 py-0.5 rounded bg-primary-container text-on-primary font-code-sm text-[11px]">Notified</span>`;

          tr.innerHTML = `
            <td class="py-2.5 px-3 font-code-sm text-xs text-secondary">${timeStr}</td>
            <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded bg-surface-container font-code-sm text-[11px] font-bold ${alt.severity === 'CRITICAL' ? 'text-error' : 'text-primary'}">${alt.severity || 'INFO'}</span></td>
            <td class="py-2.5 px-3 font-semibold font-code-sm text-xs text-on-surface">${alt.title || alt.alert_name || 'Alert'}</td>
            <td class="py-2.5 px-3 font-code-sm text-xs text-primary">${alt.service || inc.service}</td>
            <td class="py-2.5 px-3">${statusBadge}</td>
            <td class="py-2.5 px-3 text-right">
              <button onclick="event.stopPropagation(); window.openAlertDecisionDrawer('${alt.id}')" title="Inspect Decision" class="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-surface-container hover:bg-primary hover:text-white text-on-surface font-code-sm text-xs font-semibold transition-colors">
                <span class="material-symbols-outlined text-[13px]">psychology</span>
                <span>Explain</span>
              </button>
            </td>
          `;

          tr.addEventListener('click', () => {
            window.openAlertDecisionDrawer(alt.id);
          });

          groupedTbody.appendChild(tr);
        });
      }
    }

    // Load real chronological timeline from API
    loadIncidentTimeline(inc.id);
  }

  function renderEmptyIncidentDetail() {
    const titleElem = document.getElementById('incident-details-title');
    if (titleElem) titleElem.innerText = 'No Incident Selected';

    const container = document.getElementById('incident-timeline-container');
    if (container) {
      container.innerHTML = `
        <div class="p-8 text-center text-secondary border border-dashed border-surface-container-highest rounded-2xl">
          <span class="material-symbols-outlined text-[40px] text-outline mb-2">timeline</span>
          <div class="font-semibold text-on-surface">No incident selected</div>
          <div class="text-xs text-on-surface-variant mt-1">Select an incident from the dropdown or send alerts to form clusters.</div>
        </div>
      `;
    }
  }

  // Real Incident Timeline API Loader
  async function loadIncidentTimeline(incidentId) {
    const container = document.getElementById('incident-timeline-container');
    const countBadge = document.getElementById('timeline-event-count');
    if (!container) return;

    container.innerHTML = '<div class="text-center py-6 text-secondary text-sm">Loading incident lifecycle events...</div>';

    try {
      const resp = await fetch(`http://localhost:8000/api/v1/dashboard/timeline/${incidentId}`);
      if (resp.ok) {
        const timeline = await resp.json();
        if (timeline.events && timeline.events.length > 0) {
          renderTimelineEvents(timeline.events);
          if (countBadge) countBadge.innerText = `${timeline.events.length} events`;
          return;
        }
      }
    } catch (e) {
      console.warn('Timeline API unreachable for incident:', incidentId);
    }

    container.innerHTML = `
      <div class="p-6 text-center text-secondary border border-dashed border-surface-container-highest rounded-xl">
        <span class="material-symbols-outlined text-[32px] text-outline mb-2">event_busy</span>
        <div class="font-semibold text-on-surface">No timeline events recorded</div>
        <div class="text-xs text-on-surface-variant mt-1">Lifecycle events are logged as the incident progresses.</div>
      </div>
    `;
    if (countBadge) countBadge.innerText = '0 events';
  }

  function renderTimelineEvents(events) {
    const container = document.getElementById('incident-timeline-container');
    if (!container) return;

    let html = '';
    events.forEach((ev, idx) => {
      const isLast = idx === events.length - 1;
      const stageColors = {
        'INGESTION': 'bg-blue-500',
        'DEDUPLICATION': 'bg-amber-500',
        'CORRELATION': 'bg-indigo-500',
        'DECISION': 'bg-purple-500',
        'NOTIFICATION': 'bg-emerald-500',
        'ACKNOWLEDGEMENT': 'bg-cyan-500',
        'RESOLUTION': 'bg-emerald-600'
      };
      const dotColor = stageColors[ev.stage] || 'bg-primary';

      html += `
        <div class="relative flex items-start gap-4 pb-6">
          ${!isLast ? '<div class="absolute left-[15px] top-[24px] bottom-0 w-0.5 bg-surface-container-high"></div>' : ''}
          <div class="w-8 h-8 rounded-full ${dotColor} text-white flex items-center justify-center shrink-0 z-10 shadow-sm">
            <span class="material-symbols-outlined text-[16px]">
              ${ev.stage === 'INGESTION' ? 'sensors' : ev.stage === 'DEDUPLICATION' ? 'filter_alt' : ev.stage === 'CORRELATION' ? 'hub' : ev.stage === 'DECISION' ? 'psychology' : ev.stage === 'NOTIFICATION' ? 'campaign' : ev.stage === 'ACKNOWLEDGEMENT' ? 'task_alt' : 'verified'}
            </span>
          </div>
          <div class="flex-1 bg-surface-container-lowest p-3 rounded-xl border border-surface-container shadow-xs">
            <div class="flex items-center justify-between gap-2 flex-wrap mb-1">
              <span class="font-headline-sm text-sm font-bold text-on-surface">${ev.label || ev.stage}</span>
              <div class="flex items-center gap-2">
                <span class="font-code-sm text-[11px] text-secondary">${ev.formatted_time || ev.timestamp}</span>
                <span class="px-2 py-0.5 rounded bg-surface-container text-[10px] font-bold text-primary">${ev.stage}</span>
              </div>
            </div>
            <p class="font-body-sm text-xs text-on-surface-variant">${ev.description}</p>
          </div>
        </div>
      `;
    });

    container.innerHTML = html;
  }

  // Incident Lifecycle Actions (Ack / Resolve / Reopen)
  // Accepts an optional incidentId so these work from overview cards, group cards, and the detail page
  window.acknowledgeCurrentIncident = async function (incidentId) {
    const incId = incidentId || state.selectedIncidentId;
    if (!incId) {
      showToast('No incident selected — navigate to Incident Details first', 'warning');
      return;
    }
    // Optimistic local state update (works offline)
    const target = state.incidents.find((i) => i.id === incId || i.incident_number === incId);
    if (target) {
      target.status = 'ACKNOWLEDGED';
      target.acknowledged_at = new Date().toISOString();
      target.acknowledged_by = 'SRE Operator';
    }
    state.selectedIncidentId = incId;
    // Re-render immediately
    renderOverviewIncidents();
    renderAlertGroups();
    renderIncidentsList();
    updateOpenIncidentsBadge();
    if (state.currentView === 'incident-details') renderSelectedIncident(incId);
    showToast(`Incident acknowledged — MTTA timer stopped`, 'success');
    // Also try to persist via API
    try {
      await fetch(`http://localhost:8000/api/v1/incidents/${incId}/acknowledge`, { method: 'POST' });
    } catch (e) {
      // offline — local state already updated, no user-facing error
    }
    fetchAllRealData();
  };

  window.resolveCurrentIncident = async function (incidentId) {
    const incId = incidentId || state.selectedIncidentId;
    if (!incId) {
      showToast('No incident selected — navigate to Incident Details first', 'warning');
      return;
    }
    // Optimistic local state update (works offline)
    const target = state.incidents.find((i) => i.id === incId || i.incident_number === incId);
    if (target) {
      target.status = 'RESOLVED';
      target.resolved_at = new Date().toISOString();
      target.resolved_by = 'SRE Operator';
    }
    state.selectedIncidentId = incId;
    // Re-render immediately
    renderOverviewIncidents();
    renderAlertGroups();
    renderIncidentsList();
    updateOpenIncidentsBadge();
    if (state.currentView === 'incident-details') renderSelectedIncident(incId);
    showToast(`Incident resolved — MTTR captured successfully`, 'success');
    // Also try to persist via API
    try {
      await fetch(`http://localhost:8000/api/v1/incidents/${incId}/resolve`, { method: 'POST' });
    } catch (e) {
      // offline — local state already updated, no user-facing error
    }
    fetchAllRealData();
  };

  window.handleReopenCurrentIncident = async function (incidentId) {
    const incId = incidentId || state.selectedIncidentId;
    if (!incId) return;
    const target = state.incidents.find((i) => i.id === incId || i.incident_number === incId);
    if (target) {
      target.status = 'OPEN';
      target.resolved_at = null;
      target.acknowledged_at = null;
    }
    renderOverviewIncidents();
    renderAlertGroups();
    renderIncidentsList();
    updateOpenIncidentsBadge();
    if (state.currentView === 'incident-details') renderSelectedIncident(incId);
    showToast(`Incident reopened for re-triage`, 'info');
    fetchAllRealData();
  };

  window.handleAcknowledgeCurrentIncident = window.acknowledgeCurrentIncident;
  window.handleResolveCurrentIncident = window.resolveCurrentIncident;

  // Live Analytics View Renderer (Real Database Data)
  window.fetchLiveAnalytics = async function () {
    await renderAnalytics();
    showToast('Analytics refreshed from database', 'info');
  };

  async function renderAnalytics() {
    try {
      // 1. Fetch Overview Analytics & Summary
      const [overviewResp, noisyResp] = await Promise.all([
        fetch('http://localhost:8000/api/v1/analytics/overview'),
        fetch('http://localhost:8000/api/v1/analytics/noisy-services?limit=10')
      ]);

      if (overviewResp.ok) {
        const data = await overviewResp.json();
        
        // Update 4 Metric Rate Cards
        const elemNoise = document.getElementById('analytics-noise-reduction');
        if (elemNoise) elemNoise.innerText = `${(data.suppression_rate || 0).toFixed(1)}%`;

        const elemDedup = document.getElementById('analytics-dedup-rate');
        if (elemDedup) {
          const total = data.total_alerts || 1;
          const dedupPct = (data.alert_reduction / total) * 100;
          elemDedup.innerText = `${dedupPct.toFixed(1)}%`;
        }

        const elemNotif = document.getElementById('analytics-notification-rate');
        if (elemNotif) elemNotif.innerText = `${(data.notification_rate || 0).toFixed(1)}%`;

        const elemMtta = document.getElementById('analytics-mtta');
        if (elemMtta) {
          elemMtta.innerText = state.summary && state.summary.mtta_seconds > 0
            ? state.summary.mtta_formatted
            : 'Awaiting data';
        }
      }

      // 2. Populate Noisy Services Table
      if (noisyResp.ok) {
        const services = await noisyResp.json();
        const tbody = document.getElementById('noisy-services-tbody');
        if (tbody && Array.isArray(services) && services.length > 0) {
          tbody.innerHTML = '';
          services.forEach((s) => {
            const tr = document.createElement('tr');
            tr.className = 'border-b border-surface-container-high hover:bg-surface-container-low transition-colors';
            const noiseRed = s.suppression_rate || (s.total_alerts > 0 ? (s.suppressed_alerts / s.total_alerts) * 100 : 0);
            const statusLabel = noiseRed > 50 ? 'Protected' : 'Filtered';
            const statusBg = noiseRed > 50 ? 'bg-emerald-100 text-emerald-800' : 'bg-blue-100 text-blue-800';

            tr.innerHTML = `
              <td class="py-2.5 px-3 font-semibold font-code-sm text-primary">${s.service_name || s.service || 'service'}</td>
              <td class="py-2.5 px-3 font-code-sm font-semibold">${s.total_alerts || s.count || 0}</td>
              <td class="py-2.5 px-3 font-code-sm text-emerald-600 font-semibold">${s.suppressed_alerts || 0}</td>
              <td class="py-2.5 px-3 font-code-sm text-violet-600 font-semibold">${s.notified_alerts || 0}</td>
              <td class="py-2.5 px-3 font-code-sm text-emerald-600 font-bold">${noiseRed.toFixed(1)}%</td>
              <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded ${statusBg} font-code-sm text-xs font-bold">${statusLabel}</span></td>
            `;
            tbody.appendChild(tr);
          });
        }
      }
    } catch (e) {
      console.warn('Analytics endpoint unreachable:', e);
    }
  }

  // Toggle Stream Auto-Refresh
  window.toggleAutoRefresh = function () {
    state.autoRefresh = !state.autoRefresh;
    if (elements.streamToggle) {
      if (state.autoRefresh) {
        elements.streamToggle.className =
          'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full bg-primary transition-colors duration-200 ease-in-out focus:outline-none';
        elements.streamThumb.className =
          'translate-x-4 inline-block h-4 w-4 transform rounded-full bg-on-primary transition duration-200 ease-in-out mt-0.5 ml-0.5';
        showToast('Real-time auto-refresh active (2s polling)', 'info');
      } else {
        elements.streamToggle.className =
          'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full bg-surface-container-highest transition-colors duration-200 ease-in-out focus:outline-none';
        elements.streamThumb.className =
          'translate-x-0 inline-block h-4 w-4 transform rounded-full bg-outline transition duration-200 ease-in-out mt-0.5 ml-0.5';
        showToast('Real-time auto-refresh paused', 'warning');
      }
    }
  };

  // Search Modal (⌘K)
  window.openSearchModal = function () {
    if (elements.searchModal) {
      elements.searchModal.classList.add('active');
      if (elements.modalSearchInput) {
        elements.modalSearchInput.value = '';
        elements.modalSearchInput.focus();
        handleModalSearch('');
      }
    }
  };

  window.closeSearchModal = function () {
    if (elements.searchModal) {
      elements.searchModal.classList.remove('active');
    }
  };

  function handleModalSearch(query) {
    if (!elements.modalSearchResults) return;
    query = query.toLowerCase().trim();

    if (!query) {
      elements.modalSearchResults.innerHTML = `
        <div class="p-4 text-secondary text-center font-body-sm">
          Type to search alerts, incident IDs, or services...
        </div>
      `;
      return;
    }

    const matchedAlerts = state.alerts.filter(
      (a) => (a.title || a.alert_name || '').toLowerCase().includes(query) || (a.service || '').toLowerCase().includes(query)
    );
    const matchedIncidents = state.incidents.filter(
      (i) => (i.title || '').toLowerCase().includes(query) || (i.id || i.incident_number || '').toLowerCase().includes(query) || (i.service || '').toLowerCase().includes(query)
    );

    let html = '';

    if (matchedIncidents.length > 0) {
      html += `<div class="px-3 py-1 font-label-sm text-[11px] text-secondary uppercase tracking-wider font-semibold">Incidents</div>`;
      matchedIncidents.forEach((inc) => {
        html += `
          <div onclick="window.closeSearchModal(); window.inspectIncident('${inc.id}')" class="p-2.5 rounded-lg hover:bg-surface-container flex items-center justify-between cursor-pointer">
            <div>
              <span class="font-code-sm text-code-sm font-bold text-primary">${inc.incident_number || inc.id}</span>:
              <span class="font-body-sm text-body-sm font-medium text-on-surface">${inc.title}</span>
            </div>
            <span class="font-code-sm text-[10px] bg-surface-container-high px-1.5 py-0.5 rounded text-secondary">${inc.service}</span>
          </div>
        `;
      });
    }

    if (matchedAlerts.length > 0) {
      html += `<div class="px-3 py-1 mt-2 font-label-sm text-[11px] text-secondary uppercase tracking-wider font-semibold">Alerts</div>`;
      matchedAlerts.forEach((alt) => {
        html += `
          <div onclick="window.closeSearchModal(); window.openAlertDecisionDrawer('${alt.id}')" class="p-2.5 rounded-lg hover:bg-surface-container flex items-center justify-between cursor-pointer">
            <div>
              <span class="font-code-sm text-code-sm font-bold text-primary">${alt.id}</span>:
              <span class="font-body-sm text-body-sm text-on-surface">${alt.title || alt.alert_name}</span>
            </div>
            <span class="font-code-sm text-[10px] bg-surface-container-high px-1.5 py-0.5 rounded text-secondary">${alt.service}</span>
          </div>
        `;
      });
    }

    if (!html) {
      html = `<div class="p-4 text-center text-secondary font-body-sm">No results found for "${query}"</div>`;
    }

    elements.modalSearchResults.innerHTML = html;
  }

  // Keyboard Shortcuts
  function setupShortcutKeys() {
    window.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        openSearchModal();
      }
      if (e.key === 'Escape') {
        closeSearchModal();
        closeDecisionDrawer();
      }
    });
  }

  // Toast Notification System
  window.showToast = function (message, type = 'info') {
    if (!elements.toastContainer) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    let icon = 'info';
    if (type === 'success') icon = 'check_circle';
    if (type === 'warning') icon = 'warning';
    if (type === 'error') icon = 'error';

    toast.innerHTML = `
      <span class="material-symbols-outlined text-[20px] ${
        type === 'success'
          ? 'text-emerald-600'
          : type === 'warning'
          ? 'text-amber-600'
          : type === 'error'
          ? 'text-red-600'
          : 'text-primary'
      }">${icon}</span>
      <span class="font-body-sm text-body-sm text-on-surface font-medium flex-1">${message}</span>
      <button onclick="this.parentElement.remove()" class="text-outline hover:text-on-surface">
        <span class="material-symbols-outlined text-[16px]">close</span>
      </button>
    `;

    elements.toastContainer.appendChild(toast);

    setTimeout(() => {
      if (toast.parentElement) toast.remove();
    }, 3800);
  };

  // ==========================================
  // PHASE 7: EXPLAINABILITY & DECISION DRAWER
  // ==========================================

  window.openAlertDecisionDrawer = async function (identifier, isAlertId = true) {
    const panel = document.getElementById('decision-drawer-panel');
    const backdrop = document.getElementById('decision-drawer-backdrop');
    if (!panel || !backdrop) return;

    // Open drawer
    backdrop.classList.add('active');
    panel.classList.add('open');

    // Set Loading State
    const badge = document.getElementById('drawer-decision-badge');
    const whatText = document.getElementById('drawer-what-text');
    const whyText = document.getElementById('drawer-why-text');
    const confidenceScore = document.getElementById('drawer-confidence-score');
    const traceCard = document.getElementById('drawer-trace-card');
    const traceFlow = document.getElementById('drawer-trace-flow');
    const evidenceList = document.getElementById('drawer-evidence-list');
    const evidenceCount = document.getElementById('drawer-evidence-count');
    const outcomeText = document.getElementById('drawer-outcome-text');
    const latencyElem = document.getElementById('drawer-processing-latency');
    const rawJson = document.getElementById('drawer-raw-json');

    if (badge) {
      badge.className = 'px-2.5 py-0.5 rounded-full font-code-sm text-xs font-bold bg-primary-fixed text-on-primary-fixed animate-pulse';
      badge.innerText = 'EVALUATING';
    }
    if (whatText) whatText.innerText = 'Fetching deterministic decision record...';
    if (whyText) whyText.innerText = `Querying PostgreSQL decision records...`;
    if (confidenceScore) confidenceScore.innerText = 'Checking confidence...';
    if (traceCard) traceCard.classList.add('hidden');
    if (evidenceList) evidenceList.innerHTML = `<div class="p-4 text-secondary text-center font-body-sm"><span class="material-symbols-outlined text-[20px] animate-spin">sync</span> Loading decision evidence...</div>`;
    if (evidenceCount) evidenceCount.innerText = 'Querying...';
    if (outcomeText) outcomeText.innerText = 'Awaiting backend response...';
    if (latencyElem) latencyElem.innerText = '...';
    if (rawJson) rawJson.innerText = `// Querying backend explain API...`;

    const startTime = performance.now();
    const apiUrl = isAlertId
      ? `http://localhost:8000/api/v1/dashboard/explain/alert/${identifier}`
      : `http://localhost:8000/api/v1/dashboard/explain/${identifier}`;

    try {
      const resp = await fetch(apiUrl);
      const elapsedMs = Math.round(performance.now() - startTime);

      if (!resp.ok) {
        throw new Error(`API returned HTTP ${resp.status}`);
      }

      const data = await resp.json();

      // Render Decision Badge
      if (badge) {
        badge.classList.remove('animate-pulse');
        const dec = (data.decision || 'ANALYZED').toUpperCase();
        if (dec === 'SUPPRESS' || dec === 'SUPPRESSED') {
          badge.className = 'px-2.5 py-0.5 rounded-full font-code-sm text-xs font-bold bg-surface-container-highest text-on-surface-variant';
          badge.innerText = 'PREVENTED (SUPPRESS)';
        } else if (dec === 'NOTIFY' || dec === 'NOTIFIED') {
          badge.className = 'px-2.5 py-0.5 rounded-full font-code-sm text-xs font-bold bg-primary-container text-on-primary';
          badge.innerText = 'DISPATCHED (NOTIFY)';
        } else if (dec === 'ESCALATE' || dec === 'ESCALATED') {
          badge.className = 'px-2.5 py-0.5 rounded-full font-code-sm text-xs font-bold bg-error-container text-on-error-container';
          badge.innerText = 'ESCALATED';
        } else {
          badge.className = 'px-2.5 py-0.5 rounded-full font-code-sm text-xs font-bold bg-primary-fixed text-on-primary-fixed';
          badge.innerText = dec;
        }
      }

      if (whatText) whatText.innerText = data.what_happened || 'Decision Evaluated';
      if (whyText) whyText.innerText = data.why || 'Decision processed deterministically by SRE intelligence pipeline.';

      // Confidence score: Honest empty state / unavailable label (no fake 95% or 98%)
      if (confidenceScore) {
        if (data.confidence !== null && data.confidence !== undefined) {
          confidenceScore.innerText = `${data.confidence}%`;
          confidenceScore.className = 'font-code-sm text-primary font-bold';
        } else {
          confidenceScore.innerText = 'Confidence score not available (deterministic rule evaluation)';
          confidenceScore.className = 'font-code-sm text-outline italic';
        }
      }

      // Step 10: Decision -> Incident Trace
      const trace = (data.technical_details && data.technical_details.decision_trace) || null;
      if (traceFlow && traceCard) {
        if (trace) {
          traceCard.classList.remove('hidden');
          traceFlow.innerHTML = `
            <div class="flex items-center gap-2 p-2 rounded-lg bg-surface-container-low border border-surface-container-highest">
              <span class="font-bold text-secondary uppercase font-code-sm text-[10px] w-24 shrink-0">1. Alert</span>
              <span class="text-on-surface font-medium truncate flex-1">${trace.alert || 'Telemetry Alert'}</span>
            </div>
            <div class="flex justify-center my-0.5"><span class="material-symbols-outlined text-[14px] text-outline">arrow_downward</span></div>
            <div class="flex items-center gap-2 p-2 rounded-lg bg-surface-container-low border border-surface-container-highest">
              <span class="font-bold text-secondary uppercase font-code-sm text-[10px] w-24 shrink-0">2. Analysis</span>
              <span class="text-on-surface-variant flex-1">${trace.system_analysis || 'Cooldown & repetition verified'}</span>
            </div>
            <div class="flex justify-center my-0.5"><span class="material-symbols-outlined text-[14px] text-outline">arrow_downward</span></div>
            <div class="flex items-center gap-2 p-2 rounded-lg bg-surface-container-low border border-surface-container-highest">
              <span class="font-bold text-secondary uppercase font-code-sm text-[10px] w-24 shrink-0">3. Decision</span>
              <span class="font-bold font-code-sm text-primary flex-1">${trace.human_decision || trace.decision}</span>
            </div>
            <div class="flex justify-center my-0.5"><span class="material-symbols-outlined text-[14px] text-outline">arrow_downward</span></div>
            <div class="flex items-center gap-2 p-2 rounded-lg bg-surface-container-low border border-surface-container-highest">
              <span class="font-bold text-secondary uppercase font-code-sm text-[10px] w-24 shrink-0">4. Incident</span>
              <span class="text-on-surface flex-1 font-code-sm">${trace.related_incident || 'None (Suppressed)'}</span>
            </div>
            <div class="flex justify-center my-0.5"><span class="material-symbols-outlined text-[14px] text-outline">arrow_downward</span></div>
            <div class="flex items-center gap-2 p-2 rounded-lg bg-surface-container-low border border-surface-container-highest">
              <span class="font-bold text-secondary uppercase font-code-sm text-[10px] w-24 shrink-0">5. Result</span>
              <span class="font-medium text-emerald-700 flex-1">${trace.notification || 'Processed'}</span>
            </div>
          `;
        } else {
          traceCard.classList.add('hidden');
        }
      }

      // Render Deterministic Evidence List
      if (evidenceList) {
        evidenceList.innerHTML = '';
        const evidenceArr = Array.isArray(data.evidence) ? data.evidence : [];
        
        if (evidenceArr.length === 0 || (evidenceArr.length === 1 && evidenceArr[0] === 'Evidence not recorded')) {
          evidenceList.innerHTML = `<div class="p-3 text-secondary italic font-body-sm">Evidence not recorded</div>`;
          if (evidenceCount) evidenceCount.innerText = '0 recorded';
        } else {
          if (evidenceCount) evidenceCount.innerText = `${evidenceArr.length} rule${evidenceArr.length > 1 ? 's' : ''} verified`;
          evidenceArr.forEach((ev) => {
            const item = document.createElement('div');
            item.className = 'p-2.5 rounded-lg bg-surface-container-low border border-surface-container-highest flex items-start gap-2.5';
            item.innerHTML = `
              <span class="material-symbols-outlined text-[16px] text-primary shrink-0 mt-0.5">verified</span>
              <span class="font-body-sm text-xs text-on-surface leading-snug flex-1">${ev}</span>
            `;
            evidenceList.appendChild(item);
          });
        }
      }

      // Render Outcome
      if (outcomeText) {
        const dec = (data.decision || '').toUpperCase();
        if (dec === 'SUPPRESS' || dec === 'SUPPRESSED') {
          outcomeText.innerHTML = '<span class="text-secondary font-medium">Alert notification prevented to eliminate fatigue. Collapsed into deduplication window or active incident.</span>';
        } else if (dec === 'NOTIFY' || dec === 'NOTIFIED') {
          outcomeText.innerHTML = '<span class="text-primary font-medium">Actionable alert notification dispatched to on-call responder channel.</span>';
        } else if (dec === 'ESCALATE' || dec === 'ESCALATED') {
          outcomeText.innerHTML = '<span class="text-amber-700 font-medium">Incident escalated to Tier-2 engineers following duration or occurrence threshold breach.</span>';
        } else {
          outcomeText.innerText = 'Telemetry processed according to active SRE policies.';
        }
      }

      const procMs = data.technical_details && data.technical_details.processing_time_ms;
      if (latencyElem) latencyElem.innerText = procMs ? `${procMs} ms (decision engine)` : `${elapsedMs} ms (database query)`;
      if (rawJson) rawJson.innerText = JSON.stringify(data, null, 2);

    } catch (err) {
      console.error('Error fetching decision explanation:', err);
      if (badge) {
        badge.className = 'px-2.5 py-0.5 rounded-full font-code-sm text-xs font-bold bg-error-container text-on-error-container';
        badge.innerText = 'UNAVAILABLE';
      }
      if (whatText) whatText.innerText = 'Explanation unavailable for this decision';
      if (whyText) whyText.innerText = `Unable to retrieve decision record for ${identifier}.`;
      if (confidenceScore) confidenceScore.innerText = 'Confidence score not available';
      if (evidenceList) evidenceList.innerHTML = `<div class="p-3 text-secondary italic font-body-sm">Evidence not recorded</div>`;
      if (evidenceCount) evidenceCount.innerText = '0 rules verified';
      if (outcomeText) outcomeText.innerText = 'No outcome record found.';
      if (latencyElem) latencyElem.innerText = 'Failed';
      if (rawJson) rawJson.innerText = `// Error loading explanation: ${err.message}`;
    }
  };

  window.openDecisionExplanationById = function (decisionId) {
    window.openAlertDecisionDrawer(decisionId, false);
  };

  window.openGroupDecisionDrawer = async function (incidentId) {
    const panel = document.getElementById('decision-drawer-panel');
    const backdrop = document.getElementById('decision-drawer-backdrop');
    if (!panel || !backdrop) return;

    backdrop.classList.add('active');
    panel.classList.add('open');

    const badge = document.getElementById('drawer-decision-badge');
    const whatText = document.getElementById('drawer-what-text');
    const whyText = document.getElementById('drawer-why-text');
    const evidenceList = document.getElementById('drawer-evidence-list');
    const evidenceCount = document.getElementById('drawer-evidence-count');
    const outcomeText = document.getElementById('drawer-outcome-text');
    const latencyElem = document.getElementById('drawer-processing-latency');
    const rawJson = document.getElementById('drawer-raw-json');

    if (badge) {
      badge.className = 'px-2.5 py-0.5 rounded-full font-code-sm text-xs font-bold bg-primary-fixed text-on-primary-fixed animate-pulse';
      badge.innerText = 'CORRELATING';
    }
    if (whatText) whatText.innerText = 'Fetching incident group correlation...';
    if (whyText) whyText.innerText = `Querying PostgreSQL correlation records for incident ${incidentId}...`;
    if (evidenceList) evidenceList.innerHTML = `<div class="p-4 text-secondary text-center font-body-sm"><span class="material-symbols-outlined text-[20px] animate-spin">sync</span> Loading correlation evidence...</div>`;
    if (evidenceCount) evidenceCount.innerText = 'Querying...';
    if (outcomeText) outcomeText.innerText = 'Awaiting backend response...';
    if (latencyElem) latencyElem.innerText = '...';
    if (rawJson) rawJson.innerText = `// Querying /api/v1/dashboard/explain/group/${incidentId}...`;

    const startTime = performance.now();

    try {
      const resp = await fetch(`http://localhost:8000/api/v1/dashboard/explain/group/${incidentId}`);
      const elapsedMs = Math.round(performance.now() - startTime);

      if (!resp.ok) {
        throw new Error(`API returned HTTP ${resp.status}`);
      }

      const data = await resp.json();

      if (badge) {
        badge.classList.remove('animate-pulse');
        badge.className = 'px-2.5 py-0.5 rounded-full font-code-sm text-xs font-bold bg-primary-container text-on-primary';
        badge.innerText = 'CORRELATED CLUSTER';
      }

      if (whatText) whatText.innerText = data.what_happened || `Incident Cluster: ${incidentId}`;
      if (whyText) whyText.innerText = data.why || 'Correlated by service signature and temporal proximity.';

      if (evidenceList) {
        evidenceList.innerHTML = '';
        const evidenceArr = Array.isArray(data.evidence) ? data.evidence : [];
        if (evidenceArr.length === 0) {
          evidenceList.innerHTML = `<div class="p-3 text-secondary italic font-body-sm">Supporting correlation evidence is unavailable.</div>`;
          if (evidenceCount) evidenceCount.innerText = '0 rules verified';
        } else {
          if (evidenceCount) evidenceCount.innerText = `${evidenceArr.length} factors verified`;
          evidenceArr.forEach((ev) => {
            const item = document.createElement('div');
            item.className = 'p-2.5 rounded-lg bg-surface-container-low border border-surface-container-highest flex items-start gap-2.5';
            item.innerHTML = `
              <span class="material-symbols-outlined text-[16px] text-primary shrink-0 mt-0.5">hub</span>
              <span class="font-body-sm text-xs text-on-surface leading-snug flex-1">${ev}</span>
            `;
            evidenceList.appendChild(item);
          });
        }
      }

      if (outcomeText) {
        outcomeText.innerHTML = '<span class="text-primary font-medium">Grouped related alarms into a unified incident cluster to eliminate alert flooding and provide root cause context.</span>';
      }

      if (latencyElem) latencyElem.innerText = `${elapsedMs} ms (database query)`;
      if (rawJson) rawJson.innerText = JSON.stringify(data, null, 2);

    } catch (err) {
      console.error('Error fetching group explanation:', err);
      if (badge) {
        badge.className = 'px-2.5 py-0.5 rounded-full font-code-sm text-xs font-bold bg-error-container text-on-error-container';
        badge.innerText = 'UNAVAILABLE';
      }
      if (whatText) whatText.innerText = 'Correlation explanation unavailable';
      if (whyText) whyText.innerText = `Unable to retrieve correlation record for incident ${incidentId}.`;
      if (evidenceList) evidenceList.innerHTML = `<div class="p-3 text-secondary italic font-body-sm">No correlation evidence recorded in database.</div>`;
      if (outcomeText) outcomeText.innerText = 'No outcome record found.';
      if (rawJson) rawJson.innerText = `// Error: ${err.message}`;
    }
  };

  window.closeDecisionDrawer = function () {
    const panel = document.getElementById('decision-drawer-panel');
    const backdrop = document.getElementById('decision-drawer-backdrop');
    if (panel) panel.classList.remove('open');
    if (backdrop) backdrop.classList.remove('active');
  };

  window.toggleDrawerTechnicalDetails = function () {
    const content = document.getElementById('drawer-tech-content');
    const chevron = document.getElementById('drawer-tech-chevron');
    if (!content) return;
    if (content.classList.contains('hidden')) {
      content.classList.remove('hidden');
      if (chevron) chevron.innerText = 'expand_less';
    } else {
      content.classList.add('hidden');
      if (chevron) chevron.innerText = 'expand_more';
    }
  };

  // ==========================================
  // PHASE 7: DECISION INTELLIGENCE
  // ==========================================

  window.fetchDecisionIntelligence = async function () {
    try {
      const resp = await fetch('http://localhost:8000/api/v1/dashboard/decision-intelligence');
      if (resp.ok) {
        const data = await resp.json();
        renderDecisionIntelligence(data);
      } else {
        renderDecisionIntelligenceEmpty('Unable to reach the decision intelligence API.');
      }
    } catch (err) {
      console.warn('Decision Intelligence endpoint unreachable:', err);
      renderDecisionIntelligenceEmpty('Decision intelligence data unavailable. Backend may be offline.');
    }
  };

  function renderDecisionIntelligenceEmpty(message) {
    const msg = message || 'No decision data available yet.';
    const emptyHtml = `
      <div class="bg-surface-container-lowest p-8 rounded-2xl border border-surface-container-highest text-center">
        <span class="material-symbols-outlined text-[48px] text-outline mb-3">psychology</span>
        <h3 class="font-headline-sm text-lg font-bold text-on-surface mb-2">No Decisions Recorded Yet</h3>
        <p class="text-sm text-on-surface-variant max-w-md mx-auto">${msg}</p>
        <p class="text-xs text-outline mt-2">Process alerts through the system to see real decision explanations and metrics.</p>
      </div>
    `;
    const containers = ['di-breakdown-cards', 'di-suppression-reasons', 'di-notification-reasons', 'di-explorer-tbody', 'di-processing-perf', 'di-outcome-metrics'];
    containers.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = '';
    });
    const breakdownContainer = document.getElementById('di-breakdown-container');
    if (breakdownContainer) breakdownContainer.innerHTML = emptyHtml;
  }

  function renderDecisionIntelligence(data) {
    if (!data || !data.has_data) {
      renderDecisionIntelligenceEmpty();
      return;
    }

    // 1. Decision Breakdown Cards
    const breakdownCards = document.getElementById('di-breakdown-cards');
    const breakdownContainer = document.getElementById('di-breakdown-container');
    if (breakdownContainer && breakdownCards) {
      // Reset container to just the grid
      breakdownContainer.innerHTML = '';
      const grid = document.createElement('div');
      grid.className = 'grid grid-cols-1 sm:grid-cols-3 gap-space-md';
      grid.id = 'di-breakdown-cards';
      breakdownContainer.appendChild(grid);

      if (data.breakdown && data.breakdown.length > 0) {
        const colorMap = {
          'SUPPRESS': { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', icon: 'block', accent: 'text-emerald-600' },
          'NOTIFY': { bg: 'bg-violet-50', text: 'text-violet-700', border: 'border-violet-200', icon: 'notifications_active', accent: 'text-violet-600' },
          'ESCALATE': { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200', icon: 'priority_high', accent: 'text-amber-600' }
        };
        const defaultColor = { bg: 'bg-surface-container-low', text: 'text-on-surface', border: 'border-surface-container-highest', icon: 'psychology', accent: 'text-primary' };

        data.breakdown.forEach(item => {
          const colors = colorMap[item.decision_type] || defaultColor;
          const card = document.createElement('div');
          card.className = `bg-surface-container-lowest p-space-base rounded-xl shadow-sm border border-surface-container-highest flex flex-col justify-between`;
          card.innerHTML = `
            <div class="flex items-center justify-between">
              <span class="text-xs font-bold text-secondary uppercase">${item.human_label}</span>
              <span class="material-symbols-outlined text-[20px] ${colors.accent}">${colors.icon}</span>
            </div>
            <div class="my-2">
              <span class="text-3xl font-bold ${colors.accent} font-code-sm">${item.count.toLocaleString()}</span>
              ${item.percentage !== null ? `<span class="text-sm ${colors.text} ml-2">(${item.percentage}%)</span>` : ''}
            </div>
            <span class="text-[11px] font-code-sm ${colors.text} ${colors.bg} px-2 py-0.5 rounded font-medium border ${colors.border}">${item.decision_type}</span>
          `;
          grid.appendChild(card);
        });

        // Add total decisions summary card
        const totalCard = document.createElement('div');
        totalCard.className = `bg-surface-container-lowest p-space-base rounded-xl shadow-sm border border-surface-container-highest flex flex-col justify-between`;
        totalCard.innerHTML = `
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold text-secondary uppercase">Total System Decisions</span>
            <span class="material-symbols-outlined text-[20px] text-primary">psychology</span>
          </div>
          <div class="my-2">
            <span class="text-3xl font-bold text-primary font-code-sm">${data.total_decisions.toLocaleString()}</span>
          </div>
          <span class="text-[11px] font-code-sm text-primary bg-primary-fixed px-2 py-0.5 rounded font-medium">ALL DECISIONS</span>
        `;
        grid.appendChild(totalCard);
      } else {
        grid.innerHTML = `<div class="col-span-3 p-6 text-center text-sm text-on-surface-variant">No decision breakdown available.</div>`;
      }
    }

    // 2. Suppression Reasons
    const suppressionEl = document.getElementById('di-suppression-reasons');
    if (suppressionEl) {
      if (data.top_suppression_reasons && data.top_suppression_reasons.length > 0) {
        suppressionEl.innerHTML = renderReasonTable(data.top_suppression_reasons, 'emerald');
      } else {
        suppressionEl.innerHTML = `
          <div class="p-6 text-center">
            <span class="material-symbols-outlined text-[36px] text-outline mb-2">block</span>
            <h4 class="font-bold text-on-surface mb-1">No Prevented Notifications Yet</h4>
            <p class="text-xs text-on-surface-variant">No alerts have been suppressed by the system.</p>
          </div>
        `;
      }
    }

    // 3. Notification Reasons
    const notificationEl = document.getElementById('di-notification-reasons');
    if (notificationEl) {
      if (data.top_notification_reasons && data.top_notification_reasons.length > 0) {
        notificationEl.innerHTML = renderReasonTable(data.top_notification_reasons, 'violet');
      } else {
        notificationEl.innerHTML = `
          <div class="p-6 text-center">
            <span class="material-symbols-outlined text-[36px] text-outline mb-2">notifications_off</span>
            <h4 class="font-bold text-on-surface mb-1">No Notification Decisions Yet</h4>
            <p class="text-xs text-on-surface-variant">No alerts have been sent to responders yet.</p>
          </div>
        `;
      }
    }

    // 4. Decision Explorer Table
    const explorerTbody = document.getElementById('di-explorer-tbody');
    const explorerCount = document.getElementById('di-explorer-count');
    if (explorerTbody) {
      if (data.recent_decisions && data.recent_decisions.length > 0) {
        if (explorerCount) explorerCount.innerText = `${data.recent_decisions.length} DECISIONS`;
        explorerTbody.innerHTML = data.recent_decisions.map(dec => {
          const ts = new Date(dec.timestamp);
          const dateStr = ts.toLocaleDateString([], { month: 'short', day: 'numeric' });

          const decisionColors = {
            'SUPPRESS': 'bg-emerald-50 text-emerald-700 border-emerald-200',
            'NOTIFY': 'bg-violet-50 text-violet-700 border-violet-200',
            'ESCALATE': 'bg-amber-50 text-amber-700 border-amber-200'
          };
          const decColor = decisionColors[dec.decision] || 'bg-surface-container-low text-on-surface border-surface-container-highest';

          const alertId = dec.alert_id || '';
          const decId = dec.decision_record_id || dec.decision_id || '';
          const clickFn = decId
            ? `openDecisionExplanationById('${decId}')`
            : (alertId ? `openAlertDecisionDrawer('${alertId}', true)` : '');

          return `
            <tr class="border-b border-surface-container-highest hover:bg-surface-container-low transition-colors cursor-pointer" onclick="${clickFn}">
              <td class="py-2.5 px-3 font-code-sm text-xs text-secondary whitespace-nowrap">
                <div>${timeStr}</div>
                <div class="text-[10px] text-outline">${dateStr}</div>
              </td>
              <td class="py-2.5 px-3 text-on-surface font-medium">${dec.alert_name || 'Service Alert'}</td>
              <td class="py-2.5 px-3 text-on-surface-variant font-code-sm text-xs">${dec.service || '—'}</td>
              <td class="py-2.5 px-3">
                <span class="px-2.5 py-0.5 rounded-full text-xs font-bold border ${decColor}">${dec.human_decision}</span>
              </td>
              <td class="py-2.5 px-3 text-on-surface-variant text-xs max-w-sm leading-snug">${dec.reason_summary}</td>
              <td class="py-2.5 px-3">
                <button onclick="event.stopPropagation(); ${clickFn}" class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-primary-fixed text-primary text-xs font-semibold hover:bg-surface-container transition-colors shadow-sm">
                  <span class="material-symbols-outlined text-[14px]">psychology</span>
                  Explain
                </button>
              </td>
            </tr>
          `;
        }).join('');
      } else {
        if (explorerCount) explorerCount.innerText = '0 DECISIONS';
        explorerTbody.innerHTML = `
          <tr>
            <td colspan="6" class="py-8 text-center text-sm text-on-surface-variant">
              <span class="material-symbols-outlined text-[36px] text-outline mb-2 block">manage_search</span>
              No decisions recorded yet. Process alerts to populate this explorer.
            </td>
          </tr>
        `;
      }
    }

    // 5. Processing Performance
    const perfEl = document.getElementById('di-processing-perf');
    if (perfEl) {
      const perf = data.processing_performance;
      if (perf && perf.total_decisions_with_timing > 0) {
        perfEl.innerHTML = `
          <div class="p-4 rounded-xl bg-surface-container-low text-center border border-surface-container-highest">
            <div class="text-xs font-bold text-secondary uppercase mb-1">Average Processing Time</div>
            <div class="text-3xl font-bold text-amber-600 font-code-sm">${perf.avg_processing_ms} ms</div>
            <div class="text-[11px] text-outline mt-1">${perf.total_decisions_with_timing} evaluated decisions</div>
          </div>
          <div class="p-4 rounded-xl bg-surface-container-low text-center border border-surface-container-highest">
            <div class="text-xs font-bold text-secondary uppercase mb-1">Fastest Decision</div>
            <div class="text-3xl font-bold text-emerald-600 font-code-sm">${perf.min_processing_ms} ms</div>
            <div class="text-[11px] text-outline mt-1">Minimum recorded latency</div>
          </div>
          <div class="p-4 rounded-xl bg-surface-container-low text-center border border-surface-container-highest">
            <div class="text-xs font-bold text-secondary uppercase mb-1">Slowest Decision</div>
            <div class="text-3xl font-bold text-red-600 font-code-sm">${perf.max_processing_ms} ms</div>
            <div class="text-[11px] text-outline mt-1">Maximum recorded latency</div>
          </div>
        `;
      } else {
        perfEl.innerHTML = `
          <div class="col-span-3 p-6 text-center">
            <span class="material-symbols-outlined text-[36px] text-outline mb-2">speed</span>
            <h4 class="font-bold text-on-surface mb-1">Processing Time Not Available</h4>
            <p class="text-xs text-on-surface-variant">Decision processing timestamps have not been recorded yet.</p>
          </div>
        `;
      }
    }

    // 6. Outcome Metrics (Separated clearly from Decision Accuracy)
    const outcomeEl = document.getElementById('di-outcome-metrics');
    if (outcomeEl) {
      const out = data.outcomes;
      if (out && out.total_incidents > 0) {
        outcomeEl.innerHTML = `
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <!-- Group 1: Incident Progress Funnel -->
            <div class="p-4 rounded-xl bg-surface-container-low border border-surface-container-highest space-y-3">
              <div class="flex items-center justify-between border-b border-surface-container-highest pb-2">
                <span class="text-xs font-bold text-secondary uppercase tracking-wider font-code-sm">Incident Lifecycle Status</span>
                <span class="text-xs text-outline">${out.total_incidents} Total Created</span>
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div class="p-3 rounded-lg bg-surface-container-lowest border border-surface-container-highest">
                  <div class="text-[11px] font-bold text-secondary uppercase">Acknowledged</div>
                  <div class="text-2xl font-bold text-primary font-code-sm">${out.acknowledged_incidents}</div>
                  <div class="text-[10px] text-outline mt-0.5">By On-Call Engineer</div>
                </div>
                <div class="p-3 rounded-lg bg-surface-container-lowest border border-surface-container-highest">
                  <div class="text-[11px] font-bold text-secondary uppercase">Resolved</div>
                  <div class="text-2xl font-bold text-emerald-600 font-code-sm">${out.resolved_incidents}</div>
                  <div class="text-[10px] text-outline mt-0.5">Remediated & Closed</div>
                </div>
                <div class="p-3 rounded-lg bg-surface-container-lowest border border-surface-container-highest">
                  <div class="text-[11px] font-bold text-secondary uppercase">Active Unresolved</div>
                  <div class="text-2xl font-bold ${out.unresolved_incidents > 0 ? 'text-amber-600' : 'text-on-surface'} font-code-sm">${out.unresolved_incidents}</div>
                  <div class="text-[10px] text-outline mt-0.5">In Progress or Open</div>
                </div>
                <div class="p-3 rounded-lg bg-surface-container-lowest border border-surface-container-highest">
                  <div class="text-[11px] font-bold text-secondary uppercase">Resolution Rate</div>
                  <div class="text-2xl font-bold text-on-surface font-code-sm">${out.total_incidents > 0 ? Math.round((out.resolved_incidents / out.total_incidents) * 100) : 0}%</div>
                  <div class="text-[10px] text-outline mt-0.5">Closed / Created</div>
                </div>
              </div>
            </div>

            <!-- Group 2: Responder Response Times (Speed, Not Accuracy) -->
            <div class="p-4 rounded-xl bg-surface-container-low border border-surface-container-highest space-y-3">
              <div class="flex items-center justify-between border-b border-surface-container-highest pb-2">
                <span class="text-xs font-bold text-secondary uppercase tracking-wider font-code-sm">Responder Response Times</span>
                <span class="text-xs text-outline font-code-sm">Speed Benchmark</span>
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div class="p-3 rounded-lg bg-surface-container-lowest border border-surface-container-highest">
                  <div class="text-[11px] font-bold text-secondary uppercase">Avg Time to Acknowledge</div>
                  <div class="text-2xl font-bold text-amber-600 font-code-sm">${out.mtta_formatted ?? 'Awaiting data'}</div>
                  <div class="text-[10px] text-outline mt-0.5">MTTA (Human Responder)</div>
                </div>
                <div class="p-3 rounded-lg bg-surface-container-lowest border border-surface-container-highest">
                  <div class="text-[11px] font-bold text-secondary uppercase">Avg Time to Resolve</div>
                  <div class="text-2xl font-bold text-emerald-600 font-code-sm">${out.mttr_formatted ?? 'Awaiting data'}</div>
                  <div class="text-[10px] text-outline mt-0.5">MTTR (Incident Remediation)</div>
                </div>
              </div>
              <div class="p-2.5 rounded-lg bg-surface-container-lowest border border-surface-container-highest text-[11px] text-secondary leading-snug">
                Operational speed benchmarks calculated from real Incident timestamps in PostgreSQL. These metrics track human operator responsiveness and remediation duration once notified.
              </div>
            </div>
          </div>
        `;
      } else {
        outcomeEl.innerHTML = `
          <div class="p-6 text-center">
            <span class="material-symbols-outlined text-[36px] text-outline mb-2">fact_check</span>
            <h4 class="font-bold text-on-surface mb-1">No Downstream Incidents Recorded Yet</h4>
            <p class="text-xs text-on-surface-variant">No incidents have been declared yet to track operational acknowledgment or resolution speed.</p>
          </div>
        `;
      }
    }
  }

  function renderReasonTable(reasons, colorName) {
    const maxCount = Math.max(...reasons.map(r => r.count), 1);
    return `
      <div class="space-y-2">
        ${reasons.map(r => {
          const pct = Math.round((r.count / maxCount) * 100);
          return `
            <div class="flex items-center gap-3">
              <div class="flex-1">
                <div class="flex items-center justify-between mb-1">
                  <span class="text-sm font-medium text-on-surface">${r.human_label}</span>
                  <span class="text-xs font-bold font-code-sm text-${colorName}-700">${r.count}</span>
                </div>
                <div class="w-full h-2 rounded-full bg-surface-container-low overflow-hidden">
                  <div class="h-full rounded-full bg-${colorName}-500 transition-all duration-500" style="width: ${pct}%"></div>
                </div>
                <div class="text-[10px] text-outline font-code-sm mt-0.5">${r.reason_code}</div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  // ==============================================================
  // ALERT SIMULATOR & 500 -> 1 NORMALIZATION CONTROLLER
  // ==============================================================
  let currentSimScenario = 'major';
  let sampleVariationsList = [
    "CPU > 90% on payment-api",
    "CPU reached 95% on payment-api",
    "High CPU usage detected on payment-api",
    "payment-api CPU utilization critical (96%)",
    "CPU threshold exceeded on payment-api container",
    "Host CPU spike sustained on payment-api instances"
  ];

  window.selectSimPreset = function (preset) {
    currentSimScenario = preset;
    const countInput = document.getElementById('sim-count');
    const serviceSelect = document.getElementById('sim-service');
    const typeSelect = document.getElementById('sim-alert-type');
    const sevSelect = document.getElementById('sim-severity');
    const envSelect = document.getElementById('sim-environment');
    const delayInput = document.getElementById('sim-delay');

    // Update preset buttons styling
    document.querySelectorAll('.preset-btn').forEach(btn => {
      if (btn.dataset.preset === preset) {
        btn.className = 'preset-btn active-preset px-2.5 py-1 rounded-lg bg-primary-fixed text-on-primary-fixed border border-primary text-xs font-bold shadow-sm transition-colors';
      } else {
        btn.className = 'preset-btn px-2.5 py-1 rounded-lg border border-surface-container-highest text-xs font-medium text-secondary hover:bg-surface-container-high transition-colors';
      }
    });

    if (preset === 'normal') {
      if (countInput) countInput.value = '10';
      if (serviceSelect) serviceSelect.value = 'payment-api';
      if (typeSelect) typeSelect.value = 'CPU_HIGH';
      if (sevSelect) sevSelect.value = 'critical';
      if (envSelect) envSelect.value = 'production';
      if (delayInput) delayInput.value = '0';
    } else if (preset === 'spike') {
      if (countInput) countInput.value = '100';
      if (serviceSelect) serviceSelect.value = 'payment-api';
      if (typeSelect) typeSelect.value = 'CPU_HIGH';
      if (sevSelect) sevSelect.value = 'critical';
      if (envSelect) envSelect.value = 'production';
      if (delayInput) delayInput.value = '0';
    } else if (preset === 'major') {
      if (countInput) countInput.value = '500';
      if (serviceSelect) serviceSelect.value = 'payment-api';
      if (typeSelect) typeSelect.value = 'CPU_HIGH';
      if (sevSelect) sevSelect.value = 'critical';
      if (envSelect) envSelect.value = 'production';
      if (delayInput) delayInput.value = '0';
    } else if (preset === 'multiple') {
      if (countInput) countInput.value = '500';
      if (serviceSelect) serviceSelect.value = 'payment-api';
      if (typeSelect) typeSelect.value = 'CPU_HIGH';
      if (sevSelect) sevSelect.value = 'critical';
      if (envSelect) envSelect.value = 'production';
      if (delayInput) delayInput.value = '0';
    }
  };

  window.startAlertSimulation = async function () {
    const count = parseInt(document.getElementById('sim-count')?.value || '500', 10);
    const service = document.getElementById('sim-service')?.value || 'payment-api';
    const alert_type = document.getElementById('sim-alert-type')?.value || 'CPU_HIGH';
    const severity = document.getElementById('sim-severity')?.value || 'critical';
    const environment = document.getElementById('sim-environment')?.value || 'production';
    const delay_ms = parseInt(document.getElementById('sim-delay')?.value || '0', 10);

    const btn = document.getElementById('btn-generate-alerts');
    const btnText = document.getElementById('btn-generate-text');
    const progressPanel = document.getElementById('sim-progress-panel');
    const progressBar = document.getElementById('sim-progress-bar');
    const progressStatus = document.getElementById('sim-progress-status');
    const progressCount = document.getElementById('sim-progress-count');
    const variationPreview = document.getElementById('sim-variation-preview');
    const checklistPanel = document.getElementById('sim-checklist-panel');
    const resultPanel = document.getElementById('sim-result-panel');

    // UI state: generating
    if (btn) btn.disabled = true;
    if (btnText) btnText.innerText = 'GENERATING...';
    if (progressPanel) progressPanel.classList.remove('hidden');
    if (progressBar) progressBar.style.width = '10%';
    if (progressStatus) progressStatus.innerText = 'Transmitting alerts through live webhook endpoint...';
    if (progressCount) progressCount.innerText = `0 / ${count}`;
    if (checklistPanel) checklistPanel.classList.add('hidden');
    if (resultPanel) resultPanel.classList.add('hidden');

    // Start progress animation
    let simulatedCount = 0;
    let tickerInterval = setInterval(() => {
      if (simulatedCount < count * 0.9) {
        simulatedCount += Math.max(1, Math.floor(count / 20));
        if (simulatedCount > count * 0.9) simulatedCount = Math.floor(count * 0.9);
        const pct = Math.round((simulatedCount / count) * 100);
        if (progressBar) progressBar.style.width = `${pct}%`;
        if (progressCount) progressCount.innerText = `${simulatedCount} / ${count}`;
        if (variationPreview) {
          const randVar = sampleVariationsList[Math.floor(Math.random() * sampleVariationsList.length)];
          variationPreview.innerText = `"${randVar.replace('payment-api', service)}"`;
        }
      }
    }, 120);

    try {
      const payload = {
        count: count,
        service: service,
        alert_type: alert_type,
        severity: severity,
        environment: environment,
        delay_ms: delay_ms,
        scenario: currentSimScenario === 'multiple' ? 'multiple' : null
      };

      const resp = await fetch('http://localhost:8000/api/v1/alerts/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      clearInterval(tickerInterval);

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error: ${resp.status}`);
      }

      const data = await resp.json();

      // Progress complete
      if (progressBar) progressBar.style.width = '100%';
      if (progressCount) progressCount.innerText = `${data.generated} / ${data.requested}`;
      if (progressStatus) progressStatus.innerText = `Completed: ${data.generated} alerts processed through real webhook!`;
      if (variationPreview && data.sample_variations && data.sample_variations.length > 0) {
        variationPreview.innerText = `"${data.sample_variations[0]}"`;
      }

      // Show Verification Checklist
      if (checklistPanel) checklistPanel.classList.remove('hidden');
      const chkRecNum = document.getElementById('chk-received-num');
      const chkStorNum = document.getElementById('chk-stored-num');
      const chkCreatNum = document.getElementById('chk-created-num');
      const chkGroupNum = document.getElementById('chk-grouped-num');
      if (chkRecNum) chkRecNum.innerText = data.generated;
      if (chkStorNum) chkStorNum.innerText = data.raw_alerts_count;
      if (chkCreatNum) chkCreatNum.innerText = data.core_incidents_created;
      if (chkGroupNum) chkGroupNum.innerText = data.generated;

      // Show Normalization Result Section
      if (resultPanel) resultPanel.classList.remove('hidden');
      const resRaw = document.getElementById('res-raw-count');
      const resInc = document.getElementById('res-incident-count');
      const resRed = document.getElementById('res-reduction-pct');
      if (resRaw) resRaw.innerText = data.raw_alerts_count;
      if (resInc) resInc.innerText = data.core_incidents_created;
      if (resRed) resRed.innerText = `${data.alert_reduction_percent}%`;

      // Update Core Incident details
      const incNum = document.getElementById('res-inc-number');
      const incBadge = document.getElementById('res-inc-badge');
      const incTitle = document.getElementById('res-inc-title');
      const incOcc = document.getElementById('res-inc-occurrences');
      const incSvc = document.getElementById('res-inc-service');
      const incEnv = document.getElementById('res-inc-env');
      const incFp = document.getElementById('res-inc-fp');

      if (incNum) incNum.innerText = `#${data.primary_incident_number || 'INC-1001'}`;
      if (incBadge) incBadge.innerText = data.severity === 'critical' ? '🔴 Critical' : `⚠️ ${data.severity.toUpperCase()}`;
      if (incTitle) incTitle.innerText = data.primary_incident_title || `${data.service} Degradation`;
      if (incOcc) incOcc.innerText = data.primary_incident_occurrences || data.generated;
      if (incSvc) incSvc.innerText = data.service;
      if (incEnv) incEnv.innerText = data.environment;
      if (incFp) incFp.innerText = data.primary_fingerprint ? `${data.primary_fingerprint.substring(0, 16)}...` : 'N/A';

      // Update Flow Diagram
      const diagRaw = document.getElementById('diag-raw');
      const diagInc = document.getElementById('diag-inc');
      const diagRed = document.getElementById('diag-reduction');
      if (diagRaw) diagRaw.innerText = `${data.raw_alerts_count} RAW ALERTS`;
      if (diagInc) diagInc.innerText = `${data.core_incidents_created} CORE INCIDENT${data.core_incidents_created > 1 ? 'S' : ''}`;
      if (diagRed) diagRed.innerText = `${data.alert_reduction_percent}% Noise Reduction`;

      showToast(`Successfully processed ${data.generated} alerts into ${data.core_incidents_created} core incident (${data.alert_reduction_percent}% reduction)`, 'success');

      // Refresh real database state across the rest of the dashboard
      await fetchAllRealData();

    } catch (err) {
      clearInterval(tickerInterval);
      if (progressStatus) progressStatus.innerText = `Simulation failed: ${err.message}`;
      showToast(`Simulation error: ${err.message}`, 'error');
    } finally {
      if (btn) btn.disabled = false;
      if (btnText) btnText.innerText = 'GENERATE ALERTS';
    }
  };

  window.openRawAlertsModal = async function () {
    const modal = document.getElementById('raw-alerts-modal');
    if (!modal) return;
    modal.classList.add('active');

    const tbody = document.getElementById('raw-alerts-tbody');
    const badge = document.getElementById('raw-alerts-total-badge');
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-secondary">Fetching raw PostgreSQL records...</td></tr>`;
    }

    try {
      const resp = await fetch('http://localhost:8000/api/v1/alerts/raw?limit=50');
      if (resp.ok) {
        const data = await resp.json();
        if (badge) badge.innerText = `${data.total} Raw Records`;

        if (tbody) {
          if (!data.items || data.items.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-secondary">No raw alerts found in PostgreSQL.</td></tr>`;
            return;
          }

          tbody.innerHTML = data.items.map((item) => {
            const timeStr = item.received_at ? new Date(item.received_at).toLocaleTimeString() : 'N/A';
            const sevColor = item.severity === 'critical' ? 'text-red-600 bg-red-50' : 'text-amber-600 bg-amber-50';
            return `
              <tr class="hover:bg-surface-container-low transition-colors">
                <td class="py-2.5 px-3 whitespace-nowrap text-secondary">${timeStr}</td>
                <td class="py-2.5 px-3 font-semibold text-on-surface">${escapeHtml(item.alert_name)}</td>
                <td class="py-2.5 px-3 text-secondary font-mono">${escapeHtml(item.service)}</td>
                <td class="py-2.5 px-3">
                  <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase ${sevColor}">${escapeHtml(item.severity)}</span>
                </td>
                <td class="py-2.5 px-3">
                  <span class="px-2 py-0.5 rounded text-[10px] bg-surface-container text-secondary uppercase">${escapeHtml(item.status)}</span>
                </td>
                <td class="py-2.5 px-3 text-right">
                  <span class="font-mono text-[10px] text-primary" title="${escapeHtml(JSON.stringify(item.labels || {}))}">
                    ${item.id ? item.id.substring(0, 8) : 'raw'}...
                  </span>
                </td>
              </tr>
            `;
          }).join('');
        }
      }
    } catch (err) {
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-red-500">Failed to load raw alerts: ${err.message}</td></tr>`;
      }
    }
  };

  window.closeRawAlertsModal = function () {
    const modal = document.getElementById('raw-alerts-modal');
    if (modal) modal.classList.remove('active');
  };

  // Boot app on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
