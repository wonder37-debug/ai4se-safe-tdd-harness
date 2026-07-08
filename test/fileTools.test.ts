import { ToolRegistry } from '../src/tools/tool';
import { fileTools } from '../src/tools/fileTools';
import * as path from 'path';
import * as fs from 'fs/promises';
import * as os from 'os';

async function withTmpDir(): Promise<string> {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'harness-'));
  return dir;
}

test('write_file then read_file roundtrip', async () => {
  const cwd = await withTmpDir();
  const reg = new ToolRegistry([...fileTools]);
  const w = await reg.dispatch({ tool: 'write_file', args: { path: 'a.txt', content: 'hi' } }, { cwd });
  expect(w.ok).toBe(true);
  const r = await reg.dispatch({ tool: 'read_file', args: { path: 'a.txt' } }, { cwd });
  expect(r.content).toBe('hi');
});

test('list_dir lists entries', async () => {
  const cwd = await withTmpDir();
  const reg = new ToolRegistry([...fileTools]);
  await reg.dispatch({ tool: 'write_file', args: { path: 'a.txt', content: 'x' } }, { cwd });
  const l = await reg.dispatch({ tool: 'list_dir', args: { path: '.' } }, { cwd });
  expect(l.content).toContain('a.txt');
});

test('read_file on missing file returns ok:false with error', async () => {
  const cwd = await withTmpDir();
  const reg = new ToolRegistry([...fileTools]);
  const r = await reg.dispatch({ tool: 'read_file', args: { path: 'nope.txt' } }, { cwd });
  expect(r.ok).toBe(false);
  expect(r.error).toMatch(/no such file/i);
});
