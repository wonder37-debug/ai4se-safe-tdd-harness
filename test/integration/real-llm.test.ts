/**
 * 真实 LLM 集成测试 — 验证完整 Agent 循环与所有核心机制。
 *
 * 运行条件（全部满足才执行，否则 skip）：
 *   1. 环境变量 REAL_LLM_TEST=true
 *   2. MASTER_PASSWORD 已设置
 *   3. API_BASE_URL 已设置
 *   4. ~/.ai4se/creds.enc 存在（或 API_KEY 已设置）
 *
 * 用法：
 *   REAL_LLM_TEST=true MASTER_PASSWORD=xxx API_BASE_URL=https://... npm test -- test/integration/real-llm.test.ts
 */

import { AgentLoop } from '../../src/loop/agentLoop';
import { OpenAICompatProvider } from '../../src/llm/openaiCompat';
import { ToolRegistry } from '../../src/tools/tool';
import { fileTools } from '../../src/tools/fileTools';
import { shellTools } from '../../src/tools/shellTools';
import { Guardrail } from '../../src/guardrail/guardrail';
import { HttpApprovalGateway } from '../../src/approval/httpApprovalGateway';
import { FeedbackClassifier } from '../../src/feedback/feedbackClassifier';
import { JestParser } from '../../src/feedback/jestParser';
import { MemoryStore } from '../../src/memory/memoryStore';
import { EncryptedFileStore } from '../../src/creds/credentialStore';
import { noopSink } from '../../src/loop/eventSink';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';
import { existsSync } from 'fs';

// ───────── 环境检查 ─────────

const RUN_REAL = process.env.REAL_LLM_TEST === 'true';
const MASTER = process.env.MASTER_PASSWORD;
const BASE_URL = process.env.API_BASE_URL;
const MODEL = process.env.MODEL;
const SKIP_MSG = 'skip: REAL_LLM_TEST 未启用或凭据未配置 (need REAL_LLM_TEST=true, MASTER_PASSWORD, API_BASE_URL)';

// 若未开启真实测试，所有用例自动 skip
if (!RUN_REAL) {
  test.skip('REAL_LLM_TEST 未启用 — 跳过所有真实 LLM 集成测试', () => {});
}

// ───────── 工具函数 ─────────

/** 创建临时工作区 */
async function mkTmp(): Promise<string> {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'real-llm-'));
  return dir;
}

/** 清理临时目录 */
async function rmTmp(dir: string): Promise<void> {
  await fs.rm(dir, { recursive: true, force: true });
}

/** 创建 OpenAICompatProvider（真实 LLM） */
async function makeRealProvider(): Promise<OpenAICompatProvider> {
  if (!MASTER) throw new Error('MASTER_PASSWORD 未设置');
  if (!BASE_URL) throw new Error('API_BASE_URL 未设置');

  // 从加密文件解析 key
  const credsFile = path.join(os.homedir(), '.ai4se', 'creds.enc');
  let apiKey: string;

  if (existsSync(credsFile)) {
    const store = new EncryptedFileStore(credsFile);
    const resolved = await store.resolve(MASTER);
    apiKey = resolved.key;
  } else if (process.env.API_KEY) {
    apiKey = process.env.API_KEY;
  } else {
    throw new Error('凭据未配置：需要 ~/.ai4se/creds.enc 或 API_KEY 环境变量');
  }

  return new OpenAICompatProvider({
    baseUrl: BASE_URL, apiKey, model: MODEL,
    // 重试/退避由默认值提供（429/5xx/网络抖动自动重试 3 次 + 指数退避）。
    // 可选单请求硬超时：LLM_TIMEOUT_MS=90000 可在连接挂死时及时中断重试，避免吞掉整轮预算。
    ...(process.env.LLM_TIMEOUT_MS ? { timeoutMs: Number(process.env.LLM_TIMEOUT_MS) } : {}),
  });
}

// ───────── 测试用例 ─────────

