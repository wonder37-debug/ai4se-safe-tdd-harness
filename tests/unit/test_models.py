"""Core domain model validation (Pydantic)."""

import pytest
from pydantic import ValidationError

from safefix.models import (
    Action,
    ApprovalDecision,
    Feedback,
    FeedbackKind,
    Message,
    Observation,
    TokenUsage,
)


def test_message_rejects_unknown_role():
    with pytest.raises(ValidationError):
        Message(role="tool", content="x")


def test_message_observation_role_allowed():
    m = Message(role="observation", content="obs")
    assert m.role == "observation"


def test_action_requires_args_dict():
    with pytest.raises(ValidationError):
        Action(tool="finish", args="nope")


def test_observation_defaults():
    obs = Observation(ok=True)
    assert obs.stdout == "" and obs.stderr == ""
    assert obs.exit_code is None and obs.error is None


def test_feedback_kind_covers_six_classes():
    assert {k.value for k in FeedbackKind} == {
        "pass",
        "assertion",
        "syntax",
        "timeout",
        "infrastructure",
        "unexpected",
    }


def test_feedback_defaults():
    fb = Feedback(kind=FeedbackKind.PASS, hint="tests passed")
    assert fb.failed_tests == [] and fb.evidence == "" and fb.location is None


def test_approval_decision_rejects_unknown_value():
    with pytest.raises(ValidationError):
        ApprovalDecision(decision="maybe", reason="")


def test_token_usage_total():
    u = TokenUsage(prompt_tokens=10, completion_tokens=5)
    assert u.total_tokens == 15
