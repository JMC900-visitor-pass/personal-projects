"""The editable central twelve-Type chart.

Type effectiveness is one global matrix.  A species contributes one or two
defending Types; it never carries a private affinity table or absorption rule.
"""
from __future__ import annotations

import json
import os

from .data import GAME_DIR
from .model import COMBAT_TYPES, canonical_type


_PATH = os.path.join(GAME_DIR, "data", "types.json")
_CACHE: dict | None = None

# A balanced starter chart used when the editable file is absent or malformed.
# It is generated from two strong relationships per Type; reverse relations are
# hard resistances.  Every resolved cell is exactly 0.5, 1.0, or 1.5.
_ADVANTAGES = {
    "Fire": ("Nature", "Primal"), "Water": ("Fire", "Earth"),
    "Electric": ("Water", "Wind"), "Nature": ("Water", "Earth"),
    "Earth": ("Electric", "Fire"), "Wind": ("Nature", "Primal"),
    "Light": ("Dark", "Spirit"), "Dark": ("Light", "Cosmic"),
    "Cosmic": ("Spirit", "Arcane"), "Spirit": ("Dark", "Primal"),
    "Primal": ("Cosmic", "Arcane"), "Arcane": ("Light", "Wind"),
}


def _default_chart() -> dict[str, dict[str, float]]:
    chart = {attack: {defence: 1.0 for defence in COMBAT_TYPES} for attack in COMBAT_TYPES}
    for attack, targets in _ADVANTAGES.items():
        for defence in targets:
            chart[attack][defence] = 1.5
            if chart[defence][attack] == 1.0:
                chart[defence][attack] = 0.5
    return chart


def _clean_chart(raw: object) -> dict[str, dict[str, float]]:
    chart = _default_chart()
    if not isinstance(raw, dict):
        return chart
    for attack, row in raw.items():
        attack = canonical_type(attack)
        if attack is None or not isinstance(row, dict):
            continue
        for defence, value in row.items():
            defence = canonical_type(defence)
            if defence is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number in {0.0, 0.5, 1.0, 1.5}:
                chart[attack][defence] = number
    return chart


def config() -> dict:
    global _CACHE
    if _CACHE is None:
        raw = {}
        try:
            with open(_PATH, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass
        _CACHE = {"version": 2, "types": list(COMBAT_TYPES),
                  "chart": _clean_chart(raw.get("chart") if isinstance(raw, dict) else raw)}
    return _CACHE


def reload() -> None:
    global _CACHE
    _CACHE = None


def chart_value(attacker_type: object, defender_type: object) -> float:
    attack = canonical_type(attacker_type)
    defence = canonical_type(defender_type)
    if attack is None or defence is None:
        return 1.0
    return float(config()["chart"].get(attack, {}).get(defence, 1.0))


def multiplier(attacker_type: object, target) -> float:
    """Return the dual-Type defensive multiplier for a template or combatant."""
    attack = canonical_type(attacker_type)
    if attack is None:
        return 1.0
    template = getattr(target, "template", target)
    types = getattr(template, "types", None)
    if isinstance(types, dict):
        defending = (types.get("primary"), types.get("secondary"))
    else:
        defending = (getattr(template, "primary", None), getattr(template, "secondary", None))
    total = 1.0
    for defence in defending:
        if canonical_type(defence) is not None:
            total *= chart_value(attack, defence)
    return round(total, 2)


def label(mult: float) -> str:
    if mult <= 0:
        return "immune"
    if mult >= 2.0:
        return "overwhelming"
    if mult >= 1.45:
        return "weak"
    if mult >= 1.05:
        return "vulnerable"
    if mult <= 0.3:
        return "resists hard"
    if mult <= 0.55:
        return "resists"
    if mult < 0.95:
        return "mixed"
    return "neutral"


def profile(target) -> dict:
    """Every attacking Type against this target, for Codex and Forge cards."""
    return {combat_type: {
        "mult": multiplier(combat_type, target),
        "label": label(multiplier(combat_type, target)),
    } for combat_type in COMBAT_TYPES}


def weaknesses(target, floor: float = 1.15) -> list[tuple[str, float]]:
    return sorted(((name, row["mult"]) for name, row in profile(target).items()
                   if row["mult"] >= floor), key=lambda row: -row[1])


def resistances(target, ceiling: float = 0.9) -> list[tuple[str, float]]:
    return sorted(((name, row["mult"]) for name, row in profile(target).items()
                   if row["mult"] <= ceiling), key=lambda row: row[1])
