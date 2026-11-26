from statskit.average import moving_average


def test_window_two():
    assert moving_average([1, 2, 3], 2) == [1.5, 2.5]


def test_window_one_is_identity():
    assert moving_average([4, 5], 1) == [4.0, 5.0]