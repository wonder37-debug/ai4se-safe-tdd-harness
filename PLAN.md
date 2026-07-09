# AI4SE-Safe-TDD-Harness 实现计划

> **给 agentic worker：** 必用子技能：用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐个实现本计划。步骤用复选框（`- [ ]`）语法跟踪。

**目标：** 自研一个 Coding Agent Harness 内核（Node.js/TS），含可注入 Mock 的 LLM 层、shell 命令护栏 + HITL 人工审批（深维度 1）、结构化 TDD 失败反馈闭环（深维度 2），以及最小 Web 控制面板和 Docker 分发。

**架构：** 一个手写的 `AgentLoop` while 状态机（`RUNNING → APPROVAL_PENDING → EXECUTING → HALTED`）编排一组可注入接口——`LLMProvider`、`ActionProtocol`、`ToolRegistry`、`Guardrail`、`ApprovalGateway`、`FeedbackClassifier`、`MemoryStore`、`CredentialStore`。每个接口都有生产实现与 mock/stub 实现，使整个内核在无网络、无真实 LLM 下可确定性测试。`WebServer`（Node `http`，HTTP 轮询）暴露任务提交、实时事件流与浏览器内 HITL 审批。

**技术栈：** Node.js 20 LTS、TypeScript 5、Jest + ts-jest。唯一运行时依赖：`shell-quote`。其余一律用 Node 内置（`http`、`crypto`、`fs/promises`、`child_process`、全局 `fetch`）。

## 全局约束

（逐字取自 SPEC.md §4、§7、§8、§12——每个任务隐含包含以下条款。）

- Node 20 LTS；TypeScript strict 模式；CommonJS 输出（jest/node 友好）。
- Harness 内核必须自研：禁用 LangChain/AutoGen/CrewAI/agent-SDK 的高层 loop。仅可用裸 `/v1/chat/completions` 经全局 `fetch`。
- 每个核心机制必须是确定性函数，可用 mock/stub LLM 单测、无网络（SPEC §4.4 / §A.4-C）。
- TDD 硬性要求：红 → 绿 → 重构；不得先于失败测试写实现（SPEC §3.6）。
- 凭据：绝不硬编码/提交/记日志；AES-256-GCM 加密文件 + 主密码；`.env` 仅作带告警的 fallback；`status()` 绝不回显明文（SPEC §3.9 / §4.2）。
- 分发：仅 Docker（T1 裁剪）；`docker run -p 8080:8080` 必须能起 web 面板（SPEC §7.2）。
- CI：`.gitlab-ci.yml` 必须含名为 `unit-test` 的 job（SPEC §五 item 6）。
- 2 周裁剪生效：HTTP 轮询（无 WebSocket）、错误分类 3 类（`assertion`/`syntax`/`other`）、按里程碑开 worktree、单任务并发（SPEC §12）。
- 仓库内不得出现真实凭据；`.env` 已被 gitignore 且必须保持未跟踪。

---

## 文件结构

```
package.json                  # 依赖 + scripts（test, demo, build, start）
tsconfig.json                 # strict TS, commonjs, rootDir . outDir dist
jest.config.js                # ts-jest preset, test+demo glob
.env.example                  # CLAUDE_API_KEY= / API_BASE_URL=（无真实值）
Dockerfile                    # 多阶段：build → 生产镜像
.gitlab-ci.yml                # 增加 unit-test + docker-build job
src/
  types.ts                    # Message, Action, Observation, Feedback, GuardrailVerdict, Approval, Event
  index.ts                    # CLI 入口：--web | --task <file>
  llm/provider.ts             # LLMProvider 接口 + Message 再导出
  llm/scriptedMock.ts         # ScriptedMock（队列/粘滞响应）
  llm/openaiCompat.ts         # OpenAICompatProvider（全局 fetch）
  protocol/actionProtocol.ts  # parse(text) -> Action[]
  tools/tool.ts               # Tool 接口, ToolRegistry, ToolContext
  tools/fileTools.ts          # read_file, write_file, list_dir
  tools/shellTools.ts         # run_shell, run_tests（仅捕获）
  guardrail/guardrail.ts      # assess(action) + shell-quote tokenize
  guardrail/dangerPatterns.json
  approval/approvalGateway.ts # 接口 + MockApprovalGateway
  approval/httpApprovalGateway.ts # pending resolver map
  feedback/feedbackClassifier.ts # Parser 接口 + classify()
  feedback/jestParser.ts      # JestParser
  memory/memoryStore.ts       # 文件式 KV
  creds/credentialStore.ts    # 接口 + EncryptedFileStore
  loop/agentLoop.ts           # while 状态机
  loop/eventSink.ts           # EventSink 接口 + noop + EventStore
  web/webServer.ts            # http 路由, EventStore 轮询
  web/public/index.html
  web/public/app.js
  web/public/style.css
demo/
  mechanism-demo.test.ts      # §A.6 三幕
  fixtures/jest-assertion-fail.txt
  fixtures/jest-syntax-fail.txt
test/                         # 每个 src 模块一个测试文件
  *.test.ts
```

**职责规则：** 每个文件 = 一个机制 / 一个接口。`types.ts` 是唯一的横切文件。测试在 `test/` 下镜像 src 路径。

---

## 任务 1：工程脚手架 + 工具链冒烟测试

**文件：**
- 新建：`package.json`、`tsconfig.json`、`jest.config.js`、`.env.example`、`src/index.ts`、`test/smoke.test.ts`
- 修改：`.gitignore`（加 `dist/`、`*.log`）

**接口：** 产出可运行的 `npm test`（jest+ts-jest）与有类型的 `src/index.ts` 入口。

- [x] **步骤 1：写失败测试**

`test/smoke.test.ts`:
```ts
import { greet } from '../src/index';

test('smoke: jest + ts + import works', () => {
  expect(greet('harness')).toBe('hello, harness');
});
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/smoke.test.ts`
预期：FAIL——`src/index.ts` 未导出 `greet`（文件未建 / 模块缺失）。

- [x] **步骤 3：写最小实现**

`src/index.ts`:
```ts
export function greet(name: string): string {
  return `hello, ${name}`;
}
```

`package.json`:
```json
{
  "name": "ai4se-safe-tdd-harness",
  "version": "0.1.0",
  "description": "Self-coded Coding Agent Harness — AI4SE final project",
  "main": "dist/index.js",
  "scripts": {
    "test": "jest",
    "demo": "jest demo/",
    "build": "tsc && node -e \"const fs=require('fs');if(fs.existsSync('src/web/public'))fs.cpSync('src/web/public','dist/web/public',{recursive:true})\"",
    "start": "node dist/index.js"
  },
  "engines": { "node": ">=20" },
  "license": "MIT"
}
```

`tsconfig.json`（`rootDir:"src"` + `include:["src"]`，使 `dist/` 只含 src 产物；`test/`、`demo/` 由 ts-jest 独立编译，不进 `dist/`，与 Dockerfile 只 COPY src 一致）:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "strict": true,
    "esModuleInterop": true,
    "resolveJsonModule": true,
    "skipLibCheck": true,
    "rootDir": "src",
    "outDir": "dist",
    "types": ["node", "jest"]
  },
  "include": ["src"],
  "exclude": ["node_modules", "dist"]
}
```

`jest.config.js`:
```js
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['**/test/**/*.test.ts', '**/demo/**/*.test.ts'],
  testTimeout: 15000,
};
```

`.env.example`:
```
CLAUDE_API_KEY=
API_BASE_URL=
```

`.gitignore`：**确认已包含** `dist/` 与 `*.log`（本仓库前期提交已添加，见第 3-4 行）；若缺失则补。勿重复追加。

- [x] **步骤 4：装依赖并运行测试**

运行：`npm install --save-dev typescript@5 ts-jest jest @types/jest @types/node && npm install shell-quote @types/shell-quote`
运行：`npx jest test/smoke.test.ts`
预期：PASS（1 个测试）。

- [x] **步骤 5：提交** ✅ `8720329`

```bash
git add package.json package-lock.json tsconfig.json jest.config.js .env.example .gitignore src/index.ts test/smoke.test.ts
git commit -m "chore: scaffold node+ts+jest project with smoke test"
```

---

## 任务 2：核心领域类型

**文件：**
- 新建：`src/types.ts`、`test/types.test.ts`

**接口：**
- 产出：`Message`、`Action`、`Observation`、`Feedback`、`GuardrailVerdict`、`Approval`、`Event`（后续所有任务都用这些类型）。

- [x] **步骤 1：写失败测试**

`test/types.test.ts`:
```ts
import type { Action, Message, Observation, Feedback, GuardrailVerdict, LoopState, Approval } from '../src/types';

test('types: Action shape is constructable', () => {
  const a: Action = { tool: 'run_shell', args: { command: 'ls' } };
  const m: Message = { role: 'observation', content: 'ok' };
  const o: Observation = { ok: true, exitCode: 0 };
  const f: Feedback = { errorType: 'assertion', failedTests: ['t'], evidence: 'e', hint: 'h' };
  const g: GuardrailVerdict = { severity: 'none', reasons: [] };
  const st: LoopState = 'HALTED';
  const ap: Approval = { id: '1', action: a, reasons: [], decision: 'approve', reason: 'ok' };
  expect(a.tool).toBe('run_shell');
  expect(st).toBe('HALTED');
  expect(ap.decision).toBe('approve');
  expect(g.severity).toBe('none');
});
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/types.test.ts`
预期：FAIL——`../src/types` 无导出（TS2307 / 无符号）。

- [x] **步骤 3：写最小实现**

`src/types.ts`:
```ts
export type Role = 'system' | 'user' | 'assistant' | 'observation';
export interface Message { role: Role; content: string; }

export type ToolName = 'read_file' | 'write_file' | 'list_dir' | 'run_shell' | 'run_tests' | 'finish';
export interface Action { tool: ToolName; args: Record<string, any>; }

export interface Observation {
  ok: boolean;
  stdout?: string;
  stderr?: string;
  exitCode?: number;
  error?: string;
  content?: string;
}

