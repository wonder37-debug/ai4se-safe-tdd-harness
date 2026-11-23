"""Independent evaluation tests — NOT visible to the agent during generation."""

import pytest

from statskit.average import moving_average


def test_window_equals_length():
    assert moving_average([2, 4, 6], 3) == [4.0]


def test_longer_series():
    assert moving_average([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]


def test_window_larger_than_series_is_empty():
    assert moving_average([1], 3) == []


def test_empty_series():
    assert moving_average([], 2) == []


def test_invalid_window_raises():
    with pytest.raises(ValueError):
        moving_average([1, 2], 0)