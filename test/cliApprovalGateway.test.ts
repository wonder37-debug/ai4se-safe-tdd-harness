import { CliApprovalGateway } from '../src/approval/cliApprovalGateway';

const sh = (c: string) => ({ tool: 'run_shell' as const, args: { command: c } });

test('y → approve', async () => {
  const g = new CliApprovalGateway(async () => 'y');
  const d = await g.request(sh('rm -rf /'), ['recursive-delete']);
  expect(d.decision).toBe('approve');
});

test('yes → approve（大小写不敏感）', async () => {
  const g = new CliApprovalGateway(async () => 'YES');
  expect((await g.request(sh('x'), [])).decision).toBe('approve');
});

test('n → deny', async () => {
  const g = new CliApprovalGateway(async () => 'n');
  expect((await g.request(sh('x'), [])).decision).toBe('deny');
});

test('no → deny', async () => {
  const g = new CliApprovalGateway(async () => 'no');
  expect((await g.request(sh('x'), [])).decision).toBe('deny');
});

test('任意文本 → deny 且文本作为 reason（反馈重定向）', async () => {
  const g = new CliApprovalGateway(async () => 'please use a safer command like trash instead');
  const d = await g.request(sh('rm -rf /'), ['recursive-delete']);
  expect(d.decision).toBe('deny');
  expect(d.reason).toBe('please use a safer command like trash instead');
});

test('空输入 → deny', async () => {
  const g = new CliApprovalGateway(async () => '');
  expect((await g.request(sh('x'), [])).decision).toBe('deny');
});

test('提示文本含 tool / args / reasons', async () => {
  let captured = '';
  const g = new CliApprovalGateway(async (p) => { captured = p; return 'n'; });
  await g.request({ tool: 'run_shell', args: { command: 'rm -rf /' } }, ['recursive-delete']);
  expect(captured).toContain('run_shell');
  expect(captured).toContain('rm -rf /');
  expect(captured).toContain('recursive-delete');
});

test('未注入 ask 时仍可裁决（fallback deny，不崩）', async () => {
  const g = new CliApprovalGateway();
  const d = await g.request(sh('x'), []);
  expect(d.decision).toBe('deny');
});
