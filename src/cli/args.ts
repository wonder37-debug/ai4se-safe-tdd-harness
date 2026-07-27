// CLI 参数解析：纯函数，离线可单测。
// 模式优先级：显式 flag > 裸位置参数 > interactive 默认。
// 一个函数搞定，不引入 commander/yargs。

export type CliMode = 'web' | 'task' | 'interactive' | 'help';

export interface ParsedArgs {
  mode: CliMode;
  task?: string;
  cwd?: string;
}

export function parseArgs(argv: string[]): ParsedArgs {
  let mode: CliMode = 'interactive';
  let task: string | undefined;
  let cwd: string | undefined;

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--web') {
      mode = 'web';
    } else if (a === '--interactive' || a === '-i') {
      mode = 'interactive';
    } else if (a === '--help' || a === '-h') {
      mode = 'help';
    } else if (a === '--task') {
      task = argv[++i];
      mode = 'task';
    } else if (a.startsWith('--task=')) {
      task = a.slice('--task='.length);
      mode = 'task';
    } else if (a === '--cwd') {
      cwd = argv[++i];
    } else if (a.startsWith('--cwd=')) {
      cwd = a.slice('--cwd='.length);
    } else if (!a.startsWith('-') && mode !== 'task') {
      // 裸位置参数视作任务描述（--task 已设时不再吞并）
      task = a;
      mode = 'task';
    }
  }

  return { mode, task, cwd };
}
