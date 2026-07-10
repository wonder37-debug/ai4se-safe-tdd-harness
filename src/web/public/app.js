// AI4SE-Safe-TDD-Harness control panel — vanilla JS, HTTP polling
// Anthropic 极简风格：自然语言事件气泡 + 卡其反馈 Blockquote + 审批原因回灌
const $ = (id) => document.getElementById(id);
let since = 0;
let lastIter = 0;
let allSeen = [];

// ───────── 工具 ─────────
function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function truncate(s, n) { s = String(s); return s.length > n ? s.slice(0, n) + '…' : s; }

// 点击反馈：按钮短暂变为 ✓ 成功 / ✗ 失败，让用户明确知道点击结果。
// ok=true 绿色、ok=false 红色；约 1.6s 后还原按钮文案与状态。
function flash(btn, ok, msg) {
  if (!btn) return;
  if (!btn.dataset.label) btn.dataset.label = btn.textContent;
  btn.textContent = (ok ? '✓ ' : '✗ ') + (msg || (ok ? '成功' : '失败'));
  btn.classList.remove('is-flash-ok', 'is-flash-fail');
  btn.classList.add(ok ? 'is-flash-ok' : 'is-flash-fail');
  btn.disabled = true;
  clearTimeout(btn._flashT);
  btn._flashT = setTimeout(() => {
    btn.textContent = btn.dataset.label;
    btn.classList.remove('is-flash-ok', 'is-flash-fail');
    btn.disabled = false;
  }, 1600);
}

// POST 后统一处理：成功 flash ok + onSuccess，失败 flash fail
async function postWithFeedback(btn, url, payload, onSuccess, okMsg) {
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    flash(btn, true, okMsg || '成功');
    if (onSuccess) await onSuccess(r);
  } catch (e) {
    flash(btn, false, '失败');
  }
}

// ───────── Loop State 派生（从最新事件流，不侵入内核） ─────────
function deriveState(events) {
  if (!events.length) return null;
  const last = events[events.length - 1];
  if (last.type === 'halt') return 'HALTED';
  const lastReqIdx = (() => {
    for (let i = events.length - 1; i >= 0; i--) if (events[i].type === 'approval_request') return i;
    return -1;
  })();
  if (lastReqIdx !== -1) {
    const after = events.slice(lastReqIdx + 1);
    if (!after.some(e => e.type === 'approval_decision')) return 'APPROVAL_PENDING';
  }
  if (last.type === 'action') return 'EXECUTING';
  return 'RUNNING';
}

function renderState(state) {
  const rail = $('stateRail');
  [...rail.children].forEach(li => li.classList.toggle('is-active', li.dataset.state === state));
}

// ───────── 底层 JSON → 自然语言翻译 ─────────
function describeAction(p) {
  const a = p.args || {};
  switch (p.tool) {
    case 'write_file': return `写入文件 <code>${esc(a.path || '')}</code>`;
    case 'read_file':  return `读取文件 <code>${esc(a.path || '')}</code>`;
    case 'list_dir':   return `列出目录 <code>${esc(a.path || '.')}</code>`;
    case 'run_shell':  return `执行 shell <code>${esc(truncate(a.command || '', 80))}</code>`;
    case 'run_tests':  return `运行测试 <code>${esc(truncate(a.command || '', 80))}</code>`;
    case 'finish':     return `结束循环`;
    default:           return esc(p.tool);
  }
}

// ───────── 事件渲染 ─────────
function renderEvent(ev) {
  const id = `<span class="e-id">#${ev.id}</span>`;
  if (ev.type === 'action') {
    return `<li class="event event--action">${id}<span class="e-body">${describeAction(ev.payload)}</span></li>`;
  }
  if (ev.type === 'observation') {
    return renderObservation(ev, id);
  }
  if (ev.type === 'approval_request') {
    const a = ev.payload?.action || {};
    const cmd = a.args?.command ? ` <code>${esc(truncate(a.args.command, 60))}</code>` : '';
    return `<li class="event event--approval_request">${id}<span class="e-body">等待审批 · ${esc(a.tool || '?')}${cmd}</span></li>`;
  }
  if (ev.type === 'approval_decision') {
    const p = ev.payload || {};
    const deny = p.decision === 'deny';
    const txt = deny ? `已拒绝${p.reason ? ' · ' + esc(p.reason) : ''}` : '已批准';
    return `<li class="event event--approval_decision${deny ? ' is-deny' : ''}">${id}<span class="e-body">${txt}</span></li>`;
  }
  if (ev.type === 'halt') {
    const reason = ev.payload?.reason ?? JSON.stringify(ev.payload);
    return `<li class="event event--halt">${id}<span class="e-body">循环结束 · ${esc(reason)}</span></li>`;
  }
  return `<li class="event">${id}<span class="e-body">${esc(JSON.stringify(ev.payload))}</span></li>`;
}

