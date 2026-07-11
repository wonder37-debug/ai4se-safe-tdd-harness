# SPEC.md — AI4SE-Safe-TDD-Harness

---

## 1. 问题陈述

**要解决什么问题**：当 LLM 能完成大部分"写代码"的动作时，一个编码智能体能否稳定、安全、可自我修正地闭环工作，取决于包裹 LLM 的那层工程（harness）——主循环、工具分发、治理护栏、反馈回灌、凭据治理、分发。市面上的 agent 编排框架（LangChain `AgentExecutor`、AutoGen、CrewAI 等）把这层工程封装成了配置项，使学习者难以第一手理解"一台可靠机器到底由哪些确定性机制构成"。

**目标用户**：
- AI4SE 课程的学习者/评审者——借此项目第一手批判性理解 harness 工程方法论。
- 任何想在一台全新机器上、安全配置自己 key 后，观察一个编码 agent 在受限沙箱内自主 TDD 闭环的开发者。

**为什么值得做**：它把"治理 / 反馈 / 安全 / 分发"这些在 AI 协作中容易松懈的工程纪律，落实为可移除 LLM 后仍能确定性单测的代码机制——这正是课程命题"当 LLM 能完成大部分编码工作时，工程师的真正价值在哪里"的可执行回答。

**项目定位**：本项目为个人课程项目，优先可完成性。范围收敛到一个自研内核 + 两个深机制（治理护栏、TDD 反馈闭环）+ 最小 WebUI + Docker 分发。暂不引入：多 agent 编排、向量检索记忆、多 LLM 供应商适配、npm 发包流水线、WebSocket 实时推送。

---

## 2. 用户故事（INVEST）

- **US1 — 离线跑通闭环**：作为开发者，我想在无网络、无真实 LLM 的情况下用预设 Mock 跑通"写文件→跑测试→失败→修正→绿"的完整闭环，以便快速回归验证 harness 内核。（I/N/V/S/T；E：Mock 注入即可）
- **US2 — 危险命令被拦**：作为用户，我想让 agent 即便产出 `rm -rf /` 或 `curl ... | sh` 也被确定性拦截并暂停等审批，以便信任地让它跑 shell。（I/N/V/S/T；E：构造 action 断言拦截）
- **US3 — 测试失败自修正**：作为开发者，我想让 agent 跑 `npm test` 失败后，stderr 被结构化解析成断言位置/错误类型并回灌，促使 agent 在迭代上限内自我修正到绿，以便观察真实的 TDD 反馈闭环。（I/N/V/S/T；E：注入 Jest 失败 fixture 断言回灌）
- **US4 — 安全配置 key**：作为新机器用户，我想首次运行被引导隐藏录入 API key，落盘为加密文件、不回显明文、可查看状态/更新/清除，以便合规使用付费 LLM。（I/N/V/S/T；E：首运行引导 + clear 后断言不可读）
- **US5 — 一键起 Web 面板**作为部署评审者：我想 `docker run` 一条命令起一个 Web 面板，能在浏览器里提交任务、实时看循环事件流、并审批 HITL 请求，以便满足"可访问 WebUI"交付并远程观察 agent。（I/N/V/S/T；E：docker run 后浏览器可访问）

---

## 3. 功能规约（按模块）

每个模块 = 输入 / 行为 / 输出 / 边界 / 错误处理。所有模块均为独立可测单元，靠接口通信。

### 3.1 ActionProtocol（动作协议解析器）
- 输入：`string`（LLM 返回的文本，含 0 或多个 ` ```action {...} ``` ` 围栏块）。
- 行为：正则提取围栏块 → `JSON.parse` → 校验 `tool` 字段在注册表内 → 返回 `Action{tool, args}`。无围栏块时视为"无动作"并回灌一条要求重新输出合法动作的 observation。
- 输出：`Action[]`（每轮只取首个执行，其余告警丢弃）。
- 边界：JSON 非法 → 回灌解析错误 observation，不计迭代；空文本 → 回灌提示。
- 错误处理：解析异常不抛到主循环，转为结构化 observation。

