# 08 · 调试指南：出了问题从哪里下手

## 第一原则：看证据文件

每次运行都落盘三件套（`--report-dir`）：

- `outcome.json`：status / halt_reason / verification.checks / failure_analysis
- `events.jsonl`：逐事件轨迹（thought/action/observation/approval/halt）
- `patch.diff`：候选补丁

```bash
uv run safefix report .safefix-runs/fix     # 终端友好视图
```

## 症状 → 排查路径

| 症状 | 第一步 | 常见根因 |
|---|---|---|
| `real mode requires API credentials` | 检查 .env / creds | 没配 key（特性：绝不静默降级） |
| `Docker daemon is not reachable` | `docker info` | Docker Desktop 没启动 / WSL 后端没开 |
| halt=provider_error | events.jsonl 最后一条 | 401（key 错）/ 429 限流耗尽 / 网络 |
| halt=stuck | 看重复的 observation | 模型反复同一错误且无补丁进展 |
| halt=cap / budget_exceeded | outcome.iterations / duration | 预算太小或任务太难 |
| status=unverified | verification.checks 哪项红 | eval 失败 / 改了测试 / 复现仍红 |
| `hunk context mismatch` | patch.diff vs 实际文件 | 模型没先 read_file 就编 diff |
| `path escapes workspace` | 工具参数 | 越界路径或 symlink |
| 容器内 No module named pytest | setup_commands | 需要可信准备装依赖（见 04） |
| 测试 skip: symlink | Windows 权限 | 开发者模式/管理员才能建符号链接 |

## 离线复现技巧

不需要真实 LLM 就能复现循环行为：

```python
from safefix.llm.mock import ScriptedMock
provider = ScriptedMock(['```action\n{"tool": "finish", "args": {}}\n```'])
```

把可疑的模型回复塞进队列，跑 `tests/unit/test_agent_loop.py` 风格的测试。
Provider 问题用 `httpx.MockTransport`（见 `tests/unit/test_openai_provider.py`）。
沙箱 argv 问题用 FakeSpawn（见 `tests/unit/test_docker_executor.py`）。

## 日志与事件

- 结构化日志：`logging.getLogger("safefix")`（明文 key 告警等）。
- 事件流：给 `run_repair(..., sink=你的sink)` 注入自定义 EventSink 实时观察。
- 调试时把 `Budgets(max_llm_calls=3)` 调小，快速失败快速迭代。

## 运行测试的姿势

```bash
uv run pytest tests/unit -x -q            # 首个失败即停
uv run pytest tests/unit -k "stuck" -v    # 按名字筛选
uv run pytest tests/unit --cov=safefix --cov-report=term-missing  # 找未覆盖行
uv run pytest tests/integration -m integration -v                 # 真 Docker
```

## 修改代码的纪律（TDD）

1. 先写/改一个会失败的测试，运行确认**红**（且失败原因正确）；
2. 最小实现转**绿**；
3. `uv run ruff check src/safefix tests` + 全量 `pytest tests/unit`；
4. 小步提交，commit message 说明动机。

## 还是没头绪？

按数据流逐段隔离：协议解析（protocol 单测）→ 循环（mock provider）→
工具（registry 单测）→ 执行器（FakeSpawn）→ 验证器（RoutingExecutor）。
每一段都有独立测试文件，二分定位很快。