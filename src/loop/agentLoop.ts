import { LLMProvider } from '../llm/provider';
import { ToolRegistry, ToolContext } from '../tools/tool';
import { Guardrail } from '../guardrail/guardrail';
import { ApprovalGateway } from '../approval/approvalGateway';
import { FeedbackClassifier } from '../feedback/feedbackClassifier';
import { MemoryStore } from '../memory/memoryStore';
import { ActionProtocol } from '../protocol/actionProtocol';
import { Action, Message, Observation } from '../types';
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
  constructor(private deps: LoopDeps) {
    this.sink = deps.sink ?? noopSink;
    const sys = deps.systemPrompt + (deps.memory.systemPrompt() ? '\n\n' + deps.memory.systemPrompt() : '');
    this.messages = [{ role: 'system', content: sys }, { role: 'user', content: 'complete the task using tools' }];
  }

  async run(): Promise<{ haltReason: HaltReason; iterations: number }> {
    let iter = 0;
    let lastFailKey: string | null = null;
    let sameCount = 0;
    while (iter < this.deps.maxIter) {
      iter++;
      let resp;
      try { resp = await this.deps.llm.complete(this.messages); }
      catch { return { haltReason: 'provider_error', iterations: iter }; }
      this.messages.push({ role: 'assistant', content: resp.text });
      const acts = ActionProtocol.parse(resp.text);
      if (acts.length === 0) {
        this.messages.push({ role: 'observation', content: 'no action block found; emit a fenced ```action {...}``` block' });
        continue;
      }
      const action = acts[0];
      this.sink.emit({ type: 'action', payload: action, iter });

      if (action.tool === 'finish') {
        this.sink.emit({ type: 'halt', payload: { reason: 'finish' }, iter });
        return { haltReason: 'finish', iterations: iter };
      }

      // 护栏
      const verdict = this.deps.guardrail.assess(action);
      let effective: Action = action;
      if (verdict.severity === 'high') {
        const dec = await this.deps.approval.request(action, verdict.reasons);
        this.sink.emit({ type: 'approval_decision', payload: dec, iter });
        if (dec.decision === 'deny') {
          this.messages.push({ role: 'observation', content: `DENIED: ${dec.reason} (reasons: ${verdict.reasons.join('; ')})` });
          continue;
        }
      } else if (verdict.severity === 'low') {
        this.messages.push({ role: 'observation', content: `WARN(low): ${verdict.reasons.join('; ')}` });
      }

      // 执行
      const ctx: ToolContext = { cwd: this.deps.cwd };
      const obs = await this.deps.registry.dispatch(effective, ctx);

      // run_tests 失败的反馈闭环
      if (action.tool === 'run_tests' && obs.exitCode !== 0) {
        const fb = this.deps.feedback.parse(obs);
        const key = fb.assertion ? `${fb.assertion.file}:${fb.assertion.line}` : fb.errorType;
        if (key === lastFailKey) { sameCount++; } else { sameCount = 1; lastFailKey = key; }
        const content = JSON.stringify(fb);
        this.messages.push({ role: 'observation', content });
        this.sink.emit({ type: 'observation', payload: fb, iter });
        if (sameCount >= 2) {
          this.sink.emit({ type: 'halt', payload: { reason: 'stuck', key }, iter });
          return { haltReason: 'stuck', iterations: iter };
        }
      } else {
        this.messages.push({ role: 'observation', content: JSON.stringify(obs) });
        this.sink.emit({ type: 'observation', payload: obs, iter });
      }
    }
    this.sink.emit({ type: 'halt', payload: { reason: 'cap' }, iter });
    return { haltReason: 'cap', iterations: iter };
  }
}
