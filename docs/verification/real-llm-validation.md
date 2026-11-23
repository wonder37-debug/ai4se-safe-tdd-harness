# 真实 LLM 验证报告（Real-LLM Validation）

> 日期：2026-11-23 · 分支 `rewrite/python-safefix` · 验证时 HEAD：`a6e1529`
> 凭据经 gitignored `.env` 注入；**本报告与所有证据文件均不含 API key**。

## 环境

| 项 | 值 |
|---|---|
| 宿主 | Windows 11 26H2 · PowerShell 7 |
| Python | uv 0.12.3 管理 CPython 3.12.13（项目 venv） |
| Docker | Docker Desktop 29.6.1（Linux 容器，WSL2 后端） |
| WSL2 | Ubuntu · Python 3.12.3（Linux 侧验证） |
| 模型 | `qwen3.8-flash` |
| 端点 | `llm-wvdrtvcinxatskep.cn-beijing.maas.aliyuncs.com`（OpenAI compatible-mode/v1） |
| 沙箱镜像 | `safefix-sandbox:latest`（python:3.12-slim + pytest，uid 1000） |

## 1. 最小真实 API 冒烟（`examples/real_smoke.py`）

证据：`evidence/real-smoke.json`。全部通过：

- request_reached_provider ✓（真实 HTTP 请求到达端点）
- fenced_action_parsed ✓ / action_validated ✓（围栏 fallback → Pydantic 校验）
- native_tool_calling ✓（原生返回 `read_file {"path": "a.py"}`）
- usage_recorded ✓（样例 87 prompt / 70 completion）
- explicit_provider_error ✓（无效模型 → `AuthError`，无静默成功）
- 全程 `OpenAICompatProvider`，**无 ScriptedMock 替代**（构造断言）。

## 2. 真实完整修复（REAL 模式 + Docker 沙箱）

| 运行 | 任务 | status | LLM 调用 | tokens(in/out) | 耗时 | base commit |
|---|---|---|---|---|---|---|
| CLI `safefix fix` | paginate（原 fixture） | **verified** | 7 | 7233/449 | 14.8s | `d57dd150` |
| CLI `safefix fix` | querystring（**held-out 新构造**） | **verified** | 10 | 13426/961 | 16.0s | `6f441ac4` |
| 门控集成测试（AutoDeny） | paginate | **verified** | 10 | 60132/641 | 29.2s | `b39dfb43` |

每次运行均满足：真实模型工具轨迹（list_files/read_file/search_code/run_tests/
apply_patch/finish）、补丁非空、初始复现失败（exit 1）、复现转绿、回归通过、
独立 eval 通过、测试未篡改、**原仓库零改动**（git status 断言）。
证据：`evidence/real-fix-*-outcome.json` + `*.patch`、`evidence/real-llm-integration-outcome.json`。

held-out 任务 `querystring-repeated-keys` 不在原 5 fixture 与任何脚本答案中
（`evaluation/demo_script.py` 无其条目），模型自主完成含一次补丁修订的闭环。

## 3. 真实 A/B/C 基准（`benchmarks/results/real-qwen38-flash/`）

命令：`uv run safefix eval --suite benchmarks/suite.yaml --mode real --variants A,B,C`
预算：每任务 ≤12 次 LLM 调用 / ≤300s；同模型/同任务/同沙箱/同验证器；每运行干净工作区。
记录含 model、endpoint_host、code_commit（`5f3083c`）、逐运行 outcome/events/patch。

| 变体 | verified | 平均调用 | 失败类别 |
|---|---|---|---|
| A-single-shot | **0/5** | 1 | empty_patch ×5（cap） |
| B-basic-loop | **5/5** | 8.4 | — |
| C-safefix | **5/5** | 7.6 | — |

15 运行总 token：85,785。观察（**小样本，不做显著性声明**）：
迭代反馈（B/C）相对单发（A）在该套件上决定性有效；C 的平均调用数略低于 B。
A 的失败是基线设计弱点（首步未落补丁即耗尽预算），非工程缺陷。
修复 pyc 缺陷前后各跑一次，结论一致（A 0/5、B 5/5、C 5/5）。

## 4. 验证中发现并修复的工程缺陷

1. **陈旧字节码**（WSL 确定性复现）：补丁与测试同秒、CRLF→LF 字节缩减抵消修复增量，
   `.pyc` 的 (mtime,size) 校验误判有效 → 重测执行旧代码。修复：apply_patch 后清除
   工作区 `__pycache__`（`tests/unit/test_patch.py` 回归）。
2. **沙箱镜像缺 pytest**：默认 `python:3.12-slim` 无 pytest → real 模式必败。
   修复：默认 `safefix-sandbox:latest`（Dockerfile 预装），集成 conftest 自动构建，CI 增构建步骤。
3. **wheel 数据路径错配**：bundle 在 `safefix/_fixtures`，解析指向 `evaluation/_fixtures`
   → 净室 demo 失败。修复后净室安装 demo verified、mock eval 5/5。
4. **套件重跑碰撞**：Windows 只读 git 文件使 `rmtree(ignore_errors=True)` 静默泄漏。
   修复：`onexc` 处理器 + 运行前清理（回归测试）。

## 5. 复现步骤

```bash
uv sync
docker build -t safefix-sandbox:latest .
# 配置 .env（API_KEY/API_BASE_URL/MODEL，勿提交）
uv run python examples/real_smoke.py
uv run safefix fix --repo <fixture repo> --issue-file <issue.md> --mode real --yes \
  --eval-dir benchmarks/fixtures/paginate/eval --report-dir .safefix-runs/real-paginate
uv run safefix eval --suite benchmarks/suite.yaml --mode real --variants A,B,C
$env:SAFEFIX_REAL_LLM="1"; uv run pytest tests/integration/test_real_llm.py
```

## 6. 局限

- 5+1 任务小样本；缺陷局部、仓库极小；不外推到大型真实项目。
- 成本未折算美元（无内置定价表）；token 已记录。
- WSL Ubuntu 的 Docker Desktop 集成未启用（不改动用户设置）；Linux 容器沙箱经
  Windows Docker Desktop 实测，Linux 宿主路径由 CI ubuntu-latest 覆盖。