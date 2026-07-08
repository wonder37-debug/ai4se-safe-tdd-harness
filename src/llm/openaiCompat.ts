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
    const res = await this.fetchImpl(`${this.opts.baseUrl}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${this.opts.apiKey}` },
      body: JSON.stringify({ model: this.opts.model ?? 'gpt-4o-mini', messages, temperature: 0 }),
    });
    if (!res.ok) {
      if (res.status >= 400 && res.status < 500) {
        const e = await res.json().catch(() => ({}));
        throw new AuthError(`auth/http ${res.status}: ${JSON.stringify(e)}`);
      }
      throw new Error(`provider http ${res.status}`);
    }
    const data: any = await res.json();
    const text = data?.choices?.[0]?.message?.content ?? '';
    return { text, stopReason: data?.choices?.[0]?.finish_reason ?? 'ok' };
  }
}
