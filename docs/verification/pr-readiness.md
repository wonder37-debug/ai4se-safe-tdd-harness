# PR 就绪检查（PR Readiness）

> 分支：`rewrite/python-safefix` · 目标：`main`（GitHub `wonder37-debug/ai4se-safe-tdd-harness`）
> 远端名：`github`（`origin` 为 GitLab 镜像，非本 PR 目标）。

## 门槛清单

| # | 门槛 | 状态 | 证据 |
|---|---|---|---|
| 1 | 全部离线测试 | ✅ | Windows 219 passed/2 skipped；WSL 212 passed/0 skipped |
| 2 | Docker 集成测试 | ✅ | 8 passed（真实容器） |
| 3 | 真实 LLM 冒烟 | ✅ | evidence/real-smoke.json 六项全过 |
| 4 | ≥1 次独立验证的真实修复 | ✅ | 3 次 verified（含 held-out querystring） |
| 5 | 真实基准（预算内） | ✅ | A 0/5 · B 5/5 · C 5/5；85,785 tokens；≤12 调用/任务 |
| 6 | 补丁与证据审查 | ✅ | evidence/*.patch + outcome.json；最小 diff、测试未篡改 |
| 7 | lint + build | ✅ | ruff 全绿；uv build wheel+sdist |
| 8 | 原仓库不被测试任务改动 | ✅ | git status 断言（多次运行） |
| 9 | 密钥/生成物自查 | ✅ | git grep 无 key；gitignore 覆盖产物 |
| 10 | 旧 TS/JS 依赖移除 | ✅ | 68 文件删除；无 .ts/.js 跟踪；CI/Docker Python |
| 11 | 净室安装冒烟 | ✅ | 仓库外 venv + wheel：demo verified / eval 5/5 |

## 合并前风险

1. ~~远端 CI 尚未运行~~ **已解决**：HEAD `8458500` 上 `unit-test` 与
   `sandbox-integration` 均 **success**（push + PR 双事件）。过程记录：
   首轮 sandbox-integration 失败于 Linux bind-mount 权限（固定 uid 1000 vs
   runner uid 1001）→ 修复为容器用户匹配工作区属主（永不 root）；随后两轮
   失败均为旧测试硬编码 uid 1000 的预期未随语义更新（经 CI 注解定位）→
   修正断言后全绿。沙箱内完整修复测试在 ubuntu-latest 真实通过。
2. 真实模型样本小（5+1 任务），结论为观察性，非统计显著。
3. `main` 自分支点无新提交（fetch 复核：merge-base == github/main == 3512ba4，无冲突）。
4. WSL Ubuntu 的 Docker 集成未启用——不影响 PR（CI 已覆盖 Linux 宿主路径）。

## 结论

**GO**。CI 绿灯已确认；不自动合并，合并需仓库所有者显式授权。