// AI4SE-Safe-TDD-Harness control panel — vanilla JS, HTTP polling
const $ = (id) => document.getElementById(id);
let since = 0;
let lastIter = 0;
let allSeen = [];

// ---------- loop state derivation from latest events ----------
function deriveState(events) {
  if (!events.length) return null;
  const last = events[events.length - 1];
  if (last.type === 'halt') return 'HALTED';
  // an approval_request without a following decision → pending
  const lastReqIdx = (() => {
    for (let i = events.length - 1; i >= 0; i--) if (events[i].type === 'approval_request') return i;
    return -1;
  })();
  if (lastReqIdx !== -1) {
    const after = events.slice(lastReqIdx + 1);
    if (!after.some(e => e.type === 'approval_decision')) return 'APPROVAL_PENDING';
  }
  // an action without a following observation/decision → executing
  if (last.type === 'action') return 'EXECUTING';
  return 'RUNNING';
}

function renderState(state) {
  const rail = $('stateRail');
  [...rail.children].forEach(li => li.classList.toggle('is-active', li.dataset.state === state));
}

// ---------- event stream ----------
function fmtPayload(ev) {
  const p = ev.payload;
  if (ev.type === 'action') return `${p.tool}  ${JSON.stringify(p.args)}`;
  if (ev.type === 'approval_request') return `${p.action.tool}  ${JSON.stringify(p.action.args)}  ← ${p.reasons.join('; ')}`;
  if (ev.type === 'approval_decision') return `${p.decision}  ${p.reason ?? ''}`;
  if (ev.type === 'halt') return `halt: ${JSON.stringify(p)}`;
  return JSON.stringify(p);
}

function appendEvents(events) {
  const list = $('events');
  const empty = list.querySelector('.event--empty');
  if (empty) empty.remove();
  for (const ev of events) {
    if (ev.iter) lastIter = Math.max(lastIter, ev.iter);
    const li = document.createElement('li');
    li.className = `event event--${ev.type}${ev.type === 'approval_decision' && ev.payload?.decision === 'deny' ? ' is-deny' : ''}`;
    li.innerHTML =
      `<span class="e-id">#${ev.id}</span>` +
      `<span class="e-type">${ev.type}</span>` +
      `<span class="e-body">${esc(fmtPayload(ev))}</span>`;
    list.appendChild(li);
  }
  list.scrollTop = list.scrollHeight;
  $('iterCounter').textContent = `iter ${lastIter}`;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ---------- approvals ----------
async function renderApprovals() {
  const ap = await fetch('/api/approvals').then(r => r.json()).catch(() => []);
  const box = $('approvals');
  if (!ap.length) {
    box.innerHTML = '<p class="approval--empty">当前无待审批请求。</p>';
    return;
  }
  box.innerHTML = '';
  for (const a of ap) {
    const card = document.createElement('div');
    card.className = 'approval-card';
    const cmd = a.action?.args?.command ?? JSON.stringify(a.action?.args ?? {});
    card.innerHTML =
      `<div class="ac-tool">⚙ ${esc(a.action?.tool ?? '?')}</div>` +
      `<div class="ac-cmd">${esc(String(cmd))}</div>` +
      `<div class="ac-reasons">${esc(a.reasons.join(' · '))}</div>` +
      `<div class="ac-actions">` +
        `<button class="btn btn--approve" data-id="${esc(a.id)}" data-d="approve">批准</button>` +
        `<button class="btn btn--deny" data-id="${esc(a.id)}" data-d="deny">拒绝</button>` +
      `</div>`;
    box.appendChild(card);
  }
}

$('approvals').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-id]');
  if (!b) return;
  decide(b.dataset.id, b.dataset.d);
});

function decide(id, d) {
  fetch('/api/approval', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, decision: d, reason: 'browser' }),
  }).then(renderApprovals);
}

// ---------- key status ----------
async function renderKeyStatus() {
  try {
    const s = await fetch('/api/key/status').then(r => r.json());
    const el = $('keystatus');
    el.classList.toggle('is-present', !!s.present);
    el.textContent = `key 状态：${s.present ? '已配置 · ' + s.source : '未配置（保存后将加密落盘）'}`;
  } catch {}
}

// ---------- polling loop ----------
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

// ---------- actions ----------
$('start').onclick = () => {
  if (!$('#task').value.trim()) return;
  fetch('/api/task', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task: $('#task').value, cwd: $('#cwd').value }),
  });
};
$('setkey').onclick = () => {
  const key = $('#apikey').value;
  const master = $('#master').value;
  if (!key || !master) return;
  fetch('/api/key', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, masterPassword: master }),
  }).then(renderKeyStatus);
};
$('clearEvents').onclick = () => {
  const list = $('events');
  list.innerHTML = '<li class="event event--empty">已清空显示（事件仍在后端）。</li>';
  lastIter = 0;
  $('iterCounter').textContent = 'iter 0';
};

renderKeyStatus();
renderState(null);
setInterval(poll, 1000);
setInterval(renderKeyStatus, 5000);
