import { makeLoopFactory } from '../src/index';
import { EncryptedFileStore } from '../src/creds/credentialStore';
import { JsonConfigStore } from '../src/creds/configStore';
import { HttpApprovalGateway } from '../src/approval/httpApprovalGateway';
import { EventStore } from '../src/loop/eventSink';
import * as os from 'os';
import * as fsp from 'fs/promises';
import * as path from 'path';

// 人性化流式：console:true 时
// ① AgentLoop 把 LLM 回复剥除 ```action 围栏后的自然语言思考作为 thought 事件发出，
//    ConsoleSink 渲染 🤖 行；action/observation 翻译为自然语言行，不再 JSON.stringify。
// 离线 ScriptedMock 演示回复含自然语言思考 + 围栏 → 终端出现 🤖 思考行，
// 且 action/observation 已人性化；关键：终端绝不泄漏裸露 ```action 围栏与 "tool" JSON 字面。

test('console:true 人性化流式：翻译 action/observation，过滤裸露 action 围栏', async () => {
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
    // action 已翻译为自然语言动词
    expect(logs.some((l) => l.includes('写入文件'))).toBe(true);
    expect(logs.some((l) => l.includes('运行测试'))).toBe(true);
    // observation 极简
    expect(logs.some((l) => l.includes('已写入'))).toBe(true);
    expect(logs.some((l) => l.includes('断言失败') || l.includes('测试通过') || l.includes('测试失败'))).toBe(true);
    // 关键：终端绝不泄漏裸露 ```action 围栏
    expect(logs.every((l) => !l.includes('```action'))).toBe(true);
    // 不再有粗暴 JSON.stringify 的 action/observation 字典（无 "tool":... 字面）
    expect(logs.every((l) => !l.includes('"tool"'))).toBe(true);
  } finally {
    spy.mockRestore();
    if (prev) process.env.MASTER_PASSWORD = prev;
  }
});
