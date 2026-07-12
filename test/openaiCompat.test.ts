import { OpenAICompatProvider, adaptMessages } from '../src/llm/openaiCompat';
import { Message } from '../src/types';

test('returns assistant text from mocked fetch', async () => {
  const calls: any[] = [];
  const fakeFetch = async (url: string, init: any) => {
    calls.push({ url, init });
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: 'LLM-SAYS' } }] }) };
  };
  const p = new OpenAICompatProvider({ baseUrl: 'https://x', apiKey: 'k', fetch: fakeFetch as any });
  const r = await p.complete([{ role: 'user', content: 'hi' }]);
  expect(r.text).toBe('LLM-SAYS');
  expect(calls[0].init.headers['Authorization']).toBe('Bearer k');
});

test('4xx throws AuthError', async () => {
  const fakeFetch = async () => ({ ok: false, status: 401, json: async () => ({ error: { message: 'bad key' } }) });
  const p = new OpenAICompatProvider({ baseUrl: 'https://x', apiKey: 'k', fetch: fakeFetch as any });
  await expect(p.complete([{ role: 'user', content: 'hi' }])).rejects.toThrow(/auth|401/i);
});

// 非平凡逻辑：observation→user 的角色适配。内核回灌的 observation 角色会被 OpenAI 端点判为非法 → HTTP 400，
// 故 complete 发送前必须适配。一个可运行检查：喂含 observation 的消息，断言输出无非法角色且带 Observation 前缀。
test('adaptMessages converts observation→user with Observation prefix', () => {
  const input: Message[] = [
    { role: 'system', content: 'sys' },
    { role: 'user', content: 'go' },
    { role: 'assistant', content: 'a1' },
    { role: 'observation', content: 'DENIED: demo deny' },
  ];
  const out = adaptMessages(input);
  expect(out.map((m) => m.role)).toEqual(['system', 'user', 'assistant', 'user']);
  expect(out[3].content).toBe('Observation: DENIED: demo deny');
  expect(out.every((m) => (m as any).role !== 'observation')).toBe(true);
});

test('complete sends adapted messages (no observation role) to fetch', async () => {
  let captured: any;
  const fakeFetch = async (_url: string, init: any) => {
    captured = JSON.parse(init.body);
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: 'ok' } }] }) };
  };
  const p = new OpenAICompatProvider({ baseUrl: 'https://x', apiKey: 'k', fetch: fakeFetch as any });
  const msgs: Message[] = [
    { role: 'user', content: 'u' },
    { role: 'observation', content: 'oops' },
  ];
  await p.complete(msgs);
  expect(captured.messages.every((m: any) => m.role !== 'observation')).toBe(true);
  expect(captured.messages[1]).toEqual({ role: 'user', content: 'Observation: oops' });
});

// ───────── 重试 / 退避（降低真实 LLM 排队抖动）─────────

test('retries on 5xx then succeeds on next attempt', async () => {
  let n = 0;
  const fakeFetch = async () => {
    n++;
    if (n < 2) return { ok: false, status: 503, text: async () => 'busy' };
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: 'OK' } }] }) };
  };
  const p = new OpenAICompatProvider({ baseUrl: 'https://x', apiKey: 'k', fetch: fakeFetch as any, maxRetries: 3, baseDelayMs: 1 });
  const r = await p.complete([{ role: 'user', content: 'hi' }]);
  expect(r.text).toBe('OK');
  expect(n).toBe(2);
});

test('retries on network error (fetch throws) then succeeds', async () => {
  let n = 0;
  const fakeFetch = async () => {
    n++;
    if (n < 2) throw new Error('ECONNRESET');
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: 'OK' } }] }) };
  };
  const p = new OpenAICompatProvider({ baseUrl: 'https://x', apiKey: 'k', fetch: fakeFetch as any, maxRetries: 3, baseDelayMs: 1 });
  const r = await p.complete([{ role: 'user', content: 'hi' }]);
  expect(r.text).toBe('OK');
  expect(n).toBe(2);
});

test('429 is retryable and honors Retry-After', async () => {
  let n = 0;
  const fakeFetch = async () => {
    n++;
    if (n < 2) return { ok: false, status: 429, headers: { get: (h: string) => (h.toLowerCase() === 'retry-after' ? '0' : null) }, text: async () => 'rate' };
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: 'OK' } }] }) };
  };
  const p = new OpenAICompatProvider({ baseUrl: 'https://x', apiKey: 'k', fetch: fakeFetch as any, maxRetries: 3, baseDelayMs: 1 });
  const r = await p.complete([{ role: 'user', content: 'hi' }]);
  expect(r.text).toBe('OK');
  expect(n).toBe(2);
});

test('4xx (non-429) does NOT retry — single attempt, AuthError', async () => {
  let n = 0;
  const fakeFetch = async () => { n++; return { ok: false, status: 401, text: async () => 'bad key' }; };
  const p = new OpenAICompatProvider({ baseUrl: 'https://x', apiKey: 'k', fetch: fakeFetch as any, maxRetries: 3, baseDelayMs: 1 });
  await expect(p.complete([{ role: 'user', content: 'hi' }])).rejects.toThrow(/auth|401/i);
  expect(n).toBe(1);
});

test('exhausts retries on persistent 500 then throws', async () => {
  let n = 0;
  const fakeFetch = async () => { n++; return { ok: false, status: 500, text: async () => 'boom' }; };
  const p = new OpenAICompatProvider({ baseUrl: 'https://x', apiKey: 'k', fetch: fakeFetch as any, maxRetries: 2, baseDelayMs: 1 });
  await expect(p.complete([{ role: 'user', content: 'hi' }])).rejects.toThrow(/500|boom|provider/i);
  expect(n).toBe(3); // initial attempt + 2 retries
});

test('timeout aborts hung request and retries', async () => {
  let n = 0;
  const fakeFetch = async (_url: string, init: any) => {
    n++;
    if (n < 2) {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new Error('aborted')));
      });
    }
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: 'OK' } }] }) };
  };
  const p = new OpenAICompatProvider({ baseUrl: 'https://x', apiKey: 'k', fetch: fakeFetch as any, maxRetries: 3, baseDelayMs: 1, timeoutMs: 50 });
  const r = await p.complete([{ role: 'user', content: 'hi' }]);
  expect(r.text).toBe('OK');
  expect(n).toBe(2);
});
