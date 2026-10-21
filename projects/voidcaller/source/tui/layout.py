"""Player-owned terminal layout preferences.

These settings affect only presentation. They are separate from colour themes,
so any layout can be combined with any terminal palette.
"""
from __future__ import annotations

import json
import os


GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_FILE = os.path.join(GAME, "saves", "layout.json")

PRESETS = {
    "cinematic": {"label": "Cinematic Hunt", "main_width": 91,
                  "note": "maximum room for raid maps and creature sheets"},
    "balanced": {"label": "Balanced", "main_width": 78,
                 "note": "map and pack given equal attention"},
    "wide": {"label": "Wide main pane", "main_width": 86,
                "note": "more room for maps, cards, and battle detail"},
    "pack": {"label": "Pack-focused", "main_width": 68,
                "note": "a larger right rail for the active party"},
    "command": {"label": "Command Deck", "main_width": 70,
                "note": "compact main view with a readable party and mission rail"},
}

_current: dict | None = None


def current() -> dict:
    global _current
    if _current is None:
        _current = load()
    return _current


def load() -> dict:
    try:
        with open(USER_FILE, encoding="utf-8") as fh:
            saved = json.load(fh)
        name = saved.get("name")
        if name in PRESETS:
            return {"name": name, **PRESETS[name]}
    except Exception:
        pass
    return {"name": "balanced", **PRESETS["balanced"]}


def use(name: str) -> dict | None:
    global _current
    if name not in PRESETS:
        return None
    _current = {"name": name, **PRESETS[name]}
    save()
    return _current


def save() -> None:
    os.makedirs(os.path.dirname(USER_FILE), exist_ok=True)
    with open(USER_FILE, "w", encoding="utf-8") as fh:
        json.dump({"name": current()["name"]}, fh, indent=2)
