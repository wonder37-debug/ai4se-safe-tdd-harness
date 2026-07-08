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

test('run_shell captures non-zero exit and stderr', async () => {
  const cwd = await fs.mkdtemp(path.join(os.tmpdir(), 'h-'));
  const reg = new ToolRegistry([...shellTools]);
  const cmd = process.platform === 'win32' ? 'node -e "process.stderr.write(\\\"boom\\\");process.exit(1)"'
    : 'node -e "process.stderr.write(\'boom\');process.exit(1)"';
  const r = await reg.dispatch({ tool: 'run_shell', args: { command: cmd } }, { cwd });
  expect(r.exitCode).toBe(1);
  expect(r.stderr).toContain('boom');
});
