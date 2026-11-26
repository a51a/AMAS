"""Small, dependency-free statistics helpers."""
from __future__ import annotations

import math

Z95 = 1.959963984540054


def wilson_interval(successes: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion. None when n == 0."""
    if n <= 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lower = 0.0 if successes == 0 else max(0.0, centre - half)
    upper = 1.0 if successes == n else min(1.0, centre + half)
    return (lower, upper)


def newcombe_diff_interval(x1: int, n1: int, x2: int, n2: int, z: float = Z95) -> tuple[float, float] | None:
    """Newcombe (method 10) hybrid score CI for p1 - p2, built from Wilson intervals."""
    w1, w2 = wilson_interval(x1, n1, z), wilson_interval(x2, n2, z)
    if w1 is None or w2 is None:
        return None
    p1, p2 = x1 / n1, x2 / n2
    l1, u1 = w1
    l2, u2 = w2
    d = p1 - p2
    lower = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (max(-1.0, lower), min(1.0, upper))


def hamming_hex(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")
