# AI4SE SafeFix

**一个用 Python 自研内核的、测试驱动 + 沙箱隔离的 Coding Agent，用于 Git 仓库中的自动 bug 修复。**

> 历史沿革：本仓库最初是 AI4SE 期末项目（Option A: Coding Agent Harness）的 TypeScript 实现。
> 自 `rewrite/python-safefix` 分支起，维护中的应用代码已**完整迁移为 Python 3.12**（项目名 SafeFix）。
> 旧 TypeScript 代码保留在 Git 历史与 `main` 分支中，审计见 [docs/migration/source-audit.md](docs/migration/source-audit.md)；
> 开发/运行 SafeFix **不再需要 Node.js / npm / TypeScript / Jest**。

## 产品目标

输入：一个本地 Git 仓库（或 Git URL）+ 自然语言 bug 报告 + 测试命令与预算。
输出：最小化 Git diff 补丁、修复前后测试证据、独立验证结论、完整执行轨迹、token 用量与耗时。
**原始仓库绝不会被自动修改**——所有操作发生在一次性隔离工作区中。

## 已实现特性（均有测试佐证）

- **自研 AgentLoop 状态机**（`src/safefix/agent/loop.py`）：显式任务状态、结构化 tool call、
  人工审批（HITL）、测试反馈回灌、有界重试、取消、7 种终止原因、资源预算
  （LLM 调用数 / 步数 / 墙钟 / token）。
- **动作协议**：```` ```action ```` 围栏 JSON + 原生 OpenAI tool calling 双通道；
  Pydantic **严格模式**校验所有模型生成的工具参数，未知/畸形调用绝不执行。
- **8 个结构化工具**：`list_files / search_code / read_file / apply_patch / run_tests /
  git_status / git_diff / finish`。`apply_patch` 为纯 Python unified-diff 最小补丁应用器。
- **可强制执行的 Docker 沙箱**（`runtime/docker_executor.py`）：非 root、cap-drop ALL、
  no-new-privileges、无网络、CPU/内存/进程数限额、仅挂载任务工作区、无 Docker socket、
  不透传宿主环境变量、`--rm` 清理。**Docker 不可用 → 显式报错，绝不静默宿主执行。**
- **护栏 + 审批纵深防御**（`security/policy.py`）：整词匹配、子壳解包、Windows 规则、
  拒绝后升级；明确声明其**不是安全边界**（边界是沙箱）。
- **测试反馈分类**：pytest / Jest / 未知输出兜底；六类错误
  （pass / assertion / syntax / timeout / infrastructure / unexpected）。
- **独立验证器**（`repair/verifier.py`）：`finish` 只是声明，成功必须由证据判定——
  复现测试由红转绿、回归通过、独立 eval 测试通过、禁止修改/删除测试、空补丁拒绝。
- **LLM Provider**：OpenAI 兼容端点，指数退避 + 半抖动、Retry-After、429/5xx 可重试、
  4xx AuthError 不重试、token 用量记录；real / mock / demo 三模式**显式分离**，
  real 模式缺凭据显式报错，绝不静默降级演示。
- **加密凭据存储**：AES-256-GCM + PBKDF2-HMAC-SHA256（100k 迭代、随机盐、版本化 blob），
  `safefix creds set/status/clear` 隐藏输入，永不回显明文。
- **可复现评估**：5 个真实缺陷 fixture（off-by-one / 校验 / 边界 / 数据处理），
  A/B/C 基线（单发 / 基础循环 / 完整 SafeFix），JSON + CSV + Markdown 报告。
- **CLI（Typer + Rich）**：`demo / fix / eval / report / creds / ui`；
  可选 Streamlit 运行查看器（仅 localhost）。
- **253 个离线单元测试（Windows 实测 247 通过，6 个因 symlink/mkfifo 权限跳过）
  + 8 个真实 Docker 沙箱集成测试**，核心机制全部可在
  无网络、无真实 LLM 条件下用 ScriptedMock 验证。
- **真实模型验证已完成**（qwen3.8-flash，OpenAI 兼容端点）：验收测试强制
  verified（paginate + held-out querystring，2 passed）；修正方法学后的真实 A/B/C
  基准 **A 2/5 · B 5/5 · C 5/5**。详见 [docs/verification/](docs/verification/real-llm-validation.md)。

## 架构

```
safefix CLI (cli.py)
  → RepairTask / run_repair (repair/workflow.py)
      1. prepare_workspace：克隆目标仓库 → 一次性副本，记录 base commit
      2. 可信准备（可选，受控网络）→ 复现失败（证据留存）
      3. AgentLoop (agent/loop.py)
           LLMProvider (llm/) ⇄ 动作协议 (agent/protocol.py)
           → 护栏评级 (security/policy.py) → 高危人工审批 (security/approval.py)
           → ToolRegistry 严格校验 (tools/registry.py) → 工具执行
               文件/补丁/git：工作区内受控操作
               run_tests：Docker 沙箱 (runtime/docker_executor.py)
           → 反馈分类 (feedback/) 回灌 → 预算/进展感知重试
      4. git diff 提取 → 独立验证 (repair/verifier.py)
      5. outcome.json / patch.diff / events.jsonl → 清理工作区
