import { AgentLoop } from '../src/loop/agentLoop';
import { ScriptedMock } from '../src/llm/scriptedMock';
import { ToolRegistry } from '../src/tools/tool';
import { fileTools } from '../src/tools/fileTools';
import { shellTools } from '../src/tools/shellTools';
import { Guardrail } from '../src/guardrail/guardrail';
import { MockApprovalGateway, ApprovalGateway } from '../src/approval/approvalGateway';
import { Action, ApprovalDecision } from '../src/types';
import { FeedbackClassifier } from '../src/feedback/feedbackClassifier';
import { JestParser } from '../src/feedback/jestParser';
import { MemoryStore } from '../src/memory/memoryStore';
import { EventStore } from '../src/loop/eventSink';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';

function action(tool: string, args: any): string {
  return '```action\n' + JSON.stringify({ tool, args }) + '\n```';
}

async function tmp(): Promise<string> { return fs.mkdtemp(path.join(os.tmpdir(), 'loop-')); }

// runner is a .js file invoked by `node run-tests.js` — no Unix `sh` dependency,
// no cmd-vs-bash quoting. `node` is the only host requirement (guaranteed: this is a Node project).
// Resolves cross-platform on Windows PowerShell, Git Bash, and Linux CI.
const RUNNER_PASS_WHEN_CORRECT = `const a = require('./add.js');
if (a(2, 3) !== 5) {
  console.error('FAIL  ./add.test.js');
  console.error('  expect(received).toBe(expected)');
  console.error('  Expected: 5');
  console.error('  at add.test.js:4:17');
  process.exit(1);
}
process.exit(0);
`;

const RUNNER_ALWAYS_FAIL = `console.error('FAIL  ./add.test.js');
console.error('  expect(received).toBe(expected)');
console.error('  at add.test.js:4:17');
process.exit(1);
`;

test('full green loop: write buggy -> test fails -> feedback -> fix -> green -> finish', async () => {
  const cwd = await tmp();
  await fs.writeFile(path.join(cwd, 'run-tests.js'), RUNNER_PASS_WHEN_CORRECT);
  const reg = new ToolRegistry([...fileTools, ...shellTools]);
  const llm = new ScriptedMock([
    action('write_file', { path: 'add.js', content: 'module.exports=(a,b)=>a-b;\n' }), // 有 bug
    action('run_tests', { command: 'node run-tests.js' }),
    action('write_file', { path: 'add.js', content: 'module.exports=(a,b)=>a+b;\n' }), // 修复
    action('run_tests', { command: 'node run-tests.js' }),
    action('finish', {}),
  ]);
  const loop = new AgentLoop({
    llm, registry: reg, guardrail: Guardrail, approval: new MockApprovalGateway([]),
    feedback: new FeedbackClassifier(new JestParser()),
    memory: new MemoryStore(path.join(cwd, 'memory')),
    cwd, maxIter: 20, systemPrompt: 'you are a coding agent',
  });
  const res = await loop.run();
  expect(res.haltReason).toBe('finish');
  expect(res.iterations).toBe(5);
  // add.js 现已正确
  const add = require(path.join(cwd, 'add.js'));
  expect(add(2, 3)).toBe(5);
});

test('guardrail halts-to-approval then deny re-injects as observation', async () => {
  const cwd = await tmp();
  const reg = new ToolRegistry([...fileTools, ...shellTools]);
  const llm = new ScriptedMock([
    action('run_shell', { command: 'rm -rf /' }),
    action('finish', {}),
  ]);
  const approval = new MockApprovalGateway([{ decision: 'deny', reason: 'blocked' }]);
  const loop = new AgentLoop({
    llm, registry: reg, guardrail: Guardrail, approval,
    feedback: new FeedbackClassifier(new JestParser()),
    memory: new MemoryStore(path.join(cwd, 'memory')),
    cwd, maxIter: 20, systemPrompt: 'x',
  });
  const res = await loop.run();
  expect(res.haltReason).toBe('finish');
});

