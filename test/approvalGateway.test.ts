import { MockApprovalGateway } from '../src/approval/approvalGateway';

test('returns queued decisions in order', async () => {
  const g = new MockApprovalGateway([
    { decision: 'deny', reason: 'too dangerous' },
    { decision: 'approve', reason: 'ok' },
  ]);
  const a = (cmd: string) => ({ tool: 'run_shell' as const, args: { command: cmd } });
  expect((await g.request(a('rm -rf /'), ['recursive-delete'])).decision).toBe('deny');
  expect((await g.request(a('rm -rf /'), ['recursive-delete'])).decision).toBe('approve');
});
