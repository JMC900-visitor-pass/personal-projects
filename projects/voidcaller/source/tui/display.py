"""Persistent window presentation settings (separate from game saves)."""
from __future__ import annotations

import json
import os

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(GAME_DIR, "saves", "display.json")
# These are physical-window multipliers, not game balance presets. A smaller
# step makes it possible to tune the terminal to a laptop display without
# either clipping the bottom of the window or making the letters unusably tiny.
SCALES = (0.60, 0.75, 0.90, 1.0, 1.15, 1.30, 1.50, 1.75, 2.0, 2.50, 3.0)
DEFAULT = {"scale": 1.0, "fullscreen": False, "fit_monitor": True}
_state = None


def load() -> dict:
    global _state
    if _state is None:
        try:
            with open(FILE, encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:
            raw = {}
        scale = float(raw.get("scale", 1.0))
        scale = min(SCALES, key=lambda x: abs(x - scale))
        _state = {"scale": scale, "fullscreen": bool(raw.get("fullscreen", False)),
                  "fit_monitor": bool(raw.get("fit_monitor", DEFAULT["fit_monitor"]))}
    return dict(_state)


def save(state: dict) -> dict:
    global _state
    _state = {**DEFAULT, **state}
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    with open(FILE, "w", encoding="utf-8") as fh:
        json.dump(_state, fh, indent=2)
    return dict(_state)


def cycle_scale() -> dict:
    state = load()
    current = min(SCALES, key=lambda x: abs(x - state["scale"]))
    state["scale"] = SCALES[(SCALES.index(current) + 1) % len(SCALES)]
    state["fit_monitor"] = False
    return save(state)


def toggle(key: str) -> dict:
    state = load()
    state[key] = not bool(state.get(key))
    if key == "fullscreen" and state[key]:
        state["fit_monitor"] = False
    elif key == "fit_monitor" and state[key]:
        state["fullscreen"] = False
    return save(state)
