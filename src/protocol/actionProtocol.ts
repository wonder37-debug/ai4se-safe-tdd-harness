import { Action, ToolName } from '../types';

const FENCE = /```action\s*([\s\S]*?)```/g;
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
