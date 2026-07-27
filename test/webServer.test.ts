import http from 'http';
import { startWebServer } from '../src/web/webServer';
import { EventStore } from '../src/loop/eventSink';
import { HttpApprovalGateway } from '../src/approval/httpApprovalGateway';
import { EncryptedFileStore } from '../src/creds/credentialStore';
import { JsonConfigStore } from '../src/creds/configStore';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';

function req(method: string, port: number, p: string, body?: any, headers?: Record<string, string>): Promise<{status: number, body: any}> {
  return new Promise((resolve) => {
    const data = body ? JSON.stringify(body) : '';
    const r = http.request({ port, path: p, method, headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data), ...(headers ?? {}) } }, (res) => {
      let buf = '';
      res.on('data', (c) => (buf += c));
      res.on('end', () => resolve({ status: res.statusCode ?? 0, body: buf ? JSON.parse(buf) : {} }));
    });
    r.write(data); r.end();
  });
}

async function boot() {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'web-'));
  const srv = await startWebServer({
    port: 0, eventStore: new EventStore(), approval: new HttpApprovalGateway(),
    creds: new EncryptedFileStore(path.join(dir, 'c.enc')),
    config: new JsonConfigStore(path.join(dir, 'config.json')),
    loopFactory: async () => ({ haltReason: 'finish', iterations: 0 }),
  });
  return { srv, port: (srv.server.address() as any).port, dir };
}

test('GET /api/health returns 200; events poll empty initially', async () => {
  const { srv, port } = await boot();
  try {
    const h = await req('GET', port, '/api/health');
    expect(h.status).toBe(200);
    const e = await req('GET', port, '/api/events?since=0');
    expect(Array.isArray(e.body)).toBe(true);
  } finally { srv.server.close(); }
});

test('GET /api/config 初始为空对象（未配置）', async () => {
  const { srv, port } = await boot();
  try {
    const r = await req('GET', port, '/api/config');
    expect(r.status).toBe(200);
    expect(r.body).toEqual({});
  } finally { srv.server.close(); }
});

