"""Jest output parser — port of legacy ``jestParser.ts`` (optional adapter for
external JS/TS target repositories; SafeFix core itself never requires Node)."""

from __future__ import annotations

import re

from safefix.models import Feedback, FeedbackKind, SourceLocation

_FAIL_BLOCK = re.compile(r"●\s+(.+)")
_AT_LINE = re.compile(r"at\s+(?:.*?\s)?\(?(.+?):(\d+):\d+\)?")


class JestParser:
    def parse(self, stdout: str, stderr: str) -> Feedback:
        failed = [m.strip() for m in _FAIL_BLOCK.findall(stderr)]
        at = _AT_LINE.search(stderr)
        location = SourceLocation(file=at.group(1), line=int(at.group(2))) if at else None

        if re.search(r"SyntaxError|Test suite failed to parse|Unexpected token", stderr, re.IGNORECASE):
            return Feedback(
                kind=FeedbackKind.SYNTAX,
                failed_tests=failed,
                location=location,
                evidence=stderr,
                hint=f"fix syntax at {location.file}:{location.line}" if location else "fix syntax error",
            )
        if failed or re.search(r"expect\(received\)\.toBe\(expected\)", stderr, re.IGNORECASE):
            return Feedback(
                kind=FeedbackKind.ASSERTION,
                failed_tests=failed,
                location=location,
                evidence=stderr,
                hint=f"adjust implementation so {location.file}:{location.line} assertion passes"
                if location
                else "adjust implementation to pass failing test",
            )
        return Feedback(
            kind=FeedbackKind.UNEXPECTED, failed_tests=failed, evidence=stderr, hint="inspect jest output"
        )
