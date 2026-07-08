import { greet } from '../src/index';

test('smoke: jest + ts + import works', () => {
  expect(greet('harness')).toBe('hello, harness');
});