```

详见 [docs/architecture.md](docs/architecture.md)。

## 快速开始

环境要求：**Python 3.12+**、[uv](https://docs.astral.sh/uv/)、Git；
真实修复任务需要 **Docker**（Windows 11 推荐 WSL2 Ubuntu + Docker Desktop，见下）。

```bash
uv sync                      # 创建 .venv 并安装依赖（含 dev 组）
uv run safefix --help
uv run safefix demo          # 离线确定性机制演示（无需网络/Docker/凭据）
uv run pytest tests/unit     # 206 个离线单元测试
```

### WSL2 / Docker 设置（Windows 11）

1. 安装 Docker Desktop 并启用 WSL2 后端（设置 → General → Use the WSL 2 based engine）。
2. 在 WSL2 Ubuntu 中克隆本仓库并 `uv sync`（项目可直接在 WSL 内开发运行）。
3. 验证：`docker info` 可达；`uv run pytest tests/integration -m integration`
   应全部通过（Docker 不可达时这些测试**显式 skip = NOT RUN**，不会冒充成功）。
4. 可选：`docker build -t safefix-sandbox:latest .` 构建预装 pytest 的沙箱镜像。

### API 凭据设置（real 模式）

```bash
uv run safefix creds set          # 隐藏输入 API key + 主密码 → ~/.safefix/creds.enc
export MASTER_PASSWORD=...        # 或写入进程环境（注意 .env 为明文，见安全模型）
# 或者使用 .env（明文兜底，带告警）：API_KEY / API_BASE_URL / MODEL
uv run safefix fix --repo /path/to/repo --issue "paginate() 第 1 页返回了第 2 页的内容" --mode real
```

### CLI 示例

```bash
safefix demo                                    # 机制演示（护栏拦截 + 反馈闭环 + 独立验证）
safefix fix --repo PATH --issue "bug 描述" --mode real
safefix fix --repo PATH --issue-file issue.md --mode real --yes
safefix eval --suite benchmarks/suite.yaml --mode mock --variants A,B,C   # 管线验证（明确标注 MOCK）
safefix eval --suite benchmarks/suite.yaml --mode real                    # 真实模型评估
safefix report .safefix-runs/demo               # 查看运行结论与证据
safefix ui --run-dir .safefix-runs/demo         # 可选 Streamlit 查看器（uv sync --extra ui）
```

## 测试与评估

```bash
uv run pytest tests/unit                        # 离线、确定性、无网络
uv run pytest tests/integration -m integration  # 真实 Docker 沙箱（daemon 不可达则 skip）
uv run pytest tests/unit --cov=safefix          # 覆盖率（当前约 89%，ui_app 除外）
uv run python examples/run_mock_suite.py        # 5 任务 × A/B/C 管线验证（MOCK，非模型成绩）
uv run python examples/real_smoke.py            # 真实 API 冒烟（需 .env 凭据）
uv run safefix eval --suite benchmarks/suite.yaml --mode real --variants A,B,C  # 真实基准
```

真实 LLM 集成测试（`tests/integration/test_real_llm.py`）需要
`SAFEFIX_REAL_LLM=1` + 有效凭据，否则**明确标记 NOT RUN**。
配置凭据后已实测通过（真实修复 verified，62s）；真实结果与复现步骤见
[docs/verification/](docs/verification/real-llm-validation.md)。

## 安全限制（务必阅读）

- 沙箱隔离的是**命令执行**；Docker 共享内核，不是 VM 级隔离。
- 护栏是启发式纵深防御，可被创造性命令绕过；真正的边界是沙箱 + 验证器。
- 依赖安装（可信准备阶段）需要受控网络；模型生成命令执行时网络关闭。
- `.env` 与进程环境是明文可见的；长期密钥请用加密存储。
- 提示注入无法根治：仓库内容被声明为不可信数据，验证器拒绝改测试等作弊行为。

详见 [docs/security-model.md](docs/security-model.md) 与 [docs/limitations.md](docs/limitations.md)。

## 已知问题与路线图

见 [docs/limitations.md](docs/limitations.md)。要点：真实模型样本小（5+1 任务，
观察性结论）；fixture 为自研缺陷复现（非外部 CVE）；Jest/Java/C++ 目标仓库适配器未实现；
Windows 宿主直接运行沙箱依赖 Docker Desktop（推荐 WSL2）。

## 文档索引

- [docs/architecture.md](docs/architecture.md) · [docs/security-model.md](docs/security-model.md)
- [docs/evaluation.md](docs/evaluation.md) · [docs/limitations.md](docs/limitations.md)
- [docs/migration/source-audit.md](docs/migration/source-audit.md) · [docs/migration/migration-report.md](docs/migration/migration-report.md)
- [docs/portfolio-evidence.md](docs/portfolio-evidence.md)（可验证的简历素材）
- [docs/learning/](docs/learning/)（中文学习指南 00–09，含面试问答）

## 许可与致谢

MIT。原始 TypeScript harness 为 AI4SE 课程期末项目（Option A），其自研内核设计
（依赖注入、离线可测、机制即代码）是本次 Python 重写的行为参考；迁移映射与
parity 测试见迁移文档。
