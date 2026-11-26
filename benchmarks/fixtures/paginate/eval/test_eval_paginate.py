"""Independent evaluation tests — NOT visible to the agent during generation."""

from shop.paginate import paginate


def test_last_partial_page():
    assert paginate([1, 2, 3, 4, 5], 3, 2) == [5]


def test_page_beyond_range_is_empty():
    assert paginate([1, 2, 3], 9, 2) == []


def test_size_one():
    assert paginate(["a", "b", "c"], 2, 1) == ["b"]


def test_whole_list_single_page():
    assert paginate([1, 2], 1, 10) == [1, 2]


def test_empty_items():
    assert paginate([], 1, 3) == []