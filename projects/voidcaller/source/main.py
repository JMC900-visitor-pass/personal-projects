#!/usr/bin/env python3
"""
VOIDCALLER - a monster-taming RPG for the terminal.

    python3 main.py

Monsters are read live from the generator's own output (../output/monsters.jsonl
and anything you drop in data/monsters/). Generate more, and they turn up in the
Void, on the quest board and in the summoning circle without touching the code.
"""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import balance as B
from engine import quests, shop, story, summon, team, ui, void
from engine.data import load_bestiary, require_bestiary
from engine.state import Game, list_saves

TITLE = r"""
 __     __   ___   ___  ____    ____    _     _     _____  ____
 \ \   / /  / _ \ |_ _||  _ \  / ___|  / \   | |   | ____||  _ \
  \ \ / /  | | | | | | | | | || |     / _ \  | |   |  _|  | |_) |
   \ V /   | |_| | | | | |_| || |___ / ___ \ | |___| |___ |  _ <
    \_/     \___/ |___||____/  \____/_/   \_\|_____|_____||_| \_\
"""


def title_screen(bestiary) -> "Game | None":
    ui.clear()
    ui.say(ui.c(TITLE, "bright_cyan"))
    ui.say(ui.c("        a hunt in the dark         -   " + str(len(bestiary)) + " species bound to the ledger", "grey"))
    saves = list_saves()
    opts = ["New hunt"]
    if saves:
        opts.append("Continue")
    opts.append("Quit")
    pick = ui.menu("", opts, allow_back=False)
    if pick < 0 or opts[pick] == "Quit":
        return None
    if opts[pick] == "Continue":
        i = ui.menu("  Which save?", [f"{s:<8} {label}" for s, label in saves])
        if i < 0:
            return title_screen(bestiary)
        g = Game.load(saves[i][0], bestiary)
        if g:
            ui.say(ui.c(f"  Welcome back, {g.hunter}.", "bright_green"))
            ui.pause()
            return g
        ui.say(ui.c("  That save is broken.", "red"))
        ui.pause()
        return title_screen(bestiary)
    return new_game(bestiary)


def new_game(bestiary) -> Game:
    g = Game(bestiary)
    ui.header("A NEW HUNT")
    g.hunter = ui.ask("  What do they call you? ", "Hunter") or "Hunter"
    ui.say()
    ui.say(ui.c("  Mirren rolls the bones. Three things answer.", "grey"))
    ui.pause()
    for t in bestiary.starters(3):
        col = B.RARITY_COLOR.get(t.rarity, "white")
        ui.say()
        for line in ui.SIGIL:
            ui.say(ui.c("    " + line, col))
        m = g.add_monster(t)
        ui.say(ui.c(f"    {t.name.upper()}  -  {t.title or t.role}", col, "bold"))
        ui.say(ui.c(f"    {t.rarity}  L{t.level}  {t.primary}  hp {m.max_hp}  power {m.power}", col))
        if t.appearance:
            ui.say(ui.c(f"    {t.appearance[:110]}", "grey"))
    ui.say()
    ui.say(ui.c(f"  They are bound to you now, {g.hunter}. They die when you do.", "grey"))
    g.board = quests.generate_board(g)
    ui.pause()
    return g


def hub(g: Game) -> None:
    while True:
        ready = sum(1 for q in g.quests if q.done(g))
        ui.header("THE GATE TOWN",
                  f"day {g.day}  -  {g.hunter}  -  {g.gold}g  -  {g.shards} shards")
        for m in g.party:
            ui.say(f"  {ui.c(m.name, 'bold'):<28} L{m.level:<3} "
                   f"{ui.bar(m.cur_hp, m.max_hp, 14)} {m.cur_hp}/{m.max_hp}")
        opts = [
            ui.c("Walk into the Void", "bright_cyan") + ui.c("   fight, gather, extract", "grey"),
            "Quest board" + (ui.c(f"   {ready} ready to turn in", "bright_yellow") if ready else
                             ui.c(f"   {len(g.quests)} active", "grey")),
            "The stall" + ui.c("   buy and sell", "grey"),
            "The circle" + ui.c(f"   summon  ({g.shards} shards)", "grey"),
            "The thread" + ui.c(f"   story  ({g.story}/4 chapters)", "grey"),
            "The pack" + ui.c(f"   {len(g.roster)} monsters", "grey"),
            "The ledger" + ui.c(f"   {len(g.seen)}/{len(g.bestiary)} species", "grey"),
            "Rest" + ui.c("   heal everything, free", "grey"),
            "Save",
            "Save and quit",
        ]
        pick = ui.menu("", opts, allow_back=False)
        if pick < 0:                      # stdin ran out (piped play / ctrl-D)
            g.save()
            return
        if pick == 0:
            void.run(g)
        elif pick == 1:
            quests.board_screen(g)
        elif pick == 2:
            shop.screen(g)
        elif pick == 3:
            summon.screen(g)
        elif pick == 4:
            story.screen(g)
        elif pick == 5:
            team.screen(g)
        elif pick == 6:
            team.bestiary_screen(g)
        elif pick == 7:
            g.rest()
            ui.say(ui.c("  You sleep badly and wake whole. Everyone is at full.", "bright_green"))
            ui.pause()
        elif pick == 8:
            ui.say(ui.c(f"  Saved to {g.save()}", "grey"))
            ui.pause()
        elif pick == 9:
            g.save()
            ui.say(ui.c("  Saved. The gate will still be there.", "grey"))
            return


def main() -> None:
    bestiary = load_bestiary()
    if not require_bestiary(bestiary):
        return
    while True:
        g = title_screen(bestiary)
        if g is None:
            ui.say(ui.c("  The gate closes.", "grey"))
            return
        try:
            hub(g)
        except KeyboardInterrupt:
            g.save()
            ui.say(ui.c("\n  Saved. Goodbye.", "grey"))
            return


if __name__ == "__main__":
    main()
