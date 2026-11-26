# TypeScript → Python 迁移报告

分支：`rewrite/python-safefix` · 基线：`main` @ `3512ba4` · 目标：Python 3.12 + uv

## 里程碑与提交

| 里程碑 | 内容 | 关键提交 |
|---|---|---|
| M0 | 仓库审计 + 原测试/构建实测（87 suites / 593 passed；tsc 成功） | `e0c7417` |
| M1 | 核心 parity：models/协议/护栏/审批/反馈/mock/provider/记忆/凭据/工具/循环 | `a23f9a0` `627bfff` `5e04fa6` `0612448` `17f2853` `5930b57` |
| M2 | Docker 沙箱 + 一次性工作区 + 模式分离 | `da7f5f4` |
| M3 | 修复工作流 + 独立验证 + 5 fixture + 沙箱集成实测 | `34fcfb0` `8bdd581` |
| M4 | A/B/C 评估 runner + 报告 + mock 管线验证 15/15 | `c364078` |
| M5 | Typer/Rich CLI + Streamlit 查看器 + CI + 文档 | `04fbaee` `1eb9df7` |

## 行为 parity 结论

原 TS 核心机制全部有对应 Python 测试（见 `tests/unit/`）：

- 协议：未闭合围栏/畸形块/未知工具拒绝/strip ✓
- 循环：finish/cap/stuck/provider_error/user_abort + 新增 cancelled/budget_exceeded ✓
- 护栏：整词匹配/子壳解包/Windows 规则/deny 升级/tokenize 失败强制审批/误报消除 ✓
- 审批：队列耗尽默认 deny；终止意图中英文词边界 ✓
- provider：429/5xx 退避、Retry-After、AuthError 不重试、baseUrl 归一化、角色降级 ✓
- 反馈：Jest parity + pytest 新 parser + 兜底/截断 ✓
- 凭据：加解密往返/错密码/决议优先级 ✓（升级：随机盐 + 版本头）
- 记忆/工具围栏/ScriptedMock ✓

## 有意的行为变更（升级，非照抄）

| 旧行为 | 新行为 | 理由 |
|---|---|---|
| `child_process.exec` 宿主直接执行 | Docker 沙箱强制；不可用显式报错 | R1 安全 |
| 字符串前缀路径围栏 | resolve + symlink 检查 | R2 逃逸 |
| 无凭据静默降级 ScriptedMock | real 缺凭据显式 ConfigError | R3 诚实 |
| 同错 2 次即 stuck | 默认 3 次 + apply_patch 进展重置 | R4 过激 |
| 三类错误 | 六类（含 timeout/infra） | R5 |
| 固定盐加密 | 随机盐 + SFX1 版本头 | R6 |
| write_file 整文件覆写 | apply_patch 最小 diff + git 工具 + 验证器 | R7 |
| maxIter=20 硬编码 | Budgets 对象（调用/步数/墙钟/token） | R8 |

## 验证证据（实测）

- `uv run pytest tests/unit`：**206 passed, 1 skipped**（symlink 权限），覆盖率 89%。
- `uv run pytest tests/integration -m integration`：**8 passed**（真实 Docker：
  非 root/无网络/挂载可写/env 不泄漏/超时 kill/沙箱内完整修复 50.1s）。
- real-LLM 集成：**NOT RUN**（无凭据，显式 skip）。
- `examples/run_mock_suite.py`：15/15 verified（**MOCK 管线验证**，非模型成绩）。
- `docker build -t safefix-sandbox:latest .` 成功并在加固容器中验证 pytest 9.2.0。
- `uv run safefix demo`：status=verified，护栏 DENIED 证据落盘。

## 遗留

旧 TS 代码未删除（保留于 Git 历史与 main 分支）；`package.json`/`jest.config.js`
等仍在树上供历史对照，SafeFix 开发运行不依赖它们。后续可在独立清理分支移除。