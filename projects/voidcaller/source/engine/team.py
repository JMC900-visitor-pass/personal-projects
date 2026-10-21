"""Roster management and the monster card."""
from __future__ import annotations

from . import balance as B
from . import elements as EL
from . import ui
from .entities import xp_for_level


def _row(game, m, idx: int) -> str:
    inparty = m.uid in game.party_uids
    mark = ui.c(" *", "bright_green") if inparty else "  "
    col = ui.ELEMENT_COLOR.get(m.template.primary.casefold(), "white")
    return (f"{mark} {ui.c(m.name, col):<24} L{m.level:<3} {m.rarity_mark:<12} "
            f"{ui.bar(m.cur_hp, m.max_hp, 10)} {m.cur_hp:>4}/{m.max_hp:<4} "
            f"pow {m.power:<5} {ui.c(m.template.role, 'grey')}")


def screen(game) -> None:
    while True:
        ui.header("THE PACK", f"{len(game.roster)}/{B.ROSTER_CAP} bound  -  "
                              f"{len(game.party)}/{B.PARTY_SLOTS} in the fighting four")
        if not game.roster:
            ui.say(ui.c("  Nothing bound to you.", "grey"))
            ui.pause()
            return
        rows = [_row(game, m, i) for i, m in enumerate(game.roster)]
        ui.say(ui.c("  (* = goes into the Void with you)", "grey"))
        pick = ui.menu("", rows + [ui.c("-- choose your fighting four --", "bright_cyan")],
                       back="leave")
        if pick < 0:
            return
        if pick == len(rows):
            _choose_party(game)
        else:
            card(game, game.roster[pick])


def _choose_party(game) -> None:
    chosen = []
    ui.say(ui.c(f"  Pick up to {B.PARTY_SLOTS}, in the order you want them read out.", "grey"))
    while len(chosen) < B.PARTY_SLOTS:
        left = [m for m in game.roster if m not in chosen]
        if not left:
            break
        i = ui.menu(f"  Slot {len(chosen)+1}:", [_row(game, m, 0) for m in left],
                    back="done")
        if i < 0:
            break
        chosen.append(left[i])
    if chosen:
        game.set_party(chosen)
        ui.say(ui.c("  Pack set: " + ", ".join(m.name for m in chosen), "bright_green"))
    ui.pause()


def card(game, m) -> None:
    t = m.template
    col = ui.ELEMENT_COLOR.get(t.primary.casefold(), "white")
    lines = [
        ui.c(f"{m.name}", "bold", col) + ui.c(f"  {t.title}", "grey"),
        ui.c(f"{m.rarity_mark} {m.rarity}  L{m.level}  {t.role}  {t.primary}"
             + (f"/{t.secondary}" if t.secondary else "") + f"  {t.size}  {t.family}", "grey"),
        "",
        f"HP {m.cur_hp}/{m.max_hp}   power {m.power}   Skill Points {m.skill_points}",
        f"xp {m.xp}  " + (ui.c(f"({m.xp_to_next} to level {m.level+1})", "grey")
                          if m.level < B.MAX_LEVEL else ui.c("(capped)", "grey")),
        "",
        ui.c("stats  ", "grey") + "  ".join(
            f"{k.upper()} {int(m.stat(k))}" for k in ("atk", "def", "mag", "res", "spd")),
        ui.c("combat ", "grey") + "Move accuracy and critical chance are written on each move.",
        "",
    ]
    weak = EL.weaknesses(t)
    res = EL.resistances(t)
    if weak:
        lines.append(ui.c("weak to    ", "grey") + "  ".join(
            ui.c(f"{e} x{m:g}", ui.ELEMENT_COLOR.get(e, "white")) for e, m in weak))
    if res:
        lines.append(ui.c("resists    ", "grey") + "  ".join(
            ui.c(f"{e} x{m:g}", ui.ELEMENT_COLOR.get(e, "white")) for e, m in res))
    lines.append("")
    lines.append(ui.c("moves", "bright_cyan"))
    for s in m.skills:
        dmg = s.rating or "--"
        pp = f"{m.pp_left(s)}/{s.pp}pp" if s.pp else "fallback"
        lines.append(f"  {s.name:<22} {dmg:<9} {s.target:<11} {pp:<10} "
                     + ui.c(s.effect_text[:40], "grey"))
    if t.lore:
        lines += ["", ui.c(t.lore[:200], "grey")]
    ui.box(lines, title=t.id.upper())

    pick = ui.menu("", ["Rename", "Put in / take out of the fighting four"], back="back")
    if pick == 0:
        new = ui.ask("  New name: ")
        if new:
            m.nickname = new[:20]
    elif pick == 1:
        if m.uid in game.party_uids:
            game.party_uids = [u for u in game.party_uids if u != m.uid]
            ui.say(ui.c(f"  {m.name} stays home.", "grey"))
        elif len(game.party_uids) < B.PARTY_SLOTS:
            game.party_uids.append(m.uid)
            ui.say(ui.c(f"  {m.name} joins the four.", "bright_green"))
        else:
            ui.say(ui.c("  The four is full.", "red"))
        ui.pause()


def bestiary_screen(game) -> None:
    b = game.bestiary
    ui.header("THE LEDGER", f"{len(game.seen)}/{len(b)} species recorded")
    rows = []
    for t in sorted(b.all, key=lambda x: (x.level, x.name)):
        if t.id in game.seen:
            kills = game.kills.get(t.name, 0)
            rows.append(f"{t.name:<26} L{t.level:<3} "
                        f"{ui.c(t.rarity_mark + ' ' + t.rarity, ui.ELEMENT_COLOR.get(t.primary.casefold(),'white')):<12} "
                        f"{ui.c(str(kills) + ' killed', 'grey')}")
        else:
            rows.append(ui.c(f"{'?' * min(12, len(t.name)):<26} L{t.level:<3}", "grey"))
    for r in rows:
        ui.say("  " + r)
    ui.pause()
