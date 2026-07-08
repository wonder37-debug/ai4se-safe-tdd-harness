import { Action, ApprovalDecision } from '../types';
import { ApprovalGateway } from './approvalGateway';
import { randomUUID } from 'crypto';

interface Pending { id: string; action: Action; reasons: string[]; resolve: (d: ApprovalDecision) => void; }

export class HttpApprovalGateway implements ApprovalGateway {
  // ponytail: field renamed to pendingMap to avoid collision with the pending() method
  private pendingMap = new Map<string, Pending>();

  request(action: Action, reasons: string[]): Promise<ApprovalDecision> {
    const id = randomUUID();
    return new Promise<ApprovalDecision>((resolve) => {
      this.pendingMap.set(id, { id, action, reasons, resolve });
    });
  }

  pendingList(): { id: string; action: Action; reasons: string[] }[] {
    return [...this.pendingMap.values()].map(p => ({ id: p.id, action: p.action, reasons: p.reasons }));
  }
  pending(): { id: string; action: Action; reasons: string[] }[] { return this.pendingList(); }

  resolve(id: string, decision: ApprovalDecision): boolean {
    const p = this.pendingMap.get(id);
    if (!p) return false;
    this.pendingMap.delete(id);
    p.resolve(decision);
    return true;
  }
}
