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
  // Task 8：单任务并发保护——同一时刻只允许一个 loop 在跑，并发提交返回 409
  let taskRunning = false;
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
        if (taskRunning) {
          res.statusCode = 409; res.end(JSON.stringify({ error: 'busy' }));
          return;
        }
        const b = await body(req);
        taskRunning = true;
        // halt 事件由 AgentLoop 的 sink 统一发出（含 provider_error，见 agentLoop.ts），
        // web 层不再重复补 emit，避免事件流出现双 halt。
        opts.loopFactory(b.task, b.cwd).finally(() => { taskRunning = false; });
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
      // body 超限等携带 status 的错误按其状态码返回，其余 500
      res.statusCode = e?.status ?? 500; res.end(JSON.stringify({ error: String(e?.message ?? e) }));
    }
  });
  await new Promise<void>((r) => server.listen(opts.port, host, r));
  return { server };
}

// 读取请求 body（JSON）；超过 maxBytes（默认 1MB）抛 413，防恶意大包打爆内存
function body(req: http.IncomingMessage, maxBytes = 1024 * 1024): Promise<any> {
  return new Promise((resolve, reject) => {
    let buf = '';
    let size = 0;
    req.on('data', (c) => {
      size += c.length;
      if (size > maxBytes) {
        // 停止累积并排空剩余数据（不 destroy socket，保证 413 响应能送达客户端）
        req.removeAllListeners('data');
        req.removeAllListeners('end');
        req.resume();
        reject(Object.assign(new Error('payload too large'), { status: 413 }));
        return;
      }
      buf += c;
    });
    req.on('end', () => resolve(buf ? JSON.parse(buf) : {}));
  });
}

function mime(p: string): string {
  if (p.endsWith('.js')) return 'text/javascript; charset=utf-8';
  if (p.endsWith('.css')) return 'text/css; charset=utf-8';
  if (p.endsWith('.svg')) return 'image/svg+xml';
  return 'text/html; charset=utf-8';
}
