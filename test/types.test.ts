import type { Action, Message, Observation, Feedback, GuardrailVerdict, Approval } from '../src/types';

test('types: Action shape is constructable', () => {
  const a: Action = { tool: 'run_shell', args: { command: 'ls' } };
  const m: Message = { role: 'observation', content: 'ok' };
  const o: Observation = { ok: true, exitCode: 0 };
  const f: Feedback = { errorType: 'assertion', failedTests: ['t'], evidence: 'e', hint: 'h' };
  const g: GuardrailVerdict = { severity: 'none', reasons: [] };
  const ap: Approval = { id: '1', action: a, reasons: [], decision: 'approve', reason: 'ok' };
  expect(a.tool).toBe('run_shell');
  expect(ap.decision).toBe('approve');
  expect(g.severity).toBe('none');
});
