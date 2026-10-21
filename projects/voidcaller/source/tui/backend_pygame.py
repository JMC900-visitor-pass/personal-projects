"""Paints the cell grid into a window that behaves like a CRT.

Not a terminal emulator -- it only knows how to draw our own grid. Text is
rendered once per change into a layer, then a soft phosphor bloom, scanlines
and a vignette are composited over it, and the cursor blinks on top.
"""
from __future__ import annotations

import os

from .frames import FrameArt, OVERHANG, OVERHANG_Y
from .screen import BOLD, DIM, PALETTE, Screen

FONT_CANDIDATES = ["SF Mono", "Menlo", "Monaco", "IBM Plex Mono", "DejaVu Sans Mono",
                   "Liberation Mono", "Consolas", "Courier New", "monospace"]

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
BUNDLED = os.path.join(ASSETS, "VoidcallerMono.ttf")
BUNDLED_BOLD = os.path.join(ASSETS, "VoidcallerMono-Bold.ttf")
# Press Start 2P is the shell: menus, stats, dialogue, descriptions. It sits
# ahead of the system faces so the whole terminal reads as one piece.
UI_FONTS = [os.path.join(ASSETS, name) for name in
            ("PressStart2P.ttf", "PressStart2P-Regular.ttf", "press_start_2p.ttf")]
# Karmatic Arcade is reserved for the things that should stop you: battle
# feedback and the main title. Without it the shell face is used instead.
DISPLAY_FONTS = [os.path.join(ASSETS, name) for name in
                 ("KarmaticArcade.ttf", "karmatic_arcade.ttf", "Karmatic Arcade.ttf")]


_COVERAGE: dict[str, set] = {}


def font_coverage(path: str):
    """Every character a font file actually contains, read from its cmap.

    Asking the font file is the only reliable answer. `metrics()` reports a
    box for glyphs a face does not have on some SDL_ttf builds, and comparing
    renders is no better -- every missing glyph draws the same notdef, so the
    comparison cannot tell a real box-drawing character from a substitute.

    Returns None if the file cannot be read, which means "assume it has
    everything" -- the safe answer for a system font we did not ship.
    """
    import struct

    if path in _COVERAGE:
        return _COVERAGE[path]
    chars = None
    try:
        blob = open(path, "rb").read()
        base = 0
        if blob[:4] == b"ttcf":                      # a collection: take face 0
            base = struct.unpack(">I", blob[12:16])[0]
        tables = {}
        count = struct.unpack(">H", blob[base + 4:base + 6])[0]
        for i in range(count):
            rec = base + 12 + 16 * i
            tag = blob[rec:rec + 4].decode("latin1")
            tables[tag] = struct.unpack(">II", blob[rec + 8:rec + 16])[0]
        top = tables["cmap"]
        subtables = struct.unpack(">H", blob[top + 2:top + 4])[0]
        best = None
        for i in range(subtables):
            rec = top + 4 + 8 * i
            offset = struct.unpack(">I", blob[rec + 4:rec + 8])[0]
            fmt = struct.unpack(">H", blob[top + offset:top + offset + 2])[0]
            if fmt in (4, 12):
                # format 12 covers more than the basic plane, so it wins
                if best is None or fmt == 12:
                    best = (fmt, top + offset)
        fmt, at = best
        chars = set()
        if fmt == 4:
            seg = struct.unpack(">H", blob[at + 6:at + 8])[0] // 2
            ends = at + 14
            starts = ends + seg * 2 + 2
            deltas = starts + seg * 2
            ranges = deltas + seg * 2
            for i in range(seg):
                end = struct.unpack(">H", blob[ends + 2 * i:ends + 2 * i + 2])[0]
                start = struct.unpack(">H", blob[starts + 2 * i:starts + 2 * i + 2])[0]
                delta = struct.unpack(">h", blob[deltas + 2 * i:deltas + 2 * i + 2])[0]
                offset = struct.unpack(">H", blob[ranges + 2 * i:ranges + 2 * i + 2])[0]
                if start == 0xFFFF:
                    continue
                for code in range(start, end + 1):
                    if offset == 0:
                        glyph = (code + delta) & 0xFFFF
                    else:
                        at_g = ranges + 2 * i + offset + 2 * (code - start)
                        if at_g + 2 > len(blob):
                            continue
                        glyph = struct.unpack(">H", blob[at_g:at_g + 2])[0]
                        if glyph:
                            glyph = (glyph + delta) & 0xFFFF
                    if glyph:
                        chars.add(code)
        else:
            groups = struct.unpack(">I", blob[at + 12:at + 16])[0]
            for i in range(groups):
                rec = at + 16 + 12 * i
                start, end, _ = struct.unpack(">III", blob[rec:rec + 12])
                if end - start > 0x20000:            # a face that broad has it all
                    end = start + 0x20000
                chars.update(range(start, end + 1))
    except Exception:
        chars = None
    _COVERAGE[path] = chars
    return chars


