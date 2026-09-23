const state = { targets: [], runs: [], selectedId: null, detail: null, logs: {}, logKind: 'console', history: [] };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const num = (value) => Number(value || 0);
const fmt = (value) => new Intl.NumberFormat('zh-CN', { notation: Number(value) > 9999 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(num(value));
const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
}

function showToast(message, error = false) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.className = 'toast', 2800);
}

function setView(name) {
  $$('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === name));
  $$('.view').forEach(view => view.classList.toggle('active', view.id === `${name}-view`));
  const labels = { overview: ['MISSION CONTROL', '作战总览'], runs: ['RUN ARCHIVE', '运行记录'], console: ['LIVE TELEMETRY', '实时终端'] };
  $('#page-kicker').textContent = labels[name][0];
  $('#page-title').textContent = labels[name][1];
  if (name === 'console') loadLogs();
}

function populateTargets() {
  const select = $('#target-select');
  select.innerHTML = state.targets.map(target => `<option value="${esc(target.name)}">${esc(target.name)} · ${esc(target.protocol.toUpperCase())} · ${esc(target.host)}:${target.port}</option>`).join('');
}

function selectedTarget(name) { return state.targets.find(target => target.name === name) || {}; }

function statusLabel(status) {
  return ({ running: '运行中', starting: '启动中', stopping: '停止中', stopped: '已停止', completed: '已完成', completed_learning_export: '学习完成', failed: '失败', interrupted: '已中断', incomplete: '未完成', deadline_before_fuzzing: '超时' })[status] || status || '未知';
}

function renderRuns() {
  const body = $('#runs-table-body');
  $('#runs-empty').style.display = state.runs.length ? 'none' : 'block';
  body.innerHTML = state.runs.map(run => `
    <tr>
      <td><span class="run-id">${esc(run.id)}</span></td>
      <td><b>${esc(run.target)}</b></td>
      <td><span class="status-tag ${esc(run.status)}">${esc(statusLabel(run.status))}</span></td>
      <td>${esc(run.duration_minutes)} min</td>
      <td>${formatDate(run.started_at)}</td>
      <td><button class="row-action" data-select-run="${esc(run.id)}">查看</button></td>
    </tr>`).join('');
  $$('[data-select-run]').forEach(button => button.onclick = async () => {
    state.selectedId = button.dataset.selectRun;
    await refreshDetail();
    setView('overview');
  });
}

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? esc(value) : date.toLocaleString('zh-CN', { hour12: false });
}

function runtimeSeconds(runtime) {
  const text = String(runtime.running_time || '');
  const match = text.match(/(?:(\d+) days?, )?(\d+):(\d+):(\d+)/);
  if (!match) return 0;
  return num(match[1]) * 86400 + num(match[2]) * 3600 + num(match[3]) * 60 + num(match[4]);
}

function updateBars(selector, value, salt = 1) {
  const root = $(selector);
  root.innerHTML = Array.from({length: 24}, (_, index) => {
    const height = 3 + ((index * 13 + num(value) * salt + index * index) % 22);
    return `<i style="height:${height}px"></i>`;
  }).join('');
}

function renderOverview() {
  const run = state.detail;
  const runtime = run?.runtime || {};
  const active = Boolean(run?.active);
  const target = selectedTarget(run?.target);
  const seconds = runtimeSeconds(runtime);
  const planned = num(runtime.planned_duration_s) || num(run?.duration_minutes) * 60;
  const progress = planned ? Math.min(100, seconds / planned * 100) : 0;
  const paths = num(runtime.exec_path_num);
  const crashes = num(runtime.crash_num);
  const noncompliant = num(runtime.non_compliant);
  const stateSummary = run?.state_summary || { nodes: num(runtime.distinct_resp), edges: num(runtime.resp_transitions), discoveries: [] };
  const llmRows = run?.metrics?.llm_usage || [];
  const tokens = llmRows.reduce((sum, row) => sum + num(row.total_tokens), num(runtime.chat_token));
  const calls = llmRows.reduce((sum, row) => sum + num(row.llm_calls), 0);

  $('#live-pill').className = `live-pill${active ? ' running' : ''}`;
  $('#live-pill').innerHTML = `<i></i> ${active ? 'LIVE OPERATION' : esc((run?.status || 'STANDBY').toUpperCase())}`;
  $('#hero-title').textContent = run ? `${run.target} / ${run.algorithm}` : '等待测试任务';
  $('#hero-subtitle').textContent = run ? `任务 ${run.id} · ${statusLabel(run.status)}` : '选择目标并启动一次协议感知模糊测试。';
  $('#progress-label').textContent = `${progress.toFixed(1)}%`;
  $('#progress-bar').style.width = `${progress}%`;
  $('#stage-label').textContent = runtime.stage || (run ? statusLabel(run.status) : '尚未启动');
  $('#stop-run').hidden = !active;
  $('#metric-paths').textContent = fmt(paths);
  $('#metric-rate').textContent = seconds ? (paths / seconds).toFixed(2) : '0.00';
  $('#metric-states').textContent = fmt(Math.max(num(runtime.distinct_resp), stateSummary.nodes));
  $('#metric-transitions').textContent = fmt(Math.max(num(runtime.resp_transitions), stateSummary.edges));
  $('#metric-anomalies').textContent = fmt(crashes + noncompliant);
  $('#metric-crashes').textContent = fmt(crashes);
  $('#metric-noncompliant').textContent = fmt(noncompliant);
  $('#metric-tokens').textContent = fmt(tokens);
  $('#metric-llm-calls').textContent = fmt(calls);
  updateBars('#path-bars', paths, 1); updateBars('#state-bars', stateSummary.nodes, 2); updateBars('#anomaly-bars', crashes + noncompliant, 3); updateBars('#token-bars', tokens, 4);

  $('#target-name').textContent = run?.target || 'No target selected';
  $('#target-protocol').textContent = target.protocol?.toUpperCase() || runtime.protocol_name || '—';
  $('#target-address').textContent = target.host ? `${target.transport}://${target.host}:${target.port}` : '—';
  $('#fact-stage').textContent = runtime.active_phase || runtime.stage || '—';
  $('#fact-runtime').textContent = runtime.running_time || '00:00:00';
  $('#fact-io').textContent = `${fmt(runtime.sent_request)} / ${fmt(runtime.recv_resp)}`;
  $('#fact-frames').textContent = fmt(runtime.response_frames);
  renderPhases(run);
  renderActivity(run);
  drawDiscoveryChart(stateSummary.discoveries || []);
  $('#terminal-title').textContent = run ? `voltron / ${run.id}` : 'voltron / no active run';
}

