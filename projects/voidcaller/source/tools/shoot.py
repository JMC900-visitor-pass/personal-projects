"""Drives the shell with no keyboard and writes frames out as PNGs."""
from __future__ import annotations

import os
import time


def settle(app, backend, seconds=2.2):
    end = time.time() + seconds
    while time.time() < end:
        app.drain()
        app.draw()
        backend.render(app.screen)
        if not app.busy:
            break


def shot(app, backend, path):
    app.draw()
    backend.render(app.screen)
    backend.save(path)
    print("wrote", path)


def run_shots(app, backend, outdir):
    os.makedirs(outdir, exist_ok=True)
    app.root("gate")
    shot(app, backend, f"{outdir}/01_gate.png")
    app.cursor = 0; app.choose()
    settle(app, backend, 0.5)
    shot(app, backend, f"{outdir}/02_void_pick.png")

    app.run_command("walk 1")
    settle(app, backend)
    shot(app, backend, f"{outdir}/03_run.png")

    for _ in range(6):
        if app.state.get("battle"):
            break
        app.run_command("down 1")
        settle(app, backend, 3.0)
    shot(app, backend, f"{outdir}/04_battle.png")

    if app.state.get("battle"):
        app.run_command("attack 1")
        for _ in range(220):
            app.drain()
            app.draw()
            backend.render(app.screen)
            if app.tray and app.tray["kind"] == "hit":
                break
        shot(app, backend, f"{outdir}/05_dice.png")
        settle(app, backend, 8.0)

    app.root("gate"); app.go("gate.pack")
    settle(app, backend, 0.4)
    shot(app, backend, f"{outdir}/06_pack.png")
    app.cursor = 0; app.choose()
    settle(app, backend, 0.4)
    shot(app, backend, f"{outdir}/07_card.png")

    app.root("gate"); app.go("gate.ledger")
    app.cursor = 2
    settle(app, backend, 0.4)
    shot(app, backend, f"{outdir}/08_ledger.png")
    app.choose()
    settle(app, backend, 0.4)
    shot(app, backend, f"{outdir}/09_dex.png")

    app.root("gate"); app.go("gate.stall")
    settle(app, backend, 0.4)
    shot(app, backend, f"{outdir}/10_stall.png")
