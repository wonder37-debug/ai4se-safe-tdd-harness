// AI4SE-Safe-TDD-Harness control panel — vanilla JS, HTTP polling
// Anthropic 极简风格：思考气泡 + 自然语言事件行 + 卡其反馈 Blockquote + 审批原因回灌
const $ = (id) => document.getElementById(id);
let since = 0;
let lastIter = 0;
let allSeen = [];
// 承接上一 action 的工具类型，供 observation 成功提示选词（对齐 CLI ConsoleSink）
let lastTool = null;
// 启动后驻留的等待/思考提示状态
let lastEventAt = Date.now();

// ───────── 工具 ─────────
function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
// 注：已废除硬截断 truncate()——长命令/路径/错误日志一律完整输出，
// 折行交给 CSS（.e-body/.event code 的 overflow-wrap）与终端自然换行处理。

// ───────── 启动后驻留的等待/思考提示 ─────────
// 点击启动循环后显示"等待大模型响应中…"，首事件到达或循环结束时收起；
// 运行中长时间无新事件则切为"agent 正在思考…"，让用户明确知道循环在推进而非卡死。
function showWait(msg) {
  const b = $('waitBanner');
  if (!b) return;
  b.innerHTML = `<span class="wait-dot"></span><span class="wait-text">${esc(msg)}</span>`;
  b.hidden = false;
}
function hideWait() {
  const b = $('waitBanner');
  if (b) b.hidden = true;
}

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

// ───────── 底层 JSON → 自然语言翻译（对齐 CLI ConsoleSink 的 Emoji 短句） ─────────
function describeAction(p) {
  const a = p.args || {};
  lastTool = p.tool; // 记给下一条 observation 成功提示选词
  switch (p.tool) {
    case 'write_file': return `📄 写入文件 <code>${esc(a.path || '')}</code>`;
    case 'read_file':  return `📖 读取文件 <code>${esc(a.path || '')}</code>`;
    case 'list_dir':   return `📂 列出目录 <code>${esc(a.path || '.')}</code>`;
    case 'run_shell':  return `⚙️ 执行命令 <code>${esc(a.command || '')}</code>`;
    case 'run_tests':  return `🧪 运行测试 <code>${esc(a.command || '')}</code>`;
    case 'finish':     return `🏁 结束循环`;
    default:           return `🔧 ${esc(p.tool)}`;
  }
}

// observation 成功提示词：承接上一 action 的工具类型
function obsSuccess() {
  switch (lastTool) {
    case 'write_file': return '已写入';
    case 'read_file':  return '已读取';
    case 'list_dir':   return '已列出';
    case 'run_tests':  return '测试通过';
    case 'run_shell':  return '执行完成';
    default:           return '完成';
  }
}

// ───────── 事件渲染 ─────────
function renderEvent(ev) {
  const id = `<span class="e-id">#${ev.id}</span>`;
  if (ev.type === 'thought') {
    return renderThought(ev, id);
  }
  if (ev.type === 'action') {
    return `<li class="event event--action">${id}<span class="e-body">${describeAction(ev.payload)}</span></li>`;
  }
  if (ev.type === 'observation') {
    return renderObservation(ev, id);
  }
  if (ev.type === 'approval_request') {
    const a = ev.payload?.action || {};
    const cmd = a.args?.command ? ` <code>${esc(a.args.command)}</code>` : '';
    return `<li class="event event--approval_request">${id}<span class="e-body">🔐 等待审批 · ${esc(a.tool || '?')}${cmd}</span></li>`;
  }
  if (ev.type === 'approval_decision') {
    const p = ev.payload || {};
    const deny = p.decision === 'deny';
    const txt = deny ? `🚫 已拒绝${p.reason ? ' · ' + esc(p.reason) : ''}` : '✅ 已批准';
    return `<li class="event event--approval_decision${deny ? ' is-deny' : ''}">${id}<span class="e-body">${txt}</span></li>`;
  }
  if (ev.type === 'halt') {
    const reason = ev.payload?.reason ?? 'unknown';
    return `<li class="event event--halt">${id}<span class="e-body">🏁 循环结束 · ${esc(reason)}</span></li>`;
  }
  // 兜底：废除裸露 JSON 打印，仅显示事件类型
  return `<li class="event event--system">${id}<span class="e-body">${esc(ev.type)}</span></li>`;
}