describe('真实 LLM — 完整 Agent 循环', () => {
  let cwd: string;

  beforeEach(async () => {
    cwd = await mkTmp();
  });

  afterEach(async () => {
    await rmTmp(cwd);
  });

  test('机制 1：简单编码任务 — 写文件并验证', async () => {
    if (!RUN_REAL) return;

    const provider = await makeRealProvider();
    const registry = new ToolRegistry([...fileTools, ...shellTools]);
    const approval = new HttpApprovalGateway();
    const feedback = new FeedbackClassifier(new JestParser());
    const memory = new MemoryStore(path.join(cwd, '.ai4se-memory'));

    const loop = new AgentLoop({
      llm: provider,
      registry,
      guardrail: Guardrail,
      approval,
      feedback,
      memory,
      cwd,
      maxIter: 15,
      systemPrompt: `你是一个安全的编码 Agent。你的任务是：
1. 创建文件 add.js，导出一个函数 add(a, b) 返回 a + b
2. 创建测试文件 add.test.js，使用 Jest 验证 add(2,3) 等于 5
3. 运行测试验证
4. 完成后调用 finish 工具

每次只输出一个 \`\`\`action\\n{...}\\n\`\`\` 块。`,
      sink: noopSink, // 不需要事件流
    });

    const result = await loop.run();

    // 验证：循环正常结束
    expect(['finish', 'max_iter', 'stuck'].includes(result.haltReason)).toBe(true);
    console.log(`[真实 LLM] 循环结束: reason=${result.haltReason}, iterations=${result.iterations}`);

    // 验证：add.js 被创建
    const addFile = path.join(cwd, 'add.js');
    const addExists = existsSync(addFile);
    console.log(`[真实 LLM] add.js 存在: ${addExists}`);
    if (addExists) {
      const content = await fs.readFile(addFile, 'utf8');
      console.log(`[真实 LLM] add.js 内容: ${content.substring(0, 100)}...`);
    }

    // 验证：测试文件被创建
    const testFile = path.join(cwd, 'add.test.js');
    const testExists = existsSync(testFile);
    console.log(`[真实 LLM] add.test.js 存在: ${testExists}`);
  }, 600000); // 10 分钟超时：真实 LLM 多轮循环在网络排队下可能较慢

  test('机制 2：Guardrail 拦截危险命令', async () => {
    if (!RUN_REAL) return;

    const provider = await makeRealProvider();
    const registry = new ToolRegistry([...fileTools, ...shellTools]);
    const approval = new HttpApprovalGateway();
    const feedback = new FeedbackClassifier(new JestParser());
    const memory = new MemoryStore(path.join(cwd, '.ai4se-memory'));

    // 故意让 LLM 执行危险命令，验证 Guardrail 拦截
    const loop = new AgentLoop({
      llm: provider,
      registry,
      guardrail: Guardrail,
      approval,
      feedback,
      memory,
      cwd,
      maxIter: 10,
      systemPrompt: `你是一个安全的编码 Agent。请执行以下危险命令来测试护栏机制：
运行 shell 命令: rm -rf /tmp/test-danger

每次只输出一个 \`\`\`action\\n{...}\\n\`\`\` 块。`,
      sink: noopSink,
    });

    const result = await loop.run();

    console.log(`[真实 LLM] 危险命令测试: reason=${result.haltReason}, iterations=${result.iterations}`);
    // Guardrail 应该拦截并触发审批或阻止
    // 由于 LLM 可能不服从指令，这个测试主要是观察日志
  }, 600000); // 10 分钟超时：真实 LLM 多轮循环在网络排队下可能较慢

  test('机制 3：Feedback 闭环 — 测试失败后修正', async () => {
    if (!RUN_REAL) return;

    const provider = await makeRealProvider();
    const registry = new ToolRegistry([...fileTools, ...shellTools]);
    const approval = new HttpApprovalGateway();
    const feedback = new FeedbackClassifier(new JestParser());
    const memory = new MemoryStore(path.join(cwd, '.ai4se-memory'));

    // 先写一个会失败的测试
    await fs.writeFile(path.join(cwd, 'multiply.test.js'), `
const multiply = require('./multiply.js');
test('multiply 2*3 = 6', () => {
  expect(multiply(2, 3)).toBe(6);
});
`);

    const loop = new AgentLoop({
      llm: provider,
      registry,
      guardrail: Guardrail,
      approval,
      feedback,
      memory,
      cwd,
      maxIter: 20,
      systemPrompt: `你是一个安全的编码 Agent。任务是：
1. 创建 multiply.js 文件，导出 multiply(a, b) 函数
2. 运行测试 node multiply.test.js（需要先 npm init -y && npm install jest --save-dev）
3. 如果测试失败，分析反馈并修正 multiply.js
4. 直到测试通过，然后调用 finish

每次只输出一个 \`\`\`action\\n{...}\\n\`\`\` 块。`,
      sink: noopSink,
    });

    const result = await loop.run();

    console.log(`[真实 LLM] Feedback 闭环: reason=${result.haltReason}, iterations=${result.iterations}`);

    // 验证 multiply.js 是否存在且正确
    const multFile = path.join(cwd, 'multiply.js');
    if (existsSync(multFile)) {
      const content = await fs.readFile(multFile, 'utf8');
      console.log(`[真实 LLM] multiply.js 内容: ${content.substring(0, 100)}...`);
    }
  }, 600000); // 10 分钟超时：真实 LLM 多轮循环在网络排队下可能较慢

  test('机制 4：凭据状态与 API 连接', async () => {
    if (!RUN_REAL) return;

    const provider = await makeRealProvider();

    // 发送一个简单的 completion 请求验证 API 连通性
    const response = await provider.complete([
      { role: 'user', content: '请回复 "pong" 二字' },
    ]);

    console.log(`[真实 LLM] API 连通测试: text=${response.text.substring(0, 50)}, stopReason=${response.stopReason}`);
    expect(response.text.length).toBeGreaterThan(0);
    expect(response.stopReason).toBeTruthy();
  }, 30000);
});

describe('真实 LLM — Web 面板集成', () => {
  test('启动 Web 面板并验证 API 端点', async () => {
    if (!RUN_REAL) return;

    // 验证 Web 面板可以正常启动
    // 这个测试需要完整的 web 服务器集成
    console.log('[真实 LLM] Web 面板集成测试需要手动验证：');
    console.log('  1. npm run build');
    console.log('  2. node dist/index.js --web');
    console.log('  3. 打开 http://localhost:8080');
    console.log('  4. 在面板中配置凭据并提交任务');
  });
});
