# AI4SE-Safe-TDD-Harness

一个自研的 Coding Agent Harness（Node.js / TypeScript）：手写 agent 主循环 + 可注入 Mock 的 LLM 层、shell 命令护栏 + 人工审批（HITL）、结构化 TDD 反馈闭环。移除真实 LLM（换 `ScriptedMock`）后内核仍可确定性单测——把"治理 / 反馈 / 安全 / 分发"这些工程纪律落实为可单测的代码机制。

## 项目简介

本项目是 AI4SE 期末项目 A 选项（Coding Agent Harness）。交付的是一个**自研 harness 内核**：把 LLM 包装成一个可靠的编码 agent，而非在现有 agent 框架之上做配置层。核心机制——工具分发、治理拦截、反馈回灌、记忆读写、halt 决策——全部是手写的确定性函数，可用 mock/stub LLM 在**无网络**下独立验证。

- **自研主循环** `AgentLoop`：`RUNNING → APPROVAL_PENDING → EXECUTING → HALTED` 手写状态机，编排 LLM / 工具 / 护栏 / 审批 / 反馈。
- **治理维度 1 — Guardrail**：`shell-quote` token 层匹配危险模式库，揭穿 `r""m`/引号混淆；`high` 触发 HITL，`low` 告警，`none` 直行。
- **反馈维度 2 — FeedbackClassifier**：Jest 失败 stderr 解析为 `assertion`/`syntax`/`other`，回灌 `file:line` + `hint`，连续 2 轮同一断言点失败 → `HALTED(stuck)`。
- **凭据治理** `EncryptedFileStore`：AES-256-GCM 加密落盘，`status()` 不回显明文；`JsonConfigStore` 以明文 JSON 存放非密的端点配置。
- **面板解耦配置**：Web 面板可分别录入 `API_KEY`、请求地址（`API_BASE_URL`）、请求模型（`MODEL`），三者独立保存，无需改环境变量即可切换供应商。
- **最小 Web 面板**：Node `http` 轮询（非 WS），浏览器内提交任务 + 实时事件流 + HITL 审批；无有效 Key 时自动降级离线 `ScriptedMock` 自修正演示。
- **CLI 三模式**：`--web`（面板）/ `--task "<描述>"`（单次）/ `-i`（交互 REPL，默认）；终端内高危动作触发 `y/n/文本反馈` 悬停审批，反馈文本回灌重定向对话；凭据经 `creds.enc` → `.env` 兜底 → 离线 `ScriptedMock` 三级降级。
- **Docker 分发**：`docker run -p 8080:8080` 一条命令起面板。

## 安装

```bash
git clone https://git.nju.edu.cn/241880540/ai4se-safe-tdd-harness.git
cd ai4se-safe-tdd-harness
npm ci
```

环境要求：Node.js ≥ 20（见 `package.json` 的 `engines`）。本地开发还需 Docker（用于分发镜像构建，见下文「分发命令」）。

> 仓库不携带任何真实凭据：`.env` 已被 `.gitignore` 排除且必须保持未跟踪，`.env.example` 仅作字段模板（值为空）。首次运行凭据经 Web 面板录入并加密落盘，详见「安全边界说明」。

## 运行

### 1. 本地测试（无网络、无真实 LLM，确定性）

```bash
npm test          # 全部单元测试（无网络，含 mock LLM 闭环）
npm run demo      # §A.6 机制演示三幕
```

`npm test` 与 `npm run demo` 均在无网络、无真实 LLM 下确定性通过——这是内核"移除 LLM 后仍可单测"的硬标准（SPEC §4.4 / §11.3）。

### 2. Web 面板（生产/评审主入口）

构建并启动后访问 http://localhost:8080 ：

```bash
npm run build
$env:MASTER_PASSWORD="<写入你的主密码>" # 注入主密码环境变量(Windows PowerShell写法)
node dist/index.js --web          # 监听 $PORT，默认 8080
```

面板左侧「凭据与端点」区分三段独立配置（解耦设计，见下）：

