/* ============================================================
   AgentFlow Dashboard — Adaline-inspired frontend
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
let systemInfo = { model: '—' };
let traces = [];
let graphData = { nodes: [], edges: [] };

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

let lastRenderedTracesKey = null;
let lastRenderedGraphKey = null;
let lastRenderedDebugKey = null;
let lastRenderedRunKey = null;

// DOM refs
const btnThemeToggle = document.getElementById('btn-theme-toggle');
const btnTickets = document.getElementById('btn-tickets');
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
const repoPicker = document.getElementById('ticket-repo-picker');
const btnPickRepo = document.getElementById('btn-pick-repo');
const repoPickerMessage = document.getElementById('repo-picker-message');

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
  idle: 'Sin actividad',
  running: 'En ejecución',
  paused: 'Pausado',
  queued: 'En cola'
};

function renderHeader() {
  if (navModel) navModel.textContent = systemInfo.model || '—';
  if (navTicket) navTicket.textContent = runState.ticketId || '—';

  let statusKey = 'idle';
  if (runState.active) {
    statusKey = runState.status === 'paused' ? 'paused' : 'running';
  } else if ((runState.queue || []).length > 0) {
    statusKey = 'queued';
  }

  if (navStatus) {
    navStatus.textContent = STATUS_LABELS[statusKey];
    navStatus.className = 'pill-value status-' + statusKey;
  }

  if (navPath) {
    const activeTicket = (boardData.tickets || []).find(t => t.id === runState.ticketId);
    const repoPath = activeTicket && activeTicket.repoPath ? activeTicket.repoPath : '';
    navPath.textContent = repoPath ? truncatePath(repoPath, 55) : '—';
    navPath.title = repoPath || 'Sin ruta de repo';
  }
}

function renderRunBar() {
  if (!runBar) return;

  const active = runState.active;
  const ticketId = runState.ticketId || '—';
  const statusKey = active ? (runState.status || 'running') : 'idle';
  const agents = runState.agents || [];
  const running = agents.filter(a => a.status === 'running').length;
  const total = agents.length;
  const progress = total > 0 ? Math.round((agents.filter(a => a.status === 'done').length / total) * 100) : 0;

  runBar.classList.toggle('idle', !active);
  if (runBarTicket) runBarTicket.textContent = ticketId;
  if (runBarStatus) {
    runBarStatus.textContent = STATUS_LABELS[statusKey] || statusKey;
    runBarStatus.className = 'run-bar-status ' + statusKey;
  }
  if (runBarProgress) runBarProgress.style.width = `${progress}%`;
  if (runBarElapsed) runBarElapsed.textContent = formatElapsed(runState.elapsedSeconds);
  if (runBarAgents) runBarAgents.textContent = `${running}/${total} running`;
}

function updateConnectionStatus(connected) {
  isConnected = connected;
  if (!navConnection) return;
  navConnection.classList.toggle('online', connected);
  navConnection.classList.toggle('offline', !connected);
  navConnection.innerHTML = connected
    ? '<i data-lucide="wifi" class="status-icon"></i>'
    : '<i data-lucide="wifi-off" class="status-icon"></i>';
  navConnection.title = connected ? 'Conectado al servidor (WebSocket)' : 'Desconectado; reconectando...';
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
    console.warn('Error cargando traces:', err);
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

  const key = JSON.stringify({ nodes: nodes.map(n => [n.id, n.status, n.progress]), edges: edges.map(e => [e.source, e.target, e.type]) });
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
  const arrowFill = isDark ? 'rgba(255,255,255,0.25)' : 'rgba(46,67,32,0.35)';
  const activeStroke = isDark ? 'rgba(96,165,250,0.8)' : 'rgba(36,90,120,0.8)';
  const defaultStroke = isDark ? 'rgba(255,255,255,0.14)' : 'rgba(46,67,32,0.18)';

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
    <marker id="arrow-head" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="${arrowFill}" /></marker>
    <marker id="arrow-head-active" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="${activeStroke}" /></marker>
  </defs>`;

  const byId = {};
  nodes.forEach(n => byId[n.id] = n);

  function curve(p1, p2, type = 'parent', sourceRadius = 0, targetRadius = 0) {
    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    const dist = Math.hypot(dx, dy);
    if (dist === 0) {
      return `M ${p1.x.toFixed(1)} ${p1.y.toFixed(1)} C ${p1.x.toFixed(1)} ${p1.y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
    }
    const ux = dx / dist;
    const uy = dy / dist;
    // Trim the curve so it starts/ends at the node border instead of the center.
    const start = { x: p1.x + ux * sourceRadius, y: p1.y + uy * sourceRadius };
    const end = { x: p2.x - ux * targetRadius, y: p2.y - uy * targetRadius };
    const newDx = end.x - start.x;
    const newDy = end.y - start.y;
    // Message edges get a slight sideways curve so bidirectional messages don't overlap.
    const sideOffset = type === 'message' ? Math.sign(newDx || 1) * Math.min(40, Math.abs(newDx) * 0.15 + 20) : 0;
    const c1 = { x: start.x + sideOffset, y: start.y + newDy * 0.5 };
    const c2 = { x: end.x + sideOffset, y: end.y - newDy * 0.5 };
    return `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} C ${c1.x.toFixed(1)} ${c1.y.toFixed(1)}, ${c2.x.toFixed(1)} ${c2.y.toFixed(1)}, ${end.x.toFixed(1)} ${end.y.toFixed(1)}`;
  }

  const nodeRadii = {};
  nodes.forEach(node => {
    const baseSize = node.role === 'orchestrator' ? 56 : node.role === 'lead' ? 48 : 40;
    const size = Math.max(26, Math.round(baseSize * (nodeDiameter / 48)));
    nodeRadii[node.id] = size / 2;
  });

  edges.forEach((e, i) => {
    const s = positions[e.source];
    const t = positions[e.target];
    if (!s || !t) return;
    const sourceNode = byId[e.source];
    const targetNode = byId[e.target];
    const sourceRadius = nodeRadii[e.source] || nodeDiameter / 2;
    const targetRadius = nodeRadii[e.target] || nodeDiameter / 2;
    const isActive = sourceNode && targetNode && (sourceNode.status === 'running' || targetNode.status === 'running');
    const stroke = isActive ? activeStroke : defaultStroke;
    const marker = isActive ? 'url(#arrow-head-active)' : 'url(#arrow-head)';
    const pathId = `graph-edge-${i}`;
    const width = e.type === 'parent' ? (isActive ? 2.5 : 1.5) : 1.5;
    const isMessage = e.type === 'message';
    const dash = isMessage ? '2,5' : 'none';
    const dashAnimate = isMessage ? '<animate attributeName="stroke-dashoffset" from="0" to="-14" dur="1s" repeatCount="indefinite" />' : '';
    svgHtml += `<path id="${pathId}" d="${curve(s, t, e.type, sourceRadius, targetRadius)}" fill="none" stroke="${stroke}" stroke-width="${width}" stroke-dasharray="${dash}" stroke-linecap="round" marker-end="${marker}">${dashAnimate}</path>`;
    if (isActive) {
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
      <div class="graph-node-bubble ${statusClass}" style="width:${size}px;height:${size}px;font-size:${Math.max(9, size / 4)}px;" title="${escapeHtml(stripEmojis(node.name))} (${node.status})" role="button" tabindex="0" aria-label="Agente ${escapeHtml(stripEmojis(node.name))}">
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
    console.warn('Error cargando graph:', err);
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
    debugLog.innerHTML = '<div class="debug-empty">Sin logs recientes</div>';
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
    debugMeta.textContent = `${total} agente${total !== 1 ? 's' : ''} · ${active} running · ${tail.length} logs`;
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
    ticketsList.innerHTML = '<div class="tickets-empty">No hay tickets. Crea uno nuevo para empezar.</div>';
    return;
  }

  ticketsList.innerHTML = '';
  tickets.slice().reverse().forEach(ticket => {
    const runStatus = getTicketRunStatus(ticket.id);
    const runIcon = runStatusIcon(runStatus);
    const isRunnable = ['idle', 'queued', 'paused'].includes(runStatus) && ['backlog', 'ready-for-work', 'in-design', 'in-progress', 'in-review'].includes(ticket.status);
    const showRestart = ['ready-for-work', 'in-design', 'in-progress', 'in-review', 'done'].includes(ticket.status);
    const runAction = runStatus === 'running'
      ? `<button type="button" class="btn-icon btn-small ticket-action-pause" data-id="${escapeHtml(ticket.id)}" title="Pausar"><i data-lucide="pause"></i></button>`
      : isRunnable
        ? `<button type="button" class="btn-icon btn-small ticket-action-play" data-id="${escapeHtml(ticket.id)}" title="${runStatus === 'paused' ? 'Reanudar' : 'Ejecutar'}"><i data-lucide="play"></i></button>`
        : '';
    const restartAction = showRestart
      ? `<button type="button" class="btn-icon btn-small ticket-action-restart" data-id="${escapeHtml(ticket.id)}" title="Reiniciar desde cero"><i data-lucide="refresh-cw"></i></button>`
      : '';

    const row = document.createElement('div');
    row.className = 'ticket-row ticket-row-' + runStatus;
    row.innerHTML = `
      <span class="ticket-row-run-status" title="${runStatus}"><i data-lucide="${runIcon}"></i></span>
      <span class="ticket-row-id">${escapeHtml(ticket.id)}</span>
      <span class="ticket-row-title" title="${escapeHtml(ticket.title)}">${escapeHtml(ticket.title)}</span>
      <span class="ticket-row-status status-${ticket.status}">${COLUMN_LABELS[ticket.status] || ticket.status}</span>
      <div class="ticket-row-actions">
        ${runAction}
        ${restartAction}
        <button type="button" class="btn-icon btn-small" title="Editar"><i data-lucide="pencil"></i></button>
        <button type="button" class="btn-icon btn-small" title="Eliminar"><i data-lucide="trash-2"></i></button>
      </div>
    `;
    row.querySelector('[title="Editar"]').addEventListener('click', (e) => {
      e.stopPropagation();
      openTicketModal(ticket);
    });
    row.querySelector('[title="Eliminar"]').addEventListener('click', (e) => {
      e.stopPropagation();
      deleteTicketById(ticket.id);
    });
    const playBtn = row.querySelector('.ticket-action-play');
    if (playBtn) playBtn.addEventListener('click', (e) => { e.stopPropagation(); playTicket(ticket.id); });
    const pauseBtn = row.querySelector('.ticket-action-pause');
    if (pauseBtn) pauseBtn.addEventListener('click', (e) => { e.stopPropagation(); pauseTicket(ticket.id); });
    const restartBtn = row.querySelector('.ticket-action-restart');
    if (restartBtn) restartBtn.addEventListener('click', (e) => { e.stopPropagation(); restartTicket(ticket.id); });
    ticketsList.appendChild(row);
  });
  if (window.lucide) lucide.createIcons();
}

function getTicketRunStatus(ticketId) {
  if (runState.ticketId === ticketId) {
    return runState.active ? 'running' : 'paused';
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
    title: 'Reiniciar ticket',
    message: `¿Reiniciar el ticket ${ticketId} desde cero?\n\nSe borrarán el progreso del run, snapshots y los artefactos generados (PRD, plan de tareas, arquitectura). Los cambios de código en el repositorio no se eliminarán.`,
    okText: 'Reiniciar',
    cancelText: 'Cancelar',
  });
  if (!confirmed) return;
  try {
    const res = await fetch(`/api/tickets/${ticketId}/restart`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || 'Error');
    showToast(data.message || 'Ticket reiniciado');
  } catch (err) {
    showToast('Error reiniciando ticket: ' + err.message, 4000);
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
  if (modalTitle) modalTitle.textContent = isEdit ? 'Editar ticket' : 'Nuevo ticket';
  document.getElementById('ticket-id').value = ticket ? ticket.id : '';
  document.getElementById('ticket-title').value = ticket ? ticket.title : '';
  document.getElementById('ticket-description').value = ticket ? ticket.description || '' : '';
  document.getElementById('ticket-status').value = ticket ? ticket.status : 'backlog';
  document.getElementById('ticket-role').value = ticket ? ticket.assigneeRole || '' : '';
  document.getElementById('ticket-focus').value = ticket ? ticket.featureFocus || '' : '';
  document.getElementById('ticket-labels').value = ticket ? (ticket.labels || []).join(', ') : '';
  repoPathInput.value = ticket ? ticket.repoPath || '' : '';
  if (btnDelete) btnDelete.style.display = isEdit ? 'inline-block' : 'none';
  if (ticketModal) ticketModal.classList.add('open');
  closeTicketsModal();
}

function closeTicketModal() {
  if (ticketModal) ticketModal.classList.remove('open');
  if (ticketForm) ticketForm.reset();
}

async function saveTicket(e) {
  e.preventDefault();
  const id = document.getElementById('ticket-id').value;
  const payload = {
    title: document.getElementById('ticket-title').value,
    description: document.getElementById('ticket-description').value,
    status: document.getElementById('ticket-status').value,
    repoPath: repoPathInput.value.trim(),
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
    if (!res.ok) throw new Error('Error guardando ticket');
    closeTicketModal();
    showToast(id ? 'Ticket actualizado' : 'Ticket creado');
  } catch (err) {
    alert(err.message);
  }
}

async function deleteTicket() {
  const id = document.getElementById('ticket-id').value;
  if (!id) return;
  if (!confirm('¿Eliminar este ticket?')) return;
  await deleteTicketById(id);
  closeTicketModal();
}

async function deleteTicketById(id) {
  try {
    const res = await fetch(`/api/tickets/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Error eliminando ticket');
    showToast('Ticket eliminado');
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

/* ============================================================
   Ticket status & messaging
   ============================================================ */

