# 源仓库审计（Phase 0 / M0）

> 审计对象：`ai4se-safe-tdd-harness`（TypeScript Coding Agent Harness，AI4SE 期末项目 Option A）
> 审计日期：2026-11-23 · 审计分支基线：`main` @ `3512ba4226b513ffc3d72d2a21067700724767e6`（"修改README"）
> 迁移目标：Python 3.12 重写为 **AI4SE SafeFix**（分支 `rewrite/python-safefix`）

## 0. 环境与基线实测记录（真实执行，非虚构）

| 项目 | 实测结果 |
|---|---|
| 当前分支 / commit | `main` @ `3512ba4`，与 `github/main` 同步 |
| Git 工作区 | 干净，仅 `AGENTS.md` 未跟踪；4 个历史 worktree 保留不动 |
| `npm test`（Jest） | **87 suites 全部通过；593 passed / 3 skipped / 596 total**（含 worktree 内重复套件），20.1s；有一条 worker 未优雅退出的告警（测试泄漏定时器，非失败） |
| `npm run build`（tsc + 拷贝静态资源） | **成功**，无编译错误 |
| Node | v24.14.0（仅用于旧代码取证，SafeFix 核心不再依赖） |
| Python | 系统 3.13.5 / 3.11；uv 管理的 **CPython 3.12.13** 可用（重写目标版本） |
| uv | 0.12.3 |
| Docker | CLI 29.6.1 已安装，但 **daemon 未运行**（Docker Desktop 停止，`docker info` 报 npipe 连接失败）→ 沙箱实测受阻，按任务要求以显式错误 + mock 单测覆盖 |
| WSL2 | Ubuntu 发行版已安装（Stopped） |

## 1. 现有功能清单

- **自研 AgentLoop**（`src/loop/agentLoop.ts`）：system prompt + 迭代循环，每轮 LLM 回复 → 解析 action → 护栏评级 → 高危人工审批 → 工具分发 → Observation 回灌；终止原因 `finish | cap | stuck | provider_error | user_abort`。
- **动作协议**（`src/protocol/actionProtocol.ts`）：```` ```action {JSON} ```` 围栏解析，容忍未闭合围栏与畸形块；`stripActionFences` 剥出自然语言"思考"。
- **LLM 层**：`LLMProvider` 接口；`OpenAICompatProvider`（fetch 注入、指数退避 + 半抖动、Retry-After、429/5xx 可重试、4xx AuthError 不可重试、硬超时 AbortController、baseUrl 归一化防 `/v1/v1`）；`ScriptedMock`（脚本队列 + sticky）；`offlineDemo` 离线演示脚本。
- **工具**：`read_file / write_file / list_dir`（工作区路径围栏）、`run_shell / run_tests`（`child_process.exec` 直接宿主机执行，30s/60s 超时，1MB maxBuffer）、`finish`。`ToolRegistry` 统一分发并把异常转 `{ok:false,error}`。
- **护栏 Guardrail**（`src/guardrail/guardrail.ts` + `dangerPatterns.json`）：shell-quote 分词后整词匹配（递归删除、提权、远程脚本管道入 shell、DB 破坏、系统路径写、fork bomb、凭据外传、plain-rm=low）；Windows `del /s`、`rmdir /s`、`Remove-Item -Recurse` 前置匹配；子壳解包递归审计（bash/sh/zsh/dash/powershell/pwsh/cmd/wsl，深度上限 5）；状态感知升级（刚被拒绝后的任何删除尝试 → high）；分词失败强制审批。
- **人工审批**：`ApprovalGateway` 接口 + Mock/CLI/HTTP 三实现；拒绝对话中含显式终止意图（终止/停止/abort/cancel/stop，英文词边界）→ 立即 `user_abort`。
- **测试反馈闭环**：`FeedbackClassifier` + `JestParser`（assertion/syntax/other 三类，提取失败测试名与 `file:line`）；同一失败键连续 2 次 → `stuck` 终止。
- **记忆**：`MemoryStore` 文件型 note（`<dir>/<key>.md`），拼入 system prompt。
- **凭据**：`EncryptedFileStore`（AES-256-GCM + PBKDF2-SHA256 100k 迭代，固定盐 `ai4se-salt`，blob=iv‖tag‖ct）；`resolveCredentials` 纯函数决议（加密文件 > .env > 进程 env）；`JsonConfigStore` 存 baseUrl/model。
- **事件流**：`EventSink`/`EventStore`/`ConsoleSink`，事件类型 thought/action/observation/approval_request/approval_decision/halt。
- **入口与 UI**：CLI（REPL/单次任务/web 三模式）、原生 HTTP Web 面板（`src/web/`，静态前端 + 轮询）、Docker 分发（旧 Dockerfile 基于 Node）。
- **CI**：`.github/workflows/ci.yml` 与 `.gitlab-ci.yml`（含字面 `unit-test` job）。

## 2. 实际架构与执行流

```
CLI/Web 入口 (index.ts)
  → resolveCredentials（creds.enc → .env → env；全无则静默降级 ScriptedMock）
  → AgentLoop.run()
      每轮: llm.complete(messages)
        → ActionProtocol.parse（取首个 action，多块告警回灌）
        → finish? 终止
        → Guardrail.assess(action, session)
            high → approval_request 事件 → ApprovalGateway.request
                   deny+终止意图 → user_abort；deny → DENIED 回灌
            low  → WARN 回灌
        → ToolRegistry.dispatch（宿主机直接执行）
        → run_tests 失败 → FeedbackClassifier.parse → JSON 回灌
                          同键连续 2 次 → stuck
      迭代上限 → cap
