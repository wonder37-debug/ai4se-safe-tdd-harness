import { LLMProvider } from './provider';
import { Message } from '../types';

export class ScriptedMock implements LLMProvider {
  private queue: string[];
  private sticky: boolean;
  private last: string | null = null;

  constructor(responses: string[], sticky = false) {
    this.queue = [...responses];
    this.sticky = sticky;
  }

  async complete(_messages: Message[]): Promise<{ text: string; stopReason: string }> {
    if (this.queue.length > 0) {
      this.last = this.queue.shift()!;
      return { text: this.last, stopReason: 'ok' };
    }
    if (this.sticky && this.last !== null) {
      return { text: this.last, stopReason: 'ok' };
    }
    throw new Error('ScriptedMock: response queue exhausted and not sticky');
  }
}
