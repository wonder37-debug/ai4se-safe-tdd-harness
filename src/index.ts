// AI4SE-Safe-TDD-Harness 入口：保留 greet 桩（smoke test 契约），新增真实 --web 命令行入口。
export function greet(name: string): string {
  return `hello, ${name}`;
}

import * as path from 'path';
import * as os from 'os';
import { existsSync, promises as fs } from 'fs';
import { ToolRegistry } from './tools/tool';
import { fileTools } from './tools/fileTools';
import { shellTools } from './tools/shellTools';
import { Guardrail } from './guardrail/guardrail';
import { FeedbackClassifier } from './feedback/feedbackClassifier';
import { JestParser } from './feedback/jestParser';
import { MemoryStore } from './memory/memoryStore';
import { AgentLoop } from './loop/agentLoop';
import { OpenAICompatProvider } from './llm/openaiCompat';
import { ScriptedMock } from './llm/scriptedMock';
import { offlineDemoActions } from './llm/offlineDemo';
import type { LLMProvider } from './llm/provider';
import { EncryptedFileStore } from './creds/credentialStore';
import { ConfigStore, JsonConfigStore } from './creds/configStore';
import { EventStore } from './loop/eventSink';
import { HttpApprovalGateway } from './approval/httpApprovalGateway';
import { startWebServer } from './web/webServer';

export interface LoopFactoryOpts {
  creds: EncryptedFileStore;
  config: ConfigStore;
  approval: HttpApprovalGateway;
  eventStore: EventStore;
}

// 组装 system prompt：任务 + 平台信息 + 动作协议。
// 平台信息让 LLM 用系统原生命令（Windows 上 del/Remove-Item 而非 rm），
// 避免 'rm' 不是内部命令 之类的失败往返。纯函数，离线可单测。
export function buildSystemPrompt(task: string, platform: string = process.platform): string {
  const osName = platform === 'win32' ? 'Windows'
    : platform === 'darwin' ? 'macOS'
    : 'Linux/Unix';
  const shellHint = platform === 'win32'
    ? 'You are on Windows. Use Windows-native shell commands: `del` (not `rm`) to delete files, `dir` (not `ls`) to list, `type` (not `cat`) to read a file, `copy`/`move` to copy/move. PowerShell cmdlets (`Remove-Item`, `Get-ChildItem`) also work.'
    : 'You are on a Unix-like system. Use `rm`/`ls`/`cat`.';
  return `You are a safe coding agent. In each turn, you MUST output exactly one fenced code block in this format:

\`\`\`action
{"tool": "tool_name", "args": {...}}
\`\`\`

Available tools:
- write_file: {"path": "string", "content": "string"}
- read_file: {"path": "string"}
- run_shell: {"command": "string"}
- run_tests: {"command": "string"}
- finish: {}

Example:
\`\`\`action
{"tool": "write_file", "args": {"path": "add.js", "content": "module.exports=(a,b)=>a+b;"}}
\`\`\`

Platform: ${platform} (${osName}). ${shellHint}

Complete this task:
${task}`;
}

// 在线模式判据：主密码 + 端点(config 优先、env 回退) + 可解密 key 三者齐备才算「检测到有效 Key」。
// 任一缺失即降级离线 ScriptedMock，使评审无 Key 也能在浏览器完整观看 TDD 自修正演示。
async function tryOnlineKey(opts: LoopFactoryOpts): Promise<{ baseUrl: string; key: string; model?: string } | null> {
  const master = process.env.MASTER_PASSWORD;
  if (!master) return null;
  const cfg = await opts.config.get();
  const baseUrl = cfg.baseUrl || process.env.API_BASE_URL;
  if (!baseUrl) return null;
  try {
    const key = (await opts.creds.resolve(master)).key;
    return { baseUrl, key, model: cfg.model || process.env.MODEL };
  } catch {
    return null;
  }
}

// 浏览器侧 cwd 可能未填或不存在；此时落到一个可写临时目录，保证演示零配置即可跑。
async function resolveCwd(cwd: string): Promise<string> {
  if (cwd && existsSync(cwd)) return cwd;
  const dir = path.join(os.tmpdir(), 'ai4se-demo');
  await fs.mkdir(dir, { recursive: true });
  return dir;
}

// ponytail: loopFactory 在线→OpenAICompatProvider（observation 已在 complete 内 adaptMessages 适配为 user），
// 离线→ScriptedMock 跑自修正演示。两条路径都不再静默 provider_error，按钮「启动循环」必产出可见事件流。
export function makeLoopFactory(opts: LoopFactoryOpts) {
  return async (task: string, cwd: string): Promise<{ haltReason: string; iterations: number }> => {
    const workCwd = await resolveCwd(cwd);
    let llm: LLMProvider;
    const online = await tryOnlineKey(opts);
    if (online) {
      llm = new OpenAICompatProvider({ baseUrl: online.baseUrl, apiKey: online.key, model: online.model });
    } else {
      // 离线降级：无有效 Key 时走确定性自修正脚本，评审可在浏览器观看到完整纠错闭环
      llm = new ScriptedMock(offlineDemoActions());
    }
    const loop = new AgentLoop({
      llm,
      registry: new ToolRegistry([...fileTools, ...shellTools]),
      guardrail: Guardrail,
      approval: opts.approval,
      feedback: new FeedbackClassifier(new JestParser()),
      memory: new MemoryStore(path.join(workCwd, '.ai4se-memory')),
      cwd: workCwd,
      maxIter: 20,
      systemPrompt: buildSystemPrompt(task, process.platform),
      sink: opts.eventStore,
    });
    return loop.run();
  };
}

async function main() {
  const args = process.argv.slice(2);
  if (!args.includes('--web')) {
    console.log('usage: node dist/index.js --web   (control panel on $PORT, default 8080)');
    return;
  }
  const port = Number(process.env.PORT ?? 8080);
  const home = os.homedir();
  const creds = new EncryptedFileStore(path.join(home, '.ai4se', 'creds.enc'));
  const config = new JsonConfigStore(path.join(home, '.ai4se', 'config.json'));
  const approval = new HttpApprovalGateway();
  const eventStore = new EventStore();
  const loopFactory = makeLoopFactory({ creds, config, approval, eventStore });
  await startWebServer({ port, eventStore, approval, creds, config, loopFactory });
  console.log(`harness web panel on :${port}`);
}

if (require.main === module) {
  main().catch((e) => { console.error(e); process.exit(1); });
}