test('POST /api/config 写入后 GET 回显 baseUrl / model（非密，可回显）', async () => {
  const { srv, port } = await boot();
  try {
    const set = await req('POST', port, '/api/config', { baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' });
    expect(set.status).toBe(200);
    expect(set.body).toEqual({ baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' });
    const get = await req('GET', port, '/api/config');
    expect(get.body).toEqual({ baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' });
  } finally { srv.server.close(); }
});

test('POST /api/config 可只更新单字段（保留另一字段）', async () => {
  const { srv, port } = await boot();
  try {
    await req('POST', port, '/api/config', { baseUrl: 'https://x/v1', model: 'm1' });
    // 只改 model，baseUrl 应保持
    const r = await req('POST', port, '/api/config', { baseUrl: 'https://x/v1', model: 'm2' });
    expect(r.body).toEqual({ baseUrl: 'https://x/v1', model: 'm2' });
  } finally { srv.server.close(); }
});

test('GET /favicon.ico 返回 204（消除浏览器 404 噪声）', async () => {
  const { srv, port } = await boot();
  try {
    const r = await req('GET', port, '/favicon.ico');
    expect(r.status).toBe(204);
  } finally { srv.server.close(); }
});

// ───────── Task 3：可选 bearer 鉴权（HARNESS_TOKEN） ────────

describe('HARNESS_TOKEN 鉴权', () => {
  afterEach(() => { delete process.env.HARNESS_TOKEN; });

  test('设置 token 后：无 Authorization 的 /api/events → 401', async () => {
    process.env.HARNESS_TOKEN = 'secret';
    const { srv, port } = await boot();
    try {
      const r = await req('GET', port, '/api/events?since=0');
      expect(r.status).toBe(401);
    } finally { srv.server.close(); }
  });

  test('设置 token 后：带正确 Bearer → 200', async () => {
    process.env.HARNESS_TOKEN = 'secret';
    const { srv, port } = await boot();
    try {
      const r = await req('GET', port, '/api/events?since=0', undefined, { Authorization: 'Bearer secret' });
      expect(r.status).toBe(200);
      expect(Array.isArray(r.body)).toBe(true);
    } finally { srv.server.close(); }
  });

  test('设置 token 后：错误 token → 401；/api/health 豁免仍 200', async () => {
    process.env.HARNESS_TOKEN = 'secret';
    const { srv, port } = await boot();
    try {
      const bad = await req('GET', port, '/api/events?since=0', undefined, { Authorization: 'Bearer wrong' });
      expect(bad.status).toBe(401);
      const health = await req('GET', port, '/api/health');
      expect(health.status).toBe(200);
    } finally { srv.server.close(); }
  });

  test('未设 token：保持原有无认证行为', async () => {
    const { srv, port } = await boot();
    try {
      const r = await req('GET', port, '/api/events?since=0');
      expect(r.status).toBe(200);
    } finally { srv.server.close(); }
  });
});

test('POST /api_task 正常 finish 不双 emit halt（内核 sink 统一发出，web 不补）', async () => {
  // stub loopFactory 返回 finish 且不自行 emit（模拟 AgentLoop 已 emit 的场景）
  // → webServer 不应再补一条 halt
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'web2-'));
  const store = new EventStore();
  const srv = await startWebServer({
    port: 0, eventStore: store, approval: new HttpApprovalGateway(),
    creds: new EncryptedFileStore(path.join(dir, 'c.enc')),
    config: new JsonConfigStore(path.join(dir, 'config.json')),
    loopFactory: async () => ({ haltReason: 'finish', iterations: 3 }),
  });
  const port = (srv.server.address() as any).port;
  try {
    await req('POST', port, '/api/task', { task: 't', cwd: dir });
    const evs = await req('GET', port, '/api/events?since=0');
    const halts = (evs.body as any[]).filter(e => e.type === 'halt');
    expect(halts.length).toBe(0); // finish 由内核 emit，web 不再补
  } finally { srv.server.close(); }
});

test('POST /api/task provider_error：halt 仅由内核 emit 一次，web 不重复补（T9）', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'web3-'));
  const store = new EventStore();
  const srv = await startWebServer({
    port: 0, eventStore: store, approval: new HttpApprovalGateway(),
    creds: new EncryptedFileStore(path.join(dir, 'c.enc')),
    config: new JsonConfigStore(path.join(dir, 'config.json')),
    // 模拟真实 makeLoopFactory：AgentLoop 内部遭遇 provider 异常时已经通过 sink emit 了 halt
    loopFactory: async () => {
      store.emit({ type: 'halt', payload: { reason: 'provider_error', error: 'provider_error: boom' }, iter: 1 });
      return { haltReason: 'provider_error', iterations: 1 };
    },
  });
  const port = (srv.server.address() as any).port;
  try {
    await req('POST', port, '/api/task', { task: 't', cwd: dir });
    await new Promise((r) => setTimeout(r, 50)); // 等后台 then 链跑完
    const evs = await req('GET', port, '/api/events?since=0');
    const halts = (evs.body as any[]).filter(e => e.type === 'halt');
    expect(halts.length).toBe(1); // 仅内核一条，web 不重复补
    expect(halts[0].payload.reason).toBe('provider_error');
  } finally { srv.server.close(); }
});

// ───────── Task 8：body 大小上限 + 单任务并发保护 ─────────

test('POST body 超过 1MB → 413', async () => {
  const { srv, port } = await boot();
  try {
    const big = 'x'.repeat(1024 * 1024 + 100); // 略超 1MB
    const r = await req('POST', port, '/api/config', { baseUrl: big, model: 'm' });
    expect(r.status).toBe(413);
  } finally { srv.server.close(); }
});

test('任务进行中再次 POST /api/task → 409 busy；结束后可再提交', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'web4-'));
  // 可控长任务：gate resolve 前 loopFactory 不返回，模拟 in-flight
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  const srv = await startWebServer({
    port: 0, eventStore: new EventStore(), approval: new HttpApprovalGateway(),
    creds: new EncryptedFileStore(path.join(dir, 'c.enc')),
    config: new JsonConfigStore(path.join(dir, 'config.json')),
    loopFactory: async () => { await gate; return { haltReason: 'finish', iterations: 1 }; },
  });
  const port = (srv.server.address() as any).port;
  try {
    const first = await req('POST', port, '/api/task', { task: 'a', cwd: dir });
    expect(first.status).toBe(200);
    expect(first.body).toEqual({ started: true });
    const second = await req('POST', port, '/api/task', { task: 'b', cwd: dir });
    expect(second.status).toBe(409);
    expect(second.body.error).toBe('busy');
    // 任务结束后可再次提交
    release();
    await new Promise((r) => setTimeout(r, 50));
    const third = await req('POST', port, '/api/task', { task: 'c', cwd: dir });
    expect(third.status).toBe(200);
  } finally { release(); srv.server.close(); }
});
