import { Action, GuardrailVerdict, Severity, SessionState } from '../types';
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

// 漏洞 2 修复：Windows 递归/强制删除护栏。
// Windows 命令非 POSIX shell，shell-quote 会误切（反斜杠路径 / /s 标志）；
// 故在 tokenize 之前对原始小写串做词边界 + includes 精准匹配，先于 Linux 规则判定。
function matchWindows(raw: string): { id: string; severity: Severity; reason: string } | null {
  // del + /s 或 /f（递归 或 强制删除）
  if (/\bdel\b/.test(raw) && (raw.includes('/s') || raw.includes('/f')))
    return pick('windows-del-recursive');
  // rmdir / rd + /s（递归删除目录）
  if ((/\brmdir\b/.test(raw) || /\brd\b/.test(raw)) && raw.includes('/s'))
    return pick('windows-rmdir-recursive');
  // PowerShell Remove-Item -Recurse 或别名 ri -Recurse
  if ((/\bremove-item\b/.test(raw) || /\bri\b/.test(raw)) && raw.includes('-recurse'))
    return pick('windows-remove-item-recurse');
  return null;
}

// 状态感知护栏：上一轮动作刚被用户拒绝（Deny）时，任何文件删除尝试
// （含看似无害的 rm file.txt / del a.txt）都升级为 high，堵住“拒绝后分拆命令绕过”。
// 仅在 lastDenied=true 时生效；正常编码状态下单文件删除仍保持 low/none，防审批疲劳。
function isDeletionAttempt(raw: string): boolean {
  return /\b(rm|unlink|shred|del|erase|rmdir|rd|remove-item|ri)\b/.test(raw);
}

export const Guardrail = {
  assess(action: Action, state?: SessionState): GuardrailVerdict {
    if (action.tool !== 'run_shell' && action.tool !== 'run_tests') return { severity: 'none', reasons: [] };
    const cmd = String(action.args.command ?? '');
    const raw = cmd.toLowerCase();
    // 状态感知升级优先判定：刚被拒绝后的任何删除尝试强制 high
    if (state?.lastDenied && isDeletionAttempt(raw)) {
      const p = pick('deny-escalation');
      return { severity: p.severity, reasons: [`${p.id}: ${p.reason}`] };
    }
    // Windows 删除命令优先判定（tokenize 前按原始串匹配，精准且不受反斜杠影响）
    const winHit = matchWindows(raw);
    if (winHit) return { severity: winHit.severity, reasons: [`${winHit.id}: ${winHit.reason}`] };
    let tokens: string[];
    try { tokens = toTokens(cmd); }
    catch { return { severity: 'high', reasons: ['tokenize-failed: malformed command, forcing approval'] }; }
    const hit = match(tokens);
    if (!hit) return { severity: 'none', reasons: [] };
    return { severity: hit.severity, reasons: [`${hit.id}: ${hit.reason}`] };
  },
};
