import { makeLoopFactory } from '../src/index';
import { EncryptedFileStore } from '../src/creds/credentialStore';
import { JsonConfigStore, ConfigStore, ProviderConfig } from '../src/creds/configStore';
import { HttpApprovalGateway } from '../src/approval/httpApprovalGateway';
import { EventStore } from '../src/loop/eventSink';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';

// The --web loopFactory binds OpenAICompatProvider. Its safety branches must
// short-circuit to provider_error WITHOUT touching the network, so the wiring
// is deterministically testable offline.

function factory(dir: string) {
  return makeLoopFactory({
    creds: new EncryptedFileStore(path.join(dir, 'c.enc')),
    config: new JsonConfigStore(path.join(dir, 'config.json')),
    approval: new HttpApprovalGateway(),
    eventStore: new EventStore(),
  });
}

// 记录 get() 调用次数的 spy，用于断言 loopFactory 确实读取了配置文件
class SpyConfig implements ConfigStore {
  calls = 0;
  constructor(private value: ProviderConfig) {}
  async get() { this.calls++; return this.value; }
  async set() {}
  clear() {}
}

test('provider_error when MASTER_PASSWORD unset (no network)', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'lf1-'));
  const prev = process.env.MASTER_PASSWORD;
  delete process.env.MASTER_PASSWORD;
  try {
    const r = await factory(dir)('do something', dir);
    expect(r.haltReason).toBe('provider_error');
  } finally {
    if (prev) process.env.MASTER_PASSWORD = prev;
  }
});

test('provider_error when API_BASE_URL unset (no network)', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'lf2-'));
  const prevM = process.env.MASTER_PASSWORD;
  const prevB = process.env.API_BASE_URL;
  process.env.MASTER_PASSWORD = 'x';
  delete process.env.API_BASE_URL;
  try {
    const r = await factory(dir)('do something', dir);
    expect(r.haltReason).toBe('provider_error');
  } finally {
    if (prevM) process.env.MASTER_PASSWORD = prevM; else delete process.env.MASTER_PASSWORD;
    if (prevB) process.env.API_BASE_URL = prevB; else delete process.env.API_BASE_URL;
  }
});

test('provider_error when encrypted creds unresolvable (no network)', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'lf3-'));
  // no creds.set() called → resolve() throws → provider_error before OpenAICompatProvider is constructed
  const prevM = process.env.MASTER_PASSWORD;
  const prevB = process.env.API_BASE_URL;
  process.env.MASTER_PASSWORD = 'x';
  process.env.API_BASE_URL = 'https://example.invalid';
  try {
    const r = await factory(dir)('do something', dir);
    expect(r.haltReason).toBe('provider_error');
  } finally {
    if (prevM) process.env.MASTER_PASSWORD = prevM; else delete process.env.MASTER_PASSWORD;
    if (prevB) process.env.API_BASE_URL = prevB; else delete process.env.API_BASE_URL;
  }
});

test('loopFactory 读取 config 文件取 baseUrl/model（config 优先于 env，离线可测）', async () => {
  // config 提供 baseUrl，env 不提供；MASTER 设置；creds 不可解 → 走到 creds.resolve 才短路，
  // 证明 baseUrl 来自 config（否则会在 baseUrl 检查处直接返回）。同时 spy 断言 get() 被调用。
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'lf4-'));
  const spy = new SpyConfig({ baseUrl: 'https://from-config.example/v1', model: 'cfg-model' });
  const prevM = process.env.MASTER_PASSWORD;
  const prevB = process.env.API_BASE_URL;
  const prevModel = process.env.MODEL;
  process.env.MASTER_PASSWORD = 'x';
  delete process.env.API_BASE_URL;
  delete process.env.MODEL;
  try {
    const run = makeLoopFactory({
      creds: new EncryptedFileStore(path.join(dir, 'c.enc')),
      config: spy,
      approval: new HttpApprovalGateway(),
      eventStore: new EventStore(),
    });
    const r = await run('do something', dir);
    expect(r.haltReason).toBe('provider_error'); // creds 不可解 → 短路（未触网）
    expect(spy.calls).toBe(1); // config.get() 被读取，而非只看 env
  } finally {
    if (prevM) process.env.MASTER_PASSWORD = prevM; else delete process.env.MASTER_PASSWORD;
    if (prevB) process.env.API_BASE_URL = prevB; else delete process.env.API_BASE_URL;
    if (prevModel) process.env.MODEL = prevModel; else delete process.env.MODEL;
  }
});
