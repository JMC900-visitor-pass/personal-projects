"""Terminal presentation: colour, bars, boxes, menus. No game logic in here."""
from __future__ import annotations

import os
import shutil
import sys
import time

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
QUIET = False          # set True by the headless test harness
SLOW = 0.0             # seconds between combat lines; 0 = instant

_C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "black": "\033[30m", "red": "\033[31m", "green": "\033[32m",
    "yellow": "\033[33m", "blue": "\033[34m", "magenta": "\033[35m",
    "cyan": "\033[36m", "white": "\033[37m", "grey": "\033[90m",
    "bright_red": "\033[91m", "bright_green": "\033[92m",
    "bright_yellow": "\033[93m", "bright_cyan": "\033[96m",
}

ELEMENT_COLOR = {
    "fire": "bright_red", "water": "bright_cyan", "electric": "bright_yellow",
    "nature": "bright_green", "earth": "yellow", "wind": "green",
    "light": "bright_yellow", "dark": "magenta", "cosmic": "cyan",
    "spirit": "bright_cyan", "primal": "bright_green", "arcane": "magenta",
    # Imported V1 labels remain coloured while they are being re-authored.
    "ice": "bright_cyan", "lightning": "bright_yellow", "none": "white",
}


def c(text: str, *styles: str) -> str:
    if not USE_COLOR or not styles:
        return str(text)
    pre = "".join(_C.get(s, "") for s in styles)
    return f"{pre}{text}{_C['reset']}"


def width() -> int:
    return min(shutil.get_terminal_size((80, 24)).columns, 100)


def say(text: str = "", *styles: str) -> None:
    if QUIET:
        return
    print(c(text, *styles) if styles else text)
    if SLOW:
        time.sleep(SLOW)


def clear() -> None:
    if QUIET:
        return
    os.system("cls" if os.name == "nt" else "clear")


def rule(char: str = "-") -> None:
    say(c(char * width(), "grey"))


def header(title: str, subtitle: str = "") -> None:
    if QUIET:
        return
    w = width()
    say()
    say(c("+" + "-" * (w - 2) + "+", "cyan"))
    say(c("|", "cyan") + c(title.center(w - 2), "bold", "bright_cyan") + c("|", "cyan"))
    if subtitle:
        say(c("|", "cyan") + c(subtitle.center(w - 2), "grey") + c("|", "cyan"))
    say(c("+" + "-" * (w - 2) + "+", "cyan"))


def box(lines: list[str], title: str = "") -> None:
    if QUIET:
        return
    w = width()
    top = f"+-{title}" + "-" * max(0, w - 4 - len(title)) + "-+"
    say(c(top, "grey"))
    for ln in lines:
        say(c("| ", "grey") + ln)
    say(c("+" + "-" * (w - 2) + "+", "grey"))


def bar(cur: int, mx: int, size: int = 20, kind: str = "hp") -> str:
    mx = max(1, mx)
    cur = max(0, min(cur, mx))
    pct = cur / mx
    fill = int(round(pct * size))
    if kind == "hp":
        col = "bright_green" if pct > 0.5 else "bright_yellow" if pct > 0.25 else "bright_red"
    else:
        col = "blue"
    return c("#" * fill, col) + c("." * (size - fill), "grey")


def pct_bar(pct: float, size: int = 20, col: str = "cyan") -> str:
    fill = int(round(max(0.0, min(1.0, pct)) * size))
    return c("#" * fill, col) + c("." * (size - fill), "grey")


EOF = False          # set when stdin runs dry, so piped input can't spin forever


def pause(msg: str = "press enter") -> None:
    global EOF
    if QUIET or EOF:
        return
    try:
        input(c(f"  ({msg})", "grey"))
    except EOFError:
        EOF = True


def ask(prompt: str, default: str = "") -> str:
    global EOF
    if EOF:
        return default
    try:
        val = input(c(prompt, "bright_cyan")).strip()
    except EOFError:
        EOF = True
        return default
    return val or default


def menu(title: str, options: list[str], back: str = "back", allow_back: bool = True) -> int:
    """Returns a 0-based index, or -1 for back."""
    while True:
        if EOF:
            return -1
        say()
        if title:
            say(c(title, "bold"))
        for i, opt in enumerate(options, 1):
            say(f"  {c(str(i).rjust(2), 'bright_cyan')}. {opt}")
        if allow_back:
            say(f"   {c('0', 'grey')}. {c(back, 'grey')}")
        raw = ask("> ")
        if EOF:
            return -1
        if raw in ("0", "b", "q") and allow_back:
            return -1
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        say(c("  pick a number from the list.", "red"))


def confirm(prompt: str) -> bool:
    return ask(f"{prompt} (y/n) ").lower().startswith("y")


def money(gold: int) -> str:
    return c(f"{gold}g", "yellow")


def shards(n: int) -> str:
    return c(f"{n} shards", "magenta")


# the summoning sigil, drawn when something comes through the circle
SIGIL = [r"    .  ^  .    ",
         r"   / \ | / \   ",
         r"  <---(*)--->  ",
         r"   \ / | \ /   ",
         r"    '  v  '    "]