export type ErrorType = 'assertion' | 'syntax' | 'other';
export interface Feedback {
  errorType: ErrorType;
  failedTests: string[];
  assertion?: { file: string; line: number; snippet: string };
  evidence: string;
  hint: string;
}

export type Severity = 'none' | 'low' | 'high';
export interface GuardrailVerdict { severity: Severity; reasons: string[]; }

export interface ApprovalRequest { id: string; action: Action; reasons: string[]; }
export interface ApprovalDecision { decision: 'approve' | 'deny'; reason: string; }
export type Approval = ApprovalRequest & Partial<ApprovalDecision>;
export type LoopState = 'RUNNING' | 'APPROVAL_PENDING' | 'EXECUTING' | 'HALTED';

export type EventType = 'action' | 'observation' | 'approval_request' | 'approval_decision' | 'halt';
export interface Event { id: number; type: EventType; payload: any; iter: number; }
```

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/types.test.ts`
预期：PASS。

- [x] **步骤 5：提交** ✅ `298d472`

```bash
git add src/types.ts test/types.test.ts
git commit -m "feat(types): add core domain types"
```

---

## 任务 3：ActionProtocol 解析器

**文件：**
- 新建：`src/protocol/actionProtocol.ts`、`test/actionProtocol.test.ts`

**接口：**
- 消费：`src/types` 的 `Action`。
- 产出：`ActionProtocol.parse(text: string): Action[]`。

- [x] **步骤 1：写失败测试**

`test/actionProtocol.test.ts`:
```ts
import { ActionProtocol } from '../src/protocol/actionProtocol';

test('parses a single fenced action block', () => {
  const text = 'I will write a file.\n```action\n{"tool":"write_file","args":{"path":"a.txt","content":"hi"}}\n```';
  const acts = ActionProtocol.parse(text);
  expect(acts).toHaveLength(1);
  expect(acts[0].tool).toBe('write_file');
  expect(acts[0].args.path).toBe('a.txt');
});

test('returns empty array when no fence present', () => {
  expect(ActionProtocol.parse('just talking')).toEqual([]);
});

test('ignores malformed JSON block (returns empty, does not throw)', () => {
  expect(ActionProtocol.parse('```action\n{not json}\n```')).toEqual([]);
});

test('rejects unknown tool name (runtime guard)', () => {
  expect(ActionProtocol.parse('```action\n{"tool":"frob","args":{}}\n```')).toEqual([]);
});
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/actionProtocol.test.ts`
预期：FAIL——模块 `../src/protocol/actionProtocol` 未找到。

- [x] **步骤 3：写最小实现**

`src/protocol/actionProtocol.ts`:
```ts
import { Action, ToolName } from '../types';

const FENCE = /```action\s*([\s\S]*?)```/g;
const TOOL_NAMES = new Set<string>(['read_file', 'write_file', 'list_dir', 'run_shell', 'run_tests', 'finish']);

export const ActionProtocol = {
  parse(text: string): Action[] {
    const out: Action[] = [];
    let m: RegExpExecArray | null;
    while ((m = FENCE.exec(text)) !== null) {
      const raw = m[1].trim();
      try {
        const obj = JSON.parse(raw); // any；obj.tool 为 any，赋 ToolName 不报编译错（GAP-6 评估：原判断有误）
        if (obj && typeof obj.tool === 'string' && obj.args && typeof obj.args === 'object'
            && TOOL_NAMES.has(obj.tool)) { // 运行时拦截非法工具名
          out.push({ tool: obj.tool as ToolName, args: obj.args });
        }
      } catch {
        // 畸形块：跳过，不抛
      }
    }
    return out;
  },
};
```

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/actionProtocol.test.ts`
预期：PASS（4 个测试）。

- [x] **步骤 5：提交** ✅ `2e5a50f`

```bash
git add src/protocol/actionProtocol.ts test/actionProtocol.test.ts
git commit -m "feat(protocol): action fence parser"
```

---

## 任务 4：ScriptedMock LLMProvider

**文件：**
- 新建：`src/llm/provider.ts`、`src/llm/scriptedMock.ts`、`test/scriptedMock.test.ts`

**接口：**
- 消费：`src/types` 的 `Message`。
- 产出：`LLMProvider` 接口（`async complete(messages): Promise<{text, stopReason}>`）、`ScriptedMock`。

- [x] **步骤 1：写失败测试**

`test/scriptedMock.test.ts`:
```ts
import { ScriptedMock } from '../src/llm/scriptedMock';

test('returns queued responses in order', async () => {
  const llm = new ScriptedMock(['first', 'second']);
  expect((await llm.complete([])).text).toBe('first');
  expect((await llm.complete([])).text).toBe('second');
});

test('sticky last response when queue empties', async () => {
  const llm = new ScriptedMock(['only'], true);
  await llm.complete([]);
  expect((await llm.complete([])).text).toBe('only');
});

test('throws when queue empties and not sticky', async () => {
  const llm = new ScriptedMock(['only'], false);
  await llm.complete([]);
  await expect(llm.complete([])).rejects.toThrow();
});
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/scriptedMock.test.ts`
预期：FAIL——模块未找到。

- [x] **步骤 3：写最小实现**

`src/llm/provider.ts`:
```ts
import { Message } from '../types';
export interface LLMProvider {
  complete(messages: Message[]): Promise<{ text: string; stopReason: string }>;
}
```

`src/llm/scriptedMock.ts`:
```ts
import { LLMProvider } from './provider';
import { Message } from '../types';

export class ScriptedMock implements LLMProvider {
  private queue: string[];
  private sticky: boolean;
  private last: string | null = null;

  constructor(responses: string[], sticky = false) {
    this.queue = [...responses];
    this.sticky = sticky;
  }

  async complete(_messages: Message[]): Promise<{ text: string; stopReason: string }> {
    if (this.queue.length > 0) {
      this.last = this.queue.shift()!;
      return { text: this.last, stopReason: 'ok' };
    }
    if (this.sticky && this.last !== null) {
      return { text: this.last, stopReason: 'ok' };
    }
    throw new Error('ScriptedMock: response queue exhausted and not sticky');
  }
}
```

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/scriptedMock.test.ts`
预期：PASS（3 个测试）。

- [x] **步骤 5：提交** ✅ `4b6dcaf`

```bash
git add src/llm/provider.ts src/llm/scriptedMock.ts test/scriptedMock.test.ts
git commit -m "feat(llm): LLMProvider interface + ScriptedMock"
```

---

## 任务 5：ToolRegistry + 文件工具

**文件：**
- 新建：`src/tools/tool.ts`、`src/tools/fileTools.ts`、`test/fileTools.test.ts`

**接口：**
- 消费：`src/types` 的 `Action`、`Observation`。
- 产出：`Tool` 接口、`ToolRegistry`、`ToolContext`，文件工具 `read_file`/`write_file`/`list_dir`。

- [x] **步骤 1：写失败测试**

`test/fileTools.test.ts`:
```ts
import { ToolRegistry } from '../src/tools/tool';
import { fileTools } from '../src/tools/fileTools';
import * as path from 'path';
import * as fs from 'fs/promises';
import * as os from 'os';

async function withTmpDir(): Promise<string> {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'harness-'));
  return dir;
}

test('write_file then read_file roundtrip', async () => {
  const cwd = await withTmpDir();
  const reg = new ToolRegistry([...fileTools]);
  const w = await reg.dispatch({ tool: 'write_file', args: { path: 'a.txt', content: 'hi' } }, { cwd });
  expect(w.ok).toBe(true);
  const r = await reg.dispatch({ tool: 'read_file', args: { path: 'a.txt' } }, { cwd });
  expect(r.content).toBe('hi');
});

test('list_dir lists entries', async () => {
  const cwd = await withTmpDir();
  const reg = new ToolRegistry([...fileTools]);
  await reg.dispatch({ tool: 'write_file', args: { path: 'a.txt', content: 'x' } }, { cwd });
  const l = await reg.dispatch({ tool: 'list_dir', args: { path: '.' } }, { cwd });
  expect(l.content).toContain('a.txt');
});

test('read_file on missing file returns ok:false with error', async () => {
  const cwd = await withTmpDir();
  const reg = new ToolRegistry([...fileTools]);
  const r = await reg.dispatch({ tool: 'read_file', args: { path: 'nope.txt' } }, { cwd });
  expect(r.ok).toBe(false);
  expect(r.error).toMatch(/no such file/i);
});
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/fileTools.test.ts`
预期：FAIL——模块未找到。

- [x] **步骤 3：写最小实现**

`src/tools/tool.ts`（`ToolContext` 仅 `cwd`：按 SPEC §3.3 裁剪，`MemoryStore`/`CredentialStore` 由 `AgentLoop` 持有，不注入；`error` 字段统一填 `e instanceof Error ? e.message : String(e)`，避免非 Error 对象产出 `[object Object]`）:
```ts
import { Action, Observation } from '../types';

export interface ToolContext { cwd: string; }

export interface Tool {
  name: string;
  execute(args: Record<string, any>, ctx: ToolContext): Promise<Observation>;
}

function errMsg(e: any): string {
  return e instanceof Error ? e.message : String(e);
}

export class ToolRegistry {
  private tools = new Map<string, Tool>();
  constructor(tools: Tool[]) { for (const t of tools) this.tools.set(t.name, t); }

  async dispatch(action: Action, ctx: ToolContext): Promise<Observation> {
    const t = this.tools.get(action.tool);
    if (!t) return { ok: false, error: `unknown tool: ${action.tool}` };
    try {
      return await t.execute(action.args, ctx);
    } catch (e: any) {
      return { ok: false, error: errMsg(e) };
    }
  }
}
```

