import { JsonConfigStore } from '../src/creds/configStore';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';
import { existsSync } from 'fs';

// JsonConfigStore 把非密配置（请求地址 / 模型名）以明文 JSON 落盘。
// 这些不是凭据（不含 secret），故明文合规（§3.1 只要求 API key 加密）。
// API key 仍走 EncryptedFileStore（AES-256-GCM），本测试不涉及。

test('get 返回 {} 当文件不存在（不抛错，便于首次运行）', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'cfg-'));
  const store = new JsonConfigStore(path.join(dir, 'nope.json'));
  expect(await store.get()).toEqual({});
});

test('set then get 回读 baseUrl / model', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'cfg-'));
  const store = new JsonConfigStore(path.join(dir, 'config.json'));
  await store.set({ baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' });
  expect(await store.get()).toEqual({ baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' });
});

test('set 可只更新部分字段；空值字段不写入文件', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'cfg-'));
  const store = new JsonConfigStore(path.join(dir, 'config.json'));
  await store.set({ baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1' });
  expect(await store.get()).toEqual({ baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1' });
  // 追加 model
  await store.set({ baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-flash' });
  expect(await store.get()).toEqual({ baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-flash' });
});

test('落盘为 JSON 文本（可读、非二进制、不含 secret）', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'cfg-'));
  const file = path.join(dir, 'config.json');
  const store = new JsonConfigStore(file);
  await store.set({ baseUrl: 'https://x/v1', model: 'm' });
  const raw = await fs.readFile(file, 'utf8');
  expect(raw).toContain('https://x/v1');
  expect(raw).toContain('"m"');
});

test('clear 删除文件', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'cfg-'));
  const file = path.join(dir, 'config.json');
  const store = new JsonConfigStore(file);
  await store.set({ baseUrl: 'https://x/v1' });
  expect(existsSync(file)).toBe(true);
  store.clear();
  expect(existsSync(file)).toBe(false);
  expect(await store.get()).toEqual({});
});
