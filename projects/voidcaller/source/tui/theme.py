"""The look of the thing: colours, bar style, and how hard the glass glows.

A theme is a set of *roles*, not a set of colours. "red" means damage and
danger; what shade that is, is the theme's business. Because every pane asks
for roles, one file changes the whole game and nothing has to be repainted by
hand.

    data/themes.json     the presets, and the roles documented
    saves/look.json      whatever you have currently chosen, plus your own hex

Both are plain JSON and both are safe to edit while the game is closed.
"""
from __future__ import annotations

import json
import os

from . import screen as SC

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)
PRESET_FILE = os.path.join(GAME, "data", "themes.json")
USER_FILE = os.path.join(GAME, "saves", "look.json")

# how a bar is drawn: (filled, empty). "hashes" is the default because a hash
# reads as a quantity at any font size, which a solid block does not.
BAR_STYLES = {
    "hashes": ("#", "·"),
    "blocks": ("█", "░"),
    "heavy":  ("▓", "░"),
    "pills":  ("▮", "▯"),
    "ascii":  ("=", "-"),
    "dots":   ("●", "○"),
}

FALLBACK = {
    "name": "folio", "label": "Field Folio", "note": "warm graphite and calm field ink",
    "bloom": 0.0, "scanlines": 0.0, "vignette": 0.10, "crisp": True, "bars": "hashes",
    "colors": dict(zip(SC.PALETTE, ("#%02x%02x%02x" % c for c in SC.PALETTE.values()))),
}

_state: dict = {"current": None, "presets": [], "roles": {}}


# --- reading and writing ----------------------------------------------------
def _hex_to_rgb(value: str) -> tuple:
    v = str(value).strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        raise ValueError(f"not a colour: {value!r}")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, c))) for c in rgb)


def valid_hex(value: str) -> bool:
    try:
        _hex_to_rgb(value)
        return True
    except Exception:
        return False


def swatch(preset_name: str, role: str) -> str:
    """A palette key that always paints in *that* preset's colour.

    The panes can only ask for role names, so every preset's colours are
    registered under their own keys once, and the look screen can then show
    you what a theme is before you put it on.
    """
    return f"sw.{preset_name}.{role}"


def register_swatches() -> None:
    for t in presets():
        for role, value in t.get("colors", {}).items():
            if valid_hex(value):
                SC.PALETTE[swatch(t["name"], role)] = _hex_to_rgb(value)


def presets() -> list:
    if not _state["presets"]:
        try:
            with open(PRESET_FILE, encoding="utf-8") as fh:
                blob = json.load(fh)
            _state["presets"] = blob.get("themes") or [FALLBACK]
            _state["roles"] = blob.get("_roles") or {}
        except Exception:
            _state["presets"] = [FALLBACK]
    return _state["presets"]


def roles() -> dict:
    presets()
    return _state["roles"] or {k: "" for k in SC.PALETTE}


def preset(name: str) -> dict:
    for t in presets():
        if t.get("name") == name:
            out = json.loads(json.dumps(t))      # a copy, never the original
            out.setdefault("crisp", True)
            return out
    out = json.loads(json.dumps(presets()[0]))
    out.setdefault("crisp", True)
    return out


def current() -> dict:
    """The theme in force. Loaded from disk the first time it is asked for."""
    if _state["current"] is None:
        _state["current"] = load()
    return _state["current"]


def load() -> dict:
    """The saved look, or the paper-and-ink table look for a new hunt."""
    base = preset("folio")
    try:
        with open(USER_FILE, encoding="utf-8") as fh:
            saved = json.load(fh)
        base = preset(saved.get("name", "folio"))
        base["name"] = saved.get("name", base["name"])
        for key in ("bloom", "scanlines", "vignette"):
            if key in saved:
                base[key] = float(saved[key])
        if "crisp" in saved:
            base["crisp"] = bool(saved["crisp"])
        if saved.get("bars") in BAR_STYLES:
            base["bars"] = saved["bars"]
        for role, value in (saved.get("colors") or {}).items():
            if role in base["colors"] and valid_hex(value):
                base["colors"][role] = value
        base["custom"] = bool(saved.get("colors"))
    except Exception:
        pass
    return base


def save(theme: dict | None = None) -> None:
    theme = theme or current()
    os.makedirs(os.path.dirname(USER_FILE), exist_ok=True)
    stock = preset(theme.get("name", "folio"))
    changed = {r: v for r, v in theme["colors"].items()
               if stock["colors"].get(r) != v}
    blob = {"name": theme.get("name", "folio"),
            "bloom": round(float(theme.get("bloom", 0.42)), 3),
            "scanlines": round(float(theme.get("scanlines", 0.10)), 3),
            "vignette": round(float(theme.get("vignette", 0.30)), 3),
            "crisp": bool(theme.get("crisp", True)),
            "bars": theme.get("bars", "hashes"),
            "colors": changed}
    with open(USER_FILE, "w", encoding="utf-8") as fh:
        json.dump(blob, fh, indent=2)


# --- putting it on the screen -----------------------------------------------
def apply(theme: dict | None = None, backend=None) -> dict:
    """Push a theme into the palette every pane already draws with.

    PALETTE is mutated rather than replaced, because both backends imported the
    dict itself. The backend is told to throw away its cached glyphs and rebuild
    its effect layers, which is the only reason it needs to know a theme exists.
    """
    theme = theme or current()
    _state["current"] = theme
    register_swatches()
    for role, value in theme.get("colors", {}).items():
        if role in SC.PALETTE and valid_hex(value):
            SC.PALETTE[role] = _hex_to_rgb(value)
    SC.BAR_FULL, SC.BAR_EMPTY = BAR_STYLES.get(theme.get("bars", "hashes"),
                                               BAR_STYLES["hashes"])
    if backend is not None and hasattr(backend, "retheme"):
        backend.retheme(theme)
    return theme


def use(name: str, backend=None) -> dict:
    """Switch to a named preset, dropping any custom colours with it."""
    return apply(preset(name), backend)


def set_color(role: str, value: str, backend=None) -> bool:
    theme = current()
    if role not in SC.PALETTE or not valid_hex(value):
        return False
    theme["colors"][role] = "#" + str(value).strip().lstrip("#").lower()
    apply(theme, backend)
    return True


def set_bars(style: str, backend=None) -> bool:
    if style not in BAR_STYLES:
        return False
    current()["bars"] = style
    apply(current(), backend)
    return True


def toggle_crisp(backend=None) -> bool:
    """Switch between a pixel-sharp terminal and soft CRT lettering."""
    theme = current()
    theme["crisp"] = not bool(theme.get("crisp", True))
    apply(theme, backend)
    return theme["crisp"]


def nudge(key: str, delta: float, backend=None) -> float:
    """Turn the glow, the scanlines or the vignette up and down."""
    theme = current()
    theme[key] = round(max(0.0, min(1.0, float(theme.get(key, 0.0)) + delta)), 2)
    apply(theme, backend)
    return theme[key]
