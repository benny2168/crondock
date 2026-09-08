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
  // Initialize schedule picker
  window._sp = new SchedulePicker();
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
  if (name === 'settings')  loadSettings();
  if (name === 'timeline')  loadTimeline();
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
    document.getElementById('job-enabled').checked = job.enabled;
    setJobType(job.type);
    // Populate schedule picker
    if (window._sp) window._sp.setCron(job.schedule);

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
    // Reset picker to daily default
    if (window._sp) window._sp.setCron('0 3 * * *');
  }

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

  let durText = '';
  if (log.duration_ms != null) {
    durText = log.duration_ms < 1000 ? `${log.duration_ms}ms` : log.duration_ms < 60000 ? `${(log.duration_ms/1000).toFixed(1)}s` : `${Math.floor(log.duration_ms/60000)}m ${Math.floor((log.duration_ms%60000)/1000)}s`;
  } else if (log.started_at && log.finished_at) {
    durText = durationMs(log.started_at, log.finished_at);
  }

  let codeText = '';
  if (log.exit_code !== null) {
    if (log.exit_code === -1) {
      codeText = 'Timeout / Error';
    } else if (log.exit_code >= 200 && log.exit_code < 600) {
      codeText = `HTTP ${log.exit_code}`;
    } else {
      codeText = `Exit ${log.exit_code}`;
    }
  }

  const codeLabel = codeText
    ? `<span style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--muted);margin-left:auto;padding-right:8px;">${codeText}</span>`
    : '';

  const durationHtml = durText
    ? `<span class="log-duration" style="font-family:'JetBrains Mono',monospace;font-size:11.5px;color:var(--muted);${codeText ? '' : 'margin-left:auto;'}">⏱ ${durText}</span>`
    : '';

  const output = log.output ? esc(log.output) : '(no output)';
  const logId = `log-${log.id}`;

  return `
    <div class="log-entry">
      <div class="log-entry-header" onclick="toggleLog('${logId}')">
        ${statusBadge}
        <span class="log-timestamp">${formatDate(log.started_at)}</span>
        ${codeLabel}
        ${durationHtml}
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

// ═══════════════════════════════════════════════════════════════════════════
//  Schedule Picker
// ═══════════════════════════════════════════════════════════════════════════

class SchedulePicker {
  constructor() {
    this.freq = 'daily';
    this._attach();
  }

  _attach() {
    // Pill clicks
    document.querySelectorAll('.sp-pill').forEach(btn => {
      btn.addEventListener('click', () => {
        this._setFreq(btn.dataset.freq);
        this.update();
      });
    });
    // Day buttons
    document.querySelectorAll('.sp-day').forEach(btn => {
      btn.addEventListener('click', () => {
        btn.classList.toggle('active');
        // Ensure at least one day selected
        const active = document.querySelectorAll('.sp-day.active');
        if (active.length === 0) btn.classList.add('active');
        this.update();
      });
    });
    // All sub-inputs trigger update
    document.querySelectorAll('.sp-num, .sp-time, .sp-select').forEach(el => {
      el.addEventListener('change', () => this.update());
      el.addEventListener('input',  () => this.update());
    });
    this._setFreq('daily');
    this.update();
  }

  _setFreq(freq) {
    this.freq = freq;
    // Update pills
    document.querySelectorAll('.sp-pill').forEach(b =>
      b.classList.toggle('active', b.dataset.freq === freq));
    // Show/hide panels
    const panels = ['minutely','hourly','daily','weekly','monthly','yearly','custom'];
    panels.forEach(f => {
      const el = document.getElementById(`sp-panel-${f}`);
      if (el) el.style.display = f === freq ? '' : 'none';
    });
  }

  update() {
    const cron = this.getCron();
    const hidden = document.getElementById('job-schedule');
    if (hidden) hidden.value = cron;
    const text = document.getElementById('sp-summary-text');
    const cronEl = document.getElementById('sp-summary-cron');
    if (text)  text.textContent  = this._describe(cron);
    if (cronEl) cronEl.textContent = cron;
  }

  getCron() {
    const v = id => { const el = document.getElementById(id); return el ? el.value : ''; };
    const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, parseInt(n) || lo));

    switch (this.freq) {
      case 'minutely': {
        const every = clamp(v('sp-min-every'), 1, 59);
        return every === 1 ? '* * * * *' : `*/${every} * * * *`;
      }
      case 'hourly': {
        const every = clamp(v('sp-hr-every'), 1, 23);
        const min   = clamp(v('sp-hr-min'), 0, 59);
        return `${min} */${every} * * *`;
      }
      case 'daily': {
        const every = clamp(v('sp-day-every'), 1, 31);
        const [h, m] = (v('sp-day-time') || '03:00').split(':').map(Number);
        return every === 1
          ? `${m} ${h} * * *`
          : `${m} ${h} */${every} * *`;
      }
      case 'weekly': {
        const [h, m] = (v('sp-wk-time') || '09:00').split(':').map(Number);
        const days   = [...document.querySelectorAll('.sp-day.active')]
                         .map(b => b.dataset.d).sort().join(',');
        const every  = clamp(v('sp-wk-every'), 1, 52);
        // Standard cron doesn't support "every N weeks" natively;
        // for N=1 use DOW, for N>1 encode as comment hint with DOW
        return `${m} ${h} * * ${days || '1'}`;
      }
      case 'monthly': {
        const every = clamp(v('sp-mo-every'), 1, 12);
        const day   = v('sp-mo-day') || '1';
        const [h, m] = (v('sp-mo-time') || '09:00').split(':').map(Number);
        return every === 1
          ? `${m} ${h} ${day} * *`
          : `${m} ${h} ${day} */${every} *`;
      }
      case 'yearly': {
        const month = v('sp-yr-month') || '1';
        const day   = clamp(v('sp-yr-day'), 1, 31);
        const [h, m] = (v('sp-yr-time') || '00:00').split(':').map(Number);
        return `${m} ${h} ${day} ${month} *`;
      }
      case 'custom': {
        const raw = (v('sp-custom-expr') || '').trim();
        return raw || '* * * * *';
      }
    }
    return '* * * * *';
  }

  _describe(cron) {
    return describeCron(cron) || cron;
  }

  /** Load an existing cron string into the picker UI */
  setCron(expr) {
    if (!expr) return;
    const state = this._parse(expr);
    this._setFreq(state.freq);

    const set = (id, val) => { const el = document.getElementById(id); if (el && val !== undefined) el.value = val; };
    const pad = n => String(n).padStart(2, '0');
    const toTime = (h, m) => `${pad(h)}:${pad(m)}`;

    switch (state.freq) {
      case 'minutely': set('sp-min-every',  state.every); break;
      case 'hourly':
        set('sp-hr-every', state.every);
        set('sp-hr-min',   state.minute);
        break;
      case 'daily':
        set('sp-day-every', state.every);
        set('sp-day-time',  toTime(state.hour, state.minute));
        break;
      case 'weekly':
        set('sp-wk-time', toTime(state.hour, state.minute));
        // Set day buttons
        document.querySelectorAll('.sp-day').forEach(b => {
          b.classList.toggle('active', (state.days || [1]).includes(+b.dataset.d));
        });
        break;
      case 'monthly':
        set('sp-mo-every', state.every);
        set('sp-mo-day',   state.day);
        set('sp-mo-time',  toTime(state.hour, state.minute));
        break;
      case 'yearly':
        set('sp-yr-month', state.month);
        set('sp-yr-day',   state.day);
        set('sp-yr-time',  toTime(state.hour, state.minute));
        break;
      case 'custom':
        set('sp-custom-expr', expr);
        break;
    }
    this.update();
  }

  _parse(expr) {
    const parts = expr.trim().split(/\s+/);
    if (parts.length !== 5) return { freq: 'custom' };
    const [min, hour, dom, mon, dow] = parts;
    const num = s => !isNaN(s) && s !== '*';

    // Minutely
    if (min === '*' && hour === '*' && dom === '*' && mon === '*' && dow === '*')
      return { freq: 'minutely', every: 1 };
    if (/^\*\/\d+$/.test(min) && hour === '*' && dom === '*' && mon === '*' && dow === '*')
      return { freq: 'minutely', every: +min.slice(2) };

    // Hourly
    if (num(min) && (/^\*\/\d+$/.test(hour) || hour === '*') && dom === '*' && mon === '*' && dow === '*')
      return { freq: 'hourly', minute: +min, every: hour === '*' ? 1 : +hour.slice(2) };

    // Weekly (DOW set, dom=*)
    if (num(min) && num(hour) && dom === '*' && mon === '*' && dow !== '*') {
      const days = dow.split(',').map(d => +d.replace(/\D/g,''));
      return { freq: 'weekly', minute: +min, hour: +hour, days };
    }

    // Daily
    if (num(min) && num(hour) && (/^\*\/\d+$/.test(dom) || dom === '*') && mon === '*' && dow === '*')
      return { freq: 'daily', minute: +min, hour: +hour, every: dom === '*' ? 1 : +dom.slice(2) };

    // Monthly
    if (num(min) && num(hour) && num(dom) && (/^\*\/\d+$/.test(mon) || mon === '*') && dow === '*')
      return { freq: 'monthly', minute: +min, hour: +hour, day: +dom, every: mon === '*' ? 1 : +mon.slice(2) };

    // Yearly
    if (num(min) && num(hour) && num(dom) && num(mon) && dow === '*')
      return { freq: 'yearly', minute: +min, hour: +hour, day: +dom, month: +mon };

    return { freq: 'custom' };
  }
}

// Replaced updateScheduleHint — no-op for compatibility
function updateScheduleHint() {}


// ═══════════════════════════════════════════════════════════════════════════
//  Timeline
// ═══════════════════════════════════════════════════════════════════════════

let _tlData = { past: [], upcoming: [] };
let _tlFilterJobId = '';
let _tlView = 'list';
let _tlCalYear = new Date().getFullYear();
let _tlCalMonth = new Date().getMonth(); // 0-indexed

async function loadTimeline() {
  try {
    _tlData = await api('GET', '/api/timeline?days=60');
    _populateTlFilter();
    tlRender();
  } catch(e) {
    console.error('Failed to load timeline', e);
  }
}

function _populateTlFilter() {
  const sel = document.getElementById('tl-filter-job');
  if (!sel) return;
  const names = new Map();
  [..._tlData.past, ..._tlData.upcoming].forEach(r => {
    names.set(r.job_id, r.job_name);
  });
  const current = sel.value;
  sel.innerHTML = '<option value="">All Jobs</option>' +
    [...names.entries()].map(([id, name]) =>
      `<option value="${id}" ${id == current ? 'selected' : ''}>${esc(name)}</option>`
    ).join('');
}

function tlApplyFilter() {
  _tlFilterJobId = document.getElementById('tl-filter-job').value;
  tlRender();
}

function tlSetView(v) {
  _tlView = v;
  document.getElementById('tl-list-view').style.display     = v === 'list'     ? '' : 'none';
  document.getElementById('tl-calendar-view').style.display = v === 'calendar' ? '' : 'none';
  document.getElementById('tl-btn-list').classList.toggle('active',     v === 'list');
  document.getElementById('tl-btn-calendar').classList.toggle('active', v === 'calendar');
  tlRender();
}

function tlRender() {
  if (_tlView === 'list')     tlRenderList();
  else                        tlRenderCalendar();
}

// ── List view ───────────────────────────────────────────────────────────────

function tlRenderList() {
  const container = document.getElementById('tl-list-content');
  if (!container) return;

  const fid = _tlFilterJobId ? +_tlFilterJobId : null;

  // Combine past + upcoming into a single sorted timeline
  const items = [];
  _tlData.past.forEach(r => {
    if (fid && r.job_id !== fid) return;
    items.push({ ...r, _type: 'past', _time: new Date(r.started_at + 'Z') });
  });
  _tlData.upcoming.forEach(r => {
    if (fid && r.job_id !== fid) return;
    items.push({ ...r, _type: 'upcoming', _time: new Date(r.scheduled_at) });
  });

  // Sort descending (most recent first, upcoming after)
  const now = Date.now();
  items.sort((a, b) => {
    const at = a._time.getTime(), bt = b._time.getTime();
    // Put upcoming at top of the list (future), then past descending
    if (at > now && bt > now) return at - bt;    // both future: ascending
    if (at > now) return -1;                      // a is future → top
    if (bt > now) return 1;                       // b is future → top
    return bt - at;                               // both past: most recent first
  });

  if (items.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">📭</div><h3>No runs yet</h3><p>Your job run history will appear here once jobs have executed.</p></div>`;
    return;
  }

  // Group by date
  const groups = {};
  const today = new Date(); today.setHours(0,0,0,0);
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);

  items.forEach(item => {
    const d = new Date(item._time);
    d.setHours(0,0,0,0);
    const key = d.toISOString().slice(0, 10);
    if (!groups[key]) groups[key] = { label: _dateLabel(d, today, tomorrow), items: [] };
    groups[key].items.push(item);
  });

  container.innerHTML = Object.entries(groups).map(([date, group]) => `
    <div class="tl-date-group">
      <div class="tl-date-label">${group.label}</div>
      ${group.items.map(item => tlRunRow(item)).join('')}
    </div>
  `).join('');
}

