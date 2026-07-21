/* =========================================================
   CronDock — app.js
   ========================================================= */

// ── State ──────────────────────────────────────────────────────────────────

let _jobs = [];
let _settings = [];
let _currentJobType = 'http';
let _editingJobId = null;
let _editingSettingKey = null;
let _countdownInterval = null;
let _pendingDeleteJobId = null;
let _pendingDeleteSettingKey = null;

// ── Init ───────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadUser();
  loadJobs();
  loadSettings();
  setInterval(loadJobs, 15000);   // auto-refresh every 15s
  startCountdowns();
});

async function loadUser() {
  try {
    const user = await api('GET', '/api/me');
    const nameEl  = document.getElementById('user-name');
    const emailEl = document.getElementById('user-email');
    if (nameEl)  nameEl.textContent  = user.name || user.username || user.email || 'User';
    if (emailEl) emailEl.textContent = user.email || '';
  } catch (e) {
    // If 401, middleware will redirect — nothing to do here
  }
}

// ── Navigation ─────────────────────────────────────────────────────────────

function showSection(name) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById(`section-${name}`).classList.add('active');
  document.getElementById(`nav-${name}`).classList.add('active');
  if (name === 'settings') loadSettings();
}

// ── API helpers ────────────────────────────────────────────────────────────

