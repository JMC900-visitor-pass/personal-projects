"""Canonical V2 combat vocabulary.

This module is deliberately small and dependency-free.  Authoring tools,
content readers, the battle engine, and UI all import the same words from
here so a generated record cannot quietly invent a thirteenth combat Type or
bring back a retired permanent stat.
"""
from __future__ import annotations

import re


CORE_STATS = ("hp", "atk", "def", "mag", "res", "spd")
DISPLAY_STATS = ("atk", "def", "mag", "res", "spd")

COMBAT_TYPES = (
    "Fire", "Water", "Electric", "Nature", "Earth", "Wind",
    "Light", "Dark", "Cosmic", "Spirit", "Primal", "Arcane",
)
TYPE_ALIASES = {
    "fire": "Fire", "water": "Water", "lightning": "Electric",
    "electric": "Electric", "nature": "Nature", "earth": "Earth",
    "wind": "Wind", "light": "Light", "dark": "Dark",
    "cosmic": "Cosmic", "spirit": "Spirit", "primal": "Primal",
    "arcane": "Arcane", "ice": "Water",  # ice remains Water flavour in V1
}

RARITIES = ("Common", "Uncommon", "Rare", "Epic")
RARITY_MARKS = {"Common": "○", "Uncommon": "□", "Rare": "★", "Epic": "★★"}
RARITY_BST = {
    "Common": (200, 230),
    "Uncommon": (240, 270),
    "Rare": (280, 310),
    "Epic": (320, 350),
}

ROLES = ("Striker", "Caster", "Tank", "Bruiser", "Support", "Controller", "Swarm")
STATUS_KEYS = (
    "poison", "burn", "sleep", "silence", "blind", "slow", "stone",
    "stun", "confuse", "bleed", "regen", "haste", "shield",
)


def slug(value: object, fallback: str = "record") -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")
    return text or fallback


def canonical_type(value: object, *, allow_none: bool = True) -> str | None:
    """Return one of the twelve supported Type names.

    ``None`` is allowed only for a deliberately untyped/basic move.  It is not
    a thirteenth combat Type and always resolves to neutral damage.
    """
    raw = str(value or "").strip()
    if not raw or raw.casefold() in {"none", "neutral", "physical", "normal", "-"}:
        return None if allow_none else "Primal"
    mapped = TYPE_ALIASES.get(raw.casefold())
    if mapped:
        return mapped
    title = raw.title()
    return title if title in COMBAT_TYPES else (None if allow_none else "Primal")


def canonical_rarity(value: object, *, legacy_level: int = 1) -> str:
    raw = str(value or "").strip().title()
    if raw in RARITIES:
        return raw
    # Legacy records derived rarity from their authored recommended level.  The
    # conversion happens once at read time; rarity is never derived at runtime.
    level = max(1, int(legacy_level or 1))
    if raw == "Legendary":
        return "Epic"
    if level >= 27:
        return "Epic"
    if level >= 17:
        return "Rare"
    if level >= 9:
        return "Uncommon"
    return "Common"


def normalise_base_stats(stats: object, rarity: object) -> tuple[dict, list[str]]:
    """Pull a generated six-stat block into its rarity budget and per-stat bands.

    A language model will not reliably land six integers inside a 31-wide sum
    while also giving the creature a recognisable shape, and rejecting the
    record for missing it throws away good identity over arithmetic the engine
    can do itself.  The generator picks the silhouette; this reshapes it to fit
    the budget, keeping each stat's rank and relative emphasis.

    Returns the corrected block and a list of plain-English notes describing
    what moved, so the Forge can show the author what it changed.
    """
    from . import balance as B

    notes: list[str] = []
    source = stats if isinstance(stats, dict) else {}
    values = {}
    for key in CORE_STATS:
        raw = source.get(key)
        values[key] = float(raw) if isinstance(raw, (int, float)) and raw > 0 else 30.0
        if not isinstance(raw, (int, float)) or raw <= 0:
            notes.append(f"{key} was missing or not a positive number, set to 30")

    tier = str(rarity or "").strip().title()
    low, high = RARITY_BST.get(tier, RARITY_BST["Common"])
    total = sum(values.values())
    if low <= total <= high:
        target = total
    else:
        target = (low + high) / 2.0
        notes.append(f"BST {total:g} rescaled to {target:g} for the {tier or 'Common'} budget")

    if total > 0:
        factor = target / total
        values = {key: value * factor for key, value in values.items()}

    # Clamp into the per-stat bands, then give the slack back to the stats that
    # still have room so the total stays on budget.
    average = target / len(CORE_STATS)
    floor, ceiling = average * B.STAT_BAND_LOW, average * B.STAT_BAND_HIGH
    for _pass in range(8):
        clamped = {key: min(ceiling, max(floor, value)) for key, value in values.items()}
        residual = target - sum(clamped.values())
        if abs(residual) < 1e-6:
            values = clamped
            break
        movable = [key for key, value in clamped.items()
                   if (residual > 0 and value < ceiling - 1e-9)
                   or (residual < 0 and value > floor + 1e-9)]
        if not movable:
            values = clamped
            break
        for key in movable:
            clamped[key] += residual / len(movable)
        values = clamped

    rounded = {key: int(round(value)) for key, value in values.items()}
    # Integer rounding can push the sum a point or two outside the band; walk it
    # back on the stats that have the most headroom.
    guard = 0
    while not low <= sum(rounded.values()) <= high and guard < 64:
        guard += 1
        over = sum(rounded.values()) > high
        pool = [key for key in CORE_STATS
                if (rounded[key] > max(1, int(floor)) if over else rounded[key] < int(ceiling) + 1)]
        if not pool:
            break
        key = (max(pool, key=lambda k: rounded[k]) if over
               else min(pool, key=lambda k: rounded[k]))
        rounded[key] += -1 if over else 1
    for key in CORE_STATS:
        rounded[key] = max(1, rounded[key])

    if isinstance(stats, dict):
        moved = [key for key in CORE_STATS
                 if isinstance(stats.get(key), (int, float)) and int(stats[key]) != rounded[key]]
        if moved and not any("rescaled" in note for note in notes):
            notes.append("stats reshaped into the per-stat bands: " + ", ".join(moved))
    return rounded, notes


def canonical_role(value: object) -> str:
    raw = str(value or "").strip().casefold()
    aliases = {
        "fodder": "Striker", "elite": "Bruiser", "boss": "Bruiser",
        "debuffer": "Controller", "attrition caster": "Caster",
        "healer": "Support", "fighter": "Bruiser",
    }
    candidate = aliases.get(raw, str(value or "").strip().title())
    return candidate if candidate in ROLES else "Bruiser"