function _dateLabel(d, today, tomorrow) {
  if (d.getTime() >= tomorrow.getTime()) {
    const diff = Math.round((d - today) / 86400000);
    if (diff === 1) return 'Tomorrow';
    return d.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
  }
  if (d.getTime() === today.getTime()) return 'Today';
  const diff = Math.round((today - d) / 86400000);
  if (diff === 1) return 'Yesterday';
  return d.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
}

function tlRunRow(item) {
  const isUpcoming = item._type === 'upcoming';
  const isRunning  = !isUpcoming && item.success === null;

  let stripeClass, pillClass, pillLabel;
  if (isUpcoming)      { stripeClass = 's-upcoming'; pillClass = 'tl-pill-upcoming'; pillLabel = 'Scheduled'; }
  else if (isRunning)  { stripeClass = 's-running';  pillClass = 'tl-pill-running';  pillLabel = 'Running…'; }
  else if (item.success){ stripeClass = 's-success'; pillClass = 'tl-pill-success';  pillLabel = '✓ Success'; }
  else                  { stripeClass = 's-fail';    pillClass = 'tl-pill-fail';     pillLabel = '✕ Failed'; }

  const time = item._time;
  const timeStr = time.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  const dur = item.duration_ms != null
    ? (item.duration_ms < 1000 ? `${item.duration_ms}ms` : item.duration_ms < 60000 ? `${(item.duration_ms/1000).toFixed(1)}s` : `${Math.floor(item.duration_ms/60000)}m`)
    : '';

  const onclick = !isUpcoming
    ? `onclick="tlOpenDetail(${JSON.stringify(item).replace(/"/g,'&quot;')})"`
    : '';

  return `
    <div class="tl-run-row${isUpcoming ? ' tl-upcoming' : ''}" ${onclick}>
      <div class="tl-run-stripe ${stripeClass}"></div>
      <div>
        <div class="tl-run-name">${esc(item.job_name)}</div>
        ${item.exit_code != null ? `<div class="tl-run-sub">exit ${item.exit_code}${item.schedule ? ' · ' + esc(item.schedule) : ''}</div>` : ''}
      </div>
      <div class="tl-run-time">${timeStr}</div>
      <div>
        <span class="tl-status-pill ${pillClass}">${pillLabel}</span>
        ${dur ? `<div class="tl-run-dur">${dur}</div>` : ''}
      </div>
    </div>`;
}