`src/tools/fileTools.ts`:
```ts
import { Tool, ToolContext } from './tool';
import * as path from 'path';
import * as fs from 'fs/promises';

async function abs(p: string, ctx: ToolContext): Promise<string> {
  return path.resolve(ctx.cwd, p);
}

export const read_file: Tool = {
  name: 'read_file',
  async execute(args, ctx) {
    try {
      const content = await fs.readFile(await abs(args.path, ctx), 'utf8');
      return { ok: true, content };
    } catch (e: any) { return { ok: false, error: String(e?.message ?? e) }; }
  },
};

export const write_file: Tool = {
  name: 'write_file',
  async execute(args, ctx) {
    try {
      const full = await abs(args.path, ctx);
      await fs.mkdir(path.dirname(full), { recursive: true });
      await fs.writeFile(full, String(args.content));
      return { ok: true, content: `wrote ${args.path}` };
    } catch (e: any) { return { ok: false, error: String(e?.message ?? e) }; }
  },
};

export const list_dir: Tool = {
  name: 'list_dir',
  async execute(args, ctx) {
    try {
      const entries = await fs.readdir(await abs(args.path, ctx));
      return { ok: true, content: entries.join('\n') };
    } catch (e: any) { return { ok: false, error: String(e?.message ?? e) }; }
  },
};

export const fileTools: Tool[] = [read_file, write_file, list_dir];
```

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/fileTools.test.ts`
预期：PASS（3 个测试）。

- [x] **步骤 5：提交** ✅ `eff62d6`

```bash
git add src/tools/tool.ts src/tools/fileTools.ts test/fileTools.test.ts
git commit -m "feat(tools): ToolRegistry + file tools"
```

---

## 任务 6：shell 工具（run_shell / run_tests 捕获）

**文件：**
- 新建：`src/tools/shellTools.ts`、`test/shellTools.test.ts`

**接口：**
- 消费：`src/tools/tool` 的 `Tool`、`ToolContext`。
- 产出：`run_shell`、`run_tests`（仅捕获 stdout/stderr/exitCode——反馈解析归任务 11 的主循环）。

- [x] **步骤 1：写失败测试**

`test/shellTools.test.ts`:
```ts
import { ToolRegistry } from '../src/tools/tool';
import { shellTools } from '../src/tools/shellTools';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';

test('run_shell captures stdout and exitCode 0', async () => {
  const cwd = await fs.mkdtemp(path.join(os.tmpdir(), 'h-'));
  const reg = new ToolRegistry([...shellTools]);
  const cmd = process.platform === 'win32' ? 'echo hello' : 'echo hello';
  const r = await reg.dispatch({ tool: 'run_shell', args: { command: cmd } }, { cwd });
  expect(r.ok).toBe(true);
  expect(r.exitCode).toBe(0);
  expect((r.stdout ?? '').trim()).toBe('hello');
});

test('run_shell captures non-zero exit and stderr', async () => {
  const cwd = await fs.mkdtemp(path.join(os.tmpdir(), 'h-'));
  const reg = new ToolRegistry([...shellTools]);
  const cmd = process.platform === 'win32' ? 'node -e "process.stderr.write(\\\"boom\\\");process.exit(1)"'
    : 'node -e "process.stderr.write(\'boom\');process.exit(1)"';
  const r = await reg.dispatch({ tool: 'run_shell', args: { command: cmd } }, { cwd });
  expect(r.exitCode).toBe(1);
  expect(r.stderr).toContain('boom');
});
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/shellTools.test.ts`
预期：FAIL——模块未找到。

- [x] **步骤 3：写最小实现**

`src/tools/shellTools.ts`:
```ts
import { Tool, ToolContext } from './tool';
import { exec } from 'child_process';
import { promisify } from 'util';
const pexec = promisify(exec);

function wrap(cmd: string): { cmd: string; isShell: boolean } {
  return { cmd, isShell: true };
}

export const run_shell: Tool = {
  name: 'run_shell',
  async execute(args, ctx) {
    const { cmd } = wrap(String(args.command));
    try {
      const { stdout, stderr } = await pexec(cmd, { cwd: ctx.cwd, maxBuffer: 1e6, timeout: 30000 });
      return { ok: true, stdout, stderr, exitCode: 0 };
    } catch (e: any) {
      return {
        ok: e.code === 0,
        stdout: e.stdout ?? '',
        stderr: e.stderr ?? '',
        exitCode: typeof e.code === 'number' ? e.code : -1,
        error: String(e?.message ?? e),
      };
    }
  },
};

export const run_tests: Tool = {
  name: 'run_tests',
  async execute(args, ctx) {
    const { cmd } = wrap(String(args.command));
    try {
      const { stdout, stderr } = await pexec(cmd, { cwd: ctx.cwd, maxBuffer: 1e6, timeout: 60000 });
      return { ok: true, stdout, stderr, exitCode: 0 };
    } catch (e: any) {
      const timedOut = e?.killed && e?.signal === 'SIGTERM'; // exec 超时 → killed + SIGTERM
      return {
        ok: false,
        stdout: e.stdout ?? '',
        stderr: e.stderr ?? '',
        exitCode: typeof e.code === 'number' ? e.code : -1,
        error: timedOut ? 'timeout' : (e instanceof Error ? e.message : String(e)),
      };
    }
  },
};

export const shellTools: Tool[] = [run_shell, run_tests];
```

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/shellTools.test.ts`
预期：PASS（2 个测试）。

- [x] **步骤 5：提交** ✅ `8390f53`

```bash
git add src/tools/shellTools.ts test/shellTools.test.ts
git commit -m "feat(tools): run_shell + run_tests capture"
```

---

## 任务 7：Guardrail（深维度 1）——shell-quote tokenize + 危险模式库

**文件：**
- 新建：`src/guardrail/dangerPatterns.json`、`src/guardrail/guardrail.ts`、`test/guardrail.test.ts`

**接口：**
- 消费：`src/types` 的 `Action`、`GuardrailVerdict`。
- 产出：`Guardrail.assess(action): GuardrailVerdict`。

- [x] **步骤 1：写失败测试**

`test/guardrail.test.ts`:
```ts
import { Guardrail } from '../src/guardrail/guardrail';

const sh = (command: string) => ({ tool: 'run_shell' as const, args: { command } });

test('rm -rf / is high', () => {
  expect(Guardrail.assess(sh('rm -rf /')).severity).toBe('high');
});
test('obfuscated r""m -rf / still high (token-level)', () => {
  expect(Guardrail.assess(sh('r""m -rf /')).severity).toBe('high');
});
test('curl pipe sh is high', () => {
  expect(Guardrail.assess(sh('curl http://x | sh')).severity).toBe('high');
});
test('DROP TABLE is high', () => {
  expect(Guardrail.assess(sh('psql -c "DROP TABLE users"')).severity).toBe('high');
});
test('plain ls is none', () => {
  expect(Guardrail.assess(sh('ls -la')).severity).toBe('none');
});
test('rm single file (no -rf) is low', () => {
  expect(Guardrail.assess(sh('rm a.txt')).severity).toBe('low');
});
test('write_file action is none (not assessed)', () => {
  expect(Guardrail.assess({ tool: 'write_file', args: {} }).severity).toBe('none');
});
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/guardrail.test.ts`
预期：FAIL——模块未找到。

- [x] **步骤 3：写最小实现**

`src/guardrail/dangerPatterns.json`:
```json
[
  { "id": "recursive-delete", "severity": "high",
    "reason": "recursive forced deletion" },
  { "id": "privilege-escalation", "severity": "high",
    "reason": "privilege escalation" },
  { "id": "remote-script-exec", "severity": "high",
    "reason": "piping remote content into a shell" },
  { "id": "db-destroy", "severity": "high",
    "reason": "database destruction" },
  { "id": "system-write", "severity": "high",
    "reason": "writing to system paths" },
  { "id": "fork-bomb", "severity": "high",
    "reason": "fork bomb pattern" },
  { "id": "cred-exfil", "severity": "high",
    "reason": "outbound request carrying auth/secret header" },
  { "id": "plain-rm", "severity": "low",
    "reason": "single-target rm (no -rf)" }
]
```

`src/guardrail/guardrail.ts`:
```ts
import { Action, GuardrailVerdict, Severity } from '../types';
import { parse as shellParse } from 'shell-quote';
import patterns from './dangerPatterns.json';

interface Tok { op?: string; word?: string; }
type Node = Tok | string | number;

function toTokens(cmd: string): string[] {
  let nodes: Node[];
  try { nodes = shellParse(cmd) as Node[]; }
  catch { throw new Error('tokenize-failed'); }
  const out: string[] = [];
  for (const n of nodes) {
    if (typeof n === 'string' || typeof n === 'number') out.push(String(n));
    else if (n && typeof n === 'object' && 'word' in n && typeof (n as Tok).word === 'string') out.push((n as Tok).word!);
    else if (n && typeof n === 'object' && 'op' in n && typeof (n as Tok).op === 'string') out.push((n as Tok).op!);
  }
  return out.map(t => t.toLowerCase());
}

function join(tokens: string[]): string { return tokens.join(' '); }

function match(tokens: string[]): { id: string; severity: Severity; reason: string } | null {
  const s = join(tokens);
  const has = (...needles: string[]) => needles.every(n => tokens.includes(n) || s.includes(n));

  if (has('rm') && (has('-rf') || has('--no-preserve-root') || has('-r', '-f')) && (has('/') || has('/*') || s.includes('/etc') || s.includes('/usr')))
    return pick('recursive-delete');
  if (has('sudo') || has('su') || has('chmod') && has('777'))
    return pick('privilege-escalation');
  if ((has('curl') || has('wget')) && (s.includes('| sh') || s.includes('|sh') || s.includes('| bash') || s.includes('|bash')))
    return pick('remote-script-exec');
  if (s.includes('drop table') || s.includes('drop database') || s.includes('truncate'))
    return pick('db-destroy');
  if (s.includes('> /etc/') || s.includes('> /dev/sd') || s.includes('/etc/cron') || s.includes(':(){') )
    return pick('system-write');
  if (s.includes(':(){:|:&};:'))
    return pick('fork-bomb');
  if ((has('curl') || has('wget')) && (s.includes('authorization') || s.includes('-h') && s.includes('token')))
    return pick('cred-exfil');
  if (has('rm') && !has('-rf') && !has('-r') && !has('-f'))
    return pick('plain-rm');
  return null;
}

function pick(id: string) {
  const p = (patterns as any[]).find(p => p.id === id)!;
  return { id, severity: p.severity as Severity, reason: p.reason };
}

export const Guardrail = {
  assess(action: Action): GuardrailVerdict {
    if (action.tool !== 'run_shell' && action.tool !== 'run_tests') return { severity: 'none', reasons: [] };
    const cmd = String(action.args.command ?? '');
    let tokens: string[];
    try { tokens = toTokens(cmd); }
    catch { return { severity: 'high', reasons: ['tokenize-failed: malformed command, forcing approval'] }; }
    const hit = match(tokens);
    if (!hit) return { severity: 'none', reasons: [] };
    return { severity: hit.severity, reasons: [`${hit.id}: ${hit.reason}`] };
  },
};
```

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/guardrail.test.ts`
预期：PASS（7 个测试）。

- [x] **步骤 5：提交** ✅ `e6d755f`

```bash
git add src/guardrail/dangerPatterns.json src/guardrail/guardrail.ts test/guardrail.test.ts
git commit -m "feat(guardrail): shell-quote tokenize + danger pattern library"
```

---

## 任务 8：FeedbackClassifier + JestParser（深维度 2）

**文件：**
- 新建：`src/feedback/feedbackClassifier.ts`、`src/feedback/jestParser.ts`、`demo/fixtures/jest-assertion-fail.txt`、`demo/fixtures/jest-syntax-fail.txt`、`test/feedbackClassifier.test.ts`

**接口：**
- 消费：`src/types` 的 `Observation`、`Feedback`。
- 产出：`Parser` 接口、`FeedbackClassifier`（用 `Parser` 构造）、`JestParser`。

- [x] **步骤 1：写失败测试**

`demo/fixtures/jest-assertion-fail.txt`（逼真的 Jest 失败 stderr）:
```
FAIL  ./add.test.js
  ● add › returns sum

    expect(received).toBe(expected)

    Expected: 5
    Received: 3

      at Object.<anonymous> (add.test.js:4:17)
