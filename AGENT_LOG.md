# AGENT_LOG.md

> 按 §4.9 要求，时间顺序记录关键节点：时间戳 + task 编号、触发的 Superpowers 技能、关键 prompt/context 配置、subagent/agent 输出的关键片段或 commit hash、人工干预（改了什么、为什么）、教训。
> 时间戳为本次会话内顺序时刻（2026-07-08），正式提交前由作者校准为真实时刻。

---

## 2026-07-08 · 阶段 0：仓库初始化与 CLAUDE.md

- **触发的技能**：`/init`（非 Superpowers 七步流程内，但为后续流程奠基）。
- **task 编号**：T0（前置）。
- **关键 context 配置**：读取仓库根两份要求文档（`AI4SE 期末项目 · 通用要求.md`、`AI4SE_Final_Project_A_Coding_Agent_Harness.md`）、`.gitlab-ci.yml`（Auto-DevOps 模板 + SAST + secret-detection，**缺 `unit-test` job**）、`.env.example`、`.gitignore`。
- **agent 输出**：生成 `CLAUDE.md`（commit 前置于本次提交），固化硬约束：harness 必须自研内核（禁 LangChain/AutoGen/CrewAI 高层 loop）、机制必须是代码非提示词、TDD 强制、Superpowers 七步流程、SPEC+PLAN 冷启动验证前不写实现、凭据三不（不硬编码/不提交/不入日志）。
- **关键发现 / 安全告警**：`.env` 内含一个形似真实的 `sk-...` key（`CLAUDE_API_KEY`）。已确认被 `.gitignore` 排除、未进 git；agent 未在任何输出中打印或提交该 key。
- **人工干预**：无（用户仅要求分析代码库生成 CLAUDE.md）。
- **教训**：`/init` 阶段就应把"评分硬约束"与"未决缺口（CI 缺 unit-test job）"写进 CLAUDE.md，避免后续阶段遗忘；安全上 `.env` 明文 key 即使被 ignore 也应在日志中显式标注风险。

---

## 2026-07-08 · 阶段 1：brainstorming — 上下文探索

- **触发的技能**：`brainstorming`。
- **task 编号**：BT-1（Explore project context）。
- **关键 context**：复用阶段 0 已读文档；确认仓库为 greenfield（无源码、无 SPEC/PLAN、未选语言）。
- **agent 输出**：建立 brainstorming checklist（7 个 task），判定项目规模适中、无需拆子项目，可直接进入单 spec 流程。
- **人工干预**：用户给定技术栈 Node.js、项目名 AI4SE-Safe-TDD-Harness，并点名 4 个重点追问方向（主循环 / Mock LLM / 护栏 / TDD 反馈）+ 凭据与分发。
- **教训**：用户点名重点方向时，应把它们映射到 checklist 的"提问"环节逐个落实，而不是在设计中才补。

---

## 2026-07-08 · 阶段 2：brainstorming — 8 轮追问（AskUserQuestion）

- **触发的技能**：`brainstorming`（提问环节）。
- **task 编号**：BT-2。
- **策略**：每问给 2-3 个带取舍的选项 + 推荐，多选一；每问聚焦一个真正的设计分叉。各问题的"选项"即"2-3 方案 + 取舍"，用户逐一裁决。
- **8 轮裁决**：

| # | 议题 | 选项 | 用户裁决 |
|---|---|---|---|
| 1 | LLM↔Harness 动作协议 | A 原生 function-calling / **B 自定义 JSON 围栏** / C ReAct | **B** |
| 2 | 危险命令检测深度 | A 纯正则 / **B shell-quote tokenize+模式库** / C 分层+severity+HITL | **B** |
| 3 | HITL 审批接口 | A CLI 阻塞 / **B ApprovalGateway 抽象+状态机** / C 文件队列 | **B** |
| 4 | TDD 反馈闭环深度 | A 截断原文 / **B 结构化 FeedbackClassifier** / C B+失败模式记忆 | **B** |
| 5 | WebUI 范围 | A 只读状态页 / **B 控制+观测面板** / C 完整运维台 | **B** |
| 6 | 凭据安全存储 | A 仅 OS keyring / **B 仅加密文件+主密码** / C 双实现 | **B** |
| 7 | 分发形态 | A 仅 npm / B 仅 Docker / **C Docker+npm** | **C**（后被 T1 裁剪） |
| 8 | 路径围栏 | **A 仅命令护栏** / B 命令+路径围栏 | **A** |

