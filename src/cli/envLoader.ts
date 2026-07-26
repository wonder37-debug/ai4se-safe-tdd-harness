// .env 文件解析：纯函数 parseEnvFile(text) + 磁盘读 loadEnvFile(file)。
// ponytail: 不引入 dotenv 依赖；只解析 KEY=VALUE，剥离首尾引号，忽略 # 注释与空行。
// 威胁模型：.env 为明文且 process-env 可见，仅作离线/首次回退（SPEC §3.9）。

import { promises as fs } from 'fs';
import { existsSync } from 'fs';

export function parseEnvFile(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq < 0) continue;
    const key = line.slice(0, eq).trim();
    let val = line.slice(eq + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    if (key) out[key] = val;
  }
  return out;
}

export async function loadEnvFile(file: string): Promise<Record<string, string>> {
  if (!existsSync(file)) return {};
  try {
    return parseEnvFile(await fs.readFile(file, 'utf8'));
  } catch {
    return {};
  }
}
