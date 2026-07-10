import { makeLoopFactory } from '../src/index';
import { EncryptedFileStore } from '../src/creds/credentialStore';
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
    approval: new HttpApprovalGateway(),
    eventStore: new EventStore(),
  });
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
