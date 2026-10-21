#!/usr/bin/env python3
"""
VOIDCALLER — THE FORGE. Make content with a local model, in a browser.

    python3 forge.py                 # opens the forge in your browser
    python3 forge.py --no-open
    python3 forge.py --ollama http://localhost:11434

It finds whatever models Ollama has, sends it a prompt built from the game's
own schema, checks what comes back with the same validator the game ships, and
writes the survivors straight into the folders the game reads at startup.

Nothing leaves your machine. The server binds to 127.0.0.1 and talks to Ollama
on localhost; if Ollama is not running you can still write content by hand,
drop files in, and validate and save them.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import mimetypes
import os
import random
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from engine.data import (ELEMENTS, explain_empty_bestiary,  # noqa: E402
                         load_bestiary, search_paths)
from engine.model import (CORE_STATS, RARITIES, RARITY_BST, ROLES,  # noqa: E402
                          canonical_rarity, canonical_type)
from engine import areas as AREAS                            # noqa: E402
from engine import model as M                               # noqa: E402
from engine import v2_art                                   # noqa: E402
from tools import validate_content as V                  # noqa: E402

WEB = os.path.join(ROOT, "forge")
PROMPTS = os.path.join(ROOT, "prompts")
TEMPLATES = os.path.join(ROOT, "templates")
SCHEMAS = os.path.join(ROOT, "schemas")
DATA = os.path.join(ROOT, "data")

OLLAMA = "http://localhost:11434"
# How long to let a schema-constrained request run before dropping to plain
# JSON mode. Grammar-constrained decoding on a nested schema is many times
# slower than free generation, and some backends never honour it at all.
SCHEMA_TIMEOUT = 90
# Flipped to False the first time an endpoint refuses the `think` field.
_THINK_SUPPORTED = [True]
LOCK = threading.Lock()
_bestiary = None

KINDS = {
    "monster": {
        "label": "Monster",
        "prompt": "monster.txt", "schema": "monster.schema.json",
        "template": "monster.json",
        "dest": os.path.join(DATA, "monsters"), "ext": ".jsonl",
        "note": "read at startup from data/monsters/*.jsonl",
    },
    "item": {
        "label": "Item",
        "prompt": "item.txt", "schema": "item.schema.json",
        "template": "item.json",
        "dest": DATA, "ext": ".json", "merge_into": "items.json",
        "note": "merged into data/items.json — stall stock and price overrides",
    },
    "quest": {
        "label": "Contract",
        "prompt": "quest.txt", "schema": "quest.schema.json",
        "template": "quest.json",
        "dest": os.path.join(DATA, "quests"), "ext": ".json",
        "note": "read from data/quests/*.json",
    },
    "story": {
        "label": "Chapter",
        "prompt": None, "schema": "story.schema.json",
        "template": "story.json",
        "dest": DATA, "ext": ".json", "merge_into": "story.json",
        "note": "merged into data/story.json",
    },
    "recipe": {
        "label": "Crafting Recipe",
        "prompt": "recipe.txt", "schema": "recipe.schema.json",
        "template": "recipe.json",
        "dest": os.path.join(DATA, "recipes"), "ext": ".json",
        "note": "stored in data/recipes/ for the deterministic crafting system",
    },
    "move": {
        "label": "Move",
        "prompt": "move.txt", "schema": "move.schema.json",
        "template": "move.json",
        "dest": DATA, "ext": ".json", "merge_into": "moves.json",
        "note": "stored in data/moves.json — attach it to a creature or skill-tree node in the Content Library",
    },
    "material": {
        "label": "Material",
        "prompt": "material.txt", "schema": "item.schema.json",
        "template": "item.json",
        "dest": DATA, "ext": ".json", "merge_into": "items.json",
        "note": "merged into data/items.json as kind=material — what monsters drop and recipes consume",
    },
    "weapon": {
        "label": "Weapon",
        "prompt": "weapon.txt", "schema": "item.schema.json",
        "template": "item.json",
        "dest": DATA, "ext": ".json", "merge_into": "items.json",
        "note": "merged into data/items.json as kind=weapon — the offensive equipment slot",
    },
    "armor": {
        "label": "Armour",
        "prompt": "armor.txt", "schema": "item.schema.json",
        "template": "item.json",
        "dest": DATA, "ext": ".json", "merge_into": "items.json",
        "note": "merged into data/items.json as kind=armor — the defensive equipment slot",
    },
    "seed": {
        "label": "Seed",
        "prompt": "seed.txt", "schema": "item.schema.json",
        "template": "item.json",
        "dest": DATA, "ext": ".json", "merge_into": "items.json",
        "note": "merged into data/items.json as kind=seed — plantable stock the stall sells",
    },
    "crop": {
        "label": "Farm Crop",
        "prompt": "crop.txt", "schema": "crop.schema.json",
        "template": "crop.json",
        "dest": DATA, "ext": ".json", "merge_into": "farm.json",
        "note": "merged into data/farm.json — its seed, its produce and its four "
                "growth sprites are all created with it",
    },
}

# One item registry, several authoring desks.  Materials, weapons, armour and
# seeds each get their own Forge page, but they are a VIEW over data/items.json
# rather than a second copy of it — so a drop table, a recipe ingredient and a
# crop's seed all still resolve against exactly one list of names.
ITEM_FAMILY = {"item": None, "material": "material", "weapon": "weapon",
               "armor": "armor", "seed": "seed"}


def is_item_kind(kind: str) -> bool:
    return kind in ITEM_FAMILY

# The Forge asks for a role in plain English; the engine stores one of seven.
ROLE_GROUPS = {
    "mix":     ["Striker", "Caster", "Tank", "Bruiser", "Support", "Controller", "Swarm"],
    "tank":    ["Tank", "Bruiser"],
    "dps":     ["Striker", "Caster", "Swarm", "Bruiser"],
    "support": ["Support", "Controller"],
}

TYPES = V.TYPES
TONES = ["grim", "whimsical", "tragic", "grotesque", "serene", "feral",
         "patient", "ravenous", "ceremonial"]


# --- what the game already knows -------------------------------------------
def bestiary(reload: bool = False):
    global _bestiary
    if _bestiary is None or reload:
        _bestiary = load_bestiary()
    return _bestiary


def library() -> dict:
    """The shape of the dataset as it stands, so the forge can suggest values
    that fit rather than inventing a region with one creature in it."""
    b = bestiary()
    habitats, families, drops, levels = {}, {}, {}, {}
    type_counts = {combat_type: 0 for combat_type in TYPES}
    move_count = 0
    for t in b.all:
        for h in t.habitat:
            habitats[h] = habitats.get(h, 0) + 1
        if t.family:
            families[t.family] = families.get(t.family, 0) + 1
        for d in t.drops:
            drops[d.item] = drops.get(d.item, 0) + 1
        band = (t.level - 1) // 8 * 8 + 1
        levels[band] = levels.get(band, 0) + 1
        type_counts[t.primary] = type_counts.get(t.primary, 0) + 1
        if t.secondary:
            type_counts[t.secondary] = type_counts.get(t.secondary, 0) + 1
        move_count += len(t.base_moves + t.skills)
    thin = sorted(h for h, n in habitats.items() if n < 3)
    item_specs = {str(name): spec for name, spec in _items().items()
                  if not str(name).startswith("_") and isinstance(spec, dict)}
    return {
        "species": len(b.all),
        "habitats": [{"name": h, "count": n} for h, n in
                     sorted(habitats.items(), key=lambda kv: -kv[1])],
        "families": [{"name": f, "count": n} for f, n in
                     sorted(families.items(), key=lambda kv: -kv[1])[:40]],
        "drops": sorted(drops)[:200],
        "levels": [{"band": f"{k}-{k + 7}", "count": v} for k, v in sorted(levels.items())],
        "thin_habitats": thin,
        "type_counts": type_counts,
        "move_count": move_count,
        "elements": list(ELEMENTS),
        "types": TYPES,
        "tones": TONES,
        "items": sorted(item_specs),
        "item_options": [{"name": name, "kind": str(spec.get("kind") or "material")}
                         for name, spec in sorted(item_specs.items())],
        "moves": _moves(),
        "areas": AREAS.load(),
    }


def _items() -> dict:
    try:
        with open(os.path.join(DATA, "items.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _moves() -> list:
    try:
        with open(os.path.join(DATA, "moves.json"), encoding="utf-8") as fh:
            blob = json.load(fh)
        rows = blob.get("moves", []) if isinstance(blob, dict) else blob
        return [dict(row) for row in rows if isinstance(row, dict)]
    except Exception:
        return []


def next_monster_id() -> str:
    highest = 0
    for t in bestiary().all:
        tail = str(t.id).rsplit("_", 1)[-1]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f"mon_{highest + 1:04d}"


def next_move_id(rows: list | None = None) -> str:
    highest = 0
    for row in rows if rows is not None else _moves():
        tail = str(row.get("id", "")).rsplit("_", 1)[-1]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f"move_{highest + 1:04d}"


# --- planning a batch -------------------------------------------------------
def parse_levels(spec, fallback=(8, 16)) -> list:
    """'20', '10-30', '12,45,60', '10-20,35' -> a list of levels."""
    out = []
    for part in str(spec or "").replace(" ", "").split(","):
        if not part:
            continue
        try:
            if "-" in part.lstrip("-"):
                lo, hi = (int(x) for x in part.split("-", 1))
                lo, hi = min(lo, hi), max(lo, hi)
                out += list(range(max(1, lo), min(50, hi) + 1))
            else:
                out.append(max(1, min(50, int(part))))
        except ValueError:
            continue
    if not out:
        out = list(range(fallback[0], fallback[1] + 1))
    return out


def spread(values: list, n: int, how: str = "even") -> list:
    """n picks from values. 'even' cycles so every value gets used; 'random'
    samples. Cycling is what you want for flooding: 20 monsters over 4 types
    gives you five of each, not fourteen Beasts."""
    if not values:
        return [None] * n
    if how == "random":
        return [random.choice(values) for _ in range(n)]
    pool = [values[i % len(values)] for i in range(n)]
    # shuffled, so two axes with the same length do not end up locked together
    # (every Undead in the fen, every Demon in the library) while the counts
    # stay exactly even
    random.shuffle(pool)
    return pool


def plan_batch(ask: dict) -> list:
    """Turn 'twenty Undead and Demons, levels 15-25, in the fen and the crypt'
    into twenty concrete, individually-specified requests."""
    n = max(1, min(200, int(ask.get("count") or 1)))
    lib = library()
    how = ask.get("spread") or "even"

    def picked(plural: str, singular: str) -> list:
        """Accept either the chip list or the single typed field.

        The form sends `family` and `role` from text inputs but `types`,
        `habitats` and `tones` from chip rows.  Reading only the plural keys
        silently threw away whatever was typed into Family and Role, so the
        boxes looked broken.  Take either.
        """
        values = list(ask.get(plural) or [])
        if not values and ask.get(singular):
            values = [ask[singular]]
        return [v for v in (str(x).strip() for x in values) if v]

    levels = parse_levels(ask.get("levels"), (8, 16))
    types = [t for t in (canonical_type(x) for x in picked("types", "type")) if t] or list(TYPES)
    habitats = picked("habitats", "habitat") or \
               [h["name"] for h in lib["habitats"][:8]] or ["the void"]
    tones = [t for t in picked("tones", "tone") if t in TONES] or list(TONES)
    families = picked("families", "family")
    # The form offers four plain-English groups rather than the seven internal
    # roles.  Each expands to the canonical roles it covers and those are then
    # spread across the batch, so "DPS ×3" gives a striker, a caster and a
    # swarm rather than three identical bruisers.  "Mix" means the whole set —
    # which also fixes the old behaviour where leaving Role blank silently
    # made every single creature a Bruiser.
    chosen = []
    for entry in picked("roles", "role"):
        group = ROLE_GROUPS.get(str(entry).strip().casefold())
        chosen.extend(group if group else [M.canonical_role(entry)])
    roles = chosen or list(ROLE_GROUPS["mix"])

    lv = spread(levels, n, how)
    ty = spread(types, n, how)
    hb = spread(habitats, n, how)
    tn = spread(tones, n, how)
    fm = spread(families, n, how) if families else [None] * n
    rl = spread(roles, n, how) if roles else [None] * n

    taken = {t.id for t in bestiary().all}
    nxt = 1
    out = []
    for i in range(n):
        while f"mon_{nxt:04d}" in taken:
            nxt += 1
        taken.add(f"mon_{nxt:04d}")
        row = {"id": f"mon_{nxt:04d}", "level": lv[i], "type": ty[i],
               "habitat": hb[i], "tone": tn[i]}
        if ask.get("rarity") in RARITIES:
            row["rarity"] = ask["rarity"]
        if fm[i]:
            row["family"] = fm[i]
        if rl[i]:
            row["role"] = rl[i]
        if ask.get("brief"):
            row["brief"] = ask["brief"]
        if ask.get("boss"):
            row["boss"] = True
        out.append(row)
    return out


def gap_plan(count: int = 20) -> dict:
    """What this dataset is actually short of, as a batch you can just run."""
    lib = library()
    b = bestiary()
    reasons = []

    thin = lib["thin_habitats"][:6]
    if thin:
        reasons.append(f"{len(lib['thin_habitats'])} regions have fewer than three "
                       f"species, which makes them thin to walk through")

    # level bands with the fewest monsters in them
    bands = {}
    for t in b.all:
        bands.setdefault((t.level - 1) // 8 * 8 + 1, 0)
        bands[(t.level - 1) // 8 * 8 + 1] += 1
    for start in range(1, 41, 8):
        bands.setdefault(start, 0)
    lean = sorted(bands.items(), key=lambda kv: kv[1])[:2]
    levels = ",".join(f"{lo}-{lo + 7}" for lo, _ in lean)
    if lean:
        reasons.append("the thinnest level bands are "
                       + " and ".join(f"{lo}-{lo + 7} ({n} species)" for lo, n in lean))

    # types that barely exist
    counts = {t: 0 for t in TYPES}
    for t in b.all:
        counts[t.primary] = counts.get(t.primary, 0) + 1
    rare_types = [k for k, v in sorted(counts.items(), key=lambda kv: kv[1])[:4]]
    reasons.append("the rarest types are " + ", ".join(rare_types))

    return {
        "count": count,
        "levels": levels or "10-25",
        "types": rare_types,
        "habitats": thin or [h["name"] for h in lib["habitats"][:6]],
        "spread": "even",
        "brief": ("Fill out a thin part of the world. Give it a clear combat role, "
                  "exactly two reliable starter moves, and reuse an existing "
                  "family and drop where it fits."),
        "why": reasons,
    }


# --- prompts ----------------------------------------------------------------
def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return ""


def level_curve(level: int) -> dict:
    """A neutral six-stat V2 budget example for a requested combat level.

    V2 no longer fits generated creatures to a hidden curve.  The authored
    base-stat total belongs to an explicit rarity, then the engine scales it
    cleanly from Level 1 to 50.  This helper stays as a friendly prompt aid
    for old callers, not a second source of balance truth.
    """
    _ = level
    return {"hp": 42, "atk": 42, "def": 38, "mag": 38, "res": 38, "spd": 38}


def exemplar(level: int = 12) -> dict:
    """A monster from the real dataset that does everything right, to show the
    model rather than tell it. Scored on the things the game actually cares
    about, and picked near the level being asked for."""
    best, best_score = None, -1
    for t in bestiary().all:
        score = 0
        all_moves = t.base_moves + t.skills
        if len(t.base_moves) == 2:
            score += 3
        if (any(s.category == "physical" and s.power > 0 for s in t.base_moves)
                and any(s.category == "support" for s in t.base_moves)):
            score += 3
        if 2 <= len(all_moves) <= 6:
            score += 2
        if all(20 <= s.power <= 90 for s in all_moves if s.is_damage):
            score += 2
        if t.family:
            score += 1
        if t.drops:
            score += 1
        if t.lore or t.quote:
            score += 1
        if any(s.effects for s in all_moves):
            score += 2
        score -= abs(t.level - level) / 8.0
        if score > best_score:
            best, best_score = t, score
    if best is None:
        return {}
    for path in search_paths():
        for f in sorted(glob.glob(path)):
            try:
                for raw in _raw_records(f):
                    if raw.get("name") == best.name:
                        return raw
            except Exception:
                continue
    return {}


def _raw_records(path: str):
    if path.endswith(".jsonl"):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    else:
        blob = json.load(open(path, encoding="utf-8"))
        for r in (blob.get("monsters", []) if isinstance(blob, dict) else blob):
            if isinstance(r, dict):
                yield r


def build_prompt(kind: str, ask: dict) -> tuple:
    """Returns (system, user). The system half is the game's own prompt file;
    the user half is this one request, plus the dataset's real vocabulary."""
    spec = KINDS[kind]
    system = read(os.path.join(PROMPTS, spec["prompt"])) if spec["prompt"] else ""
    schema = read(os.path.join(SCHEMAS, spec["schema"]))
    lib = library()
    lines = []

    if kind == "monster":
        level = max(1, min(50, int(ask.get("level", 10) or 10)))
        habitat = ask.get("habitat") or (lib["habitats"][0]["name"]
                                         if lib["habitats"] else "unmapped void")
        # This recommendation only helps an author start a record. Rarity is
        # saved explicitly and is never derived by the game at runtime.
        suggested = ("Common" if level <= 8 else "Uncommon" if level <= 18 else
                     "Rare" if level <= 32 else "Epic")
        rarity = ask.get("rarity") if ask.get("rarity") in RARITIES else suggested
        low, high = RARITY_BST[rarity]
        primary = canonical_type(ask.get("type")) or random.choice(TYPES)
        role = ask.get("role") if ask.get("role") in ROLES else "Bruiser"

        lines += [
            "Write ONE canonical V2 creature record for the game VOIDCALLER.",
            "VOIDCALLER is the name of the GAME. Never name the creature "
            "Voidcaller, Void Caller, or any variation of it, and do not use "
            "'Void' as the first word unless the brief below asks for it.",
            "",
            f"  id                 {ask.get('id') or next_monster_id()}",
            f"  recommended level  {level} (1–50 only)",
            f"  explicit rarity    {rarity} — BST MUST total {low}–{high}",
            f"  primary Type       {primary}",
            f"  role               {role}",
            f"  field note         {habitat}",
            f"  tone               {ask.get('tone') or random.choice(TONES)}",
            "",
            "V2 RULES — follow these exactly:",
            "- Combat Types are only Fire, Water, Electric, Nature, Earth, Wind, Light, Dark, Cosmic, Spirit, Primal, Arcane.",
            "- `types` is {primary, secondary}; `family` is a separate descriptive group used by missions.",
            "- `base_stats` contains exactly hp, atk, def, mag, res, spd. No MP, LUK, HIT, EVA, or permanent CRIT exists.",
            "- Every move has id, name, category, type, power, accuracy, pp, target, priority, crit, effects, tags, description.",
            "- PP is the only move resource. Do not include mp_cost, weight, element_affinity, or legacy `type` move categories.",
            "- base_moves contains exactly two records: one physical melee action and one self-targeted defensive/support action.",
            "- The defensive move must use a structured effect, for example {\"kind\":\"stat\",\"stat\":\"def\",\"amount\":0.25,\"turns\":2,\"target\":\"self\"}.",
            "- Use `moves` for later optional moves. A move may be untyped (type: null) only when that is intentional.",
            "- Build a finite `skill_tree` object with 3–4 branches. Nodes use max_rank, cost_per_rank, prerequisites, and effects_per_rank.",
            "- The game owns XP, gold and balance rewards. Drops use 0..1 rates.",
        ]
        if ask.get("family"):
            lines.append(f"  family             {ask['family']} (use exactly)")
        if ask.get("boss"):
            lines.append("  encounter.is_boss  true")
        if ask.get("brief"):
            # Put the author's own words last and label them plainly: this is
            # the line most likely to be followed, and it is the only place
            # their intent enters the prompt.
            lines += ["",
                      "WHAT THIS CREATURE MUST BE — follow this above all else:",
                      f"  {ask['brief']}",
                      "  Its name, appearance and lore all have to come from that "
                      "description. If a name is given there, use it exactly."]

        fams = [f["name"] for f in lib["families"][:16]]
        if fams:
            lines.append("  Existing families: " + ", ".join(fams))
        if lib["drops"]:
            lines.append("  Existing drop names: " + ", ".join(lib["drops"][:20]))
        # Every request in a batch is a separate call, so without this the
        # model cannot know what it just made and happily writes the same
        # creature three times.  The UI already tracks the batch's names for
        # duplicate detection; the model needs them BEFORE it writes, not after.
        taken = sorted({t.name for t in bestiary().all}
                       | {str(n).strip() for n in (ask.get("_seen") or []) if str(n).strip()})
        if taken:
            lines += ["", "Already made — do not reuse these names, and do not "
                          "write another creature on the same idea:",
                      ", ".join(taken[:70]) + (" …" if len(taken) > 70 else "")]
        lines += ["", "Make this creature clearly distinct from anything listed above: "
                      "a different silhouette, a different way of fighting, a "
                      "different name root."]
        lines += ["", "Output one JSON object only. It must match the supplied schema."]
    elif is_item_kind(kind):
        level = int(ask.get("level", 10) or 10)
        label = {"material": "crafting material", "weapon": "weapon",
                 "armor": "piece of armour", "seed": "farm seed"}.get(kind, "item")
        lines += [f"Write ONE {label}. Theme: {ask.get('brief') or 'something a hunter would carry'}.",
                  f"It should suit a hunter around level {level}."]
        if kind in ("weapon", "armor"):
            # Flat equipment bonuses are read against a real Level 1-50 stat
            # line, so quote the actual numbers rather than a vague tier word.
            reach = int(2 * (310 / 6) * level / 50) + 5
            lines.append(f"A level {level} creature has roughly {reach} in a given stat "
                         f"and about {int(2 * (310 / 6) * level / 50) + level + 10} HP, "
                         f"so keep the flat bonus proportionate to that.")
        if kind == "seed":
            lines.append("Name the seed '<Crop> Seed' after the crop it grows.")
        if kind == "material":
            lines.append("No 'use' block, no 'buy' price unless it is a plain workshop staple.")
        lines += ["", "Names already taken: " + ", ".join(lib["items"][:40])]
    elif kind == "quest":
        lines += [f"Write ONE contract of kind '{ask.get('quest_kind', 'fetch')}' "
                  f"for a hunter around level {ask.get('level', 10)}."]
        if ask.get("quest_kind") == "fetch":
            lines.append("target must be one of these exact item names: "
                         + ", ".join(lib["drops"][:30]))
        elif ask.get("quest_kind") == "slay":
            lines.append("target must be 'family:X' where X is one of: "
                         + ", ".join(f["name"] for f in lib["families"][:20]))
        else:
            lines.append("target must be the exact name of one of: "
                         + ", ".join(sorted(t.name for t in bestiary().all)[:40]))
        if ask.get("area_id"):
            lines.append("area_id must be exactly this Forge-authored Void Area id: "
                         + str(ask["area_id"]))
        elif lib["areas"]:
            lines.append("area_id must be exactly one of these Void Area ids: "
                         + ", ".join(row["id"] for row in lib["areas"]))
        else:
            lines.append("There are no Void Areas yet. Create one in the guided Content Library before generating a mission.")
        if ask.get("brief"):
            lines += ["", "The person asking wants: " + str(ask["brief"])]
    elif kind == "recipe":
        level = int(ask.get("level", 10) or 10)
        if not lib["items"]:
            raise ValueError("create the item the recipe will make, plus its ingredient items, before generating a recipe")
        lines += [f"Write ONE crafting recipe for around level {level}.",
                  "Every ingredient and the result MUST be an exact existing item name from this library: "
                  + ", ".join(lib["items"][:80]),
                  "Do not invent a new item name. A recipe links existing items; create its weapon, armour, potion, or material in the Item Forge first."]
        if ask.get("station"):
            lines.append("station must be " + str(ask["station"]))
        if ask.get("brief"):
            lines += ["", "The craft should be: " + str(ask["brief"])]
    elif kind == "move":
        level = int(ask.get("level", 10) or 10)
        category = str(ask.get("category") or ask.get("style") or "physical").casefold()
        if category == "status":
            category = "support"
        move_type = canonical_type(ask.get("type") or ask.get("element"))
        lines += [
            "Write ONE canonical V2 reusable move-library record.",
            f"  id        {ask.get('id') or next_move_id()}",
            f"  role      {ask.get('role') or 'a dependable combat technique'}",
            f"  category  {category}",
            f"  Type      {move_type or 'null (neutral)'}",
            f"  level     {max(1, min(50, level))} (keep power appropriate for this point)",
            "Required fields: id, name, category, type, power, accuracy, pp, target, priority, crit, effects, tags, description.",
            "PP is the only resource. Physical/magical moves need useful power; support moves have power 0 and structured effects.",
            "A structured stat effect is {\"kind\":\"stat\",\"stat\":\"spd\",\"amount\":0.25,\"turns\":2,\"target\":\"self\"}.",
            "",
            "Existing move names: " + ", ".join(str(row.get("name")) for row in lib["moves"][:40]),
        ]
        if ask.get("brief"):
            lines += ["", "The technique should be: " + str(ask["brief"])]
    else:
        lines += [f"Write ONE story chapter, number {ask.get('level', 1)}, "
                  f"for a hunter around level {ask.get('level', 10)}.",
                  "Battle scenes must describe a SHAPE (boss / highest / min_rarity / "
                  "max_level), never a monster id.",
                  read(os.path.join(TEMPLATES, "story.json"))]
        if ask.get("brief"):
            lines += ["", "The person asking wants: " + str(ask["brief"])]

    if schema and kind != "monster":
        lines += ["", "It must validate against this schema:", schema]
    if not system:
        system = ("You write content for a turn-based JRPG called VOIDCALLER. "
                  "Output ONE JSON object and nothing else — no markdown fence, "
                  "no commentary.")
    return system, "\n".join(lines)


