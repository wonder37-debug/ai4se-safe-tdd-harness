"""Parse application/x-www-form-urlencoded query strings."""


def parse_query(query):
    """Return a dict mapping each key to a LIST of its values.

    Repeated keys must accumulate in order: "tag=x&tag=y" -> {"tag": ["x", "y"]}.
    A key without '=' yields an empty-string value: "a" -> {"a": [""]}.
    """
    result = {}
    for part in query.split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        result[key] = value
    return result