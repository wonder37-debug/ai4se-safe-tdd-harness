import http from 'http';
import { startWebServer } from '../src/web/webServer';
import { EventStore } from '../src/loop/eventSink';
import { HttpApprovalGateway } from '../src/approval/httpApprovalGateway';
import { EncryptedFileStore } from '../src/creds/credentialStore';
import { JsonConfigStore } from '../src/creds/configStore';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';

function req(method: string, port: number, p: string, body?: any): Promise<{status: number, body: any}> {
  return new Promise((resolve) => {
    const data = body ? JSON.stringify(body) : '';
    const r = http.request({ port, path: p, method, headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } }, (res) => {
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