# --- ollama -----------------------------------------------------------------
def candidates(endpoint: str) -> list:
    """`localhost` can resolve to ::1 while Ollama is only listening on IPv4,
    which looks exactly like Ollama being down. Try both spellings."""
    endpoint = (endpoint or OLLAMA).rstrip("/")
    out = [endpoint]
    if "localhost" in endpoint:
        out.append(endpoint.replace("localhost", "127.0.0.1"))
    elif "127.0.0.1" in endpoint:
        out.append(endpoint.replace("127.0.0.1", "localhost"))
    return out


def ollama_models(endpoint: str) -> dict:
    last = "no endpoint"
    for base in candidates(endpoint):
        try:
            with urllib.request.urlopen(base + "/api/tags", timeout=4) as r:
                blob = json.loads(r.read().decode("utf-8"))
            models = [{"name": m.get("name", ""),
                       "size": round((m.get("size") or 0) / 1e9, 1),
                       "family": ((m.get("details") or {}).get("family") or "")}
                      for m in blob.get("models", [])]
            models.sort(key=lambda m: m["name"])
            return {"ok": True, "models": models, "endpoint": base}
        except Exception as exc:
            last = str(exc)
    return {"ok": False, "models": [], "endpoint": endpoint, "error": last}


def ollama_generate(endpoint: str, model: str, system: str, user: str,
                    temperature: float, timeout: int = 300,
                    schema: dict | None = None) -> dict:
    """Ask the model for one record.

    If a schema is given, it is handed to Ollama as the `format`, which
    constrains decoding to that shape -- the model cannot emit a monster with a
    missing field or a string where a number goes. Older Ollama does not
    understand a schema there, so we fall back to plain JSON mode.
    """
    def payload(fmt, think=False):
        body = {
            "model": model, "system": system, "prompt": user,
            "format": fmt, "stream": False,
            "options": {"temperature": temperature, "top_p": 0.95},
        }
        # Reasoning models (Qwen3, and anything else with a thinking mode) put
        # their chain of thought in a separate `thinking` field and leave
        # `response` empty when the whole answer reads as reasoning.  We want
        # the record, not the deliberation, so ask for thinking to be off.
        # Ollama rejects this field outright for models that have no thinking
        # mode, so a refusal makes us drop it for the rest of the session.
        if think is not None and _THINK_SUPPORTED[0]:
            body["think"] = think
        return json.dumps(body).encode("utf-8")

    # Schema-constrained decoding is the slow path, and some backends (notably
    # MLX builds) do not implement grammar constraints at all — the request then
    # stalls rather than erroring, and the plain-JSON fallback below never gets
    # a turn.  Give the schema attempt a short leash and let the fallback,
    # which every backend supports, have the real timeout.  Nothing is lost by
    # falling back: repair_record() fills in whatever the schema would have
    # forced, so plain JSON mode produces the same valid record.
    formats = [schema, "json"] if schema else ["json"]
    last = None
    for fmt in formats:
        wait = min(timeout, SCHEMA_TIMEOUT) if fmt is schema else timeout
        for base in candidates(endpoint):
            req = urllib.request.Request(base + "/api/generate", data=payload(fmt),
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=wait) as r:
                    out = json.loads(r.read().decode("utf-8"))
                    out["_format"] = "json" if fmt == "json" else "schema"
                    return out
            except urllib.error.HTTPError as exc:
                last = exc
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "replace")
                except Exception:
                    pass
                if "think" in detail.casefold() and _THINK_SUPPORTED[0]:
                    # This model has no thinking mode. Stop sending the field
                    # and retry the same format immediately.
                    _THINK_SUPPORTED[0] = False
                    continue
                break               # the server answered; try the next format
            except urllib.error.URLError as exc:
                last = exc
            except TimeoutError as exc:
                # A stalled schema attempt is not fatal; plain JSON is next.
                last = exc
                break
    raise last or RuntimeError("no endpoint to try")


