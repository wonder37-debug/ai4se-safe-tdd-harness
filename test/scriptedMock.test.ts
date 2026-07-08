import { ScriptedMock } from '../src/llm/scriptedMock';

test('returns queued responses in order', async () => {
  const llm = new ScriptedMock(['first', 'second']);
  expect((await llm.complete([])).text).toBe('first');
  expect((await llm.complete([])).text).toBe('second');
});

test('sticky last response when queue empties', async () => {
  const llm = new ScriptedMock(['only'], true);
  await llm.complete([]);
  expect((await llm.complete([])).text).toBe('only');
});

test('throws when queue empties and not sticky', async () => {
  const llm = new ScriptedMock(['only'], false);
  await llm.complete([]);
  await expect(llm.complete([])).rejects.toThrow();
});
