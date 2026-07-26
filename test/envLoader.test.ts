import { parseEnvFile } from '../src/cli/envLoader';

test('解析 KEY=VALUE 行', () => {
  expect(parseEnvFile('A=1\nB=2')).toEqual({ A: '1', B: '2' });
});

test('忽略注释与空行', () => {
  expect(parseEnvFile('# comment\n\nA=1')).toEqual({ A: '1' });
});

test('剥离首尾引号', () => {
  expect(parseEnvFile('A="hi there"\nB=\'x\'')).toEqual({ A: 'hi there', B: 'x' });
});

test('跳过不含 = 的行', () => {
  expect(parseEnvFile('nokey\nA=1')).toEqual({ A: '1' });
});

test('空文本 → 空记录', () => {
  expect(parseEnvFile('')).toEqual({});
});

test('CRLF 行尾兼容', () => {
  expect(parseEnvFile('A=1\r\nB=2\r\n')).toEqual({ A: '1', B: '2' });
});