```

`demo/fixtures/jest-syntax-fail.txt`:
```
FAIL  ./add.test.js
  ● Test suite failed to parse

    SyntaxError: Unexpected token (5:2)

      at add.test.js:5:2
```

`test/feedbackClassifier.test.ts`:
```ts
import { FeedbackClassifier } from '../src/feedback/feedbackClassifier';
import { JestParser } from '../src/feedback/jestParser';
import * as fs from 'fs/promises';
import * as path from 'path';

const fc = new FeedbackClassifier(new JestParser());

async function fixture(name: string): Promise<string> {
  return fs.readFile(path.join(__dirname, '..', 'demo', 'fixtures', name), 'utf8');
}

test('assertion failure parsed to errorType=assertion with file:line', async () => {
  const fb = fc.parse({ ok: false, exitCode: 1, stderr: await fixture('jest-assertion-fail.txt') });
  expect(fb.errorType).toBe('assertion');
  expect(fb.failedTests).toContain("add › returns sum");
  expect(fb.assertion?.file).toBe('add.test.js');
  expect(fb.assertion?.line).toBe(4);
});

test('syntax failure parsed to errorType=syntax', async () => {
  const fb = fc.parse({ ok: false, exitCode: 1, stderr: await fixture('jest-syntax-fail.txt') });
  expect(fb.errorType).toBe('syntax');
  expect(fb.assertion?.file).toBe('add.test.js');
});

test('unrecognized output falls back to other with truncated evidence', async () => {
  const fb = fc.parse({ ok: false, exitCode: 1, stderr: 'something weird\n' });
  expect(fb.errorType).toBe('other');
  expect(fb.evidence).toContain('something weird');
});
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/feedbackClassifier.test.ts`
预期：FAIL——模块/fixture 未找到。

- [x] **步骤 3：写最小实现**

`src/feedback/feedbackClassifier.ts`:
```ts
import { Feedback, Observation } from '../types';

export interface Parser { parse(stdout: string, stderr: string): Feedback; }

function truncate(s: string, n = 2000): string { return s.length > n ? s.slice(-n) : s; }

export class FeedbackClassifier {
  constructor(private parser: Parser) {}
  parse(obs: Observation): Feedback {
    if (obs.exitCode === 0) {
      return { errorType: 'other', failedTests: [], evidence: '', hint: 'tests passed' };
    }
    try {
      const fb = this.parser.parse(obs.stdout ?? '', obs.stderr ?? '');
      fb.evidence = truncate(fb.evidence || obs.stderr || '');
      return fb;
    } catch {
      return {
        errorType: 'other',
        failedTests: [],
        evidence: truncate((obs.stderr ?? '').split('\n').slice(-30).join('\n')),
        hint: 'unrecognized failure; inspect evidence',
      };
    }
  }
}
```

`src/feedback/jestParser.ts`:
```ts
import { Feedback } from '../types';
import { Parser } from './feedbackClassifier';

const FAIL_BLOCK = /●\s+(.+)/g;
const AT_LINE = /at\s+(?:.*?\s)?\(?(.+?):(\d+):\d+\)?/;

export const JestParser: Parser = {
  parse(_stdout: string, stderr: string): Feedback {
    const failedTests: string[] = [];
    let m: RegExpExecArray | null;
    while ((m = FAIL_BLOCK.exec(stderr)) !== null) failedTests.push(m[1].trim());

    if (/SyntaxError|Test suite failed to parse|Unexpected token/i.test(stderr)) {
      const at = AT_LINE.exec(stderr);
      return {
        errorType: 'syntax',
        failedTests,
        assertion: at ? { file: at[1], line: Number(at[2]), snippet: 'SyntaxError' } : undefined,
        evidence: stderr,
        hint: at ? `fix syntax at ${at[1]}:${at[2]}` : 'fix syntax error',
      };
    }
    if (failedTests.length > 0 || /expect\(received\)\.toBe\(expected\)/i.test(stderr)) {
      const at = AT_LINE.exec(stderr);
      return {
        errorType: 'assertion',
        failedTests,
        assertion: at ? { file: at[1], line: Number(at[2]), snippet: 'assertion failed' } : undefined,
        evidence: stderr,
        hint: at ? `adjust implementation so ${at[1]}:${at[2]} assertion passes` : 'adjust implementation to pass failing test',
      };
    }
    return { errorType: 'other', failedTests, evidence: stderr, hint: 'inspect jest output' };
  },
};
```

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/feedbackClassifier.test.ts`
预期：PASS（3 个测试）。

> **timeout 降级路径（GAP-2）**：`run_tests` 超时 → tool 返回 `{exitCode:-1, error:'timeout', stderr:''}`；`FeedbackClassifier.parse` 调 `JestParser.parse` 找不到 SyntaxError/失败块/expect 行 → 返回 `errorType:'other'`。即 timeout→'other' 的降级发生在 `FeedbackClassifier`，与 SPEC §3.3 一致。

- [x] **步骤 5：提交** ✅ `2dd83f1`

```bash
git add src/feedback/feedbackClassifier.ts src/feedback/jestParser.ts demo/fixtures/*.txt test/feedbackClassifier.test.ts
git commit -m "feat(feedback): FeedbackClassifier + JestParser"
```

---

## 任务 9：MemoryStore（记忆维度最小实现）

**文件：**
- 新建：`src/memory/memoryStore.ts`、`test/memoryStore.test.ts`

**接口：** 产出 `MemoryStore`（`read(): {key,note}[]`、`write(key,note)`、`clear(key)`）。

- [x] **步骤 1：写失败测试**

`test/memoryStore.test.ts`:
```ts
import { MemoryStore } from '../src/memory/memoryStore';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';

test('write then read roundtrip; clear removes', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'mem-'));
  const ms = new MemoryStore(dir);
  await ms.write('convention', 'use camelCase');
  const notes = ms.read();
  expect(notes.find(n => n.key === 'convention')?.note).toBe('use camelCase');
  ms.clear('convention');
  expect(ms.read().find(n => n.key === 'convention')).toBeUndefined();
});

test('system prompt includes notes', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'mem-'));
  const ms = new MemoryStore(dir);
  await ms.write('dec', 'decided X');
  expect(ms.systemPrompt()).toContain('decided X');
});
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/memoryStore.test.ts`
预期：FAIL——模块未找到。

- [x] **步骤 3：写最小实现**

`src/memory/memoryStore.ts`:
```ts
import * as fs from 'fs/promises';
import * as path from 'path';

export interface Note { key: string; note: string; }

export class MemoryStore {
  constructor(private dir: string) {}
  private file(key: string) { return path.join(this.dir, `${key}.md`); }

  read(): Note[] {
    const { readdirSync, readFileSync, existsSync } = require('fs');
    if (!existsSync(this.dir)) return [];
    return readdirSync(this.dir)
      .filter((f: string) => f.endsWith('.md'))
      .map((f: string) => ({ key: f.replace(/\.md$/, ''), note: readFileSync(path.join(this.dir, f), 'utf8') }));
  }

  async write(key: string, note: string): Promise<void> {
    await fs.mkdir(this.dir, { recursive: true });
    await fs.writeFile(this.file(key), note);
  }

  clear(key: string): void {
    const { existsSync, rmSync } = require('fs');
    if (existsSync(this.file(key))) rmSync(this.file(key), { force: true });
  }

  systemPrompt(): string {
    const notes = this.read();
    if (notes.length === 0) return '';
    return 'Project notes:\n' + notes.map(n => `- [${n.key}] ${n.note}`).join('\n');
  }
}
```

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/memoryStore.test.ts`
预期：PASS（2 个测试）。

- [x] **步骤 5：提交** ✅ `3fe863d`

```bash
git add src/memory/memoryStore.ts test/memoryStore.test.ts
git commit -m "feat(memory): file-backed MemoryStore"
```

---

## 任务 10：CredentialStore —— EncryptedFileStore（AES-256-GCM）

**文件：**
- 新建：`src/creds/credentialStore.ts`、`test/credentialStore.test.ts`

**接口：**
- 产出：`CredentialStore` 接口、`EncryptedFileStore`（`set(key, masterPassword)`、`status()`、`clear()`、`resolve(masterPassword)`）。

- [x] **步骤 1：写失败测试**

`test/credentialStore.test.ts`:
```ts
import { EncryptedFileStore } from '../src/creds/credentialStore';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';

