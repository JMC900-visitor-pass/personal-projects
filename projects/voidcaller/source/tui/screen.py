"""A grid of characters, and the palette they're drawn in.

Everything above this file writes cells. Everything below it paints them --
into a CRT window, or into a real terminal. Neither knows about the other.
"""
from __future__ import annotations

BOLD = 1
DIM = 2
REV = 4

# warm phosphor: green-leaning white on near-black, amber for money, mint for you
PALETTE = {
    "bg":      (7, 12, 10),
    "text":    (198, 232, 210),
    "bright":  (232, 244, 238),
    "dim":     (95, 138, 118),
    "faint":   (61, 92, 80),
    "line":    (34, 58, 50),
    "accent":  (79, 224, 176),
    "green":   (127, 217, 143),
    "amber":   (232, 184, 96),
    "gold":    (224, 169, 63),
    "red":     (224, 106, 94),
    "magenta": (196, 137, 224),
    "blue":    (111, 184, 224),
    "cyan":    (111, 224, 210),
}
# A creature name is coloured by its combat Type, never by rarity.  The
# lowercase form keeps the renderer resilient to old records while all new
# model data uses the title-cased twelve-Type vocabulary.
TYPE_COLOR = {
    "fire": "red", "water": "blue", "electric": "amber", "nature": "green",
    "earth": "gold", "wind": "cyan", "light": "bright", "dark": "magenta",
    "cosmic": "blue", "spirit": "cyan", "primal": "amber", "arcane": "magenta",
    # Read-only aliases for imported V1 content.
    "ice": "cyan", "lightning": "amber", "none": "faint", "": "faint",
}
# Compatibility export for the older terminal renderer. New pages call this
# type palette through ``el_col`` and do not treat Types as a separate system.
ELEMENT_COLOR = TYPE_COLOR

# Straight ASCII keeps the screen feeling like a living terminal rather than
# a stack of desktop UI cards. Colour and animation carry the hierarchy.
BOX = {"tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "-", "v": "|",
       "lt": "+", "rt": "+", "tt": "+", "bt": "+", "x": "+"}
BAR_FULL, BAR_EMPTY = "█", "░"


