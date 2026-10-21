#!/usr/bin/env python3
"""Check generated content before the game sees it.

    python3 tools/validate_content.py monsters.jsonl
    python3 tools/validate_content.py --kind quest new_quests.json

Structural errors stop a record loading. Warnings mean it loads but something
in it will be ignored or will play badly. No dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import effects as FX
from engine.data import Skill
from engine.model import (COMBAT_TYPES, CORE_STATS, RARITIES, RARITY_BST,
                          ROLES, STATUS_KEYS, canonical_type)

# Public names are intentionally kept for Forge's setup endpoint.
TYPES = list(COMBAT_TYPES)
SIZES = ["Tiny", "Small", "Medium", "Large", "Huge", "Gargantuan"]
SKILL_KINDS = ["physical", "magical", "support"]
TARGETS = ["single", "all_enemies", "all_allies", "self", "random"]
STATUSES = list(STATUS_KEYS)
RESIST_WORDS = ["weak", "normal", "resist", "immune"]
DROP_KINDS = ["material", "consumable", "equipment", "weapon", "armor", "accessory",
              "seed", "treasure", "key", "rare"]
QUEST_KINDS = ["fetch", "slay", "hunt"]


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")


def need(rep, where, obj, field, kind, choices=None, lo=None, hi=None):
    if field not in obj:
        rep.err(where, f"missing '{field}'")
        return None
    val = obj[field]
    if kind and not isinstance(val, kind):
        rep.err(where, f"'{field}' should be {getattr(kind, '__name__', kind)}, got {type(val).__name__}")
        return None
    if choices and val not in choices:
        rep.err(where, f"'{field}' is '{val}', expected one of {', '.join(map(str, choices))}")
    if lo is not None and isinstance(val, (int, float)) and val < lo:
        rep.err(where, f"'{field}' is {val}, minimum {lo}")
    if hi is not None and isinstance(val, (int, float)) and val > hi:
        rep.warn(where, f"'{field}' is {val}, unusually high (over {hi})")
    return val


def _legacy_monster(record: dict) -> bool:
    """Imported V1 content remains loadable, but the Forge authors V2 only."""
    return bool(record.get("element_affinity")) or (
        isinstance(record.get("type"), dict) and "types" not in record)


def _move_category(record: dict) -> str:
    return str(record.get("category") or
               (record.get("type") if record.get("type") in SKILL_KINDS else "") or "").casefold()


def _check_effects(where: str, effects, rep: Report, *, tree: bool = False) -> None:
    if effects is None:
        return
    if not isinstance(effects, list):
        rep.err(where, "effects must be a list of structured effect objects")
        return
    for index, effect in enumerate(effects):
        effect_where = f"{where} / effect {index + 1}"
        if not isinstance(effect, dict):
            rep.err(effect_where, "must be an object")
            continue
        kind = str(effect.get("kind") or "").casefold()
        allowed = {"status", "stat", "heal", "drain", "cleanse", "revive"}
        if tree:
            allowed |= {"stat_pct", "unlock_move", "move", "move_damage_pct",
                        "physical_damage_pct", "magical_damage_pct", "crit_bonus"}
        if kind not in allowed:
            rep.err(effect_where, "kind is not a supported structured effect")
            continue
        if kind == "status":
            key = str(effect.get("status") or effect.get("key") or "").casefold()
            if key not in STATUSES:
                rep.err(effect_where, f"unknown status '{key}'")
        if kind in {"stat", "stat_pct"}:
            stat = str(effect.get("stat") or effect.get("key") or "").casefold()
            if stat not in {*CORE_STATS, "accuracy", "evasion"}:
                rep.err(effect_where, f"stat '{stat}' is retired or unknown")
        if kind in {"heal", "drain", "revive", "stat_pct", "move_damage_pct",
                    "physical_damage_pct", "magical_damage_pct", "crit_bonus"} and not isinstance(effect.get("amount"), (int, float)):
            rep.err(effect_where, "needs a numeric amount")


def _check_move(record: dict, rep: Report, where: str, *, base: bool = False) -> Skill | None:
    if not isinstance(record, dict):
        rep.err(where, "must be an object or a Forge move-library reference")
        return None
    need(rep, where, record, "id", str)
    need(rep, where, record, "name", str)
    category = _move_category(record)
    if category not in SKILL_KINDS:
        rep.err(where, "category must be physical, magical, or support")
    raw_type = record.get("type") if "category" in record else record.get("element")
    if raw_type not in (None, "", "none", "None") and canonical_type(raw_type) is None:
        rep.err(where, f"Type '{raw_type}' is unknown; use one of {', '.join(TYPES)}")
    power = need(rep, where, record, "power", (int, float), lo=0, hi=180)
    pp = need(rep, where, record, "pp", int, lo=1, hi=99)
    need(rep, where, record, "target", str, choices=TARGETS)
    if "accuracy" in record:
        need(rep, where, record, "accuracy", (int, float), lo=30, hi=100)
    if "priority" in record:
        need(rep, where, record, "priority", int, lo=-7, hi=7)
    if "crit" in record:
        need(rep, where, record, "crit", (int, float), lo=0, hi=40)
    if "mp_cost" in record:
        rep.warn(where, "mp_cost is retired and ignored; use PP only")
    if "weight" in record:
        rep.warn(where, "weight is retired; battle AI evaluates moves by their real effect")
    _check_effects(where, record.get("effects"), rep)
    old_effect = str(record.get("effect") or "").strip()
    if old_effect and not FX.parse(old_effect):
        rep.warn(where, "legacy effect prose is flavour only; author structured effects instead")
    skill = Skill.from_raw(record)
    if category in ("physical", "magical") and not power:
        rep.err(where, "a damaging category needs power above 0")
    if category == "support" and power:
        rep.err(where, "support moves have power 0")
    if base and category == "support" and skill.target != "self":
        rep.err(where, "the defensive fundamental must target self")
    if base and category == "support" and not skill.effects and skill.id != "dodge":
        rep.err(where, "the defensive fundamental needs a structured defensive or buff effect")
    return skill


def _check_skill_tree(tree, rep: Report, where: str, *, required: bool = False) -> None:
    if tree in (None, {}, []):
        if required:
            rep.warn(where, "no skill tree authored yet — build paths are a core progression layer")
        return
    if isinstance(tree, list):
        rep.warn(where, "legacy linear skill tree preserved on import; Forge writes branches/nodes in V2")
        return
    if not isinstance(tree, dict):
        rep.err(where, "skill_tree must be an object with branches")
        return
    branches = tree.get("branches")
    if not isinstance(branches, list) or not branches:
        rep.err(where, "skill_tree.branches needs at least one branch")
        return
    if not 3 <= len(branches) <= 4:
        rep.warn(where, "a player-built tree is most readable with 3–4 branches")
    node_ids = set()
    prerequisites = []
    for branch_index, branch in enumerate(branches):
        branch_where = f"{where} / branch {branch_index + 1}"
        if not isinstance(branch, dict):
            rep.err(branch_where, "must be an object")
            continue
        need(rep, branch_where, branch, "id", str)
        need(rep, branch_where, branch, "name", str)
        nodes = branch.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            rep.err(branch_where, "needs nodes")
            continue
        for node_index, node in enumerate(nodes):
            node_where = f"{branch_where} / node {node_index + 1}"
            if not isinstance(node, dict):
                rep.err(node_where, "must be an object")
                continue
            ident = need(rep, node_where, node, "id", str)
            need(rep, node_where, node, "name", str)
            if isinstance(ident, str):
                if ident in node_ids:
                    rep.err(node_where, f"duplicate node id '{ident}'")
                node_ids.add(ident)
            need(rep, node_where, node, "max_rank", int, lo=1, hi=5)
            need(rep, node_where, node, "cost_per_rank", int, lo=1, hi=5)
            _check_effects(node_where, node.get("effects_per_rank"), rep, tree=True)
            prerequisites.extend(node.get("prerequisites") or [])
    for requirement in prerequisites:
        if isinstance(requirement, dict) and requirement.get("node") not in node_ids:
            rep.err(where, f"prerequisite references unknown node '{requirement.get('node')}'")


def check_monster(m: dict, rep: Report) -> None:
    where = m.get("name") or m.get("id") or "?"
    if _legacy_monster(m):
        rep.warn(where, "legacy V1 species: it will be imported with neutralised retired stats; re-author it in Forge for V2")
        need(rep, where, m, "id", str)
        need(rep, where, m, "name", str)
        return

    need(rep, where, m, "id", str)
    need(rep, where, m, "name", str)
    need(rep, where, m, "level", int, lo=1, hi=50)
    rarity = need(rep, where, m, "rarity", str, choices=RARITIES)
    role = need(rep, where, m, "role", str, choices=ROLES)
    types = m.get("types")
    if not isinstance(types, dict):
        rep.err(where, "missing 'types' object with primary and optional secondary")
    else:
        primary = types.get("primary")
        secondary = types.get("secondary")
        if canonical_type(primary) is None:
            rep.err(where, f"types.primary '{primary}' is not one of the twelve Types")
        if secondary not in (None, "", "none") and canonical_type(secondary) is None:
            rep.err(where, f"types.secondary '{secondary}' is not one of the twelve Types")
        if primary and secondary and canonical_type(primary) == canonical_type(secondary):
            rep.err(where, "types.secondary duplicates types.primary")
    if role and role not in ROLES:
        rep.err(where, "role must use the canonical role list")
    if m.get("family") is not None and not isinstance(m.get("family"), str):
        rep.err(where, "family must be a string and is separate from combat Types")
    if m.get("capture_rate") is not None:
        need(rep, where, m, "capture_rate", (int, float), lo=0, hi=1)

    stats = m.get("base_stats") or m.get("stats")
    if not isinstance(stats, dict):
        rep.err(where, "missing base_stats object")
    else:
        for key in CORE_STATS:
            need(rep, where, stats, key, (int, float), lo=1, hi=200)
        retired = sorted(set(stats) & {"mp", "luk", "hit", "eva", "crit"})
        if retired:
            rep.err(where, "retired permanent stats present: " + ", ".join(retired))
        total = sum(stats.get(key, 0) for key in CORE_STATS if isinstance(stats.get(key), (int, float)))
        if rarity in RARITY_BST:
            low, high = RARITY_BST[rarity]
            if not low <= total <= high:
                rep.err(where, f"BST {total:g} is outside the {rarity} budget {low}–{high}")

    base_moves = m.get("base_moves")
    if not isinstance(base_moves, list) or len(base_moves) != 2:
        rep.err(where, "base_moves needs exactly two fundamentals: one melee and one defensive/support")
        base_moves = []
    parsed_base = [_check_move(row, rep, f"{where} / base move {index + 1}", base=True)
                   for index, row in enumerate(base_moves)]
    if parsed_base:
        if not any(move and move.category == "physical" and move.power > 0 for move in parsed_base):
            rep.err(where, "base_moves needs one physical melee fundamental")
        if not any(move and move.category == "support" and move.target == "self" for move in parsed_base):
            rep.err(where, "base_moves needs one self defensive/support fundamental")

    moves = m.get("moves", m.get("skills", []))
    if moves is not None and not isinstance(moves, list):
        rep.err(where, "moves must be a list")
    for index, move in enumerate(moves or []):
        if isinstance(move, str):
            continue
        _check_move(move, rep, f"{where} / move {index + 1}")
    learnset = m.get("learnset")
    if learnset is not None and not isinstance(learnset, list):
        rep.err(where, "learnset must be a list")
    _check_skill_tree(m.get("skill_tree"), rep, where, required=True)

    for drop in m.get("drops") or []:
        drop_where = f"{where} / drop {drop.get('item', '?')}" if isinstance(drop, dict) else where
        if not isinstance(drop, dict):
            rep.err(drop_where, "drop must be an object")
            continue
        need(rep, drop_where, drop, "item", str)
        rate = need(rep, drop_where, drop, "rate", (int, float), lo=0)
        if isinstance(rate, (int, float)) and rate > 1:
            rep.err(drop_where, "rate is a 0..1 fraction")
    if not m.get("drops"):
        rep.warn(where, "drops nothing, so this species cannot support a fetch contract")
    evo = m.get("evolution")
    if evo is not None and not isinstance(evo, dict):
        rep.err(where, "evolution must be an object")


def check_item(it: dict, rep: Report, name: str = "") -> None:
    where = name or it.get("name", "?")
    if "kind" in it and it["kind"] not in DROP_KINDS:
        rep.warn(where, f"kind '{it['kind']}' unknown, priced as a material")
    for field in ("value", "buy"):
        if field in it and not isinstance(it[field], (int, float)):
            rep.err(where, f"'{field}' must be a number")
    use = it.get("use")
    if use is not None:
        if not isinstance(use, dict):
            rep.err(where, "'use' must be an object")
        else:
            known = {"heal_pct", "pp_restore", "cleanse", "revive_pct", "flee", "buff"}
            for k in use:
                if k not in known:
                    if k == "mp_pct":
                        rep.warn(where, "use.mp_pct is retired and ignored; use pp_restore")
                    else:
                        rep.warn(where, f"use.{k} does nothing; known keys are {', '.join(sorted(known))}")
            for k in ("heal_pct", "revive_pct"):
                if k in use and not (0 < use[k] <= 1):
                    rep.err(where, f"use.{k} is a fraction between 0 and 1")
            if "pp_restore" in use and (not isinstance(use["pp_restore"], int) or use["pp_restore"] < 1):
                rep.err(where, "use.pp_restore is a positive integer")
    if "desc" not in it:
        rep.warn(where, "no desc, so the stall shows a blank line")
    _check_skill_tree(it.get("skill_tree"), rep, where)


def check_move(move: dict, rep: Report) -> None:
    where = move.get("name") or move.get("id") or "move"
    legacy = "category" not in move and move.get("type") in {"physical", "magical", "support", "status"}
    if legacy:
        rep.warn(where, "legacy V1 move: it loads through the compatibility reader; Forge writes category/type/effects in V2")
        # Its data reader still gives a useful warning for malformed legacy
        # fields, but it is not rejected merely for carrying retired MP.
        if not isinstance(move.get("name"), str):
            rep.err(where, "name must be a string")
        return
    _check_move(move, rep, where)


def check_starter(starter: dict, rep: Report) -> None:
    where = starter.get("label") or "starter choices"
    need(rep, where, starter, "label", str)
    ids = starter.get("monster_ids")
    if not isinstance(ids, list):
        rep.err(where, "needs exactly three monster ids")
        return
    if not ids:
        rep.warn(where, "no authored starter trio — new games use eligible creature fallback choices")
        return
    if len(ids) != 3:
        rep.err(where, "needs exactly three monster ids")
        return
    if not all(isinstance(ident, str) and ident.strip() for ident in ids):
        rep.err(where, "monster_ids must be non-empty strings")
    if len(set(ids)) != len(ids):
        rep.err(where, "the three starter ids must be different")


def check_quest(q: dict, rep: Report) -> None:
    where = q.get("title", "?")
    need(rep, where, q, "kind", str, choices=QUEST_KINDS)
    need(rep, where, q, "title", str)
    need(rep, where, q, "target", str)
    need(rep, where, q, "qty", int, lo=1, hi=20)
    need(rep, where, q, "gold", int, lo=0)
    area_id = q.get("area_id")
    if area_id is not None and (not isinstance(area_id, str) or not area_id.strip()):
        rep.err(where, "area_id must be a non-empty Void Area id when provided")
    elif not area_id:
        rep.warn(where, "no area_id — Forge missions should name their operation location")
    if not q.get("text"):
        rep.warn(where, "no text — the board reads flat without a line from the giver")
    if q.get("kind") == "slay" and not str(q.get("target", "")).startswith("family:"):
        rep.warn(where, "slay targets are usually 'family:Canine' so several species count")


def check_area(area: dict, rep: Report) -> None:
    where = area.get("name") or area.get("id") or "?"
    ident = need(rep, where, area, "id", str)
    if isinstance(ident, str) and not ident.replace("_", "").replace("-", "").isalnum():
        rep.err(where, "id uses only lower-case letters, numbers, _ and -")
    need(rep, where, area, "name", str)
    members = area.get("monster_ids")
    if not isinstance(members, list) or not members:
        rep.err(where, "needs at least one monster_id before it can appear in the Atlas")
    elif not all(isinstance(row, str) and row.strip() for row in members):
        rep.err(where, "monster_ids must be non-empty monster id strings")
    elif len(set(members)) != len(members):
        rep.warn(where, "has the same monster id more than once")
    bosses = area.get("boss_ids", [])
    if not isinstance(bosses, list) or not all(isinstance(row, str) for row in bosses):
        rep.err(where, "boss_ids must be a list of monster id strings")


def check_crop(crop: dict, rep: Report) -> None:
    where = crop.get("label") or crop.get("id") or "?"
    ident = need(rep, where, crop, "id", str)
    if isinstance(ident, str) and not ident.replace("_", "").replace("-", "").isalnum():
        rep.err(where, "id uses only lower-case letters, numbers, _ and -")
    for field in ("label", "seed", "item"):
        need(rep, where, crop, field, str)
    need(rep, where, crop, "cycle", int, lo=1)
    need(rep, where, crop, "yield", int, lo=1, hi=99)
    if crop.get("mark") is not None and (not isinstance(crop["mark"], str) or len(crop["mark"]) > 1):
        rep.err(where, "mark is one character")


def check_story(ch: dict, rep: Report) -> None:
    where = ch.get("title", "?")
    need(rep, where, ch, "id", int, lo=1)
    need(rep, where, ch, "title", str)
    need(rep, where, ch, "requires_level", int, lo=1)
    scenes = ch.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        rep.err(where, "needs scenes")
        return
    if not any("battle" in s for s in scenes):
        rep.warn(where, "no battle scene — the chapter is all text")
    for i, s in enumerate(scenes):
        if "text" not in s and "battle" not in s:
            rep.err(where, f"scene {i} has neither text nor battle")
        b = s.get("battle")
        if isinstance(b, dict) and not (b.get("monster") or b.get("fallback")):
            rep.warn(where, f"scene {i}: no monster and no fallback, so it picks at random")


def check_recipe(recipe: dict, rep: Report) -> None:
    where = recipe.get("name") or recipe.get("id") or "?"
    need(rep, where, recipe, "id", str)
    need(rep, where, recipe, "name", str)
    need(rep, where, recipe, "station", str,
         choices=["craft_shop", "farm_kitchen", "soul_forge"])
    need(rep, where, recipe, "level", int, lo=1, hi=9999)
    ingredients = recipe.get("ingredients")
    if not isinstance(ingredients, list) or not ingredients:
        rep.err(where, "needs at least one ingredient")
    else:
        for i, row in enumerate(ingredients):
            if not isinstance(row, dict):
                rep.err(where, f"ingredient {i} is not an object")
                continue
            need(rep, f"{where} / ingredient {i + 1}", row, "item", str)
            need(rep, f"{where} / ingredient {i + 1}", row, "qty", int, lo=1, hi=99)
    result = recipe.get("result")
    if not isinstance(result, dict):
        rep.err(where, "missing result object")
    else:
        need(rep, where, result, "item", str)
        need(rep, where, result, "qty", int, lo=1, hi=9)
    need(rep, where, recipe, "gold_cost", int, lo=0)
    need(rep, where, recipe, "description", str)


def load(path: str):
    with open(path, encoding="utf-8") as f:
        if path.endswith(".jsonl"):
            return [json.loads(line) for line in f if line.strip()]
        blob = json.load(f)
    for key in ("monsters", "moves", "quests", "chapters", "items", "recipes", "areas", "crops"):
        # A V2 monster itself owns a `moves` list; it is not a wrapper file.
        if isinstance(blob, dict) and key in blob and "id" not in blob and "name" not in blob:
            return blob[key]
    # Item libraries are name -> record maps rather than a wrapper list. A
    # template can also contain `_note` strings, which should not prevent the
    # actual item map from being recognised.
    item_records = ({str(name): value for name, value in blob.items()
                     if not str(name).startswith("_") and isinstance(value, dict)}
                    if isinstance(blob, dict) else {})
    bare_item_keys = {"id", "name", "kind", "value", "buy", "desc", "use", "stats", "skill_tree"}
    if item_records and isinstance(blob, dict) and not (set(blob) & bare_item_keys):
        return item_records
    # A Forge template or a hand-authored single record is a perfectly valid
    # input to the command-line checker. Wrap it so callers never iterate over
    # its keys as if every string were a record.
    return [blob] if isinstance(blob, dict) else blob


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--kind", default="monster",
                    choices=["monster", "move", "area", "item", "quest", "story", "recipe", "crop", "starter"])
    args = ap.parse_args()

    total = 0
    rep = Report()
    for path in args.paths:
        try:
            rows = load(path)
        except Exception as exc:
            rep.err(path, f"could not read: {exc}")
            continue
        if args.kind == "item" and isinstance(rows, dict):
            for name, spec in rows.items():
                total += 1
                check_item(spec, rep, name)
            continue
        if args.kind == "starter" and isinstance(rows, dict):
            rows = [rows]
        for row in rows:
            total += 1
            if not isinstance(row, dict):
                rep.err(path, "a record is not an object")
                continue
            {"monster": check_monster, "move": check_move, "area": check_area, "item": check_item,
             "quest": check_quest, "story": check_story, "recipe": check_recipe,
             "crop": check_crop, "starter": check_starter}[args.kind](row, rep)

    print(f"\nchecked {total} {args.kind} records")
    if rep.errors:
        print(f"\n{len(rep.errors)} ERRORS — these records will not load properly")
        for e in rep.errors[:40]:
            print("  " + e)
    if rep.warnings:
        print(f"\n{len(rep.warnings)} warnings — they load, but something is being ignored")
        for w in rep.warnings[:40]:
            print("  " + w)
    if not rep.errors and not rep.warnings:
        print("clean.")
    print()
    sys.exit(1 if rep.errors else 0)


if __name__ == "__main__":
    main()