test('stuck halt: same assertion point failing twice -> HALTED(stuck)', async () => {
  const cwd = await tmp();
  await fs.writeFile(path.join(cwd, 'run-tests.js'), RUNNER_ALWAYS_FAIL);
  const reg = new ToolRegistry([...fileTools, ...shellTools]);
  const llm = new ScriptedMock([
    action('run_tests', { command: 'node run-tests.js' }),
    action('run_tests', { command: 'node run-tests.js' }),
    action('run_tests', { command: 'node run-tests.js' }),
  ], true);
  const loop = new AgentLoop({
    llm, registry: reg, guardrail: Guardrail, approval: new MockApprovalGateway([]),
    feedback: new FeedbackClassifier(new JestParser()),
    memory: new MemoryStore(path.join(cwd, 'memory')),
    cwd, maxIter: 20, systemPrompt: 'x',
  });
  const res = await loop.run();
  expect(res.haltReason).toBe('stuck');
});

// ───────── Task 4：审批前先 emit approval_request（SPEC §6） ────────

test('high action emits approval_request before approval_decision', async () => {
  const cwd = await tmp();
  const reg = new ToolRegistry([...fileTools, ...shellTools]);
  const llm = new ScriptedMock([
    action('run_shell', { command: 'rm -rf /' }),
    action('finish', {}),
  ]);
  const store = new EventStore();
  const loop = new AgentLoop({
    llm, registry: reg, guardrail: Guardrail, approval: new MockApprovalGateway([{ decision: 'deny', reason: 'no' }]),
    feedback: new FeedbackClassifier(new JestParser()),
    memory: new MemoryStore(path.join(cwd, 'memory')),
    cwd, maxIter: 20, systemPrompt: 'x', sink: store,
  });
  await loop.run();
  const evs = store.all();
  const reqIdx = evs.findIndex(e => e.type === 'approval_request');
  const decIdx = evs.findIndex(e => e.type === 'approval_decision');
  expect(reqIdx).toBeGreaterThanOrEqual(0);          // 审批请求事件已发出
  expect(decIdx).toBeGreaterThan(reqIdx);            // 裁决事件紧随其后
  expect(evs[reqIdx].payload.action.args.command).toBe('rm -rf /');
  expect(evs[reqIdx].payload.reasons.join(' ')).toMatch(/recursive-delete/);
});

// ───────── 状态感知护栏：拒绝后分拆命令绕过的闭环验证 ────────

// 记录每次审批请求的 action 与 reasons，便于断言动态升级是否触发
class RecordingApprovalGateway implements ApprovalGateway {
  requests: { action: Action; reasons: string[] }[] = [];
  constructor(private inner: MockApprovalGateway) {}
  async request(action: Action, reasons: string[]): Promise<ApprovalDecision> {
    this.requests.push({ action, reasons });
    return this.inner.request(action, reasons);
  }
}

test('state-aware guardrail: after deny, plain rm is escalated to high and intercepted', async () => {
  const cwd = await tmp();
  const reg = new ToolRegistry([...fileTools, ...shellTools]);
  const llm = new ScriptedMock([
    action('run_shell', { command: 'rm -rf /' }),    // 高危 → 用户拒绝
    action('run_shell', { command: 'rm file.txt' }), // 分拆绕过尝试 → 动态升级 high → 再拦截
    action('finish', {}),
  ]);
  const approval = new RecordingApprovalGateway(new MockApprovalGateway([
    { decision: 'deny', reason: 'blocked' },
    { decision: 'deny', reason: 'blocked again' },
  ]));
  const loop = new AgentLoop({
    llm, registry: reg, guardrail: Guardrail, approval,
    feedback: new FeedbackClassifier(new JestParser()),
    memory: new MemoryStore(path.join(cwd, 'memory')),
    cwd, maxIter: 20, systemPrompt: 'x',
  });
  const res = await loop.run();
  expect(res.haltReason).toBe('finish');
  // rm file.txt 平时仅 low（不进审批）；拒绝后被升级 high，因此共 2 次审批请求
  expect(approval.requests).toHaveLength(2);
  expect(approval.requests[1].action.args.command).toBe('rm file.txt');
  expect(approval.requests[1].reasons.join(' ')).toMatch(/deny-escalation/);
});

