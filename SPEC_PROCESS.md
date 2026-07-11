# SPEC_PROCESS.md

> §4.5「自我验证：用陌生智能体冷启动试运行」的过程文档。
> 记录与 Superpowers 协作生成 spec/plan 的过程、以及用一个**不同** agent 冷启动暴露的 spec 缺陷与修订。

---

## 一、brainstorming 关键节点

启动 `brainstorming` 技能后，智能体主动追问，分块呈现设计供逐步签字。关键好问题与由此修正的原设想：

1. **"动作协议选哪种？"** —— 我原倾向用供应商原生 function-calling（最贴近生产）。智能体追问后我意识到：原生协议会把解析逻辑外包给供应商 SDK，而本项目评分标准是"机制必须是自己的代码"。遂改选**自定义 JSON 围栏协议**（B），parser 是我们自写的、mock 只需返回字符串。
2. **"护栏检测做到什么深度？"** —— 我原想纯正则黑名单最快。智能体给出 `r""m`/base64 管道等绕过案例后，我改选 **shell-quote tokenize + 危险模式库**（B），在 token 层匹配，揭穿混淆——这是治理维度工程深度的核心。
3. **"WebUI 做到什么程度？"** —— 我原以为 CLI harness 不需要 WebUI。智能体指出 §五 item 9 是硬交付（"必须提供可访问 WebUI 接口"），这改变了整体架构：`ApprovalGateway` 生产实现从 readline 变 HTTP handler，需加 HTTP server + 事件流。
4. **"凭据存储做到哪种？"** —— 我原想直接 OS keyring。智能体追问 Docker 容器内无宿主 keyring 后，改选**仅加密文件 + 主密码**（B），容器友好、纯 Node `crypto`。

至少 3 轮关键迭代的对话节选见 `AGENT_LOG.md` 阶段 2 的 8 轮裁决表。

## 二、AI 提出而我采纳的建议

- 自定义 JSON 围栏协议（替代原生 function-calling）——采纳，理由见上。
- `ApprovalGateway` 抽象 + 状态机（替代 CLI 阻塞 prompt）——采纳，使 HITL 可离线单测。
- 结构化 `FeedbackClassifier`（替代截断原文回灌）——采纳，使反馈闭环成为"代码机制"。
- 演示靶用 `run-tests.sh` 而非嵌套跑 jest——采纳（PLAN 阶段决策），规避子进程 jest 的 flakiness。

## 三、我推翻或修正的 AI 建议

- AI 建议分发用"Docker + npm 双分发"。我以"可完成性"为由**裁剪为仅 Docker**（T1），因 npm publish 是额外发包流水线、评分不增量。
- AI 建议 WebSocket 实时推送。我**改为 HTTP 轮询**（T2），省 `ws` 管道。
- AI 建议 4 类错误分类。我**收敛为 3 类**（T3）。

反思：brainstorming 技能在本项目里最发挥作用的是"每问给 2-3 带取舍的选项 + 推荐"——它逼我在每个分叉点显式权衡而非含糊带过。让我不满的是：它对"可完成性"这条约束不敏感，倾向堆工业级设计（双分发、WebSocket、4 类分类），若非我主动裁剪会膨胀。裁剪责任在人，不在技能。

---

## 四、冷启动验证（§4.5 核心客观证据）

### 4.1 方法
- **第二个 agent**：用一个与主开发不同的 agent（冷启动审计 agent），启动全新 session、**不导入本会话历史或 memory**。
- **仅提供** `SPEC.md` + `PLAN.md`，不补充口头解释。
- **指定任务**：从 PLAN 选任务 1（脚手架）+ 任务 2（核心类型）试推进，明确"遇到不确定即暂停提问"。
- **产出**：一份冷启动规约审计报告，含 3 个亮红灯（Stuck）、6 个漏洞（Gap）、7 条假设。

### 4.2 第二个 agent 在哪里暂停并提问（暴露的 spec 缺陷）

