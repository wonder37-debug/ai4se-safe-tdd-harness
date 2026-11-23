from urlkit.parse import parse_query


def test_single_pair():
    assert parse_query("a=1") == {"a": ["1"]}


def test_repeated_keys_preserved():
    assert parse_query("tag=x&tag=y") == {"tag": ["x", "y"]}