### 3.2 LLMProvider（LLM 抽象层）
- 接口：`async complete(messages: Message[]): Promise<{text: string, stopReason: string}>`。
- 生产实现 `OpenAICompatProvider`：用 HTTP 库调裸 `POST {API_BASE_URL}/v1/chat/completions`，`Authorization: Bearer <key>`，流式关、`temperature` 可配。**不使用任何 agent SDK**。
- 测试实现 `ScriptedMock`：构造时传入响应队列 `string[]`，每次 `complete` 弹一个；可选 `sticky: boolean` 让末条粘滞兜底。
- 边界：HTTP 4xx（鉴权失败）→ 抛 `AuthError` 由主循环 HALTED；5xx/超时 → 重试 1 次后 HALTED。
- 错误处理：网络错误不静默，转为 `haltReason:'provider_error'`。

### 3.3 ToolRegistry（工具分发）
- 注册工具：`read_file / write_file / list_dir / run_shell / run_tests / finish`。
- 每个 tool：`{name, schema, execute(args, ctx): Promise<Observation>}`，`ctx` 含 `cwd`；`MemoryStore`/`CredentialStore` 由 `AgentLoop` 直接持有，**不注入 `ToolContext`**（当前无 tool 需要它们，YAGNI 裁剪；后续若有 tool 需凭据/记忆，再扩 `ctx`）。
- `run_shell`/`run_tests` 执行前先过 `Guardrail.assess`（由主循环调用，非 tool 内部）。
- 边界：`read_file` 越界（如二进制大文件）→ 截断并标注；`run_tests` 超时 60s → tool 返回 `error:'timeout'`、`exitCode:-1`，由 `FeedbackClassifier` 归类为 `'other'`（降级发生在 FeedbackClassifier，非 tool）。
- 错误处理：tool 抛错 → 转 `Observation{ok:false, error}` 回灌。

### 3.4 Guardrail（治理护栏 — 主贡献维度 1）
- 输入：`Action`（仅 `run_shell`/`run_tests` 评估）。
- 行为：`shell-quote` tokenize 命令 → 命中危险模式库 → 判 `severity`。
- 输出：`{severity: 'none'|'low'|'high', reasons: string[]}`。
- 危险模式库（声明式 `dangerPatterns.json`，~7-9 条）：`rm -rf`/`--no-preserve-root` 递归删、`sudo`/`su` 提权、`curl|sh`/`wget|bash` 远程脚本执行、`DROP TABLE/DATABASE/TRUNCATE`、fork bomb、写系统路径（`> /etc/`、`> /dev/sd*`、cron）、`chmod 777` 关键路径、**带 `Authorization`/`-H ...token` 头的外发请求**（凭据外传）。
- 边界：`low`（如 `rm` 无 `-rf`）→ 告警继续；`high` → 触发 HITL；`none` → 直行。
- 错误处理：tokenize 失败（畸形命令）→ 视为 `high`，强制审批。

### 3.5 ApprovalGateway（HITL 审批抽象）
- 接口：`async request(action, reasons): Promise<{decision: 'approve'|'deny', reason: string}>`。
- 生产实现 `HttpApprovalGateway`：返回 Promise，resolver 挂到 `pendingApprovals[id]`，等 `POST /api/approval` 命中 id 后 resolve；超时 5min 默认 deny。
- 测试实现 `MockApprovalGateway`：构造时传入裁决队列，按序返回。
- 边界：deny 的 reason 作为 observation 回灌；approve 后进入 EXECUTING。

