# 02 · Python 工程结构：包、依赖注入与类型

## 解决什么问题

一个能长期维护的 Python 项目：模块边界清晰、依赖可替换、类型可检查、
测试不需要网络。

## 项目布局

```
pyproject.toml          # 项目元数据 + 依赖 + pytest/ruff 配置（uv 管理）
src/safefix/            # 应用代码（src-layout，避免误 import 源码目录）
  agent/ llm/ tools/ runtime/ security/ feedback/ memory/ creds/ repair/ evaluation/
tests/unit/             # 离线确定性测试
tests/integration/      # 需要 Docker / 真实 LLM（自动 skip）
benchmarks/fixtures/    # 缺陷仓库 fixture
```

关键依赖及理由：`pydantic`（模型校验）、`httpx`（异步 HTTP）、`typer+rich`
（CLI）、`cryptography`（加密存储）、`pyyaml`（套件配置）；dev：`pytest /
pytest-cov / pytest-asyncio / ruff`。**没有** LangChain 等 Agent 框架。

## 核心模式：依赖注入

`AgentLoop` 不自己创建 LLM/审批/执行器，而是接收 `LoopDeps`
（`agent/loop.py`，dataclass）：

```python
@dataclass
class LoopDeps:
    llm: LLMProvider          # Protocol：任何有 async complete() 的对象都行
    registry: ToolRegistry
    approval: ApprovalGateway
    executor: ExecutionBackend | None
    ...
```

`LLMProvider`（`llm/base.py`）是 `typing.Protocol`——**结构化子类型**：
不需要继承，只要签名匹配。测试里 `ScriptedMock`、生产里
`OpenAICompatProvider`，循环代码一行不改。

## 数据模型：Pydantic v2

`models.py` 里 `Action / Observation / Feedback / ...` 都是 `BaseModel`：

```python
class Action(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
```

好处：构造即校验；`model_dump_json()` 直接序列化回灌给模型；
`model_json_schema()` 生成原生 tool calling 的 JSON Schema
（`tools/registry.py:schemas()`）。

注意 `Field(default_factory=dict)`：可变默认值必须用工厂，否则所有实例共享
同一个 dict（Python 经典坑）。

## 异步一致性

所有 I/O 边界都是 async：provider（httpx）、执行器（asyncio subprocess）、
审批（可能等人输入）。同步小文件操作（memory/store）保持简单直接。
测试用 `pytest-asyncio`（`asyncio_mode=auto`，见 pyproject.toml），
async 测试函数无需手动装饰。

## 常见失败场景

- `ModuleNotFoundError: safefix` → 没 `uv sync` 或没用 `uv run`。
- Pydantic `ValidationError` → 模型输出参数类型不对（这是**特性**：严格校验
  拒绝执行，见 03）。
- Windows 上 asyncio subprocess 报错 → 需要 Proactor 事件循环（3.8+ 默认即是）。

## 如何修改与测试

加一个新模块的步骤：建包目录 + `__init__.py` → 先写 `tests/unit/test_x.py`
（红）→ 实现（绿）→ `uv run ruff check src/safefix tests` →
`uv run pytest tests/unit`（全量回归）。