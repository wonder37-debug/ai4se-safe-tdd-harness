import { ActionProtocol } from '../src/protocol/actionProtocol';

test('parses a single fenced action block', () => {
  const text = 'I will write a file.\n```action\n{"tool":"write_file","args":{"path":"a.txt","content":"hi"}}\n```';
  const acts = ActionProtocol.parse(text);
  expect(acts).toHaveLength(1);
  expect(acts[0].tool).toBe('write_file');
  expect(acts[0].args.path).toBe('a.txt');
});

test('returns empty array when no fence present', () => {
  expect(ActionProtocol.parse('just talking')).toEqual([]);
});

test('ignores malformed JSON block (returns empty, does not throw)', () => {
  expect(ActionProtocol.parse('```action\n{not json}\n```')).toEqual([]);
});

test('rejects unknown tool name (runtime guard)', () => {
  expect(ActionProtocol.parse('```action\n{"tool":"frob","args":{}}\n```')).toEqual([]);
});
