# 已知限制与路线图

## 已知限制（诚实清单）

1. **真实模型样本小**：已用 qwen3.8-flash 完成 3 次独立验证的真实修复
   （含 held-out 缺陷）与 5 任务 A/B/C 真实基准（A 0/5、B 5/5、C 5/5），
   但任务极小且局部，结论为观察性，不能外推为一般 bug 修复能力。
2. **fixture 为自研缺陷复现**：5 个小任务，非外部真实项目 CVE；规模与复杂度
   有限，不能代表一般 bug 修复能力。
3. **语言覆盖**：仅 Python/pytest 目标仓库经过实测。Jest parser 已移植（parity
   测试通过），但 JS/Java/C++ 目标仓库的端到端适配器未实现。
4. **沙箱强度**：Docker 共享内核；无 gVisor/Kata；容器逃逸不在防御范围。
5. **Windows 宿主**：沙箱依赖 Docker Desktop（WSL2 后端）；symlink 围栏测试
   在无符号链接权限时 skip（WSL2 Linux 下实测通过）。WSL Ubuntu 的 Docker
   集成未启用；Linux 宿主沙箱路径由 CI ubuntu-latest 覆盖。
6. **验证器语义盲区**：能拒绝改/删测试与空补丁，但"实现迎合断言却破坏真实
   语义"依赖独立 eval 测试的覆盖度。
7. **成本估算缺失**：token 已记录，美元成本未内置定价表。
8. **UI 为可选查看器**：Streamlit 仅展示已记录运行，不支持交互式审批
   （HITL 审批在 CLI 终端）。
9. **旧 TS Web 面板未迁移**：按任务要求不再维护 JS 前端；旧代码见 Git 历史。

## 路线图

- [x] 配置凭据后执行 real 模式 A/B/C 评估并公布真实成绩（见 docs/verification/）
- [ ] 扩充基准至 10–20 任务（含外部真实缺陷复现，记录许可与 base SHA）
- [ ] Jest/Java/C++ 目标仓库适配器（容器内构建工具链）
- [ ] 成本估算（可配置定价表）
- [ ] gVisor/Kata 可选更强隔离后端
- [ ] Streamlit 交互式审批（当前仅 CLI HITL）
- [ ] 上下文预算管理（长任务对话压缩/摘要）