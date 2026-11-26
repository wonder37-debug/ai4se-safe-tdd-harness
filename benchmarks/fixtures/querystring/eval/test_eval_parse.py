"""Independent evaluation tests — NOT visible to the agent during generation."""

from urlkit.parse import parse_query


def test_empty_query():
    assert parse_query("") == {}


def test_key_without_equals():
    assert parse_query("flag") == {"flag": [""]}


def test_empty_value():
    assert parse_query("a=") == {"a": [""]}


def test_three_repeats_order():
    assert parse_query("k=1&k=2&k=3") == {"k": ["1", "2", "3"]}


def test_empty_parts_ignored():
    assert parse_query("a=1&&b=2&") == {"a": ["1"], "b": ["2"]}


def test_mixed_keys():
    assert parse_query("x=1&y=2&x=3") == {"x": ["1", "3"], "y": ["2"]}


def test_value_with_equals_sign():
    assert parse_query("eq=a=b") == {"eq": ["a=b"]}