import { FeedbackClassifier } from '../src/feedback/feedbackClassifier';
import { JestParser } from '../src/feedback/jestParser';
import * as fs from 'fs/promises';
import * as path from 'path';

const fc = new FeedbackClassifier(new JestParser());

async function fixture(name: string): Promise<string> {
  return fs.readFile(path.join(__dirname, '..', 'demo', 'fixtures', name), 'utf8');
}

test('assertion failure parsed to errorType=assertion with file:line', async () => {
  const fb = fc.parse({ ok: false, exitCode: 1, stderr: await fixture('jest-assertion-fail.txt') });
  expect(fb.errorType).toBe('assertion');
  expect(fb.failedTests).toContain("add › returns sum");
  expect(fb.assertion?.file).toBe('add.test.js');
  expect(fb.assertion?.line).toBe(4);
});

test('syntax failure parsed to errorType=syntax', async () => {
  const fb = fc.parse({ ok: false, exitCode: 1, stderr: await fixture('jest-syntax-fail.txt') });
  expect(fb.errorType).toBe('syntax');
  expect(fb.assertion?.file).toBe('add.test.js');
});

test('unrecognized output falls back to other with truncated evidence', async () => {
  const fb = fc.parse({ ok: false, exitCode: 1, stderr: 'something weird\n' });
  expect(fb.errorType).toBe('other');
  expect(fb.evidence).toContain('something weird');
});
