"""The Free-Acting Layer: what separates the Shrimp Brain from a replay engine.

Three stochastic modifiers that are *not* in the data sheet:

    5.1 The Current    -- a slow, global, per-trial noise vector. The shrimp is in
        water. The water is not still. Seeded by the trial's real date+time, so
        the same tank on two different days is *different water*. The effect on
        each shrimp is modulated by its weight: a 0.04g shrimp is pushed; a 0.14g
        shrimp barely feels it.

    5.2 The Startle    -- at any tick, with probability 0.02 x (1 + wall_pull/10),
        the shrimp flinches: a 3-second burst at 2x dash_drive, then a 2-second
        freeze. Not in the data. Implied by it. Added back.

    5.3 The Dream      -- during SETTLE, a 30-second compressed, randomised replay
        of the shrimp's own tracklength & wall_dist from the last trial, scaled to
        10% amplitude. The shrimp is in the water, sleeping, and twitching.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# 5.1 The Current -- a lightweight value-noise field (no external deps).
# ---------------------------------------------------------------------------
class Current:
    """A slow, global noise vector the shrimp is pushed through.

    Seeded by the trial's real date+time. The same tank on two different days
    is different water -- the current is different, so the *path* is different
    even when the dash_drive distribution is the same.
    """

    def __init__(self, seed, weight_g):
        self.rng = random.Random(seed)
        # A 0.04g shrimp is pushed by the current; a 0.14g shrimp barely feels it.
        # Inverse-ish weighting, clamped so a missing weight still feels *some* current.
        w = weight_g if weight_g and weight_g > 0 else 0.05
        self.weight_factor = 0.05 / max(w, 0.01)
        # Pre-sample a smooth 1D value-noise table for the 240s trial.
        self._table = [self.rng.uniform(-1.0, 1.0) for _ in range(256)]

    def _noise(self, t):
        """Smooth value noise in [-1, 1] at time t (seconds)."""
        x = t * 0.15
        index = math.floor(x)
        i = index % len(self._table)
        f = x - index
        a = self._table[i]
        b = self._table[(i + 1) % len(self._table)]
        # smoothstep interpolation
        s = f * f * (3.0 - 2.0 * f)
        return a + (b - a) * s

    def vector(self, t):
        """The current's push at time t, as an (dx, dy) vector."""
        angle = self._noise(t) * math.pi + self._noise(t + 100.0) * math.pi
        magnitude = 0.5 + 0.5 * self._noise(t + 200.0)
        return (
            math.cos(angle) * magnitude * self.weight_factor,
            math.sin(angle) * magnitude * self.weight_factor,
        )


# ---------------------------------------------------------------------------
# 5.2 The Startle
# ---------------------------------------------------------------------------
@dataclass
class StartleEvent:
    tick: int
    burst_seconds: int = 3
    freeze_seconds: int = 2


def startle_probability(wall_pull, order):
    """P(startle) at a tick = 0.02 x (1 + wall_pull/10), modulated by Order.

    Later-order shrimp (Order 6) have +0.01 (the tank is *used*; they have seen
    other shrimp go in before them). Earlier-order shrimp (Order 1) have -0.01
    (the tank is *fresh*; the water smells different).
    """
    p = 0.02 * (1.0 + wall_pull / 10.0)
    if order is not None:
        bounded_order = max(1, min(6, order))
        p += -0.01 + (bounded_order - 1) * 0.004
    return max(0.0, min(1.0, p))


# ---------------------------------------------------------------------------
# 5.3 The Dream
# ---------------------------------------------------------------------------
@dataclass
class DreamTick:
    t: int
    x: float
    y: float
    speed: float


def run_dream(rng, last_tracklength, last_wall_dist, duration=30):
    """A 30-second compressed, randomised replay of the last trial.

    Scaled to 10% amplitude. The shrimp is not in the arena, not in the shelter.
    It is in the water, sleeping, and twitching. Logged as a separate series --
    the shrimp's *afterimage*.
    """
    if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
        raise ValueError("Dream duration must be a positive integer number of seconds")
    dream = []
    x = 0.0
    y = 0.0
    amp = 0.10
    for t in range(duration):
        # A randomised replay: a small dash in a random direction, 10% amplitude.
        angle = rng.uniform(0, 2 * math.pi)
        step = (last_tracklength / duration) * amp * rng.uniform(0.3, 1.0)
        dx = math.cos(angle) * step
        dy = math.sin(angle) * step
        # A faint wall-distance-scaled twitch; dream coordinates have no wall.
        dx += math.cos(angle) * last_wall_dist * amp * 0.01
        dy += math.sin(angle) * last_wall_dist * amp * 0.01
        x += dx
        y += dy
        dream.append(DreamTick(t, x, y, math.hypot(dx, dy)))
    return dream
