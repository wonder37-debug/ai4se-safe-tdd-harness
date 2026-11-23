"""pytest output parser.

Classifies real pytest console output (``-q`` and default verbosity):
- ``FAILED path::test`` summary lines -> failed test ids;
- ``AssertionError`` / ``E assert`` -> assertion failure with ``file:line``;
- SyntaxError / IndentationError / ImportError / ModuleNotFoundError -> syntax class
  (a broken import prevents collection just like a syntax error);
- ``INTERNALERROR`` -> infrastructure (environment/plugin problem, not the patch).
"""

from __future__ import annotations

import re

from safefix.models import Feedback, FeedbackKind, SourceLocation

_FAILED_RE = re.compile(r"^FAILED\s+(\S+)", re.MULTILINE)
_ERROR_RE = re.compile(r"^ERROR\s+(\S+)", re.MULTILINE)
_ASSERT_LOC_RE = re.compile(r"(\S+\.py):(\d+): AssertionError")
_SYNTAX_RE = re.compile(r"SyntaxError|IndentationError|TabError|ImportError|ModuleNotFoundError")
_TRACEBACK_LOC_RE = re.compile(r'File "([^"]+)", line (\d+)')


class PytestParser:
    def parse(self, stdout: str, stderr: str) -> Feedback:
        text = stdout + "\n" + stderr
        failed = _FAILED_RE.findall(text)
        errors = _ERROR_RE.findall(text)

        if "INTERNALERROR" in text:
            return Feedback(
                kind=FeedbackKind.INFRASTRUCTURE,
                failed_tests=failed + errors,
                evidence=text,
                hint="pytest internal error; check the environment/plugins, not the patch",
            )

        if _SYNTAX_RE.search(text):
            loc = _TRACEBACK_LOC_RE.search(text)
            return Feedback(
                kind=FeedbackKind.SYNTAX,
                failed_tests=failed + errors,
                location=SourceLocation(file=loc.group(1), line=int(loc.group(2))) if loc else None,
                evidence=text,
                hint="fix the syntax/import error before re-running tests",
            )

        if failed or re.search(r"AssertionError|^E\s+assert", text, re.MULTILINE):
            loc = _ASSERT_LOC_RE.search(text)
            return Feedback(
                kind=FeedbackKind.ASSERTION,
                failed_tests=failed,
                location=SourceLocation(file=loc.group(1), line=int(loc.group(2)), snippet="assertion failed")
                if loc
                else None,
                evidence=text,
                hint=f"adjust implementation so {loc.group(1)}:{loc.group(2)} passes"
                if loc
                else "adjust implementation to pass the failing tests",
            )

        return Feedback(
            kind=FeedbackKind.UNEXPECTED,
            failed_tests=failed + errors,
            evidence=text,
            hint="inspect pytest output",
        )