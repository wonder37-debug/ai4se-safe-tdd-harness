import http from 'http';
import { readFileSync, existsSync } from 'fs';
import * as path from 'path';
import { EventStore } from '../loop/eventSink';
import { HttpApprovalGateway } from '../approval/httpApprovalGateway';
import { CredentialStore } from '../creds/credentialStore';
import { ConfigStore } from '../creds/configStore';

const PUB = path.join(__dirname, 'public');

export interface WebServerOpts {
  port: number;
  eventStore: EventStore;
  approval: HttpApprovalGateway;
  creds: CredentialStore;
  config: ConfigStore;
  loopFactory: (task: string, cwd: string) => Promise<{ haltReason: string; iterations: number }>;
}

export async function startWebServer(opts: WebServerOpts): Promise<{ server: http.Server }> {
  // Task 3：可选 bearer 鉴权。启动时读一次 HARNESS_TOKEN；
  // 已设置 → 除 GET /api/health 外所有 /api/* 必须带 Authorization: Bearer <token>；
  // 未设置 → 保持本地无认证行为，但打印醒目告警。
  const token = process.env.HARNESS_TOKEN;
  if (!token) {
    console.warn('[security] 未设置 HARNESS_TOKEN，Web 面板无认证，切勿公网暴露');
  }
  const host = process.env.HOST ?? '0.0.0.0';
  if (host !== '127.0.0.1' && host !== 'localhost') {
    console.warn(`[security] Web 面板绑定非回环地址 ${host}，局域网内均可访问；公网环境请配合 HARNESS_TOKEN`);
  }
  const authorized = (req: http.IncomingMessage): boolean => {
    if (!token) return true;
    return req.headers.authorization === `Bearer ${token}`;
  };
  const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json');
    const url = new URL(req.url ?? '', `http://localhost`);
    try {
      if (req.method === 'GET' && url.pathname === '/api/health') {
        res.end(JSON.stringify({ ok: true }));
      } else if (url.pathname.startsWith('/api/') && !authorized(req)) {
        res.statusCode = 401; res.end(JSON.stringify({ error: 'unauthorized' }));
      } else if (req.method === 'GET' && url.pathname === '/favicon.ico') {
        // 消除浏览器自动请求 favicon 的 404 噪声
        res.statusCode = 204; res.end();
      } else if (req.method === 'GET' && url.pathname === '/api/events') {
        const since = Number(url.searchParams.get('since') ?? '0');
        res.end(JSON.stringify(opts.eventStore.since(since)));
      } else if (req.method === 'GET' && url.pathname === '/api/key/status') {
        res.end(JSON.stringify(opts.creds.status()));
      } else if (req.method === 'GET' && url.pathname === '/api/config') {
        // 请求地址 / 模型名非密，可回显供前端回填
        res.end(JSON.stringify(await opts.config.get()));
      } else if (req.method === 'POST' && url.pathname === '/api/config') {
        const b = await body(req);
        await opts.config.set({ baseUrl: b.baseUrl, model: b.model });
        res.end(JSON.stringify(await opts.config.get()));
      } else if (req.method === 'GET' && url.pathname === '/api/approvals') {
        res.end(JSON.stringify(opts.approval.pending()));
      } else if (req.method === 'POST' && url.pathname === '/api/key') {
        const b = await body(req);
        await opts.creds.set(b.key, b.masterPassword);
        res.end(JSON.stringify(opts.creds.status()));
      } else if (req.method === 'POST' && url.pathname === '/api/approval') {
        const b = await body(req);
        const ok = opts.approval.resolve(b.id, { decision: b.decision, reason: b.reason ?? '' });
        res.end(JSON.stringify({ ok }));
      } else if (req.method === 'POST' && url.pathname === '/api/task') {
        const b = await body(req);
        // 仅当 loopFactory 短路返回 provider_error（未走 AgentLoop、内核未 emit halt）时，
        // 由 web 补 emit 一条 halt；正常 finish/cap/stuck 内核已 emit，不再重复。
        opts.loopFactory(b.task, b.cwd).then((r) => {
          if (r.haltReason === 'provider_error') {
            opts.eventStore.emit({ type: 'halt', payload: { reason: 'provider_error', iterations: r.iterations }, iter: 0 });
          }
        });
        res.end(JSON.stringify({ started: true }));
      } else if (req.method === 'GET') {
        // 静态前端面板（仅服务于 public/ 内文件，防路径穿越）
        const rel = url.pathname === '/' ? 'index.html' : decodeURIComponent(url.pathname.slice(1));
        const safe = path.normalize(path.join(PUB, rel));
        if (safe.startsWith(PUB) && existsSync(safe) && !safe.endsWith('.json') /* 保护 dangerPatterns 等 */) {
          res.setHeader('Content-Type', mime(safe));
          res.end(readFileSync(safe));
        } else {
          res.statusCode = 404; res.end(JSON.stringify({ error: 'not found' }));
        }
      } else {
        res.statusCode = 404; res.end(JSON.stringify({ error: 'not found' }));
      }
    } catch (e: any) {
      res.statusCode = 500; res.end(JSON.stringify({ error: String(e?.message ?? e) }));
    }
  });
  await new Promise<void>((r) => server.listen(opts.port, host, r));
  return { server };
}

function body(req: http.IncomingMessage): Promise<any> {
  return new Promise((resolve) => {
    let buf = '';
    req.on('data', (c) => (buf += c));
    req.on('end', () => resolve(buf ? JSON.parse(buf) : {}));
  });
}

function mime(p: string): string {
  if (p.endsWith('.js')) return 'text/javascript; charset=utf-8';
  if (p.endsWith('.css')) return 'text/css; charset=utf-8';
  if (p.endsWith('.svg')) return 'image/svg+xml';
  return 'text/html; charset=utf-8';
}