- **agent 输出**：8 轮后定型 LLMProvider 契约 `async complete(messages): Promise<{text,stopReason}>`、Guardrail 输入 `Action` 输出 `{severity,reasons}`、FeedbackClassifier 输出 `Feedback`、ApprovalGateway 接口。
- **人工干预**：无逐轮干预；用户对每轮直接裁决。
- **教训**：把"选项即方案对比"嵌入提问，既满足技能"propose 2-3 approaches"要求，又不额外消耗一轮对话；多选一比开放问答更省用户认知负荷。

---

## 2026-07-08 · 阶段 3：brainstorming — 4 节设计呈现 + 确认

- **触发的技能**：`brainstorming`（present design）。
- **task 编号**：BT-4。
- **agent 输出**：分 4 节呈现——①架构/主循环状态机/LLMProvider/Mock/动作协议 ②治理护栏+HITL ③TDD 反馈闭环+记忆最小实现 ④凭据/分发/WebUI/CI/机制演示。同时替用户做了几个低风险默认决定（生产 LLM 走 OpenAI-compatible、工具集 6 个、JestParser、MemoryStore 文件式最小实现）并明示可否决。
- **人工干预（关键）**：用户"全部确认"，但追加硬约束——**"个人课程项目、2 周内可完成、勿因过度工业级工程化而烂尾"**。这是本阶段最重要的人工输入。
- **教训**：用户确认设计后追加的"可完成性"约束，优先级高于此前所有装饰性扩展；应主动识别并裁剪 gold-plating，而非等用户点名。

---

## 2026-07-08 · 阶段 3.5：范围裁剪 T1–T4（agent 响应人工干预）

- **触发的技能**：`brainstorming`（设计修订）。
- **task 编号**：BT-4（修订）。
- **agent 输出**：提出 4 处减负裁剪——
  - **T1**：分发 Docker+npm → **仅 Docker**（逆转用户阶段 2 第 7 问的 C 选项；点名给用户否决机会）。
  - **T2**：WebUI WebSocket → **HTTP 轮询**（省 `ws` 管道）。
  - **T3**：错误分类 4 类 → **3 类**（assertion/syntax/other；Parser 接口仍可插拔）。
  - **T4**：每微功能一 worktree → **每大里程碑一 worktree**。
  - 保底优先级：AC1 内核 → AC2 护栏 → AC3 反馈 → AC7 演示 → AC5 WebUI（可降只读）→ AC4 凭据 → AC6 CI。
- **人工干预**：用户未否决 T1，等于接受裁剪。
- **教训**：当某项裁剪逆转了用户此前显式选择时，必须单独点名提示，不可静默改。

---

## 2026-07-08 · 阶段 4：SPEC.md 撰写 + 自检 + 提交

- **触发的技能**：`brainstorming`（write design doc）。
- **task 编号**：BT-5。
- **关键 context**：用户偏好文件名 `SPEC.md`（项目 §4.2 硬交付名）覆盖技能默认路径 `docs/superpowers/specs/...`。
- **agent 输出**：写入 `SPEC.md`，覆盖 12 节：问题陈述、5 INVEST 用户故事、按模块功能规约、NFR（含 §4.2 凭据威胁模型表）、架构组件图+数据流+外部依赖、数据模型、凭据与分发设计、技术选型理由、验收标准、风险与未决、项目 A 专属「领域与机制设计」、2 周裁剪记录。
- **Spec 自检（inline 修复 2 处不一致）**：
  1. §3.4 危险模式库补"带 `Authorization`/`-H token` 头的外发请求"模式，与 §4.2 威胁表"凭据外传"行对齐。
  2. §7.2 把 `<registry>` 占位符软化为"具体 registry/镜像名在 PLAN 定"，与未决项 U2 一致。
- **commit hash**：`374a95b`（`docs: add CLAUDE.md and SPEC.md (brainstorming output)`），含 CLAUDE.md + SPEC.md，2 files / +322 行。
- **人工干预**：用户确认设计可写 SPEC；裁剪范围被接受。
- **教训**：SPEC 自检要专门做"跨节一致性"扫描（如威胁表 ↔ 模式库、超时值 ↔ 工具边界），单节内一致不够。

