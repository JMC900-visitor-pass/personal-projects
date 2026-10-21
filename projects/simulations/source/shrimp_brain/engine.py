"""A one-second, stochastic shrimp simulation informed by recorded history.

This is a behavioural sketch, not a fitted biological model. The sheet contains
trial summaries, so arena geometry, steering and state transitions are explicit
modelling choices. Simulated measurements are kept separate from source rows.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass

from .data import Shrimp, Trial
from .free_acting import Current, DreamTick, StartleEvent, run_dream, startle_probability
from .nervous_field import NervousField, sample_nervous_field

DASH = "DASH"
FREEZE = "FREEZE"
HIDE = "HIDE"
WAIT = "WAIT"
SETTLE = "SETTLE"
TRIAL_SECONDS = 240


@dataclass(frozen=True)
class TickLog:
    """State at the end of a one-second interval, indexed from zero.

    Positions and speed are synthetic, including when a source measurement is
    absent. ``speed`` is the actual distance travelled during this interval.
    """

    t: int
    x: float
    y: float
    speed: float
    state: str
    wall_dist: float
    in_arena: bool
    food_found: bool
    startle: bool


@dataclass(frozen=True)
class TrialSummary:
    """Synthetic metrics; a source NA remains None in the matching output.

    Freeze metrics and occupancy are seconds. Area is the percentage of a
    circular 40-by-40 sampling grid visited. These are model definitions; the
    source CSV alone does not establish the experiment's measurement protocol.
    A food latency of 240 also represents failure to reach food; use the
    result's food_found flag to distinguish a success in the final interval.
    """

    tracklength: float | None
    wall_dist: float | None
    area: float | None
    oft_tot_frz: float | None
    time_arena: float | None
    tl_arena: float | None
    frz_arena: float | None
    shelter_duration: float | None
    food_latency2: float | None


@dataclass
class TrialResult:
    trial: Trial
    field: NervousField
    ticks: list[TickLog]
    dream: list[DreamTick]
    summary: TrialSummary
    startles: list[StartleEvent]
    body: dict
    food_found: bool
    carry_hunger: float

    def as_dict(self):
        """Export both the original trial and clearly named simulated outputs."""
        return {
            "trial": asdict(self.trial),
            "body": self.body.copy(),
            "field": asdict(self.field),
            "ticks": [asdict(tick) for tick in self.ticks],
            "dream": [dict(asdict(tick), state=SETTLE) for tick in self.dream],
            "summary": asdict(self.summary),
            "startles": [asdict(event) for event in self.startles],
            "food_found": self.food_found,
            "carry_hunger": self.carry_hunger,
        }


class ShrimpBrain:
    """Run one shrimp's trials in chronological order.

    Each trial gets a reproducible behavioural random stream derived from the
    shrimp ID, recorded timestamp, trial type and optional user seed. The water
    current uses the recorded timestamp and body weight. Recorded past rows
    supply the nervous field; only unmet hunger carries over from simulations.
    """

    def __init__(self, shrimp: Shrimp, seed: int | None = None, arena_radius: float = 10.0):
        if not math.isfinite(arena_radius) or arena_radius <= 0:
            raise ValueError("arena_radius must be a finite positive number")
        self.shrimp = shrimp
        self.seed = seed
        self.arena_radius = arena_radius
        self.carry_hunger = 0.0
        self._last_key = None
        self._completed_rows = set()

    def run_all(self) -> list[TrialResult]:
        """Start a fresh simulation and run every recorded trial in order."""
        self.carry_hunger = 0.0
        self._last_key = None
        self._completed_rows.clear()
        return [self.run_trial(trial) for trial in self.shrimp.trials_sorted()]

    def run_trial(self, trial: Trial) -> TrialResult:
        """Simulate 240 seconds, then a separate 30-second SETTLE dream.

        Calling this on a fresh brain simulates just this trial, with recorded
        history but no simulated hunger. Use run_all() for cross-trial hunger.
        """
        if trial.id != self.shrimp.id or trial not in self.shrimp.trials:
            raise ValueError("trial must belong to this shrimp's recorded history")
        if not (trial.is_open_field or trial.is_shelter_food):
            raise ValueError(f"unsupported trial type: {trial.trial}")
        # Preserve distinct source rows, even with matching timestamps, while
        # preventing a trial from consuming hunger from its own previous run.
        source_index = next((i for i, source in enumerate(self.shrimp.trials) if source is trial), None)
        if source_index is None:
            source_index = self.shrimp.trials.index(trial)
        if source_index in self._completed_rows:
            raise ValueError("trial already simulated; use run_all() or a new ShrimpBrain to restart")
        key = (trial.timestamp, trial.order or 0)
        if self._last_key is not None and key < self._last_key:
            raise ValueError("run trials in chronological order, or use run_all() to restart")

        rng = random.Random(f"{self.seed}:{trial.id}:{trial.seed}:{trial.trial}:{trial.order}")
        field = sample_nervous_field(self.shrimp, trial, rng, carry_hunger=self.carry_hunger)
        current = Current(trial.seed, trial.weight_g)
        radius = self.arena_radius
        shelter = (radius * 0.8, 0.0)
        shelter_radius = radius * 0.15
        food_radius = radius * 0.12
        x, y = shelter if trial.is_shelter_food else (0.0, 0.0)
        heading = rng.uniform(0.0, math.tau)
        hidden = trial.is_shelter_food
        hide_cooldown = 0
        freeze_left = 0
        active_startle = None
        startles = []
        ticks = []
        food_found = False
        food_latency = float(TRIAL_SECONDS)

        for t in range(TRIAL_SECONDS):
            if active_startle is not None:
                end = active_startle.tick + active_startle.burst_seconds + active_startle.freeze_seconds
                if t >= end:
                    active_startle = None
            if active_startle is None and not hidden:
                if rng.random() < startle_probability(field.wall_pull, trial.order):
                    active_startle = StartleEvent(t)
                    startles.append(active_startle)
                    freeze_left = 0

            startled = active_startle is not None
            if startled:
                state = DASH if t < active_startle.tick + active_startle.burst_seconds else FREEZE
            elif hidden:
                # Larger shelter duration samples increase the expected stay.
                stay_length = max(2.0, field.shelter_gravity / 4.0)
                if t > 0 and rng.random() < 1.0 / stay_length:
                    hidden = False
                    hide_cooldown = t + 8
                    heading = math.atan2(-y, -x)
                    state = DASH
                else:
                    state = HIDE
            elif freeze_left > 0:
                state = FREEZE
                freeze_left -= 1
            elif rng.random() < min(0.8, field.freeze_threshold / TRIAL_SECONDS):
                state = FREEZE
                freeze_left = rng.randint(1, 4)
            elif rng.random() < 0.08:
                state = WAIT
            else:
                state = DASH

            hungry = trial.is_shelter_food and not food_found and t >= field.hunger_pulse
            if (trial.is_shelter_food and not hidden and not startled
                    and t >= hide_cooldown and not hungry
                    and math.hypot(x - shelter[0], y - shelter[1]) <= shelter_radius
                    and rng.random() < min(0.9, field.shelter_gravity / TRIAL_SECONDS)):
                hidden = True
                state = HIDE
                freeze_left = 0

            old_x, old_y = x, y
            if state == DASH:
                heading += rng.uniform(-0.8, 0.8)
                dx, dy = math.cos(heading), math.sin(heading)
                radial = math.hypot(x, y)
                if radial > 0:
                    # Historical wall distance is a preferred distance: a small
                    # sample means staying closer to the edge of the arena.
                    target_radius = max(0.0, radius - min(radius, field.wall_pull))
                    pull = (target_radius - radial) / radius
                    dx += x / radial * pull
                    dy += y / radial * pull
                if hungry:
                    distance = math.hypot(x, y)
                    if distance > 0:
                        dx -= 1.8 * x / distance
                        dy -= 1.8 * y / distance
                elif trial.is_shelter_food and t >= hide_cooldown:
                    sx, sy = shelter[0] - x, shelter[1] - y
                    distance = math.hypot(sx, sy)
                    if distance > 0:
                        attraction = min(1.5, field.shelter_gravity / TRIAL_SECONDS)
                        dx += attraction * sx / distance
                        dy += attraction * sy / distance
                direction = math.hypot(dx, dy)
                if direction > 0:
                    heading = math.atan2(dy, dx)
                    dx, dy = dx / direction, dy / direction
                # Both normal swimming and the burst use dash_drive as a
                # trial-scale distance, converted to distance per second.
                step = field.dash_drive / TRIAL_SECONDS * rng.uniform(0.5, 1.5)
                if startled:
                    step *= 2.0
                cx, cy = current.vector(t)
                x += dx * step + cx * 0.1
                y += dy * step + cy * 0.1
                distance = math.hypot(x, y)
                if distance > radius:
                    x *= radius / distance
                    y *= radius / distance
                    heading = math.atan2(-y, -x) + rng.uniform(-0.5, 0.5)

            # Detect passing over the pellet, not just landing on it. The
            # one-second interval gives food latency one-second resolution.
            if hungry and not hidden and self._segment_distance(old_x, old_y, x, y) <= food_radius:
                food_found = True
                food_latency = float(t + 1)
            ticks.append(TickLog(
                t=t, x=x, y=y, speed=math.hypot(x - old_x, y - old_y),
                state=state, wall_dist=max(0.0, radius - math.hypot(x, y)),
                in_arena=state != HIDE, food_found=food_found, startle=startled,
            ))

        summary = self._summarize(trial, ticks, food_latency)
        # This completed run is now the last trial replayed during SETTLE.
        dream = run_dream(rng, sum(t.speed for t in ticks),
                          sum(t.wall_dist for t in ticks) / len(ticks))
        self.carry_hunger = 1.0 if trial.is_shelter_food and not food_found else 0.0
        self._last_key = key
        self._completed_rows.add(source_index)
        return TrialResult(trial, field, ticks, dream, summary, startles,
                           self.shrimp.body_at(trial), food_found, self.carry_hunger)

    @staticmethod
    def _segment_distance(x0, y0, x1, y1):
        """Distance from the food at the origin to a movement segment."""
        dx, dy = x1 - x0, y1 - y0
        length_squared = dx * dx + dy * dy
        if length_squared == 0:
            return math.hypot(x0, y0)
        fraction = max(0.0, min(1.0, -(x0 * dx + y0 * dy) / length_squared))
        return math.hypot(x0 + fraction * dx, y0 + fraction * dy)

    def _summarize(self, trial, ticks, food_latency):
        arena_ticks = [tick for tick in ticks if tick.in_arena]
        # Sample the path at a fixed spatial resolution so faster trajectories
        # cover intervening cells as well as their end points.
        grid_size = 40
        cell_size = 2.0 * self.arena_radius / grid_size
        valid_cells = {
            (i, j) for i in range(grid_size) for j in range(grid_size)
            if math.hypot(i + 0.5 - grid_size / 2, j + 0.5 - grid_size / 2) <= grid_size / 2
        }
        visited = set()
        previous_x, previous_y = (self.arena_radius * 0.8, 0.0) if trial.is_shelter_food else (0.0, 0.0)
        for tick in ticks:
            steps = max(1, math.ceil(tick.speed / cell_size * 2))
            for sample in range(steps + 1):
                fraction = sample / steps
                px = previous_x + fraction * (tick.x - previous_x)
                py = previous_y + fraction * (tick.y - previous_y)
                cell = (min(grid_size - 1, max(0, int((px + self.arena_radius) / cell_size))),
                        min(grid_size - 1, max(0, int((py + self.arena_radius) / cell_size))))
                if tick.in_arena and cell in valid_cells:
                    visited.add(cell)
            previous_x, previous_y = tick.x, tick.y
        metrics = {
            "tracklength": sum(t.speed for t in ticks),
            "wall_dist": sum(t.wall_dist for t in ticks) / len(ticks),
            "area": 100.0 * len(visited) / len(valid_cells),
            "oft_tot_frz": float(sum(t.state == FREEZE for t in ticks)),
            "time_arena": float(len(arena_ticks)),
            "tl_arena": sum(t.speed for t in arena_ticks),
            "frz_arena": float(sum(t.state == FREEZE for t in arena_ticks)),
            "shelter_duration": float(sum(t.state == HIDE for t in ticks)),
            "food_latency2": food_latency,
        }
        return TrialSummary(**{
            name: value if getattr(trial, name) is not None else None
            for name, value in metrics.items()
        })