| 面板字段 | 落盘位置 | 形态 | 说明 |
|---|---|---|---|
| `API_KEY` | `~/.ai4se/creds.enc` | **密文**（AES-256-GCM） | 经主密码加密落盘，`status()` 只回 `{present, source}`，永不回显明文 |
| 请求地址 (`API_BASE_URL`) | `~/.ai4se/config.json` | **明文 JSON** | 非密，OpenAI 兼容端点，如 `https://api.openai.com/v1` |
| 请求模型 (`MODEL`) | `~/.ai4se/config.json` | **明文 JSON** | 非密，按供应商填写，如 `gpt-4o-mini` |

三者齐备（主密码 + 端点 + 可解密 key）即可使用在线 `OpenAICompatProvider`，在面板录入 `API_KEY` + 主密码保存（加密落盘），再填请求地址 / 模型后提交任务即可完成真实大模型Agent开发（点击启动循环后会有较大延迟，请耐心等待）；任一缺失则降级离线 `ScriptedMock`，无 Key 也能在浏览器观看完整 TDD 自修正闭环演示。

### 3. CLI 命令行模式（交互 REPL / 单次任务）

除 Web 面板外，harness 同样可在终端直接驱动——适合脚本编排、CI 与无浏览器场景。三种模式：

```bash
npm run build

# (a) 交互式 REPL（默认）：`harness > ` 循环提示符，连续下达自然语言任务
node dist/index.js                     # 等价于 -i / --interactive
node dist/index.js -i

# (b) 单次任务：执行一次后退出
node dist/index.js --task "实现一个 add(a,b) 函数并用测试验证"
node dist/index.js --task "..." --cwd "<工作区绝对路径>"   # 指定工作目录
node dist/index.js "实现 add"                            # 裸参数简写

# (c) Web 面板（同 §2）
node dist/index.js --web

# 帮助
node dist/index.js -h
```

**凭据与降级：** CLI 优先读 `~/.ai4se/creds.enc`（需设 `MASTER_PASSWORD` 环境变量解密）；`.env` 的 `API_KEY` / `API_BASE_URL` / `MODEL` 作明文兜底（带告警，SPEC §3.9）；三者均无时自动降级为离线 `ScriptedMock` 自修正演示——零配置即可在终端观看到完整的「写 buggy → 测试失败 → 修正 → 测试通过」闭环。

```bash
# 离线冒烟（无 Key，终端即跑）
node dist/index.js --task "implement add" --cwd "<临时目录绝对路径>"
# 期望输出：[done] haltReason=finish, iterations=5
```

**终端内 HITL 人工审批：** 当 agent 试图执行高危动作（如 `rm -rf /`，由 `Guardrail.assess` 判定 `high`），REPL 会在终端悬停并提示：

```
⚠️  高危动作待审批:
  tool: run_shell
  args: {"command":"rm -rf /"}
  reasons: recursive-delete: recursive forced deletion
[y] 批准 / [n] 拒绝 / 或输入文本反馈以重定向: 
```

- 输入 `y` / `yes` → 批准执行；
- 输入 `n` / `no` → 拒绝；
- 输入任意文本（如「请改用 trash 而非 rm」）→ 拒绝，**且该文本作为反馈回灌进对话**，agent 下一轮会看到这条拒绝原因并据此重定向——这是「治理拦截 + 反馈闭环」两条代码机制在终端的交汇点。

REPL 任务完成后**不退出进程**，继续等待下一次指令，直到输入 `exit` 或 `quit`。

### 4. 真实 LLM 集成测试（可选，需联网，可能出现超时情况）

```bash
# 【Windows PowerShell】写法：
$env:REAL_LLM_TEST="true"
$env:MASTER_PASSWORD="你的主密码" # 自动解密 ~/.ai4se/creds.enc 里的 Key
$env:API_BASE_URL="请求地址"
$env:MODEL="请求模型" 
npm test -- test/integration/real-llm.test.ts
```

## 分发命令

目标评审平台可能为 **Linux 或 Windows**，故给出两条分发路径。

### 路径 A：Docker（推荐，跨平台一致）

```bash
docker build -t ai4se-safe-tdd-harness .
docker run -p 8080:8080 -e MASTER_PASSWORD=<你的主密码> -v "<物理工作区绝对路径>:/workspace" ai4se-safe-tdd-harness
```

