# 迁移最终审计（Migration Final Audit）

> 独立复核，不沿用旧报告结论。日期：2026-11-23 · 分支 `rewrite/python-safefix`。

## 1. 旧报告声明 vs 独立复核

| 声明 | 复核结果 |
|---|---|
| 214 passed / 2 skipped | 初始复核一致（214/2）；修复缺陷并新增测试后 **219 passed / 2 skipped**（Windows） |
| 89% 覆盖率 | 复核一致（TOTAL 1754 语句 / 194 未覆盖；`ui_app.py` 未装 streamlit 计 0%） |
| 8 个 Docker 集成测试 | 一致：7 沙箱契约 + 1 沙箱内完整修复，全部真实通过 |
| 15/15 mock 基准 | 一致；且修复重跑碰撞缺陷后**可重复**重跑 15/15 |
| skip 解释 | ① Windows 无符号链接权限（Linux/WSL 下真实执行通过）② real-LLM 门控（配置凭据 + SAFEFIX_REAL_LLM=1 后真实通过 62s） |

## 2. 最终测试矩阵（实测）

| 环境 | 命令 | 结果 |
|---|---|---|
| Windows + uv CPython 3.12.13 | `uv run pytest tests/unit tests/integration` | **219 passed, 2 skipped** |
| WSL2 Ubuntu Python 3.12.3 | `python3 -m pytest tests/unit` | **212 passed, 0 skipped**（含 symlink 逃逸） |
| Windows | `uv run pytest tests/unit --cov=safefix` | 89% |
| Windows | `uv run ruff check src/safefix tests examples` | All checks passed |
| Windows | `uv build` | wheel + sdist 成功 |
| 净室（仓库外全新 venv，仅 wheel） | `safefix demo` / `safefix eval --mode mock` | demo **verified**；eval C **5/5** |
| 门控真实 LLM | `SAFEFIX_REAL_LLM=1 pytest tests/integration/test_real_llm.py` | **1 passed**（62s，真实修复 verified） |

## 3. 旧 TS/JS 清除（commit 见 git log）

已删除（68 个跟踪文件）：`src/{approval,cli,creds,feedback,guardrail,llm,loop,
memory,protocol,tools,web}`、`src/index.ts`、`src/types.ts`、`test/`（Jest）、
`demo/`（Jest 机制演示）、`package.json`、`package-lock.json`、`tsconfig.json`、
`jest.config.js`。

保留：Git 历史与 `main` 分支旧实现；`SPEC.md`/`SPEC_PROCESS.md`/`PLAN.md`/
`REFLECTION.md`/`AGENT_LOG.md` 历史文档；迁移审计与报告；MIT 许可与课程归属。

复核：`git ls-files "*.ts" "*.js"` 为空；活动文档无 `npm run`/`npx jest`；
`src/` 仅余 `safefix/`；CI（GitHub + GitLab）与 Dockerfile 均为 Python 工具链；
SafeFix 安装/开发/测试/运行不依赖 Node.js。

## 4. 特性 parity 映射

见 `docs/migration/source-audit.md` §6 与 `docs/migration/migration-report.md`。
核心机制（协议/循环/护栏/审批/反馈/provider/记忆/凭据/工具围栏）均有 Python
等价测试；有意升级（沙箱强制、模式分离、最小补丁、独立验证、进展感知重试、
随机盐加密、预算对象）逐项记录于迁移报告。

## 5. 安全与卫生

- 凭据：`.env` 被 `.gitignore` 排除（`git check-ignore .env` 确认）；
  `git grep` 全库与证据目录扫描无 key；`.env.example` 仅空占位。
- 沙箱契约复验：非 root uid 1000、无 privileged、无 docker.sock、`--network none`、
  宿主 env 不泄漏、资源限额、超时 kill、不可用显式拒绝（7 项集成断言通过）。
- 工作区隔离与清理：原仓库零改动断言；失败路径清理（rmtree onexc）。
- 无构建产物/venv 误跟踪：`dist/`、`.venv*/`、`.safefix-runs/`、
  `benchmarks/results/*/src/` 均 gitignored。

## 6. 遗留限制

见 `docs/limitations.md`（已更新）：真实样本小、仅 Python/pytest 实测、
Docker 共享内核、WSL Docker 集成未启用、成本未折算。