function renderObservation(ev, id) {
  const p = ev.payload;
  // 测试失败 Feedback（run_tests 失败时 payload 是结构化 Feedback 对象）
  if (p && typeof p === 'object' && 'errorType' in p) {
    return feedbackCard(id, p);
  }
  // 成功：退出码 0 → 极简绿底细线卡片（测试通过 / shell 成功）
  if (p && p.exitCode === 0) {
    return `<li class="event event--feedback-ok">${id}<span class="e-body">测试通过 · 退出码 0</span></li>`;
  }
  // 普通观察气泡
  let body = '观察';
  if (p && p.ok === false) body = '执行失败 · ' + esc(truncate(p.error || p.stderr || '', 120));
  else if (p && typeof p.content === 'string') body = esc(truncate(p.content, 120));
  return `<li class="event event--observation">${id}<span class="e-body">${body}</span></li>`;
}

// 测试失败：卡其色 Blockquote 引用卡片，醒目提示断言失败的行号
function feedbackCard(id, fb) {
  const labels = { assertion: '断言失败', syntax: '语法错误', other: '测试失败' };
  const label = labels[fb.errorType] || '测试失败';
  const loc = fb.assertion ? `${fb.assertion.file}:${fb.assertion.line}` : '';
  const failedTests = (fb.failedTests || []).map(esc).join(' · ');
  let html = `<li class="event event--feedback-fail">${id}<div class="fb-body">` +
    `<div class="fb-title">⚠ ${esc(label)}${failedTests ? ' · ' + failedTests : ''}</div>`;
  if (loc) html += `<div class="fb-loc">位于 <code class="line">${esc(loc)}</code></div>`;
  if (fb.hint) html += `<div class="fb-hint">${esc(fb.hint)}</div>`;
  if (fb.evidence) {
    html += `<details><summary>错误证据</summary><pre>${esc(truncate(fb.evidence, 800))}</pre></details>`;
  }
  html += `</div></li>`;
  return html;
}

function appendEvents(events) {
  const list = $('events');
  const empty = list.querySelector('.event--empty');
  if (empty) empty.remove();
  for (const ev of events) {
    if (ev.iter) lastIter = Math.max(lastIter, ev.iter);
    list.insertAdjacentHTML('beforeend', renderEvent(ev));
  }
  list.scrollTop = list.scrollHeight;
  $('iterCounter').textContent = `iter ${lastIter}`;
}

// ───────── 人工审批流：原因输入框 + Deny & 反馈 ─────────
function buildApprovalCard(a) {
  const card = document.createElement('article');
  card.className = 'approval-card';
  card.dataset.id = a.id;
  const cmd = a.action?.args?.command ?? JSON.stringify(a.action?.args ?? {});
  card.innerHTML =
    `<div class="ac-head"><span class="ac-tool">${esc(a.action?.tool ?? '?')}</span><span class="ac-sev">高危</span></div>` +
    `<pre class="ac-cmd">${esc(String(cmd))}</pre>` +
    (a.reasons?.length ? `<div class="ac-reasons">${esc(a.reasons.join(' · '))}</div>` : '') +
    // 人工审批卡片内的文本输入框：补充指示或拒绝原因
    `<textarea class="ap-input" rows="2" placeholder="补充指示或拒绝原因，将回灌给 agent…"></textarea>` +
    `<p class="ap-hint">请填写拒绝原因以回灌给 agent，引导其重定向修正。</p>` +
    `<div class="ac-actions">` +
      `<button class="btn btn--approve" data-d="approve">批准</button>` +
      // 拒绝时把输入框内容作为 reason 发送，实现对 Agent 的对话重定向
      `<button class="btn btn--deny" data-d="deny">Deny &amp; 反馈</button>` +
    `</div>`;
  return card;
}

// 按 id 增量调和：仅追加新卡片、移除已裁决的卡片，保留仍在场卡片的输入文本与焦点
async function renderApprovals() {
  const ap = await fetch('/api/approvals').then(r => r.json()).catch(() => []);
  const box = $('approvals');
  const pendingIds = new Set(ap.map(a => a.id));
  for (const card of [...box.querySelectorAll('.approval-card')]) {
    if (!pendingIds.has(card.dataset.id)) card.remove();
  }
  if (!ap.length) {
    if (!box.querySelector('.approval--empty')) {
      box.innerHTML = '<p class="approval--empty">当前无待审批请求。</p>';
    }
    return;
  }
  const empty = box.querySelector('.approval--empty');
  if (empty) empty.remove();
  for (const a of ap) {
    if (box.querySelector(`.approval-card[data-id="${a.id}"]`)) continue;
    box.appendChild(buildApprovalCard(a));
  }
}

