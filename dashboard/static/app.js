/* ============================================================
   AgenticFlow Dashboard — Adaline-inspired frontend
   ============================================================ */

const COLUMN_LABELS = {
  backlog: 'Backlog',
  'ready-for-work': 'Ready for Work',
  'in-design': 'In Design',
  'in-progress': 'In Progress',
  'in-review': 'In Review',
  done: 'Done'
};

const STATUS_COLORS = {
  backlog: 'var(--on-surface-base-disabled)',
  'ready-for-work': '#a78bfa',
  'in-design': 'var(--warning)',
  'in-progress': 'var(--info)',
  'in-review': '#06b6d4',
  done: 'var(--ok)'
};

const ACTIVE_STATUSES = ['ready-for-work', 'in-design', 'in-progress', 'in-review'];

const socket = io({
  transports: ['websocket', 'polling'],
  reconnection: true,
  reconnectionAttempts: Infinity,
  reconnectionDelay: 1000,
  reconnectionDelayMax: 10000,
  timeout: 20000,
});

let boardData = { columns: [], tickets: [], stats: {} };
let runState = { active: false, ticketId: null, status: 'idle', currentAgent: null, progress: 0, logs: [], queue: [], agents: [], pendingQuestions: [], messages: [] };
let systemInfo = { model: '—', preferredBackend: null, availableBackends: [], projectsRoot: null };
let projectsRoot = null;
let traces = [];
let graphData = { nodes: [], edges: [] };
let selectedTicketId = localStorage.getItem('meta-ralph-selected-ticket') || null;
let deliverables = [];

let isConnected = false;
let lastFetchError = false;
let currentQuestion = null;
let questionCountdownInterval = null;
let designReviewActive = false;
let designReviewCountdownInterval = null;
let designReviewExpiresAt = null;
let designReviewDismissedId = null;
let selectedAgentId = null;
let confirmModalResolve = null;
let aiLinkModalOpen = false;
let installPromptEvent = null;
let repoFolderHandle = null;
let engineReady = false;

let lastRenderedTracesKey = null;
let lastRenderedGraphKey = null;
let lastRenderedDebugKey = null;
let lastRenderedRunKey = null;

// DOM refs
const btnThemeToggle = document.getElementById('btn-theme-toggle');
const btnTickets = document.getElementById('btn-tickets');
const btnInstall = document.getElementById('btn-install');
const btnNewTicket = document.getElementById('btn-new-ticket');
const btnNewTicketModal = document.getElementById('btn-new-ticket-modal');
const navModel = document.getElementById('nav-model');
const navStatus = document.getElementById('nav-status');
const navTicket = document.getElementById('nav-ticket');
const navPath = document.getElementById('nav-path');
const navConnection = document.getElementById('nav-connection');

const runBar = document.getElementById('run-bar');
const runBarTicket = document.getElementById('run-bar-ticket');
const runBarStatus = document.getElementById('run-bar-status');
const runBarProgress = document.getElementById('run-bar-progress');
const runBarElapsed = document.getElementById('run-bar-elapsed');
const runBarAgents = document.getElementById('run-bar-agents');

const tracesList = document.getElementById('traces-list');
const behaviorsGraph = document.getElementById('behaviors-graph');
const graphStage = document.getElementById('graph-stage');
const behaviorsSvg = document.getElementById('behaviors-svg');
const graphNodes = document.getElementById('graph-nodes');
const graphEmpty = document.getElementById('graph-empty');

const ticketStatusBody = document.getElementById('ticket-status-body');
const messagingFeed = document.getElementById('messaging-feed');

const chatMessages = document.getElementById('chat-messages');
const chatAgentSelect = document.getElementById('chat-agent-select');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const chatTyping = document.getElementById('chat-typing');
const deliverablesList = document.getElementById('deliverables-list');
const btnRefreshDeliverables = document.getElementById('btn-refresh-deliverables');

const debugLog = document.getElementById('debug-log');
const debugMeta = document.getElementById('debug-meta');

const ticketsModal = document.getElementById('tickets-modal');
const ticketsList = document.getElementById('tickets-list');
const btnCloseTickets = document.getElementById('btn-close-tickets');

const ticketModal = document.getElementById('ticket-modal');
const ticketForm = document.getElementById('ticket-form');
const modalTitle = document.getElementById('modal-title');
const btnCloseModal = document.getElementById('btn-close-modal');
const btnCancel = document.getElementById('btn-cancel');
const btnDelete = document.getElementById('btn-delete');
const repoPathInput = document.getElementById('ticket-repo-path');
const repoPickerMessage = document.getElementById('repo-picker-message');
const projectsRootInput = document.getElementById('projects-root');
const btnSaveProjectsRoot = document.getElementById('btn-save-projects-root');
const projectsRootMessage = document.getElementById('projects-root-message');
const pwaInstallOverlay = document.getElementById('pwa-install-overlay');
const btnInstallPwaOverlay = document.getElementById('btn-install-pwa');
const btnContinueBrowser = document.getElementById('btn-continue-browser');
const pwaInstallInstructions = document.getElementById('pwa-install-instructions');

const questionModal = document.getElementById('question-modal');
const questionAgent = document.getElementById('question-agent');
const questionText = document.getElementById('question-text');
const questionContext = document.getElementById('question-context');
const questionOptions = document.getElementById('question-options');
const questionCustom = document.getElementById('question-custom-answer');
const questionAnswerInput = document.getElementById('question-answer-input');
const questionCountdown = document.getElementById('question-countdown');
const btnQuestionCustom = document.getElementById('btn-question-custom');
const btnQuestionSkip = document.getElementById('btn-question-skip');
const btnQuestionSubmit = document.getElementById('btn-question-submit');

const designReviewModal = document.getElementById('design-review-modal');
const designReviewQuestions = document.getElementById('design-review-questions');
const designReviewCountdown = document.getElementById('design-review-countdown');
const btnDesignReviewSubmit = document.getElementById('btn-design-submit');
const btnDesignReviewExtend = document.getElementById('btn-design-extend');
const btnDesignReviewClose = document.getElementById('btn-design-review-close');
const btnDesignReviewLater = document.getElementById('btn-design-later');

const communicationPanel = document.getElementById('communication-panel');
const communicationBackdrop = document.getElementById('communication-backdrop');
const communicationTicketFeed = document.getElementById('communication-ticket-feed');
const btnCloseCommunication = document.getElementById('btn-close-communication');

const confirmModal = document.getElementById('confirm-modal');
const confirmModalTitle = document.getElementById('confirm-modal-title');
const confirmModalMessage = document.getElementById('confirm-modal-message');
const btnConfirmOk = document.getElementById('btn-confirm-ok');
const btnConfirmCancel = document.getElementById('btn-confirm-cancel');
const btnCloseConfirm = document.getElementById('btn-close-confirm');

const aiLinkModal = document.getElementById('ai-link-modal');
const aiLinkList = document.getElementById('ai-link-list');
const aiLinkNone = document.getElementById('ai-link-none');
const btnAiLinkLater = document.getElementById('btn-ai-link-later');

const engineOverlay = document.getElementById('engine-overlay');
const engineOverlayStatus = document.getElementById('engine-overlay-status');
const engineOverlayHelp = document.getElementById('engine-overlay-help');
const btnRetryEngine = document.getElementById('btn-retry-engine');

const toast = document.getElementById('toast');

/* ============================================================
   Theme
   ============================================================ */

function initTheme() {
  const saved = localStorage.getItem('meta-ralph-theme');
  if (saved === 'dark') {
    document.body.classList.add('dark');
  } else {
    document.body.classList.remove('dark');
  }
  updateThemeIcon();
}

function updateThemeIcon() {
  if (!btnThemeToggle) return;
  const isDark = document.body.classList.contains('dark');
  btnThemeToggle.innerHTML = `<i data-lucide="${isDark ? 'sun' : 'moon'}"></i>`;
  if (window.lucide) lucide.createIcons();
}

function toggleTheme() {
  const isDark = document.body.classList.toggle('dark');
  localStorage.setItem('meta-ralph-theme', isDark ? 'dark' : 'light');
  updateThemeIcon();
  renderBehaviorsGraph();
}

/* ============================================================
   Utilities
   ============================================================ */

function escapeHtml(text) {
  if (text == null) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function stripEmojis(text) {
  if (text == null) return '';
  return String(text).replace(/[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu, '').trim();
}

function truncatePath(path, maxLength = 35) {
  if (!path) return '';
  if (path.length <= maxLength) return path;
  return '…' + path.slice(-(maxLength - 1));
}

function formatElapsed(totalSeconds) {
  if (totalSeconds === null || totalSeconds === undefined || totalSeconds < 0) return '—';
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes.toString().padStart(2, '0')}m ${seconds.toString().padStart(2, '0')}s`;
  }
  return `${minutes.toString().padStart(2, '0')}m ${seconds.toString().padStart(2, '0')}s`;
}

function formatDuration(ms) {
  if (ms === null || ms === undefined || ms < 0) return '';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000).toString().padStart(2, '0')}s`;
}

function formatTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleTimeString();
}

function timeAgo(iso) {
  if (!iso) return '—';
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 10) return 'ahora';
  if (diff < 60) return `hace ${diff}s`;
  if (diff < 3600) return `hace ${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)}h`;
  return `hace ${Math.floor(diff / 86400)}d`;
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => showToast('Copiado al portapapeles'))
    .catch(err => console.error('Error copiando:', err));
}

function roleIcon(role, agentId) {
  const id = String(agentId || '').toLowerCase();
  const r = String(role || '').toLowerCase();
  if (id.includes('orchestrator') || r === 'orchestrator') return 'brain';
  if (id.includes('pm-research')) return 'users';
  if (id.includes('pm-domain')) return 'search';
  if (id.includes('pm-ux')) return 'palette';
  if (id.includes('pm-technical')) return 'cpu';
  if (id.includes('pm-integration')) return 'plug';
  if (id.includes('pm-risk')) return 'shield-alert';
  if (id.includes('project-manager')) return 'briefcase';
  if (id.includes('architect')) return 'building';
  if (id.includes('qa')) return 'check-circle';
  if (id.includes('engineer')) return 'code';
  if (r === 'lead') return 'users';
  if (r === 'sub') return 'bot';
  return 'user';
}

function statusIcon(status) {
  switch (status) {
    case 'running': return 'loader-2';
    case 'done': return 'check';
    case 'failed': return 'x';
    case 'blocked': return 'alert-circle';
    case 'queued': return 'clock';
    default: return 'circle';
  }
}

function statusBadgeClass(status) {
  switch (status) {
    case 'running': return 'status-running';
    case 'done': return 'status-done';
    case 'failed': return 'status-failed';
    case 'queued': return 'status-queued';
    default: return 'status-queued';
  }
}

function statusLabel(status) {
  switch (status) {
    case 'running': return 'Running';
    case 'done': return 'Done';
    case 'failed': return 'Failed';
    case 'queued': return 'Queued';
    default: return status || 'Queued';
  }
}

function isAgentStalled(agent) {
  if (agent.status !== 'running') return false;
  const logs = agent.logs || [];
  if (logs.length === 0) return true;
  const last = logs[logs.length - 1];
  const ts = last && last.timestamp ? new Date(last.timestamp).getTime() : 0;
  const stalledMs = 3 * 60 * 1000;
  return Date.now() - ts > stalledMs;
}