### 3.6 FeedbackClassifier（TDD 反馈闭环 — 主贡献维度 2）
- 输入：`run_tests` 的 `Observation{stdout, stderr, exitCode}`。
- 行为：`JestParser` 识别 Jest 失败块（`● file › test`）与栈行（`at file:line:col`）→ 分类 `errorType: 'assertion'|'syntax'|'other'` → 提取 `assertion{file,line,snippet}` + `evidence`（截断至 2000 字符）。
- 输出：结构化 `Feedback` + 针对性 `hint`（`assertion`→"调整实现使 {file}:{line} 断言通过"；`syntax`→"先修复 {file}:{line} 语法"；`other`→"查看 evidence 修正"）。
- 回灌：组装成 `{role:'observation', content: JSON.stringify(feedback)}` 追加到 messages。
- 边界：解析不出结构 → `errorType:'other'`，回灌截断 stderr 末 30 行。
- 错误处理：纯函数，无副作用；超时归类 `other`。
- Parser 接口可插拔（`{parse(stdout,stderr): Feedback}`），暂只实现 `JestParser`。

### 3.7 AgentLoop（自研主循环状态机）
- 状态：`RUNNING / APPROVAL_PENDING / EXECUTING / HALTED`（`types.ts` 导出 `LoopState` 联合型作规约可追溯；循环内部以控制流位置编码这些状态）。
- 编排：见 §5 数据流。停机条件：`finish` 动作 / 绝对迭代上限 `MAX_ABS=20` / 连续 2 轮同一 `assertion.file:line` 失败（`HALTED(stuck)`）/ provider 不可恢复错误。
- 边界：每轮迭代编号、状态、action、observation 全程记 `AGENT_LOG.md` 与内存事件队列。
- 错误处理：任何未预期异常 → `HALTED(error)` 并把错误写事件流。

### 3.8 MemoryStore（记忆维度最小实现）
- 接口：`read(): Note[]`、`write(key, note): void`、`clear(key): void`。
- 实现：`./memory/*.md` 文件式 KV，启动时把约定类笔记拼进 system prompt。
- 边界：不引入向量库；非深维度，仅满足六维度"可运行最低实现"。

### 3.9 CredentialStore（凭据安全）
- 接口：`resolve(): {key, source}`、`status(): {present, source}`（不回显明文）、`set(key)`、`clear()`。
- 实现 `EncryptedFileStore`：AES-256-GCM 加密落盘 `~/.ai4se/creds.enc`，主密码隐藏输入（readline mute）；`resolve()` 顺序：加密文件（需主密码）→ `.env` fallback（附明文风险告警）。
- 首运行引导：无凭据 → 提示隐藏录入 → 写加密文件 → 验证可读。
- 边界：容器内主密码经 `MASTER_PASSWORD` 环境或 stdin 传入，避免命令行 `-e KEY=` 进 history。

### 3.10 WebServer + 前端面板（§五 item 9 WebUI）
- `WebServer`（Node `http`，**轮询非 WS**）：
  - `POST /api/key` — 录入/更新 key（隐藏，写加密文件）。
  - `GET /api/key/status` — `{present, source}` 不回显。
  - `POST /api/task` — 提交任务描述 + workspace，启动一个 `AgentLoop`。
  - `GET /api/events?since=N` — 返回 id>N 的事件数组（action/observation/审批请求/halt）。
  - `POST /api/approval` — `{id, decision, reason}`，触发 `HttpApprovalGateway` resolver。
- 前端：静态 HTML + 原生 JS（无框架），三栏：任务输入 / 事件流（每秒轮询）/ 待审批区。
- 边界：单任务并发。

---

## 4. 非功能性需求

### 4.1 性能
- 单轮 LLM 往返为主延迟；Mock 模式下完整闭环 < 1s。
- `run_tests` 超时 60s；`run_shell` 超时 30s。
- 事件队列内存上限 1000 条，超出丢弃最旧并标注。

### 4.2 安全（凭据威胁模型）

