// CLI 人工审批网关：终端内 HITL。高危动作触发时悬停接收键盘输入。
//   y/yes  → 批准
//   n/no   → 拒绝
//   其它文本 → 拒绝并把文本作为 reason 回灌（AgentLoop 将其作为 Observation 反馈给 LLM，
//             实现对话重定向——这是"治理 + 反馈"两条代码机制在终端的交汇点）
// ask 函数可注入，便于离线单测；默认无 ask 时安全拒否（不崩、不悬停）。

import { Action, ApprovalDecision } from '../types';
import { ApprovalGateway } from './approvalGateway';

export type AskFn = (prompt: string) => Promise<string>;

export class CliApprovalGateway implements ApprovalGateway {
  private askFn: AskFn | null;
  constructor(ask?: AskFn) {
    this.askFn = ask ?? null;
  }

  /** REPL 持有共享 readline 时，绑定 ask 到该接口。 */
  setAsk(ask: AskFn): void {
    this.askFn = ask;
  }

  async request(action: Action, reasons: string[]): Promise<ApprovalDecision> {
    const prompt =
      `\n⚠️  高危动作待审批:\n` +
      `  tool: ${action.tool}\n` +
      `  args: ${JSON.stringify(action.args)}\n` +
      `  reasons: ${reasons.join('; ') || '(none)'}\n` +
      `[y] 批准 / [n] 拒绝 / 或输入文本反馈以重定向: `;

    const answer = (await this.ask(prompt)).trim();

    if (/^y(es)?$/i.test(answer)) {
      return { decision: 'approve', reason: 'approved via CLI' };
    }
    if (/^no?$/i.test(answer) || !answer) {
      return { decision: 'deny', reason: answer ? 'denied via CLI' : 'denied via CLI (empty input)' };
    }
    // 任意非 y/n 文本 → 拒绝，文本作为反馈回灌
    return { decision: 'deny', reason: answer };
  }

  private async ask(prompt: string): Promise<string> {
    if (this.askFn) return this.askFn(prompt);
    // 无注入 ask 时安全拒否——非交互场景（如 pipe stdin）不应悬停
    return '';
  }
}
