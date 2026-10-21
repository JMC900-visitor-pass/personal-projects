"""What little randomness is left, in one place.

There are no dice in this game any more. Damage is a formula, accuracy is a
percentage, and everything below is the small amount of chance that remains:
a coin weighted to a percentage, a weighted pick, and a number in a range.
"""
from __future__ import annotations

import random


def happens(percent: float) -> bool:
    """percent given 0-100."""
    return random.random() * 100.0 < percent


def between(low: int, high: int) -> int:
    return random.randint(low, high)


def pick_weighted(items, weights):
    total = sum(weights) or 1
    x = random.random() * total
    for item, w in zip(items, weights):
        x -= w
        if x <= 0:
            return item
    return items[-1]


def spread(value: float, band: float) -> float:
    """value, give or take band as a fraction: spread(100, 0.1) -> 90..110."""
    return value * (1.0 + random.uniform(-band, band))