// ── Calendar view ───────────────────────────────────────────────────────────

function tlCalPrev() { _tlCalMonth--; if (_tlCalMonth < 0) { _tlCalMonth = 11; _tlCalYear--; } tlRenderCalendar(); }
function tlCalNext() { _tlCalMonth++; if (_tlCalMonth > 11) { _tlCalMonth = 0;  _tlCalYear++; } tlRenderCalendar(); }

function tlRenderCalendar() {
  const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  document.getElementById('tl-cal-title').textContent = `${MONTHS[_tlCalMonth]} ${_tlCalYear}`;

  const fid = _tlFilterJobId ? +_tlFilterJobId : null;

  // Build a map: date-string → [events]
  const eventMap = {};
  const addEvent = (dateStr, ev) => {
    if (!eventMap[dateStr]) eventMap[dateStr] = [];
    eventMap[dateStr].push(ev);
  };

  _tlData.past.forEach(r => {
    if (fid && r.job_id !== fid) return;
    if (!r.started_at) return;
    const d = new Date(r.started_at + 'Z');
    const ds = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    const cls = r.success === null ? 'ev-running' : r.success ? 'ev-success' : 'ev-fail';
    addEvent(ds, { label: r.job_name, cls, item: r });
  });
  _tlData.upcoming.forEach(r => {
    if (fid && r.job_id !== fid) return;
    const d = new Date(r.scheduled_at);
    const ds = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    addEvent(ds, { label: r.job_name, cls: 'ev-upcoming', item: null });
  });

  // Build calendar grid
  const firstDay = new Date(_tlCalYear, _tlCalMonth, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(_tlCalYear, _tlCalMonth + 1, 0).getDate();
  const prevMonthDays = new Date(_tlCalYear, _tlCalMonth, 0).getDate();

  const todayStr = new Date().toISOString().slice(0,10);
  let html = '';

  // Fill leading days from prev month
  for (let i = firstDay - 1; i >= 0; i--) {
    const day = prevMonthDays - i;
    const month = _tlCalMonth === 0 ? 12 : _tlCalMonth;
    const year  = _tlCalMonth === 0 ? _tlCalYear - 1 : _tlCalYear;
    const ds = `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
    html += _calDay(day, ds, true, false, eventMap[ds] || []);
  }

  // Current month
  for (let d = 1; d <= daysInMonth; d++) {
    const ds = `${_tlCalYear}-${String(_tlCalMonth+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    html += _calDay(d, ds, false, ds === todayStr, eventMap[ds] || []);
  }

  // Fill trailing days
  const total = firstDay + daysInMonth;
  const trailing = total % 7 === 0 ? 0 : 7 - (total % 7);
  for (let d = 1; d <= trailing; d++) {
    const month = _tlCalMonth === 11 ? 1 : _tlCalMonth + 2;
    const year  = _tlCalMonth === 11 ? _tlCalYear + 1 : _tlCalYear;
    const ds = `${year}-${String(month).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    html += _calDay(d, ds, true, false, eventMap[ds] || []);
  }

  document.getElementById('tl-cal-body').innerHTML = html;
}

function _calDay(dayNum, dateStr, otherMonth, isToday, events) {
  const maxShow = 3;
  const shown = events.slice(0, maxShow);
  const overflow = events.length - maxShow;
  const evHtml = shown.map(ev => {
    const onclick = ev.item
      ? `onclick="event.stopPropagation();tlOpenDetail(${JSON.stringify(ev.item).replace(/"/g,'&quot;')})"`
      : '';
    return `<div class="tl-cal-event ${ev.cls}" ${onclick}>${esc(ev.label)}</div>`;
  }).join('');
  const moreHtml = overflow > 0 ? `<div class="tl-cal-more">+${overflow} more</div>` : '';
  return `<div class="tl-cal-day${otherMonth ? ' tl-other-month' : ''}${isToday ? ' tl-today' : ''}">
    <div class="tl-cal-day-num">${dayNum}</div>
    <div class="tl-cal-events">${evHtml}${moreHtml}</div>
  </div>`;
}

