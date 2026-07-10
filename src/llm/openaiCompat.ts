import { LLMProvider } from './provider';
import { Message } from '../types';

export class AuthError extends Error { constructor(m: string) { super(m); this.name = 'AuthError'; } }

export interface OpenAICompatOpts { baseUrl: string; apiKey: string; model?: string; fetch?: typeof fetch; }

export class OpenAICompatProvider implements LLMProvider {
  private fetchImpl: typeof fetch;
  constructor(private opts: OpenAICompatOpts) {
    this.fetchImpl = opts.fetch ?? fetch;
  }
  async complete(messages: Message[]): Promise<{ text: string; stopReason: string }> {
    // 智能拼接：如果 baseUrl 已以 /v1 结尾，不再重复追加（兼容 https://.../v1 与 https://... 两种写法）
    const base = this.opts.baseUrl.replace(/\/+$/, '');
    const url = base.endsWith('/v1') ? `${base}/chat/completions` : `${base}/v1/chat/completions`;
    const res = await this.fetchImpl(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${this.opts.apiKey}` },
      body: JSON.stringify({ model: this.opts.model ?? 'qwen-flash', messages, temperature: 0 }),
    });
    if (!res.ok) {
      // 防御式读取 body：真实 Response 有 .text()，但单测 mock 可能只提供 .json()；
      // 两者都兼容，body 读取失败也不影响按状态码抛错。
      let body = '';
      try {
        body = typeof (res as any).text === 'function' ? await (res as any).text() : JSON.stringify(await (res as any).json());
      } catch { /* 忽略 body 读取失败，仍按状态码抛错 */ }
      if (res.status >= 400 && res.status < 500) {
        throw new AuthError(`auth/http ${res.status}: ${body}`);
      }
      throw new Error(`provider http ${res.status}: ${body}`);
    }
    const data: any = await res.json();
    const text = data?.choices?.[0]?.message?.content ?? '';
    return { text, stopReason: data?.choices?.[0]?.finish_reason ?? 'ok' };
  }
}
