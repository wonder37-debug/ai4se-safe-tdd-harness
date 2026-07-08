import { AgentLoop } from '../src/loop/agentLoop';
import { ScriptedMock } from '../src/llm/scriptedMock';
import { ToolRegistry } from '../src/tools/tool';
import { fileTools } from '../src/tools/fileTools';
import { shellTools } from '../src/tools/shellTools';
import { Guardrail } from '../src/guardrail/guardrail';
import { MockApprovalGateway } from '../src/approval/approvalGateway';
import { FeedbackClassifier } from '../src/feedback/feedbackClassifier';
import { JestParser } from '../src/feedback/jestParser';
import { MemoryStore } from '../src/memory/memoryStore';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';

function action(tool: string, args: any): string {
  return '```action\n' + JSON.stringify({ tool, args }) + '\n```';
}

async function tmp(): Promise<string> { return fs.mkdtemp(path.join(os.tmpdir(), 'loop-')); }

// ponytail: runner is a .js file invoked by `node run-tests.js` — no Unix `sh` dependency,
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