function agentRoleById(agentId) {
  const a = (runState.agents || []).find(x => x.id === agentId);
  return a ? a.role : null;
}

function showToast(message, duration = 2200) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), duration);
}

/* ============================================================
   Header & run bar
   ============================================================ */

const STATUS_LABELS = {
  idle: 'Idle',
  running: 'Running',
  paused: 'Paused',
  queued: 'Queued',
  completed: 'Done',
  done: 'Done',
  failed: 'Failed',
  backlog: 'Backlog',
  'ready-for-work': 'Ready',
  'in-design': 'Design',
  'in-progress': 'Progress',
  'in-review': 'Review'
};

function normalizeDisplayStatus(status) {
  if (status === 'completed') return 'done';
  return status || 'idle';
}

function getTicketById(ticketId) {
  if (!ticketId) return null;
  return (boardData.tickets || []).find(t => t.id === ticketId) || null;
}

function setSelectedTicket(ticketId) {
  selectedTicketId = ticketId || null;
  if (selectedTicketId) {
    localStorage.setItem('meta-ralph-selected-ticket', selectedTicketId);
  } else {
    localStorage.removeItem('meta-ralph-selected-ticket');
  }
  lastRenderedDeliverablesKey = null;
  loadDeliverables();
}

function getDisplayTicket() {
  const runningTicket = getTicketById(runState.ticketId);
  if (runState.ticketId && (runState.active || runningTicket)) {
    return runningTicket || { id: runState.ticketId, status: normalizeDisplayStatus(runState.status) };
  }
  const selected = getTicketById(selectedTicketId);
  if (selected) return selected;
  if (selectedTicketId && (boardData.tickets || []).length > 0) {
    setSelectedTicket(null);
    return null;
  }
  if (selectedTicketId) return { id: selectedTicketId, status: 'idle' };
  return null;
}

function getDisplayStatus(displayTicket) {
  if (runState.active) {
    return runState.status === 'paused' ? 'paused' : 'running';
  }
  if ((runState.queue || []).length > 0 && !displayTicket) {
    return 'queued';
  }
  if (runState.ticketId && displayTicket && displayTicket.id === runState.ticketId) {
    return normalizeDisplayStatus(runState.status === 'completed' ? 'done' : (displayTicket.status || runState.status));
  }
  return normalizeDisplayStatus(displayTicket ? displayTicket.status : 'idle');
}

function renderHeader() {
  if (navModel) {
    const model = systemInfo.preferredBackend || systemInfo.model || '—';
    navModel.textContent = model;
    navModel.title = systemInfo.preferredBackend
      ? `Linked backend: ${systemInfo.preferredBackend}`
      : (systemInfo.model || 'No backend linked');
  }
  const displayTicket = getDisplayTicket();
  const statusKey = getDisplayStatus(displayTicket);
  if (navTicket) {
    navTicket.textContent = displayTicket ? displayTicket.id : '—';
    navTicket.title = displayTicket ? `${displayTicket.title || displayTicket.id} · ${STATUS_LABELS[statusKey] || statusKey}` : 'No ticket selected';
  }

  if (navStatus) {
    navStatus.textContent = STATUS_LABELS[statusKey] || statusKey;
    navStatus.className = 'pill-value status-' + statusKey;
  }

  if (navPath) {
    const repoPath = displayTicket && displayTicket.repoPath ? displayTicket.repoPath : '';
    navPath.textContent = repoPath ? truncatePath(repoPath, 55) : '—';
    navPath.title = repoPath || 'No repository path';
  }
}

function renderRunBar() {
  if (!runBar) return;

  const active = runState.active;
  const displayTicket = getDisplayTicket();
  const ticketId = displayTicket ? displayTicket.id : '—';
  const statusKey = getDisplayStatus(displayTicket);
  const agents = runState.agents || [];
  const running = agents.filter(a => a.status === 'running').length;
  const total = agents.length;
  const progress = total > 0
    ? Math.round((agents.filter(a => a.status === 'done').length / total) * 100)
    : statusKey === 'done' ? 100 : 0;

  runBar.classList.toggle('idle', !active && !displayTicket);
  if (runBarTicket) runBarTicket.textContent = ticketId;
  if (runBarStatus) {
    runBarStatus.textContent = STATUS_LABELS[statusKey] || statusKey;
    runBarStatus.className = 'run-bar-status ' + statusKey;
  }
  if (runBarProgress) runBarProgress.style.width = `${progress}%`;
  if (runBarElapsed) runBarElapsed.textContent = formatElapsed(runState.elapsedSeconds);
  if (runBarAgents) {
    runBarAgents.textContent = total > 0
      ? `${running}/${total} running`
      : displayTicket ? (STATUS_LABELS[statusKey] || statusKey) : '0/0 running';
  }
}

function updateConnectionStatus(connected) {
  isConnected = connected;
  if (!navConnection) return;
  navConnection.classList.toggle('online', connected);
  navConnection.classList.toggle('offline', !connected);
  navConnection.innerHTML = connected
    ? '<i data-lucide="wifi" class="status-icon"></i>'
    : '<i data-lucide="wifi-off" class="status-icon"></i>';
  navConnection.title = connected ? 'Connected to server (WebSocket)' : 'Disconnected; reconnecting...';
  if (window.lucide) lucide.createIcons();
}

/* ============================================================
   Traces panel
   ============================================================ */

function estimateTokens(text) {
  if (!text) return 0;
  return Math.max(1, Math.ceil(String(text).length / 4));
}

function traceStatusFromLevel(level) {
  switch (level) {
    case 'error': return 'err';
    case 'warning': return 'wrn';
    case 'success': return 'ok';
    case 'live': return 'live';
    default: return 'ok';
  }
}

function traceBadgeText(status) {
  switch (status) {
    case 'err': return 'err';
    case 'wrn': return 'wrn';
    case 'live': return 'live';
    default: return '';
  }
}

function renderTraces() {
  if (!tracesList) return;

  const key = traces.map(t => `${t.timestamp}|${t.agentId}|${t.message}`).join('//');
  if (key === lastRenderedTracesKey) return;
  lastRenderedTracesKey = key;

  if (!traces.length) {
    tracesList.innerHTML = '<div class="traces-empty">Esperando actividad del runner...</div>';
    return;
  }

  tracesList.innerHTML = '';
  traces.slice(0, 120).forEach(trace => {
    const status = trace.status || traceStatusFromLevel(trace.level);
    const badge = traceBadgeText(status);
    const duration = formatDuration(trace.durationMs);
    const tokens = estimateTokens(trace.message);
    const name = stripEmojis(trace.agentName || trace.agentId || 'system');
    const message = stripEmojis(trace.message || '');
    const time = formatTime(trace.timestamp);

    const el = document.createElement('div');
    el.className = `trace-item status-${status}`;
    el.innerHTML = `
      <div class="trace-status-line status-${status}"></div>
      <div class="trace-content">
        <div class="trace-row">
          <span class="trace-time">${escapeHtml(time)}</span>
          <span class="trace-name" title="${escapeHtml(name)}">${escapeHtml(name)}</span>
          <span class="trace-meta">
            ${duration ? `<span class="trace-duration">${escapeHtml(duration)}</span>` : ''}
            <span class="trace-tokens">${tokens}t</span>
          </span>
        </div>
        <div class="trace-message">
          <span class="trace-message-text" title="${escapeHtml(message)}">${escapeHtml(message)}</span>
          ${badge ? `<span class="trace-badge status-${status}">${badge}</span>` : ''}
        </div>
      </div>
    `;
    tracesList.appendChild(el);
  });

  // Auto-scroll only if near bottom
  const nearBottom = tracesList.scrollHeight - tracesList.scrollTop - tracesList.clientHeight < 80;
  if (nearBottom) tracesList.scrollTop = tracesList.scrollHeight;
}

async function pollTraces() {
  try {
    const res = await fetch('/api/traces?limit=120');
    if (!res.ok) return;
    traces = await res.json();
    renderTraces();
  } catch (err) {
    console.warn('Error loading traces:', err);
  }
}

/* ============================================================
   Behaviors graph
   ============================================================ */

function computeGraphLayout(nodes, edges) {
  if (!nodes.length) return { nodes: [], edges: [] };

  const byId = {};
  nodes.forEach(n => byId[n.id] = n);

  const children = {};
  const parents = {};
  nodes.forEach(n => { children[n.id] = []; parents[n.id] = null; });
  edges.forEach(e => {
    if (e.type === 'parent' && byId[e.source] && byId[e.target]) {
      children[e.source].push(e.target);
      parents[e.target] = e.source;
    }
  });

  // Depth from roots
  const depth = {};
  const visit = (id, d) => {
    if (depth[id] !== undefined && depth[id] >= d) return;
    depth[id] = d;
    (children[id] || []).forEach(cid => visit(cid, d + 1));
  };
  nodes.forEach(n => { if (!parents[n.id]) visit(n.id, 0); });
  // Fallback for isolated nodes
  nodes.forEach(n => { if (depth[n.id] === undefined) depth[n.id] = 0; });

  const maxDepth = Math.max(0, ...Object.values(depth));
  const layers = Array.from({ length: maxDepth + 1 }, () => []);
  nodes.forEach(n => layers[depth[n.id]].push(n.id));
  const maxLayerSize = Math.max(1, ...layers.map(l => l.length));

  const rect = behaviorsGraph ? behaviorsGraph.getBoundingClientRect() : { width: 800, height: 400 };
  const padX = 60;
  const padY = 50;
  const padRight = 60;
  const padBottom = 50;

  // Adaptive node size: shrink bubbles when a layer has many agents so the whole tree fits.
  const nodeDiameter = Math.max(30, Math.min(48, Math.floor((rect.width - padX * 2) / maxLayerSize * 0.65)));
  const minGap = Math.max(10, Math.round(nodeDiameter * 0.25));
  const minLevelGap = Math.max(55, Math.min(90, Math.floor((rect.height - padY * 2) / Math.max(maxDepth, 1))));

  // Ensure enough height for all layers.
  const minContentHeight = padY * 2 + maxDepth * minLevelGap;
  const graphHeight = Math.max(rect.height, minContentHeight);
  const levelH = maxDepth > 0 ? (graphHeight - padY * 2) / maxDepth : 0;

  const positions = {};
  layers.forEach((layer, d) => {
    const count = layer.length;
    const minLayerW = count > 1 ? (count - 1) * (nodeDiameter + minGap) : 0;
    const layerW = Math.max(rect.width - padX * 2, minLayerW);
    const step = count > 1 ? layerW / (count - 1) : 0;
    const startX = padX + (Math.max(rect.width - padX * 2, minLayerW) - layerW) / 2;
    layer.forEach((id, i) => {
      const x = count === 1 ? rect.width / 2 : startX + i * step;
      const y = maxDepth === 0 ? graphHeight / 2 : padY + d * levelH;
      positions[id] = { x, y };
    });
  });

  // Shift so leftmost node isn't clipped when layer is wider than the panel.
  const xs = Object.values(positions).map(p => p.x);
  const minX = Math.min(...xs);
  if (minX < padX) {
    const offset = padX - minX;
    Object.values(positions).forEach(p => p.x += offset);
  }

  const maxX = Math.max(...Object.values(positions).map(p => p.x));
  const maxY = Math.max(...Object.values(positions).map(p => p.y));
  const width = Math.max(rect.width, maxX + nodeDiameter / 2 + padRight);
  const height = Math.max(graphHeight, maxY + nodeDiameter / 2 + padBottom);

  return { positions, depth, nodeDiameter, width, height };
}

