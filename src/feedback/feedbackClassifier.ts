import { Feedback, Observation } from '../types';

export interface Parser { parse(stdout: string, stderr: string): Feedback; }

function truncate(s: string, n = 2000): string { return s.length > n ? s.slice(-n) : s; }

export class FeedbackClassifier {
  constructor(private parser: Parser) {}
  parse(obs: Observation): Feedback {
    if (obs.exitCode === 0) {
      return { errorType: 'other', failedTests: [], evidence: '', hint: 'tests passed' };
    }
    try {
      const fb = this.parser.parse(obs.stdout ?? '', obs.stderr ?? '');
      fb.evidence = truncate(fb.evidence || obs.stderr || '');
      return fb;
    } catch {
      return {
        errorType: 'other',
        failedTests: [],
        evidence: truncate((obs.stderr ?? '').split('\n').slice(-30).join('\n')),
        hint: 'unrecognized failure; inspect evidence',
      };
    }
  }
}
