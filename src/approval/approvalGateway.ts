import { Action, ApprovalDecision } from '../types';

export interface ApprovalGateway {
  request(action: Action, reasons: string[]): Promise<ApprovalDecision>;
}

export class MockApprovalGateway implements ApprovalGateway {
  private queue: ApprovalDecision[];
  constructor(decisions: ApprovalDecision[]) { this.queue = [...decisions]; }
  async request(_action: Action, _reasons: string[]): Promise<ApprovalDecision> {
    if (this.queue.length === 0) return { decision: 'deny', reason: 'mock queue empty' };
    return this.queue.shift()!;
  }
}
