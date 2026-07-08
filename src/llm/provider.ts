import { Message } from '../types';

export interface LLMProvider {
  complete(messages: Message[]): Promise<{ text: string; stopReason: string }>;
}
