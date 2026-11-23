"""Approval gateway parity tests (legacy approvalGateway.ts + abort-intent rule)."""

from safefix.models import Action, ApprovalDecision
from safefix.security.approval import (
    AutoApproveGateway,
    AutoDenyGateway,
    MockApprovalGateway,
    has_abort_intent,
)

ACT = Action(tool="run_shell", args={"command": "rm -rf /"})


async def test_mock_gateway_returns_queued_decisions_in_order():
    gw = MockApprovalGateway(
        [ApprovalDecision(decision="approve", reason="ok"), ApprovalDecision(decision="deny", reason="no")]
    )
    assert (await gw.request(ACT, ["r"])).decision == "approve"
    assert (await gw.request(ACT, ["r"])).decision == "deny"


async def test_mock_gateway_empty_queue_defaults_deny():
    gw = MockApprovalGateway([])
    dec = await gw.request(ACT, ["r"])
    assert dec.decision == "deny" and dec.reason == "mock queue empty"


async def test_auto_gateways():
    assert (await AutoApproveGateway().request(ACT, [])).decision == "approve"
    assert (await AutoDenyGateway().request(ACT, [])).decision == "deny"


def test_abort_intent_chinese_keywords():
    assert has_abort_intent("终止任务")
    assert has_abort_intent("停止")
    assert has_abort_intent("不要执行了")


def test_abort_intent_english_word_boundary():
    assert has_abort_intent("abort")
    assert has_abort_intent("please CANCEL this")
    assert has_abort_intent("Stop now")


def test_abort_intent_no_false_positive_on_derivatives():
    assert not has_abort_intent("the process stopped")
    assert not has_abort_intent("cancelled earlier")
    assert not has_abort_intent("nonstop effort")


def test_abort_intent_plain_denial_is_not_abort():
    assert not has_abort_intent("too risky, try another approach")