| 编号 | 暂停点 | 暴露的 spec 缺陷 |
|---|---|---|
| STUCK-1 | `tsconfig rootDir:"."` + `include:["src","test","demo"]` 会使 `tsc` 把 test/demo 编进 `dist/`，而 Dockerfile 只 COPY src → 构建产物不一致、`__dirname` 解析层级在测试 vs 构建后不同 | SPEC/PLAN 未定义 build 产物边界 |
| STUCK-2 | `ToolContext` 只有 `cwd`，但 SPEC §3.3 说 ctx 含 `cwd`/`MemoryStore`/`CredentialStore` | SPEC §3.3 与 PLAN 实现不一致 |
| STUCK-3 | SPEC §6 有统一 `Approval` 型，PLAN 拆成 `ApprovalRequest`/`ApprovalDecision` 且无 `Approval` 名 | 数据模型不可追溯 |
| GAP-1 | PLAN 的 `EventType` 多出 `approval_decision`，SPEC §6 未列 | SPEC↔PLAN 不一致 |
| GAP-2 | `ErrorType` 不含 `timeout`，但 SPEC §3.3 提 `timeout→other`，未说降级发生在哪 | 机制边界模糊 |
| GAP-3 | SPEC §3.7 定义四态枚举，PLAN `types.ts` 无 `LoopState` | 规约级类型缺失 |
| GAP-4 | PLAN 任务 1 说"向 .gitignore 追加 dist/、*.log"，但仓库已存在这两行 | 机械照做会重复 |
| GAP-5 | `Observation.error` 填充规范未定义（非 Error 对象会产出 `[object Object]`） | 契约不清 |
| GAP-6 | `ActionProtocol.parse` 把 `obj.tool`（string）赋给 `ToolName`，审计疑为 strict 编译错 | 类型安全疑点（见 4.3 评估） |

### 4.3 我的评估（接受 / 驳回）

第二个 agent 的判断**大部分成立**，但有一条**误判**，我据实驳回：

- **GAP-6（驳回"会编译报错"）**：`JSON.parse` 返回 `any`，故 `obj.tool` 为 `any`，赋给 `ToolName` 字面量联合型在 TS strict 下**不报编译错**（`any` 可赋给任何类型）。第二个 agent 此处判断有误。**但**其底层关切（运行时可能产生非法工具名）成立，故我仍加 `TOOL_NAMES.has()` 运行时 guard + `as ToolName` 断言，并补一条测试。
- 其余 STUCK-1/2/3、GAP-1/2/3/4/5 **均接受**并已修正（见 4.4）。

### 4.4 修订前后关键 diff

**Diff-1（STUCK-1）：tsconfig + build 产物边界**

修订前（PLAN 任务 1）：
```json
{ "rootDir": ".", "include": ["src", "test", "demo"] }
"build": "tsc"
```
修订后：
```json
{ "rootDir": "src", "include": ["src"], "exclude": ["node_modules", "dist"] }
"build": "tsc && node -e \"…cpSync('src/web/public','dist/web/public',…)…\""
```
理由：`dist/` 只含 src 产物；test/demo 由 ts-jest 独立编译；build 脚本补拷 `public` 静态资源，使本地 `node dist/index.js --web` 与 Docker 一致。Dockerfile 同步移除冗余 `COPY demo ./demo`（镜像内无用）。

**Diff-2（STUCK-2）：ToolContext 裁剪**

修订前（SPEC §3.3）：`ctx 含 cwd、MemoryStore、CredentialStore。`
修订后：`ctx 含 cwd；MemoryStore/CredentialStore 由 AgentLoop 直接持有，不注入 ToolContext（YAGNI 裁剪）。`
PLAN 任务 5 `tool.ts` 加同名注释。理由：当前无 tool 需要它们；契合"2 周别烂尾"优先级；后续若有 tool 需凭据/记忆再扩 `ctx`。

