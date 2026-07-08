import { Feedback } from '../types';
import { Parser } from './feedbackClassifier';

const FAIL_BLOCK = /●\s+(.+)/g;
const AT_LINE = /at\s+(?:.*?\s)?\(?(.+?):(\d+):\d+\)?/;

export class JestParser implements Parser {
  parse(_stdout: string, stderr: string): Feedback {
    const failedTests: string[] = [];
    let m: RegExpExecArray | null;
    while ((m = FAIL_BLOCK.exec(stderr)) !== null) failedTests.push(m[1].trim());

    if (/SyntaxError|Test suite failed to parse|Unexpected token/i.test(stderr)) {
      const at = AT_LINE.exec(stderr);
      return {
        errorType: 'syntax',
        failedTests,
        assertion: at ? { file: at[1], line: Number(at[2]), snippet: 'SyntaxError' } : undefined,
        evidence: stderr,
        hint: at ? `fix syntax at ${at[1]}:${at[2]}` : 'fix syntax error',
      };
    }
    if (failedTests.length > 0 || /expect\(received\)\.toBe\(expected\)/i.test(stderr)) {
      const at = AT_LINE.exec(stderr);
      return {
        errorType: 'assertion',
        failedTests,
        assertion: at ? { file: at[1], line: Number(at[2]), snippet: 'assertion failed' } : undefined,
        evidence: stderr,
        hint: at ? `adjust implementation so ${at[1]}:${at[2]} assertion passes` : 'adjust implementation to pass failing test',
      };
    }
    return { errorType: 'other', failedTests, evidence: stderr, hint: 'inspect jest output' };
  }
}