function renderBehaviorsGraph() {
  if (!behaviorsGraph || !graphStage || !behaviorsSvg || !graphNodes) return;
  const { nodes, edges } = graphData;

  const key = JSON.stringify({
    selectedAgentId,
    nodes: nodes.map(n => [n.id, n.status, n.progress]),
    edges: edges.map(e => [e.source, e.target, e.type, e.count]),
  });
  if (key === lastRenderedGraphKey) return;
  lastRenderedGraphKey = key;

  if (!nodes.length) {
    behaviorsSvg.innerHTML = `<defs><marker id="arrow-head" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(46,67,32,0.35)" /></marker></defs>`;
    graphNodes.innerHTML = '';
    graphStage.style.width = '';
    graphStage.style.height = '';
    graphStage.style.transform = '';
    if (graphEmpty) graphEmpty.style.display = 'grid';
    return;
  }
  if (graphEmpty) graphEmpty.style.display = 'none';

  const isDark = document.body.classList.contains('dark');
  const arrowFill = isDark ? 'rgba(96,165,250,0.7)' : 'rgba(36,90,120,0.65)';
  const activeStroke = isDark ? 'rgba(96,165,250,0.8)' : 'rgba(36,90,120,0.8)';
  const hierarchyStroke = isDark ? 'rgba(96,165,250,0.42)' : 'rgba(36,90,120,0.38)';
  const communicationStroke = isDark ? 'rgba(203,213,225,0.92)' : 'rgba(71,85,105,0.88)';

  const { positions, nodeDiameter, width: graphWidth, height: graphHeight } = computeGraphLayout(nodes, edges);
  const rect = behaviorsGraph.getBoundingClientRect();
  const scale = Math.min(1, rect.width / graphWidth, rect.height / graphHeight);
  const offsetX = Math.max(0, (rect.width - graphWidth * scale) / 2);
  const offsetY = Math.max(0, (rect.height - graphHeight * scale) / 2);

  // Fit the whole graph inside the visible panel; scale down when there are many agents.
  graphStage.style.width = `${graphWidth}px`;
  graphStage.style.height = `${graphHeight}px`;
  graphStage.style.left = `${offsetX}px`;
  graphStage.style.top = `${offsetY}px`;
  graphStage.style.transform = `scale(${scale})`;

  // SVG edges
  let svgHtml = `<defs>
    <marker id="arrow-head" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 9 5 L 0 10 z" fill="${arrowFill}" /></marker>
    <marker id="arrow-head-active" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 9 5 L 0 10 z" fill="${activeStroke}" /></marker>
  </defs>`;

  const byId = {};
  nodes.forEach(n => byId[n.id] = n);

  function edgeAnchor(p1, p2, sourceRadius, targetRadius, type) {
    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    const dist = Math.hypot(dx, dy);
    if (dist === 0) {
      return { start: p1, end: p2 };
    }
    const ux = dx / dist;
    const uy = dy / dist;
    const sourceGap = type === 'parent' ? 4 : 8;
    const targetGap = type === 'parent' ? 9 : 10;
    return {
      start: { x: p1.x + ux * (sourceRadius + sourceGap), y: p1.y + uy * (sourceRadius + sourceGap) },
      end: { x: p2.x - ux * (targetRadius + targetGap), y: p2.y - uy * (targetRadius + targetGap) },
    };
  }

  function curve(p1, p2, type = 'parent', sourceRadius = 0, targetRadius = 0, siblingOffset = 0) {
    const { start, end } = edgeAnchor(p1, p2, sourceRadius, targetRadius, type);
    const newDx = end.x - start.x;
    const newDy = end.y - start.y;
    if (Math.hypot(newDx, newDy) < 1) {
      return `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} L ${end.x.toFixed(1)} ${end.y.toFixed(1)}`;
    }
    const isCommunication = type === 'communication' || type === 'message';
    const sideOffset = isCommunication
      ? siblingOffset + Math.sign(newDx || 1) * Math.min(34, Math.abs(newDx) * 0.12 + 14)
      : siblingOffset;
    const c1 = { x: start.x + sideOffset, y: start.y + newDy * 0.52 };
    const c2 = { x: end.x + sideOffset, y: end.y - newDy * 0.52 };
    return `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} C ${c1.x.toFixed(1)} ${c1.y.toFixed(1)}, ${c2.x.toFixed(1)} ${c2.y.toFixed(1)}, ${end.x.toFixed(1)} ${end.y.toFixed(1)}`;
  }

  const nodeRadii = {};
  nodes.forEach(node => {
    const baseSize = node.role === 'orchestrator' ? 56 : node.role === 'lead' ? 48 : 40;
    const size = Math.max(26, Math.round(baseSize * (nodeDiameter / 48)));
    nodeRadii[node.id] = size / 2;
  });

  const edgeSeen = {};

  const orderedEdges = [
    ...edges.filter(e => e.type !== 'parent'),
    ...edges.filter(e => e.type === 'parent'),
  ];

  orderedEdges.forEach((e, i) => {
    const s = positions[e.source];
    const t = positions[e.target];
    if (!s || !t) return;
    const sourceNode = byId[e.source];
    const targetNode = byId[e.target];
    const sourceRadius = nodeRadii[e.source] || nodeDiameter / 2;
    const targetRadius = nodeRadii[e.target] || nodeDiameter / 2;
    const isActive = sourceNode && targetNode && (sourceNode.status === 'running' || targetNode.status === 'running');
    const isCommunication = e.type === 'communication' || e.type === 'message';
    const stroke = isCommunication ? communicationStroke : (isActive ? activeStroke : hierarchyStroke);
    const marker = isCommunication ? '' : (isActive ? 'url(#arrow-head-active)' : 'url(#arrow-head)');
    const pathId = `graph-edge-${i}`;
    const width = isCommunication ? Math.min(2.8, 1.6 + Math.min(5, e.count || 1) * 0.22) : (isActive ? 2.35 : 1.45);
    const dash = isCommunication ? '5,5' : 'none';
    const groupKey = [e.source, e.target, e.type].join('→');
    const groupIndex = edgeSeen[groupKey] || 0;
    edgeSeen[groupKey] = groupIndex + 1;
    const siblingOffset = groupIndex ? (groupIndex % 2 === 0 ? -1 : 1) * (10 + groupIndex * 4) : 0;
    const opacity = isCommunication ? (selectedAgentId && selectedAgentId !== e.source && selectedAgentId !== e.target ? 0.35 : 0.92) : 1;
    svgHtml += `<path id="${pathId}" d="${curve(s, t, e.type, sourceRadius, targetRadius, siblingOffset)}" fill="none" stroke="${stroke}" stroke-width="${width}" stroke-dasharray="${dash}" stroke-linecap="round" stroke-opacity="${opacity}" marker-end="${marker}"></path>`;
    if (isActive && !isCommunication) {
      svgHtml += `<circle r="2.5" fill="${activeStroke}"><animateMotion dur="1.2s" repeatCount="indefinite"><mpath href="#${pathId}"/></animateMotion></circle>`;
    }
  });

  behaviorsSvg.innerHTML = svgHtml;

  // HTML nodes
  graphNodes.innerHTML = '';
  nodes.forEach((node, idx) => {
    const pos = positions[node.id];
    if (!pos) return;
    const baseSize = node.role === 'orchestrator' ? 56 : node.role === 'lead' ? 48 : 40;
    const size = Math.max(26, Math.round(baseSize * (nodeDiameter / 48)));
    const status = node.status || 'queued';
    const statusClass = statusBadgeClass(status);
    const initials = stripEmojis(node.name || node.id).split(/\s+/).map(w => w[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || 'A';

    const el = document.createElement('div');
    el.className = 'graph-node' + (selectedAgentId === node.id ? ' selected' : '');
    el.style.left = `${pos.x}px`;
    el.style.top = `${pos.y}px`;
    // Stagger float animation per node so they don't move in perfect unison.
    const floatDelay = (node.id.split('').reduce((a, c) => a + c.charCodeAt(0), 0) % 10) * 0.4;
    el.style.animationDelay = `-${floatDelay}s`;
    el.innerHTML = `
      <div class="graph-node-bubble ${statusClass}" style="width:${size}px;height:${size}px;font-size:${Math.max(9, size / 4)}px;" title="${escapeHtml(stripEmojis(node.name))} (${node.status})" role="button" tabindex="0" aria-label="Agent ${escapeHtml(stripEmojis(node.name))}">
        ${initials}
      </div>
      <span class="graph-node-label" title="${escapeHtml(stripEmojis(node.name))}">${escapeHtml(stripEmojis(node.name))}</span>
    `;

    const bubble = el.querySelector('.graph-node-bubble');
    bubble.addEventListener('click', () => {
      selectedAgentId = selectedAgentId === node.id ? null : node.id;
      renderBehaviorsGraph();
      renderDebugFooter();
    });
    bubble.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        selectedAgentId = selectedAgentId === node.id ? null : node.id;
        renderBehaviorsGraph();
        renderDebugFooter();
      }
    });

    graphNodes.appendChild(el);
  });
}

async function pollGraph() {
  try {
    const res = await fetch('/api/graph');
    if (!res.ok) return;
    graphData = await res.json();
    renderBehaviorsGraph();
  } catch (err) {
    console.warn('Error loading graph:', err);
  }
}

/* ============================================================
   Debug footer
   ============================================================ */

function levelToClass(level) {
  switch (level) {
    case 'error': return 'error';
    case 'warning': return 'warning';
    case 'success': return 'success';
    default: return 'info';
  }
}

