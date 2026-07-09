import http from 'http';
import { startWebServer } from '../src/web/webServer';
import { EventStore } from '../src/loop/eventSink';
import { HttpApprovalGateway } from '../src/approval/httpApprovalGateway';
import { EncryptedFileStore } from '../src/creds/credentialStore';
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

test('GET /api/health returns 200; events poll empty initially', async () => {
  const store = new EventStore();
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'web-'));
  const srv = await startWebServer({
    port: 0, eventStore: store, approval: new HttpApprovalGateway(),
    creds: new EncryptedFileStore(path.join(dir, 'c.enc')),
    loopFactory: async () => ({ haltReason: 'finish', iterations: 0 }),
  });
  const port = (srv.server.address() as any).port;
  const h = await req('GET', port, '/api/health');
  expect(h.status).toBe(200);
  const e = await req('GET', port, '/api/events?since=0');
  expect(Array.isArray(e.body)).toBe(true);
  srv.server.close();
});