def _brace_spans(text: str):
    """Every balanced {...} span in the text, longest first.

    Reasoning models narrate before they answer, and the narration mentions
    braces — "I'll use {hp, atk, def}" — so spanning from the first "{" to the
    last "}" swallows prose and fails.  Walk the string instead, tracking
    string literals and escapes so a brace inside a quoted value never counts.
    """
    spans, stack, in_string, escaped = [], [], False, False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            stack.append(index)
        elif char == "}" and stack:
            spans.append((stack.pop(), index + 1))
    return [text[a:b] for a, b in sorted(spans, key=lambda s: s[1] - s[0], reverse=True)]


def coerce_json(text: str):
    """Models fence it, narrate around it, or bury it in a reasoning trace.
    Take the object anyway."""
    text = (text or "").strip()
    if "```" in text:
        # Prefer a fenced block; take the largest one, ignoring the language tag.
        blocks = text.split("```")[1::2]
        for block in sorted(blocks, key=len, reverse=True):
            body = block.split("\n", 1)[-1] if block[:12].strip().isalpha() else block
            try:
                return json.loads(body.strip())
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the biggest balanced object that both parses and looks like
    # a record rather than a stray fragment from the narration.
    fragments = _brace_spans(text)
    fallback = None
    for candidate in fragments:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            if len(parsed) > 1 or any(k in parsed for k in ("name", "id", "base_stats")):
                return parsed
            fallback = parsed if fallback is None else fallback
    if fallback is not None:
        return fallback
    raise ValueError("no JSON object in the reply")


# --- duplicates -------------------------------------------------------------
def fingerprint(m: dict) -> tuple:
    st = m.get("base_stats") or m.get("stats") or {}
    return ((m.get("types") or {}).get("primary"), m.get("rarity"),
            st.get("hp"), st.get("atk"), st.get("mag"), st.get("spd"))


def apply_portrait_seed(record: dict) -> dict:
    """Give every Forge-authored monster a durable visual identity.

    It is deliberately data, not a downloaded image: the game turns this
    short BLAKE2 fingerprint into the terminal creature portrait.  Keeping the
    key in the record means a rename or reload cannot make the creature's
    visual identity drift.
    """
    if not isinstance(record, dict):
        return record
    if str(record.get("portrait_seed") or "").strip():
        return record
    identity = "|".join((
        str(record.get("id") or ""), str(record.get("name") or ""),
        str((record.get("types") or {}).get("primary") or ""),
        str(record.get("size") or ""),
        str(record.get("role") or ""),
    ))
    record["portrait_seed"] = hashlib.blake2s(identity.encode("utf-8"),
                                               digest_size=8).hexdigest()
    return record


def write_visual_assets(kind: str, record: dict) -> None:
    """Materialise deterministic Forge art next to the game, never in saves.

    The saved seed remains the source of truth.  Deleting ``assets/V2`` is
    therefore recoverable: opening or saving the record recreates the PNG.
    """
    if kind == "monster" and isinstance(record, dict):
        apply_portrait_seed(record)
        v2_art.write_monster(record.get("id"), record.get("portrait_seed"),
                             (record.get("types") or {}).get("primary", "Primal"),
                             record.get("sprite_archetype", "Core"))
    elif is_item_kind(kind) and isinstance(record, dict):
        name = str(record.get("name") or "").strip()
        if name:
            item_kind = str(record.get("kind") or ITEM_FAMILY[kind] or "material")
            identity = "|".join((name, item_kind, str(record.get("desc") or "")))
            seed = hashlib.blake2s(identity.encode("utf-8"), digest_size=8).hexdigest()
            v2_art.write_item(name, seed, item_kind)
    elif kind == "crop" and isinstance(record, dict):
        identity = "|".join((str(record.get("id") or ""), str(record.get("label") or ""),
                              str(record.get("seed") or "")))
        seed = hashlib.blake2s(identity.encode("utf-8"), digest_size=8).hexdigest()
        v2_art.write_crop(record.get("id"), seed, record.get("sprite_family", "Nature"))