function renderDebugFooter() {
  if (!debugLog) return;

  const allLogs = [];
  (runState.agents || []).forEach(agent => {
    (agent.logs || []).forEach(log => {
      if (selectedAgentId && agent.id !== selectedAgentId) return;
      allLogs.push({
        timestamp: log.timestamp,
        level: log.level || 'info',
        message: `[${stripEmojis(agent.name || agent.id)}] ${stripEmojis(log.message || '')}`,
      });
    });
  });

  // Fallback: use traces as logs
  if (allLogs.length === 0 && traces.length > 0) {
    traces.slice(0, 100).forEach(t => {
      if (selectedAgentId && t.agentId !== selectedAgentId) return;
      allLogs.push({
        timestamp: t.timestamp,
        level: t.level || 'info',
        message: `[${stripEmojis(t.agentName || t.agentId || 'system')}] ${stripEmojis(t.message || '')}`,
      });
    });
  }

  allLogs.sort((a, b) => new Date(a.timestamp || 0) - new Date(b.timestamp || 0));
  const tail = allLogs.slice(-150);

  const key = tail.map(l => `${l.timestamp}|${l.message}`).join('//');
  if (key === lastRenderedDebugKey) return;
  lastRenderedDebugKey = key;

  if (!tail.length) {
    debugLog.innerHTML = '<div class="debug-empty">No recent logs</div>';
    if (debugMeta) debugMeta.textContent = '—';
    return;
  }

  debugLog.innerHTML = tail.map(log => `
    <div class="debug-line level-${levelToClass(log.level)}">
      <span class="debug-time">${escapeHtml(formatTime(log.timestamp))}</span>
      <span class="debug-level">${escapeHtml(log.level || 'info')}</span>
      <span class="debug-message">${escapeHtml(log.message)}</span>
    </div>
  `).join('');

  if (debugMeta) {
    const active = (runState.agents || []).filter(a => a.status === 'running').length;
    const total = (runState.agents || []).length;
    debugMeta.textContent = `${total} agent${total !== 1 ? 's' : ''} · ${active} running · ${tail.length} logs`;
  }

  const nearBottom = debugLog.scrollHeight - debugLog.scrollTop - debugLog.clientHeight < 80;
  if (nearBottom) debugLog.scrollTop = debugLog.scrollHeight;
}

/* ============================================================
   Tickets modal
   ============================================================ */

function renderTicketsList() {
  if (!ticketsList) return;
  const tickets = boardData.tickets || [];
  if (!tickets.length) {
    ticketsList.innerHTML = '<div class="tickets-empty">No tickets yet. Create one to get started.</div>';
    return;
  }

  ticketsList.innerHTML = '';
  tickets.slice().reverse().forEach(ticket => {
    const runStatus = getTicketRunStatus(ticket.id);
    const runIcon = runStatusIcon(runStatus);
    const isRunnable = ['idle', 'queued', 'paused'].includes(runStatus) && ['backlog', 'ready-for-work', 'in-design', 'in-progress', 'in-review'].includes(ticket.status);
    const showRestart = ['ready-for-work', 'in-design', 'in-progress', 'in-review', 'done'].includes(ticket.status);
    const runAction = runStatus === 'running'
      ? `<button type="button" class="btn-icon btn-small ticket-action-pause" data-id="${escapeHtml(ticket.id)}" title="Pause"><i data-lucide="pause"></i></button>`
      : isRunnable
        ? `<button type="button" class="btn-icon btn-small ticket-action-play" data-id="${escapeHtml(ticket.id)}" title="${runStatus === 'paused' ? 'Resume' : 'Run'}"><i data-lucide="play"></i></button>`
        : '';
    const restartAction = showRestart
      ? `<button type="button" class="btn-icon btn-small ticket-action-restart" data-id="${escapeHtml(ticket.id)}" title="Restart from scratch"><i data-lucide="refresh-cw"></i></button>`
      : '';

    const row = document.createElement('div');
    const isSelected = selectedTicketId === ticket.id || (!selectedTicketId && runState.ticketId === ticket.id);
    row.className = 'ticket-row ticket-row-' + runStatus + (isSelected ? ' selected' : '');
    row.innerHTML = `
      <span class="ticket-row-run-status" title="${runStatus}"><i data-lucide="${runIcon}"></i></span>
      <span class="ticket-row-id">${escapeHtml(ticket.id)}</span>
      <span class="ticket-row-title" title="${escapeHtml(ticket.title)}">${escapeHtml(ticket.title)}</span>
      <span class="ticket-row-status status-${ticket.status}">${COLUMN_LABELS[ticket.status] || ticket.status}</span>
      <div class="ticket-row-actions">
        ${runAction}
        ${restartAction}
        <button type="button" class="btn-icon btn-small" title="Edit"><i data-lucide="pencil"></i></button>
        <button type="button" class="btn-icon btn-small" title="Delete"><i data-lucide="trash-2"></i></button>
      </div>
    `;
    row.querySelector('[title="Edit"]').addEventListener('click', (e) => {
      e.stopPropagation();
      setSelectedTicket(ticket.id);
      openTicketModal(ticket);
    });
    row.querySelector('[title="Delete"]').addEventListener('click', (e) => {
      e.stopPropagation();
      deleteTicketById(ticket.id);
    });
    const playBtn = row.querySelector('.ticket-action-play');
    if (playBtn) playBtn.addEventListener('click', (e) => { e.stopPropagation(); setSelectedTicket(ticket.id); playTicket(ticket.id); });
    const pauseBtn = row.querySelector('.ticket-action-pause');
    if (pauseBtn) pauseBtn.addEventListener('click', (e) => { e.stopPropagation(); pauseTicket(ticket.id); });
    const restartBtn = row.querySelector('.ticket-action-restart');
    if (restartBtn) restartBtn.addEventListener('click', (e) => { e.stopPropagation(); setSelectedTicket(ticket.id); restartTicket(ticket.id); });
    row.addEventListener('click', () => {
      setSelectedTicket(ticket.id);
      renderTicketsList();
      renderHeader();
      renderRunBar();
      renderTicketStatus();
    });
    ticketsList.appendChild(row);
  });
  if (window.lucide) lucide.createIcons();
}

function getTicketRunStatus(ticketId) {
  if (runState.ticketId === ticketId) {
    if (runState.active) return 'running';
    if (runState.status === 'completed') return 'done';
    if (runState.status === 'failed') return 'failed';
    if (runState.status === 'paused') return 'paused';
  }
  if ((runState.pausedTickets || []).includes(ticketId)) return 'paused';
  if ((runState.queue || []).includes(ticketId)) return 'queued';
  return 'idle';
}

function runStatusIcon(status) {
  switch (status) {
    case 'running': return 'play-circle';
    case 'paused': return 'pause-circle';
    case 'queued': return 'clock';
    default: return 'circle';
  }
}

async function playTicket(ticketId) {
  try {
    const res = await fetch(`/api/tickets/${ticketId}/play`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || 'Error');
    showToast(data.message);
  } catch (err) {
    showToast(err.message, 4000);
  }
}

async function pauseTicket(ticketId) {
  try {
    const res = await fetch(`/api/tickets/${ticketId}/pause`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || 'Error');
    showToast(data.message);
  } catch (err) {
    showToast(err.message, 4000);
  }
}

async function restartTicket(ticketId) {
  const confirmed = await showConfirmModal({
    title: 'Restart ticket',
    message: `Restart ticket ${ticketId} from scratch?\n\nRun progress, snapshots, and generated artifacts such as the PRD, task plan, and architecture will be removed. Repository code changes will not be deleted.`,
    okText: 'Restart',
    cancelText: 'Cancel',
  });
  if (!confirmed) return;
  try {
    const res = await fetch(`/api/tickets/${ticketId}/restart`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || 'Error');
    showToast(data.message || 'Ticket restarted');
  } catch (err) {
    showToast('Error restarting ticket: ' + err.message, 4000);
  }
}

function openTicketsModal() {
  if (!ticketsModal) return;
  renderTicketsList();
  ticketsModal.classList.add('open');
}

function closeTicketsModal() {
  if (!ticketsModal) return;
  ticketsModal.classList.remove('open');
}

/* ============================================================
   Ticket create/edit modal
   ============================================================ */

function openTicketModal(ticket = null) {
  const isEdit = !!ticket;
  if (ticket && ticket.id) {
    setSelectedTicket(ticket.id);
    renderHeader();
    renderRunBar();
    renderTicketStatus();
  }
  if (modalTitle) modalTitle.textContent = isEdit ? 'Edit ticket' : 'New ticket';
  document.getElementById('ticket-id').value = ticket ? ticket.id : '';
  document.getElementById('ticket-title').value = ticket ? ticket.title : '';
  document.getElementById('ticket-description').value = ticket ? ticket.description || '' : '';
  document.getElementById('ticket-status').value = ticket ? ticket.status : 'backlog';
  document.getElementById('ticket-role').value = ticket ? ticket.assigneeRole || '' : '';
  document.getElementById('ticket-focus').value = ticket ? ticket.featureFocus || '' : '';
  document.getElementById('ticket-labels').value = ticket ? (ticket.labels || []).join(', ') : '';
  repoPathInput.value = ticket ? ticket.repoPath || '' : '';
  if (projectsRootInput) projectsRootInput.value = projectsRoot || '';
  if (projectsRootMessage) projectsRootMessage.style.display = 'none';
  updateRepoFolderBadge(repoFolderHandle ? repoFolderHandle.name : null);
  if (btnDelete) btnDelete.style.display = isEdit ? 'inline-block' : 'none';
  if (ticketModal) ticketModal.classList.add('open');
  closeTicketsModal();
}

function closeTicketModal() {
  if (ticketModal) ticketModal.classList.remove('open');
  if (ticketForm) ticketForm.reset();
}

function isAbsolutePath(path) {
  if (!path) return false;
  if (path.startsWith('/')) return true;
  if (/^[a-zA-Z]:[\\/]/.test(path)) return true;
  return false;
}

async function saveTicket(e) {
  e.preventDefault();
  const id = document.getElementById('ticket-id').value;
  const repoPath = repoPathInput.value.trim();
  if (!repoPath) {
    showRepoMessage('Repo folder is required.');
    return;
  }
  if (!isAbsolutePath(repoPath)) {
    showRepoMessage('Please provide an absolute path (e.g., /Users/you/project or C:\\\\Users\\\\you\\\\project).');
    return;
  }
  const payload = {
    title: document.getElementById('ticket-title').value,
    description: document.getElementById('ticket-description').value,
    status: document.getElementById('ticket-status').value,
    repoPath,
    assigneeRole: document.getElementById('ticket-role').value,
    featureFocus: document.getElementById('ticket-focus').value,
    labels: document.getElementById('ticket-labels').value.split(',').map(s => s.trim()).filter(Boolean)
  };

  try {
    const url = id ? `/api/tickets/${id}` : '/api/tickets';
    const method = id ? 'PATCH' : 'POST';
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      const msg = errData.message || errData.error || 'Error saving ticket';
      throw new Error(msg);
    }
    closeTicketModal();
    showToast(id ? 'Ticket updated' : 'Ticket created');
  } catch (err) {
    alert(err.message);
  }
}

async function deleteTicket() {
  const id = document.getElementById('ticket-id').value;
  if (!id) return;
  if (!confirm('Delete this ticket?')) return;
  await deleteTicketById(id);
  closeTicketModal();
}

