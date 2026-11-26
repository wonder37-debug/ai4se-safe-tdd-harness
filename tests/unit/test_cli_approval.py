"""CLI approval gateway tests."""

from safefix.models import Action
from safefix.security.cli_approval import CliApprovalGateway

ACT = Action(tool="run_tests", args={"command": "rm -rf /"})


async def test_yes_approves():
    gw = CliApprovalGateway(ask=lambda _: "y", show=lambda _: None)
    assert (await gw.request(ACT, ["r"])).decision == "approve"


async def test_no_denies():
    gw = CliApprovalGateway(ask=lambda _: "n", show=lambda _: None)
    assert (await gw.request(ACT, ["r"])).decision == "deny"


async def test_empty_denies():
    gw = CliApprovalGateway(ask=lambda _: "", show=lambda _: None)
    assert (await gw.request(ACT, ["r"])).decision == "deny"


async def test_free_text_is_deny_with_feedback():
    gw = CliApprovalGateway(ask=lambda _: "stop, too dangerous", show=lambda _: None)
    dec = await gw.request(ACT, ["r"])
    assert dec.decision == "deny" and dec.reason == "stop, too dangerous"
