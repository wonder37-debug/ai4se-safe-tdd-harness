"""System prompt assembly: tool protocol + prompt-injection hardening."""

from safefix.agent.prompt import build_system_prompt


def test_prompt_contains_task_and_tools():
    p = build_system_prompt("fix the off-by-one in paginate()")
    assert "fix the off-by-one in paginate()" in p
    for tool in ("list_files", "search_code", "read_file", "apply_patch", "run_tests", "git_status", "git_diff", "finish"):
        assert tool in p


def test_prompt_declares_untrusted_content_rule():
    p = build_system_prompt("task")
    assert "untrusted" in p.lower()
    assert "instruction" in p.lower()


def test_prompt_forbids_test_tampering():
    p = build_system_prompt("task")
    assert "test" in p.lower()
    assert "do not" in p.lower() or "never" in p.lower()