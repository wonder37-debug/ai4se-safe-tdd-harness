"""Binary search: first index of target in a sorted list."""


def find_first(sorted_items, target):
    lo, hi = 0, len(sorted_items)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_items[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(sorted_items) else -1