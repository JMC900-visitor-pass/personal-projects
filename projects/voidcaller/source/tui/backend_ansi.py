"""The same grid, painted into a real terminal as a fixed frame.

Cursor is parked, the screen is repainted in place rather than scrolled, and
keys are read raw so the interface behaves the same as the CRT window.
"""
from __future__ import annotations

import os
import select
import sys

from .screen import BOLD, DIM, PALETTE, Screen

ESC = "\033"
NAMED = {"\r": "enter", "\n": "enter", "\x7f": "backspace", "\x08": "backspace",
         "\t": "tab", "\x1b": "esc", "\x03": "quit"}
SEQ = {"[A": "up", "[B": "down", "[C": "right", "[D": "left",
       "[5~": "pgup", "[6~": "pgdn", "[H": "home", "[F": "end", "[3~": "delete"}


class Ansi:
    def __init__(self, cols: int, rows: int, **_):
        self.cols, self.rows = cols, rows
        self.cursor = None
        self.frame = 0
        self._raw = None
        self._prev = None
        sys.stdout.write(f"{ESC}[?1049h{ESC}[?25l")     # alt screen, hide cursor
        sys.stdout.flush()
        self._enter_raw()

    def _enter_raw(self):
        try:
            import termios, tty
            self._fd = sys.stdin.fileno()
            self._raw = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        except Exception:
            self._raw = None

    def render(self, screen: Screen) -> None:
        out = [f"{ESC}[H"]
        for y in range(screen.rows):
            out.append(f"{ESC}[{y + 1};1H{ESC}[K")
            for _, x, text, fg, attrs in [r for r in screen.runs() if r[0] == y]:
                r, g, b = PALETTE.get(fg, PALETTE["text"])
                if attrs & DIM:
                    r, g, b = int(r * .62), int(g * .62), int(b * .62)
                style = "1;" if attrs & BOLD else ""
                out.append(f"{ESC}[{y + 1};{x + 1}H{ESC}[{style}38;2;{r};{g};{b}m{text}{ESC}[0m")
        sys.stdout.write("".join(out))
        sys.stdout.flush()
        screen.dirty = False
        self.frame += 1

    def poll(self) -> list:
        if not select.select([sys.stdin], [], [], 0.03)[0]:
            return []
        data = os.read(sys.stdin.fileno(), 64).decode("utf-8", "ignore")
        out, i = [], 0
        while i < len(data):
            ch = data[i]
            if ch == ESC and i + 1 < len(data):
                for seq, name in SEQ.items():
                    if data.startswith(seq, i + 1):
                        out.append(("key", name))
                        i += 1 + len(seq)
                        break
                else:
                    out.append(("key", "esc"))
                    i += 1
                continue
            if ch in NAMED:
                name = NAMED[ch]
                out.append(("quit", None) if name == "quit" else ("key", name))
            elif ch.isprintable():
                out.append(("char", ch))
            i += 1
        return out

    def save(self, path: str) -> None:
        pass

    def close(self) -> None:
        try:
            if self._raw:
                import termios
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._raw)
        except Exception:
            pass
        sys.stdout.write(f"{ESC}[?25h{ESC}[?1049l")
        sys.stdout.flush()
