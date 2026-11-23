"""Guardrail policy — Python port of legacy ``src/guardrail/guardrail.ts``.

IMPORTANT: this is a *defense-in-depth* heuristic layer, NOT a security boundary.
The enforceable boundary is the execution sandbox (``safefix.runtime``). Regex /
token rules can always be bypassed by a sufficiently creative command; they exist
to force human approval on obviously dangerous actions and to catch accidents.

Preserved behaviours:
- whole-token matching after shell tokenization (no substring false positives);
- Windows deletion rules matched on the raw string before POSIX tokenization;
- recursive subshell unwrapping (bash/sh/zsh/dash/powershell/pwsh/cmd/wsl), depth-capped;
- state-aware escalation: any deletion attempt right after a denied action -> high;
- tokenize failure -> forced approval (high).
"""

from __future__ import annotations

import re
import shlex

from safefix.models import Action, GuardrailVerdict, SessionState

# Port of dangerPatterns.json (id -> severity, reason).
_PATTERNS: dict[str, tuple[str, str]] = {
    "recursive-delete": ("high", "recursive/forced deletion (any target path)"),
    "windows-del-recursive": ("high", "Windows recursive/forced deletion (del /s, del /f)"),
    "windows-rmdir-recursive": ("high", "Windows recursive dir removal (rmdir /s, rd /s)"),
    "windows-remove-item-recurse": (
        "high",
        "PowerShell recursive removal (Remove-Item -Recurse, ri -Recurse)",
    ),
    "privilege-escalation": ("high", "privilege escalation"),
    "remote-script-exec": ("high", "piping remote content into a shell"),
    "db-destroy": ("high", "database destruction"),
    "system-write": ("high", "writing to system paths"),
    "fork-bomb": ("high", "fork bomb pattern"),
    "cred-exfil": ("high", "outbound request carrying auth/secret header"),
    "plain-rm": ("low", "single-target rm (no -rf)"),
    "deny-escalation": ("high", "file deletion attempted right after a denied action (split-command bypass)"),
    "subshell-bypass": (
        "high",
        "shell wrapper unwrapped (bash/sh/powershell/cmd/wsl -c); inner command audited",
    ),
}

_SUBSHELL_DEPTH_LIMIT = 5
_POSIX_SHELLS = ("bash", "sh", "zsh", "dash")
_PS_SHELLS = ("powershell", "pwsh")
_DELETION_RE = re.compile(r"\b(rm|unlink|shred|del|erase|rmdir|rd|remove-item|ri)\b")


def _pick(pattern_id: str) -> tuple[str, str, str]:
    severity, reason = _PATTERNS[pattern_id]
    return pattern_id, severity, reason


def _tokenize(cmd: str) -> list[str]:
    """Shell-quote equivalent: posix shlex with operator punctuation, lowercased.

    Raises ValueError on malformed input (e.g. unclosed quotes) -> forced approval.
    """
    lex = shlex.shlex(cmd, posix=True, punctuation_chars="|;&<>")
    lex.whitespace_split = True
    return [t.lower() for t in lex]


def _pipe_to_shell(tokens: list[str]) -> bool:
    return any(
        t == "|" and i + 1 < len(tokens) and tokens[i + 1] in ("sh", "bash") for i, t in enumerate(tokens)
    )


def _match(tokens: list[str]) -> tuple[str, str, str] | None:
    s = " ".join(tokens)

    def has(*needles: str) -> bool:
        return all(n in tokens for n in needles)

    if has("rm") and (has("-rf") or has("--no-preserve-root") or (has("-r") and has("-f"))):
        return _pick("recursive-delete")
    if has("rm") and (has("-r") or has("-f")) and ("/etc" in s or "/usr" in s):
        return _pick("recursive-delete")
    if has("sudo") or has("su") or (has("chmod") and has("777")):
        return _pick("privilege-escalation")
    if (has("curl") or has("wget")) and _pipe_to_shell(tokens):
        return _pick("remote-script-exec")
    if "drop table" in s or "drop database" in s or "truncate" in s:
        return _pick("db-destroy")
    if "> /etc/" in s or "> /dev/sd" in s or "/etc/cron" in s or ":(){" in s:
        return _pick("system-write")
    if ":(){:|:&};:" in s:
        return _pick("fork-bomb")
    if (has("curl") or has("wget")) and ("authorization" in s or ("-h" in s and "token" in s)):
        return _pick("cred-exfil")
    if has("rm") and not has("-rf") and not has("-r") and not has("-f"):
        return _pick("plain-rm")
    return None


