"""Feedback classification: pytest parser, Jest parity, fallbacks, truncation."""

from safefix.feedback.classifier import FeedbackClassifier
from safefix.feedback.jest_parser import JestParser
from safefix.feedback.pytest_parser import PytestParser
from safefix.models import FeedbackKind, Observation

PYTEST_ASSERT = """F                                                                        [100%]
=================================== FAILURES ===================================
_________________________________ test_add __________________________________

    def test_add():
>       assert add(1, 2) == 4
E       assert 3 == 4

tests/test_math.py:4: AssertionError
=========================== short test summary info ============================
FAILED tests/test_math.py::test_add - assert 3 == 4
1 failed in 0.02s
"""

PYTEST_SYNTAX = """=========================== short test summary info ============================
ERROR tests/test_bad.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
E   SyntaxError: invalid syntax (test_bad.py, line 3)
"""

PYTEST_IMPORT = """E   ModuleNotFoundError: No module named 'missing_dep'
ERROR tests/test_app.py
"""

PYTEST_INTERNAL = """INTERNALERROR> Traceback (most recent call last):
INTERNALERROR>   File "x.py", line 1
"""

JEST_ASSERT = """FAIL src/add.test.js
  ● adds numbers

    expect(received).toBe(expected) // Object.is equality

    Expected: 4
    Received: 3

      at Object.<anonymous> (src/add.test.js:5:21)
"""

JEST_SYNTAX = """FAIL src/bad.test.js
  ● Test suite failed to parse

    SyntaxError: Unexpected token (3:1)

      at Parser.parse (src/bad.test.js:3:1)
"""


def obs(stdout="", stderr="", exit_code=1, error=None):
    return Observation(ok=exit_code == 0, stdout=stdout, stderr=stderr, exit_code=exit_code, error=error)


def test_exit_zero_is_pass():
    fb = FeedbackClassifier(PytestParser()).parse(obs(exit_code=0))
    assert fb.kind == FeedbackKind.PASS and fb.hint == "tests passed"


def test_pytest_assertion_classified_with_location():
    fb = FeedbackClassifier(PytestParser()).parse(obs(stdout=PYTEST_ASSERT))
    assert fb.kind == FeedbackKind.ASSERTION
    assert fb.failed_tests == ["tests/test_math.py::test_add"]
    assert fb.location is not None
    assert fb.location.file == "tests/test_math.py" and fb.location.line == 4


def test_pytest_syntax_error():
    fb = FeedbackClassifier(PytestParser()).parse(obs(stdout=PYTEST_SYNTAX))
    assert fb.kind == FeedbackKind.SYNTAX


def test_pytest_import_error_is_syntax_class():
    fb = FeedbackClassifier(PytestParser()).parse(obs(stdout=PYTEST_IMPORT))
    assert fb.kind == FeedbackKind.SYNTAX


def test_pytest_internalerror_is_infrastructure():
    fb = FeedbackClassifier(PytestParser()).parse(obs(stdout=PYTEST_INTERNAL))
    assert fb.kind == FeedbackKind.INFRASTRUCTURE


def test_timeout_from_observation_error():
    fb = FeedbackClassifier(PytestParser()).parse(obs(error="timeout", exit_code=-1))
    assert fb.kind == FeedbackKind.TIMEOUT


def test_unknown_output_falls_back_to_unexpected():
    fb = FeedbackClassifier(PytestParser()).parse(obs(stdout="make: *** [test] Error 2"))
    assert fb.kind == FeedbackKind.UNEXPECTED
    assert "make" in fb.evidence


def test_jest_assertion_parity():
    fb = FeedbackClassifier(JestParser()).parse(obs(stderr=JEST_ASSERT))
    assert fb.kind == FeedbackKind.ASSERTION
    assert fb.failed_tests == ["adds numbers"]
    assert fb.location.file == "src/add.test.js" and fb.location.line == 5


def test_jest_syntax_parity():
    fb = FeedbackClassifier(JestParser()).parse(obs(stderr=JEST_SYNTAX))
    assert fb.kind == FeedbackKind.SYNTAX
    assert fb.failed_tests == ["Test suite failed to parse"]


def test_parser_exception_falls_back():
    class Broken:
        def parse(self, stdout, stderr):
            raise RuntimeError("boom")

    fb = FeedbackClassifier(Broken()).parse(obs(stderr="line1\nline2"))
    assert fb.kind == FeedbackKind.UNEXPECTED
    assert "line2" in fb.evidence


def test_evidence_truncated_to_tail():
    long = "x" * 5000
    fb = FeedbackClassifier(PytestParser()).parse(obs(stdout=long))
    assert len(fb.evidence) <= 2000