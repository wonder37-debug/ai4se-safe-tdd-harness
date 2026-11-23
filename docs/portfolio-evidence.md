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

8. **Windows 离线单元测试 247 通过、6 跳过（symlink/mkfifo 权限），覆盖率 88%，ruff 全绿**
   - 复现：`uv run pytest tests/unit --cov=safefix`

9. **真实模型（qwen3.8-flash）独立验证的自动修复 ×3**
   - 证据：`docs/verification/evidence/real-fix-*-outcome.json` + `*.patch`
   - 含 held-out 缺陷 querystring（不在任何脚本答案中）；每次均复现转绿 +
     回归 + 独立 eval + 测试未篡改 + 原仓库零改动
   - 复现：`uv run safefix fix --repo ... --mode real`（需凭据）

10. **真实 A/B/C 基准（修正方法学 v2）：A 2/5 · B 5/5 · C 5/5（92,959 tokens，预算受控）**
    - 证据：`benchmarks/results/real-qwen38-flash-v2/`（JSON/CSV/MD，与 MOCK 分离）
    - A 组预置源码+复现证据，与 B/C 信息对等；v1（A 0/5）因方法学缺陷仅作历史存档
    - 复现：`uv run safefix eval --suite benchmarks/suite.yaml --mode real --variants A,B,C`

11. **验证中发现并修复 4+24 个工程缺陷**（迁移期 4 个 + PR review 五轮 24 条，
    含 .git 元数据注入、symlink 泄漏、配置伪造 verified、容器残留、宿主内存耗尽、
    灾难正则挂死、非 ASCII 路径转义绕过防篡改、二进制补丁不可应用等），
    均有回归测试——见 docs/verification/review-fixes.md

12. **真实 LLM 验收测试强制 verified**（paginate + held-out querystring，2 passed）
    - 复现：`SAFEFIX_REAL_LLM=1 uv run pytest tests/integration/test_real_llm.py`

## 不可声明的事项（截至当前）

- 一般性 bug 修复能力（样本 5+1 个极小任务，观察性结论，无统计显著性）。
- 外部真实项目 CVE 修复（fixture 为自研缺陷复现）。
- 美元成本数字（token 已记录，定价表未内置）。
