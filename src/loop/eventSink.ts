import { Event, Action, ApprovalDecision, Feedback } from '../types';
export interface EventSink { emit(e: Omit<Event, 'id'>): void; }
export const noopSink: EventSink = { emit() {} };
export class EventStore implements EventSink {
  private events: Event[] = [];
  private next = 1;
  emit(e: Omit<Event, 'id'>): void { this.events.push({ id: this.next++, ...e }); if (this.events.length > 1000) this.events.shift(); }
  since(id: number): Event[] { return this.events.filter(e => e.id > id); }
  all(): Event[] { return [...this.events]; }
}

// 人性化终端事件 sink：放弃 JSON.stringify，把 AgentLoop 的事件翻译为自然语言行。
//   action      → 📄 写入文件: add.js / 🧪 运行测试: npx jest / ...
//   observation →   └─ ✅ 已写入 /   └─ ❌ 断言失败 add.test.js:4 /   └─ ❌ ENOENT...
//   approval    → 🔐 审批 🚫 拒绝 — reason
//   halt        → 🏁 任务完成 / ⛔ 卡死停机 / ⛔ LLM 调用失败...
// observation 承接上一 action 的工具类型选成功提示（lastTool）。
// write 可注入，便于离线单测；默认 console.log。
export class ConsoleSink implements EventSink {
  private lastTool: string | null = null;
  constructor(private write: (line: string) => void = (l) => console.log(l)) {}

  emit(e: Omit<Event, 'id'>): void {
    switch (e.type) {
      case 'action': {
        const a = e.payload as Action;
        this.lastTool = a.tool;
        this.write(this.formatAction(a));
        break;
      }
      case 'observation':
        this.write(this.formatObservation(e.payload));
        break;
      case 'approval_decision': {
        const d = e.payload as ApprovalDecision;
        const verdict = d.decision === 'approve' ? '✅ 批准' : '🚫 拒绝';
        this.write(`🔐 审批 ${verdict} — ${d.reason}`);
        break;
      }
      case 'halt':
        this.write(this.formatHalt(e.payload));
        break;
      default:
        break;
    }
  }

  private formatAction(a: Action): string {
    const p = String(a.args?.path ?? '');
    const cmd = this.clip(a.args?.command);
    switch (a.tool) {
      case 'write_file': return `📄 写入文件: ${p}`;
      case 'read_file':  return `📖 读取文件: ${p}`;
      case 'list_dir':   return `📂 列出目录: ${p || '.'}`;
      case 'run_shell':  return `⚙️ 执行命令: ${cmd}`;
      case 'run_tests':  return `🧪 运行测试: ${cmd}`;
      case 'finish':     return `🏁 完成`;
      default:           return `🔧 ${a.tool}`;
    }
  }

  private formatObservation(payload: any): string {
    // run_tests 失败回灌的 Feedback 对象（含 errorType）
    if (payload && typeof payload === 'object' && 'errorType' in payload) {
      const fb = payload as Feedback;
      if (fb.errorType === 'syntax' && fb.assertion) {
        return `  └─ ❌ 语法错误 ${fb.assertion.file}:${fb.assertion.line}`;
      }
      if (fb.errorType === 'assertion' && fb.assertion) {
        const line = `  └─ ❌ 断言失败 ${fb.assertion.file}:${fb.assertion.line}`;
        return fb.hint ? `${line}\n     💡 ${this.clip(fb.hint, 80)}` : line;
      }
      return `  └─ ❌ 测试失败`;
    }
    // 普通工具失败：提取 error 首行
    if (payload && payload.ok === false) {
      return `  └─ ❌ ${this.clip(payload.error || '失败')}`;
    }
    // 成功：按上一工具给极简提示
    return `  └─ ✅ ${this.successMsg()}`;
  }

  private successMsg(): string {
    switch (this.lastTool) {
      case 'write_file': return '已写入';
      case 'read_file':  return '已读取';
      case 'list_dir':   return '已列出';
      case 'run_tests':  return '测试通过';
      case 'run_shell':  return '执行完成';
      default:           return '完成';
    }
  }

  private formatHalt(payload: any): string {
    const reason = payload?.reason ?? 'unknown';
    switch (reason) {
      case 'finish':         return `🏁 任务完成`;
      case 'cap':            return `⛔ 达到迭代上限`;
      case 'stuck':          return `⛔ 卡死停机（连续两轮同一断言点失败）`;
      case 'provider_error': return `⛔ LLM 调用失败${payload?.error ? '：' + this.clip(payload.error, 80) : ''}`;
      default:               return `⛔ 停止：${reason}`;
    }
  }

  // 取首行并截断，避免长命令/长 evidence 溢出终端
  private clip(s: any, n = 60): string {
    const str = String(s ?? '');
    const one = str.split(/\r?\n/)[0];
    return one.length > n ? one.slice(0, n) + '…' : one;
  }
}
