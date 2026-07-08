import { EncryptedFileStore } from '../src/creds/credentialStore';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';

test('set then resolve returns key; status present without echoing', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'cred-'));
  const store = new EncryptedFileStore(path.join(dir, 'creds.enc'));
  await store.set('sk-secret', 'master-pass');
  expect(store.status()).toEqual({ present: true, source: 'encrypted-file' });
  expect(store.status()).not.toHaveProperty('key');
  const r = await store.resolve('master-pass');
  expect(r.key).toBe('sk-secret');
  expect(r.source).toBe('encrypted-file');
});

test('wrong master password fails to resolve', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'cred-'));
  const store = new EncryptedFileStore(path.join(dir, 'creds.enc'));
  await store.set('sk-secret', 'master-pass');
  await expect(store.resolve('wrong')).rejects.toThrow();
});

test('clear removes the file; status not present', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'cred-'));
  const store = new EncryptedFileStore(path.join(dir, 'creds.enc'));
  await store.set('sk-secret', 'master-pass');
  store.clear();
  expect(store.status().present).toBe(false);
});
