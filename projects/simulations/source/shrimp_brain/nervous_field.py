"""The Nervous Field: the shrimp's thought at any instant.

A 5-vector gradient derived from the shrimp's own historical rows. Not computed
from a formula -- *sampled* from the shrimp's own distribution, with a small
random perturbation (+/-15%). This is the "free-acting" part: the shrimp is
guided by its own history but is not deterministic. N01 tends to hug the wall.
It might not.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .data import Shrimp, Trial

PERTURB = 0.15    # +/-15% free-acting perturbation on every sample


@dataclass
class NervousField:
    """The five sampled values that make the shrimp *lean*."""

    wall_pull: float            # from wall_dist history -- preferred distance to wall
    dash_drive: float           # from tracklength / tl_arena -- how far it wants to go
    freeze_threshold: float     # from OFT_tot_frz / frz_arena -- how easily it locks up
    shelter_gravity: float      # from shelter_duration -- how strong the pull to hide
    hunger_pulse: float         # from food_latency2 -- how long it waits for food

    # Free-acting modifiers carried alongside the field.
    sex_jitter: float = 0.0     # +/-0.3 wall_pull jitter from sex-uncertainty
    setup_bias: float = 0.0     # additive bias from Set-Up B

    def as_dict(self):
        return {
            "wall_pull": round(self.wall_pull, 3),
            "dash_drive": round(self.dash_drive, 3),
            "freeze_threshold": round(self.freeze_threshold, 3),
            "shelter_gravity": round(self.shelter_gravity, 3),
            "hunger_pulse": round(self.hunger_pulse, 3),
            "sex_jitter": round(self.sex_jitter, 3),
            "setup_bias": round(self.setup_bias, 3),
        }

    def __str__(self):
        return (
            f"  wall_pull         = {self.wall_pull:7.2f}    "
            f"(from wall_dist history)\n"
            f"  dash_drive        = {self.dash_drive:7.2f}    "
            f"(from tracklength history)\n"
            f"  freeze_threshold = {self.freeze_threshold:7.2f}    "
            f"(from OFT_tot_frz history)\n"
            f"  shelter_gravity   = {self.shelter_gravity:7.2f}    "
            f"(from shelter_duration history)\n"
            f"  hunger_pulse      = {self.hunger_pulse:7.2f}    "
            f"(from food_latency2 history)"
        )


def _sample(values, rng, default):
    """Draw one value from the shrimp's own distribution, +/-15% perturbed.

    If the shrimp has no history for this column, fall back to a heuristic
    default so the shrimp can still *be* -- it just has no memory of it.
    """
    if not values:
        base = default
    else:
        base = rng.choice(values)
    # +/-15% perturbation -- the free-acting layer.
    return base * (1.0 + rng.uniform(-PERTURB, PERTURB))


def sample_nervous_field(shrimp, trial, rng, carry_hunger=0.0):
    """Sample the nervous field for a trial from the shrimp's *past*.

    ``carry_hunger`` is the one cross-trial memory the Shrimp Brain allows:
    not of the data, but of *hunger*. A shrimp that never found food in the
    last trial carries a boosted dash_drive forward.
    """
    # wall_pull: from wall_dist history (OFT). Sex-uncertainty adds +/-0.3 jitter.
    wall_pull = _sample(shrimp.history_values("wall_dist", upto=trial), rng, default=3.0)
    sex_jitter = 0.0
    if trial.sex_uncertain:
        sex_jitter = rng.uniform(-0.3, 0.3)
        wall_pull += sex_jitter

    # dash_drive: from tracklength (OFT) and tl_arena (OFTSHELTFOOD) history.
    dash_drive = _sample(
        shrimp.history_values("tracklength", upto=trial)
        + shrimp.history_values("tl_arena", upto=trial),
        rng,
        default=500.0,
    )
    if carry_hunger > 0.0:
        dash_drive *= 1.10    # starvation carried forward: +10% dash_drive

    # freeze_threshold: from OFT_tot_frz and frz_arena history.
    freeze_threshold = _sample(
        shrimp.history_values("oft_tot_frz", upto=trial)
        + shrimp.history_values("frz_arena", upto=trial),
        rng,
        default=10.0,
    )

    # shelter_gravity: from shelter_duration history.
    shelter_gravity = _sample(
        shrimp.history_values("shelter_duration", upto=trial),
        rng,
        default=120.0,
    )

    # hunger_pulse: from food_latency2 history.
    hunger_pulse = _sample(
        shrimp.history_values("food_latency2", upto=trial),
        rng,
        default=60.0,
    )

    # Set-Up B: the "displacement" config. The shrimp does not know it is in B.
    # It just feels *slightly off* -- a small additive bias to wall_pull & freeze.
    setup_bias = 0.0
    if trial.set_up == "B":
        setup_bias = 0.5
        wall_pull += setup_bias
        freeze_threshold += setup_bias

    return NervousField(
        wall_pull=max(0.0, wall_pull),
        dash_drive=max(0.0, dash_drive),
        freeze_threshold=max(0.0, freeze_threshold),
        shelter_gravity=max(0.0, shelter_gravity),
        hunger_pulse=max(0.0, hunger_pulse),
        sex_jitter=sex_jitter,
        setup_bias=setup_bias,
    )
