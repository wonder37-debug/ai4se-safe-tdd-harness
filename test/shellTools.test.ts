import { ToolRegistry } from '../src/tools/tool';
import { shellTools } from '../src/tools/shellTools';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';

test('run_shell captures stdout and exitCode 0', async () => {
  const cwd = await fs.mkdtemp(path.join(os.tmpdir(), 'h-'));
  const reg = new ToolRegistry([...shellTools]);
  const cmd = process.platform === 'win32' ? 'echo hello' : 'echo hello';
  const r = await reg.dispatch({ tool: 'run_shell', args: { command: cmd } }, { cwd });
  expect(r.ok).toBe(true);
  expect(r.exitCode).toBe(0);
  expect((r.stdout ?? '').trim()).toBe('hello');
});

// ───────── Task 14：args.command 缺省校验 ─────────
test('run_shell / run_tests reject missing or non-string command without spawning', async () => {
  const cwd = await fs.mkdtemp(path.join(os.tmpdir(), 'h-'));
  const reg = new ToolRegistry([...shellTools]);
  const cp = require('child_process');
  const spy = jest.spyOn(cp, 'exec');
  try {
    for (const tool of ['run_shell', 'run_tests'] as const) {
      for (const args of [{}, { command: 42 }, { command: '   ' }]) {
        const r = await reg.dispatch({ tool, args: args as any }, { cwd });
        expect(r.ok).toBe(false);
        expect(r.error).toBe('missing command');
      }
    }
    // 全部非法输入均不应触发子进程
    expect(spy).not.toHaveBeenCalled();
  } finally {
    spy.mockRestore();
  }
});

test('run_shell captures non-zero exit and stderr', async () => {
  const cwd = await fs.mkdtemp(path.join(os.tmpdir(), 'h-'));
  const reg = new ToolRegistry([...shellTools]);
  const cmd = process.platform === 'win32' ? 'node -e "process.stderr.write(\\\"boom\\\");process.exit(1)"'
    : 'node -e "process.stderr.write(\'boom\');process.exit(1)"';
  const r = await reg.dispatch({ tool: 'run_shell', args: { command: cmd } }, { cwd });
  expect(r.exitCode).toBe(1);
  expect(r.stderr).toContain('boom');
});
