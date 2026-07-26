import { parseArgs } from '../src/cli/args';

test('无参数 → interactive 默认', () => {
  expect(parseArgs([]).mode).toBe('interactive');
});

test('--web → web 模式', () => {
  expect(parseArgs(['--web']).mode).toBe('web');
});

test('--task "<desc>" → task 模式带 task', () => {
  const a = parseArgs(['--task', 'implement add']);
  expect(a.mode).toBe('task');
  expect(a.task).toBe('implement add');
});

test('--task= 形式', () => {
  const a = parseArgs(['--task=do x']);
  expect(a.mode).toBe('task');
  expect(a.task).toBe('do x');
});

test('--cwd "<path>" 被捕获', () => {
  const a = parseArgs(['--task', 't', '--cwd', '/tmp/x']);
  expect(a.cwd).toBe('/tmp/x');
});

test('--cwd= 形式', () => {
  const a = parseArgs(['--cwd=/ws']);
  expect(a.cwd).toBe('/ws');
});

test('--interactive / -i → interactive', () => {
  expect(parseArgs(['-i']).mode).toBe('interactive');
  expect(parseArgs(['--interactive']).mode).toBe('interactive');
});

test('--help / -h → help', () => {
  expect(parseArgs(['--help']).mode).toBe('help');
  expect(parseArgs(['-h']).mode).toBe('help');
});

test('裸位置参数 → task', () => {
  const a = parseArgs(['implement add']);
  expect(a.mode).toBe('task');
  expect(a.task).toBe('implement add');
});

test('-i 时 --cwd 仍可设', () => {
  const a = parseArgs(['-i', '--cwd', '/ws']);
  expect(a.mode).toBe('interactive');
  expect(a.cwd).toBe('/ws');
});
