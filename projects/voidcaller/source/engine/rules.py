"""Pure battle resolution for the canonical PP-only ruleset."""
from __future__ import annotations

import random

from . import balance as B
from . import elements as EL
from . import formula as F
from .data import BASIC_DODGE, BASIC_STRUGGLE, Skill
from .entities import Combatant


GUARD = BASIC_DODGE
DEBUFF_STATUSES = {"poison", "burn", "sleep", "silence", "blind", "slow",
                   "stone", "stun", "confuse", "bleed"}


def ev(kind: str, **data) -> dict:
    data["k"] = kind
    return data


def side(creature: Combatant) -> str:
    return "enemy" if creature.is_enemy else "party"


def brief(creature: Combatant) -> dict:
    return {"uid": creature.uid, "name": creature.name, "side": side(creature),
            "hp": creature.cur_hp, "max_hp": creature.max_hp}


def hit_chance(actor: Combatant, target: Combatant, skill: Skill) -> float:
    return F.accuracy(actor, target, skill)


def expected_damage(actor: Combatant, target: Combatant, skill: Skill) -> int:
    return F.expected_damage(actor, target, skill)


def move_options(actor: Combatant, foes: list[Combatant]) -> list[dict]:
    """Presentation-ready move rows. PP is the only resource shown or checked."""
    ref = next((foe for foe in foes if foe.alive), None)
    pool = list(actor.skills)
    if not any(actor.can_cast(move) and move.is_damage for move in pool):
        pool.append(BASIC_STRUGGLE)
    rows = []
    for index, move in enumerate(pool):
        rows.append({
            "index": index, "id": move.id, "name": move.name,
            "category": move.category, "kind": move.category,
            "type": move.type, "element": move.element,
            "target": move.target, "power": move.power, "accuracy": move.accuracy,
            "priority": move.priority, "crit": F.crit_chance(actor, move) if move.is_damage else None,
            "pp": move.pp, "pp_left": actor.pp_left(move), "usable": actor.can_cast(move),
            "effects": move.effects, "effect": move.description, "description": move.description,
            "tags": list(move.tags), "rating": move.rating, "friendly": move.is_friendly,
            "aims_at": "self" if move.target == "self" else "allies" if move.is_friendly else "enemies",
            "picks_one": move.target in ("single", "random") and move.target != "self",
            "hit": F.accuracy(actor, ref, move) if ref and move.is_damage else None,
            "damage": F.expected_damage(actor, ref, move) if ref else 0,
            "mult": EL.multiplier(move.type, ref) if ref else 1.0,
        })
    return rows


def resolve_hit(actor: Combatant, target: Combatant, skill: Skill) -> list[dict]:
    chance = F.accuracy(actor, target, skill)
    if not F.happens(chance):
        return [ev("miss", actor=actor.name, actor_uid=actor.uid, target=target.name,
                   target_uid=target.uid, chance=chance, type=skill.type, element=skill.element)]

    crit_chance = F.crit_chance(actor, skill)
    critical = F.happens(crit_chance)
    total = F.base_damage(actor, target, skill) * F.variance()
    if critical:
        total *= B.CRIT_MULT
    mult = EL.multiplier(skill.type, target)
    total *= mult
    if target.guarding:
        total *= B.GUARD_REDUCTION
    if "shield" in target.statuses:
        total *= B.SHIELD_REDUCTION
    total = max(B.MIN_DAMAGE, int(round(total))) if mult > 0 else 0
    if actor.is_enemy and getattr(target, "_voidcaller_active_battle", False):
        total = min(total, max(1, int(round(target.max_hp * B.PLAYER_HIT_CAP))))
    target.damage(total)
    target.statuses.pop("sleep", None)
    return [ev("hit", actor=actor.name, actor_uid=actor.uid, target=target.name,
               target_uid=target.uid, amount=total, chance=chance, crit=bool(critical),
               crit_chance=crit_chance, type=skill.type, element=skill.element, mult=mult,
               label=EL.label(mult), hp=target.cur_hp, max_hp=target.max_hp,
               guarded=target.guarding, shielded="shield" in target.statuses)]


def _effect_targets(effect, actor: Combatant, targets: list[Combatant], allies: list[Combatant]) -> list[Combatant]:
    requested = str(getattr(effect, "target", "") or "").casefold()
    if requested == "self":
        return [actor]
    if requested == "all_allies":
        return [creature for creature in allies if creature.alive]
    if requested == "single" and targets:
        return [targets[0]]
    return list(targets)


