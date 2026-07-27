import { Tool, ToolContext } from './tool';
import { exec } from 'child_process';
import { promisify } from 'util';
const pexec = promisify(exec);

function wrap(cmd: string): { cmd: string; isShell: boolean } {
  return { cmd, isShell: true };
}

// 缺省/非字符串 command 直接拒绝，避免 String(undefined) 变 "undefined" 串后进入 exec
function invalidCommand(args: Record<string, any>): boolean {
  return typeof args.command !== 'string' || !args.command.trim();
}

export const run_shell: Tool = {
  name: 'run_shell',
  async execute(args, ctx) {
    if (invalidCommand(args)) return { ok: false, error: 'missing command' };
    const { cmd } = wrap(String(args.command));
    try {
      const { stdout, stderr } = await pexec(cmd, { cwd: ctx.cwd, maxBuffer: 1e6, timeout: 30000 });
      return { ok: true, stdout, stderr, exitCode: 0 };
    } catch (e: any) {
      return {
        ok: e.code === 0,
        stdout: e.stdout ?? '',
        stderr: e.stderr ?? '',
        exitCode: typeof e.code === 'number' ? e.code : -1,
        error: String(e?.message ?? e),
      };
    }
  },
};

export const run_tests: Tool = {
  name: 'run_tests',
  async execute(args, ctx) {
    if (invalidCommand(args)) return { ok: false, error: 'missing command' };
    const { cmd } = wrap(String(args.command));
    try {
      const { stdout, stderr } = await pexec(cmd, { cwd: ctx.cwd, maxBuffer: 1e6, timeout: 60000 });
      return { ok: true, stdout, stderr, exitCode: 0 };
    } catch (e: any) {
      const timedOut = e?.killed && e?.signal === 'SIGTERM'; // exec 超时 → killed + SIGTERM
      return {
        ok: false,
        stdout: e.stdout ?? '',
        stderr: e.stderr ?? '',
        exitCode: typeof e.code === 'number' ? e.code : -1,
        error: timedOut ? 'timeout' : (e instanceof Error ? e.message : String(e)),
      };
    }
  },
};

export const shellTools: Tool[] = [run_shell, run_tests];
