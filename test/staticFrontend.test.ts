import http from 'http';
import { startWebServer } from '../src/web/webServer';
import { EventStore } from '../src/loop/eventSink';
import { HttpApprovalGateway } from '../src/approval/httpApprovalGateway';
import { EncryptedFileStore } from '../src/creds/credentialStore';
import * as os from 'os'; import * as fs from 'fs/promises'; import * as path from 'path';

test('GET / serves index.html', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'fe-'));
  const srv = await startWebServer({ port: 0, eventStore: new EventStore(), approval: new HttpApprovalGateway(), creds: new EncryptedFileStore(path.join(dir,'c.enc')), loopFactory: async () => ({haltReason:'finish',iterations:0}) });
  const port = (srv.server.address() as any).port;
  await new Promise<void>((r) => { http.get(`http://localhost:${port}/`, (res) => { let b=''; res.on('data',c=>b+=c); res.on('end',()=>{ expect(b).toContain('AI4SE-Safe-TDD-Harness'); r(); }); }); });
  srv.server.close();
});