class Screen:
    """cols x rows of (char, colour name, attrs)."""

    def __init__(self, cols: int, rows: int):
        self.cols, self.rows = cols, rows
        # Set by the backend. True only where real pixels can be drawn, which
        # decides whether a creature is shown as its sprite or as the ASCII
        # sigil.  Deliberately set here rather than in clear(), which runs
        # every frame.
        self.pixels = False
        self.clear()

    def clear(self, fg: str = "text") -> None:
        self.cells = [[(" ", fg, 0) for _ in range(self.cols)] for _ in range(self.rows)]
        # Pixel art is the creature wherever it can be drawn; the ASCII sigil
        # is the fallback for terminals that cannot, not an overlay on top.
        self.sprites = []
        # Free-floating battle text. It deliberately escapes the character
        # grid: a hit should read as an event with weight and motion, which a
        # fixed cell cannot express. Terminals without pixels ignore these and
        # fall back to the plain grid text.
        self.flashes = []
        # Panel frames, as rects rather than characters. A backend that can
        # draw pixels paints these underneath the text; the terminal build
        # never receives one, because frame() gives it ASCII instead.
        self.frames = []
        self.dirty = True

    def flash(self, text: str, x: float, y: float, colour: str = "amber",
              scale: float = 1.0, alpha: float = 1.0, weight: str = "display") -> None:
        """Place a piece of battle feedback in fractional cell coordinates.

        ``x``/``y`` are cell positions but may be fractional, so a number can
        drift and settle between cells. The caller owns the animation and
        passes the state it wants drawn this frame; the backend only renders.
        """
        if text and alpha > 0.01:
            self.flashes.append((str(text), float(x), float(y), str(colour),
                                 max(0.1, float(scale)), max(0.0, min(1.0, float(alpha))),
                                 str(weight)))

    def sprite(self, path: str, x: int, y: int, w: int, h: int) -> None:
        """Place a 16px Forge asset in logical terminal-cell coordinates."""
        if path and w > 0 and h > 0:
            self.sprites.append((str(path), int(x), int(y), int(w), int(h)))

    # -- primitives ----------------------------------------------------------
    def put(self, x: int, y: int, text: str, fg: str = "text", attrs: int = 0) -> int:
        if not (0 <= y < self.rows) or not text:
            return x
        for ch in str(text):
            if x >= self.cols:
                break
            if x >= 0:
                self.cells[y][x] = (ch, fg, attrs)
            x += 1
        self.dirty = True
        return x

    def rich(self, x: int, y: int, parts) -> int:
        """parts: iterable of (text, colour) or (text, colour, attrs)."""
        for p in parts:
            text, fg = p[0], p[1]
            attrs = p[2] if len(p) > 2 else 0
            x = self.put(x, y, text, fg, attrs)
        return x

    def fill(self, x: int, y: int, w: int, h: int, ch: str = " ", fg: str = "text") -> None:
        for row in range(y, min(y + h, self.rows)):
            self.put(x, row, ch * max(0, min(w, self.cols - x)), fg)

    def hline(self, x: int, y: int, w: int, fg: str = "line", ch: str = None) -> None:
        self.put(x, y, (ch or BOX["h"]) * w, fg)

    def vline(self, x: int, y: int, h: int, fg: str = "line", ch: str = None) -> None:
        for i in range(h):
            self.put(x, y + i, ch or BOX["v"], fg)

    def frame(self, x: int, y: int, w: int, h: int, fg: str = "line",
              title: str = "", title_fg: str = "dim", right: str = "") -> None:
        """One panel border, in whichever material the backend can draw.

        Where there are pixels this is a nine-slice frame, recorded as a rect
        and painted under the text. Where there are not -- a real terminal --
        it is the same ASCII box it has always been. The cell footprint is
        identical either way, so no layout above this file changes.
        """
        if self.pixels:
            # Where the title and the right-hand label sit, so the backend can
            # knock a plate out of the top edge and let them read.
            plates = []
            if title:
                plates.append((int(x) + 2, len(title) + 2))
            if right:
                plates.append((int(x) + w - 4 - len(right), len(right) + 2))
            self.frames.append((int(x), int(y), int(w), int(h), str(fg), plates))
        else:
            b = BOX
            self.put(x, y, b["tl"] + b["h"] * (w - 2) + b["tr"], fg)
            for i in range(1, h - 1):
                self.put(x, y + i, b["v"], fg)
                self.put(x + w - 1, y + i, b["v"], fg)
            self.put(x, y + h - 1, b["bl"] + b["h"] * (w - 2) + b["br"], fg)
        if title:
            self.put(x + 2, y, f" {title} ", title_fg, BOLD)
        if right:
            self.put(x + w - 2 - len(right) - 2, y, f" {right} ", "faint")

    # -- widgets -------------------------------------------------------------
    def bar(self, x: int, y: int, w: int, value: float, maximum: float,
            fg: str = None, empty_fg: str = "line", attrs: int = DIM) -> None:
        maximum = max(1.0, maximum)
        frac = max(0.0, min(1.0, value / maximum))
        filled = int(round(frac * w))
        if fg is None:
            fg = "green" if frac > 0.5 else "amber" if frac > 0.25 else "red"
        self.put(x, y, BAR_FULL * filled, fg, attrs)
        self.put(x + filled, y, BAR_EMPTY * (w - filled), empty_fg)

    def right(self, x: int, y: int, w: int, text: str, fg: str = "text",
              attrs: int = 0) -> None:
        text = str(text)
        self.put(x + max(0, w - len(text)), y, text, fg, attrs)

    def center(self, y: int, text: str, fg: str = "text", attrs: int = 0,
               x: int = 0, w: int = None) -> None:
        w = self.cols if w is None else w
        self.put(x + max(0, (w - len(text)) // 2), y, text, fg, attrs)

    def wrap(self, x: int, y: int, w: int, text: str, fg: str = "dim",
             limit: int = 99) -> int:
        import textwrap
        lines = textwrap.wrap(str(text), max(8, w))[:limit]
        for i, ln in enumerate(lines):
            self.put(x, y + i, ln, fg)
        return len(lines)

    # -- for the backends ----------------------------------------------------
    def runs(self):
        """Yield (y, x, text, fg, attrs) with adjacent same-style cells merged."""
        for y, row in enumerate(self.cells):
            x = 0
            while x < self.cols:
                ch, fg, at = row[x]
                start, buf = x, []
                while x < self.cols and row[x][1] == fg and row[x][2] == at:
                    buf.append(row[x][0])
                    x += 1
                text = "".join(buf)
                if text.strip():
                    yield y, start, text, fg, at


class Region:
    """A rectangle of the screen a pane is allowed to draw into."""

    def __init__(self, screen: Screen, x: int, y: int, w: int, h: int):
        self.s, self.x, self.y, self.w, self.h = screen, x, y, w, h

    def put(self, col, row, text, fg="text", attrs=0):
        if 0 <= row < self.h:
            return self.s.put(self.x + col, self.y + row,
                              str(text)[: max(0, self.w - col)], fg, attrs)
        return col

    def rich(self, col, row, parts):
        if 0 <= row < self.h:
            x = self.x + col
            for p in parts:
                attrs = p[2] if len(p) > 2 else 0
                room = self.x + self.w - x
                if room <= 0:
                    break
                x = self.s.put(x, self.y + row, str(p[0])[:room], p[1], attrs)
        return col

    def bar(self, col, row, w, value, maximum, fg=None, attrs=DIM):
        if 0 <= row < self.h:
            self.s.bar(self.x + col, self.y + row, min(w, self.w - col), value,
                       maximum, fg, attrs=attrs)

    def right(self, col, row, w, text, fg="text", attrs=0):
        if 0 <= row < self.h:
            self.s.right(self.x + col, self.y + row, w, text, fg, attrs)

    def hline(self, col, row, w, fg="line", ch=None):
        if 0 <= row < self.h:
            self.s.hline(self.x + col, self.y + row, min(w, self.w - col), fg, ch)

    def wrap(self, col, row, w, text, fg="dim", limit=99):
        if 0 <= row < self.h:
            return self.s.wrap(self.x + col, self.y + row, min(w, self.w - col),
                               text, fg, min(limit, self.h - row))
        return 0

    def sub(self, col, row, w, h):
        return Region(self.s, self.x + col, self.y + row, w, h)
