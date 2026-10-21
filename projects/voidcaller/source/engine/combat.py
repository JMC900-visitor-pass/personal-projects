"""Terminal rendering of a battle. All the rules live in rules.py / battle.py --
this file only decides how an event looks as text."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import balance as B
from . import ui
from .battle import Battle
from .entities import Combatant
from .rules import GUARD


@dataclass
class BattleResult:
    won: bool = False
    fled: bool = False
    wiped: bool = False
    xp: int = 0
    gold: int = 0
    shards: int = 0
    loot: list = field(default_factory=list)
    rounds: int = 0
    log: list = field(default_factory=list)


# --- display helpers --------------------------------------------------------
def _hp_line(c: Combatant) -> str:
    if not c.alive:
        return ui.c(f"  {c.name} L{c.level}  -- down --", "grey")
    tag = ui.c(f"{c.name}", "bright_red" if c.is_enemy else "bold")
    lvl = ui.c(f"L{c.level}", "grey")
    hp = f"{ui.bar(c.cur_hp, c.max_hp, 16)} {c.cur_hp:>4}/{c.max_hp:<4}"
    st = " " + ui.c("[" + ",".join(sorted(c.statuses)) + "]", "magenta") if c.statuses else ""
    return f"  {tag} {lvl} {hp}{st}"


def _snap_line(u: dict) -> str:
    if not u["alive"]:
        return ui.c(f"  {u['name']} L{u['level']}  -- down --", "grey")
    tag = ui.c(u["name"], "bright_red" if u["side"] == "enemy" else "bold")
    hp = f"{ui.bar(u['hp'], u['max_hp'], 16)} {u['hp']:>4}/{u['max_hp']:<4}"
    st = " " + ui.c("[" + ",".join(u["statuses"]) + "]", "magenta") if u["statuses"] else ""
    return f"  {tag} {ui.c('L' + str(u['level']), 'grey')} {hp}{st}"


def show_field(party, enemies, rnd: int, field=None) -> None:
    """Draws the field as it stood at the top of the round, from the event."""
    if ui.QUIET:
        return
    ui.say()
    ui.say(ui.c(f"--- round {rnd} " + "-" * (ui.width() - 12), "grey"))
    if field:
        ui.say(ui.c(" ENEMIES", "bright_red"))
        for u in [x for x in field if x["side"] == "enemy"]:
            ui.say(_snap_line(u))
        ui.say(ui.c(" YOUR PACK", "bright_green"))
        for u in [x for x in field if x["side"] == "party"]:
            ui.say(_snap_line(u))
        return
    ui.say(ui.c(" ENEMIES", "bright_red"))
    for e in enemies:
        ui.say(_hp_line(e))
    ui.say(ui.c(" YOUR PACK", "bright_green"))
    for m in party:
        ui.say(_hp_line(m))


def alive(group):
    return [c for c in group if c.alive]


def render(e: dict, bt: Battle) -> None:
    """One event, one or two lines of text."""
    if ui.QUIET:
        return
    k = e["k"]
    if k == "battle_start":
        ui.header(e["title"], " vs ".join(sorted(set(e["enemies"]))))
        if e.get("quote"):
            ui.say(ui.c('  "' + e["quote"] + '"', "grey"))
    elif k == "round":
        show_field(bt.party, bt.enemies, e["n"], e.get("field"))
    elif k == "skill":
        el = ui.c(e["element"], ui.ELEMENT_COLOR.get(e["element"], "white")) if e["element"] != "none" else ""
        ui.say(f"    {ui.c(e['actor'], 'bold')} uses {ui.c(e['skill'], 'bright_cyan')} "
               f"{el} on {', '.join(e['targets'])}")
        if e.get("note"):
            ui.say(ui.c(f"      ({e['note']})", "grey"))
    elif k == "guard":
        ui.say(f"    {ui.c(e['actor'], 'bold')} braces. " + ui.c("(takes 45% less this round)", "grey"))
    elif k == "miss":
        ui.say(f"      {e['target']} {ui.c('evades', 'grey')} "
               + ui.c(f"({e['chance']:.0f}% to connect)", "grey"))
    elif k == "hit":
        line = "      "
        if e["crit"]:
            line += ui.c("CRITICAL  ", "bright_yellow", "bold")
        line += ui.c(f"-{e['amount']}", "bright_red", "bold")
        if abs(e["mult"] - 1.0) > 0.01:
            el = ui.c(e["element"], ui.ELEMENT_COLOR.get(e["element"], "white"))
            mcol = "bright_yellow" if e["mult"] > 1 else "cyan"
            line += f"  x{e['mult']:g} {el} {ui.c(e['label'], mcol)}"
        ui.say(line + ui.c(f"   {e['target']} {e['hp']}/{e['max_hp']}", "grey"))
    elif k == "status":
        if e["applied"]:
            ui.say(ui.c(f"      {e['target']} is {e['status']}! ({e['rounds']} rounds)", "magenta"))
        elif e["reason"] == "immune":
            ui.say(ui.c(f"      {e['target']} is immune to {e['status']}.", "grey"))
        else:
            ui.say(ui.c(f"      {e['target']} shrugs off {e['status']}.", "grey"))
    elif k == "stat":
        arrow = "up" if e["amount"] > 0 else "down"
        ui.say(ui.c(f"      {e['target']} {e['stat'].upper()} {arrow} "
                    f"{abs(e['amount'])*100:.0f}% ({e['rounds']} rounds)", "cyan"))
    elif k == "heal":
        ui.say(ui.c(f"      {e['target']} recovers {e['amount']} HP.", "bright_green"))
    elif k == "drain":
        ui.say(ui.c(f"      {e['actor']} drains {e['amount']} HP.", "bright_green"))
    elif k == "pp_restore":
        ui.say(ui.c(f"      {e['target']} restores {e['amount']} PP.", "blue"))
    elif k == "cleanse":
        ui.say(ui.c(f"      {e['target']} is cleansed.", "cyan"))
    elif k == "revive":
        ui.say(ui.c(f"      {e['target']} rises again!", "bright_yellow"))
    elif k == "dot":
        ui.say(ui.c(f"      {e['who']} takes {e['amount']} {e['status']} damage.", "magenta"))
    elif k == "status_end":
        if e["status"] in ("sleep", "stone", "stun"):
            ui.say(ui.c(f"      {e['who']} comes to.", "grey"))
    elif k == "skip":
        word = {"sleep": "is asleep", "stone": "is petrified", "stun": "cannot move"}
        ui.say(ui.c(f"    {e['who']} {word.get(e['reason'], 'cannot act')}.", "grey"))
    elif k == "faint":
        ui.say(ui.c(f"    {e['who']} falls.", "bright_yellow" if e["side"] == "enemy" else "red"))
    elif k == "pressure":
        ui.say(ui.c(f"    The Void leans in. (round {e['round']}: everything takes "
                    f"{e['pct']}% damage)", "magenta"))
    elif k == "flee":
        ui.say(f"  {e['who']} looks for a way out — {e['chance']:.0f}% chance.")
        ui.say(ui.c("  You slip back into the dark." if e["success"]
                    else "  Cornered! The pack loses its footing.",
                    "cyan" if e["success"] else "red"))
    elif k == "capture":
        ui.say(ui.c(f"  {e['actor']} casts a binding seal at {e['target']} "
                    f"({e['chance']:.0f}%).", "cyan"))
        ui.say(ui.c("  The seal holds." if e["success"] else "  It breaks free.",
                    "bright_green" if e["success"] else "red"))
    elif k == "item":
        ui.say(ui.c(f"  {e['name']} used on {e['target']}.", "cyan"))
    elif k == "note":
        ui.say(ui.c("  " + e["text"], "grey"))
    elif k == "end":
        if e["result"] == "draw":
            ui.say(ui.c("  Nothing is left standing. Something drags you back to the gate.",
                        "magenta"))


def render_all(events, bt: Battle) -> None:
    for e in events:
        render(e, bt)


# --- the terminal battle ----------------------------------------------------
def battle(party, enemies, game=None, allow_flee: bool = True,
           auto: bool = False, title: str = "BATTLE") -> BattleResult:
    bt = Battle(party, enemies, title=title, allow_flee=allow_flee, auto=auto)
    render_all(bt.start(), bt)

    while not bt.finished:
        actor = bt.waiting
        if actor is None:
            render_all(bt.advance(), bt)
            continue
        choice = player_turn(actor, party, enemies, game, bt.allow_flee)
        if isinstance(choice, str):
            choice = (choice, None, None)
        action, idx, target_uid = choice
        if action == "item":
            name, tuid = idx, target_uid
            render_all(bt.use_item(game, name, tuid), bt)
        else:
            render_all(bt.act(action, idx, target_uid), bt)

    res = BattleResult(won=bt.outcome == "win", fled=bt.outcome in ("flee", "draw"),
                       wiped=bt.outcome == "lose", rounds=bt.round, log=bt.events)
    r = bt.rewards or {}
    res.xp, res.gold = r.get("xp", 0), r.get("gold", 0)
    res.shards, res.loot = r.get("shards", 0), list(r.get("loot", []))
    return res


def player_turn(actor, party, enemies, game, allow_flee: bool):
    while True:
        ui.say()
        ui.say(f"  {ui.c('>', 'bright_cyan')} {ui.c(actor.name, 'bold')}'s turn  "
               f"{ui.c(f'hp {actor.cur_hp}/{actor.max_hp}', 'grey')}")
        opts = ["Attack / skill", "Guard", "Use item", "Auto-battle from here"]
        if allow_flee:
            opts.append("Flee")
        pick = ui.menu("", opts, allow_back=False)
        if pick < 0:
            return ("auto", None, None)
        if pick == 0:
            i = choose_skill(actor)
            if i is None:
                continue
            target_uid = None
            if actor.skills[i].target == "single":
                t = choose_target(enemies)
                if t is None:
                    continue
                target_uid = t.uid
            return ("skill", i, target_uid)
        if pick == 1:
            return ("guard", None, None)
        if pick == 2:
            got = choose_item(actor, party, game)
            if got is None:
                continue
            return ("item", got[0], got[1])
        if pick == 3:
            return ("auto", None, None)
        if pick == 4:
            return ("flee", None, None)


def choose_skill(actor):
    labels = []
    for s in actor.skills:
        dmg = s.rating or "--"
        cost = ui.c(f"{actor.pp_left(s)}/{s.pp}pp", "blue") if s.pp else ui.c("fallback", "grey")
        el = ui.c(s.element, ui.ELEMENT_COLOR.get(s.element, "white")) if s.element != "none" else ""
        tail = ui.c(s.effect_text[:40], "grey") if s.effect_text else ""
        lock = "" if actor.can_cast(s) else ui.c("  [no pp]", "red")
        labels.append(f"{s.name:<22} {dmg:<8} {s.target:<11} {cost:<10} {el} {tail}{lock}")
    i = ui.menu("  Which move?", labels)
    if i < 0:
        return None
    if not actor.can_cast(actor.skills[i]):
        ui.say(ui.c("  No PP left for that move.", "red"))
        return None
    return i


def choose_target(enemies):
    live = alive(enemies)
    labels = [f"{e.name:<24} {ui.bar(e.cur_hp, e.max_hp, 12)} {e.cur_hp}/{e.max_hp}" for e in live]
    i = ui.menu("  Target?", labels)
    return None if i < 0 else live[i]


def choose_item(actor, party, game):
    if game is None or not getattr(game, "inventory", None):
        ui.say(ui.c("  Your pack is empty.", "grey"))
        return None
    usable = [(n, q) for n, q in sorted(game.inventory.items())
              if q > 0 and game.items.get(n, {}).get("use")]
    if not usable:
        ui.say(ui.c("  Nothing usable in here.", "grey"))
        return None
    i = ui.menu("  Use what?", [f"{n:<20} x{q:<3} {ui.c(game.items[n].get('desc',''), 'grey')}"
                               for n, q in usable])
    if i < 0:
        return None
    name = usable[i][0]
    spec = game.items[name]["use"]
    if spec.get("flee"):
        return (name, None)
    pool = [p for p in party if p.alive or spec.get("revive_pct")]
    if not pool:
        return None
    j = ui.menu("  On whom?", [f"{p.name:<20} {ui.bar(p.cur_hp, p.max_hp, 12)} "
                               f"{p.cur_hp}/{p.max_hp}" for p in pool])
    if j < 0:
        return None
    return (name, pool[j].uid)


class FleeSignal(Exception):
    pass