async function deleteTicketById(id) {
  try {
    const res = await fetch(`/api/tickets/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Error deleting ticket');
    showToast('Ticket deleted');
  } catch (err) {
    alert(err.message);
  }
}

/* ============================================================
   Repo picker
   ============================================================ */

function showRepoMessage(text) {
  if (!repoPickerMessage) return;
  repoPickerMessage.textContent = text;
  repoPickerMessage.style.display = 'block';
}

function hideRepoMessage() {
  if (!repoPickerMessage) return;
  repoPickerMessage.style.display = 'none';
  repoPickerMessage.textContent = '';
}

function showProjectsRootMessage(text, isError = false) {
  if (!projectsRootMessage) return;
  projectsRootMessage.textContent = text;
  projectsRootMessage.style.display = 'block';
  projectsRootMessage.style.color = isError ? 'var(--danger)' : 'var(--success)';
}

function hideProjectsRootMessage() {
  if (!projectsRootMessage) return;
  projectsRootMessage.style.display = 'none';
}

async function saveProjectsRoot() {
  if (!projectsRootInput) return;
  const value = projectsRootInput.value.trim() || null;
  try {
    const res = await fetch('/api/config', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projectsRoot: value })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'Error saving settings');
    projectsRoot = data.projectsRoot || null;
    systemInfo.projectsRoot = projectsRoot;
    showProjectsRootMessage('Default projects folder saved');
  } catch (err) {
    showProjectsRootMessage(err.message, true);
  }
}

/* ============================================================
   Ticket status & messaging
   ============================================================ */

function renderTicketStatus() {
  if (!ticketStatusBody) return;

  const activeTicket = getDisplayTicket();
  const displayStatus = getDisplayStatus(activeTicket);
  const agents = runState.agents || [];

  if (!activeTicket && agents.length === 0) {
    ticketStatusBody.innerHTML = '<div class="status-empty">No ticket selected</div>';
    return;
  }

  const progress = agents.length > 0
    ? Math.round((agents.filter(a => a.status === 'done').length / agents.length) * 100)
    : 0;

  const agentRows = agents.map(agent => {
    const icon = roleIcon(agent.role, agent.id);
    const status = agent.status || 'queued';
    return `
      <div class="agent-status-item status-${status}">
        <div class="agent-status-name">
          <i data-lucide="${icon}"></i>
          <span title="${escapeHtml(stripEmojis(agent.name || agent.id))}">${escapeHtml(stripEmojis(agent.name || agent.id))}</span>
        </div>
        <span class="agent-status-label">${status}</span>
      </div>
    `;
  }).join('');

  ticketStatusBody.innerHTML = `
    <div class="status-card">
      <div class="status-card-row">
        <span>Ticket</span>
        <span class="value">${escapeHtml(activeTicket ? activeTicket.id : '—')}</span>
      </div>
      <div class="status-card-row">
        <span>Status</span>
        <span class="status-badge status-${displayStatus}">${STATUS_LABELS[displayStatus] || displayStatus}</span>
      </div>
      <div class="status-card-row">
        <span>Progress</span>
        <span class="value">${progress}%</span>
      </div>
      <div class="status-card-row">
        <span>Time</span>
        <span class="value">${formatElapsed(runState.elapsedSeconds)}</span>
      </div>
      <div class="agent-status-list">
        ${agentRows}
      </div>
    </div>
  `;
  if (window.lucide) lucide.createIcons();
}

function renderMessaging() {
  if (!messagingFeed) return;
  const comm = runState.communication || {};
  const log = comm.log || [];
  const legacyMessages = (runState.messages || []).map(m => ({ ...m, _source: 'legacy' }));
  const entries = [...log, ...legacyMessages].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

  if (!entries.length) {
    messagingFeed.innerHTML = '<div class="messaging-empty">No internal messages yet...</div>';
    return;
  }

  messagingFeed.innerHTML = '';
  entries.slice().reverse().forEach(entry => {
    const el = document.createElement('div');
    el.className = 'comm-item';

    let headerText = '';
    let bodyText = '';
    let badge = '';

    if (entry._source === 'legacy') {
      headerText = `${entry.from || 'unknown'} → ${entry.to || 'all'}`;
      bodyText = entry.question || '';
      badge = entry.answer ? 'answered' : 'pending';
      const answerHtml = entry.answer
        ? `<div class="comm-item-answer"><strong>${escapeHtml(stripEmojis(entry.to))}:</strong> ${escapeHtml(stripEmojis(entry.answer))}</div>`
        : '<div class="comm-item-answer">Waiting for response...</div>';
      el.innerHTML = `
        <div class="comm-item-header">
          <span>${escapeHtml(stripEmojis(headerText))}</span>
          <span>${formatTime(entry.timestamp)}</span>
        </div>
        <div class="comm-item-meta">${escapeHtml(badge)}</div>
        <div class="comm-item-body">${escapeHtml(stripEmojis(bodyText))}</div>
        ${answerHtml}
      `;
    } else if (entry.type === 'message') {
      headerText = `${entry.from || 'unknown'} → ${entry.to || 'all'}`;
      bodyText = entry.payload && entry.payload.text ? entry.payload.text : '';
      badge = entry.messageType || 'message';
      el.innerHTML = `
        <div class="comm-item-header">
          <span>${escapeHtml(stripEmojis(headerText))}</span>
          <span>${formatTime(entry.timestamp)}</span>
        </div>
        <div class="comm-item-meta">${escapeHtml(badge)}</div>
        <div class="comm-item-body">${escapeHtml(stripEmojis(bodyText))}</div>
      `;
    } else if (entry.type === 'event') {
      headerText = entry.eventType || 'event';
      const payload = entry.payload || {};
      bodyText = typeof payload === 'object'
        ? Object.entries(payload).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(' · ')
        : String(payload);
      badge = entry.participantId || 'system';
      el.innerHTML = `
        <div class="comm-item-header">
          <span>${escapeHtml(stripEmojis(headerText))}</span>
          <span>${formatTime(entry.timestamp)}</span>
        </div>
        <div class="comm-item-meta">${escapeHtml(badge)}</div>
        <div class="comm-item-body">${escapeHtml(stripEmojis(bodyText))}</div>
      `;
    }

    messagingFeed.appendChild(el);
  });

  const nearBottom = messagingFeed.scrollHeight - messagingFeed.scrollTop - messagingFeed.clientHeight < 80;
  if (nearBottom) messagingFeed.scrollTop = messagingFeed.scrollHeight;
}

/* ============================================================
   Chat panel
   ============================================================ */

const DEFAULT_CHAT_AGENTS = [
  { id: 'orchestrator', name: 'Lead Orchestrator' },
  { id: 'product_manager', name: 'Product Manager' },
  { id: 'architect', name: 'Architect' },
  { id: 'project_manager', name: 'Project Manager' },
  { id: 'engineer', name: 'Engineer' },
  { id: 'qa', name: 'QA Engineer' },
  { id: 'recovery', name: 'Recovery' },
];

let currentChatAgent = chatAgentSelect ? chatAgentSelect.value : '';
let lastRenderedChatKey = null;
let pwaOverlayDismissed = false;

function updateChatAgentSelect() {
  if (!chatAgentSelect) return;
  const agents = runState.agents || [];

  chatAgentSelect.innerHTML = '';
  if (agents.length === 0) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'No agents available yet';
    chatAgentSelect.appendChild(option);
    chatAgentSelect.disabled = true;
    currentChatAgent = '';
    return;
  }

  chatAgentSelect.disabled = false;
  const known = new Map();
  agents.forEach(a => {
    known.set(a.id, a.name || a.id);
  });

  Array.from(known.entries()).forEach(([id, name]) => {
    const option = document.createElement('option');
    option.value = id;
    option.textContent = name;
    chatAgentSelect.appendChild(option);
  });

  if (known.has(currentChatAgent)) {
    chatAgentSelect.value = currentChatAgent;
  } else {
    currentChatAgent = chatAgentSelect.value;
  }
  renderChat();
}
let chatPendingReply = false;
let lastRenderedDeliverablesKey = null;

function formatFileSize(bytes) {
  if (bytes == null || Number.isNaN(bytes)) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function deliverableIcon(type) {
  switch (type) {
    case 'prd':
    case 'architecture':
    case 'research':
    case 'qa-rejection':
      return 'file-text';
    case 'tasks':
      return 'list-tree';
    default:
      return 'file';
  }
}

function renderDeliverables() {
  if (!deliverablesList) return;
  const key = JSON.stringify(deliverables.map(d => [d.path, d.updatedAt, d.exists]));
  if (key === lastRenderedDeliverablesKey) return;
  lastRenderedDeliverablesKey = key;

  if (!deliverables.length) {
    deliverablesList.innerHTML = '<div class="deliverables-empty">No deliverables yet.</div>';
    return;
  }

  deliverablesList.innerHTML = '';
  deliverables.forEach(item => {
    const el = document.createElement('div');
    el.className = `deliverable-item${item.exists ? '' : ' missing'}`;
    const size = formatFileSize(item.sizeBytes);
    const updated = item.updatedAt ? formatTime(item.updatedAt) : '';
    el.innerHTML = `
      <div class="deliverable-main">
        <i data-lucide="${deliverableIcon(item.type)}"></i>
        <div class="deliverable-copy">
          <div class="deliverable-title" title="${escapeHtml(item.name || item.path)}">${escapeHtml(item.name || 'Deliverable')}</div>
          <div class="deliverable-path" title="${escapeHtml(item.path || '')}">${escapeHtml(item.path || 'No path available')}</div>
          <div class="deliverable-meta">
            <span>${escapeHtml(item.type || 'file')}</span>
            ${size ? `<span>${escapeHtml(size)}</span>` : ''}
            ${updated ? `<span>${escapeHtml(updated)}</span>` : ''}
          </div>
        </div>
      </div>
      <div class="deliverable-actions">
        <button type="button" class="btn-icon btn-small deliverable-open-file" title="Open file" ${item.exists ? '' : 'disabled'}><i data-lucide="file"></i></button>
        <button type="button" class="btn-icon btn-small deliverable-open-folder" title="Open folder" ${item.path ? '' : 'disabled'}><i data-lucide="folder-open"></i></button>
      </div>
    `;
    const openFileBtn = el.querySelector('.deliverable-open-file');
    const openFolderBtn = el.querySelector('.deliverable-open-folder');
    if (openFileBtn) openFileBtn.addEventListener('click', () => openPath(item.path, false));
    if (openFolderBtn) openFolderBtn.addEventListener('click', () => openPath(item.path, true));
    deliverablesList.appendChild(el);
  });
  if (window.lucide) lucide.createIcons();
}

async function loadDeliverables() {
  if (!deliverablesList) return;
  const displayTicket = getDisplayTicket();
  if (!displayTicket || !displayTicket.id) {
    deliverables = [];
    lastRenderedDeliverablesKey = null;
    renderDeliverables();
    return;
  }
  try {
    const res = await fetch(`/api/deliverables?ticketId=${encodeURIComponent(displayTicket.id)}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    deliverables = data.deliverables || [];
    renderDeliverables();
  } catch (err) {
    console.warn('Error loading deliverables:', err);
    deliverablesList.innerHTML = '<div class="deliverables-empty">Could not load deliverables.</div>';
    lastRenderedDeliverablesKey = null;
  }
}

function formatChatContent(text) {
  if (!text) return '';
  let html = escapeHtml(text);
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>');
  html = html.replace(/\n/g, '<br>');
  return html;
}

function buildChatMessageHtml(entry) {
  const from = entry.from || 'system';
  const payload = entry.payload || {};
  const reply = payload.reply || payload.text || '';
  const meta = payload.meta || {};
  const trace = Array.isArray(payload.trace) ? payload.trace : [];
  const side = from === 'user' ? 'user' : (from === 'system' ? 'system' : 'agent');
  const displayName = from === 'user' ? 'You' : (from === 'system' ? 'System' : stripEmojis(from));

  const skills = Array.isArray(meta.skills) ? meta.skills : [];
  const skillsHtml = skills.length
    ? `<div class="chat-skills">${skills.map(s => `<span class="chat-skill-tag">${escapeHtml(s)}</span>`).join('')}</div>`
    : '';

  const traceHtml = trace.length
    ? `<details class="chat-trace">
        <summary>Agent trace (${trace.length})</summary>
        <div class="chat-trace-body">${trace.map(line => `<p>${formatChatContent(line)}</p>`).join('')}</div>
      </details>`
    : '';

  const sessionHint = meta.sessionHint
    ? `<div class="chat-session-hint" title="Backend session">${escapeHtml(meta.sessionHint)}</div>`
    : '';

  return `
    <div class="chat-message ${side}">
      <div class="chat-bubble">${formatChatContent(reply)}</div>
      ${skillsHtml}
      ${traceHtml}
      ${sessionHint}
      <div class="chat-meta">
        <span>${escapeHtml(displayName)}</span>
        <span>${formatTime(entry.timestamp)}</span>
      </div>
    </div>
  `;
}

function renderChat() {
  if (!chatMessages) return;
  if (!currentChatAgent) {
    chatMessages.innerHTML = '<div class="chat-empty">No agent selected.</div>';
    lastRenderedChatKey = null;
    return;
  }
  const comm = runState.communication || {};
  const log = (comm.log || []).filter(e =>
    e.type === 'message' &&
    e.messageType === 'chat' &&
    ((e.from === 'user' && e.to === currentChatAgent) ||
     (e.from === currentChatAgent && e.to === 'user'))
  );

  const key = currentChatAgent + '//' + log.map(e => `${e.timestamp}|${e.from}|${e.to}|${JSON.stringify(e.payload)}`).join('//');
  if (key === lastRenderedChatKey) return;
  lastRenderedChatKey = key;

  if (!log.length) {
    chatMessages.innerHTML = `<div class="chat-empty">Start a conversation with ${escapeHtml(currentChatAgent)}.</div>`;
    return;
  }

  chatMessages.innerHTML = log.map(buildChatMessageHtml).join('');

  const nearBottom = chatMessages.scrollHeight - chatMessages.scrollTop - chatMessages.clientHeight < 80;
  if (nearBottom) chatMessages.scrollTop = chatMessages.scrollHeight;
}

function showChatTyping() {
  if (!chatTyping) return;
  chatTyping.style.display = 'flex';
  const nearBottom = chatMessages.scrollHeight - chatMessages.scrollTop - chatMessages.clientHeight < 80;
  if (nearBottom) chatMessages.scrollTop = chatMessages.scrollHeight;
}

function hideChatTyping() {
  if (!chatTyping) return;
  chatTyping.style.display = 'none';
}

function checkChatReplyReceived() {
  if (!chatPendingReply || !currentChatAgent) return;
  const comm = runState.communication || {};
  const log = (comm.log || []).filter(e =>
    e.type === 'message' &&
    e.messageType === 'chat' &&
    ((e.from === 'user' && e.to === currentChatAgent) ||
     (e.from === currentChatAgent && e.to === 'user'))
  );
  if (!log.length) return;
  const lastUserIdx = log.map(e => e.from).lastIndexOf('user');
  if (lastUserIdx === -1) return;
  const lastEntry = log[log.length - 1];
  if (lastEntry.from !== 'user') {
    chatPendingReply = false;
    hideChatTyping();
  }
}

async function sendChatMessage(e) {
  e.preventDefault();
  if (!chatInput || !chatAgentSelect) return;
  const text = chatInput.value.trim();
  if (!text) return;
  const to = currentChatAgent || chatAgentSelect.value;
  if (!to) {
    showToast('Select an agent first', 3000);
    return;
  }
  chatInput.value = '';
  chatInput.disabled = true;
  if (chatForm) chatForm.classList.add('sending');
  chatPendingReply = true;
  showChatTyping();
  try {
    socket.emit('chat_send', { to, message: text });
  } catch (err) {
    console.error('Error sending chat:', err);
    showToast('Could not send the message', 3000);
    chatPendingReply = false;
    hideChatTyping();
  } finally {
    setTimeout(() => {
      chatInput.disabled = false;
      chatInput.focus();
      if (chatForm) chatForm.classList.remove('sending');
    }, 400);
  }
}

/* ============================================================
   Design review modal
   ============================================================ */

function renderDesignReview(state) {
  const review = state && state.designReview;
  const active = review && !review.answered;

  if (!active) {
    closeDesignReviewModal();
    return;
  }

  if (designReviewDismissedId === review.id) return;

  if (designReviewActive && designReviewModal && designReviewModal.classList.contains('open')) {
    designReviewExpiresAt = new Date(review.expiresAt).getTime();
    return;
  }

  designReviewActive = true;
  designReviewExpiresAt = new Date(review.expiresAt).getTime();
  if (designReviewQuestions) designReviewQuestions.innerHTML = '';

  (review.questions || []).forEach((q, idx) => {
    const div = document.createElement('div');
    div.className = 'design-review-question';
    div.innerHTML = `
      <div class="design-review-question-label"><i data-lucide="help-circle"></i> Question ${idx + 1}</div>
      <p class="design-review-question-text">${escapeHtml(q.question)}</p>
      <input type="text" data-id="${escapeHtml(q.id)}" value="${escapeHtml(q.assumedAnswer || '')}" placeholder="Assumed answer...">
    `;
    if (designReviewQuestions) designReviewQuestions.appendChild(div);
  });
  if (window.lucide) lucide.createIcons();

  if (designReviewModal) designReviewModal.classList.add('open');
  startDesignReviewCountdown();
}

function dismissDesignReview() {
  const review = runState.designReview;
  if (review && !review.answered) designReviewDismissedId = review.id;
  closeDesignReviewModal();
}

function closeDesignReviewModal() {
  if (!designReviewActive) return;
  designReviewActive = false;
  if (designReviewModal) designReviewModal.classList.remove('open');
  if (designReviewCountdownInterval) {
    clearInterval(designReviewCountdownInterval);
    designReviewCountdownInterval = null;
  }
}

function startDesignReviewCountdown() {
  if (designReviewCountdownInterval) clearInterval(designReviewCountdownInterval);

  function update() {
    if (!designReviewCountdown || !designReviewExpiresAt) return;
    const remaining = Math.max(0, Math.ceil((designReviewExpiresAt - Date.now()) / 1000));
    const m = Math.floor(remaining / 60).toString().padStart(2, '0');
    const s = (remaining % 60).toString().padStart(2, '0');
    designReviewCountdown.textContent = `${m}:${s}`;
    if (remaining <= 0) {
      clearInterval(designReviewCountdownInterval);
      designReviewCountdownInterval = null;
      submitDesignReview(true);
    }
  }

  update();
  designReviewCountdownInterval = setInterval(update, 1000);
}

async function submitDesignReview(auto = false) {
  if (!designReviewActive) return;
  const inputs = designReviewQuestions ? designReviewQuestions.querySelectorAll('input') : [];
  const answers = {};
  inputs.forEach(input => { answers[input.dataset.id] = input.value.trim(); });

  if (!auto) {
    try {
      const res = await fetch('/api/design-review/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers })
      });
      if (!res.ok) throw new Error('Error enviando respuestas');
    } catch (err) {
      console.error(err);
      return;
    }
  }
  closeDesignReviewModal();
}

