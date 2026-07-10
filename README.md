# AI4SE-Safe-TDD-Harness

一个自研的 Coding Agent Harness（Node.js / TypeScript）：手写 agent 主循环 + 可注入 Mock 的 LLM 层、shell 命令护栏 + 人工审批（HITL）、结构化 TDD 反馈闭环。移除真实 LLM（换 `ScriptedMock`）后内核仍可确定性单测——把"治理 / 反馈 / 安全 / 分发"这些工程纪律落实为可单测的代码机制。

## 功能概览

- **自研主循环** `AgentLoop`：`RUNNING → APPROVAL_PENDING → EXECUTING → HALTED` 手写状态机，编排 LLM / 工具 / 护栏 / 审批 / 反馈。
- **治理维度 1 — Guardrail**：`shell-quote` token 层匹配危险模式库，揭穿 `r""m`/引号混淆；`high` 触发 HITL，`low` 告警，`none` 直行。
- **反馈维度 2 — FeedbackClassifier**：Jest 失败 stderr 解析为 `assertion`/`syntax`/`other`，回灌 `file:line` + `hint`，连续 2 轮同一断言点失败 → `HALTED(stuck)`。
- **凭据治理** `EncryptedFileStore`：AES-256-GCM 加密落盘，`status()` 不回显明文。
- **最小 Web 面板**：Node `http` 轮询（非 WS），浏览器内提交任务 + 实时事件流 + HITL 审批。
- **Docker 分发**：`docker run -p 8080:8080` 一条命令起面板。

## 获取

```bash
git clone https://git.nju.edu.cn/241880540/ai4se-safe-tdd-harness.git
cd ai4se-safe-tdd-harness
```

## 运行（Docker，推荐用于部署评审）

```bash
docker build -t ai4se-safe-tdd-harness .
docker run -p 8080:8080 \
  -e MASTER_PASSWORD=<你的主密码> \
  -e API_BASE_URL=<OpenAI 兼容端点> \
  -e MODEL=<可选模型名> \
  -v "$PWD/workspace":/workspace \
  ai4se-safe-tdd-harness
```

打开 http://localhost:8080 。容器启动即起 web 面板（`CMD` 已带 `--web`）。在面板左侧「凭据」区录入 `CLAUDE_API_KEY` + 主密码保存（AES-256-GCM 加密落盘），随后提交任务即可。

> 目标平台 Linux/amd64；Windows / macOS 需本地 `docker build`。

## 本地开发

```bash
npm ci
npm test          # 全部单元测试（无网络，含 mock LLM 闭环）
npm run demo      # §A.6 机制演示三幕
npm run build && node dist/index.js --web   # 起本地面板
```

`npm test` 与 `npm run demo` 均在无网络、无真实 LLM 下确定性通过——这是内核"移除 LLM 后仍可单测"的硬标准（SPEC §4.4 / §11.3）。

## 凭据安全配置指南

**威胁模型与对策**（详见 SPEC §4.2）：

| 威胁 | 路径 | 对策 |
|---|---|---|
| Git 提交泄露 | `.env` / 配置进仓 | `.gitignore` 排除 `.env`、`~/.ai4se/`；提交前自查；CI secret-detection |
| Shell history | `export KEY=` / `-e KEY=` | 一律走加密文件或 `MASTER_PASSWORD` 环境变量；禁止命令行明文传 key |
| 进程环境可见 | `env` 可读 | 加密文件优先；`.env` 仅 fallback 并告警；运行时不打印 key |
| 磁盘明文 | `.env` 落盘 | 主路径用 AES-256-GCM 加密文件 `~/.ai4se/creds.enc` |
| 拦截绕过 | `r""m` / base64 管道 | `shell-quote` token 层匹配，揭穿引号 / 转义混淆 |
| 凭据外传 | `curl -H Authorization` | 危险模式库含"带 Authorization 的外发请求"模式 |

**操作要点：**

1. **绝不**在命令行明文传递 key（会进 shell history）。容器内主密码经 `MASTER_PASSWORD` 环境变量传入。
2. 浏览器 `POST /api/key` 录入 → AES-256-GCM 加密落盘 `~/.ai4se/creds.enc`，由主密码解锁；运行时 `resolve()` 仅在内存解密。
3. `GET /api/key/status` 只返回 `{present, source}`，**绝不回显**明文 key。
4. `.env` 仅作明文 fallback（带告警）；生产优先用加密文件。
5. `.env` 已被 gitignore 且必须保持未跟踪；每次提交前自查仓库内无真实凭据。

## 架构与数据流

```
AgentLoop (自研主循环)
  RUNNING → [Guardrail.assess] → APPROVAL_PENDING → EXECUTING
                                       │                 │
                            [observation 回灌]   ToolRegistry.dispatch
  └─ LLMProvider(OpenAICompat / ScriptedMock)
     └─ CredentialStore(EncryptedFileStore) ── MemoryStore
        └─ HttpApprovalGateway ── WebServer(http 轮询) ── 静态前端
```

一轮迭代：组装 messages → `LLMProvider.complete` → `ActionProtocol.parse` → `Guardrail.assess`（high→HITL）→ `ToolRegistry.dispatch` → 若 `run_tests` 失败则 `FeedbackClassifier.parse` 回灌 → `finish`/上限/卡死 → `HALTED`。全程事件入队列供 `GET /api/events` 轮询。

## 已知限制

- 主目标平台 Linux/amd64；Windows / macOS 需本地构建。
- 单任务，不并发（2 周裁剪，SPEC §3.10）。
- HTTP 轮询而非 WebSocket；`FeedbackClassifier` 稳健识别 Jest 的 `assertion`/`syntax`，其它 runner 回退 `other`。
- `OpenAICompatProvider` 仅适配单 OpenAI-compatible 供应商（`/v1/chat/completions`），不做多供应商适配。

## CI

`.gitlab-ci.yml` 定义了 `unit-test` job（`npm ci && npm test`）。机制演示见 `demo/mechanism-demo.test.ts`（`npm run demo`）。

## 许可

MIT