def apply_effects(actor: Combatant, targets: list[Combatant], skill: Skill,
                  damage_done: int, allies: list[Combatant]) -> list[dict]:
    out = []
    for effect in skill.effects:
        if effect.kind == "status":
            for target in _effect_targets(effect, actor, targets, allies):
                if not target.alive or (target is actor and effect.key in DEBUFF_STATUSES):
                    continue
                chance = F.status_chance(effect.chance, target, effect.key)
                if chance <= 0:
                    out.append(ev("status", target=target.name, target_uid=target.uid,
                                  status=effect.key, applied=False, reason="immune", chance=0.0))
                elif not F.happens(chance):
                    out.append(ev("status", target=target.name, target_uid=target.uid,
                                  status=effect.key, applied=False, reason="resisted", chance=chance))
                else:
                    applied = target.add_status(effect.key, effect.rounds)
                    out.append(ev("status", target=target.name, target_uid=target.uid,
                                  status=effect.key, applied=applied, rounds=effect.rounds,
                                  reason="control_conflict" if not applied else "", chance=chance))
        elif effect.kind == "stat":
            for target in _effect_targets(effect, actor, targets, allies):
                if target.alive:
                    target.add_mod(effect.key, effect.amount, effect.rounds)
                    out.append(ev("stat", target=target.name, target_uid=target.uid,
                                  stat=effect.key, amount=effect.amount, rounds=effect.rounds))
        elif effect.kind == "drain" and damage_done > 0:
            gained = actor.heal(int(round(damage_done * effect.amount)))
            if gained:
                out.append(ev("drain", actor=actor.name, actor_uid=actor.uid, amount=gained, hp=actor.cur_hp))
        elif effect.kind == "heal":
            healed_targets = _effect_targets(effect, actor, targets, allies)
            if not healed_targets or skill.is_friendly:
                healed_targets = [actor] if effect.target != "all_allies" else [a for a in allies if a.alive]
            for target in healed_targets:
                gained = target.heal(int(round(target.max_hp * effect.amount)))
                if gained:
                    out.append(ev("heal", target=target.name, target_uid=target.uid,
                                  amount=gained, hp=target.cur_hp, max_hp=target.max_hp))
        elif effect.kind == "cleanse":
            for target in _effect_targets(effect, actor, targets, allies) or [actor]:
                if effect.key == "all":
                    target.statuses.clear()
                else:
                    target.statuses.pop(effect.key, None)
                out.append(ev("cleanse", target=target.name, target_uid=target.uid, what=effect.key))
        elif effect.kind == "revive":
            downed = [ally for ally in allies if not ally.alive]
            if downed:
                target = downed[0]
                target.cur_hp = max(1, int(target.max_hp * (effect.amount or 0.5)))
                target._down_announced = False
                out.append(ev("revive", target=target.name, target_uid=target.uid, hp=target.cur_hp))
    return out


def pick_targets(skill: Skill, actor: Combatant, allies: list[Combatant], foes: list[Combatant],
                 chosen: Combatant | None = None) -> list[Combatant]:
    live_foes = [foe for foe in foes if foe.alive]
    live_allies = [ally for ally in allies if ally.alive]
    if skill.is_friendly:
        if skill.target == "self":
            return [actor]
        if skill.target in ("all_allies", "all_enemies"):
            return live_allies
        if chosen is not None and chosen.alive and chosen.is_enemy == actor.is_enemy:
            return [chosen]
        return [min(live_allies, key=lambda ally: ally.cur_hp / max(1, ally.max_hp))] if live_allies else [actor]
    if skill.target == "self":
        return [actor]
    if skill.target == "all_allies":
        return live_allies
    if skill.target == "all_enemies":
        return live_foes
    if skill.target == "random":
        return [random.choice(live_foes)] if live_foes else []
    if chosen is not None and chosen.alive:
        return [chosen]
    return [live_foes[0]] if live_foes else []


def take_turn(actor: Combatant, allies: list[Combatant], foes: list[Combatant],
              skill: Skill, chosen: Combatant | None = None) -> list[dict]:
    actor.spend_pp(skill)
    if skill.id == GUARD.id and skill.category == "support" and not skill.effects:
        actor.guarding = True
        return [ev("guard", actor=actor.name, actor_uid=actor.uid, skill=skill.name)]
    targets = pick_targets(skill, actor, allies, foes, chosen)
    if not targets:
        return []
    out = [ev("skill", actor=actor.name, actor_uid=actor.uid, skill=skill.name, skill_id=skill.id,
              type=skill.type, element=skill.element, category=skill.category, skill_kind=skill.category,
              pp=skill.pp, pp_left=actor.pp_left(skill), targets=[target.name for target in targets],
              target_uids=[target.uid for target in targets], note=skill.description if not skill.effects else "")]
    total = 0
    if skill.is_damage:
        for target in targets:
            hits = resolve_hit(actor, target, skill)
            out.extend(hits)
            total += sum(event.get("amount", 0) for event in hits if event["k"] == "hit")
    out.extend(apply_effects(actor, targets, skill, total, allies))
    for creature in [*targets, actor]:
        if not creature.alive and not getattr(creature, "_down_announced", False):
            creature._down_announced = True
            out.append(ev("faint", who=creature.name, uid=creature.uid, side=side(creature)))
    return out


