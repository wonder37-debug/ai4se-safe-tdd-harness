"""Simple moving average over a fixed window."""


def moving_average(values, window):
    if window <= 0:
        raise ValueError("window must be positive")
    out = []
    for i in range(len(values) - window):
        out.append(sum(values[i : i + window]) / window)
    return out