function renderTicketStatus() {
  if (!ticketStatusBody) return;

  const activeTicket = runState.ticketId ? { id: runState.ticketId, status: runState.status } : null;
  const agents = runState.agents || [];

  if (!activeTicket && agents.length === 0) {
    ticketStatusBody.innerHTML = '<div class="status-empty">No hay ticket seleccionado</div>';
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
        <span class="value">${escapeHtml(runState.ticketId || '—')}</span>
      </div>
      <div class="status-card-row">
        <span>Estado</span>
        <span class="status-badge status-${runState.status || 'idle'}">${runState.status || 'idle'}</span>
      </div>
      <div class="status-card-row">
        <span>Progreso</span>
        <span class="value">${progress}%</span>
      </div>
      <div class="status-card-row">
        <span>Tiempo</span>
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
  const messages = runState.messages || [];
  if (!messages.length) {
    messagingFeed.innerHTML = '<div class="messaging-empty">No internal messages yet...</div>';
    return;
  }

  messagingFeed.innerHTML = '';
  messages.slice().reverse().forEach(msg => {
    const el = document.createElement('div');
    el.className = 'comm-item';
    const answeredAt = msg.answeredAt ? formatTime(msg.answeredAt) : '';
    const answerBlock = msg.answer
      ? `<div class="comm-item-answer"><strong>${escapeHtml(stripEmojis(msg.to))}:</strong> ${escapeHtml(stripEmojis(msg.answer))}</div>`
      : '<div class="comm-item-answer">Esperando respuesta...</div>';
    el.innerHTML = `
      <div class="comm-item-header">
        <span>${escapeHtml(stripEmojis(msg.from))} → ${escapeHtml(stripEmojis(msg.to))}</span>
        <span>${formatTime(msg.timestamp)}</span>
      </div>
      <div class="comm-item-body">${escapeHtml(stripEmojis(msg.question))}</div>
      ${answerBlock}
      ${answeredAt ? `<div class="comm-item-answer">Respondido ${answeredAt}</div>` : ''}
    `;
    messagingFeed.appendChild(el);
  });

  const nearBottom = messagingFeed.scrollHeight - messagingFeed.scrollTop - messagingFeed.clientHeight < 80;
  if (nearBottom) messagingFeed.scrollTop = messagingFeed.scrollHeight;
}

/* ============================================================
   Chat panel
   ============================================================ */

const DEFAULT_CHAT_AGENTS = [
  { id: 'orchestrator', name: 'Orchestrator Principal' },
  { id: 'product_manager', name: 'Product Manager' },
  { id: 'architect', name: 'Architect' },
  { id: 'project_manager', name: 'Project Manager' },
  { id: 'engineer', name: 'Engineer' },
  { id: 'qa', name: 'QA Engineer' },
  { id: 'recovery', name: 'Recovery' },
];

function updateChatAgentSelect() {
  if (!chatAgentSelect) return;
  const currentValue = chatAgentSelect.value;
  const agents = runState.agents || [];
  const known = new Map();
  DEFAULT_CHAT_AGENTS.forEach(a => known.set(a.id, a.name));
  agents.forEach(a => {
    if (!known.has(a.id)) known.set(a.id, a.name || a.id);
  });

  const participants = (runState.communication && runState.communication.participants) || {};
  Object.entries(participants).forEach(([id, profile]) => {
    if (!known.has(id)) known.set(id, profile.name || id);
  });

  chatAgentSelect.innerHTML = '';
  Array.from(known.entries()).forEach(([id, name]) => {
    const option = document.createElement('option');
    option.value = id;
    option.textContent = name;
    chatAgentSelect.appendChild(option);
  });
  if (known.has(currentValue)) chatAgentSelect.value = currentValue;
}

let lastRenderedChatKey = null;

function renderChat() {
  if (!chatMessages) return;
  const comm = runState.communication || {};
  const log = (comm.log || []).filter(e => e.type === 'message' && e.messageType === 'chat');

  const key = log.map(e => `${e.timestamp}|${e.from}|${e.to}|${JSON.stringify(e.payload)}`).join('//');
  if (key === lastRenderedChatKey) return;
  lastRenderedChatKey = key;

  if (!log.length) {
    chatMessages.innerHTML = '<div class="chat-empty">Selecciona un agente y escribe un mensaje o instrucción.</div>';
    return;
  }

  chatMessages.innerHTML = '';
  log.forEach(entry => {
    const from = entry.from || 'system';
    const text = (entry.payload && entry.payload.text) || '';
    const side = from === 'user' ? 'user' : (from === 'system' ? 'system' : 'agent');
    const displayName = from === 'user' ? 'Tú' : (from === 'system' ? 'Sistema' : stripEmojis(from));

    const el = document.createElement('div');
    el.className = `chat-message ${side}`;
    el.innerHTML = `
      <div class="chat-bubble">${escapeHtml(text)}</div>
      <div class="chat-meta">
        <span>${escapeHtml(displayName)}</span>
        <span>${formatTime(entry.timestamp)}</span>
      </div>
    `;
    chatMessages.appendChild(el);
  });

  const nearBottom = chatMessages.scrollHeight - chatMessages.scrollTop - chatMessages.clientHeight < 80;
  if (nearBottom) chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendChatMessage(e) {
  e.preventDefault();
  if (!chatInput || !chatAgentSelect) return;
  const text = chatInput.value.trim();
  if (!text) return;
  const to = chatAgentSelect.value || 'orchestrator';
  chatInput.value = '';
  chatInput.disabled = true;
  if (chatForm) chatForm.classList.add('sending');
  try {
    socket.emit('chat_send', { to, message: text });
  } catch (err) {
    console.error('Error enviando chat:', err);
    showToast('No se pudo enviar el mensaje', 3000);
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
      <div class="design-review-question-label"><i data-lucide="help-circle"></i> Pregunta ${idx + 1}</div>
      <p class="design-review-question-text">${escapeHtml(q.question)}</p>
      <input type="text" data-id="${escapeHtml(q.id)}" value="${escapeHtml(q.assumedAnswer || '')}" placeholder="Respuesta asumida...">
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
    alert('Por favor selecciona una opción o escribe una respuesta.');
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
  if (btnQuestionSubmit) btnQuestionSubmit.textContent = 'Enviando...';
  try {
    const res = await fetch(`/api/questions/${encodeURIComponent(currentQuestion.id)}${endpointSuffix}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Error enviando respuesta');
    }
    closeQuestionModal();
  } catch (err) {
    alert(err.message);
  } finally {
    if (btnQuestionSubmit) btnQuestionSubmit.disabled = false;
    if (btnQuestionSkip) btnQuestionSkip.disabled = false;
    if (btnQuestionSubmit) btnQuestionSubmit.textContent = 'Responder';
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
    console.warn('Error cargando preguntas pendientes:', err);
  }
}

/* ============================================================
   Confirm modal
   ============================================================ */

function showConfirmModal({ title = 'Confirmar', message = '¿Estás seguro?', okText = 'Confirmar', cancelText = 'Cancelar' } = {}) {
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
   Agent restart / file actions
   ============================================================ */

async function restartAgent(agentId) {
  const ticketId = runState.ticketId;
  if (!ticketId) {
    await showConfirmModal({ title: 'Sin ticket activo', message: 'No hay un ticket activo para reiniciar el agente.', okText: 'Aceptar' });
    return;
  }
  const confirmed = await showConfirmModal({
    title: 'Reiniciar agente',
    message: `¿Reiniciar agente ${agentId}?`,
    okText: 'Reiniciar',
    cancelText: 'Cancelar'
  });
  if (!confirmed) return;
  try {
    const res = await fetch(`/api/tickets/${ticketId}/agents/${encodeURIComponent(agentId)}/restart`, { method: 'POST' });
    if (!res.ok) throw new Error(await res.text());
    showToast('Agente reiniciado');
  } catch (err) {
    console.error(err);
    await showConfirmModal({ title: 'Error', message: 'No se pudo reiniciar el agente: ' + err.message, okText: 'Aceptar' });
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
    alert('No se pudo abrir: ' + err.message);
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
    alert('No se pudo leer el archivo: ' + err.message);
    return null;
  }
}

/* ============================================================
   Run state handling
   ============================================================ */

function renderRunState(state) {
  runState = state || runState;
  renderHeader();
  renderRunBar();
  renderTicketStatus();
  renderMessaging();
  renderChat();
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
      console.warn('Error cargando run-state; se reintentará automáticamente.');
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
if (btnNewTicket) btnNewTicket.addEventListener('click', () => openTicketModal());
if (btnNewTicketModal) btnNewTicketModal.addEventListener('click', () => openTicketModal());
if (btnCloseTickets) btnCloseTickets.addEventListener('click', closeTicketsModal);
if (btnCloseModal) btnCloseModal.addEventListener('click', closeTicketModal);
if (btnCancel) btnCancel.addEventListener('click', closeTicketModal);
if (btnDelete) btnDelete.addEventListener('click', deleteTicket);
if (ticketForm) ticketForm.addEventListener('submit', saveTicket);

if (btnPickRepo && repoPicker) {
  btnPickRepo.addEventListener('click', () => repoPicker.click());
  repoPathInput.addEventListener('input', hideRepoMessage);
  repoPicker.addEventListener('change', (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const file = files[0];
    if (file.path) {
      repoPathInput.value = file.path;
      hideRepoMessage();
    } else if (file.webkitRelativePath) {
      const topFolder = file.webkitRelativePath.split('/')[0];
      showRepoMessage(`Seleccionaste "${topFolder}". El navegador no entrega la ruta absoluta; escríbela en el campo Repo folder.`);
      repoPathInput.focus();
    }
    repoPicker.value = '';
  });
}

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
  renderChat();
  updateChatAgentSelect();
});

socket.on('chat_message', (entry) => {
  if (entry && runState.communication) {
    runState.communication.log = runState.communication.log || [];
    runState.communication.log.push(entry);
    renderChat();
    updateChatAgentSelect();
  }
});

/* ============================================================
   Initialization
   ============================================================ */

initTheme();
loadPendingQuestions();

fetch('/api/system-info')
  .then(r => r.json())
  .then(info => { systemInfo = info; renderHeader(); })
  .catch(err => console.error('Error cargando system-info:', err));

fetch('/api/board')
  .then(r => r.json())
  .then(data => { boardData = data; renderTicketsList(); renderHeader(); })
  .catch(err => console.error('Error cargando board:', err));

pollRunState();
pollTraces();
pollGraph();

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
