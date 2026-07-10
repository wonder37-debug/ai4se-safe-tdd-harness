import { Guardrail } from '../src/guardrail/guardrail';
import { MockApprovalGateway } from '../src/approval/approvalGateway';
import { FeedbackClassifier } from '../src/feedback/feedbackClassifier';
import { JestParser } from '../src/feedback/jestParser';
import { AgentLoop } from '../src/loop/agentLoop';
import { ScriptedMock } from '../src/llm/scriptedMock';
import { ToolRegistry } from '../src/tools/tool';
import { fileTools } from '../src/tools/fileTools';
import { shellTools } from '../src/tools/shellTools';
import { MemoryStore } from '../src/memory/memoryStore';
import * as fs from 'fs/promises'; import * as os from 'os'; import * as path from 'path';

const sh = (c:string) => ({ tool:'run_shell' as const, args:{command:c} });
const act = (t:string,a={}) => '```action\n'+JSON.stringify({tool:t,args:a})+'\n```';

describe('§A.6 mechanism demo', () => {
  test('① guardrail blocks rm -rf / and HITL deny re-injects', async () => {
    expect(Guardrail.assess(sh('rm -rf /')).severity).toBe('high');
    const g = new MockApprovalGateway([{ decision:'deny', reason:'demo deny' }]);
    const cwd = await fs.mkdtemp(path.join(os.tmpdir(),'d1-'));
    const reg = new ToolRegistry([...fileTools,...shellTools]);
    const llm = new ScriptedMock([act('run_shell',{command:'rm -rf /'}), act('finish',{})]);
    const loop = new AgentLoop({ llm, registry:reg, guardrail:Guardrail, approval:g,
      feedback:new FeedbackClassifier(new JestParser()), memory:new MemoryStore(path.join(cwd,'m')),
      cwd, maxIter:20, systemPrompt:'demo' });
    const r = await loop.run();
    expect(r.haltReason).toBe('finish');
  });

  test('② injected Jest failure feeds back and agent self-corrects to green', async () => {
    const cwd = await fs.mkdtemp(path.join(os.tmpdir(),'d2-'));
    await fs.writeFile(path.join(cwd,'run-tests.sh'),
      `node -e "const a=require('./add.js');if(a(2,3)!==5){console.error('FAIL  ./add.test.js\\\\n  expect(received).toBe(expected)\\\\n  Expected: 5\\\\n  at add.test.js:4:17');process.exit(1)}else process.exit(0)"`);
    const fc = new FeedbackClassifier(new JestParser());
    const fb = fc.parse({ ok:false, exitCode:1, stderr:'FAIL  ./add.test.js\n  expect(received).toBe(expected)\n  Expected: 5\n  at add.test.js:4:17' });
    expect(fb.errorType).toBe('assertion');
    const reg = new ToolRegistry([...fileTools,...shellTools]);
    const llm = new ScriptedMock([
      act('write_file',{path:'add.js',content:'module.exports=(a,b)=>a-b;\n'}),
      act('run_tests',{command:'sh run-tests.sh'}),
      act('write_file',{path:'add.js',content:'module.exports=(a,b)=>a+b;\n'}),
      act('run_tests',{command:'sh run-tests.sh'}),
      act('finish',{}),
    ]);
    const loop = new AgentLoop({ llm, registry:reg, guardrail:Guardrail, approval:new MockApprovalGateway([]),
      feedback:fc, memory:new MemoryStore(path.join(cwd,'m')), cwd, maxIter:20, systemPrompt:'demo' });
    const r = await loop.run();
    expect(r.haltReason).toBe('finish');
    expect(require(path.join(cwd,'add.js'))(2,3)).toBe(5);
  });

  test('③ obfuscation bypass + severity + stuck halt', () => {
    expect(Guardrail.assess(sh('r""m -rf /')).severity).toBe('high');
    expect(Guardrail.assess(sh('rm a.txt')).severity).toBe('low');
    expect(Guardrail.assess(sh('ls')).severity).toBe('none');
  });

  test('③ stuck halt after two identical assertion failures', async () => {
    const cwd = await fs.mkdtemp(path.join(os.tmpdir(),'d3-'));
    await fs.writeFile(path.join(cwd,'run-tests.sh'),
      `node -e "console.error('FAIL  ./add.test.js\\\\n  expect(received).toBe(expected)\\\\n  at add.test.js:4:17');process.exit(1)"`);
    const reg = new ToolRegistry([...fileTools,...shellTools]);
    const llm = new ScriptedMock([act('run_tests',{command:'sh run-tests.sh'})], true);
    const loop = new AgentLoop({ llm, registry:reg, guardrail:Guardrail, approval:new MockApprovalGateway([]),
      feedback:new FeedbackClassifier(new JestParser()), memory:new MemoryStore(path.join(cwd,'m')),
      cwd, maxIter:20, systemPrompt:'demo' });
    const r = await loop.run();
    expect(r.haltReason).toBe('stuck');
  });
});