async function api(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ── Jobs ───────────────────────────────────────────────────────────────────

async function loadJobs() {
  try {
    _jobs = await api('GET', '/api/jobs');
    renderJobs();
  } catch (e) {
    console.error('Failed to load jobs', e);
  }
}

async function refreshJobs() {
  const btn = document.getElementById('refresh-btn');
  btn.innerHTML = '<span class="spinner"></span>';
  await loadJobs();
  btn.innerHTML = '↻ Refresh';
}

function renderJobs() {
  const grid = document.getElementById('jobs-grid');
  const footer = document.getElementById('job-count-footer');
  const enabled = _jobs.filter(j => j.enabled).length;
  footer.textContent = `${_jobs.length} jobs · ${enabled} active`;

  if (_jobs.length === 0) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1;">
        <div class="empty-icon">🕐</div>
        <h3>No jobs yet</h3>
        <p>Create your first cron job to get started.</p>
      </div>`;
    return;
  }

  grid.innerHTML = _jobs.map(job => jobCard(job)).join('');
}

function jobCard(job) {
  const typeBadge = job.type === 'http'
    ? `<span class="badge badge-http">HTTP</span>`
    : `<span class="badge badge-shell">Shell</span>`;

  const statusBadge = job.enabled
    ? `<span class="badge badge-enabled"><span class="status-dot dot-success"></span> Enabled</span>`
    : `<span class="badge badge-disabled">Disabled</span>`;

  let lastRunHtml = `<span class="status-dot dot-pending"></span> Never run`;
  if (job.last_run_at) {
    const dot = job.last_run_success
      ? `<span class="status-dot dot-success"></span>`
      : `<span class="status-dot dot-fail"></span>`;
    const ago = timeAgo(job.last_run_at);
    lastRunHtml = `${dot} ${job.last_run_success ? 'Success' : 'Failed'} · ${ago}`;
  }

  const nextRun = job.next_run_at
    ? `<span class="next-run">⏭ Next: <span class="countdown" data-target="${job.next_run_at}"></span></span>`
    : `<span class="next-run" style="color:var(--muted);">⏭ Not scheduled</span>`;

  const scheduleHuman = describeCron(job.schedule);

  const cardClass = job.enabled ? 'job-card' : 'job-card disabled';

  const deleteBtn = _pendingDeleteJobId === job.id
    ? `<div class="confirm-row">
        <span class="question">Sure?</span>
        <button class="btn btn-danger btn-sm" onclick="confirmDeleteJob(${job.id})">Yes, delete</button>
        <button class="btn btn-ghost btn-sm" onclick="cancelDeleteJob(${job.id})">No</button>
      </div>`
    : `<button class="btn btn-ghost btn-sm" onclick="promptDeleteJob(${job.id})">🗑 Delete</button>`;

  const toggleLabel = job.enabled ? '⏸ Disable' : '▶ Enable';

  return `
    <div class="${cardClass}" id="job-card-${job.id}">
      <div class="card-header">
        <div class="card-name">${esc(job.name)}</div>
        <div style="display:flex;gap:6px;flex-shrink:0;">
          ${typeBadge}
          ${statusBadge}
        </div>
      </div>
      ${job.description ? `<div class="card-desc">${esc(job.description)}</div>` : ''}
      <div class="card-meta">
        <span class="schedule-chip">⏱ ${esc(job.schedule)}</span>
        <span class="meta-item" title="${job.schedule}">— ${scheduleHuman}</span>
      </div>
      <div class="card-meta">
        <div class="meta-item"><span class="label">Last run:</span> ${lastRunHtml}</div>
      </div>
      ${nextRun}
      <div class="card-actions">
        <button class="btn btn-success btn-sm" onclick="runJobNow(${job.id}, '${esc(job.name)}')">▶ Run Now</button>
        <button class="btn btn-ghost btn-sm" onclick="openLogModal(${job.id}, '${esc(job.name)}')">📄 Logs</button>
        <button class="btn btn-ghost btn-sm" onclick="openJobDrawer(${job.id})">✏ Edit</button>
        <button class="btn btn-ghost btn-sm" onclick="toggleJob(${job.id}, ${job.enabled})">${toggleLabel}</button>
        ${deleteBtn}
      </div>
    </div>`;
}

async function runJobNow(jobId, name) {
  try {
    await api('POST', `/api/jobs/${jobId}/run`);
    toast(`▶ "${name}" triggered`, 'success');
    setTimeout(() => loadJobs(), 3000);
  } catch (e) {
    toast(`Error: ${e.message}`, 'error');
  }
}

async function toggleJob(jobId, currentEnabled) {
  try {
    await api('PUT', `/api/jobs/${jobId}`, { enabled: !currentEnabled });
    await loadJobs();
    toast(currentEnabled ? 'Job disabled' : 'Job enabled', 'info');
  } catch (e) {
    toast(`Error: ${e.message}`, 'error');
  }
}

function promptDeleteJob(id) {
  _pendingDeleteJobId = id;
  renderJobs();
}

function cancelDeleteJob() {
  _pendingDeleteJobId = null;
  renderJobs();
}

async function confirmDeleteJob(id) {
  try {
    await api('DELETE', `/api/jobs/${id}`);
    _pendingDeleteJobId = null;
    await loadJobs();
    toast('Job deleted', 'info');
  } catch (e) {
    toast(`Error: ${e.message}`, 'error');
  }
}

// ── Job Drawer ─────────────────────────────────────────────────────────────

function openJobDrawer(jobId) {
  _editingJobId = jobId;
  const overlay = document.getElementById('job-drawer-overlay');
  const title = document.getElementById('job-drawer-title');

  if (jobId) {
    const job = _jobs.find(j => j.id === jobId);
    if (!job) return;
    title.textContent = `Edit — ${job.name}`;
    document.getElementById('job-id').value = job.id;
    document.getElementById('job-name').value = job.name;
    document.getElementById('job-description').value = job.description || '';
    document.getElementById('job-schedule').value = job.schedule;
    document.getElementById('job-enabled').checked = job.enabled;
    setJobType(job.type);

    if (job.type === 'http') {
      document.getElementById('job-http-method').value = job.http_method || 'POST';
      document.getElementById('job-http-url').value = job.http_url || '';
      document.getElementById('job-http-headers').value = job.http_headers || '';
      document.getElementById('job-http-body').value = job.http_body || '';
    } else {
      document.getElementById('job-command').value = job.command || '';
    }
  } else {
    title.textContent = 'New Job';
    document.getElementById('job-form').reset();
    document.getElementById('job-id').value = '';
    document.getElementById('job-enabled').checked = true;
    setJobType('http');
  }

  updateScheduleHint(document.getElementById('job-schedule').value);
  overlay.classList.add('open');
}

function closeJobDrawer(e) {
  if (e && e.target !== document.getElementById('job-drawer-overlay')) return;
  document.getElementById('job-drawer-overlay').classList.remove('open');
}

function setJobType(type) {
  _currentJobType = type;
  document.getElementById('http-fields').style.display = type === 'http' ? 'block' : 'none';
  document.getElementById('shell-fields').style.display = type === 'shell' ? 'block' : 'none';
  document.getElementById('type-btn-http').classList.toggle('active', type === 'http');
  document.getElementById('type-btn-shell').classList.toggle('active', type === 'shell');
}

async function saveJob(e) {
  e.preventDefault();
  const btn = document.getElementById('save-job-btn');
  btn.innerHTML = '<span class="spinner"></span>';
  btn.disabled = true;

  try {
    const body = {
      name: document.getElementById('job-name').value.trim(),
      description: document.getElementById('job-description').value.trim() || null,
      type: _currentJobType,
      schedule: document.getElementById('job-schedule').value.trim(),
      enabled: document.getElementById('job-enabled').checked,
    };

    if (_currentJobType === 'http') {
      body.http_method = document.getElementById('job-http-method').value;
      body.http_url = document.getElementById('job-http-url').value.trim();
      body.http_headers = document.getElementById('job-http-headers').value.trim() || null;
      body.http_body = document.getElementById('job-http-body').value.trim() || null;
    } else {
      body.command = document.getElementById('job-command').value.trim();
    }

    const id = document.getElementById('job-id').value;
    if (id) {
      await api('PUT', `/api/jobs/${id}`, body);
      toast('Job updated ✓', 'success');
    } else {
      await api('POST', '/api/jobs', body);
      toast('Job created ✓', 'success');
    }

    document.getElementById('job-drawer-overlay').classList.remove('open');
    await loadJobs();
  } catch (err) {
    toast(`Save failed: ${err.message}`, 'error');
  } finally {
    btn.innerHTML = 'Save Job';
    btn.disabled = false;
  }
}

// ── Log Modal ──────────────────────────────────────────────────────────────

async function openLogModal(jobId, jobName) {
  const overlay = document.getElementById('log-modal-overlay');
  const body = document.getElementById('log-modal-body');
  document.getElementById('log-modal-title').textContent = `Logs — ${jobName}`;
  body.innerHTML = '<div style="text-align:center;padding:30px;"><div class="spinner"></div></div>';
  overlay.classList.add('open');

  try {
    const logs = await api('GET', `/api/jobs/${jobId}/logs?limit=30`);
    if (logs.length === 0) {
      body.innerHTML = '<div class="empty-state" style="padding:30px;"><div class="empty-icon">📭</div><h3>No logs yet</h3><p>Run the job to see execution history.</p></div>';
      return;
    }
    body.innerHTML = logs.map(logEntry).join('');
  } catch (e) {
    body.innerHTML = `<p style="color:var(--danger);">Failed to load logs: ${e.message}</p>`;
  }
}

function closeLogModal(e) {
  if (e && e.target !== document.getElementById('log-modal-overlay')) return;
  document.getElementById('log-modal-overlay').classList.remove('open');
}

function logEntry(log) {
  const statusBadge = log.success === null
    ? `<span class="badge badge-pending pulse">Running…</span>`
    : log.success
      ? `<span class="badge badge-success">✓ Success</span>`
      : `<span class="badge badge-fail">✕ Failed</span>`;

  const duration = log.finished_at
    ? ` · ${durationMs(log.started_at, log.finished_at)}`
    : '';

  const codeLabel = log.exit_code !== null
    ? `<span style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--muted);margin-left:auto;padding-right:10px;">code ${log.exit_code}</span>`
    : '';

  const output = log.output ? esc(log.output) : '(no output)';
  const logId = `log-${log.id}`;

  return `
    <div class="log-entry">
      <div class="log-entry-header" onclick="toggleLog('${logId}')">
        ${statusBadge}
        <span class="log-timestamp">${formatDate(log.started_at)}</span>
        ${codeLabel}
        <span class="log-duration">${duration}</span>
      </div>
      <pre class="log-body hidden" id="${logId}">${output}</pre>
    </div>`;
}