async function extendDesignReview() {
  try {
    const res = await fetch('/api/design-review/extend', { method: 'POST' });
    if (!res.ok) throw new Error('Error extendiendo tiempo');
    const data = await res.json();
    if (data.review && data.review.expiresAt) {
      designReviewExpiresAt = new Date(data.review.expiresAt).getTime();
      startDesignReviewCountdown();
    }
  } catch (err) {
    console.error(err);
  }
}

/* ============================================================
   Question modal
   ============================================================ */

const QUESTION_TIMEOUT_SECONDS = 120;

function startQuestionCountdown(expiresAtTimestamp) {
  if (questionCountdownInterval) clearInterval(questionCountdownInterval);

  function update() {
    if (!questionCountdown || !currentQuestion) return;
    const remaining = Math.max(0, Math.ceil(expiresAtTimestamp - Date.now() / 1000));
    const minutes = Math.floor(remaining / 60);
    const seconds = remaining % 60;
    questionCountdown.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    if (remaining <= 0) {
      clearInterval(questionCountdownInterval);
      questionCountdownInterval = null;
    }
  }

  update();
  questionCountdownInterval = setInterval(update, 1000);
}

function stopQuestionCountdown() {
  if (questionCountdownInterval) {
    clearInterval(questionCountdownInterval);
    questionCountdownInterval = null;
  }
}

function openQuestionModal(question) {
  if (!questionModal || !questionAgent || !questionText || !questionOptions) return;
  currentQuestion = question;
  const qAgentId = question.agentId || '';
  questionAgent.innerHTML = `<i data-lucide="${roleIcon(agentRoleById(qAgentId), qAgentId)}"></i> <span>${escapeHtml(stripEmojis(question.agentName || 'Agente'))}</span>`;
  questionText.textContent = question.question || '';
  questionContext.textContent = question.context || '';
  questionContext.style.display = question.context ? 'block' : 'none';
  questionOptions.innerHTML = '';
  if (questionCustom) questionCustom.style.display = 'none';
  if (questionAnswerInput) questionAnswerInput.value = '';

  const options = question.options || ['A', 'B'];
  options.forEach((opt, idx) => {
    const label = document.createElement('label');
    label.className = 'question-option';
    label.innerHTML = `<input type="radio" name="question-option" value="${escapeHtml(opt)}" ${idx === 0 ? 'checked' : ''}> <span>${escapeHtml(opt)}</span>`;
    questionOptions.appendChild(label);
  });

  const expiresAt = question.expiresAt || (Date.now() / 1000 + QUESTION_TIMEOUT_SECONDS);
  startQuestionCountdown(expiresAt);
  questionModal.classList.add('open');
  if (window.lucide) lucide.createIcons();
}

function closeQuestionModal() {
  if (!questionModal) return;
  questionModal.classList.remove('open');
  stopQuestionCountdown();
  currentQuestion = null;
}

function toggleCustomAnswer() {
  if (!questionCustom) return;
  const isHidden = questionCustom.style.display === 'none';
  questionCustom.style.display = isHidden ? 'block' : 'none';
  if (isHidden && questionAnswerInput) questionAnswerInput.focus();
}

async function submitQuestionAnswer() {
  if (!currentQuestion) return;
  let answer = '';
  if (questionCustom && questionCustom.style.display !== 'none') {
    answer = questionAnswerInput ? questionAnswerInput.value.trim() : '';
  } else {
    const selected = document.querySelector('input[name="question-option"]:checked');
    answer = selected ? selected.value : '';
  }
  if (!answer) {
    alert('Please select an option or write an answer.');
    return;
  }
  await sendQuestionResponse('/answer', { answer });
}

async function skipQuestion() {
  if (!currentQuestion) return;
  await sendQuestionResponse('/skip', {});
}