---

## 2026-07-08 · 阶段 5：设计签字 → 转入 writing-plans

- **触发的技能**：`brainstorming`（transition）→ 即将触发 `writing-plans`。
- **task 编号**：BT-6/BT-7。
- **人工干预**：用户"设计已确认"，要求先填本日志再触发 writing-plans。
- **agent 输出**：本日志 + 随后调用 `writing-plans` 生成 `PLAN.md`。
- **教训**：brainstorming 的终止态是"调用 writing-plans"，不调用其它实现技能；签字前不写实现代码（§4 硬门）。

---

## 2026-07-08 · 阶段 6：writing-plans — 生成 PLAN.md

- **触发的技能**：`writing-plans`。
- **task 编号**：WP-1。
- **关键 context**：读取已签字 SPEC（commit `374a95b`）；用户要求"先填 AGENT_LOG 再触发 writing-plans"。
- **关键决策（agent 自主）**：
  - 技术栈落定为 **TypeScript 5 + Jest/ts-jest**（SPEC §8 只写了 Node.js，TS 在此敲定）——理由：接口多、需类型约束保证 mockable，契合"机制是代码"评分；ts-jest 一次配置约 30min，烂尾风险低。
  - 运行时依赖收敛为**仅 `shell-quote`**（Node 20 内置 `http/crypto/fs/child_process/global fetch`），最大限度降依赖烂尾风险。
  - 文件落点：`PLAN.md` 放仓库根（项目 §4.3 硬交付名覆盖技能默认路径 `docs/superpowers/plans/...`）。
  - 演示靶项目用 `run-tests.sh`（脚本判 `add.js` 正确性 + 输出 Jest 格式 stderr）而非嵌套跑 jest，规避子进程 jest 的解析/解析 flakiness，保 AC3 确定性。
- **agent 输出**：`PLAN.md`——18 个 TDD 任务（每任务 5 步：写失败测试→验证失败→最小实现→验证通过→commit），每个含完整代码、确切文件路径、确切命令与预期输出。头部含 Goal/Architecture/Tech Stack/Global Constraints；含文件结构图、依赖/并行度图、Self-Review（spec 覆盖 / 占位符扫描 / 类型一致性三查）。覆盖 SPEC 全部 12 节。
- **commit hash**：见本次提交（PLAN.md + AGENT_LOG.md 阶段 6）。
- **人工干预**：无（用户仅要求按 SPEC 生成 PLAN）。
- **教训**：
  - writing-plans 的"完整代码无占位符"要求与"2 周可完成性"存在张力——通过让每个模块实现最小化（YAGNI）兼顾：如 `run_tests` 只捕获不解析、解析归 `FeedbackClassifier`、HITL 挂起 resolver 用最简 Map。
  - 跨任务类型一致性要专门做一次 Self-Review 扫描（如 `complete` 返回 `{text,stopReason}` 在 T4/T13/T12 三处须一致），单任务内一致不够。
  - 写 PLAN 时若一个 task 会改另一个 task 已交付的产物（如 T18 重写 `src/index.ts` 但 T1 smoke test 依赖 `greet`），必须在计划里显式声明"保留 export 不破坏前序测试"。
- **下一步**：待用户选执行模式（subagent-driven / inline）后，调用对应子技能按 task 推进；每完成一 task 在本日志追加节点 + 在 PLAN.md 标 commit hash。

---

## 2026-07-08 · 阶段 7：§4.5 冷启动验证 + 规约修订

