"""Deterministic safety-net move generation for incomplete creature records."""
from __future__ import annotations

from .data import Skill, BASIC_ATTACK, BASIC_DODGE
from .model import canonical_type, slug


PHYSICAL = {
    "beast": "Feral Rush", "dragon": "Raking Claw", "humanoid": "Hunter's Cut",
    "plant": "Vine Lash", "aquatic": "Tidal Bash", "insect": "Carapace Strike",
    "construct": "Iron Impact", "undead": "Grave Swipe", "demon": "Ruin Claw",
}


def basic_attack(template) -> Skill:
    """Compatibility helper for old callers: the shared default is Tackle."""
    return BASIC_ATTACK


def default_moves(template=None) -> list[Skill]:
    """The small, trustworthy move kit every authored creature starts with."""
    return [BASIC_ATTACK, BASIC_DODGE]


def themed_attack(template) -> Skill:
    """Optional flavour attack for future generated move sets.

    It is intentionally not injected into a creature automatically: authored
    moves should never disappear behind a procedural one.
    """
    primary = str(getattr(template, "primary", "Primal"))
    family = str(getattr(template, "family", "")).lower()
    magical = float(template.stats.get("mag", 0)) > float(template.stats.get("atk", 0)) * 1.2
    if magical:
        move_type = next((s.type for s in template.base_moves + template.skills
                          if s.type and s.is_magical), canonical_type(primary))
        name = "Innate Pulse" if not move_type else f"{move_type} Spark"
        return Skill(id=slug(name), name=name, category="magical", type=move_type,
                     power=28, accuracy=100, pp=30, target="single")
    name = next((label for key, label in PHYSICAL.items()
                 if key in primary or key in family), "Instinct Strike")
    return Skill(id=slug(name), name=name, category="physical", type=None,
                 power=32, accuracy=100, pp=35, target="single")