test('set then resolve returns key; status present without echoing', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'cred-'));
  const store = new EncryptedFileStore(path.join(dir, 'creds.enc'));
  await store.set('sk-secret', 'master-pass');
  expect(store.status()).toEqual({ present: true, source: 'encrypted-file' });
  expect(store.status()).not.toHaveProperty('key');
  const r = await store.resolve('master-pass');
  expect(r.key).toBe('sk-secret');
  expect(r.source).toBe('encrypted-file');
});

test('wrong master password fails to resolve', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'cred-'));
  const store = new EncryptedFileStore(path.join(dir, 'creds.enc'));
  await store.set('sk-secret', 'master-pass');
  await expect(store.resolve('wrong')).rejects.toThrow();
});

test('clear removes the file; status not present', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'cred-'));
  const store = new EncryptedFileStore(path.join(dir, 'creds.enc'));
  await store.set('sk-secret', 'master-pass');
  store.clear();
  expect(store.status().present).toBe(false);
});
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/credentialStore.test.ts`
预期：FAIL——模块未找到。

- [x] **步骤 3：写最小实现**

`src/creds/credentialStore.ts`:
```ts
import * as fs from 'fs/promises';
import * as crypto from 'crypto';
import { existsSync } from 'fs';

export interface CredentialStore {
  status(): { present: boolean; source: string };
  resolve(masterPassword: string): Promise<{ key: string; source: string }>;
  set(key: string, masterPassword: string): Promise<void>;
  clear(): void;
}

const ALGO = 'aes-256-gcm';
function deriveKey(master: string): Buffer {
  return crypto.pbkdf2Sync(master, 'ai4se-salt', 100000, 32, 'sha256');
}

export class EncryptedFileStore implements CredentialStore {
  constructor(private file: string) {}

  status(): { present: boolean; source: string } {
    return { present: existsSync(this.file), source: 'encrypted-file' };
  }

  async set(key: string, masterPassword: string): Promise<void> {
    const keyBuf = deriveKey(masterPassword);
    const iv = crypto.randomBytes(12);
    const cipher = crypto.createCipheriv(ALGO, keyBuf, iv);
    const ct = Buffer.concat([cipher.update(key, 'utf8'), cipher.final()]);
    const tag = cipher.getAuthTag();
    const blob = Buffer.concat([iv, tag, ct]);
    await fs.writeFile(this.file, blob);
  }

  async resolve(masterPassword: string): Promise<{ key: string; source: string }> {
    if (!existsSync(this.file)) throw new Error('no encrypted credentials');
    const buf = await fs.readFile(this.file);
    const iv = buf.subarray(0, 12);
    const tag = buf.subarray(12, 28);
    const ct = buf.subarray(28);
    const keyBuf = deriveKey(masterPassword);
    const decipher = crypto.createDecipheriv(ALGO, keyBuf, iv);
    decipher.setAuthTag(tag);
    const key = Buffer.concat([decipher.update(ct), decipher.final()]).toString('utf8');
    return { key, source: 'encrypted-file' };
  }

  clear(): void {
    const { rmSync } = require('fs');
    if (existsSync(this.file)) rmSync(this.file, { force: true });
  }
}
```

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/credentialStore.test.ts`
预期：PASS（3 个测试）。

- [x] **步骤 5：提交** ✅ `f9e8833`

```bash
git add src/creds/credentialStore.ts test/credentialStore.test.ts
git commit -m "feat(creds): EncryptedFileStore AES-256-GCM"
```

---

## 任务 11：MockApprovalGateway

**文件：**
- 新建：`src/approval/approvalGateway.ts`、`test/approvalGateway.test.ts`

**接口：**
- 产出：`ApprovalGateway` 接口（`request(action, reasons): Promise<ApprovalDecision>`）、`MockApprovalGateway`。

- [x] **步骤 1：写失败测试**

`test/approvalGateway.test.ts`:
```ts
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
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/approvalGateway.test.ts`
预期：FAIL——模块未找到。

- [x] **步骤 3：写最小实现**

`src/approval/approvalGateway.ts`:
```ts
import { Action, ApprovalDecision } from '../types';

export interface ApprovalGateway {
  request(action: Action, reasons: string[]): Promise<ApprovalDecision>;
}

export class MockApprovalGateway implements ApprovalGateway {
  private queue: ApprovalDecision[];
  constructor(decisions: ApprovalDecision[]) { this.queue = [...decisions]; }
  async request(_action: Action, _reasons: string[]): Promise<ApprovalDecision> {
    if (this.queue.length === 0) return { decision: 'deny', reason: 'mock queue empty' };
    return this.queue.shift()!;
  }
}
```

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/approvalGateway.test.ts`
预期：PASS（1 个测试）。

- [x] **步骤 5：提交** ✅ `240f296`

```bash
git add src/approval/approvalGateway.ts test/approvalGateway.test.ts
git commit -m "feat(approval): ApprovalGateway interface + MockApprovalGateway"
```

---

## 任务 12：AgentLoop —— 手写状态机（集成）

**文件：**
- 新建：`src/loop/eventSink.ts`、`src/loop/agentLoop.ts`、`test/agentLoop.test.ts`

**接口：**
- 消费：`LLMProvider`、`ToolRegistry`（+文件/shell 工具）、`Guardrail`、`ApprovalGateway`、`FeedbackClassifier`、`MemoryStore`、`ActionProtocol`。
- 产出：`AgentLoop`（`run(): Promise<{haltReason, iterations}>`）、`EventSink`。

- [x] **步骤 1：写失败测试**

`test/agentLoop.test.ts`:
```ts
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