class CRT:
    def __init__(self, cols: int, rows: int, font_size: int = 17, title: str = "VOIDCALLER",
                 bloom: float = 0.42, scanlines: float = 0.10, vignette: float = 0.30,
                 headless: bool = False, font: str | None = None,
                 window_scale: float = 1.0, fullscreen: bool = False,
                 fit_monitor: bool = False, crisp: bool = True):
        if headless:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        self.pg = pygame
        pygame.init()
        pygame.key.set_repeat(380, 34)

        self.cols, self.rows = cols, rows
        self.pixels = True      # this backend can blit real sprites
        self.bloom_amt, self.scan_amt, self.vig_amt = bloom, scanlines, vignette
        # A terminal should be legible first. Crisp mode keeps the optional
        # phosphor halo deliberately light; glyphs stay anti-aliased either
        # way so they do not turn into stair-stepped pixels.
        self.crisp = bool(crisp)
        self.forced_font = font
        # The CELL is measured from the terminal face, exactly as it always
        # was, so the wireframe never moves. Press Start 2P then supplies the
        # letters inside those cells. Changing the typeface must not change
        # the layout.
        self.font = self._load_font(font_size)
        self.font_chars = font_coverage(self.font_path)
        self.bold = self._load_font(font_size, bold=True)
        self.bold_chars = font_coverage(getattr(self, "bold_path", self.font_path))
        self.cw, self.ch = self.font.size("M")
        self.ch = int(self.font.get_linesize() * 0.98)
        self.shell = self._shell_font(self.cw)
        self.shell_chars = font_coverage(self.shell_path) if self.shell else None
        # The face we ship, held open behind the other two. Whatever a system
        # font turns out to be missing, this one has it, so a substitute box
        # never reaches the screen.
        self.frame_art = FrameArt(pygame)
        self.spare = self._spare_font(BUNDLED, font_size)
        self.spare_bold = self._spare_font(BUNDLED_BOLD, font_size) or self.spare
        self.pad = self.cw
        self.w = self.cols * self.cw + self.pad * 2
        self.h = self.rows * self.ch + self.pad * 2
        self.headless = headless
        self.window_scale = max(0.5, min(3.0, float(window_scale)))
        self.fullscreen = bool(fullscreen and not headless)
        self.fit_monitor = bool(fit_monitor and not headless)

        self.surface = self._open_window(headless)
        pygame.display.set_caption(title)
        self.canvas = pygame.Surface((self.w, self.h)).convert()
        self._update_viewport()
        self.text_layer = pygame.Surface((self.w, self.h)).convert()
        self.scan_layer = self._make_scanlines()
        self.vig_layer = self._make_vignette()
        self.glyphs: dict = {}
        self.sprite_cache: dict = {}
        self.cursor = None          # (col, row) or None
        self.frame = 0
        self.checked = False        # the one-off "is anything visible" check
        self.clock = pygame.time.Clock()
        # macOS in particular can drop the first few presentations of a new
        # window, which is what a blank CRT usually turns out to be. Force a
        # full repaint for the first second rather than trusting frame one.
        self.settle = 45

    def _open_window(self, headless: bool):
        """Open a physical window around the fixed logical character canvas."""
        pg = self.pg
        if headless:
            size, attempts = (self.w, self.h), [0]
        elif self.fullscreen:
            size, attempts = (0, 0), [pg.FULLSCREEN]
        else:
            scale = self.window_scale
            if self.fit_monitor:
                try:
                    dw, dh = pg.display.get_desktop_sizes()[0]
                except Exception:
                    info = pg.display.Info()
                    dw, dh = info.current_w, info.current_h
                scale = max(0.5, min((dw - 40) / self.w, (dh - 100) / self.h))
            size = (max(320, int(round(self.w * scale))),
                    max(240, int(round(self.h * scale))))
            # A user can drag a terminal window to exactly the scale they
            # want.  The logical canvas keeps its aspect ratio, so no content
            # is ever cropped; only the visible scale changes.
            attempts = [pg.RESIZABLE]
        last = None
        for flags in attempts:
            try:
                surf = pg.display.set_mode(size, flags)
                if surf is not None:
                    self.flags = flags
                    for _ in range(3):
                        pg.event.pump()
                    return surf
            except Exception as exc:      # noqa: BLE001 - any SDL failure at all
                last = exc
        raise RuntimeError(f"could not open a window: {last}")

    def _update_viewport(self) -> None:
        dw, dh = self.surface.get_size()
        scale = min(dw / self.w, dh / self.h)
        rw, rh = max(1, int(self.w * scale)), max(1, int(self.h * scale))
        self.viewport = ((dw - rw) // 2, (dh - rh) // 2, rw, rh)

    def reconfigure(self, *, window_scale: float | None = None,
                    fullscreen: bool | None = None, fit_monitor: bool | None = None) -> None:
        if window_scale is not None:
            self.window_scale = max(0.5, min(3.0, float(window_scale)))
        if fullscreen is not None:
            self.fullscreen = bool(fullscreen)
        if fit_monitor is not None:
            self.fit_monitor = bool(fit_monitor)
        if self.headless:
            return
        self.surface = self._open_window(False)
        self._update_viewport()
        self.settle = max(self.settle, 12)

    # -- setup ---------------------------------------------------------------
    def _spare_font(self, path: str, size: int):
        """The bundled face at the terminal size, or None if it is not there."""
        if not os.path.isfile(path):
            return None
        try:
            return self.pg.font.Font(path, size)
        except Exception:
            return None

    def _shell_font(self, cell_w: int):
        """Press Start 2P at whatever size fits the established cell width.

        The pixel face is square, so it is fitted by WIDTH: the letters land
        inside the cell the mono face defined instead of pushing it wider.
        """
        for path in UI_FONTS:
            if not os.path.isfile(path):
                continue
            best = None
            for size in range(6, max(8, cell_w * 3)):
                try:
                    trial = self.pg.font.Font(path, size)
                except Exception:
                    break
                if trial.size("M")[0] <= cell_w and trial.get_linesize() <= self.ch:
                    best = trial
                else:
                    break
            if best is not None:
                self.shell_path = path
                return best
        self.shell_path = None
        return None

    @staticmethod
    def measure_cell(font_size: int = 18) -> float:
        """Width/height of one character cell for the shell face, as a ratio.

        The grid has to be sized before a window exists, so this opens the
        font on its own and measures it rather than guessing.
        """
        import pygame
        pygame.font.init()
        for path in UI_FONTS + [BUNDLED]:
            if os.path.isfile(path):
                try:
                    font = pygame.font.Font(path, font_size)
                    w = font.size("M")[0]
                    h = max(1, int(font.get_linesize() * 0.98))
                    return max(0.25, min(2.0, w / h))
                except Exception:
                    continue
        return 0.6

    def _display_font(self, size: int):
        """The arcade face used for battle feedback, cached per pixel size."""
        cache = getattr(self, "_display_cache", None)
        if cache is None:
            cache = self._display_cache = {}
        size = max(8, int(size))
        if size in cache:
            return cache[size]
        font = None
        for path in DISPLAY_FONTS:
            if os.path.isfile(path):
                try:
                    font = self.pg.font.Font(path, size)
                    break
                except Exception:
                    font = None
        if font is None:
            font = self._load_font(size, bold=True)
        cache[size] = font
        return font

    def _load_font(self, size: int, bold: bool = False):
        """Try the bundled font first, then the system's -- and check each one
        actually puts ink on the surface before trusting it."""
        tries = []
        if self.forced_font:
            # an explicit --font wins: a path straight through, a name looked up
            if os.path.isfile(self.forced_font):
                tries.append((os.path.basename(self.forced_font), self.forced_font))
            else:
                path = self.pg.font.match_font(self.forced_font, bold=bold)
                if path:
                    tries.append((self.forced_font, path))
        # The TERMINAL face is loaded here and nowhere else. It draws the
        # wireframe — rules, corners, bars, blocks — so it has to be a face
        # that owns those glyphs. Press Start 2P does not; it is fitted
        # separately as the shell face and only ever asked for letters.
        # macOS / system monospace faces first, for clean anti-aliased letters.
        # The bundled face remains a reliable fallback on machines without one.
        for name in FONT_CANDIDATES:
            path = self.pg.font.match_font(name, bold=bold)
            if path:
                tries.append((name, path))
        shipped = BUNDLED_BOLD if bold else BUNDLED
        if os.path.isfile(shipped):
            tries.append(("bundled VoidcallerMono", shipped))
        for name, path in tries:
            try:
                font = self.pg.font.Font(path, size)
                if font.render("M", True, (255, 255, 255)).get_bounding_rect().width >= 2:
                    if bold:
                        self.bold_path = path
                    else:
                        self.font_name, self.font_path = name, path
                    return font
            except Exception:
                continue
        if bold:
            self.bold_path = "(built in)"
        else:
            self.font_name, self.font_path = "pygame default", "(built in)"
        return self.pg.font.Font(None, size)

    def retheme(self, theme: dict) -> None:
        """A new look: forget every cached glyph, rebuild the effect layers."""
        self.bloom_amt = float(theme.get("bloom", self.bloom_amt))
        self.scan_amt = float(theme.get("scanlines", self.scan_amt))
        self.vig_amt = float(theme.get("vignette", self.vig_amt))
        self.crisp = bool(theme.get("crisp", self.crisp))
        self.glyphs.clear()
        self.scan_layer = self._make_scanlines()
        self.vig_layer = self._make_vignette()
        self.settle = max(self.settle, 3)

    def _make_scanlines(self):
        surf = self.pg.Surface((self.w, self.h), self.pg.SRCALPHA)
        alpha = int(255 * self.scan_amt)
        for y in range(0, self.h, 3):
            self.pg.draw.line(surf, (0, 0, 0, alpha), (0, y), (self.w, y))
        return surf

    def _make_vignette(self):
        """Four edge gradients. No border_radius, so every SDL draws it the same."""
        surf = self.pg.Surface((self.w, self.h), self.pg.SRCALPHA)
        peak = int(255 * self.vig_amt)
        depth_x = max(8, int(self.w * 0.22))
        depth_y = max(8, int(self.h * 0.22))
        for i in range(depth_x):
            a = int(peak * ((1 - i / depth_x) ** 2.2))
            if a <= 0:
                continue
            self.pg.draw.line(surf, (0, 0, 0, a), (i, 0), (i, self.h))
            self.pg.draw.line(surf, (0, 0, 0, a), (self.w - 1 - i, 0), (self.w - 1 - i, self.h))
        for i in range(depth_y):
            a = int(peak * ((1 - i / depth_y) ** 2.2))
            if a <= 0:
                continue
            self.pg.draw.line(surf, (0, 0, 0, a), (0, i), (self.w, i))
            self.pg.draw.line(surf, (0, 0, 0, a), (0, self.h - 1 - i), (self.w, self.h - 1 - i))
        return surf

    def _shell_has(self, text: str) -> bool:
        """Whether the shell face really owns this character.

        Read from the font's own cmap. Press Start 2P covers ASCII and the
        Latin extensions and nothing else -- no box drawing, no blocks, no
        arrows -- so everything that draws the wireframe stays on the
        terminal face and no substitute box is ever rendered.
        """
        cover = self.shell_chars
        if cover is None:
            return False
        return all(ord(ch) in cover for ch in text)

    def _face_for(self, text: str, attrs: int):
        """The font that can actually draw this glyph.

        Shell face for letters, terminal face for the wireframe, and the
        bundled face behind both -- it is the one we ship, so it is the one
        we know the coverage of.
        """
        if self.shell is not None and self._shell_has(text):
            return self.shell
        font = self.bold if attrs & BOLD else self.font
        cover = self.bold_chars if attrs & BOLD else self.font_chars
        if cover is not None and any(ord(ch) not in cover for ch in text):
            spare = self.spare_bold if attrs & BOLD else self.spare
            if spare is not None:
                return spare
        return font

    def _glyph(self, text: str, fg: str, attrs: int):
        key = (text, fg, attrs, self.crisp)
        hit = self.glyphs.get(key)
        if hit is None:
            colour = PALETTE.get(fg, PALETTE["text"])
            if attrs & DIM:
                colour = tuple(int(c * 0.62) for c in colour)
            # Letters come from the shell face; rules, frames and blocks come
            # from the terminal face, which is the only one that has them.
            font = self._face_for(text, attrs)
            # The terminal can still have a sharp presentation without turning
            # every glyph into a staircase of hard pixels.
            hit = font.render(text, True, colour)
            if len(self.glyphs) > 20000:
                self.glyphs.clear()
            self.glyphs[key] = hit
        return hit

    def _effective_bloom(self) -> float:
        """Crisp text can still have a little glass glow, without a blur."""
        return self.bloom_amt * (0.28 if self.crisp else 1.0)

    # -- drawing -------------------------------------------------------------
    def render(self, screen: Screen) -> None:
        pg = self.pg
        if self.settle > 0:
            self.settle -= 1
            screen.dirty = True
        if screen.dirty:
            self.text_layer.fill(PALETTE["bg"])
            # Panel frames go down first: they are the furniture the text
            # sits inside, not decoration painted over it.
            bg = PALETTE["bg"]
            plate = tuple(min(255, c + 5) for c in bg)
            for fx, fy, fw, fh, fg, plates in getattr(screen, "frames", []):
                colour = PALETTE.get(fg, PALETTE["line"])
                px = self.pad + fx * self.cw - OVERHANG
                py = self.pad + fy * self.ch - OVERHANG_Y
                pw = fw * self.cw + OVERHANG * 2
                ph = fh * self.ch + OVERHANG_Y * 2
                art = self.frame_art.surface(pw, ph, colour, fill=plate)
                self.text_layer.blit(art, (px, py))
                # Knock the title out of the top edge so it reads as a label
                # set into the frame rather than printed across it.
                for cx, cells in plates:
                    self.text_layer.fill(
                        bg, (self.pad + cx * self.cw - 3, self.pad + fy * self.ch,
                             cells * self.cw + 6, self.ch))
            for y, x, text, fg, attrs in screen.runs():
                self.text_layer.blit(self._glyph(text, fg, attrs),
                                     (self.pad + x * self.cw, self.pad + y * self.ch))
            for path, x, y, w, h in getattr(screen, "sprites", []):
                try:
                    sprite = self.sprite_cache.get(path)
                    if sprite is None:
                        sprite = pg.image.load(path).convert_alpha()
                        self.sprite_cache[path] = sprite
                    target = (max(1, w * self.cw), max(1, h * self.ch))
                    art = pg.transform.scale(sprite, target)
                    self.text_layer.blit(art, (self.pad + x * self.cw, self.pad + y * self.ch))
                except Exception:
                    # Missing art should never block a terminal session; the
                    # deterministic text sigil below remains visible.
                    continue
            for text, fx, fy, colour, scale, alpha, _weight in getattr(screen, "flashes", []):
                try:
                    font = self._display_font(int(self.ch * 1.5 * scale))
                    ink = PALETTE.get(colour, PALETTE.get("text", (230, 230, 230)))
                    art = font.render(text, True, ink)
                    if alpha < 1.0:
                        art = art.copy()
                        art.set_alpha(int(255 * alpha))
                    px = int(self.pad + fx * self.cw - art.get_width() / 2)
                    py = int(self.pad + fy * self.ch - art.get_height() / 2)
                    self.text_layer.blit(art, (px, py))
                except Exception:
                    continue
            screen.dirty = False

        if not self.checked:
            self._safety_check()

        self.canvas.blit(self.text_layer, (0, 0))

        bloom = self._effective_bloom()
        if bloom > 0:
            scale = 4
            small = pg.transform.smoothscale(
                self.text_layer, (max(1, self.w // scale), max(1, self.h // scale)))
            blur = pg.transform.smoothscale(small, (self.w, self.h))
            g = int(255 * bloom)
            blur.fill((g, g, g), special_flags=pg.BLEND_RGB_MULT)
            self.canvas.blit(blur, (0, 0), special_flags=pg.BLEND_RGB_ADD)

        if self.cursor is not None and (self.frame // 26) % 2 == 0:
            col, row = self.cursor
            rect = pg.Rect(self.pad + col * self.cw, self.pad + row * self.ch + 2,
                           self.cw, self.ch - 3)
            block = pg.Surface(rect.size, pg.SRCALPHA)
            block.fill((*PALETTE["accent"], 205))
            self.canvas.blit(block, rect.topleft)

        if self.scan_amt > 0:
            self.canvas.blit(self.scan_layer, (0, 0))
        if self.vig_amt > 0:
            self.canvas.blit(self.vig_layer, (0, 0))

        vx, vy, vw, vh = self.viewport
        self.surface.fill(PALETTE["bg"])
        # Integer-style nearest-neighbour scaling keeps the hairline rules and
        # mono glyph edges clean on a Retina monitor.  The actual glyphs are
        # still anti-aliased at their native size; only the final glass is
        # sharpened.  Softer CRT themes retain smooth scaling by opting out of
        # crisp mode.
        scaler = pg.transform.scale if self.crisp else pg.transform.smoothscale
        frame = (self.canvas if (vw, vh) == (self.w, self.h)
                 else scaler(self.canvas, (vw, vh)))
        self.surface.blit(frame, (vx, vy))

        pg.display.flip()
        self.frame += 1
        # a window that is still black once it has settled is a real failure,
        # not a slow first frame -- catch it and turn the glass off.
        if self.frame == 90 and self._effective_bloom() + self.scan_amt + self.vig_amt > 0:
            if self._brightest(self.canvas) <= max(PALETTE["bg"]) + 12:
                self.bloom_amt = self.scan_amt = self.vig_amt = 0.0
                self.settle = 5
                print("\n  Still black after a second, so the CRT effects are off now.")
                print("  If it is still blank:  python3 crt.py --ansi\n")
        self.clock.tick(60)

    # -- input ---------------------------------------------------------------
    def poll(self) -> list:
        """Returns a list of ('key', name) / ('char', c) / ('click', (col,row)) / ('quit', None)."""
        pg = self.pg
        out = []
        NAMED = {
            pg.K_RETURN: "enter", pg.K_KP_ENTER: "enter", pg.K_BACKSPACE: "backspace",
            pg.K_TAB: "tab", pg.K_ESCAPE: "esc", pg.K_UP: "up", pg.K_DOWN: "down",
            pg.K_LEFT: "left", pg.K_RIGHT: "right", pg.K_PAGEUP: "pgup",
            pg.K_PAGEDOWN: "pgdn", pg.K_DELETE: "delete", pg.K_HOME: "home",
            pg.K_END: "end",
        }
        for ev in pg.event.get():
            if ev.type == pg.QUIT:
                out.append(("quit", None))
            elif ev.type == pg.KEYDOWN:
                if ev.key in NAMED:
                    out.append(("key", NAMED[ev.key]))
                elif ev.unicode and ev.unicode.isprintable():
                    out.append(("char", ev.unicode))
            elif ev.type == pg.VIDEORESIZE or ev.type in tuple(
                    getattr(pg, name) for name in ("WINDOWRESIZED", "WINDOWSIZECHANGED")
                    if hasattr(pg, name)):
                self.surface = pg.display.get_surface() or self.surface
                self._update_viewport()
                self.settle = max(self.settle, 3)
            elif ev.type in (pg.VIDEOEXPOSE, pg.WINDOWEVENT if hasattr(pg, "WINDOWEVENT") else pg.VIDEOEXPOSE):
                self.settle = max(self.settle, 3)
            elif ev.type == pg.MOUSEBUTTONDOWN and ev.button == 1:
                vx, vy, vw, vh = self.viewport
                logical_x = (ev.pos[0] - vx) * self.w / max(1, vw)
                logical_y = (ev.pos[1] - vy) * self.h / max(1, vh)
                col = (logical_x - self.pad) // self.cw
                row = (logical_y - self.pad) // self.ch
                if 0 <= col < self.cols and 0 <= row < self.rows:
                    out.append(("click", (int(col), int(row))))
        return out

    def _safety_check(self) -> None:
        """If the finished frame comes out black, say why and turn the effects
        off rather than leaving someone staring at an empty window."""
        self.checked = True
        bg = max(PALETTE["bg"])
        ink = self._brightest(self.text_layer)
        if ink <= bg + 12:
            print("\n  The text layer is coming out blank.")
            print(f"  font in use: {getattr(self, 'font_name', '?')} "
                  f"({getattr(self, 'font_path', '?')})")
            print("  Run  python3 crt.py --diag  to see why.")
            print("  In the meantime:  python3 crt.py --ansi\n")
            return
        probe = self.canvas.copy()
        probe.blit(self.text_layer, (0, 0))
        bloom = self._effective_bloom()
        if bloom > 0:
            small = self.pg.transform.smoothscale(
                self.text_layer, (max(1, self.w // 4), max(1, self.h // 4)))
            blur = self.pg.transform.smoothscale(small, (self.w, self.h))
            g = int(255 * bloom)
            blur.fill((g, g, g), special_flags=self.pg.BLEND_RGB_MULT)
            probe.blit(blur, (0, 0), special_flags=self.pg.BLEND_RGB_ADD)
        if self.scan_amt > 0:
            probe.blit(self.scan_layer, (0, 0))
        if self.vig_amt > 0:
            probe.blit(self.vig_layer, (0, 0))
        if self._brightest(probe) <= bg + 12 < ink:
            self.bloom_amt = self.scan_amt = self.vig_amt = 0.0
            # Remember it. This setup will fail the same check every launch,
            # and reprinting the same warning for ever is noise, not news.
            remembered = False
            try:
                from . import theme as TH
                look = TH.load()
                look.update({"bloom": 0.0, "scanlines": 0.0, "vignette": 0.0})
                TH.save(look)
                remembered = True
            except Exception:
                pass
            if not remembered:
                print("\n  The CRT effects were swallowing the picture on this setup,")
                print("  so they are off for this session. Everything else works.")
                print("  Use  python3 crt.py --plain  to skip them permanently.\n")
            else:
                print("\n  The CRT effects were blacking out this display, so they are"
                      "\n  now off by default. Turn them back on in the Screen Lab.\n")

    def diagnose(self, screen=None) -> None:
        pg = self.pg
        print("\n  VOIDCALLER render diagnostic")
        print(f"    pygame        {pg.version.ver}  (SDL {'.'.join(str(v) for v in pg.get_sdl_version())})")
        print(f"    font          {getattr(self, 'font_name', '?')}  ->  {getattr(self, 'font_path', '?')}")
        print(f"    cell          {self.cw} x {self.ch} px")
        print(f"    canvas        {self.w} x {self.h} px  for {self.cols} x {self.rows} cells")
        print(f"    window        {self.surface.get_width()} x {self.surface.get_height()} px")
        print(f"    flags         {'SCALED' if getattr(self, 'flags', 0) else 'plain'}"
              f"   driver {pg.display.get_driver()}")
        print(f"    effects       bloom {self.bloom_amt} ({self._effective_bloom():.2f} effective)"
              f"  scanlines {self.scan_amt}  vignette {self.vig_amt}  crisp {self.crisp}")
        probe = self.font.render("VOIDCALLER", True, (255, 255, 255))
        box = probe.get_bounding_rect()
        print(f"    test glyphs   surface {probe.get_size()}, ink {box.w}x{box.h}"
              f"  {'OK' if box.w > 4 and box.h > 3 else '<-- THE FONT IS RENDERING NOTHING'}")
        if screen is not None:
            self.text_layer.fill(PALETTE["bg"])
            for y, x, text, fg, attrs in screen.runs():
                self.text_layer.blit(self._glyph(text, fg, attrs),
                                     (self.pad + x * self.cw, self.pad + y * self.ch))
            print(f"    text layer    brightest pixel {self._brightest(self.text_layer)}"
                  f"   (bg is {max(PALETTE['bg'])})")
            self.render(screen)
            print(f"    after effects brightest pixel {self._brightest(self.surface)}")
            print("    if the text layer is bright and the composite is not,")
            print("    the effects are eating it: run with --plain\n")

    def _brightest(self, surf) -> int:
        """The brightest pixel in the surface. Sampled finely enough that a
        screen with only thin text on it is not mistaken for an empty one."""
        try:
            import pygame.surfarray as sa
            return int(sa.array3d(surf).max())
        except Exception:
            best = 0
            for y in range(0, surf.get_height(), 3):
                for x in range(0, surf.get_width(), 3):
                    best = max(best, max(surf.get_at((x, y))[:3]))
            return best

    def save(self, path: str) -> None:
        self.pg.image.save(self.surface, path)

    def close(self) -> None:
        self.pg.quit()
