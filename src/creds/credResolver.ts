// 凭据解析：纯函数（给定输入，输出确定），离线可单测、无网络。
// 解析顺序：
//   1. 主密码 + creds.enc 可解密 → encrypted-file（主路径，密文落盘）
//   2. .env API_KEY 或 process.env API_KEY → env-file / env（明文兜底，带告警）
//   3. 均无 → null（调用方降级离线 ScriptedMock）
// baseUrl/model 来源优先级：config.json > .env > process.env。
// ponytail: 单函数决议，不引状态机。

import { CredentialStore } from './credentialStore';
import { ConfigStore } from './configStore';

export interface CredInputs {
  creds: CredentialStore;
  config: ConfigStore;
  envFile?: Record<string, string>;
  masterPassword?: string;
  env?: Record<string, string | undefined>;
}

export type CredSource = 'encrypted-file' | 'env-file' | 'env';

export interface ResolvedCreds {
  baseUrl: string;
  key: string;
  model?: string;
  source: CredSource;
}

export async function resolveCredentials(s: CredInputs): Promise<ResolvedCreds | null> {
  const envFile = s.envFile ?? {};
  const env = s.env ?? {};
  const cfg = await s.config.get();

  const baseUrl = cfg.baseUrl || envFile.API_BASE_URL || env.API_BASE_URL;
  const model = cfg.model || envFile.MODEL || env.MODEL;

  // 1. 加密文件主路径
  if (s.masterPassword) {
    try {
      const { key } = await s.creds.resolve(s.masterPassword);
      if (key && baseUrl) return { baseUrl, key, model, source: 'encrypted-file' };
    } catch {
      // 主密码错或无文件 → 落到 env 兜底
    }
  }

  // 2. .env / process.env 明文 API_KEY 兜底
  const envKey = envFile.API_KEY || env.API_KEY;
  if (envKey && baseUrl) {
    return {
      baseUrl,
      key: envKey,
      model,
      source: envFile.API_KEY ? 'env-file' : 'env',
    };
  }

  return null;
}
