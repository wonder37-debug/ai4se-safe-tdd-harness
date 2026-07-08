import { Tool, ToolContext } from './tool';
import * as path from 'path';
import * as fs from 'fs/promises';

async function abs(p: string, ctx: ToolContext): Promise<string> {
  return path.resolve(ctx.cwd, p);
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