| 威胁 | 路径 | 对策 |
|---|---|---|
| Git 提交泄露 | `.env`/配置进仓 | `.gitignore` 排除 `.env`、`~/.ai4se/`；提交前自查；CI 设 secret-detection |
| Shell history | `export KEY=` / `-e KEY=` | 一律走 `.env` 文件或 stdin/加密文件；禁止命令行明文传 key |
| 进程环境可见 | `env` 可读 | 加密文件优先；`.env` 仅 fallback 并告警；运行时不打印 key |
| 磁盘明文 | `.env` 落盘 | 主路径用 AES-256-GCM 加密文件；`.env` 标注明文风险 |
| 拦截绕过 | `r""m`/base64 管道 | shell-quote tokenize 在 token 层匹配，揭穿引号/转义混淆 |
| 越权 shell | `rm -rf /` 等 | Guardrail high 拦截 + HITL；`low` 告警 |
| 凭据外传 | `curl -H Authorization` | 危险模式库含"带 Authorization 的外发请求"模式 |

### 4.3 可用性 / 可观测性
- WebUI 实时事件流；`AGENT_LOG.md` 全程留痕；halt 必带 `haltReason`。
- 错误信息面向开发者（含 file:line / 迭代号）。

### 4.4 可测试性（§A.4-C 硬标准）
- 每个核心机制（ActionProtocol/ToolRegistry/Guardrail/ApprovalGateway/FeedbackClassifier/MemoryStore/CredentialStore/AgentLoop）替换为 Mock 后可确定性单测，不依赖网络与真实 LLM。

---

## 5. 系统架构与数据流

### 5.1 组件图

```
┌─────────────────────────────────────────────────────────────┐
│                        AgentLoop (自研主循环)                │
│  RUNNING → [Guardrail.assess] → APPROVAL_PENDING → EXECUTING │
│                              ↑              ↓                │
│                       [observation 回灌]  ToolRegistry.dispatch│
└──────┬──────────────┬──────────────┬───────────────┬────────┘
       │              │              │               │
   LLMProvider    ActionProtocol   Guardrail     FeedbackClassifier
   (OpenAICompat   (parser)        (维度1)        (维度2 / JestParser)
   /ScriptedMock)
       │
   CredentialStore ── MemoryStore ── ApprovalGateway(Http/Mock)
       │                                  │
   EncryptedFileStore                pendingApprovals[]
       │                                  │
   ~/.ai4se/creds.enc                 POST /api/approval
                                          │
                          WebServer (http, 轮询) ── 静态前端
```

### 5.2 数据流（一轮迭代）
1. `AgentLoop` 组装 messages（system prompt + MemoryStore 笔记 + 历史 action/observation）→ `LLMProvider.complete`。
2. `ActionProtocol.parse` → `Action`。
3. `Guardrail.assess(action)`：`high`→`ApprovalGateway.request`→(approve/deny)；`low`→告警；`none`→直行。
4. `ToolRegistry.dispatch(action)` → `Observation`。
5. 若 `run_tests` 且 `exitCode!=0` → `FeedbackClassifier.parse` → 结构化 `Feedback` 回灌。
6. observation 追加进 messages → 回到 1；`finish`/上限/卡死 → `HALTED`。
7. 全程事件入队列供 `GET /api/events` 轮询。

### 5.3 外部依赖
- LLM 供应商：OpenAI-compatible `/v1/chat/completions`（匹配 `.env` 的 `API_KEY` + `API_BASE_URL` 代理）。
- npm 运行时：Node 20 LTS。
- 运行时依赖：`shell-quote`（tokenize）、HTTP 库（`undici` 或 Node 内置 `fetch`）、无框架前端。
- 外部工具：被 agent 调用的 `npm test`（靶项目用 Jest）。

---

## 6. 数据模型