$('approvals').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-d]');
  if (!b) return;
  const card = b.closest('.approval-card');
  const input = card?.querySelector('.ap-input');
  const reason = input ? input.value : '';
  // 拒绝时必须动态读取框内文本作为 reason；为空则聚焦引导人机对话重定向，不发送
  if (b.dataset.d === 'deny' && !reason.trim()) {
    card.classList.add('is-redirect');
    input?.focus();
    return;
  }
  card.classList.remove('is-redirect');
  decide(card.dataset.id, b.dataset.d, reason);
});
// 用户开始输入即解除重定向引导态
$('approvals').addEventListener('input', (e) => {
  if (!e.target.matches('.ap-input')) return;
  e.target.closest('.approval-card')?.classList.remove('is-redirect');
});

function decide(id, d, reason) {
  // 审批按钮反馈：点击即知结果
  const card = document.querySelector(`.approval-card[data-id="${id}"]`);
  const btn = card?.querySelector(`button[data-d="${d}"]`);
  postWithFeedback(btn, '/api/approval', { id, decision: d, reason: reason || '' }, renderApprovals,
    d === 'approve' ? '已批准' : '已拒绝');
}

// ───────── 凭据状态 ─────────
async function renderKeyStatus() {
  try {
    const s = await fetch('/api/key/status').then(r => r.json());
    const el = $('keystatus');
    el.classList.toggle('is-present', !!s.present);
    el.textContent = `key 状态：${s.present ? '已配置 · ' + s.source : '未配置（保存后将加密落盘）'}`;
  } catch {}
}

// ───────── 端点配置（请求地址 / 模型名，非密，明文落盘） ─────────
async function renderConfigStatus() {
  try {
    const c = await fetch('/api/config').then(r => r.json()) || {};
    const el = $('cfgstatus');
    const parts = [];
    parts.push(c.baseUrl ? `地址 ${esc(c.baseUrl)}` : '地址未配置');
    parts.push(c.model ? `模型 ${esc(c.model)}` : '模型未配置');
    el.textContent = '端点：' + parts.join(' · ');
    el.classList.toggle('is-present', !!(c.baseUrl || c.model));
    // 回填到输入框，方便查看或微调（不覆盖用户正在编辑的内容）
    if (c.baseUrl && !$('baseurl').value) $('baseurl').value = c.baseUrl;
    if (c.model && !$('model').value) $('model').value = c.model;
  } catch {}
}

// ───────── 轮询主循环 ─────────
async function poll() {
  try {
    const evs = await fetch(`/api/events?since=${since}`).then(r => r.json());
    if (evs.length) {
      since = evs[evs.length - 1].id;
      appendEvents(evs);
      renderState(deriveState(allSeen.concat(evs)));
      allSeen = allSeen.concat(evs).slice(-200);
    }
    await renderApprovals();
  } catch {}
}

// ───────── 用户动作 ─────────
$('start').onclick = () => {
  if (!$('task').value.trim()) { flash($('start'), false, '任务为空'); return; }
  postWithFeedback($('start'), '/api/task', { task: $('task').value, cwd: $('cwd').value }, null, '已提交');
};
$('setkey').onclick = () => {
  const key = $('apikey').value;
  const master = $('master').value;
  if (!key || !master) { flash($('setkey'), false, '请填全'); return; }
  postWithFeedback($('setkey'), '/api/key', { key, masterPassword: master }, renderKeyStatus, '已保存');
};
$('setcfg').onclick = () => {
  const baseUrl = $('baseurl').value.trim();
  const model = $('model').value.trim();
  if (!baseUrl && !model) { flash($('setcfg'), false, '请填一项'); return; }
  postWithFeedback($('setcfg'), '/api/config', { baseUrl, model }, renderConfigStatus, '已保存');
};
$('clearEvents').onclick = () => {
  const list = $('events');
  list.innerHTML = '<li class="event event--empty">已清空显示（事件仍在后端）。</li>';
  lastIter = 0;
  $('iterCounter').textContent = 'iter 0';
  flash($('clearEvents'), true, '已清空');
};

renderKeyStatus();
renderConfigStatus();
renderState(null);
setInterval(poll, 1000);
setInterval(renderKeyStatus, 5000);
setInterval(renderConfigStatus, 5000);