// ── Detail slide-over ───────────────────────────────────────────────────────

function tlOpenDetail(item) {
  if (!item || !item.id) return; // don't open for upcoming
  const overlay = document.getElementById('tl-detail-overlay');
  if (!overlay) return;
  overlay.classList.add('open');

  document.getElementById('tl-detail-job-name').textContent = item.job_name || '—';

  const started  = item.started_at  ? new Date(item.started_at  + 'Z') : null;
  const finished = item.finished_at ? new Date(item.finished_at + 'Z') : null;
  const fmtDt = d => d ? d.toLocaleString(undefined, { month:'short', day:'numeric', year:'numeric', hour:'2-digit', minute:'2-digit', second:'2-digit' }) : '—';
  document.getElementById('tl-detail-meta').textContent = `Started: ${fmtDt(started)}`;

  // Badges
  const badgeContainer = document.getElementById('tl-detail-badges');
  const successCls = item.success === null ? 'b-neutral' : item.success ? 'b-success' : 'b-fail';
  const successLabel = item.success === null ? 'Running…' : item.success ? '✓ Success' : '✕ Failed';
  const dur = item.duration_ms != null
    ? `${item.duration_ms < 1000 ? item.duration_ms + 'ms' : item.duration_ms < 60000 ? (item.duration_ms/1000).toFixed(2) + 's' : Math.floor(item.duration_ms/60000) + 'm ' + Math.floor((item.duration_ms%60000)/1000) + 's'}`
    : null;

  badgeContainer.innerHTML =
    `<span class="tl-detail-badge ${successCls}">${successLabel}</span>` +
    (item.exit_code != null ? `<span class="tl-detail-badge b-neutral">exit ${item.exit_code}</span>` : '') +
    (dur ? `<span class="tl-detail-badge b-neutral">⏱ ${dur}</span>` : '') +
    (finished ? `<span class="tl-detail-badge b-neutral">Finished ${fmtDt(finished)}</span>` : '');

  document.getElementById('tl-detail-output').textContent = item.output || '(no output)';
}

function tlCloseDetail(e) {
  if (e && e.target !== document.getElementById('tl-detail-overlay')) return;
  const overlay = document.getElementById('tl-detail-overlay');
  if (overlay) overlay.classList.remove('open');
}

