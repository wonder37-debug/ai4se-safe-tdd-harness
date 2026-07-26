import { Event, Action, ApprovalDecision } from '../types';
export interface EventSink { emit(e: Omit<Event, 'id'>): void; }
export const noopSink: EventSink = { emit() {} };
export class EventStore implements EventSink {
  private events: Event[] = [];
  private next = 1;
  emit(e: Omit<Event, 'id'>): void { this.events.push({ id: this.next++, ...e }); if (this.events.length > 1000) this.events.shift(); }
  since(id: number): Event[] { return this.events.filter(e => e.id > id); }
  all(): Event[] { return [...this.events]; }
}

// 漏洞 1 修复：把 AgentLoop 发出的事件翻译为终端可读行——
// [action] 工具+参数 / [observation] 结果 / [approval] 裁决 / [halt] 终止。
// 与 EventStore 并列挂载时，REPL 即可获得实时事件流（无网络、无轮询）。
// write 可注入，便于离线单测；默认 console.log。
export class ConsoleSink implements EventSink {
  constructor(private write: (line: string) => void = (l) => console.log(l)) {}

  emit(e: Omit<Event, 'id'>): void {
    const { type, payload, iter } = e;
    const prefix = `[iter ${iter}]`;
    switch (type) {
      case 'action': {
        const a = payload as Action;
        this.write(`${prefix} [action] ${a.tool} ${JSON.stringify(a.args)}`);
        break;
      }
      case 'observation':
        this.write(`${prefix} [observation] ${JSON.stringify(payload)}`);
        break;
      case 'approval_decision': {
        const d = payload as ApprovalDecision;
        this.write(`${prefix} [approval] ${d.decision} — ${d.reason}`);
        break;
      }
      case 'halt':
        this.write(`${prefix} [halt] ${JSON.stringify(payload)}`);
        break;
      default:
        // 未知事件类型静默跳过（不崩、不噪）
        break;
    }
  }
}
