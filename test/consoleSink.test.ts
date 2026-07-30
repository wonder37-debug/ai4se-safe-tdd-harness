import { ConsoleSink } from '../src/loop/eventSink';

// 人性化终端输出：放弃 JSON.stringify，把 action/observation/halt 翻译为自然语言行。

test('action: write_file → 📄 写入文件: <path>，不再泄漏 JSON', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'action', payload: { tool: 'write_file', args: { path: 'add.js', content: 'module.exports=...' } }, iter: 1 });
  expect(lines[0]).toContain('📄');
  expect(lines[0]).toContain('写入文件');
  expect(lines[0]).toContain('add.js');
  expect(lines[0]).not.toContain('{');          // 不再 JSON.stringify
  expect(lines[0]).not.toContain('write_file'); // 工具名翻译为中文动词
});

test('action: read_file → 📖 读取文件: <path>', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'action', payload: { tool: 'read_file', args: { path: 'add.test.js' } }, iter: 1 });
  expect(lines[0]).toContain('📖');
  expect(lines[0]).toContain('add.test.js');
});

test('action: run_tests → 🧪 运行测试: <command>', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'action', payload: { tool: 'run_tests', args: { command: 'npx jest' } }, iter: 1 });
  expect(lines[0]).toContain('🧪');
  expect(lines[0]).toContain('npx jest');
});

test('observation: 成功 → ✅ 已写入（承接上一 action 工具）', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'action', payload: { tool: 'write_file', args: { path: 'a' } }, iter: 1 });
  sink.emit({ type: 'observation', payload: { ok: true, content: 'wrote a' }, iter: 1 });
  const obs = lines[1];
  expect(obs).toContain('✅');
  expect(obs).toContain('已写入');
  expect(obs).not.toContain('{');        // 不再 JSON 字典
  expect(obs).not.toContain('wrote a');  // 成功时不打印冗余 content
});

test('observation: run_tests 成功 → ✅ 测试通过（不打印 stdout）', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'action', payload: { tool: 'run_tests', args: { command: 'x' } }, iter: 1 });
  sink.emit({ type: 'observation', payload: { ok: true, exitCode: 0, stdout: 'huge output' }, iter: 1 });
  expect(lines[1]).toContain('测试通过');
  expect(lines[1]).not.toContain('huge output');
});

test('observation: 断言失败 → ❌ 断言失败 file:line + hint（不打印 evidence）', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'action', payload: { tool: 'run_tests', args: {} }, iter: 1 });
  sink.emit({
    type: 'observation',
    payload: {
      errorType: 'assertion', failedTests: ['t'],
      assertion: { file: 'add.test.js', line: 4, snippet: 'x' },
      evidence: 'long raw stderr', hint: 'adjust implementation so add.test.js:4 assertion passes',
    },
    iter: 1,
  });
  expect(lines[1]).toContain('❌');
  expect(lines[1]).toContain('add.test.js:4');
  expect(lines[1]).toContain('💡');
  expect(lines[1]).not.toContain('long raw stderr');
});

test('observation: 语法失败 → ❌ 语法错误 file:line', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'action', payload: { tool: 'run_tests', args: {} }, iter: 1 });
  sink.emit({ type: 'observation', payload: { errorType: 'syntax', assertion: { file: 'a.js', line: 5, snippet: '' }, evidence: 'x', hint: 'h' }, iter: 1 });
  expect(lines[1]).toContain('语法错误');
  expect(lines[1]).toContain('a.js:5');
});

test('observation: 普通工具失败 → ❌ error 首行', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'action', payload: { tool: 'read_file', args: { path: 'x' } }, iter: 1 });
  sink.emit({ type: 'observation', payload: { ok: false, error: 'ENOENT: no such file or directory' }, iter: 1 });
  expect(lines[1]).toContain('❌');
  expect(lines[1]).toContain('ENOENT');
});

test('halt: finish → 🏁 任务完成（无 JSON）', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'halt', payload: { reason: 'finish' }, iter: 5 });
  expect(lines[0]).toContain('🏁');
  expect(lines[0]).not.toContain('{');
});

test('halt: stuck → 卡死停机', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'halt', payload: { reason: 'stuck', key: 'a.js:4' }, iter: 5 });
  expect(lines[0]).toContain('卡死');
});

test('approval: deny → 🚫 拒绝 — reason', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'approval_decision', payload: { decision: 'deny', reason: 'too dangerous' }, iter: 2 });
  expect(lines[0]).toContain('拒绝');
  expect(lines[0]).toContain('too dangerous');
});

test('长命令被截断（不溢出终端，带 …）', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  const longCmd = 'node -e "' + 'x'.repeat(200) + '"';
  sink.emit({ type: 'action', payload: { tool: 'run_shell', args: { command: longCmd } }, iter: 1 });
  expect(lines[0].length).toBeLessThan(80);
  expect(lines[0]).toContain('…');
});

test('thought: 自然语言思考 → 🤖 前缀，保留多段，不泄漏围栏/JSON', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  sink.emit({ type: 'thought', payload: { text: '先写实现，故意留 bug。\n再跑测试验证自修正。' }, iter: 1 });
  expect(lines[0]).toContain('🤖');
  expect(lines[0]).toContain('故意留 bug');
  expect(lines[0]).toContain('再跑测试');
  expect(lines[0]).not.toContain('{');
  expect(lines[0]).not.toContain('```action');
});

test('未知事件类型不崩（静默跳过）', () => {
  const lines: string[] = [];
  const sink = new ConsoleSink((l) => lines.push(l));
  expect(() => sink.emit({ type: 'approval_request' as any, payload: {}, iter: 1 })).not.toThrow();
  expect(lines).toHaveLength(0);
});
