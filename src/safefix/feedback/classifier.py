"""Feedback classifier — port of legacy ``feedbackClassifier.ts`` with upgrades.

Upgrades over the original:
- six error classes (pass / assertion / syntax / timeout / infrastructure / unexpected);
- timeout detected from the observation error, not guessed from output text;
- parser exceptions degrade to an ``unexpected`` feedback with the output tail,
  never crash the loop.
"""

from __future__ import annotations

from typing import Protocol

from safefix.models import Feedback, FeedbackKind, Observation


class Parser(Protocol):
    def parse(self, stdout: str, stderr: str) -> Feedback: ...


def _truncate(s: str, n: int = 2000) -> str:
    """Keep the tail: test runners print the decisive summary last."""
    return s[-n:] if len(s) > n else s


class FeedbackClassifier:
    def __init__(self, parser: Parser):
        self._parser = parser

    def parse(self, obs: Observation) -> Feedback:
        if obs.exit_code == 0:
            return Feedback(kind=FeedbackKind.PASS, hint="tests passed")
        if obs.error == "timeout":
            return Feedback(
                kind=FeedbackKind.TIMEOUT,
                evidence=_truncate(obs.stderr or obs.stdout),
                hint="test run timed out; narrow the test scope or fix the hang",
            )
        try:
            fb = self._parser.parse(obs.stdout, obs.stderr)
            fb.evidence = _truncate(fb.evidence or obs.stderr or obs.stdout)
            return fb
        except Exception:
            tail = "\n".join((obs.stderr or obs.stdout).splitlines()[-30:])
            return Feedback(
                kind=FeedbackKind.UNEXPECTED,
                evidence=_truncate(tail),
                hint="unrecognized failure; inspect evidence",
            )