function toggleLog(id) {
  const el = document.getElementById(id);
  el.classList.toggle('hidden');
}

// ── Settings ───────────────────────────────────────────────────────────────

async function loadSettings() {
  try {
    _settings = await api('GET', '/api/settings');
    renderSettings();
  } catch (e) {
    console.error('Failed to load settings', e);
  }
}

function renderSettings() {
  const list = document.getElementById('settings-list');

  if (_settings.length === 0) {
    list.innerHTML = '<div class="empty-state" style="padding:30px;"><div class="empty-icon">⚙️</div><h3>No settings</h3><p>Add global settings to use as placeholders in jobs.</p></div>';
    return;
  }

  list.innerHTML = _settings.map(s => {
    const val = s.is_secret
      ? `<span class="setting-secret">••••••••••••</span>`
      : `<span class="setting-value">${esc(s.value)}</span>`;

    const secretTag = s.is_secret ? `<span class="badge badge-disabled" style="font-size:10px;">secret</span>` : '';

    const deleteBtn = _pendingDeleteSettingKey === s.key
      ? `<div class="confirm-row">
          <span class="question" style="font-size:11px;">Sure?</span>
          <button class="btn btn-danger btn-sm" onclick="confirmDeleteSetting('${esc(s.key)}')">Yes</button>
          <button class="btn btn-ghost btn-sm" onclick="cancelDeleteSetting()">No</button>
        </div>`
      : `<div style="display:flex;gap:6px;">
          <button class="btn btn-ghost btn-sm" onclick="openSettingDrawer('${esc(s.key)}')">✏</button>
          <button class="btn btn-ghost btn-sm" onclick="promptDeleteSetting('${esc(s.key)}')">🗑</button>
        </div>`;

    return `
      <div class="settings-row" id="setting-row-${encodeURIComponent(s.key)}">
        <div>
          <div class="setting-key">${esc(s.key)}</div>
          ${secretTag}
        </div>
        <div>${val}</div>
        <div style="font-size:12px;color:var(--text-dim);">${esc(s.description || '')}</div>
        <div>${deleteBtn}</div>
      </div>`;
  }).join('');
}

