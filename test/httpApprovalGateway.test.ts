import { HttpApprovalGateway } from '../src/approval/httpApprovalGateway';

test('request resolves when resolve() is called with matching id', async () => {
  const g = new HttpApprovalGateway();
  const a = { tool: 'run_shell' as const, args: { command: 'rm -rf /' } };
  const p = g.request(a, ['recursive-delete']);
  const pending = g.pending();
  expect(pending).toHaveLength(1);
  g.resolve(pending[0].id, { decision: 'approve', reason: 'ok' });
  expect((await p).decision).toBe('approve');
});

test('unresolved request pending until resolved or denied', async () => {
  const g = new HttpApprovalGateway();
  const p = g.request({ tool: 'run_shell', args: { command: 'x' } }, []);
  expect(g.pending()).toHaveLength(1);
  g.resolve(g.pending()[0].id, { decision: 'deny', reason: 'no' });
  expect((await p).decision).toBe('deny');
});
