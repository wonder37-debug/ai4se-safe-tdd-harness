"""1-based pagination helper."""


def paginate(items, page, size):
    """Return the ``page``-th (1-based) slice of ``items`` with ``size`` per page."""
    start = page * size
    return items[start : start + size]