import { MemoryStore } from '../src/memory/memoryStore';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';

test('write then read roundtrip; clear removes', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'mem-'));
  const ms = new MemoryStore(dir);
  await ms.write('convention', 'use camelCase');
  const notes = ms.read();
  expect(notes.find(n => n.key === 'convention')?.note).toBe('use camelCase');
  ms.clear('convention');
  expect(ms.read().find(n => n.key === 'convention')).toBeUndefined();
});

test('system prompt includes notes', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'mem-'));
  const ms = new MemoryStore(dir);
  await ms.write('dec', 'decided X');
  expect(ms.systemPrompt()).toContain('decided X');
});
