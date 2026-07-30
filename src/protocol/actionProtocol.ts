import { Action, ToolName } from '../types';

// 围栏正则：兼容未闭合的 ```action 块。
// 大模型偶发漏写结尾三反引号，若强依赖闭合围栏会令 parse 返回空 → 主循环判无动作 →
// 死循环重试至上限。此处以 `(?:```|$)` 收尾：有闭合则吃闭合围栏，无闭合则匹配至文本结尾。
const FENCE = /```action\s*([\s\S]*?)(?:```|$)/g;
const TOOL_NAMES = new Set<string>(['read_file', 'write_file', 'list_dir', 'run_shell', 'run_tests', 'finish']);

export const ActionProtocol = {
  parse(text: string): Action[] {
    const out: Action[] = [];
    let m: RegExpExecArray | null;
    while ((m = FENCE.exec(text)) !== null) {
      const raw = m[1].trim();
      try {
        const obj = JSON.parse(raw);
        if (obj && typeof obj.tool === 'string' && obj.args && typeof obj.args === 'object'
            && TOOL_NAMES.has(obj.tool)) {
          out.push({ tool: obj.tool as ToolName, args: obj.args });
        }
      } catch {
        // 畸形块：跳过，不抛
      }
    }
    return out;
  },
};

// 剥除 LLM 回复中裸露的 ```action 围栏代码块，只保留自然语言思考文本。
// 纯函数，离线可单测；AgentLoop 用它把"思考过程"剥出来作为 thought 事件存入 EventStore，
// CLI 终端流也复用它（见 ConsoleSink / repl）。
// 兼容未闭合围栏（大模型偶发漏写结尾三反引号），否则会把半截 JSON 当自然语言泄漏。
export function stripActionFences(text: string): string {
  return text.replace(/```action\s*[\s\S]*?(?:```|$)/g, '').trim();
}
