"""The summoning circle. Shards in, dice out, something comes through."""
from __future__ import annotations

import random
import time

from . import balance as B
from . import ui


def screen(game) -> None:
    while True:
        ui.header("THE CIRCLE", f"{game.shards} shards  -  roster {len(game.roster)}/{B.ROSTER_CAP}")
        ui.say(ui.c(f"  A summon costs {B.SUMMON_COST} shards. What answers is not your choice.", "grey"))
        ui.say(ui.c("  odds: " + "  ".join(
            f"{r} {w/sum(B.RARITY_WEIGHT.values())*100:.0f}%"
            for r, w in B.RARITY_WEIGHT.items()), "grey"))
        opts = ["Summon once"]
        if game.shards >= B.SUMMON_COST * 5:
            opts.append("Summon five")
        opts.append("Release a monster back to the Void (for shards)")
        pick = ui.menu("", opts, back="leave the circle")
        if pick < 0:
            return
        if pick == 0:
            _summon(game, 1)
        elif opts[pick].startswith("Summon five"):
            _summon(game, 5)
        else:
            _release(game)


def _summon(game, times: int) -> None:
    for _ in range(times):
        if game.shards < B.SUMMON_COST:
            ui.say(ui.c("  Not enough shards.", "red"))
            break
        if len(game.roster) >= B.ROSTER_CAP:
            ui.say(ui.c("  Your roster is full. Release something first.", "red"))
            break
        game.shards -= B.SUMMON_COST
        t = game.bestiary.roll_summon()
        col = B.RARITY_COLOR.get(t.rarity, "white")
        ui.say()
        for line in ui.SIGIL:
            ui.say(ui.c("    " + line, col))
        m = game.add_monster(t)
        ui.say(ui.c(f"    {t.name.upper()}  -  {t.title or t.role}", col, "bold"))
        ui.say(ui.c(f"    {t.rarity}  L{t.level}  {t.primary}"
                    + (f"/{t.secondary}" if t.secondary else "")
                    + f"  hp {m.max_hp}  power {m.power}", col))
        if t.appearance:
            ui.say(ui.c(f"    {t.appearance[:110]}", "grey"))
    ui.pause()


def _release(game) -> None:
    if not game.roster:
        return
    rows = [f"{m.name:<24} L{m.level:<3} {ui.c(m.rarity, B.RARITY_COLOR.get(m.rarity,'white')):<12} "
            f"power {m.power}" for m in game.roster]
    i = ui.menu("  Release whom?", rows)
    if i < 0:
        return
    m = game.roster[i]
    if len(game.roster) <= 1:
        ui.say(ui.c("  You cannot walk into the Void alone.", "red"))
        return
    if ui.confirm(ui.c(f"  Release {m.name}? This cannot be undone.", "red")):
        pay = game.release(m)
        ui.say(ui.c(f"  {m.name} unravels. +{pay} shards.", "magenta"))
    ui.pause()
