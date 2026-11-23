"""Independent evaluation tests — NOT visible to the agent during generation."""

from searchkit.bisect import find_first


def test_duplicates_return_first_index():
    assert find_first([1, 2, 2, 2, 3], 2) == 1


def test_first_element():
    assert find_first([1, 2, 3], 1) == 0


def test_last_element():
    assert find_first([1, 2, 3], 3) == 2


def test_empty_list():
    assert find_first([], 1) == -1


def test_absent_smaller_than_all():
    assert find_first([10, 20], 5) == -1


def test_absent_larger_than_all():
    assert find_first([10, 20], 99) == -1


def test_single_present():
    assert find_first([7], 7) == 0