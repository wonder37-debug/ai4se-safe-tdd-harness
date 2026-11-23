# 09 · 面试问答（答案全部基于本仓库真实代码）

> 表述建议：聚焦"我理解并验证了这套系统"，不虚构手写经历。
> 每个答案都给出代码位置，方便你现场展开。

**Q1：什么是 Coding Agent？和聊天机器人有什么区别？**
聊天机器人只产出文本；Coding Agent 在"LLM 决策 + 工具执行 + 环境反馈"的
闭环里操作真实代码仓库。本项目的闭环就是 `agent/loop.py:AgentLoop.run()`：
模型输出动作 → 校验/治理 → 执行 → Observation 回灌 → 下一轮。

**Q2：LLM 和 Agent 的区别？**
LLM 是无状态文本函数（`llm/base.py:LLMProvider.complete`）；Agent 是围绕它
构建的有状态系统：消息历史、预算、终止判定、治理。LLM 可替换（mock/真实），
Agent 的机制不变——这正是依赖注入的意义。

**Q3：为什么需要 AgentLoop？直接一次生成补丁不行吗？**
可以，那就是基线 A（single-shot）。但 bug 修复通常需要"复现→定位→改→验证→
再改"。循环提供迭代反馈与失控保护（7 种终止原因、预算、取消）。
`evaluation/runner.py` 的 A/B/C 就是用来量化这个差异的。

**Q4：tool calling 是怎么工作的？**
两条通道：原生 function calling（请求带 JSON Schema，由
`tools/registry.py:schemas()` 从 Pydantic 模型生成；响应解析为 ToolCall）；
围栏协议兜底（`agent/protocol.py` 正则提取 ```action JSON）。所有参数先过
`model_validate(strict=True)`，畸形/未知调用绝不执行。

**Q5：为什么用 Pydantic？**
构造即校验、序列化回灌（`model_dump_json`）、自动生成工具 Schema。
strict 模式防止隐式类型转换带来的意外执行。见 `models.py` 与
`tests/unit/test_registry.py`。

**Q6：为什么 Git worktree 不是安全沙箱？**
worktree/copy 只隔离**仓库历史与内容**，进程仍在宿主上跑，能读宿主任意文件、
访问网络、耗尽资源。安全边界是 Docker：`runtime/docker_executor.py` 的
非 root + cap-drop + 无网络 + 限额 + 仅挂载工作区。

**Q7：Docker 是怎么隔离命令的？**
namespace（PID/网络/挂载）+ cgroups（CPU/内存/pids）+ capabilities 裁剪 +
no-new-privileges。本项目 `--network none` 断网、`--user 1000:1000` 非 root、
不挂 docker.sock、不透传宿主 env。实测断言在
`tests/integration/test_docker_sandbox.py`。注意：共享内核，逃逸 0-day 不在
防御范围（诚实加分点）。

**Q8：Agent 怎么知道 bug 修好了？**
它不知道——`finish` 只是声明。`repair/verifier.py` 独立判定：补丁非空、
测试未被篡改、复现命令转绿、回归通过、独立 eval 测试通过，且初始确实可复现。
eval 测试生成期对 agent 不可见。

**Q9：测试反复失败怎么办？**
进展感知有界重试（`agent/loop.py`）：失败键=类别+失败测试集+位置；连续同键
≥3 次才 stuck；`apply_patch` 成功清零计数。旧实现"2 次即 stuck"被证明过激。

**Q10：为什么用 pytest？**
生态标准、断言内省输出利于解析（`feedback/pytest_parser.py` 提取
FAILED 行与 file:line）、fixture/tmp_path 让测试确定性且隔离。
206 个单元测试全部离线可跑。

**Q11：怎么防止不安全的文件修改？**
三层：文件工具 `Path.resolve()` + `is_relative_to` 围栏（含 symlink 逃逸，
`tools/files.py:_fence`）；apply_patch 只接受上下文精确匹配的最小 diff；
验证器拒绝测试篡改与空补丁。命令执行则整体进沙箱。

**Q12：基准到底测了什么？**
5 个自研缺陷 fixture × A/B/C 变体，测复现率/补丁生成率/验证修复率/调用数/
token/耗时/失败类别。**当前公开结果是 MOCK 管线验证（15/15），真实模型
NOT RUN**——主动说明这点比吹嘘更加分。见 `docs/evaluation.md`。

**Q13：你做了哪些技术取舍？**
- 自研循环而非 LangChain：可解释、可离线测试（课程硬约束）；
- 纯 Python diff 应用器而非 git apply：零外部依赖、可单测、两阶段原子写；
- 文件型记忆而非向量库：需求不支撑 RAG 复杂度；
- Docker 而非 gVisor：环境可得性优先，文档声明强度上限；
- Typer CLI 优先、Streamlit 可选：不引入前端技术栈负担。

**Q14：实际实现局限是什么？**
真实 LLM 成绩未测；fixture 小且自研；仅 Python/pytest 实测；语义级作弊依赖
eval 覆盖度；成本估算未实现。完整清单在 `docs/limitations.md`。

**Q15：如果让你扩展，下一步做什么？**
配置凭据跑 real A/B/C → 扩 10–20 任务（含外部缺陷复现）→ Jest/Java 适配器 →
更强隔离后端。路线图已写在 limitations.md。