def duplicate_of(record: dict, extra_names=(), extra_prints=()) -> str:
    """Models converge hard on the same handful of names. Say so rather than
    letting six Shadowfangs into the bestiary."""
    name = str(record.get("name", "")).strip().lower()
    if not name:
        return ""
    known = {t.name.lower() for t in bestiary().all} | {str(n).lower() for n in extra_names}
    if name in known:
        return f"there is already a {record.get('name')}"
    # near-miss: same first word and same type is usually the same idea again
    head = name.split()[0]
    for other in known:
        if other.split()[0] == head and len(head) > 4:
            return f"very close to {other.title()}"
    if fingerprint(record) in set(extra_prints):
        return "identical stat line to one already in this batch"
    return ""


# --- repair -----------------------------------------------------------------
# The generator's job is identity; the engine's job is rules and balance.  A
# record that is recognisably the creature the model meant should be corrected
# and kept, not thrown away because a sum missed a 31-wide window or because
# the model wrote "buff" where the engine calls it "stat".

_EFFECT_KIND_ALIASES = {
    "buff": "stat", "debuff": "stat", "stat_change": "stat", "stat_mod": "stat",
    "statmod": "stat", "modify_stat": "stat", "damage_over_time": "status",
    "dot": "status", "ailment": "status", "inflict": "status",
    "healing": "heal", "restore": "heal", "lifesteal": "drain", "leech": "drain",
    "purify": "cleanse", "resurrect": "revive",
    # skill-tree wording
    "stat_percent": "stat_pct", "stat_pct_bonus": "stat_pct",
    "damage_pct": "move_damage_pct", "crit": "crit_bonus",
    "crit_chance": "crit_bonus", "physical_pct": "physical_damage_pct",
    "magical_pct": "magical_damage_pct", "learn_move": "unlock_move",
}
_RARITY_LEVEL = {"Common": 6, "Uncommon": 14, "Rare": 24, "Epic": 34}
_RARITY_CAPTURE = {"Common": 0.35, "Uncommon": 0.25, "Rare": 0.15, "Epic": 0.08}


def _repair_effects(effects, notes, where, *, tree=False):
    if not isinstance(effects, list):
        return [] if effects in (None, "", {}) else effects
    out = []
    for effect in effects:
        if not isinstance(effect, dict):
            notes.append(f"{where}: dropped an effect that was not an object")
            continue
        effect = dict(effect)
        kind = str(effect.get("kind") or "").strip().casefold()
        if kind in _EFFECT_KIND_ALIASES:
            mapped = _EFFECT_KIND_ALIASES[kind]
            # "debuff" is a negative "stat" change; keep the sign the author meant.
            if kind == "debuff" and isinstance(effect.get("amount"), (int, float)):
                effect["amount"] = -abs(effect["amount"])
            effect["kind"] = mapped
            notes.append(f"{where}: effect '{kind}' rewritten as '{mapped}'")
            kind = mapped
        allowed = {"status", "stat", "heal", "drain", "cleanse", "revive"}
        if tree:
            allowed |= {"stat_pct", "unlock_move", "move", "move_damage_pct",
                        "physical_damage_pct", "magical_damage_pct", "crit_bonus"}
        if kind not in allowed:
            notes.append(f"{where}: dropped unsupported effect '{kind}'")
            continue
        if kind in {"stat", "stat_pct"}:
            stat = str(effect.get("stat") or effect.get("key") or "").strip().casefold()
            stat = {"attack": "atk", "defence": "def", "defense": "def", "magic": "mag",
                    "resistance": "res", "speed": "spd", "health": "hp"}.get(stat, stat)
            if stat not in {*V.CORE_STATS, "accuracy", "evasion"}:
                notes.append(f"{where}: dropped effect on retired stat '{stat}'")
                continue
            effect["stat"] = stat
            effect.pop("key", None)
        if kind == "status":
            key = str(effect.get("status") or effect.get("key") or "").strip().casefold()
            if key not in V.STATUSES:
                notes.append(f"{where}: dropped unknown status '{key}'")
                continue
            effect["status"] = key
            effect.pop("key", None)
        # The engine reads `chance` as a percentage (0-100), but models and
        # older docs both write it as a 0-1 fraction.  A value of 0.4 almost
        # certainly means "40%", not "two fifths of one percent", so read
        # anything at or below 1 as a fraction and scale it.
        raw_chance = effect.get("chance")
        if isinstance(raw_chance, (int, float)) and 0 < raw_chance <= 1:
            effect["chance"] = round(raw_chance * 100)
            notes.append(f"{where}: chance {raw_chance} read as {effect['chance']}%")
        elif isinstance(raw_chance, (int, float)) and raw_chance > 100:
            effect["chance"] = 100
            notes.append(f"{where}: chance capped at 100%")
        if kind in {"heal", "drain", "revive", "stat", "stat_pct", "move_damage_pct",
                    "physical_damage_pct", "magical_damage_pct", "crit_bonus"} \
                and not isinstance(effect.get("amount"), (int, float)):
            effect["amount"] = 0.15
            notes.append(f"{where}: effect had no numeric amount, set to 0.15")
        out.append(effect)
    return out


def _repair_move(move, notes, where, *, base=False):
    if not isinstance(move, dict):
        return None
    move = dict(move)
    move["name"] = str(move.get("name") or "Unnamed Move").strip()[:40] or "Unnamed Move"
    move["id"] = V_slug(move.get("id") or move["name"], "move")
    category = str(move.get("category") or move.get("type") or "").strip().casefold()
    if category not in V.SKILL_KINDS:
        category = "support" if not move.get("power") else "physical"
        notes.append(f"{where}: category set to '{category}'")
    move["category"] = category
    combat_type = M.canonical_type(move.get("type") if "category" in move else move.get("element"))
    move["type"] = combat_type
    power = move.get("power")
    power = float(power) if isinstance(power, (int, float)) else 0.0
    if category == "support" and power:
        notes.append(f"{where}: support moves carry no power, set to 0")
        power = 0.0
    if category in ("physical", "magical") and power <= 0:
        power = 45.0
        notes.append(f"{where}: a damaging move needs power, set to 45")
    move["power"] = int(min(180, max(0, power)))
    pp = move.get("pp")
    move["pp"] = int(min(99, max(1, int(pp)))) if isinstance(pp, (int, float)) else 25
    target = str(move.get("target") or "").strip().casefold()
    if target not in V.TARGETS:
        target = "self" if category == "support" else "single"
        notes.append(f"{where}: target set to '{target}'")
    move["target"] = target
    accuracy = move.get("accuracy")
    move["accuracy"] = int(min(100, max(30, accuracy))) if isinstance(accuracy, (int, float)) else 95
    priority = move.get("priority")
    move["priority"] = int(min(7, max(-7, priority))) if isinstance(priority, (int, float)) else 0
    crit = move.get("crit")
    if isinstance(crit, (int, float)) and 0 < crit < 1:
        # The engine reads crit as a percentage. 0.05 means 5%, not 0.05%.
        notes.append(f"{where}: crit {crit} read as {round(crit * 100)}%")
        crit = crit * 100
    move["crit"] = float(min(40, max(0, crit))) if isinstance(crit, (int, float)) else 5
    move["effects"] = _repair_effects(move.get("effects"), notes, where)
    move.pop("mp_cost", None)
    move.pop("weight", None)
    if base and category == "support":
        move["target"] = "self"
        if not move["effects"]:
            move["effects"] = [{"kind": "stat", "stat": "def", "amount": 0.25, "turns": 2}]
            notes.append(f"{where}: the defensive fundamental needs an effect, gave it +25% DEF for 2 turns")
    return move


def _default_skill_tree(record: dict) -> dict:
    """Build a workable 3-branch tree for a creature the model left without one.

    Models routinely skip the skill tree — it is the largest and fiddliest part
    of the record.  A creature with no tree still fights, but it has no build,
    and the spec treats finite trees as a core progression layer.  This gives
    it one shaped by its own stats: an offence path that follows whichever of
    ATK or MAG it actually leads with, a resilience path, and a finesse path.

    It costs 55 points against the ~49 a creature earns by Level 50, so the
    player still has to choose. Replace it in the Forge whenever you want
    something authored.
    """
    stats = record.get("base_stats") or {}
    magical = float(stats.get("mag", 0) or 0) > float(stats.get("atk", 0) or 0)
    lead, lead_name = ("mag", "Channelling") if magical else ("atk", "Might")
    damage_kind = "magical_damage_pct" if magical else "physical_damage_pct"
    best = max(("hp", "def", "res", "spd"), key=lambda k: float(stats.get(k, 0) or 0))

    def node(ident, name, ranks, cost, effects, prereq=None, keystone=False):
        row = {"id": ident, "name": name, "max_rank": ranks, "cost_per_rank": cost,
               "prerequisites": list(prereq or []), "effects_per_rank": effects}
        if keystone:
            row["keystone"] = True
        return row

    return {"branches": [
        {"id": "offence", "name": lead_name, "nodes": [
            node(f"{lead}_training", "Training", 5, 1,
                 [{"kind": "stat_pct", "stat": lead, "amount": 0.03}]),
            node("pressing_attack", "Pressing Attack", 3, 2,
                 [{"kind": damage_kind, "amount": 0.03}],
                 [{"node": f"{lead}_training", "rank": 3}]),
            node("finishing_blow", "Finishing Blow", 3, 3,
                 [{"kind": "crit_bonus", "amount": 0.03}],
                 [{"node": "pressing_attack", "rank": 2}]),
        ]},
        {"id": "resilience", "name": "Resilience", "nodes": [
            node("vigour", "Vigour", 5, 1,
                 [{"kind": "stat_pct", "stat": "hp", "amount": 0.03}]),
            node("braced", "Braced", 3, 2,
                 [{"kind": "stat_pct", "stat": "def", "amount": 0.04}],
                 [{"node": "vigour", "rank": 3}]),
            node("warded", "Warded", 3, 3,
                 [{"kind": "stat_pct", "stat": "res", "amount": 0.04}],
                 [{"node": "vigour", "rank": 3}]),
        ]},
        {"id": "finesse", "name": "Finesse", "nodes": [
            node("quickening", "Quickening", 5, 1,
                 [{"kind": "stat_pct", "stat": "spd", "amount": 0.03}]),
            node("read_the_field", "Read the Field", 3, 2,
                 [{"kind": "crit_bonus", "amount": 0.02}],
                 [{"node": "quickening", "rank": 3}]),
            node("defining_trait", "Defining Trait", 1, 4,
                 [{"kind": "stat_pct", "stat": best, "amount": 0.10}],
                 [{"node": "read_the_field", "rank": 2}], keystone=True),
        ]},
    ]}


