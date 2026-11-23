"""Clamp a value into an inclusive range."""


def clamp(value, lo, hi):
    if value < lo:
        return hi
    if value > hi:
        return hi
    return value