import * as fs from 'fs/promises';
import * as path from 'path';

export interface Note { key: string; note: string; }

export class MemoryStore {
  constructor(private dir: string) {}
  private file(key: string) { return path.join(this.dir, `${key}.md`); }

  read(): Note[] {
    const { readdirSync, readFileSync, existsSync } = require('fs');
    if (!existsSync(this.dir)) return [];
    return readdirSync(this.dir)
      .filter((f: string) => f.endsWith('.md'))
      .map((f: string) => ({ key: f.replace(/\.md$/, ''), note: readFileSync(path.join(this.dir, f), 'utf8') }));
  }

  async write(key: string, note: string): Promise<void> {
    await fs.mkdir(this.dir, { recursive: true });
    await fs.writeFile(this.file(key), note);
  }

  clear(key: string): void {
    const { existsSync, rmSync } = require('fs');
    if (existsSync(this.file(key))) rmSync(this.file(key), { force: true });
  }

  systemPrompt(): string {
    const notes = this.read();
    if (notes.length === 0) return '';
    return 'Project notes:\n' + notes.map(n => `- [${n.key}] ${n.note}`).join('\n');
  }
}
