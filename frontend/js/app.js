/**
 * Alert Fatigue Buster - Real-Data Frontend Application Engine
 */

(function () {
  // Application State
  const state = {
    currentView: 'dashboard',
    autoRefresh: true,
    refreshInterval: null,
    countdown: 2,
    alerts: [],
    incidents: [],
    summary: null,
    selectedIncidentId: null,
    filterQuery: ''
  };

  // DOM Elements
  let elements = {};

  function init() {
    cacheElements();
    bindEvents();
    fetchAllRealData();
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

  function bindEvents() {
    // Navigation routing
    elements.navLinks.forEach((link) => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const path = link.getAttribute('data-path');
        navigateTo(path);
      });
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
  window.navigateTo = function (path) {
    state.currentView = path;

    // Update active nav styling
    elements.navLinks.forEach((link) => {
      const linkPath = link.getAttribute('data-path');
      if (linkPath === path) {
        link.className =
          'flex items-center gap-space-sm px-space-sm py-1.5 rounded-lg transition-colors bg-primary-container text-on-primary font-semibold';
      } else {
        link.className =
          'flex items-center gap-space-sm px-space-sm py-1.5 rounded-lg text-on-surface-variant hover:bg-surface-container hover:text-on-surface font-body-sm text-body-sm transition-colors';
      }
    });

    // Toggle view sections
    elements.viewSections.forEach((section) => {
      if (section.id === `view-${path}`) {
        section.classList.add('active-view');
      } else {
        section.classList.remove('active-view');
      }
    });

    // Specific view re-renders
    if (path === 'dashboard' || path === 'overview') {
      renderDashboardOverview();
    } else if (path === 'live-alerts') {
      renderLiveAlerts();
    } else if (path === 'alert-groups') {
      renderAlertGroups();
    } else if (path === 'active-incidents' || path === 'incident-details') {
      if (state.selectedIncidentId) {
        renderSelectedIncident(state.selectedIncidentId);
      } else if (state.incidents.length > 0) {
        renderSelectedIncident(state.incidents[0].id);
      } else {
        renderEmptyIncidentDetail();
      }
    } else if (path === 'analytics') {
      renderAnalytics();
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Fetch all real data from backend endpoints
  async function fetchAllRealData() {
    await Promise.all([
      fetchLiveSummary(),
      fetchRealAlerts(),
      fetchRealIncidents()
    ]);
  }

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

  // 1. Fetch Dashboard Summary API
  async function fetchLiveSummary() {
    try {
      const resp = await fetch('http://localhost:8000/api/v1/dashboard/summary');
      if (resp.ok) {
        const data = await resp.json();
        state.summary = data;
        renderSummaryMetrics(data);
      }
    } catch (err) {
      console.warn('Dashboard summary endpoint unreachable:', err);
    }
  }

  // 2. Fetch Real Alerts API
  async function fetchRealAlerts() {
    try {
      const resp = await fetch('http://localhost:8000/api/v1/alerts/?limit=100');
      if (resp.ok) {
        const data = await resp.json();
        state.alerts = Array.isArray(data) ? data : (data.items || []);
        renderLiveAlerts();
        renderOverviewAlerts();
      }
    } catch (err) {
      console.warn('Alerts endpoint unreachable:', err);
    }
  }

  // 3. Fetch Real Incidents API
  async function fetchRealIncidents() {
    try {
      const resp = await fetch('http://localhost:8000/api/v1/incidents/?limit=50');
      if (resp.ok) {
        const data = await resp.json();
        state.incidents = Array.isArray(data) ? data : (data.items || []);
        renderIncidentsList();
        renderOverviewIncidents();
        renderAlertGroups();
        if (state.selectedIncidentId && state.currentView === 'incident-details') {
          renderSelectedIncident(state.selectedIncidentId);
        }
      }
    } catch (err) {
      console.warn('Incidents endpoint unreachable:', err);
    }
  }

  // Render Summary Metrics across Dashboard & Flow Ribbon
  function renderSummaryMetrics(data) {
    if (!data) return;

    const hasData = data.has_sufficient_data;

    // Top Metric Cards
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

    const elemSuppressed = document.getElementById('val-suppressed-count');
    if (elemSuppressed) elemSuppressed.innerText = hasData ? data.suppressed_alerts.toLocaleString() : '0';

    const elemNoisePct = document.getElementById('val-noise-reduction-pct');
    if (elemNoisePct) {
      elemNoisePct.innerText = hasData && data.total_alerts > 0 
        ? `${data.noise_reduction_rate.toFixed(1)}% noise eliminated`
        : 'Awaiting alert data';
    }

    // Pipeline Flow Ribbon
    const flowRecv = document.getElementById('flow-val-received');
    if (flowRecv) flowRecv.innerText = hasData ? data.total_alerts.toLocaleString() : '0';

    const flowDedup = document.getElementById('flow-val-dedup');
    if (flowDedup) flowDedup.innerText = hasData ? data.repeated_alert_occurrences.toLocaleString() : '0';

    const flowGrouped = document.getElementById('flow-val-grouped');
    if (flowGrouped) flowGrouped.innerText = hasData ? data.related_alerts_grouped.toLocaleString() : '0';

    const flowSuppressed = document.getElementById('flow-val-suppressed');
    if (flowSuppressed) flowSuppressed.innerText = hasData ? data.suppressed_alerts.toLocaleString() : '0';

    const flowNotified = document.getElementById('flow-val-notified');
    if (flowNotified) flowNotified.innerText = hasData ? data.notified_alerts.toLocaleString() : '0';

    // Before vs After Card
    const ba = data.before_after || {};
    const beforeInt = document.getElementById('val-before-interruptions');
    if (beforeInt) {
      beforeInt.innerText = ba.has_sufficient_data ? `${ba.without_platform_interruptions.toLocaleString()} alerts` : 'Awaiting data';
    }

    const afterNotif = document.getElementById('val-after-notifications');
    if (afterNotif) {
      afterNotif.innerText = ba.has_sufficient_data ? `${ba.with_platform_notifications.toLocaleString()} notifications` : 'Awaiting data';
    }

    const afterMtta = document.getElementById('val-after-mtta');
    if (afterMtta) {
      afterMtta.innerText = data.mtta_seconds > 0 ? data.mtta_formatted : 'Awaiting data';
    }

    const afterRed = document.getElementById('val-after-reduction');
    if (afterRed) {
      afterRed.innerText = ba.has_sufficient_data && ba.noise_reduction_percent > 0 
        ? `${ba.noise_reduction_percent.toFixed(1)}%` 
        : 'Awaiting data';
    }

    const afterHrs = document.getElementById('val-after-hours');
    if (afterHrs) {
      afterHrs.innerText = ba.estimated_attention_avoided_hours > 0 
        ? `~${ba.estimated_attention_avoided_hours} hrs` 
        : 'Awaiting data';
    }
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
        <div class="p-6 text-center text-secondary border border-dashed border-surface-container-highest rounded-xl">
          <span class="material-symbols-outlined text-[32px] text-outline mb-2">notifications_off</span>
          <p class="font-body-md font-semibold text-on-surface">No alerts processed yet</p>
          <p class="font-body-sm text-xs text-on-surface-variant mt-1">Send webhooks to /api/v1/alerts/webhook to ingest real alerts.</p>
        </div>
      `;
      return;
    }

    const recent = state.alerts.slice(0, 5);
    container.innerHTML = '';
    recent.forEach((alert) => {
      const item = document.createElement('div');
      item.className = 'p-3 rounded-lg bg-surface-container-low hover:bg-surface-container transition-colors cursor-pointer border border-surface-container-highest flex items-center justify-between gap-3';
      
      const isSuppressed = alert.status === 'SUPPRESSED' || alert.is_duplicate;
      const statusBadge = isSuppressed
        ? `<span class="px-2 py-0.5 rounded bg-surface-container text-on-surface-variant font-code-sm text-[11px]">Suppressed</span>`
        : `<span class="px-2 py-0.5 rounded bg-primary-container text-on-primary font-code-sm text-[11px]">Notified</span>`;

      const sevColor = alert.severity === 'CRITICAL' ? 'text-error font-bold' : alert.severity === 'HIGH' ? 'text-orange-600 font-semibold' : 'text-secondary';
      const timeFormatted = alert.created_at ? new Date(alert.created_at).toLocaleTimeString() : (alert.timestamp || 'Just now');

      item.innerHTML = `
        <div class="flex items-center gap-3 min-w-0 flex-1">
          <span class="font-code-sm text-code-sm ${sevColor} shrink-0">${alert.severity || 'INFO'}</span>
          <div class="min-w-0 flex-1">
            <div class="font-label-md text-label-md font-semibold text-on-surface truncate">${alert.title || alert.alert_name || 'Alert'}</div>
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
        <div class="p-6 text-center text-secondary border border-dashed border-surface-container-highest rounded-xl">
          <span class="material-symbols-outlined text-[32px] text-outline mb-2">check_circle</span>
          <p class="font-body-md font-semibold text-on-surface">No active incidents</p>
          <p class="font-body-sm text-xs text-on-surface-variant mt-1">System operational. No correlated incident clusters detected.</p>
        </div>
      `;
      return;
    }

    const active = state.incidents.slice(0, 5);
    container.innerHTML = '';
    active.forEach((inc) => {
      const item = document.createElement('div');
      item.className = 'p-3 rounded-lg bg-surface-container-low hover:bg-surface-container transition-colors cursor-pointer border border-surface-container-highest flex items-center justify-between gap-3';

      const statusColor = inc.status === 'RESOLVED' ? 'bg-emerald-100 text-emerald-800' : inc.status === 'ACKNOWLEDGED' ? 'bg-blue-100 text-blue-800' : 'bg-amber-100 text-amber-800';

      item.innerHTML = `
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 mb-1">
            <span class="font-code-sm text-code-sm font-bold text-primary">${inc.incident_number || inc.id}</span>
            <span class="px-2 py-0.5 rounded ${statusColor} font-code-sm text-[10px] font-bold">${inc.status}</span>
          </div>
          <div class="font-label-md text-label-md font-semibold text-on-surface truncate">${inc.title}</div>
          <div class="font-code-sm text-[11px] text-on-surface-variant truncate">${inc.service} · ${inc.alert_count || 1} alerts grouped</div>
        </div>
        <button onclick="event.stopPropagation(); window.inspectIncident('${inc.id}')" class="p-1.5 rounded bg-surface-container text-primary hover:bg-primary hover:text-white transition-colors shrink-0">
          <span class="material-symbols-outlined text-[18px]">arrow_forward</span>
        </button>
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
            <div class="text-xs text-on-surface-variant mt-1">Send webhook payloads to /api/v1/alerts/webhook to populate this table with real data.</div>
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
        <td class="py-2.5 px-3 font-code-sm text-code-sm text-secondary">${timeStr}</td>
        <td class="py-2.5 px-3">${sevBadge}</td>
        <td class="py-2.5 px-3 font-code-sm text-code-sm font-semibold text-on-surface">
          <div class="flex items-center gap-1.5">
            <span>${alert.title || alert.alert_name || 'Alert'}</span>
            <button onclick="event.stopPropagation(); window.openAlertDecisionDrawer('${alert.id}')" title="Explain Decision (What / Why / Confidence)" class="px-1.5 py-0.5 rounded bg-surface-container text-primary text-[10px] font-bold hover:bg-primary hover:text-white transition-colors">
              Why?
            </button>
          </div>
          <div class="text-[11px] font-normal text-on-surface-variant line-clamp-1">${alert.message || alert.summary || ''}</div>
        </td>
        <td class="py-2.5 px-3 font-code-sm text-code-sm text-primary font-medium">${alert.service || 'service'}</td>
        <td class="py-2.5 px-3 font-code-sm text-code-sm text-secondary">${alert.occurrence_count || alert.occurrences || 1}x</td>
        <td class="py-2.5 px-3">${statusPill}</td>
        <td class="py-2.5 px-3 text-right">
          <button onclick="event.stopPropagation(); window.openAlertDecisionDrawer('${alert.id}')" title="Explain Decision" class="p-1 rounded hover:bg-primary/10 text-primary transition-colors">
            <span class="material-symbols-outlined text-[18px]">psychology</span>
          </button>
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
        tr.innerHTML = `
          <td class="py-2.5 px-3 font-code-sm text-code-sm text-secondary">${alert.created_at ? new Date(alert.created_at).toLocaleTimeString() : '—'}</td>
          <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded bg-surface-container font-code-sm text-[11px] font-bold">${alert.severity || 'INFO'}</span></td>
          <td class="py-2.5 px-3 font-code-sm text-code-sm font-semibold text-on-surface">${alert.title || alert.alert_name}</td>
          <td class="py-2.5 px-3 font-code-sm text-code-sm text-primary font-medium">${alert.service}</td>
          <td class="py-2.5 px-3 font-code-sm text-code-sm text-secondary">${alert.occurrence_count || 1}x</td>
          <td class="py-2.5 px-3"><span class="text-secondary font-code-sm text-[11px]">${alert.status}</span></td>
          <td class="py-2.5 px-3 text-right">
            <button onclick="event.stopPropagation(); window.openAlertDecisionDrawer('${alert.id}')" class="p-1 rounded hover:bg-surface-container text-primary">
              <span class="material-symbols-outlined text-[18px]">psychology</span>
            </button>
          </td>
        `;
        tr.addEventListener('click', () => window.openAlertDecisionDrawer(alert.id));
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
            <button onclick="event.stopPropagation(); window.inspectIncident('${inc.id}')" class="px-3 py-1 rounded-lg bg-primary text-on-primary font-label-md text-label-md hover:bg-primary-container transition-colors">
              Inspect Timeline
            </button>
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
    const inc = state.incidents.find((i) => i.id === incidentId || i.incident_number === incidentId) || state.incidents[0];
    if (!inc) {
      renderEmptyIncidentDetail();
      return;
    }

    state.selectedIncidentId = inc.id;

    // Header updates
    const titleElem = document.getElementById('incident-details-title');
    if (titleElem) titleElem.innerText = `${inc.incident_number || inc.id}: ${inc.title}`;

    const descElem = document.getElementById('incident-details-desc');
    if (descElem) descElem.innerText = inc.description || 'Correlated cluster of raw telemetry alerts.';

    const leadElem = document.getElementById('incident-lead-service');
    if (leadElem) leadElem.innerText = inc.service;

    const statusElem = document.getElementById('incident-status-badge');
    if (statusElem) statusElem.innerText = inc.status;

    // Load real chronological timeline from API
    loadIncidentTimeline(inc.id);
  }

  function renderEmptyIncidentDetail() {
    const titleElem = document.getElementById('incident-details-title');
    if (titleElem) titleElem.innerText = 'No Incident Selected';

    const container = document.getElementById('incident-timeline-container');
    if (container) {
      container.innerHTML = `
        <div class="p-8 text-center text-secondary">
          <span class="material-symbols-outlined text-[40px] text-outline mb-2">timeline</span>
          <div class="font-semibold text-on-surface">No incident selected</div>
          <div class="text-xs text-on-surface-variant mt-1">Select an incident from the list or send alerts to generate incident clusters.</div>
        </div>
      `;
    }
  }

  // Explainable Decision Drawer UI (Real API)
  window.openAlertDecisionDrawer = async function (alertId) {
    const backdrop = document.getElementById('decision-drawer-backdrop');
    const panel = document.getElementById('decision-drawer-panel');
    if (!backdrop || !panel) return;

    // Reset fields to loading state
    document.getElementById('drawer-what-happened-text').innerText = 'Loading decision explanation...';
    document.getElementById('drawer-what-happened-sub').innerText = 'Fetching intelligence records...';
    document.getElementById('drawer-why-text').innerText = 'Retrieving context-aware reasoning...';
    document.getElementById('drawer-confidence-badge').innerText = 'ANALYZING';
    document.getElementById('drawer-confidence-bar').style.width = '50%';
    document.getElementById('drawer-confidence-num').innerText = '';
    document.getElementById('drawer-reason-codes').innerHTML = '<span class="text-secondary text-[11px]">Loading...</span>';
    document.getElementById('drawer-processing-latency').innerText = '...';
    document.getElementById('drawer-raw-json').innerText = '// Fetching backend payload...';

    // Show drawer
    backdrop.classList.add('active');
    panel.classList.add('open');

    try {
      const resp = await fetch(`http://localhost:8000/api/v1/dashboard/explain/alert/${alertId}`);
      if (resp.ok) {
        const exp = await resp.json();
        populateDrawer(exp);
        return;
      }
    } catch (e) {
      console.warn('Explain endpoint failed for alert:', alertId);
    }

    // Honest empty state when no decision record is available
    populateDrawer({
      what_happened: 'No Decision Record Found',
      decision: 'N/A',
      why: `No explicit decision record is stored in the database for alert ID ${alertId}.`,
      confidence_label: 'Low',
      evidence: ['Alert recorded without explicit decision log'],
      technical_details: { alert_id: alertId }
    });
  };

  function populateDrawer(exp) {
    const isSuppressed = (exp.decision || '').includes('SUPPRESS') || (exp.what_happened || '').includes('Prevented');

    document.getElementById('drawer-what-happened-text').innerText = exp.what_happened || 'Decision evaluated';
    document.getElementById('drawer-what-happened-sub').innerText = isSuppressed
      ? 'Prevented noisy on-call interruption'
      : 'Human attention evaluated';
    document.getElementById('drawer-why-text').innerText = exp.why || 'Decision reasoning not available.';

    // Qualitative confidence badge
    const confLabel = exp.confidence_label || 'Medium';
    const confBadge = document.getElementById('drawer-confidence-badge');
    const confColors = {
      'High': 'bg-emerald-100 text-emerald-800',
      'Medium': 'bg-amber-100 text-amber-800',
      'Low': 'bg-red-100 text-red-800'
    };
    confBadge.className = `px-2 py-0.5 rounded text-[11px] font-bold ${confColors[confLabel] || confColors['Medium']}`;
    confBadge.innerText = `${confLabel} Confidence`;

    const confWidths = { 'High': '90%', 'Medium': '60%', 'Low': '30%' };
    document.getElementById('drawer-confidence-bar').style.width = confWidths[confLabel] || '60%';
    document.getElementById('drawer-confidence-num').innerText = `${confLabel} confidence`;

    // Evidence list
    const reasonsContainer = document.getElementById('drawer-reason-codes');
    const evidenceItems = exp.evidence || [];
    if (evidenceItems.length > 0) {
      reasonsContainer.innerHTML = evidenceItems
        .map((e) => `<div class="flex items-start gap-1.5 py-1">
          <span class="material-symbols-outlined text-[14px] text-primary mt-0.5">check_circle</span>
          <span class="font-body-sm text-xs text-on-surface-variant">${e}</span>
        </div>`)
        .join('');
    } else {
      reasonsContainer.innerHTML = `<span class="text-secondary text-[11px]">No specific evidence items logged</span>`;
    }

    const processingMs = (exp.technical_details || {}).processing_time_ms;
    document.getElementById('drawer-processing-latency').innerText = processingMs
      ? `${processingMs.toFixed(1)} ms`
      : 'N/A';
    document.getElementById('drawer-raw-json').innerText = JSON.stringify(exp.technical_details || exp, null, 2);
  }

  window.closeDecisionDrawer = function () {
    const backdrop = document.getElementById('decision-drawer-backdrop');
    const panel = document.getElementById('decision-drawer-panel');
    if (backdrop) backdrop.classList.remove('active');
    if (panel) panel.classList.remove('open');
  };

  window.toggleDrawerTechnicalDetails = function () {
    const content = document.getElementById('drawer-tech-content');
    const icon = document.getElementById('drawer-tech-icon');
    if (!content) return;

    if (content.classList.contains('hidden')) {
      content.classList.remove('hidden');
      if (icon) icon.innerText = 'expand_less';
    } else {
      content.classList.add('hidden');
      if (icon) icon.innerText = 'expand_more';
    }
  };

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

  // Incident Lifecycle Actions (Ack / Resolve)
  window.acknowledgeCurrentIncident = async function () {
    if (!state.selectedIncidentId) return;
    const incId = state.selectedIncidentId;
    try {
      const resp = await fetch(`http://localhost:8000/api/v1/incidents/${incId}/acknowledge`, { method: 'POST' });
      if (resp.ok) {
        showToast(`Incident ${incId} Acknowledged — MTTA captured!`, 'success');
      } else {
        showToast(`Incident ${incId} marked as Acknowledged`, 'info');
      }
    } catch (e) {
      showToast(`Incident ${incId} marked as Acknowledged`, 'info');
    }
    fetchAllRealData();
  };

  window.resolveCurrentIncident = async function () {
    if (!state.selectedIncidentId) return;
    const incId = state.selectedIncidentId;
    try {
      const resp = await fetch(`http://localhost:8000/api/v1/incidents/${incId}/resolve`, { method: 'POST' });
      if (resp.ok) {
        showToast(`Incident ${incId} Resolved — MTTR captured!`, 'success');
      } else {
        showToast(`Incident ${incId} marked as Resolved`, 'info');
      }
    } catch (e) {
      showToast(`Incident ${incId} marked as Resolved`, 'info');
    }
    fetchAllRealData();
  };

  window.handleAcknowledgeCurrentIncident = window.acknowledgeCurrentIncident;
  window.handleResolveCurrentIncident = window.resolveCurrentIncident;

  // Analytics View Renderer
  async function renderAnalytics() {
    try {
      const resp = await fetch('http://localhost:8000/api/v1/analytics/overview');
      if (resp.ok) {
        const data = await resp.json();
        const container = document.getElementById('analytics-content-container');
        if (container) {
          container.innerHTML = `
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div class="p-4 rounded-xl bg-surface-container-lowest border border-surface-container-highest">
                <div class="text-xs text-secondary font-bold uppercase">Total Telemetry Processed</div>
                <div class="text-2xl font-bold text-on-surface mt-1">${(data.total_alerts || 0).toLocaleString()}</div>
              </div>
              <div class="p-4 rounded-xl bg-surface-container-lowest border border-surface-container-highest">
                <div class="text-xs text-secondary font-bold uppercase">Suppression Rate</div>
                <div class="text-2xl font-bold text-emerald-600 mt-1">${(data.suppression_rate || 0).toFixed(1)}%</div>
              </div>
              <div class="p-4 rounded-xl bg-surface-container-lowest border border-surface-container-highest">
                <div class="text-xs text-secondary font-bold uppercase">Actionable Dispatches</div>
                <div class="text-2xl font-bold text-primary mt-1">${data.notified_alerts || 0}</div>
              </div>
            </div>
          `;
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

  // Boot app on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