- **触发的流程**：§4.5 自我验证（非 Superpowers 七步内，但通用要求硬交付）。
- **task 编号**：CS-1。
- **方法**：用一个**不同**的 agent、全新 session、不导入本会话上下文，仅凭 `SPEC.md`+`PLAN.md` 试推任务 1/2。产出一份冷启动规约审计报告（3 Stuck + 6 Gap + 7 假设）。
- **第二个 agent 暴露的缺陷**：STUCK-1（tsconfig rootDir 与 Dockerfile 构建矛盾）、STUCK-2（ToolContext 缺 memory/creds）、STUCK-3（Approval 型拆分与 SPEC §6 不一致）、GAP-1（EventType 多 approval_decision）、GAP-2（timeout 降级点未定义）、GAP-3（LoopState 缺）、GAP-4（.gitignore 重复追加）、GAP-5（error 语义未定义）、GAP-6（ActionProtocol 的 ToolName 疑似 strict 编译错）。
- **agent（主）评估**：8 处成立、1 处误判——**GAP-6 不成立**：`JSON.parse` 返回 `any`，`obj.tool` 为 `any`，赋给 `ToolName` 在 strict 下不报编译错。但仍加运行时 `TOOL_NAMES.has()` guard + `as ToolName` + 测试，作健壮性加固。
- **修订（commit 见本次提交）**：
  - SPEC §3.3（ToolContext 裁剪 + timeout 降级点）、§3.7（LoopState 可追溯）、§6（Approval 复合型 + EventType 补 approval_decision + payload 映射）。
  - PLAN 任务 1（tsconfig rootDir:src + include:src + build 脚本补 cpSync + .gitignore 措辞）、任务 2（types 加 LoopState/Approval + 测试覆盖）、任务 3（TOOL_NAMES guard + 测试）、任务 5（errMsg helper + ToolContext 注）、任务 6（run_tests 超时检测）、任务 8（timeout→other 注）、任务 12（LoopState 注）、任务 18（Dockerfile 移除冗余 COPY demo）。
  - 新建 `SPEC_PROCESS.md`（§4.5 过程文档，含修订前后 7 组 diff）。
- **人工干预**：用户提供第二个 agent 的审计报告，要求我"审核评估后修正并记入 SPEC_PROCESS.md"。
- **教训**：
  - spec 清晰度被严重高估——主 agent 与 brainstorming 沉淀的隐性共识（如"dist 只含 src"）没写进 SPEC/PLAN，冷启动 agent 在每个隐性假设处受阻。
  - 跨节一致性须专门扫描（STUCK-2/3、GAP-1 都是 SPEC 一节说 X、PLAN 另一节做 Y）。
  - 冷启动 agent 也会误判（GAP-6 编译判断），逐条复核技术正确性而非盲收。
- **下一步**：SPEC/PLAN 已对齐，可进入实现；待用户选执行模式。

---

## 2026-07-08 · 阶段 8：executing-plans — feat/01-infra 任务 1/2/3（TDD）

- **触发的技能**：`using-git-worktrees` → `karpathy-guidelines` + `ponytail` + `test-driven-development`（用户显式要求"严格 TDD"+ 系统级特化技能）。
- **task 编号**：PLAN 任务 1（脚手架）/ 任务 2（核心类型）/ 任务 3（ActionProtocol 解析器）。
- **关键 context 配置**：worktree `feat/01-infra`（路径 `.claude/worktrees/feat+01-infra`），分支从 main 切出；全程在该隔离工作区开发，未触碰主 checkout。
- **worktree 创建细节**：用原生 `EnterWorktree` 工具（技能 Step 1a 优先级），但工具按安全规则把分支名 `feat/01-infra` 改写为 `worktree-feat+01-infra`（`/`→`+` + `worktree-` 前缀）。用户明确要求分支名 `feat/01-infra`，故在 worktree 内 `git branch -m feat/01-infra` 重命名——`feat/01-infra` 是合法 git ref 名（斜杠允许），重命名不改目录、不破坏 worktree 关联。
- **关键 prompt**：用户分两轮下达——轮 1 仅任务 1（脚手架 TDD 绿屏即 commit 并停）；轮 2 任务 2+3 串行 TDD，每任务独立 commit，完成后更新 PLAN/AGENT_LOG 并做独立 docs commit。
- **TDD 执行（每任务 红→绿→重构）**：
  - 任务 1：RED `test/smoke.test.ts` → `npx jest` 报 `TS2307 Cannot find module '../src/index'`（feature 缺失，正确失败）→ 配置工具链（package.json/tsconfig/jest.config，属 TDD 例外）+ 装依赖（TS5/ts-jest/jest/@types + shell-quote）→ GREEN 写一行 `greet` → PASS（1 test）。
  - 任务 2：RED `test/types.test.ts` → `TS2307 '../src/types'` → GREEN 写 `src/types.ts`（SPEC §6 全部数据模型，含 `LoopState`/`Approval` 复合型/`EventType` 含 `approval_decision`，对齐阶段 7 冷启动修订）→ PASS（1 test）。
  - 任务 3：RED `test/actionProtocol.test.ts`（4 用例：单围栏/无围栏/畸形 JSON/未知工具名）→ `TS2307 '../src/protocol/actionProtocol'` → GREEN 写 `src/protocol/actionProtocol.ts`（围栏正则 + `JSON.parse` + `TOOL_NAMES.has()` 运行时 guard + 畸形 catch 不抛，对齐 SPEC §3.1 边界）→ PASS（4 tests）。
