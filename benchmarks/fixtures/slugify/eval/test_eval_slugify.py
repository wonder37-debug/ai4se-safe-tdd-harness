"""Independent evaluation tests — NOT visible to the agent during generation."""

from textutil.slugify import slugify


def test_leading_symbols():
    assert slugify("!!!lead") == "lead"


def test_trailing_symbols():
    assert slugify("trail???") == "trail"


def test_only_symbols_is_empty():
    assert slugify("!!! ???") == ""


def test_multiple_separators_collapse():
    assert slugify("a   b___c") == "a-b-c"


def test_digits_preserved():
    assert slugify("Version 2 Release") == "version-2-release"


def test_empty_input():
    assert slugify("") == ""