async function sendQuestionResponse(endpointSuffix, body) {
  if (!currentQuestion) return;
  if (btnQuestionSubmit) btnQuestionSubmit.disabled = true;
  if (btnQuestionSkip) btnQuestionSkip.disabled = true;
  if (btnQuestionSubmit) btnQuestionSubmit.textContent = 'Sending...';
  try {
    const res = await fetch(`/api/questions/${encodeURIComponent(currentQuestion.id)}${endpointSuffix}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Error sending response');
    }
    closeQuestionModal();
  } catch (err) {
    alert(err.message);
  } finally {
    if (btnQuestionSubmit) btnQuestionSubmit.disabled = false;
    if (btnQuestionSkip) btnQuestionSkip.disabled = false;
    if (btnQuestionSubmit) btnQuestionSubmit.textContent = 'Answer';
  }
}

async function loadPendingQuestions() {
  try {
    const res = await fetch('/api/questions?status=pending');
    if (!res.ok) return;
    const data = await res.json();
    const pending = (data.questions || []).filter(q => q.status === 'pending');
    if (pending.length > 0 && !currentQuestion) openQuestionModal(pending[0]);
  } catch (err) {
    console.warn('Error loading pending questions:', err);
  }
}

/* ============================================================
   Confirm modal
   ============================================================ */

function showConfirmModal({ title = 'Confirm', message = 'Are you sure?', okText = 'Confirm', cancelText = 'Cancel' } = {}) {
  return new Promise((resolve) => {
    if (!confirmModal) {
      resolve(false);
      return;
    }
    confirmModalResolve = resolve;
    if (confirmModalTitle) confirmModalTitle.textContent = title;
    if (confirmModalMessage) confirmModalMessage.textContent = message;
    if (btnConfirmOk) btnConfirmOk.textContent = okText;
    if (btnConfirmCancel) btnConfirmCancel.textContent = cancelText;
    confirmModal.classList.add('open');
  });
}

function closeConfirmModal(result = false) {
  if (confirmModal) confirmModal.classList.remove('open');
  if (confirmModalResolve) {
    confirmModalResolve(result);
    confirmModalResolve = null;
  }
}

/* ============================================================
   AI backend link modal
   ============================================================ */

function openAiLinkModal() {
  if (!aiLinkModal) return;
  aiLinkModalOpen = true;
  renderAiLinkModal();
  aiLinkModal.classList.add('open');
}

function closeAiLinkModal() {
  if (!aiLinkModal) return;
  aiLinkModalOpen = false;
  aiLinkModal.classList.remove('open');
}

function renderAiLinkModal() {
  if (!aiLinkList || !aiLinkNone) return;
  const backends = systemInfo.availableBackends || [];
  const available = backends.filter(b => b.available);

  if (available.length === 0) {
    aiLinkList.innerHTML = '';
    aiLinkNone.style.display = 'block';
    return;
  }

  aiLinkNone.style.display = 'none';
  aiLinkList.innerHTML = '';
  available.forEach(backend => {
    const item = document.createElement('div');
    item.className = 'ai-link-item';
    item.innerHTML = `
      <div class="ai-link-info">
        <strong>${escapeHtml(backend.displayName)}</strong>
        <span class="ai-link-meta">${escapeHtml(backend.reason)}</span>
      </div>
      <button type="button" class="btn-primary btn-small" data-backend="${escapeHtml(backend.name)}">Link</button>
    `;
    const btn = item.querySelector('button');
    btn.addEventListener('click', () => selectBackend(backend.name));
    aiLinkList.appendChild(item);
  });
}

async function selectBackend(name) {
  try {
    const res = await fetch('/api/backends/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ backend: name })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'Error linking backend');
    systemInfo.preferredBackend = name;
    showToast(`Linked ${name}`);
    renderHeader();
    closeAiLinkModal();
  } catch (err) {
    showToast(err.message, 4000);
  }
}

/* ============================================================
   PWA install & service worker
   ============================================================ */

function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  navigator.serviceWorker.register('/static/service-worker.js')
    .then(reg => console.log('Service Worker registered:', reg.scope))
    .catch(err => console.error('Service Worker registration failed:', err));
}

function handleBeforeInstallPrompt(e) {
  e.preventDefault();
  installPromptEvent = e;
  if (btnInstall) btnInstall.style.display = 'inline-flex';
}

async function installPwa() {
  if (!installPromptEvent) return;
  installPromptEvent.prompt();
  const { outcome } = await installPromptEvent.userChoice;
  if (outcome === 'accepted') {
    showToast('AgenticFlow installed');
  }
  installPromptEvent = null;
  if (btnInstall) btnInstall.style.display = 'none';
}

function showEngineOverlay(message, showHelp = false) {
  if (!engineOverlay) return;
  if (engineOverlayStatus) engineOverlayStatus.textContent = message || 'Connecting to local engine...';
  if (engineOverlayHelp) engineOverlayHelp.style.display = showHelp ? 'block' : 'none';
  if (btnRetryEngine) btnRetryEngine.style.display = showHelp ? 'inline-flex' : 'none';
  engineOverlay.classList.remove('hidden');
}

function hideEngineOverlay() {
  if (!engineOverlay) return;
  engineOverlay.classList.add('hidden');
}

function isPwaInstalled() {
  if (navigator.standalone === true) return true;
  if (!window.matchMedia) return false;
  const modes = ['standalone', 'minimal-ui', 'fullscreen', 'window-controls-overlay'];
  return modes.some(mode => window.matchMedia(`(display-mode: ${mode})`).matches);
}

function supportsFolderPicker() {
  return 'showDirectoryPicker' in window;
}

function showPwaInstallOverlay() {
  if (!pwaInstallOverlay) return;
  if (isPwaInstalled()) {
    hidePwaInstallOverlay();
    return;
  }
  pwaInstallOverlay.style.display = 'flex';
  const canInstall = Boolean(installPromptEvent);
  const canContinue = supportsFolderPicker();
  if (btnInstallPwaOverlay) btnInstallPwaOverlay.style.display = canInstall ? 'inline-flex' : 'none';
  if (btnContinueBrowser) btnContinueBrowser.style.display = canContinue ? 'inline-flex' : 'none';
  if (pwaInstallInstructions) pwaInstallInstructions.style.display = canContinue ? 'none' : 'block';
}

function hidePwaInstallOverlay() {
  if (!pwaInstallOverlay) return;
  pwaInstallOverlay.style.display = 'none';
}

async function installPwaFromOverlay() {
  if (!installPromptEvent) return;
  installPromptEvent.prompt();
  const { outcome } = await installPromptEvent.userChoice;
  if (outcome === 'accepted') {
    showToast('AgenticFlow installed');
    hidePwaInstallOverlay();
    bootAppCore();
  }
  installPromptEvent = null;
  if (btnInstall) btnInstall.style.display = 'none';
}

function continueInBrowser() {
  hidePwaInstallOverlay();
  bootAppCore();
}

async function checkBackend() {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    const res = await fetch('/api/health', { signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) throw new Error('health check failed');
    const data = await res.json();
    if (data.status !== 'ok') throw new Error('backend not ready');

    engineReady = true;
    hideEngineOverlay();
    systemInfo = {
      ...systemInfo,
      preferredBackend: data.preferredBackend,
      availableBackends: data.availableBackends,
    };
    renderHeader();
    if (!data.preferredBackend) {
      const available = (data.availableBackends || []).filter(b => b.available);
      if (available.length > 0 && !aiLinkModalOpen) openAiLinkModal();
    }
    return true;
  } catch (err) {
    engineReady = false;
    showEngineOverlay('Unable to reach the local engine', true);
    return false;
  }
}

/* ============================================================
   File System Access API helpers
   ============================================================ */

const FS_HANDLE_DB = 'agenticflow-fs';
const FS_HANDLE_STORE = 'repo-handles';

async function openFsHandleDb() {
  if (!('indexedDB' in window)) return null;
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(FS_HANDLE_DB, 1);
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(FS_HANDLE_STORE)) {
        db.createObjectStore(FS_HANDLE_STORE);
      }
    };
    request.onsuccess = (event) => resolve(event.target.result);
    request.onerror = () => reject(request.error);
  });
}

async function saveRepoHandle(handle) {
  const db = await openFsHandleDb();
  if (!db) return false;
  return new Promise((resolve) => {
    const tx = db.transaction(FS_HANDLE_STORE, 'readwrite');
    const store = tx.objectStore(FS_HANDLE_STORE);
    const request = store.put(handle, 'repo');
    request.onsuccess = () => resolve(true);
    request.onerror = () => resolve(false);
  });
}

async function loadRepoHandle() {
  const db = await openFsHandleDb();
  if (!db) return null;
  return new Promise((resolve) => {
    const tx = db.transaction(FS_HANDLE_STORE, 'readonly');
    const store = tx.objectStore(FS_HANDLE_STORE);
    const request = store.get('repo');
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => resolve(null);
  });
}

function updateRepoFolderBadge(name) {
  const badge = document.getElementById('repo-folder-badge');
  const nameEl = document.getElementById('repo-folder-name');
  if (!badge || !nameEl) return;
  if (name) {
    nameEl.textContent = name;
    badge.style.display = 'inline-flex';
  } else {
    badge.style.display = 'none';
  }
}

async function pickRepoFolder() {
  if (!('showDirectoryPicker' in window)) {
    showToast('Folder picker is only available in Chrome/Edge');
    return;
  }
  try {
    const handle = await window.showDirectoryPicker();
    repoFolderHandle = handle;
    updateRepoFolderBadge(handle.name);
    await saveRepoHandle(handle);

    // Verify that it looks like a Git repo by trying to access .git
    let isGitRepo = false;
    try {
      await handle.getDirectoryHandle('.git');
      isGitRepo = true;
    } catch {
      isGitRepo = false;
    }

    // The File System Access API does not expose absolute paths. If the user
    // configured a default projects root, auto-fill {root}/{folder-name}; otherwise
    // ask them to paste the absolute path manually.
    if (repoPathInput) {
      if (projectsRoot) {
        const separator = projectsRoot.endsWith('/') ? '' : '/';
        repoPathInput.value = `${projectsRoot}${separator}${handle.name}`;
      } else {
        repoPathInput.value = '';
        repoPathInput.placeholder = `Paste absolute path to "${handle.name}"`;
        repoPathInput.focus();
      }
    }

    const message = document.getElementById('repo-picker-message');
    if (message) {
      message.textContent = isGitRepo
        ? `Folder "${handle.name}" selected. Paste its absolute path above, then save the ticket.`
        : `Folder "${handle.name}" selected (no .git folder found). Paste its absolute path above, then save the ticket.`;
      message.style.display = 'block';
    }

    showToast(isGitRepo ? `Linked folder: ${handle.name}` : `Folder selected (not a git repo): ${handle.name}`);
  } catch (err) {
    if (err.name !== 'AbortError') {
      console.error('Error picking folder:', err);
      showToast('Could not access folder: ' + err.message, 4000);
    }
  }
}

async function pickRepoFolderNative() {
  try {
    const res = await fetch('/api/pick-folder', { method: 'POST' });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      showRepoMessage(data.error || 'Could not open system folder picker');
      return;
    }
    const data = await res.json();
    if (data.canceled) return;
    if (!data.ok || !data.path) {
      showRepoMessage(data.error || 'No folder selected');
      return;
    }
    if (repoPathInput) repoPathInput.value = data.path;
    updateRepoFolderBadge(data.path.split('/').pop() || data.path);
    showRepoMessage(`Selected: ${data.path}`);
    showToast(`Selected folder: ${data.path}`);
  } catch (err) {
    console.error('Error opening native folder picker:', err);
    showRepoMessage('Could not open system folder picker. Make sure the local engine is running.');
  }
}

async function restoreRepoFolderHandle() {
  const handle = await loadRepoHandle();
  if (!handle) return;
  try {
    // Re-request permission if needed.
    const permission = await handle.requestPermission({ mode: 'read' });
    if (permission !== 'granted') return;
    repoFolderHandle = handle;
    updateRepoFolderBadge(handle.name);
  } catch (err) {
    console.warn('Could not restore repo folder handle:', err);
  }
}

async function loadSystemInfo() {
  try {
    const res = await fetch('/api/system-info');
    if (!res.ok) return;
    systemInfo = await res.json();
    projectsRoot = systemInfo.projectsRoot || null;
    renderHeader();
    if (aiLinkModalOpen) renderAiLinkModal();
  } catch (err) {
    console.error('Error loading system-info:', err);
  }
}

/* ============================================================
   Agent restart / file actions
   ============================================================ */

async function restartAgent(agentId) {
  const ticketId = runState.ticketId;
  if (!ticketId) {
    await showConfirmModal({ title: 'No active ticket', message: 'There is no active ticket for restarting this agent.', okText: 'OK' });
    return;
  }
  const confirmed = await showConfirmModal({
    title: 'Restart agent',
    message: `Restart agent ${agentId}?`,
    okText: 'Restart',
    cancelText: 'Cancel'
  });
  if (!confirmed) return;
  try {
    const res = await fetch(`/api/tickets/${ticketId}/agents/${encodeURIComponent(agentId)}/restart`, { method: 'POST' });
    if (!res.ok) throw new Error(await res.text());
    showToast('Agent restarted');
  } catch (err) {
    console.error(err);
    await showConfirmModal({ title: 'Error', message: 'Could not restart the agent: ' + err.message, okText: 'OK' });
  }
}

async function openPath(path, folder = false) {
  if (!path) return;
  try {
    const res = await fetch('/api/open-path', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, folder })
    });
    if (!res.ok) throw new Error(await res.text());
  } catch (err) {
    console.error(err);
    alert('Could not open: ' + err.message);
  }
}

async function readFileContent(path) {
  if (!path) return null;
  try {
    const res = await fetch('/api/read-file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    return data.content || '';
  } catch (err) {
    console.error(err);
    alert('Could not read the file: ' + err.message);
    return null;
  }
}

/* ============================================================
   Run state handling
   ============================================================ */

function renderRunState(state) {
  runState = state || runState;
  if (runState.ticketId) setSelectedTicket(runState.ticketId);
  renderHeader();
  renderRunBar();
  renderTicketStatus();
  renderMessaging();
  renderChat();
  loadDeliverables();
  updateChatAgentSelect();
  renderDesignReview(runState);
  renderDebugFooter();
  renderTicketsList();
  if (window.lucide) lucide.createIcons();
}

async function pollRunState() {
  try {
    const res = await fetch('/api/run-state');
    if (!res.ok) return;
    const state = await res.json();
    renderRunState(state);
    if (!isConnected) updateConnectionStatus(true);
    lastFetchError = false;
  } catch (err) {
    if (!lastFetchError) {
      console.warn('Error loading run-state; retrying automatically.');
      lastFetchError = true;
    }
    updateConnectionStatus(false);
  }
}

/* ============================================================
   Event listeners
   ============================================================ */

if (btnThemeToggle) btnThemeToggle.addEventListener('click', toggleTheme);
if (btnTickets) btnTickets.addEventListener('click', openTicketsModal);
if (btnInstall) btnInstall.addEventListener('click', installPwa);
if (btnNewTicket) btnNewTicket.addEventListener('click', () => openTicketModal());

window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
if (btnNewTicketModal) btnNewTicketModal.addEventListener('click', () => openTicketModal());
if (btnCloseTickets) btnCloseTickets.addEventListener('click', closeTicketsModal);
if (btnCloseModal) btnCloseModal.addEventListener('click', closeTicketModal);
if (btnCancel) btnCancel.addEventListener('click', closeTicketModal);
if (btnDelete) btnDelete.addEventListener('click', deleteTicket);
if (ticketForm) ticketForm.addEventListener('submit', saveTicket);

if (repoPathInput) repoPathInput.addEventListener('input', hideRepoMessage);

const btnPickFolder = document.getElementById('btn-pick-folder');
const btnPickFolderNative = document.getElementById('btn-pick-folder-native');
if (btnPickFolder) btnPickFolder.addEventListener('click', pickRepoFolder);
if (btnPickFolderNative) btnPickFolderNative.addEventListener('click', pickRepoFolderNative);

if (btnSaveProjectsRoot) btnSaveProjectsRoot.addEventListener('click', saveProjectsRoot);
if (projectsRootInput) projectsRootInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') saveProjectsRoot(); });

if (btnInstallPwaOverlay) btnInstallPwaOverlay.addEventListener('click', installPwaFromOverlay);
if (btnContinueBrowser) btnContinueBrowser.addEventListener('click', () => {
  pwaOverlayDismissed = true;
  continueInBrowser();
});

window.addEventListener('appinstalled', () => {
  installPromptEvent = null;
  pwaOverlayDismissed = true;
  if (btnInstall) btnInstall.style.display = 'none';
  hidePwaInstallOverlay();
  bootAppCore();
});

if (btnQuestionCustom) btnQuestionCustom.addEventListener('click', toggleCustomAnswer);
if (btnQuestionSkip) btnQuestionSkip.addEventListener('click', skipQuestion);
if (btnQuestionSubmit) btnQuestionSubmit.addEventListener('click', submitQuestionAnswer);
if (questionModal) {
  questionModal.addEventListener('click', (e) => { if (e.target === questionModal) e.stopPropagation(); });
}

if (btnDesignReviewSubmit) btnDesignReviewSubmit.addEventListener('click', () => submitDesignReview(false));
if (btnDesignReviewExtend) btnDesignReviewExtend.addEventListener('click', extendDesignReview);
if (btnDesignReviewClose) btnDesignReviewClose.addEventListener('click', dismissDesignReview);
if (btnDesignReviewLater) btnDesignReviewLater.addEventListener('click', dismissDesignReview);

if (chatForm) chatForm.addEventListener('submit', sendChatMessage);
if (chatAgentSelect) {
  chatAgentSelect.addEventListener('change', () => {
    currentChatAgent = chatAgentSelect.value;
    lastRenderedChatKey = null;
    renderChat();
  });
}
if (btnRefreshDeliverables) btnRefreshDeliverables.addEventListener('click', () => {
  lastRenderedDeliverablesKey = null;
  loadDeliverables();
});
if (chatInput) {
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (chatForm) chatForm.dispatchEvent(new Event('submit'));
    }
  });
}

if (btnCloseCommunication) btnCloseCommunication.addEventListener('click', closeCommunicationPanel);
if (communicationBackdrop) communicationBackdrop.addEventListener('click', closeCommunicationPanel);

if (btnConfirmOk) btnConfirmOk.addEventListener('click', () => closeConfirmModal(true));
if (btnConfirmCancel) btnConfirmCancel.addEventListener('click', () => closeConfirmModal(false));
if (btnCloseConfirm) btnCloseConfirm.addEventListener('click', () => closeConfirmModal(false));
if (confirmModal) {
  confirmModal.addEventListener('click', (e) => { if (e.target === confirmModal) closeConfirmModal(false); });
}

if (btnAiLinkLater) btnAiLinkLater.addEventListener('click', closeAiLinkModal);
if (aiLinkModal) {
  aiLinkModal.addEventListener('click', (e) => { if (e.target === aiLinkModal) closeAiLinkModal(); });
}

if (btnRetryEngine) btnRetryEngine.addEventListener('click', () => {
  showEngineOverlay('Connecting to local engine...', false);
  checkBackend().then(ok => {
    if (ok) {
      loadSystemInfo();
      fetch('/api/board')
        .then(r => r.json())
        .then(data => { boardData = data; renderTicketsList(); renderHeader(); renderRunBar(); renderTicketStatus(); })
        .catch(err => console.error('Error loading board:', err));
      pollRunState();
      pollTraces();
      pollGraph();
    }
  });
});

// Close modals on backdrop click
[ticketsModal, ticketModal].forEach(modal => {
  if (modal) {
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('open'); });
  }
});

/* ============================================================
   Socket events
   ============================================================ */

socket.on('connect', () => {
  updateConnectionStatus(true);
  socket.emit('request_update');
});

socket.on('disconnect', () => updateConnectionStatus(false));
socket.on('connect_error', () => updateConnectionStatus(false));
socket.on('reconnect', () => updateConnectionStatus(true));

socket.on('board_update', (data) => {
  boardData = data;
  renderTicketsList();
  renderHeader();
  renderRunBar();
  renderTicketStatus();
});

socket.on('run_state_update', (state) => {
  renderRunState(state);
});

socket.on('pending_question', (question) => {
  if (question && question.status === 'pending' && !currentQuestion) openQuestionModal(question);
});

socket.on('question_answered', (question) => {
  if (currentQuestion && currentQuestion.id === question.id) closeQuestionModal();
  loadPendingQuestions();
});

socket.on('communication_update', (communication) => {
  runState.communication = communication;
  renderMessaging();
  renderChat();
  updateChatAgentSelect();
  checkChatReplyReceived();
});

socket.on('chat_message', (entry) => {
  if (entry && runState.communication) {
    runState.communication.log = runState.communication.log || [];
    runState.communication.log.push(entry);
    renderMessaging();
    renderChat();
    updateChatAgentSelect();
  }
});

/* ============================================================
   Initialization
   ============================================================ */

initTheme();
loadPendingQuestions();
registerServiceWorker();
restoreRepoFolderHandle();

async function bootAppCore() {
  const ok = await checkBackend();
  if (!ok) return;

  await loadSystemInfo();

  fetch('/api/board')
    .then(r => r.json())
    .then(data => { boardData = data; renderTicketsList(); renderHeader(); renderRunBar(); renderTicketStatus(); })
    .catch(err => console.error('Error loading board:', err));

  pollRunState();
  pollTraces();
  pollGraph();
}

function bootApp() {
  if (isPwaInstalled() || pwaOverlayDismissed) {
    hidePwaInstallOverlay();
    bootAppCore();
    return;
  }
  showPwaInstallOverlay();
}

bootApp();

setInterval(async () => {
  if (!isPwaInstalled() && !pwaOverlayDismissed) {
    showPwaInstallOverlay();
    return;
  }
  if (!engineReady) {
    await checkBackend();
  }
}, 3000);

setInterval(pollRunState, 2000);
setInterval(pollTraces, 2000);
setInterval(pollGraph, 5000);

// Re-layout graph on resize
let resizeTimeout;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimeout);
  resizeTimeout = setTimeout(() => {
    lastRenderedGraphKey = null;
    renderBehaviorsGraph();
  }, 150);
});
