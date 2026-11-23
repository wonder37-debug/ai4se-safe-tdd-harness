"""Independent evaluation tests — NOT visible to the agent during generation."""

import pytest

from numtools.clamp import clamp


def test_at_lower_bound():
    assert clamp(10, 10, 20) == 10


def test_at_upper_bound():
    assert clamp(20, 10, 20) == 20


def test_above_range_returns_hi():
    assert clamp(99, 10, 20) == 20


def test_equal_bounds():
    assert clamp(3, 7, 7) == 7


def test_invalid_range_raises_for_any_value():
    with pytest.raises(ValueError):
        clamp(100, 20, 10)


def test_negative_range():
    assert clamp(-50, -20, -10) == -20