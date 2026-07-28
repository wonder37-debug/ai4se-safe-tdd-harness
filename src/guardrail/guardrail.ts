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

// 管道入 shell 判定：token 序列中 '|' 的下一个 token 为 sh/bash 才算，
// 避免 'echo curly | sh' 被子串 'curl' 误报（误报源头在 has 的子串兑底，已移除）。
function pipeToShell(tokens: string[]): boolean {
  return tokens.some((t, i) => t === '|' && (tokens[i + 1] === 'sh' || tokens[i + 1] === 'bash'));
}

function match(tokens: string[]): { id: string; severity: Severity; reason: string } | null {
  const s = join(tokens);
  // 仅整词 token 匹配：命令名/标志不再用 s.includes 兑底，
  // 消除 echo issue 命中 'su'、echo curly 命中 'curl' 一类子串误报；
  // token 层仍能揭穿 r""m 一类引号混淆（shell-quote 已归一化）。
  const has = (...needles: string[]) => needles.every(n => tokens.includes(n));

  // 递归/强制删除：出现 -rf / --no-preserve-root / （-r 且 -f）即 high，
  // 不再强制根路径前缀（rm -rf node_modules 同样不可逆）；/etc、/usr 作补充匹配。
  if (has('rm') && (has('-rf') || has('--no-preserve-root') || (has('-r') && has('-f'))))
    return pick('recursive-delete');
  if (has('rm') && (has('-r') || has('-f')) && (s.includes('/etc') || s.includes('/usr')))
    return pick('recursive-delete');
  if (has('sudo') || has('su') || has('chmod') && has('777'))
    return pick('privilege-escalation');
  if ((has('curl') || has('wget')) && pipeToShell(tokens))
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

// 漏洞 3 修复：子壳/套壳命令绕过。
// bash -c "rm -rf /" 经 shell-quote 解析后内部命令是单个字符串 token，
// 整词匹配完全失明。解包 bash/sh/zsh/dash/powershell/pwsh/cmd/wsl 的包裹层，
// 提取内部真实子命令递归审计；深度上限防无限套娃。
// 仅当首 token 是 shell 解释器时才解包，避免 echo/git commit 等普通参数误报。
const SUBSHELL_DEPTH_LIMIT = 5;
const POSIX_SHELLS = ['bash', 'sh', 'zsh', 'dash'];
const PS_SHELLS = ['powershell', 'pwsh'];

// 提取套壳命令的内部子命令串；非套壳调用返回 null
function extractInner(tokens: string[]): string | null {
  const t0 = tokens[0];
  if (POSIX_SHELLS.includes(t0)) {
    const i = tokens.indexOf('-c');
    return i >= 0 && tokens[i + 1] ? tokens[i + 1] : null;
  }
  if (PS_SHELLS.includes(t0)) {
    // token 已小写：-Command → -command；PowerShell 允许多参数拼接成脚本体
    const i = tokens.findIndex(t => t === '-c' || t === '-command');
    return i >= 0 && tokens.length > i + 1 ? tokens.slice(i + 1).join(' ') : null;
  }
  if (t0 === 'cmd' || t0 === 'cmd.exe') {
    const i = tokens.findIndex(t => t === '/c' || t === '/k');
    return i >= 0 && tokens.length > i + 1 ? tokens.slice(i + 1).join(' ') : null;
  }
  return null;
}

// 递归审计 token 序列：先按现有规则匹配，未命中再解包子壳内部命令继续审计
function assessTokens(tokens: string[], depth: number):
  { hit: { id: string; severity: Severity; reason: string }; viaSubshell: boolean } | null {
  const hit = match(tokens);
  if (hit) return { hit, viaSubshell: false };
  if (depth <= 0 || tokens.length === 0) return null;
  // wsl 前缀剥离：wsl bash -c "..." 的实际命令从第二个 token 开始
  if (tokens[0] === 'wsl' && tokens.length > 1) {
    const r = assessTokens(tokens.slice(1), depth - 1);
    return r ? { ...r, viaSubshell: true } : null;
  }
  const inner = extractInner(tokens);
  if (inner === null) return null;
  // 内部命令同样要过 Windows 删除护栏（如 bash -c "del /s ..."）
  const win = matchWindows(inner);
  if (win) return { hit: win, viaSubshell: true };
  let innerTokens: string[];
  try { innerTokens = toTokens(inner); }
  catch {
    // 内部命令无法解析：与外层 tokenize-failed 同样强制审批
    return { hit: { id: 'tokenize-failed', severity: 'high' as Severity, reason: 'malformed inner command, forcing approval' }, viaSubshell: true };
  }
  const r = assessTokens(innerTokens, depth - 1);
  return r ? { ...r, viaSubshell: true } : null;
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
    // 递归审计：先匹配当前层，未命中再解包子壳（bash -c 等）内部命令
    const res = assessTokens(tokens, SUBSHELL_DEPTH_LIMIT);
    if (!res) return { severity: 'none', reasons: [] };
    const reasons = [`${res.hit.id}: ${res.hit.reason}`];
    // 命中发生在解包之后：前置 subshell-bypass 标记，审批面板可见套壳链路
    if (res.viaSubshell) {
      const p = pick('subshell-bypass');
      reasons.unshift(`${p.id}: ${p.reason}`);
    }
    return { severity: res.hit.severity, reasons };
  },
};