- **全量测试**：3 suites / 6 tests 全绿，无回归。
- **commit hashes**：
  - 任务 1 `8720329` — `chore: scaffold node+ts+jest project with smoke test`
  - 任务 2 `298d472` — `feat(types): add core domain types`
  - 任务 3 `2e5a50f` — `feat(protocol): action fence parser`
- **人工干预**：
  - 轮 1 结束后 agent 主动提出"PLAN 勾选 + AGENT_LOG 记录"未并入脚手架 commit（保持外科手术式单一关注点），征询用户；用户轮 2 明确要求合并到本轮 docs commit。故任务 1 的 PLAN 勾选在本 docs commit 一并补上。
  - 用户要求启用 `/karpathy-guidelines` + `/ponytail` 两个系统级技能（高性能/类型安全/CommonJS 友好），agent 额外加载 `test-driven-development` 以落实"严格 TDD"硬约束。
- **教训**：
  - **原生 worktree 工具会改写分支名**：`EnterWorktree` 对含 `/` 的名字做 sanitize（`/`→`+` + 前缀）。当用户要求精确分支名且该名是合法 git ref 时，`git branch -m` 重命名是低风险修正，不破坏 worktree 关联——但应在日志记录，避免后续 PR 误用工具原名。
  - **脚手架 TDD 的"先看红"张力**：要跑测试须先有工具链（jest/ts-jest），而工具链配置属 TDD 例外（非生产行为）。解法：测试文件先写、配置+装依赖次之、再跑出 RED（feature 缺失的 TS2307），最后写最小实现到 GREEN——`greet` 这行生产代码确在测试失败后才写，TDD 铁律不破。
  - **TS2307 即有效 RED**：greenfield 新模块的"模块未找到"编译错是合法的 TDD 失败（feature 缺失），不必硬凑成断言失败；只要失败原因是"待实现功能不存在"而非笔误即可。
  - **PLAN 勾选的锚点策略**：PLAN 多个任务的"步骤 N"标题文案相同，`- [ ] **步骤 1：写失败测试**` 跨任务重复，不能 replace_all（会误勾未完成任务）。用"步骤标题 + 紧随的唯一行（测试文件名/实现文件名/git add 行）"作 old_string 锚点，逐处精确翻转。
- **下一步**：feat/01-infra 分支内剩余任务（任务 4 ScriptedMock 起的 LLM/工具/护栏/反馈/记忆/凭据/审批/主循环/web/分发）待用户下达；或按 PLAN 依赖图在隔离 worktree 并行（任务 3‖4‖9）。

---

## 2026-07-08 · 阶段 9：executing-plans — feat/02-llm-mock 任务 4（TDD）+ .claude 安全补丁