function openSettingDrawer(key) {
  _editingSettingKey = key;
  const overlay = document.getElementById('setting-drawer-overlay');
  const title = document.getElementById('setting-drawer-title');

  if (key) {
    const s = _settings.find(s => s.key === key);
    if (!s) return;
    title.textContent = `Edit — ${s.key}`;
    document.getElementById('setting-key').value = s.key;
    document.getElementById('setting-key').readOnly = true;
    document.getElementById('setting-value').value = s.value;
    document.getElementById('setting-desc').value = s.description || '';
    document.getElementById('setting-secret').checked = s.is_secret;
  } else {
    title.textContent = 'New Setting';
    document.getElementById('setting-form').reset();
    document.getElementById('setting-key').readOnly = false;
  }
  overlay.classList.add('open');
}

function closeSettingDrawer(e) {
  if (e && e.target !== document.getElementById('setting-drawer-overlay')) return;
  document.getElementById('setting-drawer-overlay').classList.remove('open');
}

async function saveSetting(e) {
  e.preventDefault();
  try {
    const body = {
      key: document.getElementById('setting-key').value.trim(),
      value: document.getElementById('setting-value').value.trim(),
      description: document.getElementById('setting-desc').value.trim() || null,
      is_secret: document.getElementById('setting-secret').checked,
    };
    await api('POST', '/api/settings', body);
    document.getElementById('setting-drawer-overlay').classList.remove('open');
    await loadSettings();
    toast('Setting saved ✓', 'success');
  } catch (err) {
    toast(`Error: ${err.message}`, 'error');
  }
}

