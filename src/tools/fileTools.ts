import { Tool, ToolContext } from './tool';
import * as path from 'path';
import * as fs from 'fs/promises';

// 工作区路径围栏：解析后必须落在 ctx.cwd 内（含 cwd 自身），
// 绝对路径 / ../ 穿越一律拒绝，防止 LLM 读写工作区外任意文件。
// 三个工具统一复用；越界时抛错，由各工具 catch 转成 { ok:false, error }。
async function abs(p: string, ctx: ToolContext): Promise<string> {
  const root = path.resolve(ctx.cwd);
  const full = path.resolve(root, String(p ?? ''));
  if (full !== root && !full.startsWith(root + path.sep)) {
    throw new Error('path escapes workspace');
  }
  return full;
}

export const read_file: Tool = {
  name: 'read_file',
  async execute(args, ctx) {
    try {
      const content = await fs.readFile(await abs(args.path, ctx), 'utf8');
      return { ok: true, content };
    } catch (e: any) { return { ok: false, error: String(e?.message ?? e) }; }
  },
};

export const write_file: Tool = {
  name: 'write_file',
  async execute(args, ctx) {
    try {
      const full = await abs(args.path, ctx);
      await fs.mkdir(path.dirname(full), { recursive: true });
      await fs.writeFile(full, String(args.content));
      return { ok: true, content: `wrote ${args.path}` };
    } catch (e: any) { return { ok: false, error: String(e?.message ?? e) }; }
  },
};

export const list_dir: Tool = {
  name: 'list_dir',
  async execute(args, ctx) {
    try {
      const entries = await fs.readdir(await abs(args.path, ctx));
      return { ok: true, content: entries.join('\n') };
    } catch (e: any) { return { ok: false, error: String(e?.message ?? e) }; }
  },
};

export const fileTools: Tool[] = [read_file, write_file, list_dir];
