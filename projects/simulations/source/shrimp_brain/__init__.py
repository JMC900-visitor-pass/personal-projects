"""The Shrimp Brain.

A free-acting digital shrimp — a behavioural agent model built from the body of
a shrimp that has sat in an open-field arena, hugging a wall, waiting for food
it can't see, and then dashing to a shelter it half-remembers.

The data sheet is not a rulebook. It is a *genome of behaviour*. The Shrimp
Brain reads it the way a shrimp reads water: as a gradient, a pressure, a
direction of least resistance.

The shrimp is free. The shrimp is small. The shrimp is in the water.
"""

from .data import DataSheet, Shrimp, Trial, default_sheet_path
from .nervous_field import NervousField, sample_nervous_field
from .free_acting import Current, run_dream, startle_probability
from .engine import (
    ShrimpBrain,
    TrialResult,
    TrialSummary,
    TickLog,
    DASH,
    FREEZE,
    HIDE,
    WAIT,
    SETTLE,
)

__all__ = [
    "DataSheet",
    "Shrimp",
    "Trial",
    "default_sheet_path",
    "NervousField",
    "sample_nervous_field",
    "Current",
    "run_dream",
    "startle_probability",
    "ShrimpBrain",
    "TrialResult",
    "TrialSummary",
    "TickLog",
    "DASH",
    "FREEZE",
    "HIDE",
    "WAIT",
    "SETTLE",
]
