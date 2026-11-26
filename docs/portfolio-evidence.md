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

## 公开开源项目复验

```bash
uv sync --frozen
uv run python examples/replay_more_itertools.py
uv run safefix report .safefix-runs/more-itertools-1304
```

这个示例会下载固定版本的 more-itertools，并在本机运行它的 pytest 测试。样例源于 [issue #1304](https://github.com/more-itertools/more-itertools/issues/1304)，基准固定为 `790bb0bb2c03e7a07282e5f16f4b1fde35b8fcf5`。在临时克隆中提交两个复现用例后，脚本模型提出 [上游已发布的实现补丁](https://github.com/more-itertools/more-itertools/pull/1305)。SafeFix 导出补丁，在独立副本上用 Git 重新应用，再执行复现、项目测试与额外行为检查。

实测基线有 2 个失败，重放后复现用例 2 个通过，全项目 768 个测试、21,202 个 subtest 通过，额外行为检查 2 个通过。

此案例使用脚本模型和真实 pytest，验证的是补丁交付与复验流程。真实模型验收和小样本 A/B/C 结果是此前在 SafeFix 自建样例上的独立证据。

## 开源与岗位调研应用（2026-11-26）

Star 数为当日 GitHub 查询快照，按项目四舍五入。

| 项目 | Star 约数 | 适合学什么 |
| --- | ---: | --- |
| [OpenCode](https://github.com/anomalyco/opencode) | 229k | [CLI](https://opencode.ai/docs/cli/) 支持项目目录和非交互入口，SafeFix 默认接受当前仓库，继续支持显式路径与 Git URL |
| [OpenHands](https://github.com/OpenHands/OpenHands) | 94k | [评测仓库](https://github.com/OpenHands/benchmarks) 将评测任务放在独立设施中，SafeFix 先做好固定基准和独立复验 |
| [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) | 81k | 前两课把工具分发放在可手读的小循环里，可对照 SafeFix 的 AgentLoop 与 ToolRegistry |
| [Aider](https://github.com/Aider-AI/aider) | 50k | [测试反馈](https://aider.chat/docs/usage/lint-test.html) 与 [仓库结构摘要](https://aider.chat/docs/repomap.html) 可用于减少盲目尝试，先验证收益再扩大上下文 |
| [LangGraph](https://github.com/langchain-ai/langgraph) | 45k | 适合学习持久化与人工介入，SafeFix 的课程目标适合继续保留自有循环 |
| [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) | 10k | [轨迹文件](https://mini-swe-agent.com/latest/usage/output_files/)同存模型调用、动作和结果，SafeFix 已有 trace 与 report，可用两者串起证据 |

小红书的 [Coding Agent 实习](https://job.xiaohongshu.com/campus/intern/position/19021) 明确关注 loop、上下文、依赖和真实测试闭环，[Agent 工程岗位](https://job.xiaohongshu.com/campus/intern/position/22526) 还列出结构化输出、工具调用与回归评测。[百度代码智能相关实习](https://talent.baidu.com/jobs/detail/INTERN/e3cec5b8-b7a3-4946-99fc-b292b749cd53) 加上工程基础、Python/Java/Go、代码分析与应用框架经验。字节的 [Agent 开发岗位转载](https://jobs.ultraai.site/jobs/bytedance_campus/7701627607725394229) 强调 Benchmark 和问题归因。[OpenAI 的 Codex 岗位](https://openai.com/careers/applied-ai-engineer-codex-core-agent-san-francisco/) 是偏资深的工程参考，关注任务解决率、工具策略、性能与线上失败分析。

[牛客面经](https://www.nowcoder.com/discuss/940040254214389760) 的个人分享涉及模型与 Harness 的分工、工具调用细节、基准数据质量与个人贡献。[Anthropic 的评估实践](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) 用环境中的最终结果验收，[Hamel Husain 和 Shreya Shankar 的工程博客](https://hamel.dev/blog/posts/evals-faq/why-is-error-analysis-so-important-in-llm-evals-and-how-is-it-performed.html) 建议从轨迹中的第一处失败入手归因。SafeFix 据此把测试环境错误提前暴露，把成功判定落在实际交付补丁上。

### 简历建议表述

- 使用 Python 实现面向 Git 仓库的测试驱动代码修复 Agent，串联结构化工具调用、Docker 测试执行与 pytest 反馈，输出补丁和运行轨迹。
- 将基线用例失败与测试环境错误分开处理，在独立 Git 副本重放交付补丁并复验，使用 more-itertools 公开历史缺陷验证交付流程。