def _repair_monster(record, notes):
    record["rarity"] = M.canonical_rarity(record.get("rarity"), legacy_level=record.get("level") or 1)
    record["role"] = M.canonical_role(record.get("role"))
    record["name"] = str(record.get("name") or "Unnamed").strip()[:28] or "Unnamed"
    record["id"] = V_slug(record.get("id") or record["name"], "mon")
    level = record.get("level")
    if not isinstance(level, (int, float)) or not 1 <= level <= 50:
        record["level"] = _RARITY_LEVEL.get(record["rarity"], 6)
        notes.append(f"level set to {record['level']} to suit a {record['rarity']} creature")
    else:
        record["level"] = int(level)
    if record.get("size") not in V.SIZES:
        record["size"] = "Medium"
    capture = record.get("capture_rate")
    if not isinstance(capture, (int, float)) or not 0 <= capture <= 1:
        record["capture_rate"] = _RARITY_CAPTURE.get(record["rarity"], 0.25)
    types = record.get("types") if isinstance(record.get("types"), dict) else {}
    primary = M.canonical_type(types.get("primary"), allow_none=False)
    secondary = M.canonical_type(types.get("secondary"))
    if secondary == primary:
        secondary = None
        notes.append("secondary Type duplicated the primary, cleared it")
    record["types"] = {"primary": primary, "secondary": secondary}
    if not isinstance(record.get("family"), str) or not record["family"].strip():
        record["family"] = "Aberration"

    stats, stat_notes = M.normalise_base_stats(record.get("base_stats") or record.get("stats"),
                                               record["rarity"])
    record["base_stats"] = stats
    record.pop("stats", None)
    notes.extend(stat_notes)

    base_moves = record.get("base_moves")
    base_moves = [m for m in base_moves if isinstance(m, dict)] if isinstance(base_moves, list) else []
    repaired = [_repair_move(m, notes, f"base move {i + 1}", base=True)
                for i, m in enumerate(base_moves[:2])]
    repaired = [m for m in repaired if m]
    melee = next((m for m in repaired if m["category"] == "physical" and m["power"] > 0), None)
    support = next((m for m in repaired if m["category"] == "support" and m["target"] == "self"), None)
    spare = [m for m in repaired if m is not melee and m is not support]
    if melee is None:
        melee = _repair_move({"id": f"{record['id']}_strike", "name": "Strike", "category": "physical",
                              "type": record["types"]["primary"], "power": 45, "accuracy": 95,
                              "pp": 30, "target": "single", "priority": 0, "crit": 5, "effects": [],
                              "description": "a plain committed blow"}, notes, "base move 1")
        notes.append("added the missing physical fundamental")
    if support is None:
        support = _repair_move({"id": f"{record['id']}_brace", "name": "Brace", "category": "support",
                                "type": None, "power": 0, "accuracy": 100, "pp": 20, "target": "self",
                                "priority": 0, "crit": 0,
                                "effects": [{"kind": "stat", "stat": "def", "amount": 0.25, "turns": 2}],
                                "description": "sets itself against the next blow"},
                               notes, "base move 2", base=True)
        notes.append("added the missing defensive fundamental")
    record["base_moves"] = [melee, support]

    extra = [m for m in (record.get("moves") or []) if isinstance(m, dict)]
    record["moves"] = [m for m in (_repair_move(m, notes, f"move {i + 1}")
                                   for i, m in enumerate(spare + extra)) if m]

    tree = record.get("skill_tree")
    if isinstance(tree, dict) and isinstance(tree.get("branches"), list):
        node_ids = set()
        for branch in tree["branches"]:
            if not isinstance(branch, dict):
                continue
            branch["id"] = V_slug(branch.get("id") or branch.get("name"), "branch")
            branch["name"] = str(branch.get("name") or branch["id"].title())[:40]
            nodes = branch.get("nodes") if isinstance(branch.get("nodes"), list) else []
            clean = []
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node["id"] = V_slug(node.get("id") or node.get("name"), "node")
                if node["id"] in node_ids:
                    continue
                node_ids.add(node["id"])
                node["name"] = str(node.get("name") or node["id"].title())[:40]
                rank = node.get("max_rank")
                node["max_rank"] = int(min(5, max(1, rank))) if isinstance(rank, (int, float)) else 3
                cost = node.get("cost_per_rank")
                node["cost_per_rank"] = int(min(5, max(1, cost))) if isinstance(cost, (int, float)) else 1
                node["effects_per_rank"] = _repair_effects(node.get("effects_per_rank"), notes,
                                                           f"node {node['name']}", tree=True)
                clean.append(node)
            branch["nodes"] = clean
        tree["branches"] = [b for b in tree["branches"]
                            if isinstance(b, dict) and b.get("nodes")][:4]
        for branch in tree["branches"]:
            for node in branch["nodes"]:
                prereqs = [r for r in (node.get("prerequisites") or [])
                           if not isinstance(r, dict) or r.get("node") in node_ids]
                if len(prereqs) != len(node.get("prerequisites") or []):
                    notes.append(f"node {node['name']}: dropped a prerequisite pointing at no node")
                node["prerequisites"] = prereqs
    # Whatever survived, a creature must end up with a usable tree. An empty
    # branch list is a hard validation error, and "no tree at all" leaves the
    # creature with no build, so fill it in.
    tree = record.get("skill_tree")
    if not (isinstance(tree, dict) and isinstance(tree.get("branches"), list)
            and tree["branches"]):
        record["skill_tree"] = _default_skill_tree(record)
        notes.append("no usable skill tree in the record — built a default "
                     "3-branch tree from its stats; re-author it in the Forge when you like")

    drops = []
    for drop in record.get("drops") or []:
        if not isinstance(drop, dict) or not str(drop.get("item") or "").strip():
            continue
        rate = drop.get("rate")
        drop["rate"] = min(1.0, max(0.01, float(rate))) if isinstance(rate, (int, float)) else 0.25
        drops.append(drop)
    record["drops"] = drops
    return record


def V_slug(value, fallback):
    return M.slug(value, fallback)


def _known_item_names() -> list:
    return [str(name) for name in _items() if not str(name).startswith("_")]


