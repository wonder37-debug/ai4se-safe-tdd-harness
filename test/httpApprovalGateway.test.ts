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

// ───────── Task 6：审批超时默认 deny（SPEC §3.5）─────────

test('超时无人裁决→ 自动 deny（approval timeout）并清理 pending', async () => {
  const g = new HttpApprovalGateway(50); // 50ms 短超时
  const p = g.request({ tool: 'run_shell', args: { command: 'rm -rf /' } }, ['recursive-delete']);
  const d = await p;
  expect(d.decision).toBe('deny');
  expect(d.reason).toMatch(/approval timeout/);
  expect(g.pending()).toHaveLength(0);
});

test('超时前正常 resolve 优先，超时后再 resolve 幂等忽略', async () => {
  const g = new HttpApprovalGateway(30);
  // 先正常批准：超时不应覆盖已有裁决
  const p1 = g.request({ tool: 'run_shell', args: { command: 'a' } }, []);
  const id1 = g.pending()[0].id;
  expect(g.resolve(id1, { decision: 'approve', reason: 'ok' })).toBe(true);
  expect((await p1).decision).toBe('approve');
  // 超时后再 resolve：返回 false（pending 已清理），不抛异常
  const p2 = g.request({ tool: 'run_shell', args: { command: 'b' } }, []);
  const id2 = g.pending()[0].id;
  const d2 = await p2; // 等到超时 deny
  expect(d2.decision).toBe('deny');
  expect(g.resolve(id2, { decision: 'approve', reason: 'late' })).toBe(false);
});

test('默认构造（不传 timeoutMs）行为不变：可正常 resolve', async () => {
  const g = new HttpApprovalGateway();
  const p = g.request({ tool: 'run_shell', args: { command: 'x' } }, []);
  g.resolve(g.pending()[0].id, { decision: 'approve', reason: 'ok' });
  expect((await p).decision).toBe('approve');
});