function promptDeleteSetting(key) {
  _pendingDeleteSettingKey = key;
  renderSettings();
}

function cancelDeleteSetting() {
  _pendingDeleteSettingKey = null;
  renderSettings();
}

async function confirmDeleteSetting(key) {
  try {
    await api('DELETE', `/api/settings/${encodeURIComponent(key)}`);
    _pendingDeleteSettingKey = null;
    await loadSettings();
    toast('Setting deleted', 'info');
  } catch (e) {
    toast(`Error: ${e.message}`, 'error');
  }
}

// ── Cron description ───────────────────────────────────────────────────────

function updateScheduleHint(val) {
  const el = document.getElementById('schedule-hint');
  if (!el) return;
  const desc = describeCron(val);
  el.textContent = desc ? `— ${desc}` : '';
}

function describeCron(expr) {
  if (!expr) return '';
  const p = expr.trim().split(/\s+/);
  if (p.length !== 5) return '';
  const [min, hour, dom, month, dow] = p;

  if (min === '*' && hour === '*' && dom === '*' && month === '*' && dow === '*')
    return 'Every minute';
  if (min.startsWith('*/') && hour === '*' && dom === '*' && month === '*' && dow === '*')
    return `Every ${min.slice(2)} minutes`;
  if (hour.startsWith('*/') && dom === '*' && month === '*' && dow === '*')
    return `Every ${hour.slice(2)} hours at minute ${min}`;
  if (dom === '*' && month === '*' && dow === '*')
    return `Every day at ${padTime(hour, min)}`;
  if (dom === '*' && month === '*') {
    const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    if (!isNaN(dow) && days[+dow]) return `Every ${days[+dow]} at ${padTime(hour, min)}`;
  }
  if (dow === '*' && month === '*')
    return `Day ${dom} of each month at ${padTime(hour, min)}`;
  return '';
}

function padTime(h, m) {
  if (h === '*' || m === '*') return `${h}:${m}`;
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`;
}

// ── Countdowns ─────────────────────────────────────────────────────────────

function startCountdowns() {
  clearInterval(_countdownInterval);
  _countdownInterval = setInterval(tickCountdowns, 1000);
}

function tickCountdowns() {
  document.querySelectorAll('.countdown[data-target]').forEach(el => {
    const target = new Date(el.dataset.target);
    const diff = target - Date.now();
    if (diff <= 0) {
      el.textContent = 'now';
      return;
    }
    el.textContent = formatDiff(diff);
  });
}

function formatDiff(ms) {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}

// ── Toasts ─────────────────────────────────────────────────────────────────

function toast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  const icon = type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ';
  el.innerHTML = `<span>${icon}</span><span>${msg}</span>`;
  container.appendChild(el);
  setTimeout(() => {
    el.classList.add('out');
    setTimeout(() => el.remove(), 350);
  }, 3500);
}

// ── Utilities ──────────────────────────────────────────────────────────────

function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function timeAgo(iso) {
  const diff = Date.now() - new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatDate(iso) {
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'));
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}

function durationMs(start, end) {
  const ms = new Date(end + (end.endsWith('Z') ? '' : 'Z')) - new Date(start + (start.endsWith('Z') ? '' : 'Z'));
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms/1000).toFixed(1)}s`;
  return `${Math.floor(ms/60000)}m ${Math.floor((ms%60000)/1000)}s`;
}
