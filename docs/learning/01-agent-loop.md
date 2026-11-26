# 01 · AgentLoop：为什么需要一个主循环

## 解决什么问题

LLM 一次回复不能修好 bug：它需要"看代码 → 改一点 → 跑测试 → 看失败 → 再改"。
AgentLoop 就是这个**多轮决策的调度器**，同时保证它不会失控（预算、审批、终止）。

## 它怎么工作

文件：`src/safefix/agent/loop.py`（类 `AgentLoop`，入口 `run()`）。
状态定义：`src/safefix/agent/state.py`（`TaskState` / `HaltReason` / `Budgets`）。

每轮做 6 件事：

1. **检查边界**：取消事件？LLM 调用数到上限？墙钟/token 超预算？→ 终止。
2. **问模型**：`await deps.llm.complete(messages)`，异常 → `provider_error` 终止。
3. **解析动作**：原生 `tool_calls` 优先，否则 `parse_actions(text)` 解析围栏块；
   没有动作 → 回灌提示让它重发；多个动作 → 只执行第一个并告警。
4. **治理**：`policy.assess(action, session)` → high 走审批；deny 且含终止意图
   （`has_abort_intent`）→ `user_abort`；普通 deny → DENIED 回灌。
5. **执行**：`registry.dispatch(action, ctx)`（参数先过 Pydantic 严格校验）。
6. **反馈**：`run_tests` 失败 → `FeedbackClassifier` 结构化回灌；同一失败键
   连续 ≥3 次 → `stuck`；`apply_patch` 成功会**重置**失败计数（有进展就不算卡死）。

终止原因共 7 种：`finish / cap / stuck / provider_error / user_abort /
budget_exceeded / cancelled`。注意 `finish` 只是模型"声称完成"，
真正成功由 `repair/verifier.py` 判定。

## 逐步执行轨迹（demo 实测）

```
用户提交任务 → cli.demo 组装 LoopDeps
→ AgentLoop.run 注入 system prompt（含记忆 note）
→ iter1: ScriptedMock 返回 run_tests → 沙箱/模拟执行 → 失败反馈回灌
→ iter2: 模型尝试 "rm -rf /" → policy=high → AutoDeny → DENIED 回灌
→ iter3: read_file shop/paginate.py → 内容回灌
→ iter4: apply_patch（最小 diff）→ 成功 → 失败计数清零
→ iter5: run_tests → 通过
→ iter6: finish → halt(finish) → verifier 判定 verified
```

对应事件全部写入 `events.jsonl`（`agent/events.py:JsonlSink`）。

## 涉及的 Python 概念

- `async/await`：循环是协程，LLM/执行/审批都不阻塞事件循环。
- `dataclass`（`LoopDeps`）：依赖注入容器，测试时换成 mock 即可。
- `StrEnum`：终止原因是枚举，比较/序列化都安全。
- `asyncio.Event`：协作式取消（每轮开头检查）。

## 常见失败场景

| 现象 | 原因 | 去哪看 |
|---|---|---|
| halt=provider_error | mock 队列耗尽 / 真实端点 4xx | `llm/mock.py`、`llm/openai_compatible.py` |
| halt=stuck | 同一失败重复 3 次且无补丁进展 | `loop.py` 的 `same_count` 逻辑 |
| halt=cap | 调用数到 `max_llm_calls` | `state.py:Budgets` |
| 一直"no action block" | 模型没按协议输出 | `agent/protocol.py` 正则 |

## 如何修改与测试

例：把默认同错阈值改成 5 —— 改 `Budgets.max_same_failure` 默认值，然后：

```bash
uv run pytest tests/unit/test_agent_loop.py -k stuck
```

先改测试期望（TDD：红），再改实现（绿）。新增终止原因时，记得同时更新
`HaltReason`、`loop.py` 分支与 `tests/unit/test_agent_loop.py`。