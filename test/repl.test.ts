import { stripActionFences } from '../src/cli/repl';

test('strips a closed action fence, keeps natural language', () => {
  const text = 'thinking...\n```action\n{"tool":"write_file","args":{}}\n```\nafter';
  expect(stripActionFences(text)).toBe('thinking...\n\nafter');
});

test('strips an UNCLOSED action fence (no trailing backticks)', () => {
  const text = 'thinking...\n```action\n{"tool":"write_file","args":{}}';
  expect(stripActionFences(text)).toBe('thinking...');
});

test('returns original text when no fence present', () => {
  expect(stripActionFences('just talking')).toBe('just talking');
});