**Diff-3（STUCK-3 + GAP-1）：Approval 复合型 + EventType 对齐**

修订前（SPEC §6）：
```
Approval = {id, action, reasons, decision?, reason?}
Event.type = 'action'|'observation'|'approval_request'|'halt'
```
修订后：
```
Approval = ApprovalRequest & Partial<ApprovalDecision>
Event.type = 'action'|'observation'|'approval_request'|'approval_decision'|'halt'
```
PLAN 任务 2 `types.ts` 新增 `export type Approval = ApprovalRequest & Partial<ApprovalDecision>;`。SPEC §6 补 `approval_decision`（前端轮询审批结果用）及 payload 类型映射。

**Diff-4（GAP-3）：LoopState 类型**

修订前：无。
修订后：PLAN 任务 2 `types.ts` 新增 `export type LoopState = 'RUNNING'|'APPROVAL_PENDING'|'EXECUTING'|'HALTED';`；SPEC §3.7 注明"循环内部以控制流位置编码四态，LoopState 仅作规约可追溯"。任务 12 加同名说明。

**Diff-5（GAP-2 + GAP-5）：timeout 降级 + error 语义**

修订前：`run_tests 超时 → errorType:'timeout'→'other'`（未说在哪降级）；`error: String(e?.message ?? e)`。
修订后：
- PLAN 任务 6 `run_tests` catch 检测 `e.killed && e.signal==='SIGTERM'` → `error:'timeout'`、`exitCode:-1`。
- PLAN 任务 8 注：`FeedbackClassifier` 经 `JestParser` 无匹配 → `'other'`（timeout→other 降级点在此）。
- PLAN 任务 5 `ToolRegistry.dispatch` 改 `e instanceof Error ? e.message : String(e)`，避免非 Error 对象产出 `[object Object]`，并在 `tool.ts` 注明 error 填充规范。

**Diff-6（GAP-4）：.gitignore 措辞**

修订前（PLAN 任务 1）："向 .gitignore 追加 dist/ 与 *.log。"
修订后："确认 .gitignore 已包含 dist/ 与 *.log（本仓库已存在，第 3-4 行）；勿重复追加。"

**Diff-7（GAP-6）：ActionProtocol 运行时 guard**

修订前：`if (obj && typeof obj.tool === 'string' ...) out.push({ tool: obj.tool, args });`
修订后：加 `TOOL_NAMES = new Set([...])`，`&& TOOL_NAMES.has(obj.tool)`，`out.push({ tool: obj.tool as ToolName, args })`，补测试"非法工具名被拒"。并注明：编译本就不报错（any），guard 是运行时健壮性加固。

### 4.5 产出与预期差距
第二个 agent 未实际编码，而是停在"对 PLAN 任务 1/2 做规约审计"层面就提出 9 处质疑——这恰是冷启动的价值：它在每个未明文写下的假设处受阻。9 处中 8 处成立、1 处（GAP-6 编译判断）误判。修订后 SPEC↔PLAN 在 build 边界、ToolContext、数据模型、EventType、LoopState、timeout、error 语义七处达成一致。

### 4.6 教训
- **spec 清晰度被严重高估**：我与主 agent 在 brainstorming 沉淀了大量隐性共识（如"dist 只含 src"本是我的默认假设），却没写进 SPEC/PLAN。冷启动 agent 在每个隐性假设处都受阻——这是单人项目里最接近同侪评审的信号。
- **要专门做"跨节一致性"扫描**：STUCK-2/3、GAP-1 都是 SPEC 一节说了 X、PLAN 另一节做了 Y 的跨节不一致，单节内自洽不够。
- **冷启动 agent 也会误判**（GAP-6）：盲目接受其所有结论与盲目忽略一样有害；需逐条复核技术正确性。
- **"机制是代码"标准反向救场**：GAP-6 即使编译不报错，加 guard 也使"非法工具名"成为可确定性单测的行为——契合 §A.4-C。
