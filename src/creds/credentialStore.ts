import * as fs from 'fs/promises';
import * as crypto from 'crypto';
import { existsSync } from 'fs';

export interface CredentialStore {
  status(): { present: boolean; source: string };
  resolve(masterPassword: string): Promise<{ key: string; source: string }>;
  set(key: string, masterPassword: string): Promise<void>;
  clear(): void;
}

const ALGO = 'aes-256-gcm';
function deriveKey(master: string): Buffer {
  return crypto.pbkdf2Sync(master, 'ai4se-salt', 100000, 32, 'sha256');
}

export class EncryptedFileStore implements CredentialStore {
  constructor(private file: string) {}

  status(): { present: boolean; source: string } {
    return { present: existsSync(this.file), source: 'encrypted-file' };
  }

  async set(key: string, masterPassword: string): Promise<void> {
    const keyBuf = deriveKey(masterPassword);
    const iv = crypto.randomBytes(12);
    const cipher = crypto.createCipheriv(ALGO, keyBuf, iv);
    const ct = Buffer.concat([cipher.update(key, 'utf8'), cipher.final()]);
    const tag = cipher.getAuthTag();
    const blob = Buffer.concat([iv, tag, ct]);
    await fs.writeFile(this.file, blob);
  }

  async resolve(masterPassword: string): Promise<{ key: string; source: string }> {
    if (!existsSync(this.file)) throw new Error('no encrypted credentials');
    const buf = await fs.readFile(this.file);
    const iv = buf.subarray(0, 12);
    const tag = buf.subarray(12, 28);
    const ct = buf.subarray(28);
    const keyBuf = deriveKey(masterPassword);
    const decipher = crypto.createDecipheriv(ALGO, keyBuf, iv);
    decipher.setAuthTag(tag);
    const key = Buffer.concat([decipher.update(ct), decipher.final()]).toString('utf8');
    return { key, source: 'encrypted-file' };
  }

  clear(): void {
    const { rmSync } = require('fs');
    if (existsSync(this.file)) rmSync(this.file, { force: true });
  }
}
