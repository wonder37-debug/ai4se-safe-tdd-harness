from shop.paginate import paginate


def test_first_page():
    assert paginate([1, 2, 3, 4, 5], 1, 2) == [1, 2]


def test_second_page():
    assert paginate([1, 2, 3, 4, 5], 2, 2) == [3, 4]