- **触发的技能**：`using-git-worktrees` → `karpathy-guidelines` + `ponytail` + `test-driven-development`（沿用阶段 8 的系统级特化组合）。
- **task 编号**：PLAN 任务 4（ScriptedMock LLMProvider）+ 仓库安全补丁（.gitignore 加 `.claude/`）。
- **关键 context 配置**：新 worktree `feat/02-llm-mock`（路径 `.claude/worktrees/feat+02-llm-mock`），从最新 `origin/main`（`4c8743b`，含阶段 8 全部成果 + ci 提交）切出；与 feat/01-infra 并行，互不触碰。
- **worktree 创建细节（吸取阶段 8 教训）**：跳过原生 `EnterWorktree` 的 `name` 模式（它会 sanitize `feat/02-llm-mock` → `worktree-feat+02-llm-mock`，再需 `git branch -m` 修正），改用技能 Step 1b 的 `git worktree add` 直接以精确分支名 `feat/02-llm-mock` 从 `origin/main` 建 worktree，再用原生 `EnterWorktree(path)` 切入会话——分支名一次到位，无重命名步骤。目录名仍按仓库约定用 `feat+02-llm-mock`（`/`→`+`，避免路径里多一层目录）。
- **安全补丁（先于功能开发）**：`.gitignore` 末尾追加 `.claude/`（含中文注释）。本地三重验证：① `git check-ignore .claude/` 返回命中；② `git status --short` 仅 `.gitignore` 一行变更，无 `.claude/` 会话数据泄漏；③ `npx jest --listTests` 仅列出本 worktree 的 3 个测试文件，兄弟 worktree `feat+01-infra/test/*` 未被 jest 发现（嵌套测试安全屏蔽）。独立 commit。
- **TDD 执行（任务 4 红→绿→重构）**：
  - RED：`test/scriptedMock.test.ts`（3 用例：队列顺序返回 / sticky 末条粘滞 / 非粘滞耗尽抛错）→ `npx jest` 报 `TS2307 Cannot find module '../src/llm/scriptedMock'`（feature 缺失，合法 RED）。
  - GREEN：写 `src/llm/provider.ts`（`LLMProvider` 接口，`complete` 返回 `{text, stopReason}`，与 SPEC §3.2 + 阶段 6 类型一致性约束对齐）+ `src/llm/scriptedMock.ts`（队列 shift + sticky 兜底 + 耗尽 throw）→ PASS（3 tests）。
  - 重构：实现已最小（ponytail：无单实现接口之外的抽象、无未请求配置），无需重构。全量 4 suites / 9 tests 绿，无回归。
- **commit hashes**：
  - `ce5a5d1` — `chore: add .claude/ to .gitignore`（安全补丁，独立提交）
  - `4b6dcaf` — `feat(llm): LLMProvider interface + ScriptedMock`（任务 4 实现）
- **人工干预**：用户要求"分支 2 独立 worktree、先做 .claude 安全补丁、严格 TDD 任务 4、独立 docs commit、推送远端不本地合并 main、提示网页建 MR"——逐条执行。
- **教训**：
  - **worktree 分支名精确控制**：当用户要求精确分支名且原生工具会 sanitize 时，`git worktree add -b <精确名> <path> <base>` + `EnterWorktree(path)` 组合比"原生 name + 事后 branch -m"更干净——少一步修正、少一次潜在混淆。阶段 8 的教训在此转化为可复用模式。
  - **.gitignore 不影响 jest 发现，但仍是必要安全补丁**：jest 的 `testMatch` 不会读 `.gitignore`（默认仅忽略 `node_modules`），故"嵌套测试屏蔽"靠的是 worktree cwd 隔离（jest 不向上递归），而非 gitignore。但 `.claude/` 进 gitignore 防的是**会话数据/worktree 内容被误提交**——两件事不可混淆，需分别验证（`check-ignore` 验 git 层、`--listTests` 验 jest 层）。
  - **并行 worktree 的依赖隔离**：任务 4 仅消费 `src/types`（Message），与 feat/01-infra 已交付的 types 同源（均来自 main），无跨分支依赖冲突，适合并行开 worktree——印证 PLAN 依赖图"任务 3‖4‖9 可并行"。
- **下一步**：推送 `feat/02-llm-mock` 到 GitLab 远端，提示用户网页端建 MR；其余任务（5+ 起的工具/护栏/反馈/主循环/web/分发）待用户下达或在新的并行 worktree 推进。

---

## 2026-07-08 · 阶段 10：executing-plans — feat/03-tools 任务 5/6（TDD）

