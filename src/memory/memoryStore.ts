import * as fs from 'fs/promises';
import * as path from 'path';

export interface Note { key: string; note: string; }

export class MemoryStore {
  constructor(private dir: string) {}
  private file(key: string) { return path.join(this.dir, `${key}.md`); }

  // Task 10：统一 fs/promises 异步 API，不再在函数内 require('fs') 同步读
  async read(): Promise<Note[]> {
    let files: string[];
    try { files = await fs.readdir(this.dir); } catch { return []; } // 目录不存在 → 空
    const notes: Note[] = [];
    for (const f of files.filter(f => f.endsWith('.md'))) {
      notes.push({ key: f.replace(/\.md$/, ''), note: await fs.readFile(path.join(this.dir, f), 'utf8') });
    }
    return notes;
  }

  async write(key: string, note: string): Promise<void> {
    await fs.mkdir(this.dir, { recursive: true });
    await fs.writeFile(this.file(key), note);
  }

  async clear(key: string): Promise<void> {
    await fs.rm(this.file(key), { force: true });
  }

  async systemPrompt(): Promise<string> {
    const notes = await this.read();
    if (notes.length === 0) return '';
    return 'Project notes:\n' + notes.map(n => `- [${n.key}] ${n.note}`).join('\n');
  }
}
