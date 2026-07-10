// AI4SE-Safe-TDD-Harness 入口：保留 greet 桩（smoke test 契约），新增真实 --web 命令行入口。
export function greet(name: string): string {
  return `hello, ${name}`;
}

import * as path from 'path';
import * as os from 'os';
import { ToolRegistry } from './tools/tool';
import { fileTools } from './tools/fileTools';
import { shellTools } from './tools/shellTools';
import { Guardrail } from './guardrail/guardrail';
import { FeedbackClassifier } from './feedback/feedbackClassifier';
import { JestParser } from './feedback/jestParser';
import { MemoryStore } from './memory/memoryStore';
import { AgentLoop } from './loop/agentLoop';
import { OpenAICompatProvider } from './llm/openaiCompat';
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

// ponytail: loopFactory 解析主密码 + 加密 key，再装配真实 AgentLoop（OpenAICompatProvider）。
// 请求地址 / 模型名优先取自明文 config 文件（Web 面板可写入），缺省回退环境变量
// （Docker / CI 仍可用 env 注入）。缺凭据的三条短路路径都返回 provider_error，
// 不触网、不崩——使 --web 接线可离线确定性单测。
export function makeLoopFactory(opts: LoopFactoryOpts) {
  return async (task: string, cwd: string): Promise<{ haltReason: string; iterations: number }> => {
    const master = process.env.MASTER_PASSWORD;
    if (!master) return { haltReason: 'provider_error', iterations: 0 };
    const cfg = await opts.config.get();
    const baseUrl = cfg.baseUrl || process.env.API_BASE_URL;
    if (!baseUrl) return { haltReason: 'provider_error', iterations: 0 };
    let apiKey: string;
    try {
      apiKey = (await opts.creds.resolve(master)).key;
    } catch {
      return { haltReason: 'provider_error', iterations: 0 };
    }
    const workCwd = cwd || process.cwd();
    const model = cfg.model || process.env.MODEL;
    const llm = new OpenAICompatProvider({ baseUrl, apiKey, model });
    const loop = new AgentLoop({
      llm,
      registry: new ToolRegistry([...fileTools, ...shellTools]),
      guardrail: Guardrail,
      approval: opts.approval,
      feedback: new FeedbackClassifier(new JestParser()),
      memory: new MemoryStore(path.join(workCwd, '.ai4se-memory')),
      cwd: workCwd,
      maxIter: 20,
      systemPrompt: `You are a safe coding agent. In each turn, you MUST output exactly one fenced code block in this format:

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

Complete this task:
${task}`,
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
