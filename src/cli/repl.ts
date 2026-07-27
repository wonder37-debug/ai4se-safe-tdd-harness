// 交互式 REPL 会话：终端 `harness > ` 循环提示符。
// 共享一个 readline 接口：REPL 主提示与 AgentLoop 触发的 HITL 审批提示分时复用
// （loop 运行期主提示不在 await，互不抢占）。任务完成后不退出，继续等待下一指令，
// 直到 exit / quit。高危动作触发时由 CliApprovalGateway 悬停接收 y/n/文本反馈。
// readline 是 Node stdlib，不引依赖；REPL 胶水薄、委托已测模块。

import * as readline from 'readline';
import { CliApprovalGateway, AskFn } from '../approval/cliApprovalGateway';

export interface ReplOpts {
  loopFactory: (task: string, cwd: string) => Promise<{ haltReason: string; iterations: number }>;
  cwd: string;
  approval: CliApprovalGateway;
}

/** 把 readline 接口包成 AskFn，供 CliApprovalGateway 复用同一 stdin。 */
export function rlAsk(rl: readline.Interface): AskFn {
  return (prompt: string) => new Promise<string>((res) => rl.question(prompt, res));
}

// 过滤 LLM 响应中裸露的 ```action {...} ``` 围栏代码块，只保留自然语言解释。
// 纯函数，离线可单测；被 makeLoopFactory 的 console 包装器复用。
// 同样兼容未闭合围栏（大模型偶发漏写结尾三反引号），否则终端会把半截 JSON 当自然语言打印。
export function stripActionFences(text: string): string {
  return text.replace(/```action\s*[\s\S]*?(?:```|$)/g, '').trim();
}

export async function runRepl(opts: ReplOpts): Promise<void> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  opts.approval.setAsk(rlAsk(rl));
  console.log('AI4SE-Safe-TDD-Harness REPL. 输入自然语言任务；exit / quit 退出。');
  for (;;) {
    let line: string;
    try {
      line = await new Promise<string>((res) => rl.question('harness > ', res));
    } catch {
      break;
    }
    const t = line.trim();
    if (!t) continue;
    if (t === 'exit' || t === 'quit') break;
    try {
      const r = await opts.loopFactory(t, opts.cwd);
      console.log(`[done] haltReason=${r.haltReason}, iterations=${r.iterations}`);
    } catch (e: any) {
      console.error('task error:', e?.message ?? String(e));
    }
  }
  rl.close();
}
