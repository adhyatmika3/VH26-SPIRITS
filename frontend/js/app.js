/**
 * Alert Fatigue Buster - Frontend Application Core
 */

(function () {
  // Application State
  const state = {
    currentView: 'dashboard',
    autoRefresh: true,
    refreshInterval: null,
    countdown: 2,
    alerts: [...window.ALERT_DATA.alerts],
    alertGroups: [...window.ALERT_DATA.alertGroups],
    incidents: [...window.ALERT_DATA.incidents],
    stats: { ...window.ALERT_DATA.stats },
    selectedIncidentId: 'INC-1042',
    filterQuery: ''
  };

  // DOM Elements
  let elements = {};

  function init() {
    cacheElements();
    bindEvents();
    renderStats();
    renderLiveAlerts();
    renderAlertGroups();
    renderIncidentsList();
    renderSelectedIncident(state.selectedIncidentId);
    fetchLiveAnalytics();
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
      alertGroupsContainer: document.getElementById('alert-groups-container'),
      toastContainer: document.getElementById('toast-container'),
      newIncidentModal: document.getElementById('new-incident-modal'),
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

    // New Incident Form Submission
    const newIncidentForm = document.getElementById('new-incident-form');
    if (newIncidentForm) {
      newIncidentForm.addEventListener('submit', (e) => {
        e.preventDefault();
        createNewIncidentFromForm();
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

    // Specific view actions
    if (path === 'dashboard' || path === 'overview') {
      renderStats();
    } else if (path === 'live-alerts') {
      renderLiveAlerts();
    } else if (path === 'alert-groups') {
      renderAlertGroups();
    } else if (path === 'active-incidents' || path === 'incident-details') {
      renderSelectedIncident(state.selectedIncidentId);
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Telemetry KPIs Rendering
  function renderStats() {
    if (elements.valIncoming) {
      elements.valIncoming.innerText = state.stats.incomingAlerts.toLocaleString();
    }
    if (elements.valActionable) {
      elements.valActionable.innerText = state.stats.actionableAlerts.toLocaleString();
    }

    // Dynamic IDs across overview and live stream
    const elemIngress = document.getElementById('val-ingress-velocity');
    if (elemIngress) elemIngress.innerText = state.stats.ingressVelocity.toFixed(1);

    const elemFatigue = document.getElementById('val-fatigue-absorb');
    if (elemFatigue) elemFatigue.innerText = `${state.stats.fatigueAbsorptionPercent.toFixed(1)}%`;

    const elemDedupe = document.getElementById('val-dedupe-pool');
    if (elemDedupe) elemDedupe.innerText = state.stats.activeDedupePool;
  }

  // Live Alerts Table Rendering
  function renderLiveAlerts() {
    if (!elements.alertsTableBody) return;

    elements.alertsTableBody.innerHTML = '';
    state.alerts.forEach((alert) => {
      const tr = document.createElement('tr');
      tr.className =
        'hover:bg-surface-container-low transition-colors border-b border-surface-container-high group cursor-pointer';
      tr.id = `row-${alert.id}`;

      // Severity badge styling
      let sevBadge = '';
      if (alert.severity === 'CRITICAL') {
        sevBadge = `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-error-container text-on-error-container font-code-sm text-code-sm font-semibold"><span class="w-1.5 h-1.5 rounded-full bg-error animate-pulse"></span>CRIT</span>`;
      } else if (alert.severity === 'HIGH') {
        sevBadge = `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-orange-100 text-orange-800 font-code-sm text-code-sm font-semibold"><span class="w-1.5 h-1.5 rounded-full bg-orange-500"></span>HIGH</span>`;
      } else if (alert.severity === 'MEDIUM') {
        sevBadge = `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-100 text-amber-800 font-code-sm text-code-sm font-semibold"><span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>MED</span>`;
      } else {
        sevBadge = `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-blue-100 text-blue-800 font-code-sm text-code-sm font-semibold"><span class="w-1.5 h-1.5 rounded-full bg-blue-500"></span>INFO</span>`;
      }

      // Actionable status pill
      let statusPill = '';
      if (alert.suppressed) {
        statusPill = `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-surface-container text-on-surface-variant font-code-sm text-[11px]"><span class="material-symbols-outlined text-[13px]">filter_alt_off</span>Suppressed</span>`;
      } else if (alert.actionable) {
        statusPill = `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-primary-container text-on-primary font-code-sm text-[11px] font-medium"><span class="material-symbols-outlined text-[13px]">bolt</span>Actionable</span>`;
      } else {
        statusPill = `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-surface-container-high text-secondary font-code-sm text-[11px]">Batched</span>`;
      }

      tr.innerHTML = `
        <td class="py-2.5 px-3 font-code-sm text-code-sm text-secondary">${alert.timestamp}</td>
        <td class="py-2.5 px-3">${sevBadge}</td>
        <td class="py-2.5 px-3 font-code-sm text-code-sm font-semibold text-on-surface">
          ${alert.title}
          <div class="text-[11px] font-normal text-on-surface-variant line-clamp-1">${alert.message}</div>
        </td>
        <td class="py-2.5 px-3 font-code-sm text-code-sm text-primary font-medium">${alert.service}</td>
        <td class="py-2.5 px-3 font-code-sm text-code-sm text-secondary">${alert.occurrences}x</td>
        <td class="py-2.5 px-3">${statusPill}</td>
        <td class="py-2.5 px-3 text-right">
          <div class="flex items-center justify-end gap-1 opacity-80 group-hover:opacity-100">
            <button onclick="event.stopPropagation(); window.acknowledgeAlert('${alert.id}')" title="Acknowledge Alert" class="p-1 rounded hover:bg-surface-container text-secondary hover:text-primary transition-colors">
              <span class="material-symbols-outlined text-[18px]">check_circle</span>
            </button>
            <button onclick="event.stopPropagation(); window.suppressAlert('${alert.id}')" title="Suppress Fingerprint" class="p-1 rounded hover:bg-surface-container text-secondary hover:text-error transition-colors">
              <span class="material-symbols-outlined text-[18px]">do_not_disturb_on</span>
            </button>
            <button onclick="event.stopPropagation(); window.drillDownAlert('${alert.group || alert.id}')" title="Investigate Incident" class="p-1 rounded hover:bg-surface-container text-secondary hover:text-primary transition-colors">
              <span class="material-symbols-outlined text-[18px]">arrow_forward</span>
            </button>
          </div>
        </td>
      `;

      tr.addEventListener('click', () => {
        window.drillDownAlert(alert.group || 'GRP-DB-POOL-01');
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
      return (
        a.title.toLowerCase().includes(state.filterQuery) ||
        a.service.toLowerCase().includes(state.filterQuery) ||
        a.message.toLowerCase().includes(state.filterQuery) ||
        a.severity.toLowerCase().includes(state.filterQuery)
      );
    });

    if (elements.alertsTableBody) {
      elements.alertsTableBody.innerHTML = '';
      if (filtered.length === 0) {
        elements.alertsTableBody.innerHTML = `<tr><td colspan="7" class="py-8 text-center text-secondary font-body-md">No telemetry alerts match "${state.filterQuery}"</td></tr>`;
        return;
      }
      filtered.forEach((alert) => {
        // Reuse row rendering
        const tr = document.createElement('tr');
        tr.className =
          'hover:bg-surface-container-low transition-colors border-b border-surface-container-high group cursor-pointer';
        tr.innerHTML = `
          <td class="py-2.5 px-3 font-code-sm text-code-sm text-secondary">${alert.timestamp}</td>
          <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded bg-surface-container font-code-sm text-[11px] font-bold">${alert.severity}</span></td>
          <td class="py-2.5 px-3 font-code-sm text-code-sm font-semibold text-on-surface">${alert.title}</td>
          <td class="py-2.5 px-3 font-code-sm text-code-sm text-primary font-medium">${alert.service}</td>
          <td class="py-2.5 px-3 font-code-sm text-code-sm text-secondary">${alert.occurrences}x</td>
          <td class="py-2.5 px-3"><span class="text-secondary font-code-sm text-[11px]">${alert.status}</span></td>
          <td class="py-2.5 px-3 text-right">
            <button onclick="event.stopPropagation(); window.drillDownAlert('${alert.group || alert.id}')" class="p-1 rounded hover:bg-surface-container text-primary">
              <span class="material-symbols-outlined text-[18px]">arrow_forward</span>
            </button>
          </td>
        `;
        elements.alertsTableBody.appendChild(tr);
      });
    }
  }

  // Render Alert Groups
  function renderAlertGroups() {
    const container = document.getElementById('alert-groups-list');
    if (!container) return;

    container.innerHTML = '';
    state.alertGroups.forEach((group) => {
      const card = document.createElement('div');
      const isCrit = group.highestSeverity === 'CRITICAL';
      card.className = `p-space-base bg-surface-container-lowest rounded-xl shadow-sm border-l-4 ${
        isCrit ? 'border-l-error' : 'border-l-primary'
      } hover:shadow-md transition-all cursor-pointer`;

      card.innerHTML = `
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-space-sm">
          <div class="space-y-1">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="px-2 py-0.5 rounded ${
                isCrit ? 'bg-error-container text-on-error-container' : 'bg-primary-fixed text-on-primary-fixed'
              } font-code-sm text-code-sm font-bold">${group.highestSeverity}</span>
              <span class="font-code-md text-code-md font-semibold text-on-surface">${group.id}</span>
              <span class="text-on-surface-variant font-code-sm text-[11px]">${group.createdTime}</span>
            </div>
            <h3 class="font-headline-sm text-headline-sm text-on-surface font-semibold">${group.title}</h3>
            <p class="font-body-sm text-body-sm text-on-surface-variant">${group.rootCauseSummary}</p>
            <div class="flex items-center gap-2 pt-1 flex-wrap">
              ${group.affectedServices
                .map(
                  (s) =>
                    `<span class="px-2 py-0.5 rounded bg-surface-container font-code-sm text-[11px] text-secondary">${s}</span>`
                )
                .join('')}
            </div>
          </div>
          <div class="flex flex-col items-end gap-2 shrink-0">
            <div class="flex items-baseline gap-1.5">
              <span class="font-headline-lg text-headline-lg text-on-surface font-bold">${group.rawAlertsCount}</span>
              <span class="font-body-sm text-body-sm text-secondary">alerts →</span>
              <span class="font-headline-lg text-headline-lg text-primary font-bold">${group.actionableAlertsCount}</span>
              <span class="font-body-sm text-body-sm text-primary font-medium">incident</span>
            </div>
            <div class="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-emerald-50 text-emerald-800 font-code-sm text-code-sm font-bold border border-emerald-200">
              <span class="material-symbols-outlined text-[16px]">verified</span>
              <span>${group.noiseReductionRatio} Noise Suppressed</span>
            </div>
            <div class="flex items-center gap-2 mt-1">
              <button onclick="event.stopPropagation(); window.drillDownAlert('${group.id}')" class="px-3 py-1 rounded-lg bg-primary text-on-primary font-label-md text-label-md hover:bg-primary-container transition-colors">
                Triage Incident
              </button>
            </div>
          </div>
        </div>
      `;

      card.addEventListener('click', () => {
        window.drillDownAlert(group.id);
      });

      container.appendChild(card);
    });
  }

  // Render Incidents List
  function renderIncidentsList() {
    const list = document.getElementById('incidents-quick-list');
    if (!list) return;

    list.innerHTML = '';
    state.incidents.forEach((inc) => {
      const item = document.createElement('div');
      item.className =
        'p-3 rounded-lg bg-surface-container-low hover:bg-surface-container transition-colors cursor-pointer border border-surface-container-highest';
      item.innerHTML = `
        <div class="flex items-center justify-between mb-1">
          <span class="font-code-sm text-code-sm font-bold text-error">${inc.id}</span>
          <span class="font-code-sm text-[10px] text-secondary">${inc.duration}</span>
        </div>
        <div class="font-label-md text-label-md text-on-surface font-semibold line-clamp-1">${inc.title}</div>
        <div class="flex items-center justify-between mt-2 font-code-sm text-[11px] text-on-surface-variant">
          <span>${inc.leadService}</span>
          <span class="text-primary font-medium">${inc.status}</span>
        </div>
      `;
      item.addEventListener('click', () => {
        renderSelectedIncident(inc.id);
        navigateTo('incident-details');
      });
      list.appendChild(item);
    });
  }

  // Render Selected Incident in Details Screen
  function renderSelectedIncident(incidentId) {
    const inc = state.incidents.find((i) => i.id === incidentId) || state.incidents[0];
    if (!inc) return;

    state.selectedIncidentId = inc.id;

    // Header updates
    const titleElem = document.getElementById('incident-details-title');
    if (titleElem) titleElem.innerText = `${inc.id}: ${inc.title}`;

    const descElem = document.getElementById('incident-details-desc');
    if (descElem) descElem.innerText = inc.description;

    const leadElem = document.getElementById('incident-lead-service');
    if (leadElem) leadElem.innerText = inc.leadService;

    const ownerElem = document.getElementById('incident-owner');
    if (ownerElem) ownerElem.innerText = inc.owner;
  }

  // Interactive Triage Actions
  window.acknowledgeAlert = function (alertId) {
    const alert = state.alerts.find((a) => a.id === alertId);
    if (alert) {
      alert.status = 'ACKNOWLEDGED';
      showToast(`Acknowledged alert ${alertId} (${alert.service})`, 'success');
      renderLiveAlerts();
    }
  };

  window.suppressAlert = function (alertId) {
    const alert = state.alerts.find((a) => a.id === alertId);
    if (alert) {
      alert.suppressed = true;
      alert.actionable = false;
      alert.status = 'SUPPRESSED_MANUAL';
      state.stats.droppedAlerts += 1;
      state.stats.fatigueAbsorptionPercent = Math.min(99.9, state.stats.fatigueAbsorptionPercent + 0.1);
      showToast(`Suppressed fingerprint ${alert.fingerprint} for service ${alert.service}`, 'warning');
      renderLiveAlerts();
      renderStats();
    }
  };

  window.drillDownAlert = function (groupIdOrIncidentId) {
    // If it's a group, find associated incident or show details
    renderSelectedIncident('INC-1042');
    navigateTo('incident-details');
    showToast(`Navigated to correlated incident context`, 'info');
  };

  // Auto-Refresh & Live Simulation Engine
  function startAutoRefresh() {
    if (state.refreshInterval) clearInterval(state.refreshInterval);

    state.refreshInterval = setInterval(() => {
      if (!state.autoRefresh) return;

      state.countdown -= 1;
      if (state.countdown <= 0) {
        state.countdown = 2;
        fetchLiveAnalytics();
        simulateIngressTick();
      }
      if (elements.countdownTag) {
        elements.countdownTag.innerText = `${state.countdown}s`;
      }
    }, 1000);
  }

  // Live Backend Analytics Integration (Phase 4 - Near-Real-Time Polling)
  async function fetchLiveAnalytics() {
    try {
      const resp = await fetch('http://localhost:8000/api/v1/analytics/overview');
      if (resp.ok) {
        const data = await resp.json();
        if (data && data.total_alerts > 0) {
          state.stats.incomingAlerts = data.total_alerts;
          state.stats.actionableAlerts = data.notified_alerts + data.escalated_alerts;
          state.stats.fatigueAbsorptionPercent = data.suppression_rate;
          // Correction 1: Map real active deduplication fingerprint pool count
          state.stats.activeDedupePool = data.active_dedupe_pool;
          if (data.average_processing_time_ms > 0) {
            state.stats.ingressVelocity = data.average_processing_time_ms;
          }
          renderStats();
        }
      }
    } catch (err) {
      // Graceful fallback if backend server is not running or offline
    }
  }

  window.toggleAutoRefresh = function () {
    state.autoRefresh = !state.autoRefresh;
    if (elements.streamToggle) {
      if (state.autoRefresh) {
        elements.streamToggle.className =
          'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full bg-primary transition-colors duration-200 ease-in-out focus:outline-none';
        elements.streamThumb.className =
          'translate-x-4 inline-block h-4 w-4 transform rounded-full bg-on-primary transition duration-200 ease-in-out mt-0.5 ml-0.5';
        showToast('Near-real-time auto-refresh active (2s polling)', 'info');
      } else {
        elements.streamToggle.className =
          'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full bg-surface-container-highest transition-colors duration-200 ease-in-out focus:outline-none';
        elements.streamThumb.className =
          'translate-x-0 inline-block h-4 w-4 transform rounded-full bg-outline transition duration-200 ease-in-out mt-0.5 ml-0.5';
        showToast('Near-real-time auto-refresh paused', 'warning');
      }
    }
  };

  function simulateIngressTick() {
    // Increase incoming counts slightly
    const burst = Math.floor(Math.random() * 8) + 3;
    state.stats.incomingAlerts += burst;
    state.stats.ingressVelocity = 135 + Math.random() * 15;

    // 95% of incoming alerts are deduplicated/suppressed
    const isActionable = Math.random() > 0.88;
    if (isActionable) {
      state.stats.actionableAlerts += 1;
    }

    renderStats();

    // Occasionally generate an alert stream entry
    if (Math.random() > 0.4) {
      const services = ['payment-gateway', 'checkout-api', 'inventory-worker', 'auth-service', 'ingress-nginx'];
      const svc = services[Math.floor(Math.random() * services.length)];
      const severities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
      const sev = severities[Math.floor(Math.random() * severities.length)];

      const now = new Date();
      const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(
        2,
        '0'
      )}:${String(now.getSeconds()).padStart(2, '0')}`;

      const newAlert = {
        id: `ALT-${Math.floor(1000 + Math.random() * 9000)}`,
        fingerprint: Math.random().toString(16).substring(2, 10),
        timestamp: timeStr,
        relativeTime: 'just now',
        service: svc,
        cluster: 'us-east-prod-k8s',
        namespace: 'production',
        severity: sev,
        title: `TelemetryStreamSignal_${svc}`,
        message: `High frequency event cluster detected on ${svc} container replicas.`,
        status: isActionable ? 'TRIGGERED' : 'SUPPRESSED',
        group: 'GRP-DB-POOL-01',
        occurrences: Math.floor(Math.random() * 50) + 1,
        suppressed: !isActionable,
        deduped: true,
        actionable: isActionable
      };

      state.alerts.unshift(newAlert);
      if (state.alerts.length > 50) state.alerts.pop();

      if (state.currentView === 'live-alerts') {
        renderLiveAlerts();
      }
    }
  }

  // Surge Simulation
  window.simulateSurge = function () {
    showToast('🚨 Triggering 500-Alert Traffic Surge...', 'error');
    state.stats.incomingAlerts += 520;
    state.stats.ingressVelocity = 380.5;
    state.stats.activeDedupePool += 14;
    state.stats.fatigueAbsorptionPercent = 99.2;
    state.stats.droppedAlerts += 512;

    renderStats();
    setTimeout(() => {
      showToast('⚡ Deduplication Engine absorbed 512 noisy events into 1 cluster!', 'success');
      renderAlertGroups();
    }, 1200);
  };

  // Recalculate Hashes Animation
  window.recalculateHashes = function () {
    showToast('Recalculating sliding temporal fingerprint hashes...', 'info');
    setTimeout(() => {
      showToast('Hash reduction optimal: 98.5% noise eliminated', 'success');
    }, 800);
  };

  // Export Telemetry File
  window.exportTelemetry = function () {
    const exportData = {
      exportTimestamp: new Date().toISOString(),
      cluster: 'us-east-prod-k8s',
      stats: state.stats,
      alertGroups: state.alertGroups,
      alerts: state.alerts,
      incidents: state.incidents
    };

    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(exportData, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `telemetry-export-${Date.now()}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();

    showToast('Exported telemetry payload as JSON', 'success');
  };

  // Modal Handlers
  window.openNewIncidentModal = function () {
    if (elements.newIncidentModal) {
      elements.newIncidentModal.classList.add('active');
    }
  };

  window.closeNewIncidentModal = function () {
    if (elements.newIncidentModal) {
      elements.newIncidentModal.classList.remove('active');
    }
  };

  function createNewIncidentFromForm() {
    const title = document.getElementById('modal-inc-title').value;
    const severity = document.getElementById('modal-inc-severity').value;
    const service = document.getElementById('modal-inc-service').value;
    const desc = document.getElementById('modal-inc-desc').value;

    const newInc = {
      id: `INC-${Math.floor(1000 + Math.random() * 9000)}`,
      title: title || 'Service Degradation Alert',
      severity: severity || 'HIGH',
      status: 'INVESTIGATING',
      startTime: 'Just now',
      duration: '0m ago',
      owner: 'Alex Rivera (Lead SRE)',
      leadService: service || 'payment-gateway',
      impact: 'Triaged via Operator Console',
      description: desc || 'Manual operator incident escalation.',
      alertsCount: 1,
      actionableCount: 1,
      runbookStatus: 'Step 1/4 (Initial Assessment)'
    };

    state.incidents.unshift(newInc);
    state.stats.activeIncidentsCount += 1;
    closeNewIncidentModal();
    showToast(`Created Incident ${newInc.id}`, 'success');
    renderIncidentsList();
    renderSelectedIncident(newInc.id);
    navigateTo('incident-details');
  }

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
          Type to search alerts, incident IDs, fingerprints, or services...
        </div>
      `;
      return;
    }

    const matchedAlerts = state.alerts.filter(
      (a) => a.title.toLowerCase().includes(query) || a.service.toLowerCase().includes(query) || a.id.toLowerCase().includes(query)
    );
    const matchedIncidents = state.incidents.filter(
      (i) => i.title.toLowerCase().includes(query) || i.id.toLowerCase().includes(query) || i.leadService.toLowerCase().includes(query)
    );

    let html = '';

    if (matchedIncidents.length > 0) {
      html += `<div class="px-3 py-1 font-label-sm text-[11px] text-secondary uppercase tracking-wider font-semibold">Incidents</div>`;
      matchedIncidents.forEach((inc) => {
        html += `
          <div onclick="window.closeSearchModal(); window.drillDownAlert('${inc.id}')" class="p-2.5 rounded-lg hover:bg-surface-container flex items-center justify-between cursor-pointer">
            <div>
              <span class="font-code-sm text-code-sm font-bold text-error">${inc.id}</span>:
              <span class="font-body-sm text-body-sm font-medium text-on-surface">${inc.title}</span>
            </div>
            <span class="font-code-sm text-[10px] bg-surface-container-high px-1.5 py-0.5 rounded text-secondary">${inc.leadService}</span>
          </div>
        `;
      });
    }

    if (matchedAlerts.length > 0) {
      html += `<div class="px-3 py-1 mt-2 font-label-sm text-[11px] text-secondary uppercase tracking-wider font-semibold">Alerts</div>`;
      matchedAlerts.forEach((alt) => {
        html += `
          <div onclick="window.closeSearchModal(); window.navigateTo('live-alerts')" class="p-2.5 rounded-lg hover:bg-surface-container flex items-center justify-between cursor-pointer">
            <div>
              <span class="font-code-sm text-code-sm font-bold text-primary">${alt.id}</span>:
              <span class="font-body-sm text-body-sm text-on-surface">${alt.title}</span>
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
      // ⌘K or Ctrl+K for search
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        openSearchModal();
      }
      // Escape to close modals
      if (e.key === 'Escape') {
        closeSearchModal();
        closeNewIncidentModal();
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
