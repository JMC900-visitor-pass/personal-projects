"""Pure combat odds for the V2 six-stat / PP-only ruleset."""
from __future__ import annotations

import random

from . import balance as B
from . import elements as EL
from .data import Skill
from .entities import Combatant


def _percent_modifier(creature: Combatant, key: str) -> float:
    return max(-0.75, min(0.75, creature.modifier(key)))


def accuracy(actor: Combatant, target: Combatant | None, skill: Skill) -> float:
    """Move-owned accuracy with only temporary accuracy/evasion effects."""
    if not skill.is_damage:
        return 100.0
    chance = float(skill.accuracy)
    chance *= 1.0 + _percent_modifier(actor, "accuracy")
    if target is not None:
        chance *= 1.0 - min(B.EVASION_CAP, max(-B.EVASION_CAP, _percent_modifier(target, "evasion")))
        if target.guarding:
            chance -= B.GUARD_ACCURACY_PENALTY
    if "blind" in actor.statuses:
        chance *= B.BLIND_ACCURACY_PENALTY
    return round(max(B.ACCURACY_FLOOR, min(B.ACCURACY_CEIL, chance)), 0)


def crit_chance(actor: Combatant, skill: Skill | None = None) -> float:
    """A global five-percent crit baseline, overridden by explicit move data."""
    base = B.BASE_CRIT
    if skill is not None and skill.crit > 0:
        base = skill.crit
    bonus = getattr(actor, "move_crit_bonus", lambda _skill: 0.0)(skill)
    return round(max(0.0, min(B.CRIT_CAP, base + bonus * 100.0)), 1)


def mitigation(attack: float, guard: float) -> float:
    """Retired helper kept for tools that still report a mitigation share."""
    return attack / max(1.0, attack + guard * B.GUARD_WEIGHT)


def stab(actor: Combatant, skill: Skill) -> float:
    """Same Type Attack Bonus: x1.5 when a move matches one of its user's Types."""
    move_type = getattr(skill, "type", None)
    if not move_type:
        return 1.0
    template = getattr(actor, "template", actor)
    own = (getattr(template, "primary", None), getattr(template, "secondary", None))
    return B.STAB_MULTIPLIER if move_type in [t for t in own if t] else 1.0


def base_damage(actor: Combatant, target: Combatant, skill: Skill) -> float:
    """Pokemon's damage formula, before Type, crit and the damage roll.

        floor( floor( floor(2 x level / 5 + 2) x power x ATK / DEF ) / 50 ) + 2

    Linear in ATK/DEF rather than quadratic in the attacker's stat, so a
    high-ATK species hits hard without erasing its target in one turn, and the
    level term lengthens fights as a team grows.
    """
    if not skill.is_damage:
        return 0.0
    attack = max(1.0, actor.power_stat(skill))
    guard = max(1.0, target.guard_stat(skill))
    level = max(1, int(getattr(actor, "level", 1) or 1))
    step = int(2.0 * level / B.DAMAGE_LEVEL_DIVISOR + B.DAMAGE_LEVEL_BONUS)
    raw = int(int(step * skill.power * attack / guard) / B.DAMAGE_DIVISOR) + B.DAMAGE_FLAT
    raw *= stab(actor, skill)
    raw *= 1.0 + getattr(actor, "move_damage_bonus", lambda _skill: 0.0)(skill)
    return max(float(B.MIN_DAMAGE), raw)


def expected_damage(actor: Combatant, target: Combatant, skill: Skill) -> int:
    if not skill.is_damage:
        return 0
    raw = base_damage(actor, target, skill)
    crit = crit_chance(actor, skill) / 100.0
    raw *= 1.0 + crit * (B.CRIT_MULT - 1.0)
    return max(0, int(round(raw * EL.multiplier(skill.type, target))))


def status_chance(base_chance: float, target: Combatant, key: str) -> float:
    factor = target.resist_factor(key)
    return round(max(0.0, min(100.0, base_chance * factor)), 0)


def flee_chance(party: list[Combatant], enemies: list[Combatant]) -> float:
    ours = max((creature.speed() for creature in party if creature.alive), default=1.0)
    theirs = max((creature.speed() for creature in enemies if creature.alive), default=1.0)
    chance = B.FLEE_BASE + (ours - theirs) / max(1.0, theirs) * B.FLEE_SPEED_WEIGHT
    return round(max(B.FLEE_FLOOR, min(B.FLEE_CEIL, chance)), 0)


def happens(percent: float, rng: random.Random | None = None) -> bool:
    source = rng or random
    return source.random() * 100.0 < percent


def variance(rng: random.Random | None = None) -> float:
    """Pokemon's damage roll: 85%–100% of the computed damage, never above."""
    source = rng or random
    return source.uniform(*B.DAMAGE_ROLL)


def action_order(actions: list[tuple[Combatant, Skill]], rng: random.Random | None = None) -> list[tuple[Combatant, Skill]]:
    """Priority → effective SPD → unbiased seeded tie-breaker.

    Sorting only by a random value after the two defined keys makes ties fair
    while retaining predictable behaviour in deterministic tests.
    """
    source = rng or random
    rolled = [(actor, skill, int(skill.priority), actor.speed(), source.random())
              for actor, skill in actions]
    rolled.sort(key=lambda row: (-row[2], -row[3], row[4]))
    return [(actor, skill) for actor, skill, _priority, _speed, _tie in rolled]


def turn_order(combatants: list[Combatant]) -> list[tuple[Combatant, float]]:
    """Compatibility helper for non-battle callers: effective SPD only."""
    return sorted(((creature, creature.speed()) for creature in combatants), key=lambda row: -row[1])
