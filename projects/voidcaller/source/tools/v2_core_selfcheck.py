#!/usr/bin/env python3
"""Focused acceptance checks for VOIDCALLER's V2 load-bearing systems.

Run with:

    .venv/bin/python3 tools/v2_core_selfcheck.py

This uses only in-memory fixtures. It never changes project content or saves.
The larger systems from the master brief (breeding, Hunt bundles, provenance
summoning, equipment refinement, Ironman) intentionally have their own future
acceptance suites.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import elements as EL
from engine import formula as F
from engine import rules
from engine.battle import Battle
from engine.data import Bestiary, MonsterTemplate, Skill
from engine.entities import spawn, xp_for_level
from engine.model import CORE_STATS, RARITY_MARKS
from engine.state import Game
from tools import validate_content as V


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"PASS  {label}")
        return
    raise AssertionError(label)


def move(ident: str, name: str, *, category: str = "physical",
         combat_type: str | None = None, power: int = 42, pp: int = 20,
         priority: int = 0, effects: list | None = None) -> dict:
    return {
        "id": ident, "name": name, "category": category, "type": combat_type,
        "power": power, "accuracy": 100, "pp": pp,
        "target": "self" if category == "support" else "single",
        "priority": priority, "crit": 0, "effects": effects or [],
        "tags": ["basic"] if category == "support" else ["melee"],
        "description": "A test technique.",
    }


def species(ident: str, name: str, primary: str, *, secondary: str | None = None,
            role: str = "Bruiser", capture_rate: float = 0.35,
            stats: dict | None = None) -> dict:
    # Exact Common budget: 210.
    stats = stats or {"hp": 36, "atk": 54, "def": 28, "mag": 28, "res": 28, "spd": 36}
    return {
        "id": ident,
        "name": name,
        "title": "Acceptance fixture",
        "level": 8,
        "rarity": "Common",
        "role": role,
        "types": {"primary": primary, "secondary": secondary},
        "family": "Fixture",
        "size": "Medium",
        "sex_mode": "none",
        "capture_rate": capture_rate,
        "habitat": ["fixture_marsh"],
        "encounter": {"is_boss": False},
        "base_stats": stats,
        "base_moves": [
            move("fixture_jab", "Fixture Jab", combat_type=primary, power=42, pp=12),
            move("fixture_guard", "Fixture Guard", category="support", power=0, pp=15,
                 priority=1,
                 effects=[{"kind": "stat", "stat": "def", "amount": 0.25,
                           "rounds": 2, "target": "self"}]),
        ],
        "moves": [move("fixture_dash", "Fixture Dash", combat_type=primary, power=50, pp=10)],
        "learnset": [],
        "skill_tree": {
            "branches": [
                {"id": "body", "name": "Body", "nodes": [
                    {"id": "body_hardy", "name": "Hardy", "max_rank": 2,
                     "cost_per_rank": 1, "prerequisites": [],
                     "effects_per_rank": [{"kind": "stat_pct", "stat": "hp", "amount": 0.05}],
                     "description": "+5% HP per rank."},
                ]},
                {"id": "instinct", "name": "Instinct", "nodes": [
                    {"id": "instinct_quick", "name": "Quick", "max_rank": 1,
                     "cost_per_rank": 1,
                     "prerequisites": [{"node": "body_hardy", "rank": 2}],
                     "effects_per_rank": [{"kind": "stat_pct", "stat": "spd", "amount": 0.05}],
                     "description": "+5% SPD after Hardy II."},
                ]},
                {"id": "craft", "name": "Craft", "nodes": [
                    {"id": "craft_force", "name": "Force", "max_rank": 1,
                     "cost_per_rank": 1, "prerequisites": [],
                     "effects_per_rank": [{"kind": "stat_pct", "stat": "atk", "amount": 0.05}],
                     "description": "+5% ATK."},
                ]},
            ]
        },
        "drops": [{"item": "Fixture Scrap", "rate": 0.5, "kind": "material"}],
        "appearance": "A compact test silhouette.",
        "lore": "Only exists for the V2 self-check.",
    }


def validate_species(raw: dict) -> MonsterTemplate:
    report = V.Report()
    V.check_monster(raw, report)
    check("canonical species validates with no errors", not report.errors)
    template = MonsterTemplate.from_raw(raw)
    check("template preserves the six core stats", set(template.base_stats) == set(CORE_STATS))
    check("template has no V2 structural issue", not template.validation_issues())
    check("rarity uses the exact V2 mark", RARITY_MARKS[template.rarity] == "○")
    return template


def test_level_and_tree(template: MonsterTemplate) -> None:
    level_one = spawn(template)
    level_twenty_five = spawn(template, 25)
    level_fifty = spawn(template, 50)
    check("owned creatures start at Level 1", level_one.level == 1)
    check("engine permits Level 25 and Level 50", level_twenty_five.level == 25 and level_fifty.level == 50)
    check("Level scaling grows actual combat stats", level_fifty.max_hp > level_one.max_hp and level_fifty.stat("atk") > level_one.stat("atk"))
    check("new creatures have exactly two usable fundamentals", [skill.id for skill in level_one.skills] == ["fixture_jab", "fixture_guard"])

    level_one.gain_xp(xp_for_level(4) - level_one.xp)
    check("XP raises a creature through multiple Levels", level_one.level == 4 and level_one.skill_points == 3)
    ok, _message = level_one.purchase_skill_node("body_hardy")
    check("a ranked skill node can be bought", ok and level_one.skill_tree_state["body_hardy"] == 1)
    blocked, _message = level_one.purchase_skill_node("instinct_quick")
    check("a prerequisite blocks its child node", not blocked)
    ok, _message = level_one.purchase_skill_node("body_hardy")
    check("a rank can be purchased again until its cap", ok and level_one.skill_tree_state["body_hardy"] == 2)
    ok, _message = level_one.purchase_skill_node("instinct_quick")
    check("a satisfied prerequisite unlocks its child", ok and level_one.skill_points == 0)
    denied, _message = level_one.purchase_skill_node("craft_force")
    check("Skill Points cannot be overspent", not denied)

    level_one.gain_xp(xp_for_level(50) - level_one.xp + 100_000)
    check("Level never exceeds 50", level_one.level == 50 and level_one.xp_to_next == 0)


def test_type_and_battle(player_template: MonsterTemplate, enemy_template: MonsterTemplate) -> None:
    player = spawn(player_template, 8)
    enemy = spawn(enemy_template, 8, enemy=True)
    dual_enemy = MonsterTemplate.from_raw(species("mon_dual", "Dual Fixture", "Fire", secondary="Earth"))
    dual = spawn(dual_enemy, 8, enemy=True)
    check("single-Type chart relation is applied", EL.multiplier("Water", enemy) == 1.5)
    check("dual-Type chart relation multiplies", EL.multiplier("Water", dual) == 2.25)

    priority_move = Skill.from_raw(move("priority", "Priority", priority=1))
    slow = spawn(player_template, 8)
    fast = spawn(enemy_template, 8, enemy=True)
    slow.template.stats["spd"] = 1
    fast.template.stats["spd"] = 200
    ordered = F.action_order([(slow, priority_move), (fast, Skill.from_raw(move("normal", "Normal")))], random.Random(4))
    check("priority resolves before Speed", ordered[0][0] is slow)

    battle = Battle([player], [enemy, spawn(enemy_template, 8, enemy=True)], title="V2 fixture")
    events = battle.start()
    check("battle keeps one active creature on each side", len(battle.enemies) == 1 and battle.waiting is player)
    before_pp = player.pp_left(player.skills[0])
    events += battle.act("skill", 0, enemy.uid)
    check("using a move spends PP", player.pp_left(player.skills[0]) == before_pp - 1)
    check("battle emits a concrete V2 turn", any(event["k"] == "turn_order" for event in events))

    attack_template = MonsterTemplate.from_raw(species(
        "mon_attack", "Attack Fixture", "Water",
        stats={"hp": 36, "atk": 80, "def": 28, "mag": 10, "res": 28, "spd": 28},
    ))
    magic_template = MonsterTemplate.from_raw(species(
        "mon_magic", "Magic Fixture", "Water",
        stats={"hp": 36, "atk": 10, "def": 28, "mag": 80, "res": 28, "spd": 28},
    ))
    high_attack = spawn(attack_template, 8)
    high_magic = spawn(magic_template, 8)
    target = spawn(enemy_template, 8, enemy=True)
    physical = Skill.from_raw(move("physical_test", "Physical Test", category="physical", power=55))
    magical = Skill.from_raw(move("magical_test", "Magical Test", category="magical", power=55))
    check("physical and magical damage use distinct stat pairs", F.base_damage(high_attack, target, physical) > F.base_damage(high_attack, target, magical) and F.base_damage(high_magic, target, magical) > F.base_damage(high_magic, target, physical))


def test_capture(player_template: MonsterTemplate, enemy_template: MonsterTemplate) -> None:
    game = Game(Bestiary([player_template, enemy_template]))
    player = game.add_monster(player_template, 8)
    assert player is not None
    enemy = spawn(enemy_template, 8, enemy=True)
    battle = Battle([player], [enemy])
    battle.start()
    full_health = battle.capture_chance()
    # Keep this below full health but away from the 95% capture cap so the
    # status multiplier remains observable.
    enemy.cur_hp = max(2, enemy.max_hp // 2)
    low_health = battle.capture_chance()
    enemy.add_status("sleep", 2)
    controlled = battle.capture_chance()
    check("lower enemy HP improves capture chance", low_health > full_health)
    check("supported status improves capture chance", controlled > low_health)

    original_happens = F.happens
    F.happens = lambda _percent, rng=None: True
    try:
        events = battle.capture(game)
    finally:
        F.happens = original_happens
    check("a successful capture adds the wild creature to the roster", battle.outcome == "capture" and len(game.roster) == 2 and any(event["k"] == "capture" and event["success"] for event in events))

    boss_raw = species("mon_boss", "Boss Fixture", "Fire")
    boss_raw["encounter"] = {"is_boss": True}
    boss = spawn(MonsterTemplate.from_raw(boss_raw), 8, enemy=True)
    boss_battle = Battle([spawn(player_template, 8)], [boss])
    boss_battle.start()
    check("bosses are explicitly uncapturable", boss_battle.capture_chance() == 0.0 and not boss_battle.options()["can_capture"])


def test_retired_fields_are_rejected(raw: dict) -> None:
    broken = deepcopy(raw)
    broken["base_stats"]["mp"] = 20
    report = V.Report()
    V.check_monster(broken, report)
    check("retired permanent stats are rejected from V2 records", any("retired permanent stats" in error for error in report.errors))


def main() -> int:
    water = validate_species(species("mon_water", "Water Fixture", "Water"))
    fire = validate_species(species("mon_fire", "Fire Fixture", "Fire"))
    test_level_and_tree(water)
    test_type_and_battle(water, fire)
    test_capture(water, fire)
    test_retired_fields_are_rejected(species("mon_retired", "Retired Fixture", "Water"))
    print("\nV2 core self-check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
