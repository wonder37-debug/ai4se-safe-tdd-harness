import * as fs from 'fs/promises';
import { existsSync, rmSync } from 'fs';

// 非密配置：LLM 请求地址与模型名。
// 这些不是凭据（不含 secret）—— §3.1 只要求 API key 加密落盘，
// 故请求地址 / 模型名以明文 JSON 存储即可，便于查看与跨会话复用。
// API key 仍由 EncryptedFileStore（AES-256-GCM）保管，与本配置分离。

export interface ProviderConfig {
  baseUrl?: string;
  model?: string;
}

export interface ConfigStore {
  /** 读取配置；文件不存在时返回 {}（不抛错，便于首次运行）。 */
  get(): Promise<ProviderConfig>;
  /** 写入配置；空值字段不落盘。 */
  set(cfg: ProviderConfig): Promise<void>;
  /** 删除配置文件。 */
  clear(): void;
}

export class JsonConfigStore implements ConfigStore {
  constructor(private file: string) {}

  async get(): Promise<ProviderConfig> {
    if (!existsSync(this.file)) return {};
    try {
      const raw = await fs.readFile(this.file, 'utf8');
      const obj = JSON.parse(raw) ?? {};
      return { baseUrl: obj.baseUrl, model: obj.model };
    } catch {
      // 损坏文件视为空配置，不阻断启动
      return {};
    }
  }

  async set(cfg: ProviderConfig): Promise<void> {
    const obj: Record<string, string> = {};
    if (cfg.baseUrl) obj.baseUrl = cfg.baseUrl;
    if (cfg.model) obj.model = cfg.model;
    await fs.writeFile(this.file, JSON.stringify(obj, null, 2) + '\n', 'utf8');
  }

  clear(): void {
    if (existsSync(this.file)) rmSync(this.file, { force: true });
  }
}
