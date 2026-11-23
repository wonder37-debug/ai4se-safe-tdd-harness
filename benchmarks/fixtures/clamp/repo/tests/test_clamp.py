import pytest

from numtools.clamp import clamp


def test_below_range_returns_lo():
    assert clamp(5, 10, 20) == 10


def test_inside_range_unchanged():
    assert clamp(15, 10, 20) == 15


def test_invalid_range_raises():
    with pytest.raises(ValueError):
        clamp(5, 20, 10)