def _add_item(name: str, body: dict) -> None:
    """Write one item straight into data/items.json and give it a sprite."""
    path = os.path.join(DATA, "items.json")
    blob = _items()
    blob[name] = body
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(blob, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    write_visual_assets("item", {"name": name, **body})


# What a harvest is allowed to do. These are the only keys engine/session.py
# acts on, so anything else in a `use` block is decoration that never fires.
CROP_STATS = ["atk", "def", "mag", "res", "spd"]


def crop_use(raw) -> dict:
    """The harvest effect, clamped to what the game can actually perform.

    A crop with no effect is not broken -- it is an ingredient, and that is a
    legitimate crop. Returning an empty dict says exactly that.
    """
    if not isinstance(raw, dict):
        return {}
    use = {}
    try:
        heal = float(raw.get("heal_pct") or 0)
        if heal > 1.5:                      # a model that answered in percent
            heal /= 100.0
        if heal > 0:
            use["heal_pct"] = round(max(0.05, min(1.0, heal)), 3)
    except (TypeError, ValueError):
        pass
    try:
        pp = int(raw.get("pp_restore") or 0)
        if pp > 0:
            use["pp_restore"] = max(1, min(20, pp))
    except (TypeError, ValueError):
        pass
    try:
        revive = float(raw.get("revive_pct") or 0)
        if revive > 1.5:
            revive /= 100.0
        if revive > 0:
            use["revive_pct"] = round(max(0.1, min(1.0, revive)), 3)
    except (TypeError, ValueError):
        pass
    if raw.get("cleanse"):
        use["cleanse"] = True
    buff = raw.get("buff")
    if isinstance(buff, (list, tuple)) and len(buff) >= 3:
        stat = str(buff[0] or "").lower()
        if stat in CROP_STATS:
            try:
                amount = float(buff[1])
                if amount > 1.5:
                    amount /= 100.0
                rounds = int(buff[2])
                use["buff"] = [stat, round(max(0.05, min(0.5, amount)), 3),
                               max(1, min(10, rounds))]
            except (TypeError, ValueError):
                pass
    return use


def ensure_crop_items(record: dict, notes: list) -> None:
    """A crop is only playable if its seed can be bought and its produce sold.

    Authoring a crop whose seed does not exist as an item is the single most
    common way to end up with a farm that cannot be started, because the stall
    has nothing to sell you.  Create both sides the moment the crop is saved.
    """
    if not isinstance(record, dict):
        return
    known = set(_known_item_names())
    seed_name = str(record.get("seed") or "").strip()
    crop_name = str(record.get("item") or "").strip()
    try:
        amount = max(1, int(record.get("yield", 1)))
    except (TypeError, ValueError):
        amount = 1
    use = crop_use(record.get("use"))
    if use:
        record["use"] = use
    grown_on = record.get("label") or "the farm"
    if crop_name and crop_name not in known:
        body = {"kind": "consumable" if use else "material", "value": 14,
                "desc": f"harvested from {grown_on}"}
        if use:
            body["use"] = use
        _add_item(crop_name, body)
        notes.append(f"created the produce item '{crop_name}' as a "
                     f"{'consumable that ' + _use_summary(use) if use else 'crafting material'}")
        known.add(crop_name)
    elif crop_name and use:
        # The crop grew an effect after its produce already existed. Without
        # this the harvest stays a dead material for the rest of the save.
        current = _items().get(crop_name) or {}
        if current.get("use") != use or current.get("kind") != "consumable":
            _add_item(crop_name, {**current, "kind": "consumable", "use": use,
                                  "value": int(current.get("value") or 14),
                                  "desc": str(current.get("desc") or f"harvested from {grown_on}")})
            notes.append(f"'{crop_name}' now {_use_summary(use)} when eaten")
    if seed_name and seed_name not in known:
        value = int((_items().get(crop_name) or {}).get("value") or 14)
        _add_item(seed_name, {"kind": "seed", "value": max(2, value // 3),
                              "buy": max(10, int(value * amount * 0.55)),
                              "desc": f"plantable stock for {record.get('label') or 'the farm'}"})
        notes.append(f"created the seed item '{seed_name}' and priced it at the stall")


def _use_summary(use: dict) -> str:
    """What this harvest does, in the words the Forge reports back to you."""
    parts = []
    if use.get("heal_pct"):
        parts.append(f"restores {int(use['heal_pct'] * 100)}% HP")
    if use.get("pp_restore"):
        parts.append(f"gives back {use['pp_restore']} PP")
    if use.get("revive_pct"):
        parts.append(f"revives at {int(use['revive_pct'] * 100)}% HP")
    if use.get("cleanse"):
        parts.append("cures status")
    if use.get("buff"):
        stat, amount, rounds = use["buff"]
        parts.append(f"raises {stat.upper()} by {int(amount * 100)}% for {rounds} rounds")
    return " and ".join(parts) if parts else "does nothing"


def _resolve_item_name(name: str, known: list) -> str:
    """Snap a near-miss item name onto a real one."""
    import difflib
    exact = {value.casefold(): value for value in known}
    if name in exact.values():
        return name
    if name.casefold() in exact:
        return exact[name.casefold()]
    close = difflib.get_close_matches(name, known, n=1, cutoff=0.78)
    return close[0] if close else ""


def _repair_recipe(record: dict, notes: list) -> dict:
    """Make every ingredient and result point at an item that really exists.

    Models invent ingredient names however firmly the prompt forbids it.  A
    near-miss is snapped onto the real item; anything genuinely new is created
    as a material so the recipe is playable instead of rejected.
    """
    known = _known_item_names()
    record["id"] = V_slug(record.get("id") or record.get("name"), "recipe")
    record["name"] = str(record.get("name") or "Unnamed Recipe").strip()[:50]
    if record.get("station") not in ("craft_shop", "farm_kitchen", "soul_forge"):
        record["station"] = "craft_shop"
    level = record.get("level")
    record["level"] = int(min(9999, max(1, level))) if isinstance(level, (int, float)) else 5
    gold = record.get("gold_cost")
    record["gold_cost"] = int(max(0, gold)) if isinstance(gold, (int, float)) else 0
    record.setdefault("description", f"{record['name']}, assembled at the bench")

    def fix(name: str, role: str) -> str:
        name = str(name or "").strip()
        if not name:
            return ""
        resolved = _resolve_item_name(name, known)
        if resolved and resolved != name:
            notes.append(f"{role} '{name}' matched to the existing item '{resolved}'")
            return resolved
        if resolved:
            return resolved
        _add_item(name, {"kind": "material", "value": max(6, record["level"] * 3),
                         "desc": "a crafting component"})
        known.append(name)
        notes.append(f"created the missing item '{name}' so this recipe can be crafted")
        return name

    ingredients = []
    for row in record.get("ingredients") or []:
        if not isinstance(row, dict):
            continue
        name = fix(row.get("item"), "ingredient")
        if not name:
            continue
        qty = row.get("qty")
        ingredients.append({"item": name,
                            "qty": int(min(99, max(1, qty))) if isinstance(qty, (int, float)) else 1})
    if not ingredients and known:
        ingredients = [{"item": known[0], "qty": 1}]
    record["ingredients"] = ingredients

    result = record.get("result") if isinstance(record.get("result"), dict) else {}
    name = fix(result.get("item"), "result")
    qty = result.get("qty")
    record["result"] = {"item": name,
                        "qty": int(min(9, max(1, qty))) if isinstance(qty, (int, float)) else 1}
    return record


def repair_record(kind: str, record):
    """Correct what can be corrected, and report every change in plain English."""
    if not isinstance(record, dict):
        return record, []
    record = json.loads(json.dumps(record))
    notes: list[str] = []
    if kind == "monster":
        record = _repair_monster(record, notes)
    elif kind == "move":
        repaired = _repair_move(record, notes, "move")
        if repaired:
            record = repaired
    elif kind == "recipe":
        record = _repair_recipe(record, notes)
    elif kind == "crop":
        ensure_crop_items(record, notes)
    return record, notes


# --- validation -------------------------------------------------------------
def check(kind: str, record) -> dict:
    rep = V.Report()
    if is_item_kind(kind):
        # A Forge item library is a name -> record map. Templates may also
        # carry `_note` strings, so do not mistake those harmless annotations
        # for a malformed bare item record.
        library = ({str(name): spec for name, spec in record.items()
                    if not str(name).startswith("_") and isinstance(spec, dict)}
                   if isinstance(record, dict) else {})
        bare_item_keys = {"name", "kind", "value", "buy", "desc", "use", "stats", "skill_tree"}
        if library and isinstance(record, dict) and not (set(record) & bare_item_keys):
            for name, spec in library.items():
                V.check_item(spec, rep, name)
        else:
            V.check_item(record if isinstance(record, dict) else {}, rep)
    else:
        fn = {"monster": V.check_monster, "quest": V.check_quest,
              "story": V.check_story, "recipe": V.check_recipe,
              "area": V.check_area, "crop": V.check_crop, "move": V.check_move,
              "starter": V.check_starter}[kind]
        fn(record if isinstance(record, dict) else {}, rep)
    return {"errors": rep.errors, "warnings": rep.warnings, "ok": not rep.errors}


def linked_content_errors(kind: str, record: dict) -> list[str]:
    """Recipe and crop names are real inventory references, never free text."""
    if kind not in ("recipe", "crop") or not isinstance(record, dict):
        return []
    known = {str(name) for name in _items() if not str(name).startswith("_")}
    if not known:
        return ["create Item records before linking a recipe or crop"]
    if kind == "recipe":
        names = [str(row.get("item") or "") for row in record.get("ingredients") or []]
        names.append(str((record.get("result") or {}).get("item") or ""))
    else:
        names = [str(record.get("seed") or ""), str(record.get("item") or "")]
    missing = [name for name in names if name and name not in known]
    return (["unknown item reference: " + ", ".join(dict.fromkeys(missing))]
            if missing else [])


def unwrap(kind: str, blob):
    """Accept a bare record, a list, or the wrapper shapes the game writes."""
    if isinstance(blob, list):
        return blob
    if isinstance(blob, dict):
        for key in ("monsters", "moves", "quests", "chapters", "items", "recipes"):
            if key in blob and isinstance(blob[key], list):
                return blob[key]
        if kind == "item":
            return [blob]
        return [blob]
    return []


# --- writing ----------------------------------------------------------------
def save_records(kind: str, records: list, filename: str) -> dict:
    spec = KINDS[kind]
    os.makedirs(spec["dest"], exist_ok=True)
    # The last gate before data reaches disk and the bestiary.  Records that
    # came from /api/generate were repaired already and pass through unchanged,
    # but a hand-edited or imported one has never been through the pass — and
    # this is the only place both routes meet.
    records = [repair_record(kind, record)[0] if isinstance(record, dict) else record
               for record in records]
    stem = "".join(c for c in (filename or "forged") if c.isalnum() or c in "-_")
    stem = stem or "forged"

    if kind == "monster":
        path = os.path.join(spec["dest"], stem + ".jsonl")
        seen = {t.id for t in bestiary().all}      # never collide with anything loaded
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        try:
                            seen.add(json.loads(line).get("id"))
                        except json.JSONDecodeError:
                            pass
        written = 0
        with open(path, "a", encoding="utf-8") as fh:
            for rec in records:
                if not rec.get("id") or rec.get("id") in seen:
                    rec["id"] = next_monster_id_from(seen)
                    # A reassigned id is a different creature in the library,
                    # so it deserves a fresh visual identity too.
                    rec.pop("portrait_seed", None)
                seen.add(rec.get("id"))
                apply_portrait_seed(rec)
                write_visual_assets("monster", rec)
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written += 1
        return {"path": rel(path), "written": written}

    if kind == "quest":
        path = os.path.join(spec["dest"], stem + ".json")
        existing = []
        if os.path.isfile(path):
            try:
                blob = json.load(open(path, encoding="utf-8"))
                existing = blob.get("quests", blob) if isinstance(blob, dict) else blob
            except Exception:
                existing = []
        existing = [q for q in existing if isinstance(q, dict)] + records
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"quests": existing}, fh, indent=2, ensure_ascii=False)
        return {"path": rel(path), "written": len(records)}

    if is_item_kind(kind):
        path = os.path.join(DATA, "items.json")
        blob = _items()
        stamp = ITEM_FAMILY[kind]
        added = 0
        for rec in records:
            for name, body in rec.items():
                if str(name).startswith("_") or not isinstance(body, dict):
                    continue
                if stamp is not None:
                    body["kind"] = stamp
                blob[name] = body
                write_visual_assets(kind, {"name": name, **body})
                added += 1
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(blob, fh, indent=2, ensure_ascii=False)
        return {"path": rel(path), "written": added}

    if kind == "move":
        path = os.path.join(DATA, "moves.json")
        existing = _moves()
        used = {str(row.get("id") or "") for row in existing}
        added = 0
        for rec in records:
            if not rec.get("id") or rec["id"] in used:
                rec["id"] = next_move_id(existing)
            used.add(str(rec["id"]))
            existing.append(rec)
            added += 1
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"moves": existing}, fh, indent=2, ensure_ascii=False)
        return {"path": rel(path), "written": added}

    if kind == "crop":
        path = os.path.join(DATA, "farm.json")
        blob = {}
        if os.path.isfile(path):
            try:
                blob = json.load(open(path, encoding="utf-8")) or {}
            except Exception:
                blob = {}
        existing = [c for c in (blob.get("crops") or []) if isinstance(c, dict)]
        used = {str(c.get("id") or "") for c in existing}
        added = 0
        for rec in records:
            base = str(rec.get("id") or "crop") or "crop"
            candidate, n = base, 2
            while candidate in used:
                candidate, n = f"{base}_{n}", n + 1
            rec["id"] = candidate
            used.add(candidate)
            # The seed, the produce and the four growth sprites are the crop.
            # Writing the record without them leaves a plot you cannot plant.
            ensure_crop_items(rec, [])
            write_visual_assets("crop", rec)
            existing.append(rec)
            added += 1
        blob["crops"] = existing
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(blob, fh, indent=2, ensure_ascii=False)
        return {"path": rel(path), "written": added}

    if kind == "recipe":
        path = os.path.join(spec["dest"], stem + ".json")
        existing = []
        if os.path.isfile(path):
            try:
                blob = json.load(open(path, encoding="utf-8"))
                existing = blob.get("recipes", blob) if isinstance(blob, dict) else blob
            except Exception:
                existing = []
        existing = [x for x in existing if isinstance(x, dict)] + records
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"recipes": existing}, fh, indent=2, ensure_ascii=False)
        return {"path": rel(path), "written": len(records)}

    path = os.path.join(DATA, "story.json")
    try:
        blob = json.load(open(path, encoding="utf-8"))
    except Exception:
        blob = {"chapters": []}
    chapters = blob.get("chapters", blob if isinstance(blob, list) else [])
    used = {c.get("id") for c in chapters if isinstance(c, dict)}
    for rec in records:
        while rec.get("id") in used:
            rec["id"] = int(rec.get("id", 0)) + 1
        used.add(rec.get("id"))
        chapters.append(rec)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"chapters": chapters}, fh, indent=2, ensure_ascii=False)
    return {"path": rel(path), "written": len(records)}


def next_monster_id_from(seen: set) -> str:
    n = 1
    while f"mon_{n:04d}" in seen:
        n += 1
    return f"mon_{n:04d}"


def rel(path: str) -> str:
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:
        return path


