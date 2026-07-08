import { Action, Observation } from '../types';

export interface ToolContext { cwd: string; }

export interface Tool {
  name: string;
  execute(args: Record<string, any>, ctx: ToolContext): Promise<Observation>;
}

function errMsg(e: any): string {
  return e instanceof Error ? e.message : String(e);
}

export class ToolRegistry {
  private tools = new Map<string, Tool>();
  constructor(tools: Tool[]) { for (const t of tools) this.tools.set(t.name, t); }

  async dispatch(action: Action, ctx: ToolContext): Promise<Observation> {
    const t = this.tools.get(action.tool);
    if (!t) return { ok: false, error: `unknown tool: ${action.tool}` };
    try {
      return await t.execute(action.args, ctx);
    } catch (e: any) {
      return { ok: false, error: errMsg(e) };
    }
  }
}