// 大模型思考气泡：Anthropic 极简风的"笔记本边注"——serif 斜体 + 暖灰墨 +
// 左侧发丝细线 + 柔色底，多段自然语言以 pre-wrap 原样保留，配 💭 标记。
function renderThought(ev, id) {
  const p = ev.payload;
  const text = (p && typeof p === 'object' && 'text' in p) ? String(p.text) : String(p ?? '');
  if (!text) return '';
  return `<li class="event event--thought">${id}` +
    `<div class="thought-body"><span class="thought-mark">💭</span>` +
    `<span class="thought-text">${esc(text)}</span></div></li>`;
}

function renderObservation(ev, id) {
  const p = ev.payload;
  // 测试失败 Feedback（run_tests 失败时 payload 是结构化 Feedback 对象）
  if (p && typeof p === 'object' && 'errorType' in p) {
    return feedbackCard(id, p);
  }
  // 失败：完整 error/stderr 输出（多行堆栈原样保留，折行交给 CSS）
  if (p && p.ok === false) {
    return `<li class="event event--observation">${id}<span class="e-body">❌ ${esc(p.error || p.stderr || '失败')}</span></li>`;
  }
  // 成功：按上一动作工具给极简提示（测试通过 / 已写入 …），不倾倒 stdout/content
  return `<li class="event event--feedback-ok">${id}<span class="e-body">✅ ${obsSuccess()}</span></li>`;
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
    html += `<details><summary>错误证据</summary><pre>${esc(fb.evidence)}</pre></details>`;
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
    let state = null;
    if (evs.length) {
      since = evs[evs.length - 1].id;
      lastEventAt = Date.now();
      hideWait(); // 首个事件到达即收起"等待响应"提示
      appendEvents(evs);
      state = deriveState(allSeen.concat(evs));
      renderState(state);
      allSeen = allSeen.concat(evs).slice(-200);
    } else {
      state = deriveState(allSeen);
    }
    if (state === 'HALTED') {
      hideWait();
    } else if (state && evs.length === 0 && Date.now() - lastEventAt > 3500) {
      // 运行中长时间无新事件 → 切换为"思考中"，让用户知道循环仍在推进
      showWait('agent 正在思考…');
    }
    await renderApprovals();
  } catch {}
}

// ───────── 用户动作 ─────────
$('start').onclick = async () => {
  // 任务框留空时给一个默认演示任务，避免空点击静默无反馈——离线降级下也能直接看到自修正闭环
  const task = $('task').value.trim() || 'implement add(a,b) returning the sum, verified by Jest';
  const btn = $('start');
  // 启动后驻留"等待大模型响应中…"，首事件到达或循环结束前持续显示
  lastEventAt = Date.now();
  showWait('等待大模型响应中…');
  try {
    const r = await fetch('/api/task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task, cwd: $('cwd').value }),
    });
    if (!r.ok) {
      // 409 busy：已有任务在跑；其他错误一并提示
      hideWait();
      const msg = r.status === 409 ? '已有任务在运行' : `提交失败 (${r.status})`;
      flash(btn, false, msg);
      return;
    }
    flash(btn, true, '已提交');
  } catch (e) {
    hideWait();
    flash(btn, false, '网络错误');
  }
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
  hideWait();
  flash($('clearEvents'), true, '已清空');
};

renderKeyStatus();
renderConfigStatus();
renderState(null);
setInterval(poll, 1000);
setInterval(renderKeyStatus, 5000);
setInterval(renderConfigStatus, 5000);
