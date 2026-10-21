"""Wick's stall: he buys anything and asks nothing."""
from __future__ import annotations

from . import ui

from .entities import xp_for_level

# A preferred running order only.  The real stock list is every item that
# carries a `buy` price in data/items.json, so anything forged with a price —
# a seed, a material, a consumable — appears on the shelf without a code change.
# The old hard-coded list named seven items that no longer exist in the data,
# which is why the stall had nothing to sell and the farm could never be
# started: its seed was unbuyable.
STOCK = ["Void Salve", "Greater Salve", "Ether Dust", "Antidote Root",
         "Smoke Bomb", "Whetstone", "Phoenix Ember"]
KIND_ORDER = ["consumable", "seed", "material", "weapon", "armor",
              "accessory", "treasure", "key"]


def stock_list(game) -> list:
    """Everything the stall will sell, in a stable, readable order."""
    priced = [name for name, spec in (game.items or {}).items()
              if isinstance(spec, dict) and int(spec.get("buy") or 0) > 0
              and not str(name).startswith("_")]
    preferred = {name: index for index, name in enumerate(STOCK)}

    def sort_key(name):
        spec = game.items.get(name) or {}
        kind = str(spec.get("kind") or "material")
        kind_rank = KIND_ORDER.index(kind) if kind in KIND_ORDER else len(KIND_ORDER)
        return (preferred.get(name, len(STOCK)), kind_rank, name.lower())

    return sorted(priced, key=sort_key)


def screen(game) -> None:
    while True:
        ui.header("THE STALL", f"{game.gold}g  -  {game.shards} shards")
        pick = ui.menu("", ["Sell haul", "Buy supplies", "Sell everything unlisted (quick)",
                            "Pay the trainer" + ui.c("   turn gold into levels", "grey")],
                       back="leave")
        if pick < 0:
            return
        if pick == 0:
            _sell(game)
        elif pick == 1:
            _buy(game)
        elif pick == 2:
            _quick_sell(game)
        else:
            _train(game)


def training_cost(m) -> int:
    return int(round(70 + 22 * m.level ** 1.15))


def _train(game) -> None:
    """The only thing in town that turns coin into power."""
    if not game.roster:
        return
    rows = [f"{m.name:<24} L{m.level:<3} {ui.money(training_cost(m)):<10} "
            f"{ui.c('one level of hard work', 'grey')}" for m in game.roster]
    ui.say(ui.c("  A retired hunter runs drills behind the stall. She is not cheap.", "grey"))
    i = ui.menu("  Train whom?", rows)
    if i < 0:
        return
    m = game.roster[i]
    cost = training_cost(m)
    if cost > game.gold:
        ui.say(ui.c(f"  {cost}g. You have {game.gold}g.", "red"))
        ui.pause()
        return
    game.gold -= cost
    gain = max(1, xp_for_level(m.level + 1) - xp_for_level(m.level))
    levels = m.gain_xp(gain)
    if levels:
        ui.say(ui.c(f"  {m.name} reaches level {levels[-1]}. hp {m.max_hp}, power {m.power}",
                    "bright_yellow"))
    else:
        ui.say(ui.c(f"  {m.name} sweats through it. +{gain} xp.", "grey"))
    ui.pause()


def _sellable(game):
    keep = {q.target for q in game.quests if q.kind == "fetch"}
    out = []
    for name, qty in sorted(game.inventory.items()):
        spec = game.items.get(name, {})
        if qty <= 0 or spec.get("kind") == "key" or game.value_of(name) <= 0:
            continue
        out.append((name, qty, game.value_of(name), name in keep))
    return out


def _sell(game) -> None:
    rows = _sellable(game)
    if not rows:
        ui.say(ui.c("  Nothing here he'd take.", "grey"))
        ui.pause()
        return
    labels = [f"{n:<26} x{q:<4} {ui.money(v)} each"
              + (ui.c("   [quest item]", "bright_yellow") if flag else "")
              for n, q, v, flag in rows]
    i = ui.menu("  Sell what?", labels)
    if i < 0:
        return
    name, qty, val, flag = rows[i]
    raw = ui.ask(f"  How many? (1-{qty}, enter for all) ", str(qty))
    n = qty if raw.lower() in ("a", "all", "") else max(0, min(qty, int(raw) if raw.isdigit() else 0))
    if n <= 0:
        return
    game.consume(name, n)
    game.gold += val * n
    ui.say(ui.c(f"  Sold {n}x {name} for {val*n}g.", "yellow"))


def _quick_sell(game) -> None:
    rows = [r for r in _sellable(game) if not r[3] and game.items.get(r[0], {}).get("kind") == "material"]
    total = sum(q * v for _, q, v, _ in rows)
    if not rows:
        ui.say(ui.c("  Nothing loose to shift.", "grey"))
        ui.pause()
        return
    ui.say(ui.c(f"  {len(rows)} kinds of material, {total}g the lot.", "grey"))
    if ui.confirm("  Sell all materials not tied to a contract?"):
        for name, qty, val, _ in rows:
            game.consume(name, qty)
            game.gold += val * qty
        ui.say(ui.c(f"  +{total}g", "yellow"))
    ui.pause()


def _buy(game) -> None:
    stock = stock_list(game)
    if not stock:
        ui.say(ui.c("  Wick has nothing priced up today.", "grey"))
        ui.pause()
        return
    labels = [f"{n:<20} {ui.money(game.items[n].get('buy', 100)):<8} "
              f"{ui.c(game.items[n].get('desc',''), 'grey')}  "
              f"{ui.c('have ' + str(game.count(n)), 'grey')}" for n in stock]
    i = ui.menu("  Buy what?", labels)
    if i < 0:
        return
    name = stock[i]
    price = int(game.items[name].get("buy", 100))
    raw = ui.ask(f"  How many at {price}g? ", "1")
    n = int(raw) if raw.isdigit() else 1
    cost = price * n
    if cost > game.gold:
        ui.say(ui.c("  Not enough coin.", "red"))
        return
    game.gold -= cost
    game.add_item(name, n)
    ui.say(ui.c(f"  Bought {n}x {name} for {cost}g.", "yellow"))
