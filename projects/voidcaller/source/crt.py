#!/usr/bin/env python3
"""
VOIDCALLER — the fixed-frame build.

    python3 crt.py              a window that behaves like a warm old terminal
    python3 crt.py --ansi       the same interface, painted into your real terminal
    python3 crt.py --plain      no bloom, no scanlines, just the grid
    python3 crt.py --looks      the looks you can wear
    python3 crt.py --theme ice  start in one of them
    python3 crt.py --diag       what the renderer is actually doing

First run needs pygame for the window:  .venv/bin/python -m pip install pygame-ce
The --ansi mode needs nothing at all.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.data import load_bestiary
from engine.session import Session
from engine.state import Game, list_saves
from tui import theme as TH
from tui import display as DISPLAY
from tui.app import App, set_grid
from tui import app as APP


def build_session(slot: str | None, name: str) -> Session | None:
    bestiary = load_bestiary()
    game = None
    if slot:
        game = Game.load(slot, bestiary)
        if game is None:
            print(f"no save called '{slot}'")
    session = Session(game or Game(bestiary))
    session.default_hunter = name
    if session.game.roster:
        session.screen = "home"
    return session


def venv_with_pygame() -> str:
    """A .venv beside the game that already has pygame in it. The usual cause
    of 'pygame isn't installed' is running the system python by habit."""
    here = os.path.dirname(os.path.abspath(__file__))
    for name in (".venv", "venv", "env"):
        base = os.path.join(here, name)
        python = os.path.join(base, "bin", "python3")
        if not os.path.isfile(python) and not os.path.islink(python):
            continue
        import glob as _glob
        if _glob.glob(os.path.join(base, "lib", "python*", "site-packages", "pygame")):
            return python
    return ""


def no_pygame() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    ready = venv_with_pygame()
    lines = ["", "  This python has no pygame, so there is no window to open."]
    if ready:
        lines += [
            "",
            "  There is already a virtualenv here that has it. Use that python:",
            "",
            f"      {ready} {os.path.join(here, 'crt.py')}",
            "",
            "  or turn it on for this shell first:",
            "",
            f"      source {os.path.join(os.path.dirname(ready), 'activate')}",
            "      python3 crt.py",
        ]
    else:
        lines += [
            "",
            "  Homebrew python will not let pip install into it system-wide,",
            "  so make a virtualenv for the game:",
            "",
            f"      cd {here}",
            "      python3 -m venv .venv",
            "      source .venv/bin/activate",
            "      pip install pygame-ce",
            "      python3 crt.py",
            "",
            "  (pygame-ce is the maintained fork; it imports as pygame.)",
        ]
    lines += ["",
              "  Or play the same interface right now, with no install at all:",
              "",
              "      python3 crt.py --ansi", ""]
    return "\n".join(lines)


def handoff_to_project_python() -> bool:
    """Re-launch with the local environment when system Python lacks pygame.

    This keeps the normal Mac command (`python3 crt.py`) working without
    installing packages into Homebrew's managed Python.
    """
    try:
        import pygame  # noqa: F401
        return True
    except ImportError:
        ready = venv_with_pygame()
        # A venv's python is commonly a symlink to Homebrew Python. Comparing
        # real paths would incorrectly treat them as the same interpreter even
        # though invoking through the venv path changes sys.prefix/site-packages.
        if ready and os.path.abspath(ready) != os.path.abspath(sys.executable):
            os.execv(ready, [ready, os.path.abspath(__file__), *sys.argv[1:]])
        print(no_pygame())
        return False


def _desktop_size():
    """The primary monitor's pixel size, however this SDL build reports it."""
    import pygame
    pygame.display.init()
    try:
        return pygame.display.get_desktop_sizes()[0]
    except Exception:
        info = pygame.display.Info()
        return info.current_w, info.current_h


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ansi", action="store_true", help="paint into the real terminal")
    ap.add_argument("--plain", action="store_true", help="no bloom, scanlines or vignette")
    ap.add_argument("--theme", default=None,
                    help="start in a named look: " + "/".join(
                        t["name"] for t in TH.presets()))
    ap.add_argument("--looks", action="store_true", help="list the looks and exit")
    ap.add_argument("--headless", action="store_true", help="render with no window (for tests)")
    ap.add_argument("--font-size", type=int, default=18)
    ap.add_argument("--font", default=None,
                    help="a font file, or a system font name, instead of the bundled one")
    ap.add_argument("--slot", default=None)
    ap.add_argument("--name", default="Hunter")
    ap.add_argument("--shots", default=None, help="write frames to this directory and exit")
    ap.add_argument("--diag", action="store_true", help="report what the renderer is doing")
    ap.add_argument("--scale", type=float, default=None, help="window scale, e.g. 1.25")
    ap.add_argument("--fullscreen", action="store_true", help="open in fullscreen")
    ap.add_argument("--fit", action="store_true", help="fit the terminal to this monitor")
    args = ap.parse_args()

    if args.looks:
        print()
        for t in TH.presets():
            print(f"  {t['name']:<12} {t['label']:<18} {t.get('note', '')}")
        print("\n  python3 crt.py --theme amber      "
              "or press L at the gate to change it in the game\n")
        return

    if not args.ansi and not handoff_to_project_python():
        return

    look = TH.preset(args.theme) if args.theme else TH.load()
    if args.plain:
        look["bloom"] = look["scanlines"] = look["vignette"] = 0.0
    TH.apply(look)

    session = build_session(args.slot, args.name)
    if session is None:
        return

    if args.ansi:
        import shutil
        size = shutil.get_terminal_size((80, 24))
        COLS, ROWS = APP.COLS, APP.ROWS
        if size.columns < COLS or size.lines < ROWS:
            print(f"\n  This build needs a {COLS}x{ROWS} terminal — yours is "
                  f"{size.columns}x{size.lines}.")
            print("  Make the window bigger (or drop the font size) and run it again.")
            print("  Full screen at 12pt usually does it.\n")
            if input("  Try anyway? [y/N] ").strip().lower() not in ("y", "yes"):
                return
        from tui.backend_ansi import Ansi
        backend = Ansi(APP.COLS, APP.ROWS)
    else:
        from tui.backend_pygame import CRT
        display = DISPLAY.load()
        # The grid stays at its designed 118x45. Growing it to the monitor's
        # shape only pays off if the screens actually use the extra room, and
        # they lay out against fixed rows — so a taller grid bought nothing
        # but a large empty band under the page. Fullscreen scales the whole
        # canvas up instead, which keeps the proportions the UI was drawn for.
        COLS, ROWS = APP.COLS, APP.ROWS
        if args.scale is not None:
            display["scale"] = args.scale
        if args.fullscreen:
            display["fullscreen"] = True
        if args.fit:
            display["fit_monitor"] = True
        backend = CRT(COLS, ROWS, font_size=args.font_size,
                      bloom=look["bloom"], scanlines=look["scanlines"],
                      vignette=look["vignette"],
                      headless=args.headless or bool(args.shots),
                      font=args.font, window_scale=display["scale"],
                      fullscreen=display["fullscreen"], fit_monitor=display["fit_monitor"],
                      crisp=bool(look.get("crisp", True)))
    TH.apply(look, backend)

    app = App(backend, session)
    if args.diag and hasattr(backend, "diagnose"):
        app.draw()
        backend.diagnose(app.screen)
        backend.close()
        return
    try:
        if args.shots:
            from tools.shoot import run_shots
            run_shots(app, backend, args.shots)
        else:
            app.loop()
    finally:
        backend.close()
        try:
            app.s.game.save()
        except Exception:
            pass


if __name__ == "__main__":
    main()
