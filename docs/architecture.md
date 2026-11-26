# SafeFix 架构

> 代码根：`src/safefix/`。所有核心机制都是自研确定性函数，可用 ScriptedMock
> 在无网络条件下独立验证（继承原 TS harness 的"机制即代码"原则）。

## 模块划分

| 模块 | 职责 | 关键符号 |
|---|---|---|
| `models.py` | Pydantic 领域模型 | `Action / ToolCall / Observation / Feedback / ApprovalDecision / ExecutionEvent / TokenUsage` |
| `config.py` | 模式分离与 provider 工厂 | `Mode(real/mock/demo) / build_provider / load_env_file` |
| `agent/protocol.py` | 围栏动作协议 | `parse_actions / strip_action_fences / TOOL_NAMES` |
| `agent/loop.py` | AgentLoop 状态机 | `AgentLoop.run / LoopDeps` |
| `agent/state.py` | 状态/终止/预算 | `TaskState / HaltReason / Budgets / LoopResult` |
| `agent/events.py` | 事件流 | `EventLog / JsonlSink / FanOutSink` |
| `agent/prompt.py` | 系统提示（含防注入声明） | `build_system_prompt` |
| `llm/base.py` | Provider 契约 | `LLMProvider(Protocol) / LLMResponse` |
| `llm/openai_compatible.py` | 真实端点 | `OpenAICompatProvider / normalize_base_url / adapt_messages` |
| `llm/mock.py` / `llm/demo.py` | 确定性脚本 | `ScriptedMock / demo_responses` |
| `tools/registry.py` | 分发 + 严格参数校验 | `ToolRegistry.dispatch / schemas / ToolContext` |
| `tools/files.py` | 文件工具（symlink 围栏） | `ReadFileTool / ListFilesTool / SearchCodeTool / _fence` |
| `tools/patch.py` | 纯 Python unified-diff | `ApplyPatchTool / _parse / _render` |
| `tools/git.py` | 固定 argv git 调用 | `GitStatusTool / GitDiffTool / _git` |
| `tools/tests.py` | run_tests → 执行后端 | `RunTestsTool` |
| `runtime/executor.py` | 执行后端契约 | `ExecutionBackend / ExecResult / SandboxUnavailableError` |
| `runtime/docker_executor.py` | 强制沙箱 | `DockerExecutor / SandboxLimits / run_trusted_prep` |
| `runtime/workspace.py` | 一次性工作区 | `prepare_workspace / cleanup_workspace / Workspace` |
| `runtime/demo_executor.py` | 演示模拟（零进程） | `DemoExecutor` |
| `runtime/local_executor.py` | 仅 mock 管线（可信命令） | `LocalTrustedExecutor` |
| `security/policy.py` | 护栏（纵深防御） | `assess / _tokenize / _assess_tokens` |
| `security/approval.py` | 审批网关 | `MockApprovalGateway / AutoApprove/AutoDeny / has_abort_intent` |
| `security/cli_approval.py` | 终端 HITL | `CliApprovalGateway` |
| `feedback/` | 测试输出分类 | `FeedbackClassifier / PytestParser / JestParser` |
| `memory/store.py` | 文件型任务记忆 | `MemoryStore` |
| `creds/` | 加密凭据 | `EncryptedFileStore / resolve_credentials` |
| `repair/workflow.py` | 产品工作流 | `RepairTask / run_repair / RepairOutcome` |
| `repair/verifier.py` | 独立验证 | `verify_patch / VerificationReport` |
| `evaluation/` | 基准评估 | `run_suite / Variant / summarize / reporter / fixtures` |
| `cli.py` / `ui_app.py` | Typer CLI / 可选 Streamlit | `app` |

## 一次真实修复的执行流

```
用户: safefix fix --repo R --issue "..." --mode real
→ cli.fix 解析参数；build_provider(real) 决议凭据（缺则显式报错）
→ run_repair:
   prepare_workspace(R) → git clone --local --no-hardlinks → 记录 base_commit
   [可信准备] executor.run_trusted_prep(setup)（受控网络，命令来自人写的配置）
   [复现] executor.run(repro_command) → ExecSummary（失败证据）
   AgentLoop.run:
     每轮: 预算/取消检查 → llm.complete(messages)
       → 原生 tool_calls 或 parse_actions(text)
       → finish? 终止（仅声明）
       → policy.assess(action, session)
           high → approval_request 事件 → 审批网关
                  deny+终止意图 → user_abort；deny → DENIED 回灌
           low → WARN 回灌
       → ToolRegistry.dispatch（Pydantic strict 校验）
           run_tests → DockerExecutor.run（--network none ...）
       → run_tests 失败 → FeedbackClassifier → 结构化反馈回灌
           同键连续 ≥ max_same_failure(3) 且无进展 → stuck
           apply_patch 成功 → 重置失败计数（进展感知）
   git diff → patch.diff
   verify_patch: patch_nonempty / tests_untouched / repro_passes /
                 regression_passes / eval_passes（独立测试，生成期不可见）
   status = verified 当且仅当 全部通过 ∧ 初始可复现 ∧ 补丁非空
   outcome.json + events.jsonl 落盘 → cleanup_workspace
```

## 设计决策

1. **不用现成 Agent 框架**：循环/治理/反馈/终止全部自研（课程要求与可解释性）。
2. **asyncio 全异步**：provider、执行器、审批均 async；取消用 `asyncio.Event`。
3. **双通道工具调用**：原生 function calling 优先，围栏协议兜底——不假设所有
   OpenAI 兼容端点支持相同特性。
4. **验证器与生成器分离**：eval 测试存放在 fixture 的 `eval/`，生成期绝不进入
   工作区；验证在 agent 终止后执行。
5. **简单记忆**：文件型 note + 任务内对话历史 + 上下文截断；不引向量库/RAG。
6. **预算对象化**：`Budgets` 统一约束调用数/步数/墙钟/token/同错重试。