import { buildSystemPrompt } from '../src/index';

// buildSystemPrompt 把任务 + 平台信息组装成 system prompt。

test('buildSystemPrompt 含任务文本与 action 格式块', () => {
  const p = buildSystemPrompt('实现 add(a,b)', 'linux');
  expect(p).toContain('实现 add(a,b)');
  expect(p).toContain('```action');
  expect(p).toContain('Platform:');
});

test('buildSystemPrompt 注入平台字符串', () => {
  expect(buildSystemPrompt('t', 'win32')).toContain('win32');
  expect(buildSystemPrompt('t', 'darwin')).toContain('darwin');
});

test('Windows 平台提示用 del/Remove-Item 而非 rm', () => {
  const p = buildSystemPrompt('t', 'win32');
  expect(p).toContain('Windows');
  expect(p).toContain('del');
  expect(p).toContain('Remove-Item');
  expect(p).toMatch(/not\s*`?rm/i);
});

test('Unix 平台提示用 rm/ls', () => {
  const p = buildSystemPrompt('t', 'darwin');
  expect(p).toMatch(/`?rm/);
  expect(p).toMatch(/`?ls/);
});
