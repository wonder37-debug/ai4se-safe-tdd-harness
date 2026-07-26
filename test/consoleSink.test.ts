import { ConsoleSink } from '../src/loop/eventSink';

// 漏洞 1 修复：REPL 会话实时打印事件流。ConsoleSink 把 AgentLoop 发出的事件
// 翻译为可读行：[action] 工具+参数 / [observation] 结果 / [approval] 裁决 / [halt] 终止。
// write 函数可注入，便于离线单测（默认 console.log）。

test('ConsoleSink 打印 action 行（含 tool 与 args）', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'action', payload: { tool: 'write_file', args: { path: 'a.txt', content: 'hi' } }, iter: 1 });
  expect(lines[0]).toContain('[action]');
  expect(lines[0]).toContain('write_file');
  expect(lines[0]).toContain('a.txt');
});

test('ConsoleSink 打印 observation 行', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'observation', payload: { ok: true, content: 'wrote a.txt' }, iter: 2 });
  expect(lines.some((l) => l.includes('[observation]'))).toBe(true);
  expect(lines.some((l) => l.includes('wrote a.txt'))).toBe(true);
});

test('ConsoleSink 打印 approval_decision 行（含 decision 与 reason）', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'approval_decision', payload: { decision: 'deny', reason: 'too dangerous' }, iter: 3 });
  expect(lines[0]).toContain('[approval]');
  expect(lines[0]).toContain('deny');
  expect(lines[0]).toContain('too dangerous');
});

test('ConsoleSink 打印 halt 行（含 reason）', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'halt', payload: { reason: 'finish' }, iter: 5 });
  expect(lines[0]).toContain('[halt]');
  expect(lines[0]).toContain('finish');
});

test('ConsoleSink 对未知事件类型不崩（静默跳过）', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  expect(() => sink.emit({ type: 'approval_request' as any, payload: {}, iter: 1 })).not.toThrow();
  expect(lines).toHaveLength(0);
});