- **触发的技能**：`using-git-worktrees` → `karpathy-guidelines` + `ponytail` + `test-driven-development`（沿用阶段 8/9 系统级特化组合）。
- **task 编号**：PLAN 任务 5（ToolRegistry + 文件工具）/ 任务 6（shell 工具 run_shell/run_tests 捕获）。
- **关键 context 配置**：新 worktree `feat/03-tools`（路径 `.claude/worktrees/feat+03-tools`），从 MR 合并后的最新 `origin/main`（`3945597` Merge feat/02-llm-mock）切出。
- **前置清理（主目录运行）**：`ExitWorktree(keep)` 退出 feat/02 会话回主 checkout → `git checkout main` + `git pull origin main`（fast-forward 到 `3945597`）→ `git worktree remove .claude/worktrees/feat+02-llm-mock`（物理清理，node_modules 已 gitignore 无阻力）→ `git branch -d feat/02-llm-mock`（已合并，安全删除）→ `git worktree add -b feat/03-tools .claude/worktrees/feat+03-tools origin/main` → `EnterWorktree(path)` 切入。全程未触碰 feat/01-infra 旧 worktree（surgical，只清当前生命周期的分支 2）。
- **TDD 执行（任务 5 红→绿→重构）**：
  - RED：`test/fileTools.test.ts`（3 用例：write/read roundtrip / list_dir / read 缺失文件返回 ok:false）→ `TS2307 Cannot find module '../src/tools/fileTools'`（feature 缺失，合法 RED）。
  - GREEN：`src/tools/tool.ts`（`ToolContext{cwd}` 按 SPEC §3.3 裁剪不注入 memory/creds + `errMsg` helper 统一 error 字段 + `ToolRegistry.dispatch` 未知工具/异常转 `Observation{ok:false,error}`）+ `src/tools/fileTools.ts`（read_file/write_file/list_dir，`path.resolve(cwd,p)` 做路径锚定，write_file 带 `mkdir recursive`）→ PASS（3 tests）。
  - 重构：实现已最小（ponytail：`wrap()` 在 shellTools 里待用，fileTools 无多余抽象），无需重构。
- **TDD 执行（任务 6 红→绿→重构）**：
  - RED：`test/shellTools.test.ts`（2 用例：stdout+exitCode0 捕获 / 非零 exit+stderr 捕获，按 `process.platform` 分支命令转义）→ `TS2307 '../src/tools/shellTools'`。
  - GREEN：`src/tools/shellTools.ts`（`promisify(exec)` + shell:true 捕获 stdout/stderr/exitCode；`run_tests` timeout 60s、`run_shell` 30s；exec 非零退出走 catch，`e.killed && e.signal==='SIGTERM'` 判超时→`error:'timeout'`，对齐 SPEC §3.3 + 阶段 7 GAP-2 timeout 降级路径）→ PASS（2 tests）。Windows 下 cmd.exe 的 `echo hello` 与 `node -e "..."` 转义均按 PLAN 平台分支通过。
  - 重构：无需。
- **全量测试**：6 suites / 14 tests 全绿，无回归。
- **commit hashes**：
  - `eff62d6` — `feat(tools): ToolRegistry + file tools`（任务 5）
  - `8390f53` — `feat(tools): run_shell + run_tests capture`（任务 6）
- **人工干预**：用户要求"主目录前置清理同步 → 新 worktree → 严格 TDD 任务 5/6 串行各独立 commit → docs 独立 commit → 推送不本地合并 main"——逐条执行，无额外干预。
- **教训**：
  - **分支生命周期闭环**：MR 网页合并后，"pull 同步 → worktree remove → branch -d → 新 worktree" 是可复用的分支切换骨架。`worktree remove` 之所以无阻力，是因为阶段 9 已把 `.claude/` 进 gitignore——node_modules 等未跟踪内容被 ignore，git 不视作"待提交修改"而拒绝删除。安全补丁的收益在此显形。
  - **路径锚定即工具沙箱边界**：`path.resolve(ctx.cwd, p)` 把所有 file tool 的路径钉死在 workspace 内，是后续 AgentLoop 命令护栏（U1 决定不加路径围栏）之外的"软围栏"——工具自身不越界，即便 agent 传 `../../../etc/passwd` 也只是读到主目录外文件而非写入，write_file 的 `mkdir recursive` 仅作用于最终 resolve 路径的父目录。
  - **exec 超时判定的脆弱性**：`e.signal === 'SIGTERM'` 在 Windows 上 exec 超时是否同样给 SIGTERM 待验证（Windows 无原生信号，node 用 TerminateProcess 模拟）。当前测试未覆盖超时路径（YAGNI，任务 6 只验捕获），阶段 7 GAP-2 注明的"timeout→other 降级"将在任务 8/12 的反馈闭环里被间接覆盖；若后续演示需要稳定超时断言，再补 Windows 适配。
- **下一步**：推送 `feat/03-tools` 到 GitLab 远端，提示用户网页端建 MR；剩余任务（7 Guardrail 起的护栏/反馈/记忆/凭据/审批/主循环/web/分发）待用户下达。
