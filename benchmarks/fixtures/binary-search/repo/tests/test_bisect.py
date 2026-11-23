from searchkit.bisect import find_first


def test_present():
    assert find_first([1, 3, 5], 3) == 1


def test_absent_returns_minus_one():
    assert find_first([1, 3, 5], 4) == -1