def tick_statuses(creature: Combatant) -> list[dict]:
    out = []
    for key in ("poison", "burn", "bleed"):
        if key not in creature.statuses:
            continue
        percent = {"poison": B.POISON_PCT, "burn": B.BURN_PCT, "bleed": B.POISON_PCT}[key]
        amount = max(1, int(round(creature.max_hp * percent)))
        creature.damage(amount)
        out.append(ev("dot", who=creature.name, uid=creature.uid, status=key, amount=amount,
                      hp=creature.cur_hp, max_hp=creature.max_hp))
    if "regen" in creature.statuses:
        gained = creature.heal(int(round(creature.max_hp * B.REGEN_PCT)))
        if gained:
            out.append(ev("heal", target=creature.name, target_uid=creature.uid, amount=gained,
                          hp=creature.cur_hp, max_hp=creature.max_hp))
    for key in list(creature.statuses):
        creature.statuses[key].rounds -= 1
        if creature.statuses[key].rounds <= 0:
            creature.statuses.pop(key)
            out.append(ev("status_end", who=creature.name, uid=creature.uid, status=key))
    creature.tick_mods()
    if not creature.alive and not getattr(creature, "_down_announced", False):
        creature._down_announced = True
        out.append(ev("faint", who=creature.name, uid=creature.uid, side=side(creature)))
    return out


def skip_reason(creature: Combatant) -> str | None:
    return next((key for key in ("sleep", "stone", "stun") if key in creature.statuses), None)


def void_pressure(everyone: list[Combatant], round_number: int) -> list[dict]:
    if round_number < B.PRESSURE_START:
        return []
    step = round_number - B.PRESSURE_START + 1
    percent = B.PRESSURE_PCT * step
    out = [ev("pressure", round=round_number, pct=round(percent * 100))]
    for creature in everyone:
        if creature.alive:
            creature.damage(max(1, int(round(creature.max_hp * percent))))
            if not creature.alive and not getattr(creature, "_down_announced", False):
                creature._down_announced = True
                out.append(ev("faint", who=creature.name, uid=creature.uid, side=side(creature)))
    return out


def ai_choose(actor: Combatant, allies: list[Combatant], foes: list[Combatant]) -> tuple[Skill, Combatant | None]:
    """Rule-based intent scoring; generated moves provide no hidden weights."""
    options = actor.usable_skills()
    live_foes = [foe for foe in foes if foe.alive]
    live_allies = [ally for ally in allies if ally.alive]
    hurt = min(live_allies, key=lambda ally: ally.cur_hp / ally.max_hp, default=actor)
    scored = []
    for move in options:
        score = 0.0
        if move.is_damage and live_foes:
            score = 20.0 + max(F.expected_damage(actor, foe, move) for foe in live_foes)
        if any(effect.kind == "heal" for effect in move.effects):
            score = max(score, 40.0 if hurt.cur_hp / hurt.max_hp < 0.45 else 6.0)
        if move.category == "support":
            score = max(score, 5.0)
        score += random.random() * 0.05
        scored.append((score, move))
    _score, move = max(scored, key=lambda row: row[0])
    if move.is_friendly:
        return move, hurt
    if live_foes:
        target = max(live_foes, key=lambda foe: F.expected_damage(actor, foe, move) / max(1, foe.cur_hp))
        return move, target
    return move, None


def battle_rewards(enemies: list[Combatant]) -> dict:
    """Engine-owned XP and rewards; species records never invent XP values.

    Pokemon's yield shape: a fallen creature is worth its species' base yield
    times its own level, over seven.  Rarity picks the yield rather than
    multiplying a flat number, so a Level 50 Epic is worth roughly three times
    a Level 50 Common instead of one and a half.
    """
    xp = gold = 0
    loot = []
    for enemy in enemies:
        xp += B.xp_reward(enemy.level, enemy.rarity, boss=bool(enemy.template.is_boss))
        gold += int(enemy.template.rewards.get("gold", 10))
        for drop in enemy.template.drops:
            if F.happens(drop.rate * 100):
                loot.append(drop.item)
    shards = random.randint(*B.SHARDS_PER_FIGHT) + sum(6 for enemy in enemies if enemy.template.is_boss)
    return {"xp": xp, "gold": gold, "shards": shards, "loot": loot}
