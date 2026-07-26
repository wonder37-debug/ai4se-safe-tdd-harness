import { makeLoopFactory } from '../src/index';
import { EncryptedFileStore } from '../src/creds/credentialStore';
import { JsonConfigStore } from '../src/creds/configStore';
import { HttpApprovalGateway } from '../src/approval/httpApprovalGateway';
import { EventStore } from '../src/loop/eventSink';
import * as os from 'os';
import * as fsp from 'fs/promises';
import * as path from 'path';

// 漏洞 1 集成：console:true 时 makeLoopFactory 把事件流与 LLM 回复实时打到 stdout。
// 离线 ScriptedMock 无 key → 自修正演示 → finish；断言 stdout 出现 [assistant]/[action]/[observation]。

test('console:true 实时流式打印 assistant 文本 + action + observation（离线）', async () => {
  const dir = await fsp.mkdtemp(path.join(os.tmpdir(), 'cli-stream-'));
  const logs: string[] = [];
  const spy = jest.spyOn(console, 'log').mockImplementation((...a) => logs.push(a.join(' ')));
  const prev = process.env.MASTER_PASSWORD;
  delete process.env.MASTER_PASSWORD;
  try {
    const run = makeLoopFactory({
      creds: new EncryptedFileStore(path.join(dir, 'c.enc')),
      config: new JsonConfigStore(path.join(dir, 'cfg.json')),
      approval: new HttpApprovalGateway(),
      eventStore: new EventStore(),
      console: true,
    });
    const r = await run('implement add', dir);
    expect(r.haltReason).toBe('finish');
    // LLM 自然语言/回复文本
    expect(logs.some((l) => l.includes('[assistant]'))).toBe(true);
    // 工具调用
    expect(logs.some((l) => l.includes('[action]'))).toBe(true);
    // 执行结果
    expect(logs.some((l) => l.includes('[observation]'))).toBe(true);
  } finally {
    spy.mockRestore();
    if (prev) process.env.MASTER_PASSWORD = prev;
  }
});