def _match_windows(raw: str) -> tuple[str, str, str] | None:
    """Windows commands are not POSIX shell; match on the raw lowercased string."""
    if re.search(r"\bdel\b", raw) and ("/s" in raw or "/f" in raw):
        return _pick("windows-del-recursive")
    if (re.search(r"\brmdir\b", raw) or re.search(r"\brd\b", raw)) and "/s" in raw:
        return _pick("windows-rmdir-recursive")
    if (re.search(r"\bremove-item\b", raw) or re.search(r"\bri\b", raw)) and "-recurse" in raw:
        return _pick("windows-remove-item-recurse")
    return None


def _extract_inner(tokens: list[str]) -> str | None:
    if not tokens:
        return None
    t0 = tokens[0]
    if t0 in _POSIX_SHELLS:
        if "-c" in tokens:
            i = tokens.index("-c")
            return tokens[i + 1] if i + 1 < len(tokens) else None
        return None
    if t0 in _PS_SHELLS:
        for i, t in enumerate(tokens):
            if t in ("-c", "-command"):
                return " ".join(tokens[i + 1 :]) if i + 1 < len(tokens) else None
        return None
    if t0 in ("cmd", "cmd.exe"):
        for i, t in enumerate(tokens):
            if t in ("/c", "/k"):
                return " ".join(tokens[i + 1 :]) if i + 1 < len(tokens) else None
        return None
    return None


def _assess_tokens(tokens: list[str], depth: int) -> tuple[tuple[str, str, str], bool] | None:
    """Match current layer first, then unwrap subshell wrappers recursively."""
    hit = _match(tokens)
    if hit:
        return hit, False
    if depth <= 0 or not tokens:
        return None
    if tokens[0] == "wsl" and len(tokens) > 1:
        r = _assess_tokens(tokens[1:], depth - 1)
        return (r[0], True) if r else None
    inner = _extract_inner(tokens)
    if inner is None:
        return None
    win = _match_windows(inner)
    if win:
        return win, True
    try:
        inner_tokens = _tokenize(inner)
    except ValueError:
        return ("tokenize-failed", "high", "malformed inner command, forcing approval"), True
    r = _assess_tokens(inner_tokens, depth - 1)
    return (r[0], True) if r else None


def assess(action: Action, state: SessionState | None = None) -> GuardrailVerdict:
    """Rate a tool action. Only command-carrying tools are audited."""
    if action.tool not in ("run_shell", "run_tests"):
        return GuardrailVerdict(severity="none")
    cmd = str(action.args.get("command") or "")
    raw = cmd.lower()

    if state is not None and state.last_denied and _DELETION_RE.search(raw):
        pid, severity, reason = _pick("deny-escalation")
        return GuardrailVerdict(severity=severity, reasons=[f"{pid}: {reason}"])

    win = _match_windows(raw)
    if win:
        return GuardrailVerdict(severity=win[1], reasons=[f"{win[0]}: {win[2]}"])

    try:
        tokens = _tokenize(cmd)
    except ValueError:
        return GuardrailVerdict(
            severity="high", reasons=["tokenize-failed: malformed command, forcing approval"]
        )

    res = _assess_tokens(tokens, _SUBSHELL_DEPTH_LIMIT)
    if res is None:
        return GuardrailVerdict(severity="none")
    hit, via_subshell = res
    reasons = [f"{hit[0]}: {hit[2]}"]
    if via_subshell:
        pid, _, reason = _pick("subshell-bypass")
        reasons.insert(0, f"{pid}: {reason}")
    return GuardrailVerdict(severity=hit[1], reasons=reasons)
