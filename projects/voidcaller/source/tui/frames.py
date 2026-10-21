"""Pixel-art panel frames, generated rather than drawn.

A nine-slice frame the way a GBA-era menu has one: a hard outline, a lit
edge, a woven band, a shadowed edge and an inner line, with solid blocks at
the corners. The anatomy is read off classic tilesheets; the art is made
here so the colour is free -- a focused panel is the same frame in amber,
which is the whole selection model in one property.

Nothing here imports pygame at module level. The backend passes its own
module in, so the ANSI terminal build can import this file harmlessly.

TO REPLACE THIS WITH YOUR OWN ART: rewrite ``ring_map`` only. Everything
else is colour and caching.
"""
from __future__ import annotations

# One entry per art pixel of ring depth, outside in.
RING = ["line", "hi", "weave", "lo", "inner"]
DEPTH = len(RING)
# Art pixels are drawn this many screen pixels across. Three is the chunky
# NES read; two is a finer GBA bevel.
SCALE = 3
# The ring hangs this far outside the panel's cell box, into the gutter, so
# a 15px border can sit on a 10px cell without eating the text column.
OVERHANG = 5
# Vertical overhang is smaller: rows are already tall enough to take it.
OVERHANG_Y = 3


def ring_map(w: int, h: int, weave: bool = True):
    """The role of every art pixel in a w x h frame. None means interior."""
    grid = [[None] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            depth = min(x, y, w - 1 - x, h - 1 - y)
            if depth >= DEPTH:
                continue
            role = RING[depth]
            if role == "weave":
                # The band alternates along its run. That alternation is what
                # reads as woven rather than as a flat painted bar.
                run = x if (y < DEPTH or y >= h - DEPTH) else y
                role = "body" if (not weave or run % 4 in (0, 1)) else "mid"
            grid[y][x] = role
    # Solid corner blocks. A purely mitred ring reads as a picture frame; the
    # corner has to have weight for it to read as a menu.
    for cx in (0, 1):
        for cy in (0, 1):
            for dy in range(DEPTH):
                for dx in range(DEPTH - dy):
                    x = dx if cx == 0 else w - 1 - dx
                    y = dy if cy == 0 else h - 1 - dy
                    depth = min(dx, dy)
                    grid[y][x] = "line" if depth == 0 else ("hi" if depth <= 1 else "lo")
    return grid


def shades(rgb):
    """The tints one palette colour has to supply for a whole ring."""
    def mix(amount, towards):
        return tuple(int(c + (t - c) * amount) for c, t in zip(rgb, towards))
    return {"line": (10, 12, 14),
            "hi": mix(0.42, (255, 255, 255)),
            "body": mix(0.16, (255, 255, 255)),
            # The weave is a shadow, not a spark. Alternating into the
            # highlight makes an idle panel brighter than its own contents.
            "mid": mix(0.20, (0, 0, 0)),
            "lo": mix(0.48, (0, 0, 0)),
            "inner": mix(0.70, (0, 0, 0))}


class FrameArt:
    """Builds and caches frame surfaces for one backend."""

    def __init__(self, pygame_module):
        self.pg = pygame_module
        self.cache = {}

    def surface(self, pw: int, ph: int, rgb, fill=None, weave: bool = True):
        """A frame ``pw`` x ``ph`` screen pixels, cached by every argument."""
        key = (pw, ph, tuple(rgb), tuple(fill) if fill else None, weave)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        aw = max(DEPTH * 2 + 2, pw // SCALE)
        ah = max(DEPTH * 2 + 2, ph // SCALE)
        grid = ring_map(aw, ah, weave)
        tint = shades(rgb)
        small = self.pg.Surface((aw, ah), self.pg.SRCALPHA)
        for y in range(ah):
            row = grid[y]
            for x in range(aw):
                role = row[x]
                if role is None:
                    if fill is not None:
                        small.set_at((x, y), tuple(fill) + (255,))
                else:
                    small.set_at((x, y), tint[role] + (255,))
        art = self.pg.transform.scale(small, (aw * SCALE, ah * SCALE))
        if len(self.cache) > 400:
            self.cache.clear()
        self.cache[key] = art
        return art