test('state-aware guardrail: state clears after a normal executed action (no approval fatigue)', async () => {
  const cwd = await tmp();
  const reg = new ToolRegistry([...fileTools, ...shellTools]);
  const llm = new ScriptedMock([
    action('run_shell', { command: 'rm -rf /' }),     // 高危 → 拒绝（lastDenied=true）
    action('list_dir', { path: '.' }),                // 正常动作执行 → 清除拒绝状态
    action('run_shell', { command: 'rm ghost.txt' }), // 恢复 low，不再触发审批
    action('finish', {}),
  ]);
  const approval = new RecordingApprovalGateway(new MockApprovalGateway([
    { decision: 'deny', reason: 'blocked' },
  ]));
  const loop = new AgentLoop({
    llm, registry: reg, guardrail: Guardrail, approval,
    feedback: new FeedbackClassifier(new JestParser()),
    memory: new MemoryStore(path.join(cwd, 'memory')),
    cwd, maxIter: 20, systemPrompt: 'x',
  });
  const res = await loop.run();
  expect(res.haltReason).toBe('finish');
  // 仅首次 rm -rf / 触发审批；中隔正常动作后 rm ghost.txt 保持 low 无打扰
  expect(approval.requests).toHaveLength(1);
  expect(approval.requests[0].action.args.command).toBe('rm -rf /');
});

// ───────── Task 12：多 action 丢弃补告警 ─────────

test('同一回复含多个 action 块：仅执行首个，messages 补 warn observation', async () => {
  const cwd = await tmp();
  const reg = new ToolRegistry([...fileTools, ...shellTools]);
  // 单条回复里塞两个 action 块：只有首个 write_file 应被执行
  const multi = action('write_file', { path: 'a.txt', content: '1' }) + '\n' +
                action('write_file', { path: 'b.txt', content: '2' });
  const llm = new ScriptedMock([multi, action('finish', {})]);
  const loop = new AgentLoop({
    llm, registry: reg, guardrail: Guardrail, approval: new MockApprovalGateway([]),
    feedback: new FeedbackClassifier(new JestParser()),
    memory: new MemoryStore(path.join(cwd, 'memory')),
    cwd, maxIter: 20, systemPrompt: 'x',
  });
  const res = await loop.run();
  expect(res.haltReason).toBe('finish');
  // 首个执行、其余丢弃
  await expect(fs.access(path.join(cwd, 'a.txt'))).resolves.toBeUndefined();
  await expect(fs.access(path.join(cwd, 'b.txt'))).rejects.toThrow();
  // 丢弃不再静默：messages 中出现告警 observation（忽略其余 1 个）
  const msgs: { role: string; content: string }[] = (loop as any).messages;
  expect(msgs.some(m => m.role === 'user' && /仅执行首个 action.*忽略其余 1 个/.test(m.content))).toBe(true);
});

// ───────── Thought 事件：剥除 action 围栏后的自然语言思考存入 EventStore ────────
// 大模型回复 = 自然语言解释 + ```action 围栏。AgentLoop 须把围栏剥除后的干净文本
// 作为 thought 事件发出（供 web 前端轮询渲染思考气泡），且先于 action 事件。

test('LLM 回复含自然语言 + action 围栏 → 发出 thought 事件（剥除围栏的干净文本），先于 action', async () => {
  const cwd = await tmp();
  const reg = new ToolRegistry([...fileTools, ...shellTools]);
  const resp = '我先写一个 add 实现，但故意留个 bug 用来演示自修正。\n```action\n' +
    JSON.stringify({ tool: 'write_file', args: { path: 'add.js', content: 'module.exports=(a,b)=>a-b;\n' } }) + '\n```';
  const llm = new ScriptedMock([resp, action('finish', {})]);
  const store = new EventStore();
  const loop = new AgentLoop({
    llm, registry: reg, guardrail: Guardrail, approval: new MockApprovalGateway([]),
    feedback: new FeedbackClassifier(new JestParser()),
    memory: new MemoryStore(path.join(cwd, 'memory')),
    cwd, maxIter: 20, systemPrompt: 'x', sink: store,
  });
  await loop.run();
  const evs = store.all();
  const thoughtIdx = evs.findIndex(e => e.type === 'thought');
  const actionIdx = evs.findIndex(e => e.type === 'action');
  expect(thoughtIdx).toBeGreaterThanOrEqual(0);
  expect(actionIdx).toBeGreaterThan(thoughtIdx);              // thought 先于 action
  const thought = evs[thoughtIdx].payload as { text: string };
  expect(thought.text).toContain('故意留个 bug');
  expect(thought.text).not.toContain('```action');            // 围栏已剥除
  expect(thought.text).not.toContain('"tool"');                // 不泄漏 action JSON
});