- `Message = {role: 'system'|'user'|'assistant'|'observation', content: string}`。
- `Action = {tool: string, args: object}`。
- `Observation = {ok: boolean, stdout?, stderr?, exitCode?, error?, content?}`。
- `Feedback = {errorType: 'assertion'|'syntax'|'other', failedTests: string[], assertion?: {file,line,snippet}, evidence: string, hint: string}`。
- `GuardrailVerdict = {severity: 'none'|'low'|'high', reasons: string[]}`。
- `Approval = ApprovalRequest & Partial<ApprovalDecision>`（实现侧拆为 `ApprovalRequest{ id, action, reasons }` 与 `ApprovalDecision{ decision, reason }` 两型，组合还原本统一型）。
- `Event = {id, type: 'action'|'observation'|'approval_request'|'approval_decision'|'halt', payload, iter}`。`approval_decision` 为 PLAN 扩展（前端轮询审批结果用）；`payload` 对应：`action`→`Action`、`observation`→`Observation|Feedback`、`approval_request`→`ApprovalRequest`、`approval_decision`→`ApprovalDecision`、`halt`→`{reason}`。

---

## 7. 凭据与分发设计

### 7.1 凭据
- 存储：`EncryptedFileStore`（AES-256-GCM，`~/.ai4se/creds.enc`，主密码隐藏输入）。
- 录入/更新/清除：首运行引导隐藏录入；`status()` 只返回 `{present, source}` 不回显明文；`clear()` 删文件并断言不可读。
- 来源优先级：加密文件 > `.env`（fallback，附告警）。
- 容器：主密码经 `MASTER_PASSWORD` 环境或 stdin；禁止 `-e API_KEY=sk-...`。

### 7.2 分发（仅 Docker，2 周裁剪）
- `Dockerfile`（多阶段：stage1 装依赖+构建静态前端；stage2 `npm ci --omit=dev` + 复制产物 → 单镜像 `node server.js`）。
- 获取：`docker pull` 镜像（推送到公开 registry，具体 registry/镜像名在 PLAN 定）；运行：`docker run -p 8080:8080 -e MASTER_PASSWORD=... -v ./workspace:/workspace`。
- 目标机 key 配置：浏览器 `POST /api/key` 录入（写容器内加密文件）或挂载加密文件卷。
- 已知限制：Linux/amd64 优先；Windows/Mac 需自行构建；单任务并发。
- CI：`.gitlab-ci.yml` 增 `unit-test` job（`npm ci && npm test`）与 `docker-build` job。

---

## 8. 技术选型与理由

- **Node.js 20 LTS**：生态成熟、与靶项目（Jest/npm）同构、`crypto`/`http`/`fetch` 内置、学习成本低。
- **自研主循环（while 状态机）**：满足 §A.4-A"不得寄生高层框架"；状态机用普通 switch 实现，可单测。
- **OpenAI-compatible 单供应商**：匹配现成 `.env` 代理；不做多供应商适配（YAGNI）。
- **shell-quote tokenize**：在 token 层而非字符串层匹配，揭穿混淆，是治理维度工程深度的核心。
- **轮询而非 WebSocket**：省 `ws` 管道，演示够用。
- **无框架前端 (Open Design)**：选用 `Anthropic Minimal` 设计系统与 `frontend-design` 技能。免去构建链，利用原生静态 HTML/JS/CSS 满足面板与审批的轻量级交互。
- **Docker 单分发**：满足分发要求。

---

## 9. 验收标准

- **AC1（内核可运行）**：Mock 模式下 `npm test` 跑通 US1 闭环，全程无网络。
- **AC2（护栏）**：构造 `Action(run_shell,'rm -rf /')` 断言 `severity==='high'`；构造 `r""m -rf /` 等混淆用例断言仍命中；`MockApprovalGateway` 走完 approve/deny 两分支。
- **AC3（反馈闭环）**：注入 Jest 断言失败 fixture → `FeedbackClassifier.errorType==='assertion'` 且 `assertion.file:line` 正确；`ScriptedMock` 下一轮返回修正 `write_file` → 循环走到绿。
- **AC4（凭据）**：首运行引导录入 → `status()` 返回 present 且不回显明文 → `clear()` 后不可读；`.env` fallback 触发风险告警。
- **AC5（WebUI/分发）**：`docker run` 后浏览器可访问面板；提交任务后事件流可见；高危动作在浏览器内可审批。
- **AC6（CI）**：`.gitlab-ci.yml` 含 `unit-test` job 且最后一次 CI pass。
- **AC7（机制演示）**：`demo/mechanism-demo.test.ts` 三幕可一键运行复现 §A.6 ①②③。

