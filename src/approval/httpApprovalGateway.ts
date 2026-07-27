import { Action, ApprovalDecision } from '../types';
import { ApprovalGateway } from './approvalGateway';
import { randomUUID } from 'crypto';

interface Pending { id: string; action: Action; reasons: string[]; resolve: (d: ApprovalDecision) => void; timer: NodeJS.Timeout; }

export class HttpApprovalGateway implements ApprovalGateway {
  // 字段名 pendingMap 避免与 pending() 方法同名碰撞
  private pendingMap = new Map<string, Pending>();

  // SPEC §3.5：审批悬停超时默认 deny（默认 5 分钟），避免 Promise 永挂阻塞 loop
  constructor(private timeoutMs: number = 300000) {}

  request(action: Action, reasons: string[]): Promise<ApprovalDecision> {
    const id = randomUUID();
    return new Promise<ApprovalDecision>((resolve) => {
      // 到点无人裁决 → 自动 deny 并清理；若已被 resolve() 摘除则幂等跳过
      const timer = setTimeout(() => {
        if (this.pendingMap.delete(id)) resolve({ decision: 'deny', reason: 'approval timeout' });
      }, this.timeoutMs);
      timer.unref?.(); // 不阻止进程退出（测试/CLI 友好）
      this.pendingMap.set(id, { id, action, reasons, resolve, timer });
    });
  }

  pendingList(): { id: string; action: Action; reasons: string[] }[] {
    return [...this.pendingMap.values()].map(p => ({ id: p.id, action: p.action, reasons: p.reasons }));
  }
  pending(): { id: string; action: Action; reasons: string[] }[] { return this.pendingList(); }

  resolve(id: string, decision: ApprovalDecision): boolean {
    const p = this.pendingMap.get(id);
    if (!p) return false; // 已超时清理或 id 不存在 → 幂等忽略
    clearTimeout(p.timer);
    this.pendingMap.delete(id);
    p.resolve(decision);
    return true;
  }
}
