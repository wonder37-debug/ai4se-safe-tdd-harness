from textutil.slugify import slugify


def test_basic_slug():
    assert slugify("Hello World") == "hello-world"


def test_padded_punctuation():
    assert slugify("  Hello, World!  ") == "hello-world"