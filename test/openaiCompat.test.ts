import { OpenAICompatProvider } from '../src/llm/openaiCompat';

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
