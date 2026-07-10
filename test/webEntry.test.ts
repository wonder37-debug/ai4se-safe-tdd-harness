import { makeLoopFactory } from '../src/index';
import { EncryptedFileStore } from '../src/creds/credentialStore';
import { HttpApprovalGateway } from '../src/approval/httpApprovalGateway';
import { EventStore } from '../src/loop/eventSink';
import * as os from 'os';
import * as fsp from 'fs/promises';
import * as path from 'path';

// makeLoopFactory 现在二选一：检测到有效 Key → OpenAICompatProvider（在线）；
// 否则降级 ScriptedMock 跑自修正 TDD 演示（离线）。两条路径都不触网即可确定性单测：
// 离线路径用 ScriptedMock（无网络）；在线路径用注入的 fake fetch（无网络）。

function factory(dir: string) {
  return makeLoopFactory({
    creds: new EncryptedFileStore(path.join(dir, 'c.enc')),
    approval: new HttpApprovalGateway(),
    eventStore: new EventStore(),
  });
}

// 离线降级：无 MASTER_PASSWORD → ScriptedMock 自修正演示 → finish，且 add(2,3)===5。
test('offline fallback runs self-repair demo when no key (no network)', async () => {
  const dir = await fsp.mkdtemp(path.join(os.tmpdir(), 'lf1-'));
  const prev = process.env.MASTER_PASSWORD;
  delete process.env.MASTER_PASSWORD;
  try {
    const r = await factory(dir)('implement add', dir);
    expect(r.haltReason).toBe('finish');
    const add = require(path.join(dir, 'add.js'));
    expect(add(2, 3)).toBe(5);
  } finally {
    if (prev) process.env.MASTER_PASSWORD = prev;
  }
});

// 离线降级：主密码+端点已设但凭据不可解（未录入 key）→ 仍降级 ScriptedMock，而非崩 provider_error。
test('offline fallback when creds unresolvable (no network)', async () => {
  const dir = await fsp.mkdtemp(path.join(os.tmpdir(), 'lf2-'));
  const prevM = process.env.MASTER_PASSWORD;
  const prevB = process.env.API_BASE_URL;
  process.env.MASTER_PASSWORD = 'x';
  process.env.API_BASE_URL = 'https://example.invalid';
  try {
    const r = await factory(dir)('implement add', dir);
    expect(r.haltReason).toBe('finish');
  } finally {
    if (prevM) process.env.MASTER_PASSWORD = prevM; else delete process.env.MASTER_PASSWORD;
    if (prevB) process.env.API_BASE_URL = prevB; else delete process.env.API_BASE_URL;
  }
});

// 在线路径：录入有效 key + 端点 → 走 OpenAICompatProvider。
// 用注入 fake fetch 拦截网络，断言 fetch 被调用（说明选了在线 provider 而非离线 mock）。
test('online path selects OpenAICompatProvider when key resolvable (fake fetch, no network)', async () => {
  const dir = await fsp.mkdtemp(path.join(os.tmpdir(), 'lf3-'));
  const prevM = process.env.MASTER_PASSWORD;
  const prevB = process.env.API_BASE_URL;
  process.env.MASTER_PASSWORD = 'masterpw';
  process.env.API_BASE_URL = 'https://example.invalid';
  // 录入一个真实可解的 key
  const creds = new EncryptedFileStore(path.join(dir, 'c.enc'));
  await creds.set('sk-demo', 'masterpw');
  // 拦截 fetch：返回一个 finish 动作，使循环立即结束，不触网
  const calls: any[] = [];
  const fakeFetch = async (url: string, init: any) => {
    calls.push({ url, body: init?.body });
    return {
      ok: true,
      status: 200,
      json: async () => ({
        choices: [{ message: { content: '```action\n' + JSON.stringify({ tool: 'finish', args: {} }) + '\n```' }, finish_reason: 'stop' }],
      }),
    };
  };
  const g = (globalThis as any);
  const prevFetch = g.fetch;
  g.fetch = fakeFetch;
  try {
    const lf = makeLoopFactory({ creds, approval: new HttpApprovalGateway(), eventStore: new EventStore() });
    const r = await lf('do something', dir);
    expect(r.haltReason).toBe('finish');
    expect(calls.length).toBeGreaterThan(0);
    // 在线 provider 发出的 messages 不应含非法 observation 角色（adaptMessages 已适配）
    const sent = JSON.parse(calls[0].body).messages;
    expect(sent.every((m: any) => m.role !== 'observation')).toBe(true);
  } finally {
    g.fetch = prevFetch;
    if (prevM) process.env.MASTER_PASSWORD = prevM; else delete process.env.MASTER_PASSWORD;
    if (prevB) process.env.API_BASE_URL = prevB; else delete process.env.API_BASE_URL;
  }
});