---

## 10. 风险与未决问题

- **R1**：`shell-quote` 对畸形/极构造命令可能抛错 → 缓解：捕获异常一律判 `high` 强制审批。
- **R2**：Jest 输出格式随版本变化 → 缓解：Parser 接口可插拔，固定演示用 Jest 版本；解析失败降级 `other`。
- **R3**：`HttpApprovalGateway` 挂起 resolver 在进程崩溃时泄漏 → 接受单任务、重启即清。
- **U1**：是否需要 agent 工作区路径围栏？→ 本期决定**不加**（仅命令护栏），评审时若质疑再补。

---

## 11. 领域与机制设计（项目 A 专属，呼应 §A.4 / §A.5）

### 11.1 领域：coding
- **反馈信号**：`npm test` 退出码 + stderr（客观、确定、可回灌）→ `FeedbackClassifier`。
- **危险动作**：递归删除、提权、远程脚本执行、数据销毁、系统写入 → `Guardrail`。
- **所需工具**：读写文件、列目录、跑 shell、跑测试、停机 → `ToolRegistry`。
- **记忆需求**：项目约定/历史决策（轻量）→ `MemoryStore` 文件式最小实现。

### 11.2 重点维度与理由
- **重点 1：治理（Guardrail + ApprovalGateway HITL 状态机）**——天然由代码构成，tokenize + 危险模式库 + severity 分级 + 挂起审批，深入后最能体现工程深度。
- **重点 2：反馈闭环（FeedbackClassifier + 回灌 + 卡死停机）**——确定性校验器 + 失败分类 + 多轮自我修正，契合 §A.4-B"反馈信号=你编写的校验器"。
- 其余四维度（决策/工具/记忆/配置）做"可运行最低实现"，不深入。

### 11.3 机制如何编码实现（呼应 §A.4-B/C）
- 反馈信号 = `FeedbackClassifier.parse(obs)` 确定性函数（非"让 LLM 自查"提示词）；喂 stderr fixture 即可断言。
- 危险动作拦截 = `Guardrail.assess(action)` 确定性函数（非系统提示里一句"注意安全"）；构造 `Action(command='rm -rf /')` 即可断言拦截，每次成立。
- **判定标准**：移除真实 LLM（换 `ScriptedMock`）后，ActionProtocol / ToolRegistry / Guardrail / ApprovalGateway / FeedbackClassifier / MemoryStore / CredentialStore / AgentLoop 仍全部可确定性单测——它们才计入 harness 实现。

### 11.4 机制演示（§A.6，对齐重点维度）
- **幕①**：`Guardrail` 拦截 `rm -rf /` + 混淆变体 → `MockApprovalGateway` 走完 deny（回灌）与 approve（执行）两分支。
- **幕②**：注入 Jest 断言失败 fixture → `FeedbackClassifier` 回灌 → `ScriptedMock` 下一轮改 `write_file` 修正 → 循环走到测试绿。
- **幕③**：重点维度深行为——护栏多混淆绕过案例（`rm -- -rf /`、`$(echo rm) -rf /`、base64 管道）+ severity 高/低分级 + 卡死停机（连续 2 轮同断言点失败 → `HALTED(stuck)`）。
- 形态：`demo/mechanism-demo.test.ts`，`npm run demo` 一键复现，离线。