```

依赖注入良好（LLM/审批/事件 sink 均可注入 mock），全部核心机制离线可测——这是最值得保留的架构资产。

## 3. 值得保留的特性（迁移 parity 清单）

1. 围栏动作协议 + 未闭合围栏容错 + 畸形块跳过（`protocol.py`）。
2. AgentLoop 的终止语义五态与事件流（扩展为显式状态机 + 预算 + 取消）。
3. 护栏的分词整词匹配、子壳解包、Windows 规则、deny 升级、tokenize 失败强制审批（`security/policy.py`）。
4. 审批终止意图硬约束（中英文关键词 + 英文词边界）。
5. Provider 的重试/退避/Retry-After/AuthError 语义、baseUrl 归一化、observation→user 角色降级。
6. ScriptedMock 队列 + sticky + 耗尽抛错。
7. 反馈分类器"解析失败兜底 + evidence 截断"结构（升级为多 parser + 六类错误）。
8. 文件工具的工作区路径围栏（升级为 resolve + symlink 检查）。
9. 加密凭据存储与纯函数凭据决议（升级为随机盐；real 模式缺 key 显式报错，**不再静默降级 mock**）。
10. 文件型 MemoryStore（保持简单，不引向量库）。

## 4. Bug 与安全风险（重写必须修复）

| # | 风险 | 位置 | 重写对策 |
|---|---|---|---|
| R1 | **模型生成的 shell 命令直接在宿主机执行**（`child_process.exec`），护栏只是正则/分词启发式，非安全边界 | `shellTools.ts` | 执行后端抽象；默认 Docker 沙箱（非 root、cap-drop、no-new-privileges、无网络、资源限额）；Docker 不可用 → 显式错误，绝不静默宿主执行 |
| R2 | 文件工具路径围栏用字符串前缀比较，**未解析 symlink**，可经符号链接逃逸 | `fileTools.ts abs()` | `Path.resolve()` + symlink 逐段检查 + 输出截断 |
| R3 | 无有效凭据时**静默降级 ScriptedMock**，真实任务可能被误报为演示成功 | `index.ts makeLoopFactory` | real/mock/demo 三模式显式分离；real 缺 key 抛显式错误 |
| R4 | 同一失败出现 2 次即判 `stuck`，过于激进（同错≠不可修复） | `agentLoop.ts` | 有界重试策略：结合同错次数（可配，默认 3）、实际进展与预算 |
| R5 | 反馈仅 Jest 一类 parser、三类错误，无 timeout/infra 区分 | `feedback/` | parser 抽象：pytest / Jest / unknown 兜底；六类分类 |
| R6 | 加密存储**固定盐**、无版本头 | `credentialStore.ts` | 随机盐 + 版本化 blob（`SFX1` 魔数），AES-256-GCM 保留 |
| R7 | 无 Git patch 管理：整文件覆写、无 diff 产出、无独立验证 | `write_file` | `apply_patch` 最小补丁 + `git_status/git_diff` + 独立 verifier |
| R8 | 无任务级评估/预算（仅 maxIter=20 硬编码） | 全局 | 预算对象（LLM 调用数/步数/墙钟/token/成本）+ 评估 runner |
| R9 | 真实 LLM 集成断言弱（`test/integration/real-llm.test.ts` 仅冒烟） | test/ | 集成测试显式标记 skip/NOT RUN，不冒充真实结果 |
| R10 | Jest worker 泄漏定时器（测试告警） | test/ | Python 侧 asyncio 资源显式清理 |

## 5. 缺失能力（SafeFix 新增）

- 目标仓库装载（本地路径 / Git URL）+ base commit 记录 + 一次性隔离工作区（原仓库零改动）。
- `list_files / search_code / apply_patch / git_status / git_diff` 结构化工具与 Pydantic 参数校验。
- 独立成功验证（复现测试由红转绿、回归通过、禁止改测试、空补丁拒绝）。
- 可复现基准套件（≥5 个真实缺陷 fixture）+ JSON/CSV/Markdown 报告 + A/B/C 基线对比。
- Typer/Rich CLI（`demo / fix / eval / report / ui`）与可选 Streamlit UI。
- 中文学习文档与面试问答（`docs/learning/`）。

## 6. TypeScript → Python 迁移映射

| TS 模块 | Python 目标 | 说明 |
|---|---|---|
| `src/types.ts` | `safefix/models.py` | Pydantic v2 模型：Message/Action/Observation/Feedback/Approval*/TaskResult/ExecutionEvent |
| `src/protocol/actionProtocol.ts` | `safefix/agent/protocol.py` | 正则等价移植（`re.DOTALL` 非贪婪 + `(?:```\|$)`） |
| `src/loop/agentLoop.ts` | `safefix/agent/loop.py` + `state.py` | 显式状态机 + 预算 + 取消（asyncio） |
| `src/loop/eventSink.ts` | `safefix/agent/events.py` | EventSink 协议 + 内存/JSONL sink |
| `src/llm/provider.ts` | `safefix/llm/base.py` | Protocol + LLMResponse（含 usage） |
| `src/llm/openaiCompat.ts` | `safefix/llm/openai_compatible.py` | httpx.AsyncClient 注入；原生 tool calling + 围栏 fallback |
| `src/llm/scriptedMock.ts` | `safefix/llm/mock.py` | 队列/sticky/耗尽抛错 parity |
| `src/tools/tool.ts` | `safefix/tools/registry.py` | 分发 + Pydantic 参数校验，未知工具/畸形参数拒绝执行 |
| `src/tools/fileTools.ts` | `safefix/tools/files.py` | read_file/list_files/search_code，resolve+symlink 围栏 |
| `src/tools/shellTools.ts` | `safefix/tools/tests.py` + `runtime/executor.py` | run_tests 走执行后端（Docker），不再直接 exec |
| （新增） | `safefix/tools/patch.py` / `git.py` | apply_patch（unified diff）/ git_status / git_diff |
| `src/guardrail/*` | `safefix/security/policy.py` | shlex 分词 + 同等规则集；明确"纵深防御而非边界" |
| `src/approval/*` | `safefix/security/approval.py` | 协议 + Mock/CLI/Auto 实现 |
| `src/feedback/*` | `safefix/feedback/{classifier,pytest_parser,jest_parser}.py` | 六类错误 + 兜底 |
| `src/memory/memoryStore.ts` | `safefix/memory/store.py` | 文件型 note parity |
| `src/creds/*` | `safefix/creds/{store,resolver}.py` | cryptography AESGCM + PBKDF2HMAC；随机盐 |
| `src/index.ts buildSystemPrompt` | `safefix/agent/prompt.py` | 工具协议提示（含防注入声明） |
| `src/cli/*` + `src/web/*` | `safefix/cli.py`（Typer/Rich）+ 可选 Streamlit | 旧 Web 面板不迁移（JS 前端不再维护） |
| Jest 测试 | `tests/unit|integration|e2e`（pytest） | 行为 parity 见 §7 |

## 7. 行为 parity 所需测试（pytest）

- **协议**：单/多 action 块、未闭合围栏、畸形 JSON 跳过、未知工具名拒绝、strip 围栏。
- **循环**：finish/cap/provider_error/user_abort/stuck 终止；deny 回灌；low WARN 回灌；多 action 告警；无 action 提示；迭代上限；取消；预算耗尽。
- **护栏**：`rm -rf`、`sudo`、`curl|sh`、Windows `del /s`、子壳 `bash -c "rm -rf /"`、deny 后删除升级、分词失败强制审批、`echo curly`/`echo issue` 不误报。
- **审批**：Mock 队列耗尽默认 deny；终止意图中英文 + 词边界（stopped 不误判）。
- **Provider**：429/5xx 重试与退避、Retry-After、4xx AuthError 不重试、baseUrl 归一化四写法、observation 角色降级、超时、usage 记录。
- **Mock**：队列顺序、sticky、耗尽抛错。
- **反馈**：pytest assertion/syntax/timeout/infra 分类、Jest parity、未知输出兜底、evidence 截断、exit 0 → pass。
- **凭据**：加解密往返、错密码拒绝、clear/status、决议优先级（加密 > env-file > env）、real 模式缺 key 显式错误。
- **工具**：路径逃逸/symlink 拒绝、输出截断、未知工具、参数校验、apply_patch 最小修改、git diff 产出。
- **记忆**：read/write/clear/systemPrompt 拼接、目录不存在为空。

## 8. 结论

旧代码是**行为参考**而非必须照抄的设计：依赖注入与离线可测性保留；宿主直接执行、静默 mock 降级、整文件覆写、激进 stuck 判定必须替换。迁移在 `rewrite/python-safefix` 分支增量进行，旧代码经 Git 历史与本审计长期可查，M1 parity 完成前不删除任何旧文件。