def export(kind: str) -> str:
    """Everything the game currently has, in the format it reads back in."""
    if kind == "monster":
        rows = []
        for pattern in (os.path.join(DATA, "monsters", "*.jsonl"),
                        os.path.join(DATA, "monsters", "*.json")):
            for path in sorted(glob.glob(pattern)):
                try:
                    if path.endswith(".jsonl"):
                        rows += [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
                    else:
                        blob = json.load(open(path, encoding="utf-8"))
                        rows += blob.get("monsters", blob) if isinstance(blob, dict) else blob
                except Exception:
                    continue
        for path in (os.path.join(os.path.dirname(ROOT), "output", "monsters.jsonl"),):
            if os.path.isfile(path):
                rows += [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    if kind == "item":
        return json.dumps(_items(), indent=2, ensure_ascii=False)
    if kind == "quest":
        out = []
        for path in [os.path.join(DATA, "quests.json")] + sorted(
                glob.glob(os.path.join(DATA, "quests", "*.json"))):
            if not os.path.isfile(path):
                continue
            try:
                blob = json.load(open(path, encoding="utf-8"))
                out += blob.get("quests", blob) if isinstance(blob, dict) else blob
            except Exception:
                continue
        return json.dumps({"quests": out}, indent=2, ensure_ascii=False)
    if kind == "recipe":
        out = []
        for path in sorted(glob.glob(os.path.join(DATA, "recipes", "*.json"))):
            try:
                blob = json.load(open(path, encoding="utf-8"))
                out += blob.get("recipes", blob) if isinstance(blob, dict) else blob
            except Exception:
                continue
        return json.dumps({"recipes": out}, indent=2, ensure_ascii=False)
    if kind == "move":
        return json.dumps({"moves": _moves()}, indent=2, ensure_ascii=False)
    return read(os.path.join(DATA, "story.json"))


# --- content manager --------------------------------------------------------
# The Forge's content desk is the source of truth for a blank project. It can
# manage every player-facing record without asking someone to discover a file
# format first. Areas are deliberately separate from monsters: an area owns an
# exact list of monster IDs, which is what the Void Atlas spawns.

CONTENT = {
    "monster": {"label": "Monster", "wrapper": "monsters", "title": "name",
                "template": "monster.json", "custom": os.path.join(DATA, "monsters", "custom.jsonl")},
    "area": {"label": "Void Area", "wrapper": "areas", "title": "name",
             "template": "area.json", "custom": os.path.join(DATA, "areas.json")},
    "quest": {"label": "Quest", "wrapper": "quests", "title": "title",
              "template": "quest.json", "custom": os.path.join(DATA, "quests", "custom.json")},
    "item": {"label": "Item", "wrapper": None, "title": "name",
             "template": "item.json", "custom": os.path.join(DATA, "items.json")},
    "recipe": {"label": "Recipe", "wrapper": "recipes", "title": "name",
               "template": "recipe.json", "custom": os.path.join(DATA, "recipes", "custom.json")},
    "crop": {"label": "Farm Crop", "wrapper": "crops", "title": "label",
             "template": "crop.json", "custom": os.path.join(DATA, "farm.json")},
    "move": {"label": "Move", "wrapper": "moves", "title": "name",
             "template": "move.json", "custom": os.path.join(DATA, "moves.json")},
    "starter": {"label": "Starter Choices", "wrapper": None, "title": "label",
                "template": "starter.json", "custom": os.path.join(DATA, "starters.json"),
                "single": True},
    "material": {"label": "Material", "wrapper": None, "title": "name",
                 "template": "item.json", "custom": os.path.join(DATA, "items.json")},
    "weapon": {"label": "Weapon", "wrapper": None, "title": "name",
               "template": "item.json", "custom": os.path.join(DATA, "items.json")},
    "armor": {"label": "Armour", "wrapper": None, "title": "name",
              "template": "item.json", "custom": os.path.join(DATA, "items.json")},
    "seed": {"label": "Seed", "wrapper": None, "title": "name",
             "template": "item.json", "custom": os.path.join(DATA, "items.json")},
}
CONTENT_KINDS = set(CONTENT)


def _content_patterns(kind: str) -> list:
    if kind == "monster":
        return [os.path.join(DATA, "monsters", "*.jsonl"), os.path.join(DATA, "monsters", "*.json")]
    if kind == "quest":
        return [os.path.join(DATA, "quests.json"), os.path.join(DATA, "quests", "*.json")]
    if kind == "recipe":
        return [os.path.join(DATA, "recipes.json"), os.path.join(DATA, "recipes", "*.json")]
    if is_item_kind(kind):
        return [os.path.join(DATA, "items.json")]
    names = {"area": "areas.json", "crop": "farm.json",
             "move": "moves.json", "starter": "starters.json"}
    return [os.path.join(DATA, names[kind])]


def _content_rows(kind: str, path: str) -> list:
    """Read records in the shape the desk edits (one item is one record)."""
    try:
        if path.endswith(".jsonl"):
            with open(path, encoding="utf-8") as fh:
                return [json.loads(line) for line in fh if line.strip()]
        with open(path, encoding="utf-8") as fh:
            blob = json.load(fh)
        if is_item_kind(kind):
            if not isinstance(blob, dict):
                return []
            wanted = ITEM_FAMILY[kind]
            return [{"name": str(name), **spec} for name, spec in blob.items()
                    if not str(name).startswith("_") and isinstance(spec, dict)
                    and (wanted is None or str(spec.get("kind") or "") == wanted)]
        if kind == "starter":
            return [blob] if isinstance(blob, dict) else []
        rows = blob.get(CONTENT[kind]["wrapper"], []) if isinstance(blob, dict) else blob
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    except Exception:
        return []


def _content_path(kind: str, source: str) -> str:
    if kind not in CONTENT_KINDS:
        raise ValueError("pick a content type from the Forge")
    path = os.path.realpath(os.path.join(ROOT, str(source or "")))
    allowed = set()
    for pattern in _content_patterns(kind):
        for candidate in glob.glob(pattern):
            allowed.add(os.path.realpath(candidate))
    if path not in allowed:
        raise ValueError("that source is not a Forge-managed %s file" % CONTENT[kind]["label"].lower())
    if not path.endswith((".json", ".jsonl")) or not os.path.isfile(path):
        raise ValueError("that content source does not exist")
    return path


def _write_content_rows(kind: str, path: str, rows: list) -> None:
    clean = [row for row in rows if isinstance(row, dict)]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        if path.endswith(".jsonl"):
            for row in clean:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        elif is_item_kind(kind):
            # A typed desk owns only its own slice of items.json.  Everything it
            # does not manage is read back and rewritten untouched, so saving a
            # material can never delete the consumables.
            wanted = ITEM_FAMILY[kind]
            out = {}
            if wanted is not None:
                try:
                    with open(path, encoding="utf-8") as existing:
                        blob = json.load(existing)
                except Exception:
                    blob = {}
                if isinstance(blob, dict):
                    out = {name: spec for name, spec in blob.items()
                           if str(name).startswith("_") or not isinstance(spec, dict)
                           or str(spec.get("kind") or "") != wanted}
            for row in clean:
                name = str(row.get("name") or "").strip()
                if name:
                    body = {key: value for key, value in row.items() if key != "name"}
                    if wanted is not None:
                        body["kind"] = wanted
                    out[name] = body
            json.dump(out, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        elif kind == "starter":
            json.dump(clean[0] if clean else {"label": "First Companions", "monster_ids": []},
                      fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        else:
            json.dump({CONTENT[kind]["wrapper"]: clean}, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    os.replace(tmp, path)


def _content_name(kind: str, record: dict) -> str:
    return str(record.get(CONTENT[kind]["title"]) or "Untitled")


def _content_key(kind: str, record: dict, index: int) -> str:
    if is_item_kind(kind):
        return str(record.get("name") or index)
    return str(index)


def content_list(kind: str) -> list:
    if kind not in CONTENT_KINDS:
        raise ValueError("pick a content type from the Forge")
    paths, seen_paths, out = [], set(), []
    for pattern in _content_patterns(kind):
        paths.extend(sorted(glob.glob(pattern)))
    for raw in paths:
        path = os.path.realpath(raw)
        if path in seen_paths:
            continue
        seen_paths.add(path)
        for index, record in enumerate(_content_rows(kind, path)):
            out.append({"source": rel(path), "index": _content_key(kind, record, index),
                        "record": record, "name": _content_name(kind, record), "protected": False})
    return out


def _content_validate(kind: str, record: dict) -> None:
    if is_item_kind(kind) and not str(record.get("name") or "").strip():
        raise ValueError("an item needs a name")
    checked = {record["name"]: {key: value for key, value in record.items() if key != "name"}} \
        if is_item_kind(kind) and record.get("name") else record
    report = check(kind, checked)
    errors = report["errors"] + linked_content_errors(kind, record)
    if errors:
        raise ValueError("; ".join(errors[:5]))
    if kind == "area":
        known = {t.id for t in bestiary().all}
        assigned = list(record.get("monster_ids", [])) + list(record.get("boss_ids", []))
        missing = [x for x in assigned if x not in known]
        if missing:
            raise ValueError("unknown monster id: " + ", ".join(missing[:4]))
    if kind == "starter":
        known = {t.id: t for t in bestiary().all}
        missing = [ident for ident in record.get("monster_ids", []) if ident not in known]
        bosses = [ident for ident in record.get("monster_ids", [])
                  if ident in known and known[ident].is_boss]
        if missing:
            raise ValueError("unknown starter monster id: " + ", ".join(missing[:4]))
        if bosses:
            raise ValueError("bosses cannot be starter choices: " + ", ".join(bosses[:4]))
    if kind == "quest":
        area_id = str(record.get("area_id") or "").strip().lower()
        if not area_id:
            raise ValueError("a mission needs a Void Area for its operation")
        known = {str(row["record"].get("id") or "").lower()
                 for row in content_list("area")}
        if area_id not in known:
            raise ValueError("unknown Void Area id: " + area_id)


def _content_index(kind: str, rows: list, value) -> int:
    if is_item_kind(kind):
        return next((i for i, row in enumerate(rows) if row.get("name") == str(value)), -1)
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _record_reply(kind: str, path: str, index: int, record: dict) -> dict:
    return {"source": rel(path), "index": _content_key(kind, record, index), "record": record,
            "name": _content_name(kind, record), "protected": False}


def content_create(kind: str, record: dict) -> dict:
    if kind not in CONTENT_KINDS or not isinstance(record, dict):
        raise ValueError("choose a valid content record")
    record = json.loads(json.dumps(record))
    record, _repairs = repair_record(kind, record)
    if kind == "monster":
        used = {t.id for t in bestiary().all}
        if not record.get("id") or record["id"] in used:
            record["id"] = next_monster_id_from(used)
        apply_portrait_seed(record)
    if kind == "move":
        move_rows = content_list("move")
        used = {str((row.get("record") or {}).get("id") or "") for row in move_rows}
        if not record.get("id") or record["id"] in used:
            record["id"] = next_move_id([row["record"] for row in move_rows])
    _content_validate(kind, record)
    path = CONTENT[kind]["custom"]
    rows = _content_rows(kind, path) if os.path.isfile(path) else []
    if is_item_kind(kind) and any(row.get("name") == record.get("name") for row in rows):
        raise ValueError("an item with that name already exists")
    if kind in ("area", "crop", "recipe", "move") and any(row.get("id") == record.get("id") for row in rows):
        raise ValueError("that id already exists")
    if kind == "starter":
        rows = [record]
        _write_content_rows(kind, path, rows)
        return _record_reply(kind, path, 0, record)
    rows.append(record)
    _write_content_rows(kind, path, rows)
    write_visual_assets(kind, record)
    return _record_reply(kind, path, len(rows) - 1, record)


def content_update(kind: str, source: str, index, record: dict) -> dict:
    path = _content_path(kind, source)
    if not isinstance(record, dict):
        raise ValueError("the record must be a JSON object")
    rows = _content_rows(kind, path)
    at = _content_index(kind, rows, index)
    if at < 0 or at >= len(rows):
        raise ValueError("that record no longer exists — refresh the manager")
    record = json.loads(json.dumps(record))
    record, _repairs = repair_record(kind, record)
    if kind == "monster":
        old_id = str(rows[at].get("id") or "")
        others = {t.id for t in bestiary().all if t.id != rows[at].get("id")}
        if not record.get("id"):
            record["id"] = rows[at].get("id") or next_monster_id_from(others)
        if record["id"] in others:
            raise ValueError(f"monster id {record['id']} is already in use")
        if old_id and record["id"] != old_id:
            places = [area["name"] for area in content_list("area")
                      if old_id in (area["record"].get("monster_ids") or [])
                      or old_id in (area["record"].get("boss_ids") or [])]
            if places:
                raise ValueError("remove this monster from Void Area(s) before changing its id: " +
                                 ", ".join(places[:4]))
            starters = _content_rows("starter", os.path.join(DATA, "starters.json"))
            if starters and old_id in (starters[0].get("monster_ids") or []):
                raise ValueError("remove this monster from Starter Choices before changing its id")
        apply_portrait_seed(record)
    if kind in ("area", "crop", "recipe", "move"):
        ident = str(record.get("id") or "")
        if any(i != at and str(row.get("id") or "") == ident for i, row in enumerate(rows)):
            raise ValueError(f"{kind} id {ident!r} is already in use")
    _content_validate(kind, record)
    rows[at] = record
    _write_content_rows(kind, path, rows)
    write_visual_assets(kind, record)
    return _record_reply(kind, path, at, record)


def content_delete(kind: str, source: str, index) -> None:
    path = _content_path(kind, source)
    rows = _content_rows(kind, path)
    at = _content_index(kind, rows, index)
    if at < 0 or at >= len(rows):
        raise ValueError("that record no longer exists — refresh the manager")
    if kind == "starter":
        raise ValueError("the starter choice record is always present; edit its three entries instead")
    if kind == "monster":
        monster_id = str(rows[at].get("id") or "")
        places = [area["name"] for area in content_list("area")
                  if monster_id in (area["record"].get("monster_ids") or [])
                  or monster_id in (area["record"].get("boss_ids") or [])]
        if places:
            raise ValueError("remove this monster from Void Area(s) first: " +
                             ", ".join(places[:4]))
        starters = _content_rows("starter", os.path.join(DATA, "starters.json"))
        if starters and monster_id in (starters[0].get("monster_ids") or []):
            raise ValueError("remove this monster from Starter Choices first")
    del rows[at]
    _write_content_rows(kind, path, rows)


def content_copy(kind: str, source: str, index) -> dict:
    path = _content_path(kind, source)
    rows = _content_rows(kind, path)
    at = _content_index(kind, rows, index)
    if at < 0 or at >= len(rows):
        raise ValueError("that record no longer exists — refresh the manager")
    record = json.loads(json.dumps(rows[at]))
    if kind == "monster":
        record["id"], record["name"] = next_monster_id(), f"{_content_name(kind, record)} Copy"
        record.pop("portrait_seed", None)
    elif kind in ("area", "crop", "recipe", "move"):
        record["id"] = f"{record.get('id', kind)}_copy"
        record[CONTENT[kind]["title"]] = f"{_content_name(kind, record)} Copy"
    else:
        record[CONTENT[kind]["title"]] = f"{_content_name(kind, record)} Copy"
    return content_create(kind, record)


# --- the server -------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "voidcaller-forge"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _file(self, relpath):
        path = os.path.normpath(os.path.join(WEB, relpath.lstrip("/")))
        if not path.startswith(WEB) or not os.path.isfile(path):
            self._send(404, b"not found", "text/plain")
            return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        self._send(200, open(path, "rb").read(), ctype)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        path, _, query = self.path.partition("?")
        args = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
        if path in ("/", "/index.html"):
            self._file("index.html")
        elif path == "/api/setup":
            with LOCK:
                self._json({"kinds": [{"key": k, **{kk: vv for kk, vv in v.items()
                                                    if kk in ("label", "note")}}
                                      for k, v in KINDS.items()],
                            "ollama": ollama_models(
                                urllib.parse.unquote(args.get("endpoint") or "") or OLLAMA),
                            "library": library(),
                            "next_id": next_monster_id()})
        elif path == "/api/models":
            self._json(ollama_models(urllib.parse.unquote(args.get("endpoint") or OLLAMA)))
        elif path == "/api/template":
            kind = args.get("kind", "monster")
            filename = (CONTENT.get(kind) or KINDS.get(kind, KINDS["monster"])).get("template")
            self._send(200, read(os.path.join(TEMPLATES, filename)).encode("utf-8"),
                       "text/plain; charset=utf-8")
        elif path == "/api/export":
            kind = args.get("kind", "monster")
            self._send(200, export(kind).encode("utf-8"), "text/plain; charset=utf-8")
        elif path == "/api/reload":
            with LOCK:
                bestiary(reload=True)
            self._json({"species": len(bestiary().all)})
        elif path == "/api/content":
            kind = args.get("kind", "monster")
            with LOCK:
                try:
                    self._json({"kind": kind, "records": content_list(kind)})
                except ValueError as exc:
                    self._json({"error": str(exc)}, 400)
        else:
            self._file(path)

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._body()
        if path == "/api/plan":
            plan = plan_batch(body.get("ask") or {})
            self._json({"plan": plan, "count": len(plan)})
            return
        if path == "/api/gaps":
            self._json(gap_plan(int(body.get("count") or 20)))
            return
        if path == "/api/prompt":
            system, user = build_prompt(body.get("kind", "monster"), body.get("ask") or {})
            self._json({"system": system, "user": user})
            return
        if path == "/api/generate":
            self._generate(body)
            return
        if path == "/api/validate":
            kind = body.get("kind", "monster")
            out = []
            for rec in unwrap(kind, body.get("records")):
                out.append({"record": rec, **check(kind, rec)})
            self._json({"results": out})
            return
        if path == "/api/save":
            kind = body.get("kind", "monster")
            records = [r for r in (body.get("records") or []) if isinstance(r, (dict, list))]
            if not records:
                self._json({"error": "nothing to save"}, 400)
                return
            with LOCK:
                try:
                    result = save_records(kind, records, body.get("filename", "forged"))
                    bestiary(reload=True)
                    result["species"] = len(bestiary().all)
                except Exception as exc:
                    self._json({"error": str(exc)}, 500)
                    return
            self._json(result)
            return
        if path in ("/api/content/create", "/api/content/update",
                    "/api/content/delete", "/api/content/copy"):
            kind = body.get("kind", "monster")
            try:
                with LOCK:
                    if path == "/api/content/create":
                        result = content_create(kind, body.get("record"))
                    elif path == "/api/content/update":
                        result = content_update(kind, body.get("source"), body.get("index"),
                                                body.get("record"))
                    elif path == "/api/content/delete":
                        content_delete(kind, body.get("source"), body.get("index"))
                        result = {"deleted": True}
                    else:
                        result = content_copy(kind, body.get("source"), body.get("index"))
                    bestiary(reload=True)
                    result["species"] = len(bestiary().all)
            except (ValueError, TypeError) as exc:
                self._json({"error": str(exc)}, 400)
                return
            except Exception as exc:
                self._json({"error": str(exc)}, 500)
                return
            self._json(result)
            return
        self._send(404, b"not found", "text/plain")

    def _generate(self, body: dict):
        kind = body.get("kind", "monster")
        endpoint = body.get("endpoint") or OLLAMA
        model = body.get("model") or ""
        if not model:
            self._json({"error": "pick a model first"}, 400)
            return
        ask = body.get("ask") or {}
        if isinstance(ask, dict) and body.get("seen_names"):
            ask = {**ask, "_seen": list(body.get("seen_names") or [])}
        try:
            system, user = build_prompt(kind, ask)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
            return
        schema = None
        if body.get("strict", True):
            try:
                with open(os.path.join(SCHEMAS, KINDS[kind]["schema"]), encoding="utf-8") as fh:
                    schema = json.load(fh)
            except Exception:
                schema = None
        try:
            blob = ollama_generate(endpoint, model, system, user,
                                   float(body.get("temperature", 0.9)),
                                   schema=schema)
        except urllib.error.URLError as exc:
            self._json({"error": f"could not reach Ollama at {endpoint}: {exc}"}, 502)
            return
        except Exception as exc:
            self._json({"error": str(exc)}, 502)
            return
        # A reasoning model may leave `response` empty and put everything in
        # `thinking`. Take whichever one actually carries the record.
        raw = (blob.get("response") or "").strip() or (blob.get("thinking") or "").strip()
        try:
            record = coerce_json(raw)
        except Exception as exc:
            self._json({"error": f"the model did not return JSON: {exc}", "raw": raw[:2000]}, 200)
            return
        if kind == "monster" and not record.get("id"):
            record["id"] = ask.get("id") or next_monster_id()
        if kind == "move" and not record.get("id"):
            record["id"] = ask.get("id") or next_move_id()
        if kind == "quest" and ask.get("area_id"):
            record["area_id"] = str(ask["area_id"])
        record, repairs = repair_record(kind, record)
        if kind == "monster":
            record.setdefault("_source", f"ollama:{model}")
            apply_portrait_seed(record)
        dupe = ""
        if kind == "monster":
            dupe = duplicate_of(record, body.get("seen_names") or [],
                                [tuple(x) for x in (body.get("seen_prints") or [])])
        self._json({"record": record, **check(kind, record), "duplicate": dupe,
                    "repairs": repairs,
                    "fingerprint": list(fingerprint(record)) if kind == "monster" else [],
                    "format": blob.get("_format", "json"),
                    "took": round((blob.get("total_duration") or 0) / 1e9, 1)})


def main():
    global OLLAMA
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8778)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--ollama", default=OLLAMA)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    OLLAMA = args.ollama

    b = bestiary()
    tags = ollama_models(OLLAMA)
    if not b.all:
        # A blank project is the intended first-run state.  The Forge is how
        # it becomes a game, so do not present this as a broken installation.
        print("\n  This is a blank Forge-first project.")
        print("  Create a Monster, then a Void Area and assign that monster to it.")
        print("  Add missions, items, recipes, and farm crops when you need them.\n")
    print(f"\n  THE FORGE  ·  {len(b.all)} species already loaded")
    if tags["ok"]:
        print(f"  ollama at {OLLAMA} — {len(tags['models'])} model"
              f"{'' if len(tags['models']) == 1 else 's'}: "
              + ", ".join(m["name"] for m in tags["models"][:6]))
    else:
        print(f"  ollama is not answering at {OLLAMA}.")
        print("  Start it with `ollama serve`, or write content by hand in the forge.")
    url = f"http://{args.host}:{args.port}/"
    print(f"  forging at  {url}\n  ctrl-c to stop\n")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n  the fire goes out.")


if __name__ == "__main__":
    main()
