"""Behavioral parity tests for the fenced action protocol (TS actionProtocol.ts)."""

from safefix.agent.protocol import parse_actions, strip_action_fences
from safefix.models import Action


def test_parses_single_action_block():
    text = 'sure\n```action\n{"tool": "read_file", "args": {"path": "a.py"}}\n```\n'
    acts = parse_actions(text)
    assert acts == [Action(tool="read_file", args={"path": "a.py"})]


def test_parses_multiple_blocks_in_order():
    text = (
        '```action\n{"tool": "list_files", "args": {"path": "."}}\n```\n'
        '```action\n{"tool": "finish", "args": {}}\n```'
    )
    acts = parse_actions(text)
    assert [a.tool for a in acts] == ["list_files", "finish"]


def test_tolerates_unclosed_fence():
    text = '```action\n{"tool": "finish", "args": {}}'
    assert parse_actions(text) == [Action(tool="finish", args={})]


def test_skips_malformed_json_block():
    text = '```action\n{not json}\n```\n```action\n{"tool": "finish", "args": {}}\n```'
    assert parse_actions(text) == [Action(tool="finish", args={})]


def test_rejects_unknown_tool_name():
    text = '```action\n{"tool": "drop_database", "args": {}}\n```'
    assert parse_actions(text) == []


def test_requires_args_object():
    text = '```action\n{"tool": "finish", "args": "nope"}\n```'
    assert parse_actions(text) == []


def test_requires_tool_string():
    text = '```action\n{"tool": 42, "args": {}}\n```'
    assert parse_actions(text) == []


def test_empty_text_yields_no_actions():
    assert parse_actions("") == []
    assert parse_actions("just natural language") == []


def test_strip_removes_fences_keeps_thought():
    text = 'I will inspect the file.\n```action\n{"tool": "finish", "args": {}}\n```\nDone thinking.'
    assert strip_action_fences(text) == "I will inspect the file.\n\nDone thinking."


def test_strip_handles_unclosed_fence():
    text = 'thinking\n```action\n{"tool": "finish", "args": {}}'
    assert strip_action_fences(text) == "thinking"


def test_strip_pure_fence_yields_empty():
    assert strip_action_fences('```action\n{"tool": "finish", "args": {}}\n```') == ""