启动容器后访问 http://localhost:8080。使用方式与本地开发一致（无key降级为机制演示；保存key后使用真实大模型）。在面板录入 `API_KEY` + 主密码保存（加密落盘），再填请求地址 / 模型后提交任务即可。（在 Web 面板输入的「工作区目录」必须固定填写为 /workspace，点击启动循环后会有较大延迟，请耐心等待）。

> Docker 镜像基于 `node:20-bookworm-slim`（Linux）。Linux 直接 `docker build`；Windows / macOS 通过 Docker Desktop 构建（跨平台一致）。

### 路径 B：原生 Node（无需 Docker）

适用于机器未装 Docker 或需直接运行源码的场景：

```bash
npm ci
npm run build
# 【Windows PowerShell】
$env:MASTER_PASSWORD="<写入你的主密码>"
node dist/index.js --web          # Linux / Windows 通用
```

> 主密码经 `MASTER_PASSWORD` 环境变量传入；生产优先用面板录入 + 加密文件。

## 目录结构

```
ai4se-safe-tdd-harness/
├── src/
│   ├── approval/          # HITL 审批网关：approvalGateway / httpApprovalGateway / cliApprovalGateway
│   ├── cli/               # CLI 模式：args(参数解析) / envLoader(.env) / repl(交互会话)
│   ├── creds/             # 凭据与配置：credentialStore(AES-256-GCM) / configStore(明文 JSON) / credResolver(凭据决议)
│   ├── feedback/          # 反馈分类：feedbackClassifier + jestParser
│   ├── guardrail/         # 治理护栏：guardrail + dangerPatterns（危险模式库）
│   ├── llm/               # LLM 层：provider(接口) / openaiCompat(在线) / scriptedMock + offlineDemo(离线)
│   ├── loop/              # 自研主循环：agentLoop(状态机) + eventSink(事件队列)
│   ├── memory/            # 记忆读写：memoryStore
│   ├── protocol/          # 动作协议：actionProtocol（LLM 输出解析）
│   ├── tools/             # 工具分发：tool(注册表) / fileTools / shellTools
│   ├── web/               # Web 面板：webServer(http 轮询) + public/(index.html/app.js/style.css)
│   ├── index.ts           # 入口：buildSystemPrompt + makeLoopFactory + CLI 三模式分发（--web / --task / -i）
│   └── types.ts
├── test/                  # 单元测试（无网络，mock LLM）；integration/real-llm.test.ts 可选联网
├── demo/                  # §A.6 机制演示：mechanism-demo.test.ts + fixtures/
├── Dockerfile             # 多阶段构建（build → 生产镜像），CMD 带 --web
├── .gitlab-ci.yml         # 含 unit-test job（npm ci && npm test）
├── .env.example           # 字段模板（值为空，不含真实凭据）
├── package.json           # scripts: test / demo / build / start
├── tsconfig.json
├── jest.config.js
├── SPEC.md                # 规范（含「领域与机制设计」章节）
├── PLAN.md                # 任务计划（随提交标记完成）
├── SPEC_PROCESS.md        # 规范流程（含冷启动校验 diff）
├── AGENT_LOG.md           # 按时间戳的过程证据
└── REFLECTION.md          # 自述反思（1500–2500 字）
```

## 安全边界说明

### 威胁模型与对策（详见 SPEC §4.2）

| 威胁 | 路径 | 对策 |
|---|---|---|
| Git 提交泄露 | `.env` / 配置进仓 | `.gitignore` 排除 `.env`、`~/.ai4se/`；提交前自查；CI secret-detection |
| Shell history | `export KEY=` / `-e KEY=` | 一律走加密文件或 `MASTER_PASSWORD` 环境变量；禁止命令行明文传 key |
| 进程环境可见 | `env` 可读 | 加密文件优先；`.env` 仅 fallback 并告警；运行时不打印 key |
| 磁盘明文 | `.env` 落盘 | 主路径用 AES-256-GCM 加密文件 `~/.ai4se/creds.enc` |
| 拦截绕过 | `r""m` / base64 管道 | `shell-quote` token 层匹配，揭穿引号 / 转义混淆 |
| 凭据外传 | `curl -H Authorization` | 危险模式库含"带 Authorization 的外发请求"模式 |

