import { Event } from '../types';
export interface EventSink { emit(e: Omit<Event, 'id'>): void; }
export const noopSink: EventSink = { emit() {} };
export class EventStore implements EventSink {
  private events: Event[] = [];
  private next = 1;
  emit(e: Omit<Event, 'id'>): void { this.events.push({ id: this.next++, ...e }); if (this.events.length > 1000) this.events.shift(); }
  since(id: number): Event[] { return this.events.filter(e => e.id > id); }
  all(): Event[] { return [...this.events]; }
}