test('LLM 回复纯 action 围栏（无自然语言）→ 不发空 thought 事件', async () => {
  const cwd = await tmp();
  const reg = new ToolRegistry([...fileTools, ...shellTools]);
  const llm = new ScriptedMock([action('finish', {})]);
  const store = new EventStore();
  const loop = new AgentLoop({
    llm, registry: reg, guardrail: Guardrail, approval: new MockApprovalGateway([]),
    feedback: new FeedbackClassifier(new JestParser()),
    memory: new MemoryStore(path.join(cwd, 'memory')),
    cwd, maxIter: 20, systemPrompt: 'x', sink: store,
  });
  await loop.run();
  expect(store.all().filter(e => e.type === 'thought')).toHaveLength(0);
});

// ───────── 漏洞 4：用户终止意图硬性约束 ────────
// 用户在审批拒绝对话中输入"终止/停止/不要执行了/abort/cancel/stop"等显式终止意图时，
// 循环必须立即终止（user_abort），严禁 LLM 寻找替代工具重试。

function abortLoop(reason: string) {
  return async () => {
    const cwd = await tmp();
    const reg = new ToolRegistry([...fileTools, ...shellTools]);
    const llm = new ScriptedMock([
      action('run_shell', { command: 'rm -rf /' }),  // 高危 → 用户拒绝
      action('finish', {}),                          // 不应到达
    ]);
    const loop = new AgentLoop({
      llm, registry: reg, guardrail: Guardrail, approval: new MockApprovalGateway([{ decision: 'deny', reason }]),
      feedback: new FeedbackClassifier(new JestParser()),
      memory: new MemoryStore(path.join(cwd, 'memory')),
      cwd, maxIter: 20, systemPrompt: 'x',
    });
    const res = await loop.run();
    expect(res.haltReason).toBe('user_abort');
    expect(res.iterations).toBe(1);
  };
}

test('abort intent "终止任务" halts loop immediately', abortLoop('终止任务'));
test('abort intent "停止" halts loop immediately', abortLoop('停止'));
test('abort intent "不要执行了" halts loop immediately', abortLoop('不要执行了'));
test('abort intent "abort" halts loop immediately', abortLoop('please abort'));
test('abort intent "cancel" halts loop immediately', abortLoop('cancel'));
test('abort intent "stop" halts loop immediately', abortLoop('stop'));

test('non-abort deny reason continues loop to finish (no false halt)', async () => {
  const cwd = await tmp();
  const reg = new ToolRegistry([...fileTools, ...shellTools]);
  const llm = new ScriptedMock([
    action('run_shell', { command: 'rm -rf /' }),  // 高危 → 拒绝"blocked"（无终止意图）
    action('finish', {}),                          // 继续到 finish
  ]);
  const loop = new AgentLoop({
    llm, registry: reg, guardrail: Guardrail, approval: new MockApprovalGateway([{ decision: 'deny', reason: 'blocked' }]),
    feedback: new FeedbackClassifier(new JestParser()),
    memory: new MemoryStore(path.join(cwd, 'memory')),
    cwd, maxIter: 20, systemPrompt: 'x',
  });
  const res = await loop.run();
  expect(res.haltReason).toBe('finish');
});

test('user abort emits halt event with reason user_abort', async () => {
  const cwd = await tmp();
  const reg = new ToolRegistry([...fileTools, ...shellTools]);
  const llm = new ScriptedMock([
    action('run_shell', { command: 'rm -rf /' }),
    action('finish', {}),
  ]);
  const store = new EventStore();
  const loop = new AgentLoop({
    llm, registry: reg, guardrail: Guardrail, approval: new MockApprovalGateway([{ decision: 'deny', reason: '终止' }]),
    feedback: new FeedbackClassifier(new JestParser()),
    memory: new MemoryStore(path.join(cwd, 'memory')),
    cwd, maxIter: 20, systemPrompt: 'x', sink: store,
  });
  await loop.run();
  const halt = store.all().find(e => e.type === 'halt');
  expect(halt).toBeDefined();
  expect((halt!.payload as any).reason).toBe('user_abort');
});