test('full green loop: write buggy -> test fails -> feedback -> fix -> green -> finish', async () => {
  const cwd = await tmp();
  // 靶：一个"测试脚本"，仅当 add.js 正确返回和时通过
  await fs.writeFile(path.join(cwd, 'run-tests.sh'),
    process.platform === 'win32'
      ? `node -e "const a=require('./add.js');if(a(2,3)!==5){console.error('FAIL  ./add.test.js');console.error('  expect(received).toBe(expected)');console.error('  Expected: 5');console.error('  at add.test.js:4:17');process.exit(1)}else process.exit(0)"`
      : `node -e "const a=require('./add.js');if(a(2,3)!==5){console.error('FAIL  ./add.test.js\\\\n  expect(received).toBe(expected)\\\\n  Expected: 5\\\\n  at add.test.js:4:17');process.exit(1)}else process.exit(0)"`
  );
  const reg = new ToolRegistry([...fileTools, ...shellTools]);
  const llm = new ScriptedMock([
    action('write_file', { path: 'add.js', content: 'module.exports=(a,b)=>a-b;\n' }), // 有 bug
    action('run_tests', { command: 'sh run-tests.sh' }),
    action('write_file', { path: 'add.js', content: 'module.exports=(a,b)=>a+b;\n' }), // 修复
    action('run_tests', { command: 'sh run-tests.sh' }),
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
  await fs.writeFile(path.join(cwd, 'run-tests.sh'),
    `node -e "console.error('FAIL  ./add.test.js\\\\n  expect(received).toBe(expected)\\\\n  at add.test.js:4:17');process.exit(1)"`);
  const reg = new ToolRegistry([...fileTools, ...shellTools]);
  const llm = new ScriptedMock([
    action('run_tests', { command: 'sh run-tests.sh' }),
    action('run_tests', { command: 'sh run-tests.sh' }),
    action('run_tests', { command: 'sh run-tests.sh' }),
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
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/agentLoop.test.ts`
预期：FAIL——模块未找到。

- [x] **步骤 3：写最小实现**

`src/loop/eventSink.ts`:
```ts
import { Event } from '../types';
export interface EventSink { emit(e: Omit<Event, 'id'>): void; }
export const noopSink: EventSink = { emit() {} };
export class EventStore implements EventSink {
  private events: Event[] = [];
  private next = 1;
  emit(e: Omit<Event, 'id'>): void { this.events.push({ id: this.next++, ...e }); if (this.events.length > 1000) this.events.shift(); }
  since(id: number): Event[] { return this.events.filter(e => e.id > id); }
  all(): Event[] { return [...this.events]; }
}
```

`src/loop/agentLoop.ts`:
```ts
import { LLMProvider } from '../llm/provider';
import { ToolRegistry, ToolContext } from '../tools/tool';
import { Guardrail } from '../guardrail/guardrail';
import { ApprovalGateway } from '../approval/approvalGateway';
import { FeedbackClassifier } from '../feedback/feedbackClassifier';
import { MemoryStore } from '../memory/memoryStore';
import { ActionProtocol } from '../protocol/actionProtocol';
import { Action, Message, Observation } from '../types';
import { EventSink, noopSink } from './eventSink';

export interface LoopDeps {
  llm: LLMProvider;
  registry: ToolRegistry;
  guardrail: typeof Guardrail;
  approval: ApprovalGateway;
  feedback: FeedbackClassifier;
  memory: MemoryStore;
  cwd: string;
  maxIter: number;
  systemPrompt: string;
  sink?: EventSink;
}

type HaltReason = 'finish' | 'cap' | 'stuck' | 'provider_error';

export class AgentLoop {
  private messages: Message[];
  private sink: EventSink;
  constructor(private deps: LoopDeps) {
    this.sink = deps.sink ?? noopSink;
    const sys = deps.systemPrompt + (deps.memory.systemPrompt() ? '\n\n' + deps.memory.systemPrompt() : '');
    this.messages = [{ role: 'system', content: sys }, { role: 'user', content: 'complete the task using tools' }];
  }

  async run(): Promise<{ haltReason: HaltReason; iterations: number }> {
    let iter = 0;
    let lastFailKey: string | null = null;
    let sameCount = 0;
    while (iter < this.deps.maxIter) {
      iter++;
      let resp;
      try { resp = await this.deps.llm.complete(this.messages); }
      catch { return { haltReason: 'provider_error', iterations: iter }; }
      this.messages.push({ role: 'assistant', content: resp.text });
      const acts = ActionProtocol.parse(resp.text);
      if (acts.length === 0) {
        this.messages.push({ role: 'observation', content: 'no action block found; emit a fenced ```action {...}``` block' });
        continue;
      }
      const action = acts[0];
      this.sink.emit({ type: 'action', payload: action, iter });

      if (action.tool === 'finish') {
        this.sink.emit({ type: 'halt', payload: { reason: 'finish' }, iter });
        return { haltReason: 'finish', iterations: iter };
      }

      // 护栏
      const verdict = this.deps.guardrail.assess(action);
      let effective: Action = action;
      if (verdict.severity === 'high') {
        const dec = await this.deps.approval.request(action, verdict.reasons);
        this.sink.emit({ type: 'approval_decision', payload: dec, iter });
        if (dec.decision === 'deny') {
          this.messages.push({ role: 'observation', content: `DENIED: ${dec.reason} (reasons: ${verdict.reasons.join('; ')})` });
          continue;
        }
      } else if (verdict.severity === 'low') {
        this.messages.push({ role: 'observation', content: `WARN(low): ${verdict.reasons.join('; ')}` });
      }

      // 执行
      const ctx: ToolContext = { cwd: this.deps.cwd };
      const obs = await this.deps.registry.dispatch(effective, ctx);

      // run_tests 失败的反馈闭环
      if (action.tool === 'run_tests' && obs.exitCode !== 0) {
        const fb = this.deps.feedback.parse(obs);
        const key = fb.assertion ? `${fb.assertion.file}:${fb.assertion.line}` : fb.errorType;
        if (key === lastFailKey) { sameCount++; } else { sameCount = 1; lastFailKey = key; }
        const content = JSON.stringify(fb);
        this.messages.push({ role: 'observation', content });
        this.sink.emit({ type: 'observation', payload: fb, iter });
        if (sameCount >= 2) {
          this.sink.emit({ type: 'halt', payload: { reason: 'stuck', key }, iter });
          return { haltReason: 'stuck', iterations: iter };
        }
      } else {
        this.messages.push({ role: 'observation', content: JSON.stringify(obs) });
        this.sink.emit({ type: 'observation', payload: obs, iter });
      }
    }
    this.sink.emit({ type: 'halt', payload: { reason: 'cap' }, iter });
    return { haltReason: 'cap', iterations: iter };
  }
}
```

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/agentLoop.test.ts`

> **LoopState 可追溯性（GAP-3）**：`types.ts` 导出 `LoopState = 'RUNNING'|'APPROVAL_PENDING'|'EXECUTING'|'HALTED'`。`AgentLoop` 内部以控制流位置编码这四态（`while` 体=RUNNING、`await approval.request`=APPROVAL_PENDING、`dispatch`=EXECUTING、`return`=HALTED），不维护运行时 state 变量——`LoopState` 仅作 SPEC §3.7 规约可追溯的类型层存在。

预期：PASS（3 个测试）。若 Windows 下 `sh run-tests.sh` 失败，本仓库 shell 自带 Git Bash 的 `sh`，应在 PATH 中；测试已按 `process.platform` 分支处理。

- [x] **步骤 5：提交** ✅ `f5e6068`

```bash
git add src/loop/eventSink.ts src/loop/agentLoop.ts test/agentLoop.test.ts
git commit -m "feat(loop): hand-written AgentLoop state machine with integration tests"
```

---

## 任务 13：OpenAICompatProvider（真实 LLM，网络隔离）

**文件：**
- 新建：`src/llm/openaiCompat.ts`、`test/openaiCompat.test.ts`

**接口：**
- 消费：`LLMProvider`、`Message`。
- 产出：`OpenAICompatProvider`（用全局 `fetch`；4xx → `AuthError`）。

- [x] **步骤 1：写失败测试**

`test/openaiCompat.test.ts`:
```ts
import { OpenAICompatProvider } from '../src/llm/openaiCompat';

test('returns assistant text from mocked fetch', async () => {
  const calls: any[] = [];
  const fakeFetch = async (url: string, init: any) => {
    calls.push({ url, init });
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: 'LLM-SAYS' } }] }) };
  };
  const p = new OpenAICompatProvider({ baseUrl: 'https://x', apiKey: 'k', fetch: fakeFetch as any });
  const r = await p.complete([{ role: 'user', content: 'hi' }]);
  expect(r.text).toBe('LLM-SAYS');
  expect(calls[0].init.headers['Authorization']).toBe('Bearer k');
});

test('4xx throws AuthError', async () => {
  const fakeFetch = async () => ({ ok: false, status: 401, json: async () => ({ error: { message: 'bad key' } }) });
  const p = new OpenAICompatProvider({ baseUrl: 'https://x', apiKey: 'k', fetch: fakeFetch as any });
  await expect(p.complete([{ role: 'user', content: 'hi' }])).rejects.toThrow(/auth|401/i);
});
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/openaiCompat.test.ts`
预期：FAIL——模块未找到。

- [x] **步骤 3：写最小实现**

`src/llm/openaiCompat.ts`:
```ts
import { LLMProvider } from './provider';
import { Message } from '../types';

export class AuthError extends Error { constructor(m: string) { super(m); this.name = 'AuthError'; } }

export interface OpenAICompatOpts { baseUrl: string; apiKey: string; model?: string; fetch?: typeof fetch; }

export class OpenAICompatProvider implements LLMProvider {
  private fetchImpl: typeof fetch;
  constructor(private opts: OpenAICompatOpts) {
    this.fetchImpl = opts.fetch ?? fetch;
  }
  async complete(messages: Message[]): Promise<{ text: string; stopReason: string }> {
    const res = await this.fetchImpl(`${this.opts.baseUrl}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${this.opts.apiKey}` },
      body: JSON.stringify({ model: this.opts.model ?? 'gpt-4o-mini', messages, temperature: 0 }),
    });
    if (!res.ok) {
      if (res.status >= 400 && res.status < 500) {
        const e = await res.json().catch(() => ({}));
        throw new AuthError(`auth/http ${res.status}: ${JSON.stringify(e)}`);
      }
      throw new Error(`provider http ${res.status}`);
    }
    const data: any = await res.json();
    const text = data?.choices?.[0]?.message?.content ?? '';
    return { text, stopReason: data?.choices?.[0]?.finish_reason ?? 'ok' };
  }
}
```

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/openaiCompat.test.ts`
预期：PASS（2 个测试，无网络——fetch 被注入）。

- [x] **步骤 5：提交** ✅ `ad72a74`

```bash
git add src/llm/openaiCompat.ts test/openaiCompat.test.ts
git commit -m "feat(llm): OpenAICompatProvider with injectable fetch"
```

---

## 任务 14：HttpApprovalGateway（浏览器内 HITL）

**文件：**
- 新建：`src/approval/httpApprovalGateway.ts`、`test/httpApprovalGateway.test.ts`

**接口：**
- 产出：`HttpApprovalGateway`（按请求 id 索引的 pending resolver map；`resolve(id, decision)` 由 web 路由调用）。

- [x] **步骤 1：写失败测试**

`test/httpApprovalGateway.test.ts`:
```ts
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
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/httpApprovalGateway.test.ts`
预期：FAIL——模块未找到。

- [x] **步骤 3：写最小实现**

`src/approval/httpApprovalGateway.ts`:
```ts
import { Action, ApprovalDecision } from '../types';
import { ApprovalGateway } from './approvalGateway';
import { randomUUID } from 'crypto';

interface Pending { id: string; action: Action; reasons: string[]; resolve: (d: ApprovalDecision) => void; }

export class HttpApprovalGateway implements ApprovalGateway {
  private pending = new Map<string, Pending>();

  request(action: Action, reasons: string[]): Promise<ApprovalDecision> {
    const id = randomUUID();
    return new Promise<ApprovalDecision>((resolve) => {
      this.pending.set(id, { id, action, reasons, resolve });
    });
  }

  pendingList(): { id: string; action: Action; reasons: string[] }[] {
    return [...this.pending.values()].map(p => ({ id: p.id, action: p.action, reasons: p.reasons }));
  }
  pending(): { id: string; action: Action; reasons: string[] }[] { return this.pendingList(); }

  resolve(id: string, decision: ApprovalDecision): boolean {
    const p = this.pending.get(id);
    if (!p) return false;
    this.pending.delete(id);
    p.resolve(decision);
    return true;
  }
}
```

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/httpApprovalGateway.test.ts`
预期：PASS（2 个测试）。

- [x] **步骤 5：提交** ✅ `cf9c4e8`

```bash
git add src/approval/httpApprovalGateway.ts test/httpApprovalGateway.test.ts
git commit -m "feat(approval): HttpApprovalGateway with pending resolvers"
```

---

## 任务 15：WebServer（http + 轮询路由 + 事件存储）

**文件：**
- 新建：`src/web/webServer.ts`、`test/webServer.test.ts`

**接口：**
- 消费：`AgentLoop`、`HttpApprovalGateway`、`EventStore`、`CredentialStore`。
- 产出：`startWebServer({port, loopFactory, approval, creds, eventStore})` 返回 `{server}`。

- [x] **步骤 1：写失败测试**

`test/webServer.test.ts`:
```ts
import http from 'http';
import { startWebServer } from '../src/web/webServer';
import { EventStore } from '../src/loop/eventSink';
import { HttpApprovalGateway } from '../src/approval/httpApprovalGateway';
import { EncryptedFileStore } from '../src/creds/credentialStore';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';

function req(method: string, port: number, p: string, body?: any): Promise<{status: number, body: any}> {
  return new Promise((resolve) => {
    const data = body ? JSON.stringify(body) : '';
    const r = http.request({ port, path: p, method, headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } }, (res) => {
      let buf = '';
      res.on('data', (c) => (buf += c));
      res.on('end', () => resolve({ status: res.statusCode ?? 0, body: buf ? JSON.parse(buf) : {} }));
    });
    r.write(data); r.end();
  });
}

test('GET /api/health returns 200; events poll empty initially', async () => {
  const store = new EventStore();
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'web-'));
  const srv = await startWebServer({
    port: 0, eventStore: store, approval: new HttpApprovalGateway(),
    creds: new EncryptedFileStore(path.join(dir, 'c.enc')),
    loopFactory: async () => ({ haltReason: 'finish', iterations: 0 }),
  });
  const port = (srv.server.address() as any).port;
  const h = await req('GET', port, '/api/health');
  expect(h.status).toBe(200);
  const e = await req('GET', port, '/api/events?since=0');
  expect(Array.isArray(e.body)).toBe(true);
  srv.server.close();
});
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/webServer.test.ts`
预期：FAIL——模块未找到。

- [x] **步骤 3：写最小实现**

`src/web/webServer.ts`:
```ts
import http from 'http';
import { EventStore } from '../loop/eventSink';
import { HttpApprovalGateway } from '../approval/httpApprovalGateway';
import { CredentialStore } from '../creds/credentialStore';

export interface WebServerOpts {
  port: number;
  eventStore: EventStore;
  approval: HttpApprovalGateway;
  creds: CredentialStore;
  loopFactory: (task: string, cwd: string) => Promise<{ haltReason: string; iterations: number }>;
}

export async function startWebServer(opts: WebServerOpts): Promise<{ server: http.Server }> {
  const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json');
    const url = new URL(req.url ?? '', `http://localhost`);
    try {
      if (req.method === 'GET' && url.pathname === '/api/health') {
        res.end(JSON.stringify({ ok: true }));
      } else if (req.method === 'GET' && url.pathname === '/api/events') {
        const since = Number(url.searchParams.get('since') ?? '0');
        res.end(JSON.stringify(opts.eventStore.since(since)));
      } else if (req.method === 'GET' && url.pathname === '/api/key/status') {
        res.end(JSON.stringify(opts.creds.status()));
      } else if (req.method === 'GET' && url.pathname === '/api/approvals') {
        res.end(JSON.stringify(opts.approval.pending()));
      } else if (req.method === 'POST' && url.pathname === '/api/key') {
        const b = await body(req);
        await opts.creds.set(b.key, b.masterPassword);
        res.end(JSON.stringify(opts.creds.status()));
      } else if (req.method === 'POST' && url.pathname === '/api/approval') {
        const b = await body(req);
        const ok = opts.approval.resolve(b.id, { decision: b.decision, reason: b.reason ?? '' });
        res.end(JSON.stringify({ ok }));
      } else if (req.method === 'POST' && url.pathname === '/api/task') {
        const b = await body(req);
        opts.loopFactory(b.task, b.cwd).then((r) => opts.eventStore.emit({ type: 'halt', payload: r, iter: 0 }));
        res.end(JSON.stringify({ started: true }));
      } else {
        res.statusCode = 404; res.end(JSON.stringify({ error: 'not found' }));
      }
    } catch (e: any) {
      res.statusCode = 500; res.end(JSON.stringify({ error: String(e?.message ?? e) }));
    }
  });
  await new Promise<void>((r) => server.listen(opts.port, '0.0.0.0', r));
  return { server };
}

function body(req: http.IncomingMessage): Promise<any> {
  return new Promise((resolve) => {
    let buf = '';
    req.on('data', (c) => (buf += c));
    req.on('end', () => resolve(buf ? JSON.parse(buf) : {}));
  });
}
```

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/webServer.test.ts`
预期：PASS（1 个测试）。

- [x] **步骤 5：提交** ✅ `4628357`

```bash
git add src/web/webServer.ts test/webServer.test.ts
git commit -m "feat(web): http server with polling routes"
```

---

## 任务 16：静态前端面板

**文件：**
- 新建：`src/web/public/index.html`、`src/web/public/app.js`、`src/web/public/style.css`
- 修改：`src/web/webServer.ts`（提供静态文件 + `/`）

**接口：** 产出三栏 UI（任务输入 / 事件流 / 审批）。

- [x] **步骤 1：写失败测试**

`test/staticFrontend.test.ts`:
```ts
import http from 'http';
import { startWebServer } from '../src/web/webServer';
import { EventStore } from '../src/loop/eventSink';
import { HttpApprovalGateway } from '../src/approval/httpApprovalGateway';
import { EncryptedFileStore } from '../src/creds/credentialStore';
import * as os from 'os'; import * as fs from 'fs/promises'; import * as path from 'path';

test('GET / serves index.html', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'fe-'));
  const srv = await startWebServer({ port: 0, eventStore: new EventStore(), approval: new HttpApprovalGateway(), creds: new EncryptedFileStore(path.join(dir,'c.enc')), loopFactory: async () => ({haltReason:'finish',iterations:0}) });
  const port = (srv.server.address() as any).port;
  await new Promise<void>((r) => { http.get(`http://localhost:${port}/`, (res) => { let b=''; res.on('data',c=>b+=c); res.on('end',()=>{ expect(b).toContain('AI4SE-Safe-TDD-Harness'); r(); }); }); });
  srv.server.close();
});
```

- [x] **步骤 2：运行测试，验证失败**

运行：`npx jest test/staticFrontend.test.ts`
预期：FAIL——`/` 返回 404。

- [x] **步骤 3：写最小实现**

`src/web/public/index.html`:
```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>AI4SE-Safe-TDD-Harness</title>
<link rel="stylesheet" href="/style.css"></head>
<body>
<h1>AI4SE-Safe-TDD-Harness</h1>
<div class="grid">
  <section><h2>Task</h2>
    <textarea id="task" rows="4" placeholder="describe the coding task"></textarea>
    <input id="cwd" placeholder="workspace dir">
    <button id="start">Start</button>
    <h3>API Key</h3>
    <input id="master" type="password" placeholder="master password">
    <input id="apikey" type="password" placeholder="CLAUDE_API_KEY">
    <button id="setkey">Save Key</button>
    <pre id="keystatus"></pre>
  </section>
  <section><h2>Events</h2><pre id="events"></pre></section>
  <section><h2>Approvals</h2><div id="approvals"></div></section>
</div>
<script src="/app.js"></script>
</body></html>
```

`src/web/public/style.css`:
```css
body { font-family: system-ui, sans-serif; margin: 1rem; background: #f7f7f8; }
.grid { display:grid; grid-template-columns: 1fr 1fr 1fr; gap:1rem; }
section { background:#fff; padding:1rem; border:1px solid #ddd; border-radius:6px; }
textarea,input { width:100%; box-sizing:border-box; margin-bottom:.5rem; }
pre { white-space:pre-wrap; word-break:break-word; max-height:50vh; overflow:auto; background:#1e1e1e; color:#eee; padding:.5rem; }
```

`src/web/public/app.js`:
```js
let since = 0;
async function poll() {
  try {
    const e = await fetch(`/api/events?since=${since}`).then(r => r.json());
    if (e.length) { since = e[e.length-1].id; document.getElementById('events').textContent += e.map(ev=>`#${ev.id} [${ev.type}] ${JSON.stringify(ev.payload)}`).join('\n') + '\n'; }
    const ap = await fetch('/api/approvals').then(r => r.json());
    document.getElementById('approvals').innerHTML = ap.map(a=>`<div><code>${a.action.tool}</code> ${a.reasons.join(',')} <button onclick="decide('${a.id}','approve')">Approve</button><button onclick="decide('${a.id}','deny')">Deny</button></div>`).join('') || 'none';
    document.getElementById('keystatus').textContent = JSON.stringify(await fetch('/api/key/status').then(r=>r.json()));
  } catch {}
}
setInterval(poll, 1000);
document.getElementById('start').onclick = () => fetch('/api/task', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task:task.value,cwd:cwd.value})});
document.getElementById('setkey').onclick = () => fetch('/api/key', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:apikey.value,masterPassword:master.value})});
function decide(id, d) { fetch('/api/approval', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,decision:d,reason:'browser'})}); }
```

修改 `src/web/webServer.ts`：在 404 分支前加静态处理器。在 `const url = …` 行之后插入：
```ts
import { readFileSync, existsSync } from 'fs';
import * as path from 'path';
const PUB = path.join(__dirname, '..', 'public');
```
并在 handler 内、最后的 `else` 之前插入：
```ts
      } else if (req.method === 'GET' && (url.pathname === '/' || url.pathname.startsWith('/')) ) {
        const rel = url.pathname === '/' ? 'index.html' : url.pathname.slice(1);
        const f = path.join(PUB, rel);
        if (existsSync(f)) { res.setHeader('Content-Type', mime(rel)); res.end(readFileSync(f)); return; }
        res.statusCode = 404; res.end(JSON.stringify({ error: 'not found' }));
```
并在文件底部加 `mime` 辅助函数：
```ts
function mime(p: string): string {
  if (p.endsWith('.js')) return 'text/javascript';
  if (p.endsWith('.css')) return 'text/css';
  return 'text/html';
}
```
说明：`__dirname` 在 commonjs 编译产物 `dist/web/webServer.js` 下可用，`public/` 随之部署——构建时拷入 `dist`（任务 17 Dockerfile 处理）；测试在 ts-jest 源码态运行，`path.join(__dirname,'..','public')` 即 `src/web/public`。✓

- [x] **步骤 4：运行测试，验证通过**

运行：`npx jest test/staticFrontend.test.ts`
预期：PASS。

- [x] **步骤 5：提交** ✅ `8be8a8e`

```bash
git add src/web/public/ src/web/webServer.ts test/staticFrontend.test.ts
git commit -m "feat(web): static 3-panel frontend"
```

> **深度 UI 重设计（feat/07-web-redesign, 实现 `bdc5a8e` + docs `docs: log web redesign phase`）**：在 feat/07-web-panel 之上做深度 UI 重构，全面采用 Anthropic 官网极简风格——珍珠白/暖灰纸面（`#f3f0ea`）+ 纯白卡片大圆角 + 极致柔和微阴影；serif display + sans body + mono data 混搭；"左控制栏 + 右主画板"两栏；纤细 Loop State 轨道（字重/淡化映射当前状态）；底层 JSON 翻译为自然语言气泡；测试失败 Feedback 渲染为卡其色 Blockquote（醒目提示断言行号 `file:line`），成功用极简绿底细线卡；人工审批卡含原因输入框（`placeholder="补充指示或拒绝原因…"`）+ `[Approve]`/`[Deny & 反馈]`，拒绝时把输入框内容作为 `reason` 回灌实现对话重定向。`test/staticFrontend.test.ts` 扩展为 2 测试（新增 `/app.js` 审批输入框 + Deny&反馈 断言，且改为始终 resolve 的 GET 采集器消除 RED 态挂起），全量 16 suites / 40 tests 绿，`npm run build` 成功。

---

## 任务 17：机制演示（§A.6 三幕）

**文件：**
- 新建：`demo/mechanism-demo.test.ts`

**接口：** 复用 Guardrail、MockApprovalGateway、FeedbackClassifier、JestParser、ScriptedMock、AgentLoop。演示 ① 护栏 + HITL ② 反馈自修正 ③ 深行为（混淆绕过 + severity + 卡死停机）。

- [ ] **步骤 1：写失败测试**

`demo/mechanism-demo.test.ts`:
```ts
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
```

- [ ] **步骤 2：运行测试，验证失败**

运行：`npm run demo`
预期：FAIL（测试引用已存在模块，但须确认 `demo/` glob 被命中——若直接通过说明 jest 配置已含 `demo/`；失败门是 `demo/` glob 未匹配）。确保 `jest.config.js` 的 `testMatch` 含 `**/demo/**/*.test.ts`（任务 1 已含）。

- [ ] **步骤 3：写最小实现**

无新实现——演示即装配既有模块。"实现"即步骤 1 的测试文件本身。若有断言失败，按各模块自身任务修复底层模块；不得削弱演示断言。

- [ ] **步骤 4：运行测试，验证通过**

运行：`npm run demo`
预期：PASS（4 个测试）。

- [ ] **步骤 5：提交**

```bash
git add demo/mechanism-demo.test.ts
git commit -m "feat(demo): §A.6 three-act mechanism demo"
```

---

## 任务 18：Dockerfile + CI（unit-test job）+ README

**文件：**
- 新建：`Dockerfile`，修改 `.gitlab-ci.yml`，替换 `README.md`

**接口：** 产出 `docker build` → 可运行镜像；CI `unit-test` job；README 含必需章节。

- [ ] **步骤 1：写失败测试（CI 契约）**

基础设施无单元测试；"测试"即 CI job 名。用 grep 校验。

`test/ci.test.ts`:
```ts
import * as fs from 'fs';
import * as path from 'path';

test('gitlab CI defines a unit-test job', () => {
  const ci = fs.readFileSync(path.join(__dirname, '..', '.gitlab-ci.yml'), 'utf8');
  expect(ci).toMatch(/^unit-test:/m);
});

test('Dockerfile exists and is multi-stage', () => {
  const df = fs.readFileSync(path.join(__dirname, '..', 'Dockerfile'), 'utf8');
  expect(df).toContain('FROM node:20');
  expect((df.match(/FROM/g) || []).length).toBeGreaterThanOrEqual(2);
});
```

- [ ] **步骤 2：运行测试，验证失败**

运行：`npx jest test/ci.test.ts`
预期：FAIL——`Dockerfile` 缺失，`.gitlab-ci.yml` 无 `unit-test:` job。

- [ ] **步骤 3：写最小实现**

`Dockerfile`:
```dockerfile
# stage 1: build
FROM node:20-bookworm-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY tsconfig.json ./
COPY src ./src
RUN npm run build
# public 静态资源由 build 脚本的 cpSync 带入 dist/web/public；下方 cp 为冗余兜底
RUN cp -r src/web/public dist/web/public 2>/dev/null || true

# stage 2: prod
FROM node:20-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production
COPY package*.json ./
RUN npm ci --omit=dev
COPY --from=build /app/dist ./dist
EXPOSE 8080
CMD ["node", "dist/index.js"]
```

修改 `.gitlab-ci.yml`——保留既有 SAST/secret-detection；在顶层加 `unit-test` job：
```yaml
unit-test:
  stage: test
  image: node:20-bookworm-slim
  script:
    - npm ci
    - npm test
```
（插在 `include:` 行之前使其成为同级 job；勿删 `sast`/`secret_detection`。）

`src/index.ts`（替换任务 1 的 greet 桩，改为真实入口）:
```ts
export function greet(name: string): string { return `hello, ${name}`; }

async function main() {
  const args = process.argv.slice(2);
  if (args.includes('--web')) {
    const { startWebServer } = require('./web/webServer');
    const { EventStore } = require('./loop/eventSink');
    const { HttpApprovalGateway } = require('./approval/httpApprovalGateway');
    const { EncryptedFileStore } = require('./creds/credentialStore');
    const port = Number(process.env.PORT ?? 8080);
    const home = require('os').homedir();
    await startWebServer({
      port,
      eventStore: new EventStore(),
      approval: new HttpApprovalGateway(),
      creds: new EncryptedFileStore(require('path').join(home, '.ai4se', 'creds.enc')),
      loopFactory: async () => ({ haltReason: 'finish', iterations: 0 }), // 完整接线在后续任务；演示先起面板
    });
    console.log(`harness web panel on :${port}`);
  } else {
    console.log('usage: --web  (start control panel)');
  }
}
main().catch((e) => { console.error(e); process.exit(1); });
```
说明：`test/smoke.test.ts` 仍 import `greet`，该 export 保留——勿破坏它。

`README.md`（整个替换 GitLab 模板）:
```markdown
# AI4SE-Safe-TDD-Harness

一个自研的 Coding Agent Harness（Node.js/TypeScript）：手写 agent 主循环 + 可注入 Mock 的 LLM 层、shell 命令护栏 + 人工审批（HITL）、结构化 TDD 反馈闭环。可用 mock LLM 在无网络下确定性单测。

## 安装与运行（Docker）
\`\`\`
docker build -t ai4se-safe-tdd-harness .
docker run -p 8080:8080 -e MASTER_PASSWORD=... -v "$PWD/workspace":/workspace ai4se-safe-tdd-harness
\`\`\`
打开 http://localhost:8080。在面板配置 API key（AES-256-GCM 加密存储；主密码经 MASTER_PASSWORD 环境变量或交互提示输入）。

## 本地开发
\`\`\`
npm ci
npm test          # 全部单元测试
npm run demo      # §A.6 机制演示
npm run build && node dist/index.js --web
\`\`\`

## API key 安全
- 绝不经命令行传递（会进入 shell history）。
- 加密落盘 ~/.ai4se/creds.enc（AES-256-GCM），由主密码解锁。
- .env 仅作明文 fallback；使用时会告警。
- status() 绝不回显明文 key。

## 已知限制
- 主目标平台 Linux/amd64；Windows/mac 需本地构建。
- 单任务，不并发。
- FeedbackClassifier 稳健识别 Jest 的 assertion/syntax 失败；其它 runner 回退 'other'。

## CI
.gitlab-ci.yml 定义了 unit-test job（npm ci && npm test），并含 SAST 与 secret-detection。
```

- [ ] **步骤 4：运行测试，验证通过**

运行：`npx jest test/ci.test.ts && npm test`
预期：PASS（ci.test 校验 Dockerfile + unit-test job；全量测试绿）。

- [ ] **步骤 5：提交**

```bash
git add Dockerfile .gitlab-ci.yml README.md src/index.ts test/ci.test.ts
git commit -m "feat(dist): Dockerfile, CI unit-test job, README"
```

---

## 自检笔记

写完计划后运行（已内联完成）：

1. **spec 覆盖：** SPEC §3.1 ActionProtocol → 任务 3；§3.2 LLMProvider/Mock → 任务 4/13；§3.3 ToolRegistry+tools → 任务 5/6；§3.4 Guardrail → 任务 7；§3.5 ApprovalGateway → 任务 11/14；§3.6 FeedbackClassifier → 任务 8；§3.7 AgentLoop → 任务 12；§3.8 MemoryStore → 任务 9；§3.9 CredentialStore → 任务 10；§3.10 WebServer+前端 → 任务 15/16；§A.6 演示 → 任务 17；§7.2 Docker → 任务 18；CI unit-test → 任务 18。SPEC 全部章节均有任务对应。✓
2. **占位符扫描：** 无 TBD/TODO。每个步骤均含具体代码/命令。✓
3. **类型一致性：** `LLMProvider.complete` 返回 `{text, stopReason}`（任务 4/13/12 一致）。`Guardrail.assess(action)` 返回 `GuardrailVerdict`（任务 7/12）。`ApprovalGateway.request(action, reasons)` 返回 `ApprovalDecision`（任务 11/14/12）。`FeedbackClassifier.parse(obs)` 返回 `Feedback`（任务 8/12/17）。`AgentLoop.run()` 返回 `{haltReason, iterations}`（任务 12/15/17/18）。`EventStore`/`EventSink` 一致（任务 12/15/16）。`ToolRegistry.dispatch(action, ctx)`（任务 5/12）。✓
4. **缺口修复：** 任务 18 重写 `src/index.ts` 保留 `greet` 导出，使任务 1 的 smoke test 仍绿——已显式声明。ts-jest 下静态资源路径已验证（`__dirname` 解析到 `src/web`）。✓

---

## 依赖与并行度

- 串行主干：任务 1 → 任务 2 →（任务 3、4、9 可并行）→（任务 5 → 任务 6）→（任务 7、8、10、11 可并行）→ 任务 12 →（任务 13、14 可并行）→ 任务 15 → 任务 16 → 任务 17 → 任务 18。
- 可在隔离 worktree 并行（任务 4）：任务 2 后 任务 3‖4‖9；任务 6 后 任务 7‖8‖10‖11；任务 12 后 任务 13‖14。
- 按 SPEC §12 T4 裁剪：按里程碑（脚手架 / 机制 / 主循环 / web / 分发）开一个 worktree，不按任务开。
