# 简历素材（仅可验证事实）

> 每条均链接到源码 / 测试 / 可复现演示。未实现的能力不在此列出。
> 注意：本项目由 AI 辅助完成迁移实现；面试表述应聚焦"理解、验证与扩展能力"，
> 不虚构手写经历。

## 可验证条目

1. **自研 Coding Agent 内核（Python 3.12，无高层 Agent 框架）**
   - 源码：`src/safefix/agent/loop.py`（状态机 + 预算 + 取消 + 进展感知重试）
   - 测试：`tests/unit/test_agent_loop.py`（16 个终止/审批/预算/取消用例）
   - 演示：`uv run safefix demo`（离线、确定性）

2. **可强制执行的 Docker 沙箱执行后端**
   - 源码：`src/safefix/runtime/docker_executor.py`（非 root/cap-drop/无网络/限额）
   - 测试：`tests/unit/test_docker_executor.py`（离线契约）+
     `tests/integration/test_docker_sandbox.py`（7 个真实容器断言，实测通过）
   - 演示：`uv run pytest tests/integration/test_docker_sandbox.py -v`

3. **独立验证的 bug 修复工作流（原仓库零改动）**
   - 源码：`src/safefix/repair/workflow.py` + `verifier.py`
   - 测试：`tests/unit/test_workflow.py`（verified/空补丁拒绝/改测试拒绝）+
     `tests/integration/test_sandboxed_repair.py`（沙箱内完整修复，实测 50.1s 通过）
   - 证据：运行产出 `outcome.json / patch.diff / events.jsonl`

4. **测试反馈闭环与六类错误分类**
   - 源码：`src/safefix/feedback/`
   - 测试：`tests/unit/test_feedback.py`（pytest/Jest/兜底/截断/timeout）

5. **OpenAI 兼容 Provider 的工程化重试语义**
   - 源码：`src/safefix/llm/openai_compatible.py`
   - 测试：`tests/unit/test_openai_provider.py`（12 用例：退避范围/Retry-After/
     AuthError 不重试/原生 tool calling/usage）

6. **加密凭据存储（AES-256-GCM + PBKDF2，随机盐）**
   - 源码：`src/safefix/creds/store.py`
   - 测试：`tests/unit/test_creds.py`（含"明文不落盘"断言）

7. **可复现评估管线（A/B/C 基线，JSON/CSV/MD 报告）**
   - 源码：`src/safefix/evaluation/`
   - 证据：`benchmarks/results/mock-pipeline-validation/`（15 运行，**标注 MOCK**）
   - 测试：`tests/unit/test_evaluation.py`

8. **206 个离线单元测试，覆盖率 89%（ui_app 除外），ruff 全绿**
   - 复现：`uv run pytest tests/unit --cov=safefix`

## 不可声明的事项（截至当前）

- 真实 LLM 修复成功率（NOT RUN，无凭据）。
- 外部真实项目 CVE 修复（fixture 为自研缺陷复现）。
- 统计显著性改进（样本 5 任务）。