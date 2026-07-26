import { resolveCredentials } from '../src/creds/credResolver';

// ponytail: 凭据与配置 store 用最小手写 fake，避免引入整个实现类。
function okCreds(key: string) {
  return {
    status: () => ({ present: true, source: 'encrypted-file' }),
    resolve: async (m: string) =>
      m === 'master' ? { key, source: 'encrypted-file' } : Promise.reject(new Error('bad master')),
    set: async () => {},
    clear: () => {},
  };
}
function cfg(v: { baseUrl?: string; model?: string }) {
  return { get: async () => v, set: async () => {}, clear: () => {} };
}

test('master + 可解密 key + baseUrl → encrypted-file', async () => {
  const r = await resolveCredentials({
    creds: okCreds('sk-1') as any, config: cfg({ baseUrl: 'https://x/v1' }) as any,
    envFile: {}, masterPassword: 'master', env: {},
  });
  expect(r?.source).toBe('encrypted-file');
  expect(r?.key).toBe('sk-1');
  expect(r?.baseUrl).toBe('https://x/v1');
});

test('无 master 但 .env 有 API_KEY → env-file 兜底', async () => {
  const r = await resolveCredentials({
    creds: okCreds('sk-1') as any, config: cfg({}) as any,
    envFile: { API_KEY: 'sk-env', API_BASE_URL: 'https://y/v1' },
    masterPassword: undefined, env: {},
  });
  expect(r?.source).toBe('env-file');
  expect(r?.key).toBe('sk-env');
});

test('process env API_KEY → env 兜底', async () => {
  const r = await resolveCredentials({
    creds: okCreds('sk-1') as any, config: cfg({}) as any,
    envFile: {}, masterPassword: undefined, env: { API_KEY: 'sk-penv', API_BASE_URL: 'https://z/v1' },
  });
  expect(r?.source).toBe('env');
  expect(r?.key).toBe('sk-penv');
});

test('master 错但 .env 有 key → 降级 env-file', async () => {
  const r = await resolveCredentials({
    creds: okCreds('sk-1') as any, config: cfg({}) as any,
    envFile: { API_KEY: 'sk-env', API_BASE_URL: 'https://y/v1' },
    masterPassword: 'wrong', env: {},
  });
  expect(r?.source).toBe('env-file');
});

test('全无 → null（降级离线）', async () => {
  const r = await resolveCredentials({
    creds: okCreds('sk-1') as any, config: cfg({}) as any,
    envFile: {}, masterPassword: undefined, env: {},
  });
  expect(r).toBeNull();
});

test('有 key 但无 baseUrl → null', async () => {
  const r = await resolveCredentials({
    creds: okCreds('sk-1') as any, config: cfg({}) as any,
    envFile: { API_KEY: 'sk-env' }, masterPassword: undefined, env: {},
  });
  expect(r).toBeNull();
});

test('config baseUrl 优先于 envFile baseUrl', async () => {
  const r = await resolveCredentials({
    creds: okCreds('sk-1') as any, config: cfg({ baseUrl: 'https://cfg/v1' }) as any,
    envFile: { API_KEY: 'sk-env', API_BASE_URL: 'https://envfile/v1' },
    masterPassword: undefined, env: {},
  });
  expect(r?.baseUrl).toBe('https://cfg/v1');
});

test('model 来自 config / envFile / env', async () => {
  const r = await resolveCredentials({
    creds: okCreds('sk-1') as any, config: cfg({ model: 'cfg-model' }) as any,
    envFile: { API_KEY: 'sk-env', API_BASE_URL: 'https://y/v1', MODEL: 'envfile-model' },
    masterPassword: undefined, env: {},
  });
  expect(r?.model).toBe('cfg-model');
});
