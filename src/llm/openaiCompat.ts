import { LLMProvider } from './provider';
import { Message, Role } from '../types';

export class AuthError extends Error { constructor(m: string) { super(m); this.name = 'AuthError'; } }

export interface OpenAICompatOpts {
  baseUrl: string;
  apiKey: string;
  model?: string;
  fetch?: typeof fetch;
  /** 失败后重试次数（不含首次）。默认 3。仅对瞬时错误（429/5xx/网络/超时）生效。 */
  maxRetries?: number;
  /** 退避基准毫秒，默认 500。实际延迟 = base × backoff^attempt × 半抖动。 */
  baseDelayMs?: number;
  /** 退避因子，默认 2（指数）。 */
  backoffFactor?: number;
  /** 单次请求硬超时毫秒，0 表示不启用（不中断长生成）。默认 0。 */
  timeoutMs?: number;
}

// OpenAI /v1/chat/completions 只接受 system/user/assistant 角色；内核回灌的 'observation'
// 角色会被端点判为非法 → HTTP 400。故发送前把 observation 降级为 user 并加 Observation 前缀，
// 既保留语义、又彻底兼容标准端点。
export function adaptMessages(messages: Message[]): { role: Role; content: string }[] {
  return messages.map((m) =>
    m.role === 'observation'
      ? { role: 'user', content: 'Observation: ' + m.content }
      : { role: m.role, content: m.content },
  );
}

// 防御性清洗 baseUrl：先剥末尾斜杠，再剥末尾 /v1，使调用方始终拼 /v1/chat/completions。
// 兼容 https://.../v1、.../v1/、.../、... 四种写法及末尾多斜杠（/v1//）边界；
// 杜绝 .../v1/v1 双重路径——曾因 config.json 存了带 /v1 后缀的 baseUrl 触发 provider_error。
// 顺序敏感：必须先去斜杠再去 /v1，否则 /v1// 会残留 /v1 → 仍双重拼接。纯函数，离线可单测。
export function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, '').replace(/\/v1$/, '');
}

function sleep(ms: number): Promise<void> { return new Promise((r) => setTimeout(r, ms)); }

function isRetryableStatus(status: number): boolean {
  return status === 429 || (status >= 500 && status < 600);
}

/** 解析 Retry-After 头（仅支持秒整数形式；HTTP-date 形式忽略并回退到指数退避）。返回毫秒。 */
function parseRetryAfterMs(headers: any): number | null {
  if (!headers || typeof headers.get !== 'function') return null;
  const v = headers.get('retry-after');
  if (!v) return null;
  const sec = Number(v);
  return Number.isFinite(sec) && sec >= 0 ? sec * 1000 : null;
}

export class OpenAICompatProvider implements LLMProvider {
  private fetchImpl: typeof fetch;
  private maxRetries: number;
  private baseDelayMs: number;
  private backoffFactor: number;
  private timeoutMs: number;
  constructor(private opts: OpenAICompatOpts) {
    this.fetchImpl = opts.fetch ?? fetch;
    this.maxRetries = opts.maxRetries ?? 3;
    this.baseDelayMs = opts.baseDelayMs ?? 500;
    this.backoffFactor = opts.backoffFactor ?? 2;
    this.timeoutMs = opts.timeoutMs ?? 0;
  }

  /** 指数退避 + 半抖动：delay ∈ [0.5×, 1×) of base × backoff^attempt。半抖动避免重试惊群。 */
  private backoffDelay(attempt: number): number {
    const base = this.baseDelayMs * Math.pow(this.backoffFactor, attempt);
    return Math.floor(base * (0.5 + Math.random() * 0.5));
  }

  async complete(messages: Message[]): Promise<{ text: string; stopReason: string }> {
    // baseUrl 经 normalizeBaseUrl 清洗后统一拼 /v1/chat/completions，杜绝 /v1/v1 双重路径
    const url = `${normalizeBaseUrl(this.opts.baseUrl)}/v1/chat/completions`;
    const body = JSON.stringify({ model: this.opts.model ?? 'gpt-4o-mini', messages: adaptMessages(messages), temperature: 0 });

    let lastErr: Error | null = null;
    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      // 单次请求硬超时（仅当 timeoutMs>0）：用 AbortController 中断挂死连接，避免吞掉整轮预算
      const ctrl = this.timeoutMs > 0 ? new AbortController() : null;
      const timer = ctrl ? setTimeout(() => ctrl.abort(), this.timeoutMs) : null;
      try {
        const res = await this.fetchImpl(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${this.opts.apiKey}` },
          body,
          ...(ctrl ? { signal: ctrl.signal } : {}),
        });

        if (!res.ok) {
          // 防御式读取 body：真实 Response 有 .text()，但单测 mock 可能只提供 .json()；
          // 两者都兼容，body 读取失败也不影响按状态码抛错。
          let bodyText = '';
          try {
            bodyText = typeof (res as any).text === 'function' ? await (res as any).text() : JSON.stringify(await (res as any).json());
          } catch { /* 忽略 body 读取失败，仍按状态码抛错 */ }

          // 瞬时错误：429（限流） / 5xx（服务端）→ 退避重试
          if (isRetryableStatus(res.status) && attempt < this.maxRetries) {
            lastErr = new Error(`provider http ${res.status}: ${bodyText}`);
            const retryAfter = parseRetryAfterMs((res as any).headers);
            await sleep(retryAfter ?? this.backoffDelay(attempt));
            continue;
          }
          // 重试耗尽后仍为瞬时错误 → 抛通用错误（不误判为 auth）
          if (isRetryableStatus(res.status)) {
            throw new Error(`provider http ${res.status} (retries exhausted): ${bodyText}`);
          }
          // 4xx（非 429）→ 不可重试，直接抛 AuthError
          if (res.status >= 400 && res.status < 500) {
            throw new AuthError(`auth/http ${res.status}: ${bodyText}`);
          }
          throw new Error(`provider http ${res.status}: ${bodyText}`);
        }

        const data: any = await res.json();
        const text = data?.choices?.[0]?.message?.content ?? '';
        return { text, stopReason: data?.choices?.[0]?.finish_reason ?? 'ok' };
      } catch (e: any) {
        // AuthError 不可重试（凭据问题不会因重试而自愈）
        if (e instanceof AuthError) throw e;
        if (timer) clearTimeout(timer);
        // 网络错误 / 超时中止 / fetch 抛错 → 可重试
        if (attempt < this.maxRetries) {
          lastErr = e instanceof Error ? e : new Error(String(e));
          await sleep(this.backoffDelay(attempt));
          continue;
        }
        throw e instanceof Error ? e : new Error(String(e));
      } finally {
        if (timer) clearTimeout(timer);
      }
    }
    // 兜底：循环内每次要么 return 要么 throw，理论不可达
    throw lastErr ?? new Error('provider: retries exhausted');
  }
}