function renderPhases(run) {
  const rows = run?.metrics?.phases || [];
  const phases = [
    ['doc_analysis', '规范分析', '解析 RFC 并生成组件'],
    ['model_learning', '状态学习', '构建协议状态模型'],
    ['fuzzing', '引导测试', '调度与变异测试序列'],
  ];
  const current = run?.runtime?.active_phase;
  const finalPhases = run?.final?.phases || {};
  let done = 0;
  $('#phase-list').innerHTML = phases.map(([key, title, desc], index) => {
    const row = [...rows].reverse().find(item => item.phase === key);
    const status = finalPhases[key] || row?.status || (current === key ? 'running' : 'pending');
    const finished = ['completed', 'deadline_reached', 'skipped'].includes(status);
    if (finished) done += 1;
    const cls = finished ? 'done' : status === 'running' ? 'running' : '';
    const icon = finished ? '✓' : status === 'running' ? '•' : index + 1;
    return `<div class="phase ${cls}"><i class="phase-icon">${icon}</i><span><b>${title}</b><small>${desc}</small></span><time>${row?.duration_s ? `${num(row.duration_s).toFixed(1)}s` : status === 'running' ? 'RUNNING' : 'WAITING'}</time></div>`;
  }).join('');
  $('#phase-count').textContent = `${done} / 3`;
}

function renderActivity(run) {
  const items = [];
  if (run) items.push([`任务状态：${statusLabel(run.status)}`, run.id, run.finished_at || run.started_at]);
  const runtime = run?.runtime || {};
  if (runtime.snapshot_reason) items.push([`状态快照 #${runtime.status_sequence || 0}`, runtime.snapshot_reason, runtime.last_update_timestamp ? new Date(num(runtime.last_update_timestamp) * 1000).toISOString() : '']);
  if (num(runtime.distinct_resp)) items.push([`发现 ${runtime.distinct_resp} 类响应`, `${runtime.resp_transitions || 0} 个转换`, '']);
  if (num(runtime.crash_num) || num(runtime.non_compliant)) items.push(['检测到异常', `${runtime.crash_num || 0} crash / ${runtime.non_compliant || 0} non-compliant`, '']);
  $('#activity-list').innerHTML = items.length ? items.slice(0, 4).map(item => `<div class="activity"><i></i><span><b>${esc(item[0])}</b><small>${esc(item[1])}</small></span><time>${item[2] ? esc(formatDate(item[2])) : ''}</time></div>`).join('') : '<div class="activity"><i></i><span><b>控制台就绪</b><small>等待新任务</small></span></div>';
}

