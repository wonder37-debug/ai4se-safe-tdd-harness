// AI4SE-Safe-TDD-Harness 入口。
// 保留 greet 桩（smoke test 契约）+ buildSystemPrompt / makeLoopFactory（被 webEntry / systemPrompt 测试引用）。
// CLI 三模式：--web | --task "<desc>" [--cwd] | --interactive/-i（默认）。

import * as path from 'path';
import * as os from 'os';
import * as readline from 'readline';
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
import { resolveCredentials } from './creds/credResolver';
import { EventStore } from './loop/eventSink';
import { HttpApprovalGateway } from './approval/httpApprovalGateway';
import { CliApprovalGateway } from './approval/cliApprovalGateway';
import type { ApprovalGateway } from './approval/approvalGateway';
import { startWebServer } from './web/webServer';
import { parseArgs } from './cli/args';
import { loadEnvFile } from './cli/envLoader';
import { rlAsk, runRepl } from './cli/repl';

export function greet(name: string): string {
  return `hello, ${name}`;
}

export interface LoopFactoryOpts {
  creds: EncryptedFileStore;
  config: ConfigStore;
  // 宽化为 ApprovalGateway 接口：web 传 HttpApprovalGateway，CLI 传 CliApprovalGateway。
  approval: ApprovalGateway;
  eventStore: EventStore;
  /** CLI 注入 .env 兜底；web 不传 → 不读 .env（保持 web 行为不变）。 */
  envFile?: Record<string, string>;
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

// 浏览器侧 cwd 可能未填或不存在；此时落到一个可写临时目录，保证演示零配置即可跑。
async function resolveCwd(cwd: string): Promise<string> {
  if (cwd && existsSync(cwd)) return cwd;
  const dir = path.join(os.tmpdir(), 'ai4se-demo');
  await fs.mkdir(dir, { recursive: true });
  return dir;
}

// makeLoopFactory：凭据经 resolveCredentials 决议——
//   creds.enc + MASTER_PASSWORD（密文主路径）→ OpenAICompatProvider
//   .env / process.env API_KEY（明文兜底，带告警）→ OpenAICompatProvider
//   全无 → 离线 ScriptedMock 自修正演示
// 离线路径无网络；在线路径用全局 fetch（生产）或注入 fake fetch（测试）。
export function makeLoopFactory(opts: LoopFactoryOpts) {
  return async (task: string, cwd: string): Promise<{ haltReason: string; iterations: number }> => {
    const workCwd = await resolveCwd(cwd);
    const resolved = await resolveCredentials({
      creds: opts.creds,
      config: opts.config,
      envFile: opts.envFile,
      masterPassword: process.env.MASTER_PASSWORD,
      env: process.env as Record<string, string | undefined>,
    });
    let llm: LLMProvider;
    if (resolved) {
      llm = new OpenAICompatProvider({ baseUrl: resolved.baseUrl, apiKey: resolved.key, model: resolved.model });
      if (resolved.source !== 'encrypted-file') {
        // ponytail: SPEC §3.9 要求 .env fallback 带告警；明文 key 一律告警
        console.warn(`[security] 使用明文 API_KEY（source=${resolved.source}）；生产请用 creds.enc + MASTER_PASSWORD`);
      }
    } else {
      // 无有效 Key → 离线降级，确定性自修正演示
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

function printUsage(): void {
  console.log(`AI4SE-Safe-TDD-Harness CLI

用法:
  node dist/index.js                                   交互式 REPL（默认）
  node dist/index.js -i | --interactive                交互式 REPL
  node dist/index.js --task "<任务描述>" [--cwd "<路径>"]   单次任务
  node dist/index.js "<任务描述>"                       单次任务（简写）
  node dist/index.js --web                             Web 控制面板（$PORT，默认 8080）
  node dist/index.js -h | --help                       显示本帮助

凭据:
  优先读 ~/.ai4se/creds.enc（需设 MASTER_PASSWORD 环境变量解密）；
  .env 的 API_KEY / API_BASE_URL / MODEL 作明文兜底（带告警）；
  无有效 Key 时自动降级离线 ScriptedMock 自修正演示。

REPL 内:
  输入自然语言任务 → 回车执行；高危动作会在终端悬停，
  [y] 批准 / [n] 拒绝 / 或输入文本反馈以重定向对话；exit 或 quit 退出。`);
}

async function main() {
  const parsed = parseArgs(process.argv.slice(2));
  const home = os.homedir();
  const creds = new EncryptedFileStore(path.join(home, '.ai4se', 'creds.enc'));
  const config = new JsonConfigStore(path.join(home, '.ai4se', 'config.json'));
  const eventStore = new EventStore();

  if (parsed.mode === 'help') {
    printUsage();
    return;
  }

  if (parsed.mode === 'web') {
    const approval = new HttpApprovalGateway();
    const loopFactory = makeLoopFactory({ creds, config, approval, eventStore });
    const port = Number(process.env.PORT ?? 8080);
    await startWebServer({ port, eventStore, approval, creds, config, loopFactory });
    console.log(`harness web panel on :${port}`);
    return;
  }

  // task / interactive → CLI 人工审批网关 + .env 兜底
  const cwd = parsed.cwd && existsSync(parsed.cwd) ? parsed.cwd : process.cwd();
  const approval = new CliApprovalGateway();
  const envFile = await loadEnvFile(path.join(process.cwd(), '.env'));
  const loopFactory = makeLoopFactory({ creds, config, approval, eventStore, envFile });

  if (parsed.mode === 'task') {
    if (!parsed.task) {
      printUsage();
      return;
    }
    // 单次任务也绑定 stdin，使高危动作可在终端悬停审批
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    approval.setAsk(rlAsk(rl));
    try {
      const r = await loopFactory(parsed.task, cwd);
      console.log(`[done] haltReason=${r.haltReason}, iterations=${r.iterations}`);
    } finally {
      rl.close();
    }
    return;
  }

  // interactive（默认）
  await runRepl({ loopFactory, cwd, approval });
}

if (require.main === module) {
  main().catch((e) => { console.error(e); process.exit(1); });
}
