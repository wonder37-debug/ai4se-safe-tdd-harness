# SafeFix 评估方法

## 数据集

`benchmarks/suite.yaml`（safefix-python-v1）：5 个 Python/pytest 任务，全部为
**自研 fixture 复现的常见缺陷类**（off-by-one、输入校验、边界处理、数据处理），
MIT 许可，**不是外部项目的 CVE**。每个任务含：

- `repo/`：带 bug 的项目 + agent 可见测试；
- `eval/`：独立评估测试（生成期对 agent 不可见）；
- `task.yaml`：issue 文本、复现/测试命令、预算、缺陷类、许可。

base commit SHA 在每次运行时物化 fixture 后记录于 `outcome.json`
（fixture 以 `git init + commit` 物化，SHA 随物化确定，可复现缺陷内容）。

## 基线（A/B/C）

| 变体 | 含义 | 实现差异 |
|---|---|---|
| A-single-shot | 单发补丁，无迭代反馈 | `max_llm_calls=1, max_steps=1` |
| B-basic-loop | 基础循环 + 测试反馈 | 工具集缩减为 read_file/apply_patch/run_tests |
| C-safefix | 完整 SafeFix | 全工具集 + 沙箱 + 独立验证 |

三者共享同一执行后端与验证器（比较的是循环/工具能力，不是安全网）；
模型、数据集、环境、预算保持可比。

## 指标

`evaluation/metrics.py`：resolved/verified 数、复现成功率、补丁生成率、
验证修复率、平均 LLM 调用数、token 总量、平均耗时、失败类别分布
（not_reproducible / empty_patch / test_tampering / stuck / budget_exhausted /
provider_error / aborted / verification_failed）、审批拒绝次数。

输出：`results.json`（逐运行）+ `summary.csv` + `report.md`。

## 已执行的真实结果（诚实记录）

1. **单元/集成测试**：Windows 219 passed + 2 skipped（symlink 权限 / real-LLM 门控）；
   WSL2 Linux 212 passed + 0 skipped；8 个真实 Docker 沙箱集成通过。
2. **MOCK 管线验证**（`benchmarks/results/mock-pipeline-validation/`）：
   `examples/run_mock_suite.py`，5 任务 × A/B/C = 15 运行全部 verified。
   **这是脚本化 provider 的管线验证，不是模型修复能力证据。**
3. **真实模型评估（qwen3.8-flash，已执行）**：
   `benchmarks/results/real-qwen38-flash/`（与 MOCK 目录/报告分离）。
   预算 ≤12 调用/任务、≤300s；同模型/同沙箱/同验证器；逐运行记录
   model/endpoint_host/code_commit/outcome/events/patch。

   | 变体 | verified | 平均调用 | 失败类别 |
   |---|---|---|---|
   | A-single-shot | 0/5 | 1 | empty_patch ×5 |
   | B-basic-loop | 5/5 | 8.4 | — |
   | C-safefix | 5/5 | 7.6 | — |

   15 运行总 token 85,785。观察：迭代反馈决定性优于单发；C 平均调用略低于 B。
   另有 3 次独立真实修复 verified（paginate ×2、held-out querystring ×1），
   见 `docs/verification/real-llm-validation.md` 与 `docs/verification/evidence/`。

## 局限与混杂因素

- 样本极小（5 任务），**不做任何统计显著性声明**。
- fixture 缺陷简单且局部；不能外推到大型真实仓库。
- A/B/C 在 mock 下全部成功，说明该套件对"已知正确补丁"无区分度；
  真实模型下 A 0/5 与 B/C 5/5 的差异是观察性结论。
- 运行间差异：LLM 采样温度 0 仍可能有非确定性；容器启动耗时波动。
- 成本估算未实现（定价表未内置）；token 用量已记录。