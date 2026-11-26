# 07 · 评估：怎么证明它有用（而不只是演示成功）

## 解决什么问题

一次 demo 成功 ≠ 有 bug 修复能力。需要**可复现的任务套件 + 基线对比 +
诚实的指标**。

## 套件结构

`benchmarks/suite.yaml` 列 5 个任务；每个 fixture（`benchmarks/fixtures/<name>/`）：

```
repo/       带 bug 的项目 + agent 可见测试
eval/       独立评估测试（生成期不可见）
task.yaml   issue / 复现命令 / 测试命令 / 预算 / 许可 / 缺陷类
```

`evaluation/fixtures.py:materialize_fixture()` 把 repo/ 物化成真实 git 仓库
（init + commit），所以每次运行都有真实 base SHA 与 diff。

## A/B/C 基线（evaluation/runner.py）

- **A-single-shot**：`max_llm_calls=1`，无迭代反馈；
- **B-basic-loop**：迭代 + 反馈，但工具集只有 read_file/apply_patch/run_tests；
- **C-safefix**：全工具 + 沙箱 + 独立验证。

同一 provider、同一执行后端、同一验证器——差异只在循环/工具配置。

## 指标与报告

`evaluation/metrics.py:summarize()`：verified 率、复现成功率、补丁生成率、
平均调用数、token、耗时、失败类别、审批拒绝数。
`reporter.py` 输出 `results.json + summary.csv + report.md`。

失败类别（`classify_failure`）：not_reproducible / empty_patch /
test_tampering / stuck / budget_exhausted / provider_error / aborted /
verification_failed。

## 诚实规则（重要）

- mock 运行**必须标注**"MOCK PIPELINE VALIDATION"，绝不冒充模型成绩；
- 真实 LLM 未配置 → 集成测试显式 skip = **NOT RUN**；
- 5 个任务的小样本**不做统计显著性声明**；
- 已执行的真实结果记录在 `docs/evaluation.md`。

## 动手跑一次

```bash
uv run python examples/run_mock_suite.py     # 15 运行（5 任务 × A/B/C），MOCK
uv run safefix eval --suite benchmarks/suite.yaml --mode mock --variants A,B,C
# 有凭据后：
uv run safefix eval --suite benchmarks/suite.yaml --mode real
```

查看 `benchmarks/results/mock-pipeline-validation/report.md`。

## 常见失败场景

- 全部 verified 且毫无区分度 → 你跑的是 mock（脚本里就是正确补丁）。
- `unknown fixture` → suite.yaml 的 fixture 名与目录不一致。
- real 模式报 ConfigError → 没配凭据（这是特性，不是 bug）。

## 如何修改与测试

加第 6 个任务：建 fixture 三件套 → suite.yaml 加条目 →
`tests/unit/test_fixtures.py` 会自动验证"base 必须红"。
改指标：先改 `tests/unit/test_evaluation.py::test_summarize_rates`（红），
再改 `metrics.py`（绿）。