function drawDiscoveryChart(points) {
  const svg = $('#discovery-chart');
  $('#chart-empty').style.display = points.length ? 'none' : 'grid';
  if (!points.length) { svg.innerHTML = gridLines(); return; }
  const compact = points.filter((_, index) => index % Math.max(1, Math.floor(points.length / 80)) === 0);
  const max = Math.max(1, ...compact.flatMap(point => [num(point.nodes), num(point.edges)]));
  const path = key => compact.map((point, index) => `${index ? 'L' : 'M'} ${(index / Math.max(1, compact.length - 1) * 730 + 15).toFixed(1)} ${(230 - num(point[key]) / max * 205).toFixed(1)}`).join(' ');
  const area = `${path('nodes')} L 745 230 L 15 230 Z`;
  svg.innerHTML = `${gridLines()}<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#44e5dc" stop-opacity=".2"/><stop offset="1" stop-color="#44e5dc" stop-opacity="0"/></linearGradient></defs><path d="${area}" fill="url(#area)"/><path d="${path('nodes')}" fill="none" stroke="#44e5dc" stroke-width="2"/><path d="${path('edges')}" fill="none" stroke="#9c83ff" stroke-width="1.5" stroke-dasharray="4 4"/>`;
}

function gridLines() {
  return [25, 76, 127, 178, 229].map(y => `<line x1="15" y1="${y}" x2="745" y2="${y}" stroke="#20282f" stroke-width="1"/>`).join('');
}

async function loadLogs() {
  if (!state.selectedId) return;
  try {
    state.logs = await api(`/api/runs/${encodeURIComponent(state.selectedId)}/logs?lines=300`);
    const text = state.logs[state.logKind] || `No ${state.logKind} output yet.`;
    $('#terminal-output').textContent = text;
    const pre = $('#terminal-output'); pre.scrollTop = pre.scrollHeight;
  } catch (error) { $('#terminal-output').textContent = error.message; }
}

async function refreshDetail() {
  if (!state.selectedId) { state.detail = null; renderOverview(); return; }
  try { state.detail = await api(`/api/runs/${encodeURIComponent(state.selectedId)}`); renderOverview(); }
  catch (error) { showToast(error.message, true); }
}

async function refreshAll(showFeedback = false) {
  try {
    const [targets, runs] = await Promise.all([api('/api/targets'), api('/api/runs')]);
    state.targets = targets.targets; state.runs = runs.runs;
    if (!state.selectedId && state.runs.length) state.selectedId = state.runs[0].id;
    populateTargets(); renderRuns(); await refreshDetail();
    if ($('#console-view').classList.contains('active')) await loadLogs();
    if (showFeedback) showToast('数据已刷新');
  } catch (error) { showToast(error.message, true); }
}

function openLauncher(open) {
  $('#launcher').classList.toggle('open', open);
  $('#launcher').setAttribute('aria-hidden', String(!open));
  $('#form-error').textContent = '';
}

async function launch(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = {
    target: form.elements.target_name.value,
    duration_minutes: num(form.elements.duration_minutes.value),
    spec_knowledge: form.elements.spec_knowledge.checked,
    state_learning: form.elements.state_learning.checked,
    guided_scheduling: form.elements.guided_scheduling.checked,
    observer: form.elements.observer.checked,
    compliance_analysis: form.elements.compliance_analysis.checked,
    load_aflnet_seeds: true,
  };
  $('#launch-submit').disabled = true;
  try {
    const run = await api('/api/runs', { method: 'POST', body: JSON.stringify(payload) });
    state.selectedId = run.id; openLauncher(false); showToast(`任务 ${run.target} 已启动`); await refreshAll();
  } catch (error) { $('#form-error').textContent = error.message; }
  finally { $('#launch-submit').disabled = false; }
}

function bind() {
  $$('.nav-item').forEach(button => button.onclick = () => setView(button.dataset.view));
  $$('[data-view-link]').forEach(button => button.onclick = () => setView(button.dataset.viewLink));
  $('#open-launcher').onclick = () => openLauncher(true);
  $('#close-launcher').onclick = $('#cancel-launch').onclick = () => openLauncher(false);
  $('#launcher').onclick = event => { if (event.target.id === 'launcher') openLauncher(false); };
  $('#launch-form').onsubmit = launch;
  $('#refresh-button').onclick = () => refreshAll(true);
  $('#stop-run').onclick = async () => {
    if (!state.selectedId || !confirm('确定停止当前模糊测试任务？')) return;
    try {
      await api(`/api/runs/${encodeURIComponent(state.selectedId)}/stop`, { method: 'POST', body: '{}' });
      showToast('已发送停止信号'); await refreshAll();
    } catch (error) { showToast(error.message, true); }
  };
  $$('.console-tabs button').forEach(button => button.onclick = () => {
    state.logKind = button.dataset.log;
    $$('.console-tabs button').forEach(item => item.classList.toggle('active', item === button));
    loadLogs();
  });
  $('#copy-log').onclick = () => navigator.clipboard.writeText($('#terminal-output').textContent).then(() => showToast('日志已复制'));
  document.addEventListener('keydown', event => { if (event.key === 'Escape') openLauncher(false); });
}

function tickClock() { $('#clock').textContent = new Date().toLocaleTimeString('zh-CN', { hour12: false }); }

bind(); tickClock(); setInterval(tickClock, 1000); refreshAll(); setInterval(() => refreshAll(false), 3000);
