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

test('POST /api_task 正常 finish 不再双 emit halt（仅 provider_error 才补 emit）', async () => {
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

test('POST /api/task provider_error 时 web 补 emit 一条 halt（短路上未走 AgentLoop）', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'web3-'));
  const store = new EventStore();
  const srv = await startWebServer({
    port: 0, eventStore: store, approval: new HttpApprovalGateway(),
    creds: new EncryptedFileStore(path.join(dir, 'c.enc')),
    config: new JsonConfigStore(path.join(dir, 'config.json')),
    loopFactory: async () => ({ haltReason: 'provider_error', iterations: 0 }),
  });
  const port = (srv.server.address() as any).port;
  try {
    await req('POST', port, '/api/task', { task: 't', cwd: dir });
    const evs = await req('GET', port, '/api/events?since=0');
    const halts = (evs.body as any[]).filter(e => e.type === 'halt');
    expect(halts.length).toBe(1); // provider_error 未走内核，web 补 emit
    expect(halts[0].payload.reason).toBe('provider_error');
  } finally { srv.server.close(); }
});
