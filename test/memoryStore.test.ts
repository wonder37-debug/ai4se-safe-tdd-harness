import { MemoryStore } from '../src/memory/memoryStore';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';

test('write then read roundtrip; clear removes', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'mem-'));
  const ms = new MemoryStore(dir);
  await ms.write('convention', 'use camelCase');
  const notes = await ms.read();
  expect(notes.find(n => n.key === 'convention')?.note).toBe('use camelCase');
  await ms.clear('convention');
  expect((await ms.read()).find(n => n.key === 'convention')).toBeUndefined();
});

test('system prompt includes notes', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'mem-'));
  const ms = new MemoryStore(dir);
  await ms.write('dec', 'decided X');
  expect(await ms.systemPrompt()).toContain('decided X');
});

// ───────── Task 10：统一异步 fs（fs/promises），清理 require 混用 ─────────

test('read/clear 为异步 API；clear() 后文件确实不存在', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'mem-'));
  const ms = new MemoryStore(dir);
  await ms.write('k', 'v');
  const p = ms.read();
  expect(p).toBeInstanceOf(Promise); // 异步契约：不再是同步 readdirSync
  expect((await p).find(n => n.key === 'k')?.note).toBe('v');
  await ms.clear('k');
  await expect(fs.access(path.join(dir, 'k.md'))).rejects.toThrow();
});

test('目录不存在时 read 返回空数组（不抛错）', async () => {
  const ms = new MemoryStore(path.join(os.tmpdir(), 'mem-not-exist-' + Date.now()));
  expect(await ms.read()).toEqual([]);
  expect(await ms.systemPrompt()).toBe('');
});
