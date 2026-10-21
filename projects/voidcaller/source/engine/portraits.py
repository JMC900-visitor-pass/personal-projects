"""Deterministic ASCII portraits.

No art assets, no downloads: each monster's id seeds a symmetrical glyph blob
whose silhouette, density and character ramp come from its type and size. The
same monster always looks the same, and a monster you generate tomorrow gets a
portrait the moment it loads.
"""
from __future__ import annotations

import hashlib
import math
import random

W, H = 19, 12

RAMPS = {
    "Construct":  " ...:=+*#%@█",
    "Undead":     " ...''`^:;!|",
    "Plant":      " ...,;:%&@$#",
    "Dragon":     " ..::-=+*#%@",
    "Aquatic":    " ...~~≈≈≋@%#",
    "Insect":     " ..``''^*x%#",
    "Elemental":  " ...''\"*^#%@",
    "Divine":     " ...`'\"^*+#@",
    "Demon":      " ..:;!*&%$#@",
    "Humanoid":   " ...:;i|)#%@",
    "Beast":      " ..,;:*&%$#@",
    "Aberration": " ..`,~;?*%$@",
}
# Combat Type controls the terminal ink; Family still changes the shape via
# the deterministic seed.  This makes a freshly authored Forge creature read
# as *its own thing* even when its family is deliberately unfamiliar.
TYPE_RAMPS = {
    "Fire": " ..,:;!+*#%@", "Water": " ..,~≈≋@%#", "Electric": " ..`^!*#%@",
    "Nature": " ..,;:%&@$#", "Earth": " ..,:=+*#%@", "Wind": " ..`'~^*#%@",
    "Light": " ..`'\"^*+#@", "Dark": " ..:;!*&%$#@", "Cosmic": " ..`~;?*%$@",
    "Spirit": " ..''`^:;!|", "Primal": " ..,;:*&%$#@", "Arcane": " ..::-=+*#%@",
}
DEFAULT_RAMP = " ...:-=+*#%@"

SIZE_SPREAD = {"Tiny": 0.55, "Small": 0.7, "Medium": 0.85, "Large": 1.0,
               "Huge": 1.15, "Gargantuan": 1.3}

_CACHE: dict[str, list[str]] = {}


def signature(t, width: int = 8) -> str:
    """A stable little identity stamp for a creature.

    Python's built-in ``hash`` deliberately changes between processes, which
    made a creature's generated portrait subtly change every time the game
    relaunched.  The Forge now keeps ``portrait_seed`` with new records, but
    old records get an equally stable seed from their readable identity.
    """
    supplied = str(getattr(t, "portrait_seed", "") or "").strip()
    identity = supplied or "|".join((
        str(getattr(t, "id", "")), str(getattr(t, "name", "")),
        str(getattr(t, "primary", "")), str(getattr(t, "size", "")),
        str(getattr(t, "role", "")),
    ))
    return hashlib.blake2s(identity.encode("utf-8"), digest_size=16).hexdigest().upper()[:width]


def _seed(t) -> int:
    """Turn the visible signature into a repeatable random seed."""
    return int(signature(t, 16), 16)


def _noise(rng: random.Random, w: int, h: int) -> list[list[float]]:
    grid = [[rng.random() for _ in range(w)] for _ in range(h)]
    for _ in range(2):                       # smooth it so it reads as a body
        out = [[0.0] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                tot = n = 0.0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < h and 0 <= xx < w:
                            tot += grid[yy][xx]
                            n += 1
                out[y][x] = tot / n
        grid = out
    return grid


def for_template(t) -> list[str]:
    key = signature(t, 16)
    if key in _CACHE:
        return _CACHE[key]

    rng = random.Random(_seed(t))
    ramp = TYPE_RAMPS.get(t.primary, RAMPS.get(t.primary, DEFAULT_RAMP))
    spread = SIZE_SPREAD.get(t.size, 0.85)
    boss = getattr(t, "is_boss", False)

    half = W // 2 + 1
    noise = _noise(rng, half, H)
    rows = []
    cx, cy = 0.0, H / 2.0
    body_w = (W / 2.0) * spread
    body_h = (H / 2.0) * (0.92 if not boss else 1.0)
    lean = rng.uniform(-0.15, 0.15)

    for y in range(H):
        line = []
        # a waist: narrower near the bottom, wider at the shoulders
        t_y = (y - cy) / body_h
        width = math.sqrt(max(0.0, 1.0 - t_y * t_y)) * body_w
        width *= 1.0 + lean * t_y
        for x in range(half):
            dx = x - cx
            edge = width if width > 0 else 0.001
            fall = 1.0 - (dx / edge) ** 2 if abs(dx) < edge else -1.0
            v = fall * 0.75 + noise[y][x] * 0.55 - 0.25
            if boss:
                v += 0.08
            idx = int(max(0.0, min(0.999, v)) * (len(ramp) - 1))
            line.append(ramp[idx])
        full = list(reversed(line[1:])) + line
        rows.append("".join(full[:W]).rstrip() or " ")
    # trim empty top/bottom rows so portraits sit centred in their panel
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    _CACHE[key] = rows
    return rows


def as_text(t) -> str:
    return "\n".join(for_template(t))