### 密码 / 密文 / 明文 的分层设计

系统区分**密**与**非密**两类数据，分别采用不同存储形态：

1. **`API_KEY`（密文落盘）**——这是唯一真正的 secret。浏览器 `POST /api/key` 录入后，用主密码经 PBKDF2 派生密钥（`aes-256-gcm`，100k 轮迭代），加密落盘至 `~/.ai4se/creds.enc`；运行时 `resolve()` 仅在内存解密，`GET /api/key/status` 只返回 `{present, source}`，**绝不回显**明文 key。
2. **请求地址 `API_BASE_URL` / 请求模型 `MODEL`（明文 JSON 落盘）**——二者不含 secret，仅是供应商端点与模型名。按 §3.1 只要求 API key 加密落盘，故端点 / 模型以明文存于 `~/.ai4se/config.json`，便于查看与跨会话复用，与加密凭据**物理分离**。
3. **主密码（不落盘）**——解锁加密凭据的口令，经 `MASTER_PASSWORD` 环境变量或面板输入传入，进程内使用、不持久化；丢失后无法解密 `creds.enc`（需重新录入 key）。
4. **`.env`（明文 fallback，带告警）**——仅作离线开发兜底，生产优先用加密文件；`.env` 已被 gitignore 且必须保持未跟踪。

### 操作要点

- **绝不**在命令行明文传递 key（会进 shell history）。容器内主密码经 `MASTER_PASSWORD` 环境变量传入。
- 面板录入的 `API_KEY` 经 AES-256-GCM 加密落盘，由主密码解锁；请求地址 / 模型明文存于独立 JSON。
- `.env` 仅作明文 fallback（带告警）；每次提交前自查仓库内无真实凭据（`grep 'sk-'` 暂存区无命中）。

### 治理护栏的代码边界（机制非提示）

"不要删除数据库"写在 system prompt 里**不算**治理；`Guardrail.assess(action)` 这个确定性函数拦截 `rm -rf /` 才算。本仓库所有核心机制——`Guardrail`、`FeedbackClassifier`、`ToolRegistry.dispatch`、`MemoryStore`、`AgentLoop` 的 halt 判定——均为手写函数，移除真实 LLM 换 `ScriptedMock` 后仍可确定性单测（`npm test` 全绿）。

## 架构与数据流

```
AgentLoop (自研主循环)
  RUNNING → [Guardrail.assess] → APPROVAL_PENDING → EXECUTING
                                       │                 │
                            [observation 回灌]   ToolRegistry.dispatch
  └─ LLMProvider(OpenAICompat / ScriptedMock)
     └─ CredentialStore(EncryptedFileStore) ── ConfigStore(JsonConfigStore)
        └─ HttpApprovalGateway ── WebServer(http 轮询) ── 静态前端
```

在一轮完整的系统迭代中，数据流运转逻辑如下：状态机首先组装历史上下文（Messages） → 呼叫 LLMProvider.complete 获取决策 → 通过 ActionProtocol.parse 提取动作 → 引入 Guardrail.assess 进行安全审计（high 等级进入 HITL 审批流） → 调用 ToolRegistry.dispatch 分发工具并物理执行。若工具为测试执行且返回非零退出，则由 FeedbackClassifier.parse 进行错误分类与断言定位，并结构化回灌进上下文。当遇到 finish 动作、卡死（stuck）或达到绝对迭代上限时，循环状态机熔断转入 HALTED。所有的系统事件均会被实时推送至内存事件队列，供前端面板轮询。

## 已知限制

- 单任务，不并发。
- HTTP 轮询而非 WebSocket；`FeedbackClassifier` 稳健识别 Jest 的 `assertion`/`syntax`，其它 runner 回退 `other`。
- `OpenAICompatProvider` 仅适配单 OpenAI-compatible 供应商（`/v1/chat/completions`）。

## CI

`.gitlab-ci.yml` 定义了 `unit-test` job（`npm ci && npm test`）。机制演示见 `demo/mechanism-demo.test.ts`（`npm run demo`）。

## 许可

MIT
