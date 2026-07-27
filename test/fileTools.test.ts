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

// ───────── Task 5：工作区路径围栏 ────────
// 绝对路径/../ 穿越都不得逃出 ctx.cwd，防止 LLM 读写工作区外的任意文件。

test('read_file 绝对路径越界（/etc/shadow）→ ok:false', async () => {
  const cwd = await withTmpDir();
  const reg = new ToolRegistry([...fileTools]);
  const r = await reg.dispatch({ tool: 'read_file', args: { path: '/etc/shadow' } }, { cwd });
  expect(r.ok).toBe(false);
  expect(r.error).toMatch(/escapes workspace/);
});

test('write_file ../ 穿越越界→ ok:false 且目标文件未落盘', async () => {
  const cwd = await withTmpDir();
  const target = path.resolve(cwd, '../../escape.txt');
  await fs.rm(target, { force: true }); // 清理历史残留，保证断言只看本次行为
  const reg = new ToolRegistry([...fileTools]);
  const r = await reg.dispatch({ tool: 'write_file', args: { path: '../../escape.txt', content: 'x' } }, { cwd });
  expect(r.ok).toBe(false);
  expect(r.error).toMatch(/escapes workspace/);
  await expect(fs.access(target)).rejects.toThrow();
});

test('list_dir 越界（..）→ ok:false', async () => {
  const cwd = await withTmpDir();
  const reg = new ToolRegistry([...fileTools]);
  const r = await reg.dispatch({ tool: 'list_dir', args: { path: '..' } }, { cwd });
  expect(r.ok).toBe(false);
  expect(r.error).toMatch(/escapes workspace/);
});

test('合法子目录相对路径仍正常读写', async () => {
  const cwd = await withTmpDir();
  const reg = new ToolRegistry([...fileTools]);
  const w = await reg.dispatch({ tool: 'write_file', args: { path: 'sub/dir/b.txt', content: 'ok' } }, { cwd });
  expect(w.ok).toBe(true);
  const r = await reg.dispatch({ tool: 'read_file', args: { path: 'sub/dir/b.txt' } }, { cwd });
  expect(r.content).toBe('ok');
});
