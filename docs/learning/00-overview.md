# 00 · SafeFix 总览：这个项目到底在做什么

## 它解决什么问题

给一个 Git 仓库和一段 bug 描述，让 LLM 自动写出**最小修复补丁**，并且用
**独立证据**证明修好了——整个过程不碰你的原始仓库，危险命令被关在沙箱里。

一句话：**LLM 负责想办法，代码负责守规矩、验结果。**

## 为什么不能只靠提示词

在系统提示里写"不要删库"没用——模型可能不听。SafeFix 的每个关键机制都是
**你写的确定性函数**：

- 危险命令 → `security/policy.py:assess()` 评级 + 人工审批；
- 命令执行 → `runtime/docker_executor.py` 容器隔离；
- "修好了" → `repair/verifier.py` 用测试证据判定，`finish` 只是声明。

把真实 LLM 换成脚本 mock，这些机制照样可以完整测试（206 个离线单元测试）。

## 十分钟跑起来

```bash
uv sync                    # 安装依赖（需要 uv + Python 3.12）
uv run safefix demo        # 离线演示：复现→危险动作被拒→读码→补丁→验证
uv run pytest tests/unit   # 跑全部离线测试
uv run safefix report .safefix-runs/demo   # 看演示的证据
```

有 Docker 时再跑真实沙箱集成：

```bash
uv run pytest tests/integration -m integration
```

## 代码地图（建议阅读顺序）

1. `src/safefix/models.py` —— 数据长什么样（10 分钟）
2. `src/safefix/agent/protocol.py` —— LLM 怎么"说话"（10 分钟）
3. `src/safefix/agent/loop.py` —— 主循环（30 分钟，配合 01 文档）
4. `src/safefix/tools/` —— 工具怎么执行（配合 03 文档）
5. `src/safefix/security/` + `runtime/` —— 治理与沙箱（配合 04 文档）
6. `src/safefix/feedback/` —— 测试失败怎么喂回给模型（配合 05 文档）
7. `src/safefix/repair/` —— 完整产品流程（配合 06 文档）
8. `src/safefix/evaluation/` —— 怎么证明它有用（配合 07 文档）

## 学习路径建议

- 第 1 天：跑 demo + 读 00/01，理解循环。
- 第 2 天：读 02/03，给 `read_file` 加一个小功能并写测试（见各文档"如何修改"）。
- 第 3 天：读 04/05，理解沙箱与反馈。
- 第 4 天：读 06/07，跑一次 mock 评估。
- 第 5 天：读 08（调试）/09（面试问答），尝试向别人讲清楚整个系统。

## 常见误区

- "Agent = 调 LLM API 的循环" —— 不，治理/验证/预算才是工程含量所在。
- "worktree 隔离 = 安全" —— 不，它只保护历史；安全边界是容器（见 04）。
- "demo 成功 = 能修真实 bug" —— 不，demo 是脚本；真实能力需要 real 模式评估
  （当前 NOT RUN，见 docs/limitations.md）。