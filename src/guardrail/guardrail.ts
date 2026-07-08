import { Action, GuardrailVerdict, Severity } from '../types';
import { parse as shellParse } from 'shell-quote';
import patterns from './dangerPatterns.json';

interface Tok { op?: string; word?: string; }
type Node = Tok | string | number;

function toTokens(cmd: string): string[] {
  let nodes: Node[];
  try { nodes = shellParse(cmd) as Node[]; }
  catch { throw new Error('tokenize-failed'); }
  const out: string[] = [];
  for (const n of nodes) {
    if (typeof n === 'string' || typeof n === 'number') out.push(String(n));
    else if (n && typeof n === 'object' && 'word' in n && typeof (n as Tok).word === 'string') out.push((n as Tok).word!);
    else if (n && typeof n === 'object' && 'op' in n && typeof (n as Tok).op === 'string') out.push((n as Tok).op!);
  }
  return out.map(t => t.toLowerCase());
}

function join(tokens: string[]): string { return tokens.join(' '); }

function match(tokens: string[]): { id: string; severity: Severity; reason: string } | null {
  const s = join(tokens);
  const has = (...needles: string[]) => needles.every(n => tokens.includes(n) || s.includes(n));

  if (has('rm') && (has('-rf') || has('--no-preserve-root') || has('-r', '-f')) && (has('/') || has('/*') || s.includes('/etc') || s.includes('/usr')))
    return pick('recursive-delete');
  if (has('sudo') || has('su') || has('chmod') && has('777'))
    return pick('privilege-escalation');
  if ((has('curl') || has('wget')) && (s.includes('| sh') || s.includes('|sh') || s.includes('| bash') || s.includes('|bash')))
    return pick('remote-script-exec');
  if (s.includes('drop table') || s.includes('drop database') || s.includes('truncate'))
    return pick('db-destroy');
  if (s.includes('> /etc/') || s.includes('> /dev/sd') || s.includes('/etc/cron') || s.includes(':(){') )
    return pick('system-write');
  if (s.includes(':(){:|:&};:'))
    return pick('fork-bomb');
  if ((has('curl') || has('wget')) && (s.includes('authorization') || s.includes('-h') && s.includes('token')))
    return pick('cred-exfil');
  if (has('rm') && !has('-rf') && !has('-r') && !has('-f'))
    return pick('plain-rm');
  return null;
}

function pick(id: string) {
  const p = (patterns as any[]).find(p => p.id === id)!;
  return { id, severity: p.severity as Severity, reason: p.reason };
}

export const Guardrail = {
  assess(action: Action): GuardrailVerdict {
    if (action.tool !== 'run_shell' && action.tool !== 'run_tests') return { severity: 'none', reasons: [] };
    const cmd = String(action.args.command ?? '');
    let tokens: string[];
    try { tokens = toTokens(cmd); }
    catch { return { severity: 'high', reasons: ['tokenize-failed: malformed command, forcing approval'] }; }
    const hit = match(tokens);
    if (!hit) return { severity: 'none', reasons: [] };
    return { severity: hit.severity, reasons: [`${hit.id}: ${hit.reason}`] };
  },
};
