"""The Void: pick a region, walk in, and keep walking until it stops being wise."""
from __future__ import annotations

import random

from . import balance as B
from . import areas as AREAS
from . import combat, luck, ui
from .entities import spawn

DEPTHS = [("Shallow", 3, 1.0), ("Deep", 5, 1.35), ("Abyssal", 7, 1.8)]

GATHER_FLAVOUR = [
    "A seam of something glitters where the dark thins.",
    "Bones, picked clean, and something under them worth taking.",
    "A dead hunter's pack, still buckled. He will not need it.",
    "Fungus grows in a ring here, and the ring is worth money.",
]
CACHE_FLAVOUR = [
    "A strongbox, half swallowed by the floor.",
    "Coins in a hollow skull. Someone's idea of a joke.",
    "A caravan that never came back. Its cargo did not walk away.",
]
SHRINE_FLAVOUR = [
    "A shrine of stacked stones. The air here is kinder.",
    "Still water, and it does not reflect you. You drink anyway.",
    "Someone carved a prayer here and meant it.",
]


def region_menu(game) -> str | None:
    b = game.bestiary
    lvl = max(1, sum(m.level for m in game.party) // max(1, len(game.party)))
    rows, keys = [], []
    for area in AREAS.regions(b, lvl):
        danger = area["danger"]
        col = {"quiet": "grey", "fair": "bright_green", "hard": "bright_yellow",
               "lethal": "bright_red"}[danger]
        cleared = game.regions_cleared.get(area["key"], 0)
        rows.append(f"{area['name']:<26} {ui.c(danger, col):<20} "
                    f"{area['species']:>3} species  {ui.c(f'cleared {cleared}x', 'grey')}")
        keys.append(area["key"])
    if not rows:
        ui.say(ui.c("  The Void Atlas is empty. Forge an area and assign a monster first.", "yellow"))
        ui.pause()
        return None
    i = ui.menu("  Where are you walking?", rows, back="stay in town")
    return None if i < 0 else keys[i]


def depth_menu() -> tuple[str, int, float] | None:
    rows = [f"{name:<10} {n} encounters   loot x{mult:g}" for name, n, mult in DEPTHS]
    i = ui.menu("  How far in?", rows, back="turn back")
    return None if i < 0 else DEPTHS[i]


def build_encounter(game, region: str, level: int, boss: bool = False):
    b = game.bestiary
    assigned = AREAS.templates_for(b, region, bosses=None)
    ordinary = [t for t in assigned if not t.is_boss]
    if boss:
        pool = AREAS.templates_for(b, region, bosses=True)
        pool = pool or [t for t in assigned if t.is_boss] or ordinary
        if not pool:
            return []
        t = random.choice(pool)
        return [spawn(t, max(1, level + 2), enemy=True)]
    pool = ordinary
    if not pool:
        return []
    lead = random.choice(pool)
    # The terminal battle is explicitly one active companion versus one active
    # wild creature. Groups remain an area-authoring signal, not simultaneous
    # enemy turns that can dog-pile a new hunter.
    return [spawn(lead, max(1, level + random.randint(-1, 1)), enemy=True)]


def pack_status(game) -> None:
    ui.say(ui.c("  your pack:", "grey"))
    for m in game.party:
        ui.say(combat._hp_line(m))


def run(game) -> None:
    if not game.party:
        ui.say(ui.c("  You have no monsters to send in.", "red"))
        ui.pause()
        return
    region = region_menu(game)
    if region is None:
        return
    depth = depth_menu()
    if depth is None:
        return
    depth_name, steps, mult = depth
    lvl = max(1, sum(m.level for m in game.party) // len(game.party))

    bag: list[str] = []
    gold = shards = xp = 0
    ui.clear()
    ui.header(f"THE VOID - {region.title()}", f"{depth_name} run - {steps} encounters")
    ui.say(ui.c("  The light behind you thins to a coin, then a pinprick, then nothing.", "grey"))
    ui.pause()

    step = 0
    while step < steps:
        step += 1
        last = step == steps
        roll = luck.between(1, 20)
        ui.say()
        ui.say(ui.c(f"  -- step {step}/{steps} --  (d20 event roll: {roll})", "grey"))

        if last and depth_name != "Shallow":
            event = "boss"
        elif roll <= 13:
            event = "fight"
        elif roll <= 16:
            event = "gather"
        elif roll <= 18:
            event = "cache"
        else:
            event = "shrine"

        if event in ("fight", "boss"):
            foes = build_encounter(game, region, lvl + step // 2, boss=(event == "boss"))
            title = "VOID BOSS" if event == "boss" else f"{region.title()} - encounter {step}"
            res = combat.battle(game.party, foes, game=game,
                                allow_flee=(event != "boss"), title=title)
            if res.fled:
                ui.say(ui.c("  You break contact and pull out. Loot stays yours.", "cyan"))
                break
            if res.wiped:
                _wipe(game, bag, gold)
                return
            for f in foes:
                if not f.alive:
                    game.record_kill(f.template)
            gold += int(res.gold * mult)
            shards += res.shards
            xp += res.xp
            bag += res.loot
            _reward_lines(game, res, mult)
            if event == "boss":
                game.regions_cleared[region] = game.regions_cleared.get(region, 0) + 1

        elif event == "gather":
            ui.say(ui.c("  " + random.choice(GATHER_FLAVOUR), "cyan"))
            found = _gather(game, region, lvl, 2 + luck.between(1, 3))
            bag += found
            ui.say("  found: " + ", ".join(found))

        elif event == "cache":
            ui.say(ui.c("  " + random.choice(CACHE_FLAVOUR), "cyan"))
            g = int((20 + lvl * 9) * mult * random.uniform(0.7, 1.5))
            s = luck.between(1, 6)
            gold += g
            shards += s
            ui.say(f"  {ui.money(g)} and {ui.shards(s)}.")

        else:
            ui.say(ui.c("  " + random.choice(SHRINE_FLAVOUR), "cyan"))
            for m in game.party:
                m.heal(int(m.max_hp * 0.35))
                m.restore_pp(6)
            ui.say(ui.c("  The pack breathes. (+35% HP, +6 PP)", "bright_green"))

        game.deepest_run = max(game.deepest_run, step)
        if step < steps:
            leaving = False
            while True:
                pack_status(game)
                choice = ui.menu("", ["Push deeper",
                                      ui.c("Extract now (keep everything)", "bright_yellow"),
                                      "Use an item"], allow_back=False)
                if choice == 0:
                    break
                if choice == 1 or choice < 0:
                    ui.say(ui.c("  You walk back towards the coin of light.", "cyan"))
                    leaving = True
                    break
                _camp(game)
            if leaving:
                break

    _extract(game, bag, gold, shards, xp)


def _gather(game, region: str, lvl: int, n: int) -> list[str]:
    pool = []
    for t in AREAS.templates_for(game.bestiary, region, bosses=False):
        pool += [d.item for d in t.drops if d.kind in ("material", "consumable")]
    if not pool:
        pool = ["Void Residue"]
    return [random.choice(pool) for _ in range(n)]


def _reward_lines(game, res, mult: float) -> None:
    ui.say()
    ui.say(ui.c("  the dark settles.", "grey"))
    ui.say(f"  {ui.money(int(res.gold*mult))}   {ui.shards(res.shards)}   "
           f"{ui.c(str(res.xp)+' xp', 'bright_green')}")
    if res.loot:
        ui.say("  loot: " + ", ".join(res.loot))
    for m in game.party:
        if not m.alive:
            continue
        for lv in m.gain_xp(res.xp):
            ui.say(ui.c(f"  {m.name} reaches level {lv}!  "
                        f"(hp {m.max_hp}, power {m.power})", "bright_yellow", "bold"))


def _camp(game) -> None:
    usable = [(n, q) for n, q in sorted(game.inventory.items())
              if q > 0 and game.items.get(n, {}).get("use")]
    if not usable:
        ui.say(ui.c("  Nothing in the pack but string and regret.", "grey"))
        return
    i = ui.menu("  Use what?", [f"{n:<20} x{q}  {ui.c(game.items[n].get('desc',''),'grey')}"
                               for n, q in usable])
    if i < 0:
        return
    name = usable[i][0]
    spec = game.items[name]["use"]
    pool = [m for m in game.party if (m.alive or spec.get("revive_pct"))]
    j = ui.menu("  On whom?", [f"{m.name:<20} {ui.bar(m.cur_hp, m.max_hp, 12)}" for m in pool])
    if j < 0:
        return
    t = pool[j]
    game.consume(name)
    if "heal_pct" in spec:
        ui.say(ui.c(f"  {t.name} recovers {t.heal(int(t.max_hp*spec['heal_pct']))} HP.", "bright_green"))
    if "pp_restore" in spec:
        ui.say(ui.c(f"  {t.name} restores {t.restore_pp(int(spec['pp_restore']))} PP.", "blue"))
    if spec.get("cleanse"):
        t.statuses.clear()
    if "revive_pct" in spec:
        t.cur_hp = max(t.cur_hp, int(t.max_hp * spec["revive_pct"]))


def _wipe(game, bag: list[str], gold: int) -> None:
    ui.say()
    ui.header("THE PACK FALLS", "you wake at the gate, emptied")
    kept = bag[: len(bag) // 2]
    lost_gold = int(gold * 0.5)
    for item in kept:
        game.add_item(item)
    game.gold += gold - lost_gold
    ui.say(ui.c(f"  Half of what you carried is gone. {lost_gold}g lost, "
                f"{len(bag) - len(kept)} items lost.", "red"))
    for m in game.roster:
        m.full_heal()
    game.advance_time(24 * 60)
    game.board = []
    ui.pause()


def _extract(game, bag: list[str], gold: int, shards: int, xp: int) -> None:
    ui.say()
    ui.header("EXTRACTION", "back through the gate")
    for item in bag:
        game.add_item(item)
    game.gold += gold
    game.shards += shards
    counts: dict[str, int] = {}
    for i in bag:
        counts[i] = counts.get(i, 0) + 1
    lines = [f"{ui.money(gold)}    {ui.shards(shards)}    {ui.c(str(xp) + ' xp', 'bright_green')}"]
    if counts:
        lines.append("")
        for name, n in sorted(counts.items()):
            lines.append(f"  {n}x {name}  {ui.c('(' + str(game.value_of(name)) + 'g each)', 'grey')}")
    ui.box(lines, title="HAUL")
    for m in game.roster:
        m.clear_battle_state()
    game.advance_time(24 * 60)
    game.board = []
    ui.pause()
