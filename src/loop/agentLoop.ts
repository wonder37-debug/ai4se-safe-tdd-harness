import { LLMProvider } from '../llm/provider';
import { ToolRegistry, ToolContext } from '../tools/tool';
import { Guardrail } from '../guardrail/guardrail';
import { ApprovalGateway } from '../approval/approvalGateway';
import { FeedbackClassifier } from '../feedback/feedbackClassifier';
import { MemoryStore } from '../memory/memoryStore';
import { ActionProtocol } from '../protocol/actionProtocol';
import { Action, Message, Observation, SessionState } from '../types';
import { EventSink, noopSink } from './eventSink';

export interface LoopDeps {
  llm: LLMProvider;
  registry: ToolRegistry;
  guardrail: typeof Guardrail;
  approval: ApprovalGateway;
  feedback: FeedbackClassifier;
  memory: MemoryStore;
  cwd: string;
  maxIter: number;
  systemPrompt: string;
  sink?: EventSink;
}

type HaltReason = 'finish' | 'cap' | 'stuck' | 'provider_error';

export class AgentLoop {
  private messages: Message[];
  private sink: EventSink;
  // 会话状态：供 Guardrail 做状态感知评估（拒绝后的删除尝试动态升级 high）
  private session: SessionState = { lastDenied: false };
  constructor(private deps: LoopDeps) {
    this.sink = deps.sink ?? noopSink;
    this.messages = [{ role: 'system', content: deps.systemPrompt }, { role: 'user', content: 'complete the task using tools' }];
  }

  async run(): Promise<{ haltReason: HaltReason; iterations: number }> {
    // memory 注记为异步读取（Task 10），构造器无法 await，改在首次运行时拼入 system prompt
    const mem = await this.deps.memory.systemPrompt();
    if (mem) this.messages[0].content += '\n\n' + mem;
    let iter = 0;
    let lastFailKey: string | null = null;
    let sameCount = 0;
    while (iter < this.deps.maxIter) {
      iter++;
      let resp;
      try { resp = await this.deps.llm.complete(this.messages); }
      catch (e: any) {
        const errMsg = `provider_error: ${String(e?.message ?? e)}`;
        this.sink.emit({ type: 'halt', payload: { reason: 'provider_error', error: errMsg }, iter });
        return { haltReason: 'provider_error', iterations: iter };
      }
      this.messages.push({ role: 'assistant', content: resp.text });
      const acts = ActionProtocol.parse(resp.text);
      if (acts.length === 0) {
        this.messages.push({ role: 'user', content: 'Observation: no action block found; emit a fenced ```action {...}``` block' });
        continue;
      }
      const action = acts[0];
      this.sink.emit({ type: 'action', payload: action, iter });

      if (action.tool === 'finish') {
        this.sink.emit({ type: 'halt', payload: { reason: 'finish' }, iter });
        return { haltReason: 'finish', iterations: iter };
      }

      // 护栏（携带会话状态：上一轮刚被拒绝时，删除类命令被动态升级为 high）
      const verdict = this.deps.guardrail.assess(action, this.session);
      let effective: Action = action;
      if (verdict.severity === 'high') {
        // SPEC §6：先广播审批请求，再悬停等待裁决（web/CLI 前端据此展示待审批项）
        this.sink.emit({ type: 'approval_request', payload: { action, reasons: verdict.reasons }, iter });
        const dec = await this.deps.approval.request(action, verdict.reasons);
        this.sink.emit({ type: 'approval_decision', payload: dec, iter });
        if (dec.decision === 'deny') {
          this.session.lastDenied = true; // 记录拒绝：下一轮删除尝试将被强制拦截
          this.messages.push({ role: 'user', content: `Observation: DENIED: ${dec.reason} (reasons: ${verdict.reasons.join('; ')})` });
          continue;
        }
      } else if (verdict.severity === 'low') {
        this.messages.push({ role: 'user', content: `Observation: WARN(low): ${verdict.reasons.join('; ')}` });
      }

      // 执行（动作已通过门禁：清除“刚被拒绝”状态，恢复日常无打扰评级）
      this.session.lastDenied = false;
      const ctx: ToolContext = { cwd: this.deps.cwd };
      const obs = await this.deps.registry.dispatch(effective, ctx);

      // run_tests 失败的反馈闭环
      if (action.tool === 'run_tests' && obs.exitCode !== 0) {
        const fb = this.deps.feedback.parse(obs);
        const key = fb.assertion ? `${fb.assertion.file}:${fb.assertion.line}` : fb.errorType;
        if (key === lastFailKey) { sameCount++; } else { sameCount = 1; lastFailKey = key; }
        const content = JSON.stringify(fb);
        this.messages.push({ role: 'user', content: `Observation: ${content}` });
        this.sink.emit({ type: 'observation', payload: fb, iter });
        if (sameCount >= 2) {
          this.sink.emit({ type: 'halt', payload: { reason: 'stuck', key }, iter });
          return { haltReason: 'stuck', iterations: iter };
        }
      } else {
        this.messages.push({ role: 'user', content: `Observation: ${JSON.stringify(obs)}` });
        this.sink.emit({ type: 'observation', payload: obs, iter });
      }
    }
    this.sink.emit({ type: 'halt', payload: { reason: 'cap' }, iter });
    return { haltReason: 'cap', iterations: iter };
  }
}
