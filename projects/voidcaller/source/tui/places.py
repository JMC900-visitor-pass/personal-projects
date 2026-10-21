"""Places, and what you can do in them. Every list behaves identically."""
from __future__ import annotations

import math
import os
import time

from .screen import BOLD, DIM, ELEMENT_COLOR, Region

EVENT_PACE = {"hit": 0.34, "miss": 0.24, "skill": 0.22, "faint": 0.4,
              "round": 0.24, "pressure": 0.4, "end": 0.4, "level": 0.4,
              "summon": 0.5, "claimed": 0.3, "capture": 1.1, "flee": 1.0}
# How long the bind bar takes to fill before it reports held or cracked.
CAPTURE_FILL_SECONDS = 0.85

CRUMB = {
    "main": "VOIDCALLER", "main.saves": "VOIDCALLER › CONTINUE",
    "main.starter": "VOIDCALLER › CHOOSE COMPANION",
    "main.layout": "VOIDCALLER › SCREEN LAYOUT",
    "main.settings": "VOIDCALLER › SETTINGS", "main.look": "VOIDCALLER › APPEARANCE",
    "gate": "THE GATE", "gate.void": "THE GATE › THE VOID",
    "gate.pack": "THE GATE › THE PACK", "gate.pack.card": "THE GATE › THE PACK ›",
    "gate.pack.build": "THE GATE › THE PACK › BUILD",
    "gate.pack.move": "THE GATE › THE PACK › MOVE ›",
    "gate.ledger": "THE GATE › THE LEDGER", "gate.ledger.card": "THE GATE › THE LEDGER ›",
    "gate.ledger.move": "THE GATE › THE LEDGER › MOVE ›",
    "gate.stall": "THE GATE › THE STALL", "gate.circle": "THE GATE › THE CIRCLE",
    "gate.board": "THE GATE › THE BOARD", "gate.look": "THE GATE › THE LOOK",
    "gate.mission": "THE GATE › MISSION FRONT",
    "gate.layout": "THE GATE › SCREEN LAYOUT", "gate.farm": "THE GATE › THE FARM",
    "gate.farm.plant": "THE FARM › CHOOSE CROP",
    "gate.farm.quantity": "THE FARM › ALLOCATE PLOTS",
    "gate.craft": "THE GATE › THE WORKSHOP", "gate.pack.equip": "THE PACK › EQUIPMENT",
    "void": "IN THE VOID",
    "battle": "A FIGHT", "spoils": "THE SPOILS",
}

# A destination in the field folio owns the whole work surface.  These are not
# tabs in a generic dashboard: each is a distinct place with its own tools and
# information hierarchy.
FOLIO_PAGES = {
    "gate.farm", "gate.pack", "gate.pack.build", "gate.stall",
    "gate.void", "void", "gate.board", "gate.mission", "gate.craft",
}
FOLIO_TITLES = {
    "gate.farm": "SOLO FARM / GARDEN",
    "gate.pack": "PARTY / FIELD CODEX",
    "gate.pack.build": "COMPANION / SKILL PATHS",
    "gate.stall": "VILLAGE SHOP / PACK",
    "gate.void": "VOID ATLAS / EXPEDITION",
    "void": "VOID EXPEDITION / ROUTE",
    "gate.board": "HUNT BOARD / OPERATIONS",
    "gate.mission": "OPERATION BRIEF / RAID PLAN",
    "gate.craft": "FIELD WORKSHOP / RECIPES",
}


def is_folio_page(place: str) -> bool:
    return place in FOLIO_PAGES


def folio_title(place: str) -> str:
    return FOLIO_TITLES.get(place, "FIELD FOLIO")


def clip(text: str, width: int) -> str:
    text = str(text or "")
    if len(text) <= width:
        return text
    cut = text[:width].rsplit(" ", 1)[0]
    return (cut or text[:width - 1]) + "…"


def el_col(name: str) -> str:
    return ELEMENT_COLOR.get(str(name or "none").casefold(), "faint")


def rarity_mark(row: dict | None) -> str:
    """Small visual rarity language used everywhere a creature is named."""
    row = row or {}
    return row.get("rarity_mark") or {
        "Common": "○", "Uncommon": "□", "Rare": "★", "Epic": "★★",
    }.get(row.get("rarity"), "○")


def rarity_fg(row: dict | None) -> str:
    """Compatibility name: creature identity colour belongs to its Type."""
    row = row or {}
    combat_type = row.get("type") or row.get("primary")
    return el_col(combat_type) if combat_type else "bright"


def breadcrumb(app) -> str:
    crumb = CRUMB.get(app.place, app.place.upper())
    if app.place.endswith(".move") and getattr(app, "focus_move_name", ""):
        return f"{crumb} {app.focus_move_name.upper()}"
    if app.place.endswith(".card") and app.focus_uid is not None:
        name = getattr(app, "focus_name", "")
        return f"{crumb} {name.upper()}"
    return crumb


def keyhints(app) -> str:
    base = "WASD/arrows move · enter select · esc back · pgup log · ? help"
    if app.place == "gate":
        return "WASD move · enter visit · V void · Q missions · F farm · K craft · P party · C index"
    if app.place == "gate.mission":
        return "WASD choose · enter confirm · esc mission board · operation progress is live"
    if app.place == "gate.farm":
        return "WASD choose · enter tend · 1-4 action cards · esc returns to the gate"
    if app.place.startswith("gate.farm"):
        return "WASD choose · enter plant/harvest · esc back · crops use world time"
    if app.place == "gate.craft":
        return "WASD browse recipe · enter craft · esc back · books unlock blueprints"
    if app.place == "gate.void":
        return "WASD choose region or depth · enter select · esc returns to the gate"
    if app.place == "gate.board":
        return "WASD choose a contract · enter focus · esc returns to the gate"
    if app.place == "gate.look":
        return "↑↓ move · enter chooses or turns it up · esc back · colour <role> <#hex>"
    if app.place.endswith("layout"):
        return "↑↓ move · enter changes the terminal layout · esc back · layout <name>"
    if app.place == "battle":
        mode = getattr(app, "battle_mode", "main")
        if mode in ("bag", "switch"):
            return "WASD choose · enter confirm · esc returns to the battle menu"
        return "arrows move · enter select · esc back · T target · P party"
    if app.place == "spoils":
        return "↑↓ move · space leaves a thing behind · enter takes the rest"
    if app.place == "gate.pack":
        return "WASD select · enter inspect or use a move · 1-4 field actions · esc returns to the gate"
    if app.place == "gate.pack.build":
        return "WASD choose a node · enter spend Skill Point · esc returns to the companion card"
    if app.place == "gate.stall":
        return "WASD browse pack and stock · enter buy or sell · 1-4 counter actions · esc returns to the gate"
    if app.place == "void":
        return "WASD choose a way on · enter descend · E extracts the expedition"
    return base


def item(app, r: Region, y: int, label: str, action=None, hint: str = "",
         fg: str = "text", tail: str = "", tail_fg: str = "faint",
         hint_at: int = 26, mark: str = "", x: int = 0) -> int:
    i = len(app.items)
    app.items.append({"action": action, "label": label,
                      "nav": (r.x + max(x + 2, r.w // 3), r.y + y)})
    sel = i == app.cursor
    if sel:
        r.put(x, y, "›", "accent", BOLD)
    if mark:
        r.put(x + 1, y, mark, "amber", BOLD)
    r.put(x + 2, y, label, "bright" if sel else fg, BOLD if sel else 0)
    if hint:
        r.put(max(hint_at, x + len(label) + 4), y, hint, "dim" if sel else "faint")
    if tail:
        r.right(x, y, r.w - x - 1, tail, tail_fg)
    app.click_map[(r.y + y, r.x + x, r.x + r.w)] = ("index", i)
    return i


def window(app, total: int, height: int) -> tuple[int, int]:
    """Keep the cursor inside a scrolling list."""
    if total <= height:
        return 0, total
    start = max(0, min(app.cursor - height // 2, total - height))
    return start, start + height


# --- field-folio building blocks ------------------------------------------
def folio_panel(r: Region, x: int, y: int, w: int, h: int, title: str,
                right: str = "") -> Region:
    """Frame a calm work area and return its safe inner writing region."""
    w = max(4, min(w, r.w - x))
    h = max(4, min(h, r.h - y))
    r.s.frame(r.x + x, r.y + y, w, h, "line", title, "dim", right)
    return r.sub(x + 1, y + 1, w - 2, h - 2)


def folio_action(app, r: Region, x: int, y: int, w: int, label: str,
                 action=None, note: str = "", key: str = "") -> int:
    """A large, low-noise action card used along a folio's bottom edge."""
    i = len(app.items)
    app.items.append({"action": action, "label": label,
                      "nav": (r.x + x + max(2, w // 2), r.y + y + 2)})
    selected = i == app.cursor
    edge = "amber" if selected else "line"
    r.s.frame(r.x + x, r.y + y, w, 6, edge)
    if selected:
        r.put(x + 2, y + 1, "›", "amber", BOLD)
    if key:
        r.right(x + 1, y + 1, w - 2, f"[{key}]", "amber" if selected else "faint")
    r.put(x + 4, y + 1, clip(label.upper(), max(4, w - 8)),
          "amber" if selected else "text", BOLD)
    if note:
        r.wrap(x + 4, y + 3, w - 7, note, "dim", limit=2)
    for row in range(y, y + 6):
        app.click_map[(r.y + row, r.x + x, r.x + x + w)] = ("index", i)
    return i


def folio_stat_stack(r: Region, stats: dict, x: int, y: int, width: int) -> None:
    """One-column combat bars for a narrow information rail."""
    keys = ("atk", "def", "mag", "res", "spd")
    ceiling = max(10, max(int(stats.get(key, 0)) for key in keys))
    bar_w = max(7, width - 11)
    for row, key in enumerate(keys):
        value = int(stats.get(key, 0))
        yy = y + row * 2
        r.put(x, yy, key.upper(), "faint", BOLD)
        r.bar(x + 5, yy, bar_w, value, ceiling,
              "amber" if key in ("atk", "mag") else "green" if key in ("def", "res") else "cyan")
        r.right(x, yy, width, str(value), "text")


def _folio_item_icon(spec: dict) -> list[str]:
    """A deliberately tiny, stable glyph rather than generated item art."""
    kind = str(spec.get("kind") or "material").lower()
    if kind in ("seed", "crop"):
        return ["   .   ", "  /|\\  ", "   |   ", "  / \\  "]
    if kind in ("weapon", "armor", "accessory", "equipment"):
        return ["   /\\  ", "  /  \\ ", "    || ", "    || "]
    if kind in ("book", "craft_book") or spec.get("book"):
        return ["  ____ ", " / __/ ", " |  |  ", " |__|  "]
    if spec.get("use"):
        return ["   __  ", "  |  | ", "  |~~| ", "   ||  "]
    return ["  .--. ", " / .. \\ ", " | :: |", "  '--' "]


# --- the rolling history ----------------------------------------------------
def event_line(e: dict) -> tuple[str, str]:
    k = e.get("k")
    if k == "battle_start":
        return f"{e['title']} — {', '.join(e['enemies'])}", "accent"
    if k == "switch":
        return (f"{e['who']} {'steps forward' if e.get('side') == 'party' else 'appears'}.",
                "accent" if e.get("side") == "party" else "red")
    if k == "round":
        return f"— round {e['n']} —", "faint"
    if k == "skill":
        el = f" {e['element']}" if e.get("element") not in ("none", None) else ""
        return f"{e['actor']} uses {e['skill']}{el} on {', '.join(e['targets'])}", "text"
    if k == "guard":
        return f"{e['actor']} uses {e.get('skill', 'Dodge')} — 45% less this round.", "dim"
    if k == "miss":
        return f"  {e['target']} slips it · {e['chance']:.0f}% to connect", "faint"
    if k == "hit":
        head = "CRITICAL  " if e["crit"] else "  "
        extra = f" ×{abs(e['mult']):g} {e['label']}" if abs(e["mult"] - 1) > 0.01 else ""
        return (f"{head}-{e['amount']}{extra}  →  {e['target']} "
                f"{e['hp']}/{e['max_hp']}",
                "amber" if e["crit"] else "red")
    if k == "status":
        return ((f"  {e['target']} is {e['status']} ({e['rounds']})", "magenta")
                if e["applied"] else
                (f"  {e['target']} shrugs off {e['status']}", "faint"))
    if k == "claimed":
        left = f", left {e['left']}" if e.get("left") else ""
        return (f"took {e['gold']}g, {e['shards']} shards, {e['xp']} xp and "
                f"{e['taken']} pieces of loot{left}", "accent")
    if k == "stat":
        way = "up" if e["amount"] > 0 else "down"
        return f"  {e['target']} {e['stat'].upper()} {way} {abs(e['amount'])*100:.0f}%", "cyan"
    if k == "heal":
        return f"  {e['target']} +{e['amount']} hp", "green"
    if k == "drain":
        return f"  {e['actor']} drains {e['amount']} hp", "green"
    if k == "dot":
        return f"  {e['who']} takes {e['amount']} {e['status']}", "magenta"
    if k == "skip":
        return f"  {e['who']} cannot act ({e['reason']})", "faint"
    if k == "faint":
        return f"  {e['who']} falls.", "amber" if e["side"] == "enemy" else "red"
    if k == "pressure":
        return f"  the Void leans in — {e['pct']}% to everything", "magenta"
    if k == "flee":
        return ((f"  {e['who']} slips away." if e["success"]
                 else f"  {e['who']} is cornered — no way out."),
                "green" if e["success"] else "red")
    if k == "level":
        return f"{e['who']} reaches level {e['level']} — hp {e['hp']}, power {e['power']}", "amber"
    if k == "end":
        return f"  {str(e['result']).upper()}", "accent"
    if k == "found":
        return f"found {', '.join(e['items'])}", "green"
    if k == "cache":
        return f"{e['gold']}g and {e['shards']} shards", "amber"
    if k == "shrine":
        return f"the pack breathes (+{e['hp']}% hp, +{e.get('pp', 0)} PP)", "green"
    if k == "extract":
        got = ", ".join(f"{v}× {kk}" for kk, v in (e.get("items") or {}).items())
        return (f"extracted — {e['gold']}g, {e['shards']} shards, {e['xp']} xp, "
                f"depth {e['depth']}/{e['rows']}" + (f" · {got}" if got else ""), "accent")
    if k == "wipe":
        return f"the pack falls — lost {e['gold_lost']}g and {e['items_lost']} items", "red"
    if k == "item":
        return f"{e['name']} used on {e['target']}", "cyan"
    if k == "pp_restore":
        return f"{e['target']} recovers {e['amount']} PP", "cyan"
    if k == "capture":
        return ((f"{e['target']} is bound." if e["success"]
                 else f"the seal cracks — {e['target']} breaks free."),
                "accent" if e["success"] else "faint")
    if k == "skill_tree":
        return f"{e['who']} advances their skill path · {e['points']} SP left", "amber"
    if k == "sold":
        return f"sold {e['qty']}× {e['name']} for {e['gold']}g", "amber"
    if k == "bought":
        return f"bought {e['qty']}× {e['name']} for {e['gold']}g", "amber"
    if k == "crafted":
        return f"crafted {e['qty']}× {e['name']} at the village workshop", "accent"
    if k == "trained":
        return f"{e['who']} trains hard — level {e['level']} for {e['gold']}g", "amber"
    if k == "summon":
        return (f"{e['name'].upper()} — {e['title']} · {e['rarity']} L{e['level']} · "
                f"hp {e['hp']} · power {e['power']}", "amber")
    if k == "released":
        return f"{e['who']} unravels. +{e['shards']} shards", "magenta"
    if k == "accepted":
        return f"contract signed with {e['giver']} — {e['title']}", "accent"
    if k == "paid":
        return f"{e['giver']} counts it out — {e['title']}: {e['gold']}g, {e['shards']} shards", "amber"
    if k == "note":
        return e.get("text", ""), "dim"
    return "", "faint"


# --- the right-hand rail ----------------------------------------------------
def sidebar(app, r: Region) -> None:
    """Compact party cards plus the currently tracked contract.

    The map gets to breathe; this rail is deliberately dense enough to make
    party composition and the next objective readable at a glance.
    """
    st = app.state
    r.put(1, 0, "PARTY", "dim", BOLD)
    r.right(0, 0, r.w - 1, f"{len(st['party'])}/4", "faint")
    row = 2
    battle = st.get("battle")
    live = {u["uid"]: u for u in (battle["party"] if battle else [])}
    for m in st["party"][:4]:
        u = live.get(m["uid"], m)
        down = u.get("hp", 1) <= 0
        full = app.s.unit(next(x for x in app.s.game.roster if x.uid == m["uid"]), full=True)
        bob = "◆" if (int(time.monotonic() * 2) + row) % 2 else "◇"
        r.put(1, row, bob, "accent" if not down else "faint")
        r.put(3, row, f"{rarity_mark(u)} {clip(u['name'].upper(), max(7, r.w - 14))}",
              rarity_fg(u) if not down else "faint", BOLD)
        r.right(0, row, r.w - 1, f"L{m['level']}", "accent")
        if down:
            r.put(2, row + 1, "── DOWN ──", "red")
            row += 3
            continue
        bar_w = max(7, min(12, r.w - 17))
        r.put(2, row + 1, "HP", "faint")
        r.bar(5, row + 1, bar_w, u["hp"], u["max_hp"])
        r.right(0, row + 1, r.w - 1, f"{u['hp']}/{u['max_hp']}", "dim")
        stats = full["stats"]
        r.put(2, row + 2, f"SP.ATK {stats['mag']:>3}  SPD {stats['spd']:>3}", "faint")
        row += 4
    row = min(row, r.h - 6)
    r.hline(1, row, r.w - 2, "line")
    q = st.get("mission") or (st.get("board") or [None])[0]
    r.put(1, row + 1, "TRACKED QUEST", "dim", BOLD)
    if q:
        have = q.get("have", 0)
        qty = max(1, q.get("qty", 1))
        r.put(2, row + 2, clip(q["title"].upper(), r.w - 4), "amber", BOLD)
        r.bar(2, row + 3, max(8, r.w - 5), have, qty, "accent")
        r.put(2, row + 4, clip(f"{q.get('target', 'unknown')} · {q.get('where', 'anywhere')}", r.w - 4), "faint")
    else:
        r.put(2, row + 3, "No hunt tracked. Visit the Board.", "faint")


# --- the gate ---------------------------------------------------------------
def hub_tile(app, r: Region, x: int, y: int, w: int, h: int, title: str,
             copy: str, action, symbol: str, fg: str = "text") -> int:
    """A large, clickable location card for the town's tabletop hub."""
    i = len(app.items)
    app.items.append({"action": action, "label": title,
                      "nav": (r.x + x + w // 2, r.y + y + h // 2)})
    selected = i == app.cursor
    border = "accent" if selected else "line"
    title_fg = "bright" if selected else fg
    r.put(x, y, "╔" + "═" * max(1, w - 2) + "╗", border, BOLD if selected else 0)
    for yy in range(y + 1, y + h - 1):
        r.put(x, yy, "║", border)
        r.put(x + w - 1, yy, "║", border)
    r.put(x, y + h - 1, "╚" + "═" * max(1, w - 2) + "╝", border, BOLD if selected else 0)
    r.put(x + 2, y + 1, symbol, "accent" if selected else "dim", BOLD)
    r.put(x + 4, y + 1, clip(title.upper(), max(1, w - 6)), title_fg, BOLD)
    r.wrap(x + 2, y + 3, max(1, w - 4), copy, "dim" if selected else "faint", limit=2)
    if selected:
        r.put(x + 2, y + h - 2, "ENTER TO VISIT", "accent", BOLD)
    for yy in range(y, y + h):
        app.click_map[(r.y + yy, r.x + x, r.x + x + w)] = ("index", i)
    return i


def grid_item(app, r: Region, x: int, y: int, w: int, label: str, action,
              tail: str = "", chosen: bool = False, fg: str = "text") -> int:
    """A compact segmented choice used by the atlas and other dense boards."""
    i = len(app.items)
    app.items.append({"action": action, "label": label,
                      "nav": (r.x + x + w // 2, r.y + y)})
    selected = i == app.cursor
    col = "accent" if selected else "faint"
    r.put(x, y, "›" if selected else "·", col, BOLD if selected else 0)
    r.put(x + 2, y, clip(label, max(4, w - len(tail) - 4)),
          "bright" if selected else fg, BOLD if selected else 0)
    if tail:
        r.right(x, y, w - 1, tail, "dim")
    app.click_map[(r.y + y, r.x + x, r.x + x + w)] = ("index", i)
    return i


def place_gate(app, r: Region) -> None:
    """A dense command deck: the town is visible at a glance and stays alive."""
    st = app.state
    pulse = ">" if int(time.monotonic() * 2) % 2 else ":"
    r.put(1, 0, f"{pulse} COMMAND DECK // WILDERWOOD", "accent", BOLD)
    r.right(0, 0, r.w - 1, "LIVE SETTLEMENT FEED", "green")
    r.hline(1, 1, r.w - 2, "line", "-")

    choices = [
        ("VOID ATLAS", "gate.void", "V"), ("MISSION BOARD", "gate.board", "Q"),
        ("FARM", "gate.farm", "F"), ("WORKSHOP", "gate.craft", "K"),
        ("PARTY", "gate.pack", "P"), ("CODEX", "gate.ledger", "C"),
        ("SHOP", "gate.stall", "O"), ("SYSTEM", "gate.look", "L"),
    ]
    gap, x0 = 1, 1
    cell_w = max(14, (r.w - 2 - gap * 3) // 4)
    for i, (label, place, key) in enumerate(choices):
        x = x0 + (i % 4) * (cell_w + gap)
        y = 3 + i // 4 * 2
        grid_item(app, r, x, y, cell_w, label, lambda p=place: app.go(p), tail=key)

    r.hline(1, 7, r.w - 2, "line", "-")
    mission = st.get("mission")
    r.put(2, 8, "ACTIVE RAID", "amber", BOLD)
    if mission:
        r.put(16, 8, clip(mission["title"].upper(), 30), "bright", BOLD)
        r.right(0, 8, r.w - 2, f"{mission['where'].upper()}  {mission['have']}/{mission['qty']}", "cyan")
        stages = max(1, mission.get("stages", 1))
        r.bar(2, 10, max(20, r.w - 20), mission.get("stage", 0), stages, "accent")
        r.right(0, 10, r.w - 2,
                f"ROUND {mission.get('stage', 0)}/{stages}  {mission.get('stages_left', stages)} LEFT",
                "accent" if mission.get("deployed") else "faint", BOLD)
    else:
        r.put(16, 8, "NO CONTRACT SIGNED", "faint")
        if st.get("board"):
            r.put(2, 10, "The board has work. Nothing begins until you choose it.", "dim")
        else:
            r.put(2, 10, "No missions posted. Add one in the Forge when this world is ready.", "dim")

    r.hline(1, 12, r.w - 2, "line", "-")
    farm = st.get("farm") or {}
    party = st.get("party") or []
    inv = st.get("inventory") or []
    r.put(2, 13, "SETTLEMENT", "dim", BOLD)
    r.put(2, 15, "FARM", "green", BOLD)
    r.put(10, 15, f"{farm.get('total', 0) - farm.get('empty', 0)}/{farm.get('total', 0)} plots",
          "text")
    r.put(29, 15, f"{farm.get('ready', 0)} ready", "accent" if farm.get("ready") else "faint")
    r.put(2, 16, "PARTY", "cyan", BOLD)
    names = ", ".join(m["name"] for m in party) or "none"
    bob = "^" if int(time.monotonic() * 3) % 2 else "_"
    r.put(10, 16, clip(f"{bob} {names}", r.w - 24), "text")
    r.right(0, 16, r.w - 2, f"{len(party)}/4 ACTIVE", "faint")
    r.put(2, 17, "CODEX", "magenta", BOLD)
    r.put(10, 17, f"{st.get('seen', 0)}/{st.get('species', 0)} species", "text")
    r.put(29, 17, f"{len(st.get('craft_books', []))} craft books", "faint")
    r.put(2, 18, "BAG", "amber", BOLD)
    r.put(10, 18, f"{sum(i['qty'] for i in inv)} items", "text")
    r.right(0, 18, r.w - 2, "Rain ticks against the terminal glass.", "faint")


def place_farm(app, r: Region) -> None:
    """The farm is a place to tend, not a mini-widget beside a dashboard."""
    st = app.state
    farm = st.get("farm") or {"plots": [], "total": 4, "empty": 4, "ready": 0}
    plots = farm.get("plots") or []
    crops = farm.get("crops") or []
    selected = next((crop for crop in crops if crop["key"] == app.farm_crop),
                    crops[0] if crops else None)

    left = folio_panel(r, 0, 0, 27, 28, "PLOT ALLOCATION")
    grid = folio_panel(r, 28, 0, 58, 28, "FARM PLOTS",
                       f"{max(1, farm.get('cols', 1))} x {max(1, farm.get('cols', 1))}")
    season = folio_panel(r, 87, 0, 27, 11, "SEASONAL TIMELINE")
    inventory = folio_panel(r, 87, 12, 27, 16, "FARM INVENTORY",
                            f"{farm.get('total', 0) - farm.get('empty', 0)}/{farm.get('total', 0)}")

    total, used = int(farm.get("total", 0)), int(farm.get("total", 0) - farm.get("empty", 0))
    for y, label, value, fg in (
        (1, "TOTAL PLOTS", f"{total}", "green"),
        (3, "IN USE", f"{used} / {total}", "text"),
        (5, "AVAILABLE SOIL", str(farm.get("empty", 0)), "green"),
        (7, "PLOT SIZE", "1 x 1", "text"),
    ):
        left.put(1, y, label, "faint", BOLD)
        left.right(1, y, left.w - 2, value, fg)
    left.hline(1, 9, left.w - 2, "line", "-")
    left.put(1, 11, "SELECTED CROP", "dim", BOLD)
    if selected:
        left.s.frame(left.x + 1, left.y + 13, 8, 6, "green")
        if selected.get("id"):
            from engine import v2_art
            left.s.sprite(str(v2_art.crop_path(selected["id"], "seed")), left.x + 3, left.y + 14, 4, 3)
        left.put(4, 14, selected.get("mark", "*")[:1], "green", BOLD)
        left.put(11, 13, clip(selected["label"].upper(), left.w - 12), "green", BOLD)
        left.put(11, 15, clip(f"SEED  {selected['seed']}", left.w - 11), "faint")
        left.put(11, 16, f"OWNED  {selected.get('seeds', 0)}", "text")
        hours, mins = divmod(int(selected["cycle"]), 60)
        left.put(11, 18, f"GROW  {hours:02d}:{mins:02d}", "cyan")
        left.put(1, 20, "HARVEST YIELD", "faint", BOLD)
        left.put(1, 21, clip(f"{selected['yield']} - {selected['yield'] + 2}  {selected['item']}", left.w - 2), "green")
    else:
        left.put(1, 14, "No crop entries yet.", "faint")
        left.wrap(1, 16, left.w - 2, "Create a crop and its seed in the Forge to start farming.", "dim", limit=3)

    cols = max(1, int(farm.get("cols", 1)))
    rows = max(1, (len(plots) + cols - 1) // cols)
    cell_w = max(7, (grid.w - 2 - (cols - 1)) // cols)
    cell_h = max(3, min(4, (grid.h - 4) // rows))
    phase = int(time.monotonic() * 2) % 2
    for plot in plots:
        col, row = plot["index"] % cols, plot["index"] // cols
        x, y = 1 + col * (cell_w + 1), 2 + row * cell_h
        status = plot.get("status", "empty")
        fg = "amber" if status == "ready" else "green" if status == "growing" else "line"
        grid.s.frame(grid.x + x, grid.y + y, cell_w, min(cell_h, grid.h - y), fg)
        if plot.get("sprite_asset"):
            grid.s.sprite(plot["sprite_asset"], grid.x + x + max(1, cell_w // 2 - 2), grid.y + y + 1, 4, 2)
        grid.put(x + 1, y + 1, f"{chr(65 + row)}{col + 1}", "faint")
        mark = plot.get("mark", ".")
        if status == "growing" and phase:
            mark = mark.lower()
        label = "READY" if status == "ready" else "WATERED" if status == "growing" else "EMPTY"
        grid.put(x + max(1, (cell_w - len(mark)) // 2), y + 1, mark, fg, BOLD)
        if cell_h >= 4:
            grid.s.center(grid.y + y + 2, label, fg if status != "empty" else "faint",
                          x=grid.x + x, w=cell_w)
    grid.hline(1, grid.h - 3, grid.w - 2, "line", "-")
    grid.put(2, grid.h - 2, "SPROUT", "green")
    grid.put(14, grid.h - 2, "WATERED", "cyan")
    grid.put(29, grid.h - 2, "READY", "amber")
    grid.put(41, grid.h - 2, "EMPTY", "faint")

    seasons = ("SPRING", "SUMMER", "AUTUMN", "WINTER")
    current_season = (int(st.get("day", 1)) - 1) // 28 % len(seasons)
    x = 1
    for i, name in enumerate(seasons):
        active = i == current_season
        season.put(x, 2, name[:3], "green" if active else "faint", BOLD if active else 0)
        season.put(x, 4, "●" if active else "○", "green" if active else "line")
        if i < len(seasons) - 1:
            season.put(x + 1, 4, "---", "green" if i < current_season else "line")
        x += 7
    season.put(1, 7, f"DAY {st.get('day', 1)} OF {current_season * 28 + 28}", "green")
    season.put(1, 8, "BEST GROWTH   " + ("* * *" if selected else "—"), "faint")

    inventory.put(1, 1, "SEED / CROP", "faint", BOLD)
    y = 3
    crop_rows = [(crop["label"], crop.get("seeds", 0), "green") for crop in crops]
    made = list((farm.get("produced") or {}).items())
    for name, qty, fg in (crop_rows + [(name, qty, "text") for name, qty in made])[:8]:
        inventory.put(1, y, clip(name.upper(), inventory.w - 8), fg)
        inventory.right(1, y, inventory.w - 2, f"x {qty}", "text")
        y += 2
    if y == 3:
        inventory.put(1, y, "Nothing stored yet.", "faint")
    inventory.hline(1, inventory.h - 3, inventory.w - 2, "line", "-")
    inventory.put(1, inventory.h - 2, "HARVEST IS MANUAL", "faint", BOLD)

    y = 29
    action_w = 27
    folio_action(app, r, 1, y, action_w, "Plant", lambda: app.go("gate.farm.plant"),
                 "Allocate seed to empty soil.", "1")
    folio_action(app, r, 29, y, action_w, "Harvest",
                 (lambda: app.act("harvest_farm", {})) if farm.get("ready") else None,
                 f"{farm.get('ready', 0)} mature crop{'s' if farm.get('ready', 0) != 1 else ''} ready.", "2")
    folio_action(app, r, 57, y, action_w, "Expand Plot",
                 (lambda: app.act("expand_farm", {})) if farm.get("can_expand") else None,
                 (f"Next terrace: {farm.get('next_total')} plots · {farm.get('expand_cost', 0)}g"
                  if farm.get("can_expand") else "The terrace is fully expanded."), "3")
    folio_action(app, r, 85, y, action_w, "Visit Shop", lambda: app.go("gate.stall"),
                 "Buy seed, books and field supplies.", "4")
    r.put(1, r.h - 1, "SOLO FARM  ·  seed is spent per plot  ·  crops advance with world time", "faint")


def choose_farm_crop(app, key: str) -> None:
    app.farm_crop = key
    app.go("gate.farm.quantity")


def place_farm_plant(app, r: Region) -> None:
    farm = app.state.get("farm") or {}
    r.put(2, 0, "CHOOSE A CROP", "green", BOLD)
    r.right(0, 0, r.w - 1, f"{farm.get('empty', 0)} EMPTY PLOTS", "faint")
    r.put(2, 1, "Seed is spent per plot. Nothing is planted until you confirm a quantity.", "faint")
    if not farm.get("crops"):
        r.put(2, 5, "NO CROPS IN THE FARM LEDGER", "amber", BOLD)
        r.put(2, 7, "In the Forge, add a Farm Crop and an Item for its seed.", "faint")
        item(app, r, 11, "BACK TO FARM", app.back, fg="accent")
        return
    y = 3
    for crop in farm.get("crops", []):
        hrs = crop["cycle"] / 60
        item(app, r, y, crop["label"], lambda key=crop["key"]: choose_farm_crop(app, key),
             hint=f"{crop['seed']}  have {crop['seeds']}", hint_at=22,
             tail=f"{hrs:g}h -> {crop['yield']}x {crop['item']}",
             tail_fg="green" if crop["seeds"] else "faint",
             fg="text" if crop["seeds"] and farm.get("empty") else "dim")
        y += 3
    item(app, r, y + 1, "BACK TO FARM", app.back)


def finish_planting(app, crop: str, qty: int) -> None:
    app.act("plant_crop", {"crop": crop, "qty": qty})
    app.root("gate")
    app.go("gate.farm")


def place_farm_quantity(app, r: Region) -> None:
    farm = app.state.get("farm") or {}
    crop = next((x for x in farm.get("crops", []) if x["key"] == app.farm_crop), None)
    if crop is None:
        app.back()
        return
    maximum = min(farm.get("empty", 0), crop.get("seeds", 0))
    r.put(2, 0, f"ALLOCATE // {crop['label']}", "green", BOLD)
    r.put(2, 2, f"EMPTY PLOTS  {farm.get('empty', 0)}", "faint")
    r.put(28, 2, f"SEED OWNED  {crop.get('seeds', 0)}", "faint")
    r.put(2, 4, "HOW MANY PLOTS?", "dim", BOLD)
    if maximum <= 0:
        r.put(2, 6, f"You need {crop['seed']} and an empty plot.", "amber")
        item(app, r, 9, "VISIT SHOP", lambda: app.go("gate.stall"), fg="accent")
    else:
        options = list(range(1, min(maximum, 8) + 1))
        if maximum > 8:
            options.append(maximum)
        for i, qty in enumerate(options):
            item(app, r, 6 + i, f"{qty} PLOT{'S' if qty != 1 else ''}",
                 lambda q=qty: finish_planting(app, crop["key"], q),
                 hint=f"spend {qty}x {crop['seed']}", hint_at=18,
                 tail="ALL AVAILABLE" if qty == maximum else "")
    item(app, r, min(r.h - 2, 8 + max(1, maximum)), "BACK", app.back)


def open_farm_worker(app, uid: int, name: str) -> None:
    app.focus_uid, app.focus_name = uid, name
    app.go("gate.farm.job")


def place_farm_assign(app, r: Region) -> None:
    farm = app.state.get("farm") or {}
    assigned = {w["uid"]: w for w in farm.get("workers", [])}
    r.put(2, 0, "WORK ROTA", "dim", BOLD)
    r.right(0, 0, r.w - 1, "active party members must stay ready", "faint")
    for y, mon in enumerate((farm.get("available") or [])[:16], 2):
        worker = assigned.get(mon["uid"])
        action = lambda uid=mon["uid"], name=mon["name"]: open_farm_worker(app, uid, name)
        item(app, r, y, clip(mon["name"], 22), action,
             hint=(worker["job_label"] if worker else
                   "ACTIVE PARTY" if mon["in_party"] else "idle"), hint_at=27,
             fg="faint" if mon["in_party"] else "text",
             tail=f"L{mon['level']}")
    item(app, r, min(r.h - 2, len(farm.get("available") or []) + 4), "Back", app.back)


def assign_farm_job(app, uid: int, job: str) -> None:
    app.act("assign_worker", {"uid": uid, "job": job})
    app.back()


def place_farm_job(app, r: Region) -> None:
    mon = next((m for m in app.state.get("roster", []) if m["uid"] == app.focus_uid), None)
    if mon is None:
        app.back()
        return
    farm = app.state.get("farm") or {}
    current = next((w for w in farm.get("workers", []) if w["uid"] == mon["uid"]), None)
    r.put(2, 0, mon["name"].upper(), "bright", BOLD)
    r.put(2, 1, "Choose the job this creature will perform while you hunt.", "faint")
    y = 3
    for job in farm.get("jobs", []):
        item(app, r, y, job["label"].title(),
             lambda key=job["key"]: assign_farm_job(app, mon["uid"], key),
             hint=f"{job['item']} every {job['cycle']//60}h", hint_at=24,
             mark="•" if current and current["job"] == job["key"] else "")
        y += 2
    if current:
        item(app, r, y + 1, "Remove from the Rota",
             lambda: (app.act("unassign_worker", {"uid": mon["uid"]}), app.back()),
             fg="red")
    item(app, r, y + 3, "Back", app.back)


# --- crafting --------------------------------------------------------------
def _craft_focus(app, recipes: list[dict]) -> dict | None:
    """Keep a blueprint on the bench while the cursor visits an action card."""
    visible = recipes[:10]
    if 0 <= app.cursor < len(visible):
        app.craft_focus_id = visible[app.cursor]["id"]
    wanted = getattr(app, "craft_focus_id", "")
    return next((row for row in recipes if row["id"] == wanted),
                visible[0] if visible else None)


def place_craft(app, r: Region) -> None:
    """A full bench: blueprints, selected result, and the material pack."""
    st = app.state
    recipes = st.get("recipes") or []
    unknown = int(st.get("unknown_recipes", 0))
    library = folio_panel(r, 0, 0, 27, 28, "BLUEPRINT LIBRARY",
                          f"{len(recipes)} KNOWN")
    bench = folio_panel(r, 28, 0, 58, 28, "CRAFTING BENCH",
                        f"{st.get('gold', 0)}g ON HAND")
    pack = folio_panel(r, 87, 0, 27, 28, "MATERIAL PACK",
                       f"{unknown} LOCKED")

    library.put(1, 1, "FIELD BOOKS", "faint", BOLD)
    library.put(1, 2, "Known recipes are ready", "faint")
    library.put(1, 3, "to lay out on the bench.", "faint")
    if not recipes:
        library.hline(1, 5, library.w - 2, "line", "-")
        library.put(1, 7, "NO BLUEPRINTS", "amber", BOLD)
        library.wrap(1, 9, library.w - 2,
                     "Buy a craft book at the village shop to add its recipes here.",
                     "dim", limit=3)
    else:
        library.hline(1, 5, library.w - 2, "line", "-")
        for n, recipe in enumerate(recipes[:10]):
            y = 7 + n * 2
            result = recipe["result"]
            item(app, library, y, clip(recipe["name"].upper(), library.w - 8),
                 (lambda rid=recipe["id"]: app.act("craft", {"recipe": rid}))
                 if recipe.get("can_craft") else None,
                 hint="READY" if recipe.get("can_craft") else "MISSING",
                 hint_at=max(12, library.w - 10),
                 fg="text" if recipe.get("can_craft") else "faint")
            library.put(3, y + 1,
                        clip(f"→ {result['qty']}× {result['item']}", library.w - 5),
                        "green" if recipe.get("can_craft") else "dim")
        if len(recipes) > 10:
            library.put(1, 25, f"+ {len(recipes) - 10} more blueprints", "faint")

    chosen = _craft_focus(app, recipes)
    if chosen:
        result = chosen["result"]
        item_spec = dict((app.s.game.items.get(result["item"], {}) or {}))
        item_spec.update({"name": result["item"], "qty": result["qty"]})
        bench.put(1, 1, clip(chosen["name"].upper(), bench.w - 17), "bright", BOLD)
        bench.right(1, 1, bench.w - 2,
                    clip(str(chosen.get("station", "craft shop")).upper(), 15), "cyan")
        bench.put(1, 3, "OUTPUT", "dim", BOLD)
        bench.s.frame(bench.x + 1, bench.y + 5, 12, 8,
                      "amber" if chosen.get("can_craft") else "line")
        for n, line in enumerate(_folio_item_icon(item_spec)):
            bench.put(4, 7 + n, line, "cyan" if item_spec.get("use") else "green")
        bench.put(16, 5, clip(result["item"].upper(), bench.w - 18), "green", BOLD)
        copies = "COPY" if result["qty"] == 1 else "COPIES"
        bench.put(16, 7, f"MAKES  {result['qty']} {copies}", "text")
        bench.put(16, 8, f"FEE    {chosen['gold_cost']}g", "amber")
        bench.put(16, 10, "FIELD DESCRIPTION", "dim", BOLD)
        bench.wrap(16, 11, bench.w - 18,
                   item_spec.get("desc") or chosen.get("description") or
                   "No description has been written for this result yet.",
                   "text" if (item_spec.get("desc") or chosen.get("description")) else "faint",
                   limit=2)
        bench.hline(1, 15, bench.w - 2, "line", "-")
        bench.put(1, 17, "INGREDIENT CHECK", "dim", BOLD)
        y = 19
        for need in chosen["ingredients"][:4]:
            ready = int(need.get("have", 0)) >= int(need["qty"])
            bench.put(2, y, "●" if ready else "○", "green" if ready else "red", BOLD)
            bench.put(5, y, clip(need["item"].upper(), 28), "text" if ready else "dim")
            bench.right(2, y, bench.w - 4, f"{need.get('have', 0)}/{need['qty']}",
                        "green" if ready else "red", BOLD if ready else 0)
            y += 2
        bench.put(1, 25,
                  "READY TO CRAFT" if chosen.get("can_craft") else "MISSING MATERIALS OR GOLD",
                  "accent" if chosen.get("can_craft") else "amber", BOLD)
    else:
        bench.put(2, 5, "THE BENCH IS CLEAR", "amber", BOLD)
        bench.wrap(2, 7, bench.w - 4,
                   "Select a learned recipe. Its materials, output, and exact cost will appear here.",
                   "dim", limit=3)

    pack.put(1, 1, "ON THIS BLUEPRINT", "faint", BOLD)
    materials = []
    if chosen:
        seen = set()
        for need in chosen["ingredients"]:
            name = need["item"]
            if name not in seen:
                materials.append((name, int(need.get("have", 0)), int(need["qty"])))
                seen.add(name)
    for row in st.get("inventory", []):
        if row["name"] not in {name for name, _, _ in materials} and len(materials) < 9:
            materials.append((row["name"], int(row.get("qty", 0)), 0))
    y = 3
    for name, have, need in materials[:9]:
        ready = not need or have >= need
        pack.put(1, y, clip(name.upper(), pack.w - 9), "text" if ready else "dim")
        pack.right(1, y, pack.w - 2, f"{have}" + (f"/{need}" if need else ""),
                   "green" if ready else "red")
        y += 2
    if not materials:
        pack.put(1, 4, "Your pack is empty.", "faint")
    pack.hline(1, 22, pack.w - 2, "line", "-")
    pack.put(1, 23, "RULE", "faint", BOLD)
    pack.wrap(1, 24, pack.w - 2,
              "Recipes are deterministic. If the requirements are met, the result is made.",
              "dim", limit=2)

    y = 29
    folio_action(app, r, 1, y, 27, "Craft Selected",
                 (lambda rid=chosen["id"]: app.act("craft", {"recipe": rid}))
                 if chosen and chosen.get("can_craft") else None,
                 "Make the exact result shown on the bench." if chosen else "Choose a blueprint first.", "1")
    folio_action(app, r, 29, y, 27, "Visit Shop", lambda: app.go("gate.stall"),
                 "Buy books, remedies, seed, and baseline supplies.", "2")
    folio_action(app, r, 57, y, 27, "Open Pack", lambda: app.go("gate.stall"),
                 "Review every item before selling or restocking.", "3")
    folio_action(app, r, 85, y, 27, "Return Gate", app.back,
                 "Leave the workshop bench.", "4")
    r.put(1, r.h - 1, "FIELD WORKSHOP  ·  select a recipe to preview its full, deterministic output", "faint")


# --- the title / main menu -------------------------------------------------
def start_new_hunt(app) -> None:
    if not app.s.game.bestiary.all:
        app.say("No monsters installed. In the Forge, make a monster, then assign it to a Void Area.", "amber")
        return
    app.act("new_game", {"name": getattr(app.s, "default_hunter", "Hunter")})
    if app.state.get("starter_choices"):
        app.root("main.starter")
    elif app.s.game.roster:
        app.root("gate")


def load_main_save(app, slot: str) -> None:
    app.act("load", {"slot": slot})
    if app.s.game.roster:
        app.root("gate")


def place_main(app, r: Region) -> None:
    st = app.state
    empty_project = not st.get("species")
    col = max(2, (r.w - 64) // 2)
    width = min(64, r.w - col - 2)
    r.put(col, 1, "VOIDCALLER", "bright", BOLD)
    r.put(col, 2, "A FIELD JOURNAL FOR THE UNMAPPED VOID", "dim")
    r.hline(col, 4, width, "line", "─")
    saves = st.get("saves") or []
    if empty_project:
        r.put(col, 6, "THIS WORLD HAS NO ENTRIES YET.", "amber", BOLD)
        r.wrap(col, 8, width, "Begin in the Forge. Create one creature, then place it in a Void Area. "
               "The game will only show systems that have authored data behind them.", "text", limit=3)
        r.put(col, 13, "FIRST TWO ENTRIES", "dim", BOLD)
        r.put(col, 15, "01", "accent", BOLD)
        r.put(col + 5, 15, "Monster", "bright")
        r.put(col + 25, 15, "a creature with a free move", "faint")
        r.put(col, 17, "02", "accent", BOLD)
        r.put(col + 5, 17, "Void Area", "bright")
        r.put(col + 25, 17, "its explicit spawn roster", "faint")
        r.hline(col, 18, width, "line", "─")
        r.put(col, 19, "NEW GAME", "faint")
        r.put(col + 18, 19, "requires those two entries", "faint")
        item(app, r, 21, "APPEARANCE", lambda: app.go("main.settings"),
             hint="palette, layout, window", hint_at=col + 18, x=col)
        item(app, r, 22, "QUIT", lambda: setattr(app, "running", False),
             hint="close the journal", hint_at=col + 18, fg="red", x=col)
        return

    r.put(col, 6, "BEGIN A NEW HUNT", "accent", BOLD)
    r.put(col, 8, "One companion answers the call. Everything else is earned in the field.", "faint")
    item(app, r, 11, "NEW GAME", lambda: start_new_hunt(app),
         hint="one companion; an empty farm", hint_at=col + 18, fg="accent", x=col)
    item(app, r, 14, "LOAD GAME", (lambda: app.go("main.saves")) if saves else None,
         hint=f"{len(saves)} saved hunt{'s' if len(saves) != 1 else ''}" if saves else "no saved hunts",
         hint_at=col + 18, fg="text" if saves else "faint", x=col)
    item(app, r, 17, "APPEARANCE", lambda: app.go("main.settings"),
         hint="palette, layout, window", hint_at=col + 18, x=col)
    item(app, r, 20, "QUIT", lambda: setattr(app, "running", False),
         hint="close the journal", hint_at=col + 18, fg="red", x=col)


def place_main_saves(app, r: Region) -> None:
    saves = app.state.get("saves") or []
    r.put(2, 0, "CONTINUE A HUNT", "dim", BOLD)
    if not saves:
        r.put(2, 2, "no saved hunts.", "faint")
    for i, row in enumerate(saves[:12]):
        item(app, r, i + 2, row["label"],
             lambda slot=row["slot"]: load_main_save(app, slot), hint_at=99)
    item(app, r, min(16, len(saves) + 4), "Back", app.back, hint_at=26)


def choose_starter(app, ident: str) -> None:
    app.act("choose_starter", {"id": ident})
    if app.s.game.roster:
        app.root("gate")


def place_main_starter(app, r: Region) -> None:
    choices = app.state.get("starter_choices") or []
    r.put(2, 1, "CHOOSE YOUR FIRST COMPANION", "accent", BOLD)
    r.put(2, 2, "One travels with you. The other two remain somewhere in the Void.", "faint")
    if not choices:
        r.put(2, 5, "No candidates are available. Add three creatures in the Forge.", "amber")
        item(app, r, 8, "BACK", lambda: app.root("main"))
        return
    y = 5
    for n, row in enumerate(choices[:3], 1):
        name = f"{rarity_mark(row)} {row.get('name', 'Unknown')}"
        stats = row.get("stats") or {}
        moves = row.get("moves") or []
        base = ", ".join(move.get("name", "move") for move in moves[:2]) or "no moves"
        item(app, r, y, name, lambda ident=row.get("id", ""): choose_starter(app, ident),
             hint=f"Lv {row.get('level', 1)} · {row.get('role', 'Fodder')} · {row.get('type', 'Beast')}",
             hint_at=31, fg=rarity_fg(row), x=2)
        r.put(6, y + 1, f"HP {stats.get('hp', 0)}  ATK {stats.get('atk', 0)}  DEF {stats.get('def', 0)}  SPD {stats.get('spd', 0)}", "faint")
        r.put(6, y + 2, f"STARTING KIT  {base}", "dim")
        y += 5


def apply_display_setting(app, action: str) -> None:
    from . import display as DISPLAY
    state = DISPLAY.cycle_scale() if action == "scale" else DISPLAY.toggle(action)
    if hasattr(app.b, "reconfigure"):
        app.b.reconfigure(window_scale=state["scale"], fullscreen=state["fullscreen"],
                          fit_monitor=state["fit_monitor"])
    message = (f"display scale {state['scale']:g}x" if action == "scale" else
               f"{action.replace('_', ' ')} {'on' if state[action] else 'off'}")
    app.say(message, "accent")


def place_main_settings(app, r: Region) -> None:
    from . import display as DISPLAY
    state = DISPLAY.load()
    r.put(2, 0, "TERMINAL SETTINGS", "accent", BOLD)
    r.put(2, 1, "These settings are saved separately from every hunt.", "faint")
    item(app, r, 4, "APPEARANCE", lambda: app.go("main.look"),
         hint="colour, bars, glow", hint_at=24)
    item(app, r, 6, "PANEL LAYOUT", lambda: app.go("main.layout"),
         hint="map / party space", hint_at=24)
    item(app, r, 9, "WINDOW SCALE", lambda: apply_display_setting(app, "scale"),
         hint=f"{state['scale']:g}x", hint_at=24)
    item(app, r, 11, "FIT MONITOR", lambda: apply_display_setting(app, "fit_monitor"),
         hint="on" if state["fit_monitor"] else "off", hint_at=24)
    item(app, r, 13, "FULLSCREEN", lambda: apply_display_setting(app, "fullscreen"),
         hint="on" if state["fullscreen"] else "off", hint_at=24)
    item(app, r, 17, "BACK", app.back)


def place_layout(app, r: Region) -> None:
    from . import layout as LAYOUT
    current = LAYOUT.current()
    r.put(2, 0, "SCREEN LAYOUT", "dim", BOLD)
    r.put(2, 1, "This only changes the terminal presentation, never game rules.", "faint")
    y = 3
    for name, spec in LAYOUT.PRESETS.items():
        chosen = name == current["name"]
        item(app, r, y, spec["label"], lambda n=name: pick_layout(app, n),
             hint=spec["note"], hint_at=26, mark="•" if chosen else "")
        r.right(0, y, r.w - 1, f"main {spec['main_width']} cols", "faint")
        y += 2
    item(app, r, y + 1, "Back", app.back, hint_at=26)


def pick_layout(app, name: str) -> None:
    from . import layout as LAYOUT
    chosen = LAYOUT.use(name)
    if chosen:
        app.say(f"layout is now {chosen['label'].lower()}.", "accent")


def place_void_pick(app, r: Region) -> None:
    """The Atlas is a destination: region list, route plan, and field readout."""
    st = app.state
    regions = st.get("regions") or []
    if app.region is None and regions:
        app.region = regions[0]["key"]
    here = next((x for x in regions if x["key"] == app.region), regions[0] if regions else None)
    depths = st.get("depths") or []
    depth = next((d for d in depths if d["key"] == app.depth),
                 depths[0] if depths else {"key": "deep", "label": "Deep", "rows": 8, "loot": 1.0})
    danger_col = {"quiet": "faint", "fair": "green", "hard": "amber", "lethal": "red"}
    regions_panel = folio_panel(r, 0, 0, 27, 28, "ATLAS REGIONS",
                                 f"{len(regions)} REACHABLE")
    route = folio_panel(r, 28, 0, 58, 28, "EXPEDITION ROUTE",
                        f"{str(depth.get('label', 'Deep')).upper()} DESCENT")
    signals = folio_panel(r, 87, 0, 27, 13, "FIELD SIGNALS")
    prep = folio_panel(r, 87, 14, 27, 14, "RUN PREP")

    regions_panel.put(1, 1, "SELECT A REGION", "faint", BOLD)
    if regions:
        for n, reg in enumerate(regions[:10]):
            y = 3 + n * 2
            active = reg["key"] == app.region
            item(app, regions_panel, y, clip(reg["name"].upper(), regions_panel.w - 10),
                 lambda k=reg["key"]: pick_region(app, k),
                 hint=f"L{reg.get('level', 1)}", hint_at=regions_panel.w - 7,
                 mark="•" if active else "",
                 fg=danger_col.get(reg.get("danger"), "text"))
            regions_panel.put(3, y + 1,
                              clip(f"{reg.get('species', 0)} species  ·  {str(reg.get('danger', 'unknown')).upper()}",
                                   regions_panel.w - 5),
                              danger_col.get(reg.get("danger"), "faint") if active else "faint")
        if len(regions) > 10:
            regions_panel.put(1, 24, f"+ {len(regions) - 10} more regions", "faint")
    else:
        regions_panel.hline(1, 4, regions_panel.w - 2, "line", "-")
        regions_panel.put(1, 6, "ATLAS IS EMPTY", "amber", BOLD)
        regions_panel.wrap(1, 8, regions_panel.w - 2,
                           "In the Forge, create a creature, then assign it to a Void Area.",
                           "dim", limit=4)

    if here:
        route.put(1, 1, here["name"].upper(), "bright", BOLD)
        route.right(1, 1, route.w - 2,
                    f"{str(here.get('danger', 'unknown')).upper()} SIGNAL",
                    danger_col.get(here.get("danger"), "faint"))
        route.wrap(1, 3, route.w - 2,
                   here.get("description") or "No field note has been written for this region yet.",
                   "text" if here.get("description") else "faint", limit=2)
        route.hline(1, 6, route.w - 2, "line", "-")
        route.put(1, 8, "DESCENT PROFILE", "dim", BOLD)
        for n, row in enumerate(depths[:3]):
            y = 10 + n * 3
            active = row["key"] == app.depth
            item(app, route, y, clip(str(row["label"]).upper(), 18),
                 lambda k=row["key"]: pick_depth(app, k),
                 hint=f"{max(0, int(row.get('rows', 1)) - 1)} ROOMS",
                 hint_at=22, tail=f"LOOT ×{float(row.get('loot', 1)):g}",
                 tail_fg="amber" if active else "faint", mark="•" if active else "",
                 fg="cyan" if active else "text")
        route.hline(1, 19, route.w - 2, "line", "-")
        route.put(1, 21, "EXPECTED ROUTE", "dim", BOLD)
        stages = max(2, min(7, int(depth.get("rows", 2))))
        x = 3
        for n in range(stages):
            route.put(x, 23, "◇" if n == 0 else "○", "accent" if n == 0 else "line", BOLD if n == 0 else 0)
            if n < stages - 1:
                route.put(x + 1, 23, "────", "line")
            x += 5
        route.put(1, 25,
                  f"{here.get('species', 0)} assigned species  ·  cleared {here.get('cleared', 0)}×",
                  "faint")
    else:
        route.put(2, 6, "NO ROUTE TO DRAW", "amber", BOLD)
        route.wrap(2, 8, route.w - 4,
                   "The Atlas becomes usable as soon as an authored Void Area has at least one assigned creature.",
                   "dim", limit=3)

    signals.put(1, 1, "SCOUTING READOUT", "faint", BOLD)
    if here:
        rows = (
            ("TYPE TRACE", here.get("type_trace") or "UNREAD"),
            ("FAMILY TRACE", here.get("family_trace") or "UNREAD"),
            ("RARITY SIGNAL", here.get("rarity_signal") or str(here.get("danger", "unknown")).upper()),
            ("DISCOVERIES", here.get("discoveries") or "PENDING"),
        )
        for n, (label, value) in enumerate(rows):
            y = 3 + n * 2
            signals.put(1, y, label, "faint", BOLD)
            signals.put(1, y + 1, clip(str(value).upper(), signals.w - 2),
                        "cyan" if n < 2 else "amber" if n == 2 else "dim")
    else:
        signals.put(1, 4, "NO SIGNAL", "faint")

    party = st.get("party") or []
    prep.put(1, 1, "PARTY", "faint", BOLD)
    prep.right(1, 1, prep.w - 2, f"{len(party)}/4", "green")
    y = 3
    for mon in party[:2]:
        prep.put(1, y, clip(mon.get("name", "COMPANION").upper(), prep.w - 10), "text")
        prep.right(1, y, prep.w - 2, f"L{mon.get('level', 1)}", "faint")
        prep.bar(1, y + 1, prep.w - 3, mon.get("hp", 0), max(1, mon.get("max_hp", 1)), "green")
        y += 3
    if not party:
        prep.put(1, 4, "No companion bound.", "faint")
    prep.hline(1, 9, prep.w - 2, "line", "-")
    prep.put(1, 10, f"ROOMS  {max(0, int(depth.get('rows', 1)) - 1)}", "faint")
    prep.right(1, 10, prep.w - 2, f"×{float(depth.get('loot', 1)):g} LOOT", "amber")
    prep.put(1, 11, f"SHARDS  {st.get('shards', 0)}", "magenta")

    y = 29
    folio_action(app, r, 1, y, 27, "Deploy Free Roam",
                 (lambda: app.act("start_run", {"region": app.region, "depth": app.depth}))
                 if here else None,
                 (f"{here['name']} · {depth.get('label', 'Deep')} route" if here else
                  "Add a creature and Void Area in the Forge first."), "1")
    folio_action(app, r, 29, y, 27, "Mission Board", lambda: app.go("gate.board"),
                 "Signed operations deploy into their exact authored area.", "2")
    folio_action(app, r, 57, y, 27, "Field Codex", lambda: app.go("gate.ledger"),
                 "Review species already encountered in the field.", "3")
    folio_action(app, r, 85, y, 27, "Return Gate", app.back,
                 "Leave the Atlas table.", "4")
    r.put(1, r.h - 1, "VOID ATLAS  ·  region rosters come directly from the Forge", "faint")


def pick_region(app, key: str) -> None:
    app.region = key
    app.cursor = 0          # never leave someone staring at a chosen list


def pick_depth(app, key: str) -> None:
    app.depth = key
    app.cursor = 0


def choose_atlas_region(app, key: str, jump: int) -> None:
    app.region = key
    app.cursor = jump


def choose_atlas_depth(app, key: str, jump: int) -> None:
    app.depth = key
    app.cursor = jump


# --- the pack ---------------------------------------------------------------
def place_pack(app, r: Region) -> None:
    """A live party page: roster right, selected creature centre, rules left."""
    st = app.state
    roster = st["roster"]
    if not roster:
        r.put(2, 1, "nothing bound to you.", "faint")
        return
    active = [m for m in roster if m["in_party"]]
    order = active + [m for m in roster if not m["in_party"]]
    selected_i = app.cursor if 0 <= app.cursor < len(order) else 0
    selected = order[selected_i]
    source = next((m for m in app.s.game.roster if m.uid == selected["uid"]), None)
    if source is None:
        return
    full = app.s.unit(source, full=True)

    profile = folio_panel(r, 0, 0, 32, 28, "COMBAT PROFILE",
                          f"L{full['level']}")
    field = folio_panel(r, 33, 0, 48, 28, "FIELD ENTRY",
                        f"{rarity_mark(full)} {full['rarity'].upper()}")
    party = folio_panel(r, 82, 0, 32, 28, "PARTY / ROSTER",
                        f"{len(active)}/4")

    profile.put(1, 1, "STAT INDEX", "dim", BOLD)
    folio_stat_stack(profile, full["stats"], 1, 3, profile.w - 2)
    profile.hline(1, 16, profile.w - 2, "line", "-")
    profile.put(1, 17, "EQUIPPED MOVES", "dim", BOLD)
    skills = full.get("skills") or []

    name = f"{rarity_mark(full)}  {full['name'].upper()}"
    field.s.center(field.y + 1, name, rarity_fg(full), BOLD, x=field.x, w=field.w)
    field.s.center(field.y + 2, clip(f"{full['type']}  /  {full['role']}", field.w - 2),
                   "faint", x=field.x, w=field.w)
    portrait_w = min(28, field.w - 6)
    _portrait_box(field, full, (field.w - portrait_w) // 2, 4, portrait_w, 9, rarity_fg(full))
    field.put(2, 14, "HP", "faint", BOLD)
    field.bar(7, 14, field.w - 18, full["hp"], full["max_hp"], "green")
    field.right(2, 14, field.w - 4, f"{full['hp']}/{full['max_hp']}", "text")
    field.put(2, 16, "XP", "faint", BOLD)
    field.bar(7, 16, field.w - 18, full["xp_done"], full["xp_span"], "green")
    field.right(2, 16, field.w - 4, f"{full['xp_done']}/{full['xp_span']}", "green")
    field.hline(1, 18, field.w - 2, "line", "-")
    field.put(2, 19, "FIELD NOTE", "dim", BOLD)
    bio = full.get("appearance") or full.get("lore") or "No field note has been written for this creature yet."
    field.wrap(2, 20, field.w - 4, bio, "text" if full.get("appearance") else "faint", limit=2)
    where = _authored_places(app, full["species"]) or ", ".join(full.get("habitat") or []) or "not assigned"
    field.put(2, 23, clip("FOUND  " + where, field.w - 4), "cyan" if where != "not assigned" else "faint")
    field.put(2, 25, f"SKILL POINTS  {full.get('skill_points', 0)}", "amber" if full.get("skill_points") else "faint", BOLD)

    party.put(1, 1, "ACTIVE FIRST", "faint", BOLD)
    for i, m in enumerate(order[:6]):
        yy = 3 + i * 3
        mark = "◆" if app.marked == m["uid"] else ("*" if m["in_party"] else "+")
        idx = item(app, party, yy, " " + clip(m["name"].upper(), party.w - 11),
                   lambda uid=m["uid"], name=m["name"]: open_card(app, uid, name),
                   mark=mark, fg=rarity_fg(m), hint_at=party.w - 8,
                   tail=f"L{m['level']}", tail_fg="faint")
        party.put(3, yy + 1, "HP", "faint")
        party.bar(7, yy + 1, party.w - 15, m["hp"], m["max_hp"], "green")
        party.right(2, yy + 1, party.w - 4, f"{m['hp']}/{m['max_hp']}", "faint")
        if i == selected_i:
            party.put(3, yy, clip(m["name"].upper(), party.w - 11), rarity_fg(m), BOLD)
    if len(order) > 6:
        party.right(1, 20, party.w - 2, f"{len(order) - 6} more in roster", "faint")
    tree = full.get("skill_tree") or []
    unlocked = sum(1 for node in tree if node.get("unlocked"))
    party.hline(1, 21, party.w - 2, "line", "-")
    party.put(1, 22, f"SKILL PATH  {unlocked}/{len(tree)}", "amber" if tree else "faint", BOLD)
    if tree:
        for i, node in enumerate(tree[:2]):
            fg = "green" if node.get("unlocked") else "faint"
            party.put(2, 23 + i, "●" if node.get("unlocked") else "○", fg, BOLD)
            party.put(5, 23 + i, clip(f"R{node.get('rank', 0)}/{node.get('max_rank', 1)}  {node.get('name', 'UNTITLED')}", party.w - 7), fg)
    else:
        party.put(1, 24, "Author nodes in the Forge.", "faint")

    # Add roster entries to the navigation order before move cards. That makes
    # the party rail the first thing selected on entry, exactly as it reads.
    if skills:
        for i, skill in enumerate(skills[:2]):
            yy = 19 + i * 3
            kind = str(skill.get("kind", "")).lower()
            marker = "MELEE" if kind in ("physical", "magical") and skill.get("power") else "GUARD / BUFF"
            item(app, profile, yy, clip(skill["name"].upper(), profile.w - 12),
                 lambda uid=selected["uid"], name=selected["name"], n=i:
                 open_unit_move(app, uid, name, n),
                 hint=marker, hint_at=max(13, profile.w - 13),
                 fg=el_col(skill.get("type", "")))
            profile.put(3, yy + 1,
                        clip(f"PP {skill.get('pp_left', skill.get('pp', 0))}/{skill.get('pp', 0)}"
                             if skill.get("pp") else "PP ∞",
                             profile.w - 5), "faint")
    else:
        profile.put(1, 20, "No moves authored yet.", "faint")

    y = 29
    folio_action(app, r, 1, y, 27, "Inspect", lambda: open_card(app, selected["uid"], selected["name"]),
                 "Open full equipment and training options.", "1")
    folio_action(app, r, 29, y, 27, "Equip", lambda: open_equipment(app, selected["uid"], selected["name"]),
                 "Weapons, armour and accessories.", "2")
    level_cost = int(round(70 + 22 * full["level"] ** 1.15))
    folio_action(app, r, 57, y, 27, "Train", lambda: app.act("train", {"uid": selected["uid"]}),
                 f"One level for {level_cost}g.", "3")
    folio_action(app, r, 85, y, 27, "View Index", lambda: app.go("gate.ledger"),
                 "Browse every recorded species.", "4")
    r.put(1, r.h - 1, "PARTY  ·  select a companion to update this field entry  ·  moves open as readable cards", "faint")


def open_card(app, uid: int, name: str) -> None:
    app.focus_uid = uid
    app.focus_name = name
    app.go("gate.pack.card")


def open_equipment(app, uid: int, name: str) -> None:
    app.focus_uid = uid
    app.focus_name = name
    app.go("gate.pack.equip")


def open_build(app, uid: int, name: str) -> None:
    app.focus_uid = uid
    app.focus_name = name
    app.go("gate.pack.build")


def place_skill_build(app, r: Region) -> None:
    """A dedicated, legible place for finite companion and equipped-gear paths."""
    mon = next((m for m in app.s.game.roster if m.uid == app.focus_uid), None)
    if mon is None:
        app.back()
        return
    full = app.s.unit(mon, full=True)
    nodes = full.get("skill_tree") or []
    left = folio_panel(r, 0, 0, 28, r.h - 2, "BUILD OVERVIEW", f"L{full['level']}")
    paths = folio_panel(r, 29, 0, 62, r.h - 2, "SKILL PATHS", f"{full.get('skill_points', 0)} SP READY")
    # This rail is deliberately narrow on the fixed 118-column frame. Keep
    # its heading short so it never truncates into an ugly half-word.
    right = folio_panel(r, 92, 0, r.w - 92, r.h - 2, "GEAR PATH", "LIVE")

    left.put(1, 1, f"{rarity_mark(full)} {full['name'].upper()}", rarity_fg(full), BOLD)
    left.put(1, 3, "SKILL POINTS", "faint", BOLD)
    left.put(1, 4, str(full.get("skill_points", 0)), "amber" if full.get("skill_points") else "faint", BOLD)
    left.hline(1, 6, left.w - 2, "line", "-")
    left.put(1, 8, "HOW IT WORKS", "dim", BOLD)
    left.wrap(1, 9, left.w - 2,
              "Gain one Skill Point per level after Level 1. Buy a node rank when its prerequisites are met. Equipment paths only apply while that gear is worn.",
              "faint", limit=6)
    left.hline(1, 17, left.w - 2, "line", "-")
    left.put(1, 19, "AUTHORED IN FORGE", "dim", BOLD)
    left.wrap(1, 20, left.w - 2,
              "The Forge owns every branch, node, rank, and reward. This screen only spends earned points.",
              "faint", limit=4)

    if not nodes:
        paths.put(2, 3, "No skill paths are authored for this companion yet.", "faint")
        paths.put(2, 5, "Open the Forge and add 3–4 finite branches to its creature record.", "dim")
    else:
        y = 2
        last = None
        for node in nodes[:14]:
            branch = str(node.get("branch_name") or "Path")
            if branch != last:
                if last is not None:
                    y += 1
                paths.put(1, y, clip(branch.upper(), paths.w - 3), "dim", BOLD)
                y += 1
                last = branch
            rank = f"R{node.get('rank', 0)}/{node.get('max_rank', 1)}"
            state = "●" if node.get("unlocked") else "○"
            usable = bool(node.get("can_buy"))
            fg = "green" if node.get("unlocked") else "amber" if usable else "faint"
            reward = _tree_reward(node)
            item(app, paths, y, clip(f"{state}  {node.get('name', 'UNTITLED')}", 27),
                 lambda n=node: app.act("purchase_skill", {"uid": full["uid"], "node": n["id"]}),
                 hint=clip(reward, 19), hint_at=31, tail=rank, tail_fg=fg, fg=fg)
            paths.put(4, y + 1, clip(node.get("description") or "", paths.w - 6), "dim")
            y += 3
            if y >= paths.h - 3:
                break
        if len(nodes) > 14:
            paths.put(1, paths.h - 2, f"{len(nodes) - 14} more nodes below the field limit.", "faint")

    gear_rows = [node for node in nodes if node.get("source") != "Species"]
    if gear_rows:
        y = 2
        for node in gear_rows[:8]:
            right.put(1, y, clip(str(node.get("source", "GEAR")).upper(), right.w - 2), "cyan", BOLD)
            right.put(1, y + 1, clip(f"{node.get('name', 'NODE')}  R{node.get('rank', 0)}/{node.get('max_rank', 1)}", right.w - 2), "faint")
            y += 3
    else:
        right.put(1, 3, "No equipped item", "faint")
        right.wrap(1, 5, right.w - 2,
                   "Gear paths apply only while that item is equipped.", "dim", limit=5)
    item(app, r, r.h - 1, "Back to companion", app.back, fg="accent")


def open_unit_move(app, uid: int, name: str, index: int) -> None:
    app.focus_uid = uid
    app.focus_name = name
    open_move(app, "pack", index)


def open_move(app, origin: str, index: int) -> None:
    """Open a move as a readable ability card instead of leaving its effect
    truncated in a party or Codex row."""
    app.move_origin = origin
    app.move_index = index
    if origin == "pack":
        mon = next((m for m in app.state.get("roster", []) if m["uid"] == app.focus_uid), {})
        full = next((m for m in app.s.game.roster if m.uid == app.focus_uid), None)
        skills = app.s.unit(full, full=True).get("skills", []) if full else []
        app.focus_move_name = str((skills[index] if index < len(skills) else {}).get("name", "MOVE"))
        app.focus_name = mon.get("name", app.focus_name)
        app.go("gate.pack.move")
    else:
        creature = app.s.game.bestiary.get(app.focus_uid)
        skills = creature.moves_at_level(creature.level) if creature else []
        app.focus_move_name = str(getattr(skills[index], "name", "MOVE")) if index < len(skills) else "MOVE"
        app.go("gate.ledger.move")


def _move_value(skill, key: str, default=None):
    if isinstance(skill, dict):
        if key == "category":
            return skill.get("category", skill.get("kind", default))
        if key == "fx":
            return skill.get("effects", skill.get("fx", default))
        return skill.get(key, default)
    if key == "category":
        return getattr(skill, "category", getattr(skill, "kind", default))
    return getattr(skill, key, default)


def _move_effect(skill) -> str:
    return str(_move_value(skill, "description", _move_value(skill, "effect_text", "")) or "")


def _move_effect_explanation(skill, effect: str) -> str:
    """Translate an effect parser result, and call out unsupported prose rather
    than pretending a decorative phrase is a battle mechanic."""
    if not effect:
        return "No extra effect — this move is direct and reliable."
    fx = _move_value(skill, "fx", None)
    if fx is None:
        from engine.effects import parse
        fx = parse(effect)
    if not fx:
        return ("This effect text is not a recognised battle rule yet. Right now the move "
                "only performs its listed direct action.")
    parts = []
    for rule in fx[:3]:
        uncertain = rule.chance < 100
        turns = f" for {rule.rounds} turns" if rule.rounds else ""
        if rule.kind == "status":
            verb = "Grants" if rule.key in ("regen", "haste", "shield") else "Inflicts"
            if uncertain:
                parts.append(f"Has a {rule.chance:g}% chance to {verb.lower()} {rule.key.upper()}{turns}.")
            else:
                parts.append(f"{verb} {rule.key.upper()}{turns}.")
        elif rule.kind == "stat":
            verb = "Raises" if rule.amount > 0 else "Lowers"
            if uncertain:
                parts.append(f"Has a {rule.chance:g}% chance to {verb.lower()} {rule.key.upper()} by "
                             f"{abs(rule.amount) * 100:g}%{turns}.")
            else:
                parts.append(f"{verb} {rule.key.upper()} by {abs(rule.amount) * 100:g}%{turns}.")
        elif rule.kind == "heal":
            parts.append(f"Has a {rule.chance:g}% chance to restore HP." if uncertain else "Restores HP.")
        elif rule.kind == "drain":
            parts.append(f"Restores {rule.amount * 100:g}% of damage dealt as HP.")
        elif rule.kind == "revive":
            parts.append("Revives a fallen ally.")
        elif rule.kind == "cleanse":
            parts.append("Removes harmful status effects.")
    return " ".join(parts) or "The move has a special rule, shown below."


def _move_explanation(skill) -> tuple[str, str]:
    """Explain battle data in player language. The raw effect stays visible
    too, since its percentage/turn count is the exact rule the engine uses."""
    kind = str(_move_value(skill, "category", "physical"))
    power = int(_move_value(skill, "power", 0) or 0)
    target = str(_move_value(skill, "target", "single"))
    if kind == "physical":
        action = ("Deals physical damage using the user's ATK against the target's DEF."
                  if power else "A physical technique with no direct damage listed.")
    elif kind == "magical":
        action = ("Deals Type damage using the user's MAG against the target's RES."
                  if power else "A magical technique with no direct damage listed.")
    elif kind == "status":
        action = "A status technique: it does not deal direct damage unless its effect says so."
    else:
        action = "A support technique: it does not deal direct damage unless its effect says so."
    targets = {
        "single": "one chosen enemy", "all_enemies": "every enemy",
        "all_allies": "your whole party", "self": "the user", "random": "a random target",
    }
    return action, targets.get(target, target.replace("_", " "))


def _focused_move(app):
    if app.move_origin == "pack":
        mon = next((m for m in app.s.game.roster if m.uid == app.focus_uid), None)
        skills = app.s.unit(mon, full=True).get("skills", []) if mon else []
    else:
        creature = app.s.game.bestiary.get(app.focus_uid)
        skills = creature.moves_at_level(creature.level) if creature else []
    return skills[app.move_index] if 0 <= app.move_index < len(skills) else None


def place_move_detail(app, r: Region) -> None:
    skill = _focused_move(app)
    if skill is None:
        app.back()
        return
    name = str(_move_value(skill, "name", "UNKNOWN MOVE"))
    kind = str(_move_value(skill, "category", "physical"))
    element = str(_move_value(skill, "type", "") or "NONE")
    power = int(_move_value(skill, "power", 0) or 0)
    pp = int(_move_value(skill, "pp", 0) or 0)
    pp_left = int(_move_value(skill, "pp_left", pp) or 0)
    rating = str(_move_value(skill, "rating", "") or "—")
    accuracy = float(_move_value(skill, "accuracy", 100) or 100)
    priority = int(_move_value(skill, "priority", 0) or 0)
    crit = float(_move_value(skill, "crit", 0) or 0)
    action, target = _move_explanation(skill)
    effect = _move_effect(skill)

    r.put(2, 0, "MOVE ANALYSIS", "dim", BOLD)
    r.right(0, 0, r.w - 1,
            "PARTY ABILITY" if app.move_origin == "pack" else "CODEX ABILITY", "faint")
    r.put(2, 2, clip(name.upper(), r.w - 4), "bright", BOLD)
    r.rich(2, 3, [(kind.upper(), "amber"), ("  ·  ", "faint"),
                  (element.upper(), el_col(element)), ("  ·  ", "faint"),
                  (f"RATING {rating}", "dim")])
    r.hline(1, 4, r.w - 2, "line", "-")
    r.put(2, 6, "POWER", "faint", BOLD)
    r.put(15, 6, str(power) if power else "—", "amber" if power else "faint")
    r.put(28, 6, "PP", "faint", BOLD)
    r.put(34, 6, f"{pp_left}/{pp}" if pp else "∞", "amber" if pp else "faint")
    r.put(48, 6, "ACC", "faint", BOLD)
    r.put(53, 6, f"{accuracy:g}%", "cyan")
    r.right(1, 6, r.w - 2, f"PRIO {priority:+d}  CRIT {crit:g}%" if priority or crit else "", "dim")
    r.put(2, 7, "TARGET", "faint", BOLD)
    r.put(15, 7, clip(target.upper(), 25), "text")
    r.put(42, 7, "MOVE-OWNED PP", "dim")
    r.hline(1, 9, r.w - 2, "line", "-")
    r.put(2, 11, "WHAT IT DOES", "dim", BOLD)
    lines = r.wrap(2, 12, r.w - 4, action, "text", limit=2)
    y = 12 + lines + 1
    r.put(2, y, "SPECIAL EFFECT", "dim", BOLD)
    summary = _move_effect_explanation(skill, effect)
    lines = r.wrap(2, y + 1, r.w - 4, summary, "cyan" if effect else "faint", limit=2)
    if effect:
        r.put(2, min(r.h - 4, y + lines + 2), clip(f"RULE TEXT: {effect}", r.w - 4), "faint")
    item(app, r, r.h - 2, "Back to moves", app.back, fg="accent")


def _tree_reward(node: dict) -> str:
    """A short, player-facing description of one visible skill-path node."""
    effects = node.get("effects_per_rank") or []
    for effect in effects:
        if not isinstance(effect, dict):
            continue
        kind = str(effect.get("kind") or "")
        if kind in ("unlock_move", "move"):
            move = effect.get("move") or effect.get("value") or {}
            return "learn " + str(move.get("name") if isinstance(move, dict) else move or "a move")
        if kind in ("stat_pct", "stat"):
            stat = str(effect.get("stat") or effect.get("key") or "stat").upper()
            amount = float(effect.get("amount") or 0)
            return f"{stat} {'+' if amount >= 0 else '−'}{abs(amount) * 100:g}%"
        if kind in ("move_damage_pct", "physical_damage_pct", "magical_damage_pct"):
            amount = float(effect.get("amount") or 0)
            return f"MOVE DMG +{amount * 100:g}%"
    return str(node.get("description") or "Author a reward in the Forge.")


def _authored_tree_nodes(tree) -> list[dict]:
    """Flatten a V2 authored tree for static Codex and item-card previews.

    Owned companions already receive a richer, rank-aware flattened view from
    the Session. This helper is for species and shop records before a player
    owns or equips them.
    """
    if isinstance(tree, list):
        return [dict(node) for node in tree if isinstance(node, dict)]
    rows = []
    if not isinstance(tree, dict):
        return rows
    for branch in tree.get("branches") or []:
        if not isinstance(branch, dict):
            continue
        branch_name = str(branch.get("name") or branch.get("id") or "Path")
        for node in branch.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            row = dict(node)
            row.setdefault("branch_name", branch_name)
            rows.append(row)
    return rows


def _pixels_ready(r: Region, unit: dict) -> bool:
    """Whether this creature can be drawn as pixel art right now.

    Pixel art IS the creature. The ASCII sigil is not an overlay and not a
    companion to it — it exists only for terminals that cannot draw pixels, and
    for the rare case where the PNG has gone missing off disk.
    """
    path = unit.get("sprite_asset")
    return bool(getattr(r.s, "pixels", False) and path and os.path.isfile(str(path)))


def _portrait_box(r: Region, unit: dict, x: int, y: int, w: int = 24, h: int = 8,
                  fg: str = "accent") -> None:
    """A small field card showing the creature's sprite, or its sigil if the
    terminal cannot draw one."""
    r.s.frame(r.x + x, r.y + y, w, h, "line")
    r.put(x + 2, y + 1, "FIELD SIGIL", "faint", BOLD)
    r.right(x + 1, y + 1, w - 2, str(unit.get("portrait_sig") or "—"), "dim")
    if _pixels_ready(r, unit):
        r.s.sprite(unit["sprite_asset"], r.x + x + w // 2 - 4, r.y + y + 2, 8, 4)
        return
    portrait = list(unit.get("portrait") or [])[:4]
    for n, line in enumerate(portrait):
        r.put(x + max(2, (w - len(line)) // 2), y + 2 + n, line, fg)
    if not portrait:
        r.put(x + w // 2, y + 4, "·", "faint")


def _stat_bars(r: Region, stats: dict, x: int, y: int, width: int) -> None:
    """Six core stats as bars, without a redundant raw-stat paragraph."""
    keys = ("atk", "def", "mag", "res", "spd")
    ceiling = max(10, max(int(stats.get(key, 0)) for key in keys))
    col_w = max(20, width // 2)
    for n, key in enumerate(keys):
        col, row = x + (n % 2) * col_w, y + n // 2
        bar_w = max(6, min(12, col_w - 10))
        value = int(stats.get(key, 0))
        r.put(col, row, key.upper().ljust(3), "faint", BOLD)
        r.bar(col + 4, row, bar_w, value, ceiling,
              "amber" if key in ("atk", "mag") else "green" if key in ("def", "res") else "cyan")
        r.put(col + 5 + bar_w, row, f"{value:>3}", "text")


def _authored_places(app, species) -> str:
    """Prefer the exact Forge-owned Void Area over legacy habitat prose."""
    from engine import areas as AREAS
    here = AREAS.area_for_monster(app.s.game.bestiary, species)
    return str(here.get("name") if here else "")


def place_card(app, r: Region) -> None:
    st = app.state
    m = next((x for x in st["roster"] if x["uid"] == app.focus_uid), None)
    if not m:
        app.back()
        return
    full = app.s.unit(next(x for x in app.s.game.roster if x.uid == m["uid"]), full=True)
    r.put(2, 0, f"{rarity_mark(full)} {full['name']}", rarity_fg(full), BOLD)
    r.put(2 + len(full["name"]) + 5, 0, clip(full["title"] or full["role"], 28), "faint")
    r.right(0, 0, r.w - 1, f"POWER {full['power']}", "dim")
    r.put(2, 1, clip(f"{full['rarity']} · L{full['level']} · {full['type']}"
                     f"{'/' + full['secondary'] if full['secondary'] else ''} · {full['family']}", r.w - 4), "dim")
    r.put(28, 2, f"HP {full['hp']}/{full['max_hp']}", "faint", BOLD)
    r.bar(42, 2, max(10, min(16, r.w - 60)), full["hp"], full["max_hp"])
    r.right(1, 2, r.w - 2, f"SP {full.get('skill_points', 0)}", "amber" if full.get("skill_points") else "faint")
    _portrait_box(r, full, 1, 4, fg=rarity_fg(full))
    r.put(28, 4, "COMBAT SHAPE", "dim", BOLD)
    _stat_bars(r, full["stats"], 28, 5, max(42, r.w - 29))
    r.put(28, 9, "TRAINING", "faint", BOLD)
    r.bar(38, 9, max(10, min(24, r.w - 58)), full["xp_done"], full["xp_span"], "accent")
    r.put(max(64, r.w - 18), 9, f"{full['xp_next']} XP LEFT", "dim")
    r.put(2, 13, "FIELD NOTE", "dim", BOLD)
    bio = full.get("appearance") or full.get("lore") or "No field note has been written for this creature yet."
    r.wrap(2, 14, r.w - 4, bio, "text" if full.get("appearance") else "faint", limit=2)
    area = _authored_places(app, full["species"])
    where = area or ", ".join(full.get("habitat") or []) or "not assigned to a Void Area"
    r.put(2, 16, clip(f"FOUND  {where}", r.w - 4), "cyan" if area else "faint")
    evo = full.get("evolution") or {}
    if evo.get("into"):
        at = f" at L{evo['at_level']}" if evo.get("at_level") else ""
        r.put(2, 17, clip(f"EVOLUTION  {full['species']} → {evo['into']}{at}", r.w - 4), "cyan")
    else:
        r.put(2, 17, "TYPE / LEVEL / BUILD determine this creature's field role.", "faint")
    r.put(2, 18, "MOVES", "dim", BOLD)
    for i, sk in enumerate(full["skills"][:2]):
        x = 12 + i * max(26, (r.w - 12) // 2)
        item(app, r, 18, clip(sk["name"], max(14, r.w // 3 - 8)),
             lambda n=i: open_move(app, "pack", n), fg="text", x=x)
        r.put(x + 2, 19, f"PP {sk.get('pp_left', sk.get('pp', 0))}/{sk.get('pp', 0)}" if sk.get("pp")
              else "PP ∞", "faint")
    tree = full.get("skill_tree") or []
    unlocked = sum(1 for node in tree if node.get("unlocked"))
    item(app, r, 20, f"SKILL PATH  {unlocked}/{len(tree)}",
         lambda: open_build(app, m["uid"], m["name"]),
         hint="open build paths", hint_at=26, fg="amber" if tree else "faint")
    if tree:
        node = tree[0]
        marker = "●" if node.get("unlocked") else "○"
        fg = "green" if node.get("unlocked") else "faint"
        r.put(23, 20, marker, fg, BOLD)
        r.put(26, 20, clip(f"R{node.get('rank', 0)}/{node.get('max_rank', 1)}  {node['name']} · {_tree_reward(node)}", r.w - 28),
              "text" if node.get("unlocked") else "dim")
    else:
        r.put(23, 20, "add nodes in Forge", "faint")
    y = r.h - 4
    cost = int(round(70 + 22 * full["level"] ** 1.15))
    item(app, r, y, "Equipment", lambda: app.go("gate.pack.equip"),
         hint="weapon · armor · accessory", hint_at=26, fg="amber")
    item(app, r, y + 1, "Put in the four" if not m["in_party"] else "Take out of the four",
         lambda: app.act("toggle_party", {"uid": m["uid"]}), hint_at=26)
    item(app, r, y + 2, "Train", lambda: app.act("train", {"uid": m["uid"]}),
         hint=f"{cost}g for one level", hint_at=26)
    item(app, r, y + 3, "Release to the Void",
         lambda: (app.act("release", {"uid": m["uid"]}), app.back()),
         hint="gone for good, paid in shards", fg="red", hint_at=26)


def place_equipment(app, r: Region) -> None:
    mon = next((m for m in app.state.get("roster", []) if m["uid"] == app.focus_uid), None)
    if mon is None:
        app.back()
        return
    r.put(2, 0, f"EQUIP · {rarity_mark(mon)} {mon['name'].upper()}", rarity_fg(mon), BOLD)
    r.right(0, 0, r.w - 1, "bonuses are already reflected in stat bars", "faint")
    y = 2
    for slot in ("weapon", "armor", "accessory"):
        spec = (mon.get("equipment") or {}).get(slot)
        label = spec["name"] if spec else "— empty —"
        stats = " ".join(f"{k.upper()} +{v}" for k, v in (spec.get("stats", {}) if spec else {}).items())
        item(app, r, y, f"{slot.title():<10} {clip(label, 24)}",
             (lambda s=slot: app.act("equip", {"uid": mon["uid"], "slot": s})) if spec else None,
             hint=stats or ("select gear below" if not spec else ""), hint_at=39,
             fg="text" if spec else "faint", tail="REMOVE" if spec else "")
        y += 1
    r.hline(1, 6, r.w - 2, "line")
    r.put(2, 7, "AVAILABLE GEAR", "dim", BOLD)
    y = 9
    gear = [x for x in app.state.get("inventory", [])
            if x.get("kind") in ("weapon", "armor", "accessory", "equipment")]
    if not gear:
        r.put(3, y, "No loose gear. Craft some at the Workshop or find it in the Void.", "faint")
    for spec in gear[:9]:
        bonus = " ".join(f"{k.upper()} +{v}" for k, v in spec.get("stats", {}).items())
        item(app, r, y, clip(spec["name"], 24),
             lambda name=spec["name"]: app.act("equip", {"uid": mon["uid"], "name": name}),
             hint=bonus or clip(spec.get("desc", ""), 30), hint_at=28,
             tail=f"×{spec['qty']}", tail_fg="amber")
        y += 1
    item(app, r, r.h - 2, "Open the Workshop", lambda: app.go("gate.craft"), fg="accent")


# --- the ledger -------------------------------------------------------------
def place_ledger(app, r: Region) -> None:
    b = app.s.game.bestiary
    seen = app.s.game.seen
    species = sorted(b.all, key=lambda t: (t.id not in seen, t.level, t.name))
    r.put(2, 0, "species", "faint")
    r.put(34, 0, "level  type        threat     killed", "faint")
    start, end = window(app, len(species), r.h - 3)
    for i, t in enumerate(species[start:end], start):
        y = 2 + (i - start)
        known = t.id in seen
        kills = app.s.game.kills.get(t.name, 0)
        item(app, r, y, clip(t.name if known else "?" * min(11, len(t.name)), 26),
             (lambda tid=t.id, name=t.name: open_dex(app, tid, name)),
             fg="text" if known else "faint", hint_at=99)
        if known:
            r.put(2, y, clip(t.name, 26), rarity_fg({"rarity": t.rarity, "type": t.primary}),
                  BOLD if i == app.cursor else 0)
        r.put(34, y, f"L{t.level}", "faint")
        r.put(41, y, t.primary[:10] if known else "—", "dim" if known else "faint")
        r.put(53, y, rarity_mark({"rarity": t.rarity, "boss": t.is_boss}),
              rarity_fg({"rarity": t.rarity, "type": t.primary}), BOLD)
        r.right(0, y, r.w - 1, str(kills) if kills else "", "dim")
    r.right(0, r.h - 1, r.w - 1, f"{len(seen)}/{len(b)}", "faint")


def open_dex(app, tid: str, name: str) -> None:
    app.focus_uid = tid
    app.focus_name = name
    app.go("gate.ledger.card")


def place_dex(app, r: Region) -> None:
    from engine import elements as EL
    t = app.s.game.bestiary.get(app.focus_uid)
    if t is None:
        app.back(); return
    record = app.s.game.codex_record(t)
    known = bool(record["encounters"] or record["captured"] or t.id in app.s.game.seen)
    defeated = record["defeats"] > 0
    captured = record["captured"] > 0
    kills = app.s.game.kills.get(t.name, 0)
    creature = {"rarity": t.rarity, "type": t.primary, "boss": t.is_boss}
    r.put(2, 0, (rarity_mark(creature) + " " + t.name) if known else "UNRECORDED",
          rarity_fg(creature) if known else "bright", BOLD)
    r.put(2 + len(t.name) + 5, 0, t.title if known else "", "faint")
    r.put(2, 1, f"{t.primary}{'/' + t.secondary if t.secondary else ''} · {t.size} · "
                f"{t.family} · level {t.level} · {t.rarity} · killed {kills}×", "dim")
    if not known:
        r.put(2, 4, "You have never met this thing. The ledger fills itself in", "faint")
        r.put(2, 5, "the first time you put one down.", "faint")
        item(app, r, 8, "Back", app.back)
        return
    if not defeated and not captured:
        r.put(2, 4, "You have encountered this creature, but not brought one down.", "faint")
        r.put(2, 5, "Defeat it to reveal its combat record, drops, and resistances.", "faint")
        r.put(2, 7, "HABITAT", "dim", BOLD)
        r.put(12, 7, "???", "faint")
        r.put(2, 9, "WEAKNESS", "dim", BOLD)
        r.put(12, 9, "???", "faint")
        r.put(2, 11, "DROPS", "dim", BOLD)
        r.put(12, 11, "???", "faint")
        item(app, r, 14, "Back", app.back)
        return
    from engine import portraits, v2_art
    unit = {"portrait": portraits.for_template(t), "portrait_sig": portraits.signature(t),
            "sprite_asset": v2_art.write_monster(
                t.id, t.portrait_seed, t.primary,
                getattr(t, "sprite_archetype", "Core"))}
    _portrait_box(r, unit, 1, 3, fg=rarity_fg(creature))
    r.put(28, 3, "COMBAT SHAPE", "dim", BOLD)
    _stat_bars(r, t.stats, 28, 4, max(42, r.w - 29))
    r.put(2, 12, "FIELD NOTE", "dim", BOLD)
    r.wrap(2, 13, r.w - 4, t.lore or t.appearance or "No field note recorded.", "dim", limit=2)
    r.put(2, 15, "weak", "faint")
    r.rich(9, 15, [(f"{e} ×{m:g}  ", el_col(e)) for e, m in EL.weaknesses(t)[:4]]
           or [("nothing much", "faint")])
    r.put(2, 16, "resists", "faint")
    r.rich(9, 16, [(f"{e} ×{m:g}  ", el_col(e)) for e, m in EL.resistances(t)[:4]]
           or [("nothing", "faint")])
    tree = _authored_tree_nodes(t.skill_tree)
    r.put(2, 18, f"SKILL PATH  {len(tree)} NODE{'S' if len(tree) != 1 else ''}", "amber" if tree else "faint", BOLD)
    if tree:
        for n, node in enumerate(tree[:2]):
            r.put(3, 19 + n, "○", "faint")
            r.put(6, 19 + n, clip(f"{node.get('branch_name', 'PATH')}  {node.get('name', 'Untitled')} · {_tree_reward(node)}", r.w - 8), "dim")
    else:
        r.put(22, 18, "no authored nodes", "faint")
    r.put(2, 21, "MOVES", "dim", BOLD)
    for i, sk in enumerate(t.moves_at_level(t.level)[:3]):
        item(app, r, 22 + i, clip(sk.name, 20),
             lambda n=i: open_move(app, "dex", n), fg="text")
        r.put(25, 22 + i, sk.rating or "—", "dim")
        r.put(43, 22 + i, clip(sk.effect_text, max(10, r.w - 45)), "faint")


# --- the stall --------------------------------------------------------------
def _item_effect_summary(spec: dict) -> list[str]:
    """Translate an item record into the exact useful thing it does."""
    use = spec.get("use") or {}
    lines = []
    if use.get("heal_pct"):
        lines.append(f"Restores {float(use['heal_pct']) * 100:g}% of max HP.")
    if use.get("pp_restore"):
        lines.append(f"Restores {int(use['pp_restore'])} PP to the first depleted equipped move.")
    if use.get("revive_pct"):
        lines.append(f"Revives a fallen companion at {float(use['revive_pct']) * 100:g}% HP.")
    if use.get("cleanse"):
        lines.append("Clears harmful status effects.")
    if use.get("flee"):
        lines.append("Lets the party escape a normal fight.")
    buff = use.get("buff")
    if isinstance(buff, (list, tuple)) and len(buff) >= 3:
        lines.append(f"Raises {str(buff[0]).upper()} by {float(buff[1]) * 100:g}% for {int(buff[2])} turns.")
    stats = spec.get("stats") or {}
    if stats:
        bonus = "  ".join(f"{str(key).upper()} +{value}" for key, value in stats.items())
        lines.append(f"Equipment bonus: {bonus}.")
    if spec.get("book"):
        lines.append("Teaches the recipes in this craft book when purchased.")
    nodes = _authored_tree_nodes(spec.get("skill_tree"))
    if nodes:
        lines.append(f"Carries {len(nodes)} skill-path node{'s' if len(nodes) != 1 else ''} while equipped.")
    if not lines:
        lines.append("No active use. A material or trade good for crafting and selling.")
    return lines


def _item_card(r: Region, spec: dict, mode: str) -> None:
    """The selected row's terminal-friendly hover card."""
    r.hline(0, 0, r.w, "line", "-")
    r.put(1, 1, f"ITEM CARD // {mode}", "amber", BOLD)
    r.put(1, 2, clip(str(spec.get("name") or "UNKNOWN ITEM").upper(), r.w - 2), "bright", BOLD)
    kind = str(spec.get("kind") or "material").upper()
    value = spec.get("buy") if mode == "BUY" else spec.get("value")
    price = f"{value}g" if isinstance(value, (int, float)) and value else "—"
    r.right(0, 2, r.w - 1, f"{kind} · {price}", "amber" if price != "—" else "faint")
    r.wrap(1, 4, r.w - 2, spec.get("desc") or "No description written yet.", "dim", limit=2)
    r.put(1, 7, "WHAT IT DOES", "faint", BOLD)
    y = 8
    for line in _item_effect_summary(spec)[:2]:
        y += r.wrap(1, y, r.w - 2, line, "text", limit=1)
    hint = "ENTER PURCHASE" if mode == "BUY" else "ENTER SELL ALL"
    r.put(1, r.h - 1, f"{hint}  ·  move the selector to preview another item", "faint")


def _folio_item_preview(r: Region, spec: dict, mode: str) -> None:
    """A large, fixed item card between the pack and the merchant's stock."""
    r.put(1, 1, f"ITEM CARD  //  {mode}", "amber", BOLD)
    r.hline(1, 2, r.w - 2, "line", "-")
    r.s.frame(r.x + 2, r.y + 4, 14, 9, "amber" if mode == "BUY" else "line")
    for i, line in enumerate(_folio_item_icon(spec)):
        r.put(5, 6 + i, line, "cyan" if spec.get("use") else "green")
    name = clip(str(spec.get("name") or "UNKNOWN ITEM").upper(), r.w - 21)
    r.put(19, 4, name, "bright", BOLD)
    kind = str(spec.get("kind") or "material").upper()
    price_value = spec.get("buy") if mode == "BUY" else spec.get("value")
    price = f"{price_value}g" if isinstance(price_value, (int, float)) and price_value else "—"
    r.put(19, 6, kind, "green" if kind in ("SEED", "CROP") else "faint", BOLD)
    r.put(19, 7, f"PRICE  {price}", "amber" if price != "—" else "faint")
    if mode == "BUY":
        r.put(19, 8, f"IN PACK  {spec.get('have', 0)}", "faint")
    else:
        r.put(19, 8, f"IN PACK  {spec.get('qty', 0)}", "faint")
    r.put(19, 10, "FIELD DESCRIPTION", "dim", BOLD)
    r.wrap(19, 11, r.w - 21, spec.get("desc") or "No description has been written for this item yet.",
           "text" if spec.get("desc") else "faint", limit=3)
    r.hline(1, 15, r.w - 2, "line", "-")
    r.put(2, 17, "WHAT IT DOES", "dim", BOLD)
    y = 19
    for line in _item_effect_summary(spec)[:3]:
        y += r.wrap(2, y, r.w - 4, line, "cyan" if spec.get("use") else "text", limit=1)
        y += 1
    if spec.get("book"):
        r.put(2, min(r.h - 3, y), "CRAFT BOOK  ·  purchase to learn its recipes", "green")
    elif mode == "SELL":
        r.put(2, min(r.h - 3, y), "SELLING REMOVES EVERY COPY IN YOUR PACK.", "faint")
    else:
        r.put(2, min(r.h - 3, y), "MOVE THE SELECTOR TO COMPARE ANOTHER ITEM.", "faint")


def place_stall(app, r: Region) -> None:
    """Pack, item card and merchant stock: one uninterrupted shop counter."""
    st = app.state
    sell = [i for i in st["inventory"] if i["value"] > 0]
    sell.sort(key=lambda row: (not bool((app.s.game.items.get(row["name"], {}) or {}).get("use")),
                               row["name"].lower()))
    left = folio_panel(r, 0, 0, 30, 28, "YOUR PACK / SELL",
                       f"{sum(row['qty'] for row in st['inventory'])} ITEMS")
    card = folio_panel(r, 31, 0, 54, 28, "SELECTED ITEM",
                       f"PURSE {st['gold']}g")
    right = folio_panel(r, 86, 0, 28, 28, "SHOP STOCK / BUY")
    preview = None
    left.put(1, 1, "PACK INVENTORY", "faint", BOLD)
    for n, row in enumerate(sell[:9]):
        y = 3 + n * 2
        idx = item(app, left, y, clip(row["name"], 18),
                   lambda n=row["name"]: app.act("sell", {"name": n, "all": True}),
                   hint=f"x{row['qty']}", hint_at=19,
                   tail=f"{row['value']}g", tail_fg="amber")
        if idx == app.cursor:
            preview = ({**(app.s.game.items.get(row["name"], {})), **row}, "SELL")
    junk_y = min(left.h - 2, 3 + min(len(sell), 9) * 2)
    idx = item(app, left, junk_y, "SELL LOOSE MATERIAL", lambda: app.act("sell_junk", {}),
               hint="quest safe", hint_at=20, fg="faint")
    if idx == app.cursor:
        preview = ({"name": "Loose material", "kind": "material", "value": 0,
                    "desc": "Sells every loose material not owed to a current fetch contract."}, "SELL")
    if not sell:
        left.put(1, 5, "nothing saleable in the pack", "faint")

    right.put(1, 1, "BOOKS / SEED / GEAR", "faint", BOLD)
    priority = {"book": 0, "seed": 1}
    stock = sorted(st.get("stock", []), key=lambda x: (priority.get(x.get("kind"), 2), x["name"]))
    for n, spec in enumerate(stock[:10]):
        y = 3 + n * 2
        learned = spec.get("learned")
        idx = item(app, right, y, clip(spec["name"], 20),
                   None if learned else (lambda n=spec["name"]: app.act("buy", {"name": n, "qty": 1})),
                   hint="LEARNED" if learned else (f"have {spec['have']}" if spec["have"] else ""),
                   hint_at=17, tail=f"{spec['buy']}g", tail_fg="faint" if learned else "amber",
                   fg="faint" if learned else "text")
        if idx == app.cursor:
            preview = (spec, "BUY")
    if preview is None and stock:
        preview = (stock[0], "BUY")
    if preview is not None:
        _folio_item_preview(card, *preview)
    else:
        card.put(2, 4, "No item is in focus.", "faint")

    spec, mode = preview if preview else ({}, "BUY")
    if mode == "BUY":
        transaction = (lambda name=spec.get("name", ""): app.act("buy", {"name": name, "qty": 1}))
        transaction_label = "Buy Selected"
        transaction_note = f"Spend {spec.get('buy', 0)}g for one copy."
    elif spec.get("name") == "Loose material":
        transaction = lambda: app.act("sell_junk", {})
        transaction_label = "Sell Loose"
        transaction_note = "Keep active quest items safe."
    else:
        transaction = (lambda name=spec.get("name", ""): app.act("sell", {"name": name, "all": True}))
        transaction_label = "Sell Selected"
        transaction_note = f"Sell every copy for {spec.get('value', 0)}g each."
    y = 29
    folio_action(app, r, 1, y, 27, transaction_label, transaction, transaction_note, "1")
    folio_action(app, r, 29, y, 27, "Open Workshop", lambda: app.go("gate.craft"),
                 "Turn materials into prepared gear.", "2")
    folio_action(app, r, 57, y, 27, "Check Field Book", lambda: app.go("gate.ledger"),
                 "Review recorded creatures and drops.", "3")
    folio_action(app, r, 85, y, 27, "Return Gate", app.back,
                 "Leave the village counter.", "4")
    r.put(1, r.h - 1, "VILLAGE SHOP  ·  buy and sell update the field card before you commit", "faint")


# --- the circle -------------------------------------------------------------
def place_circle(app, r: Region) -> None:
    st = app.state
    r.put(2, 0, f"A summon costs {st['summon_cost']} shards. What answers is not your choice.",
          "dim")
    r.put(2, 1, "common 51%   uncommon 29%   rare 14%   epic 6%", "faint")
    r.right(0, 0, r.w - 1, f"◆{st['shards']}", "magenta")
    item(app, r, 3, "Summon", lambda: app.act("summon", {}),
         hint=f"{st['summon_cost']} shards", hint_at=20,
         fg="accent" if st["shards"] >= st["summon_cost"] else "faint")
    r.hline(1, 5, r.w - 2, "line")
    r.put(2, 6, "RELEASE — gone for good, paid in shards", "faint")
    y = 7
    for m in st["roster"]:
        if m["in_party"]:
            continue
        item(app, r, y, clip(m["name"], 22),
             (lambda uid=m["uid"]: app.act("release", {"uid": uid})),
             hint=f"L{m['level']} {m['rarity']}", hint_at=26,
             tail=f"power {m['power']}")
        y += 1
        if y > r.h - 4:
            break
    item(app, r, min(y + 1, r.h - 2), "Back", app.back)


KIND_VERB = {"fetch": "bring", "slay": "slay", "hunt": "hunt"}


def _board_focus(app, entries: list[tuple[str, dict]]) -> tuple[str, dict] | tuple[None, None]:
    """A dossier remains visible while the cursor moves to its action cards."""
    visible = entries[:10]
    if 0 <= app.cursor < len(visible):
        app.board_focus_uid = visible[app.cursor][1]["uid"]
    wanted = getattr(app, "board_focus_uid", "")
    return next(((source, quest) for source, quest in entries if quest["uid"] == wanted),
                visible[0] if visible else (None, None))


def focus_board_contract(app, uid: str) -> None:
    app.board_focus_uid = uid


def open_mission(app, index: int) -> None:
    app.act("track_quest", {"index": index})
    app.go("gate.mission")


def accept_mission(app, index: int) -> None:
    before = len(app.state.get("quests", []))
    app.act("accept_quest", {"index": index})
    if len(app.state.get("quests", [])) > before:
        app.go("gate.mission")


def place_board(app, r: Region) -> None:
    """The contract desk reads like a field dossier, not a generic task list."""
    st = app.state
    taken = st.get("quests", [])
    offers = st.get("board", [])
    entries = [("ACTIVE", quest) for quest in taken] + [("BOARD", quest) for quest in offers]
    source, chosen = _board_focus(app, entries)
    docket = folio_panel(r, 0, 0, 27, 28, "CONTRACT LEDGER",
                         f"DAY {st.get('day', 1)}")
    dossier = folio_panel(r, 28, 0, 58, 28, "OPERATION DOSSIER",
                          "SELECTED CONTRACT")
    readiness = folio_panel(r, 87, 0, 27, 13, "HUNTER READY")
    tracker = folio_panel(r, 87, 14, 27, 14, "TRACKING")

    docket.put(1, 1, "CARRIED", "faint", BOLD)
    y = 3
    shown = 0
    for label, quest in entries[:10]:
        if label == "BOARD" and not any(kind == "BOARD" for kind, _ in entries[:shown]):
            docket.hline(1, y - 1, docket.w - 2, "line", "-")
            docket.put(1, y, "ON THE BOARD", "faint", BOLD)
            y += 2
        active = chosen is quest
        done = bool(quest.get("done"))
        item(app, docket, y, clip(quest["title"].upper(), docket.w - 9),
             lambda uid=quest["uid"]: focus_board_contract(app, uid),
             hint="READY" if done else ("TRACKED" if quest.get("tracked") else label),
             hint_at=max(11, docket.w - 11), mark="•" if active else "",
             fg="accent" if done else "text")
        docket.put(3, y + 1,
                   clip(f"{KIND_VERB.get(quest.get('kind'), 'do').upper()}  {quest.get('target', 'UNKNOWN')}",
                        docket.w - 5),
                   "green" if done else "faint")
        y += 2
        shown += 1
    if not entries:
        docket.hline(1, 4, docket.w - 2, "line", "-")
        docket.put(1, 6, "NO CONTRACTS", "amber", BOLD)
        docket.wrap(1, 8, docket.w - 2,
                    "There is nothing posted yet. A world needs authored creatures and areas before work can appear.",
                    "dim", limit=4)
    elif len(entries) > 10:
        docket.put(1, 24, f"+ {len(entries) - 10} more contracts", "faint")

    if chosen:
        is_active = source == "ACTIVE"
        done = bool(chosen.get("done"))
        kind = str(chosen.get("kind") or "hunt").upper()
        dossier.put(1, 1, clip(chosen["title"].upper(), dossier.w - 18), "bright", BOLD)
        dossier.right(1, 1, dossier.w - 2, "SIGNED" if is_active else "POSTED",
                      "accent" if is_active else "faint", BOLD if is_active else 0)
        dossier.s.frame(dossier.x + 1, dossier.y + 4, 15, 10,
                        "amber" if kind == "HUNT" else "line")
        sigil = "☠" if kind == "HUNT" else "◆" if kind == "SLAY" else "◈"
        dossier.s.center(dossier.y + 7, sigil, "amber" if kind == "HUNT" else "cyan", BOLD,
                         x=dossier.x + 1, w=15)
        dossier.s.center(dossier.y + 10, kind, "dim", 0, x=dossier.x + 1, w=15)
        dossier.put(19, 4, "TARGET", "dim", BOLD)
        dossier.put(19, 5, clip(str(chosen.get("target", "UNKNOWN")).upper(), dossier.w - 21),
                    "amber" if kind == "HUNT" else "text", BOLD)
        dossier.put(19, 7, "OPERATION AREA", "dim", BOLD)
        dossier.put(19, 8, clip(str(chosen.get("where", "anywhere")).upper(), dossier.w - 21), "cyan")
        dossier.put(19, 10, "POSTED BY", "dim", BOLD)
        dossier.put(19, 11, clip(str(chosen.get("giver", "UNKNOWN")), dossier.w - 21), "text")
        dossier.hline(1, 15, dossier.w - 2, "line", "-")
        dossier.put(1, 17, "OPERATION PROGRESS", "dim", BOLD)
        have, qty = int(chosen.get("have", 0)), max(1, int(chosen.get("qty", 1)))
        dossier.bar(1, 19, dossier.w - 14, have if is_active else 0, qty, "accent")
        dossier.right(1, 19, dossier.w - 2,
                      f"{have}/{qty}" if is_active else "UNSIGNED", "accent" if done else "faint", BOLD if done else 0)
        dossier.put(1, 21, "FIELD BRIEF", "dim", BOLD)
        dossier.wrap(1, 22, dossier.w - 2,
                     chosen.get("text") or "No briefing was supplied for this operation.",
                     "text" if chosen.get("text") else "faint", limit=2)
        dossier.rich(1, 25, [("REWARD  ", "faint"),
                             (f"{chosen.get('gold', 0)}g", "amber", BOLD), ("  ·  ", "faint"),
                             (f"{chosen.get('shards', 0)} shards", "magenta", BOLD), ("  ·  ", "faint"),
                             (f"{chosen.get('xp', 0)} xp", "green", BOLD)])
    else:
        dossier.put(2, 6, "SELECT A CONTRACT", "amber", BOLD)
        dossier.wrap(2, 8, dossier.w - 4,
                     "The selected contract becomes a complete field operation with its own destination and objective.",
                     "dim", limit=3)

    party = st.get("party") or []
    readiness.put(1, 1, "BOUND PARTY", "faint", BOLD)
    readiness.right(1, 1, readiness.w - 2, f"{len(party)}/4", "green")
    y = 3
    for mon in party[:2]:
        readiness.put(1, y, clip(mon.get("name", "COMPANION").upper(), readiness.w - 10), "text")
        readiness.right(1, y, readiness.w - 2, f"L{mon.get('level', 1)}", "faint")
        readiness.bar(1, y + 1, readiness.w - 3, mon.get("hp", 0), max(1, mon.get("max_hp", 1)), "green")
        y += 3
    if not party:
        readiness.put(1, 4, "No companion bound.", "faint")
    readiness.hline(1, 9, readiness.w - 2, "line", "-")
    readiness.put(1, 10, "Check the party before deploy.", "faint")

    tracker.put(1, 1, "CURRENT ORDER", "faint", BOLD)
    if chosen:
        tracker.put(1, 3, "STATUS", "faint", BOLD)
        tracker.right(1, 3, tracker.w - 2,
                      "COMPLETE" if chosen.get("done") else "SIGNED" if source == "ACTIVE" else "AVAILABLE",
                      "accent" if chosen.get("done") else "amber" if source == "ACTIVE" else "cyan")
        tracker.put(1, 5, "AREA", "faint", BOLD)
        tracker.put(1, 6, clip(str(chosen.get("where", "anywhere")).upper(), tracker.w - 2), "cyan")
        tracker.put(1, 8, "TARGET", "faint", BOLD)
        tracker.put(1, 9, clip(str(chosen.get("target", "unknown")).upper(), tracker.w - 2), "text")
        tracker.put(1, 11, "Each hunt owns its operation.", "faint")
    else:
        tracker.put(1, 4, "No contract in focus.", "faint")

    if chosen and source == "ACTIVE" and chosen.get("done"):
        primary_label = "Claim Reward"
        primary_action = lambda i=chosen["i"]: app.act("turn_in", {"index": i})
        primary_note = "The objective is complete. Turn the operation in."
    elif chosen and source == "ACTIVE":
        primary_label = "Open Operation"
        primary_action = lambda i=chosen["i"]: open_mission(app, i)
        primary_note = "Review the route and deploy when the party is ready."
    elif chosen:
        primary_label = "Sign Contract"
        primary_action = lambda i=chosen["i"]: accept_mission(app, i)
        primary_note = "Accept this contract and open its operation brief."
    else:
        primary_label, primary_action, primary_note = "No Contract", None, "Nothing is available to sign."
    y = 29
    folio_action(app, r, 1, y, 27, primary_label, primary_action, primary_note, "1")
    folio_action(app, r, 29, y, 27, "Void Atlas", lambda: app.go("gate.void"),
                 "Review Free Roam expeditions and region signals.", "2")
    folio_action(app, r, 57, y, 27, "Check Party", lambda: app.go("gate.pack"),
                 "Inspect companions, moves, and field condition.", "3")
    folio_action(app, r, 85, y, 27, "Return Gate", app.back,
                 "Leave the contract desk.", "4")
    r.put(1, r.h - 1, "HUNT BOARD  ·  choose a contract, read its dossier, then enter its own operation", "faint")


def place_mission(app, r: Region) -> None:
    """A signed contract gets a complete operation page before it starts."""
    mission = app.state.get("mission")
    brief = folio_panel(r, 0, 0, 27, 28, "CONTRACT BRIEF")
    route = folio_panel(r, 28, 0, 58, 28, "OPERATION ROUTE")
    readiness = folio_panel(r, 87, 0, 27, 13, "DEPLOYMENT CHECK")
    reward = folio_panel(r, 87, 14, 27, 14, "OPERATION REWARD")
    if not mission:
        brief.put(1, 5, "NO OPERATION", "amber", BOLD)
        brief.wrap(1, 7, brief.w - 2, "Return to the Hunt Board and sign a contract first.", "dim", limit=3)
        route.put(2, 6, "NO ROUTE ON FILE", "faint", BOLD)
        route.wrap(2, 8, route.w - 4,
                   "Every signed contract arrives here before the hunter deploys into its assigned Void Area.",
                   "dim", limit=3)
        readiness.put(1, 4, "No operation selected.", "faint")
        reward.put(1, 4, "No reward pending.", "faint")
        primary_label, primary_action, primary_note = "Mission Board", app.back, "Choose a contract to plan."
    else:
        kind = str(mission.get("kind") or "hunt").upper()
        brief.put(1, 1, clip(mission["title"].upper(), brief.w - 2), "bright", BOLD)
        brief.put(1, 3, f"{kind}  TARGET", "dim", BOLD)
        brief.put(1, 4, clip(str(mission.get("target", "UNKNOWN")).upper(), brief.w - 2),
                  "amber" if kind == "HUNT" else "text", BOLD)
        brief.hline(1, 6, brief.w - 2, "line", "-")
        brief.put(1, 8, "OPERATION AREA", "faint", BOLD)
        brief.put(1, 9, clip(str(mission.get("where", "anywhere")).upper(), brief.w - 2), "cyan")
        brief.put(1, 11, "SIGNED BY", "faint", BOLD)
        brief.put(1, 12, clip(str(mission.get("giver", "UNKNOWN")), brief.w - 2), "text")
        brief.hline(1, 14, brief.w - 2, "line", "-")
        brief.put(1, 16, "FIELD BRIEF", "dim", BOLD)
        brief.wrap(1, 18, brief.w - 2,
                   mission.get("text") or "No briefing was supplied for this operation.",
                   "text" if mission.get("text") else "faint", limit=4)
        brief.put(1, 24, "OBJECTIVE", "faint", BOLD)
        brief.right(1, 24, brief.w - 2, f"{mission.get('have', 0)}/{mission.get('qty', 1)}",
                    "accent" if mission.get("done") else "faint", BOLD if mission.get("done") else 0)

        stage = int(mission.get("stage", 0))
        stages = max(1, int(mission.get("stages", 7)))
        route.put(1, 1, "RAID PROGRESS", "dim", BOLD)
        route.right(1, 1, route.w - 2, f"STAGE {stage}/{stages}", "amber", BOLD)
        route.bar(1, 3, route.w - 2, stage, stages, "accent")
        route.hline(1, 5, route.w - 2, "line", "-")
        shown = min(7, max(3, stages))
        current = min(shown - 1, int(round(stage / max(1, stages) * (shown - 1))))
        labels = ("SIGN", "TRAVEL", "TRACK", "LOCATE", "ENGAGE", "SECURE", "RETURN")
        x = 3
        for n in range(shown):
            fg = "green" if n < current else "amber" if n == current else "line"
            mark = "●" if n < current else "◉" if n == current else "○"
            route.put(x, 9, mark, fg, BOLD)
            if n < shown - 1:
                route.put(x + 1, 9, "────", "green" if n < current else "line")
            route.s.center(route.y + 11, labels[n], fg, BOLD if n == current else 0,
                           x=route.x + max(0, x - 3), w=7)
            x += 8
        route.put(1, 15, "OBJECTIVE", "dim", BOLD)
        route.put(1, 16, clip(f"{KIND_VERB.get(mission.get('kind'), 'complete').upper()}  {mission.get('target', 'UNKNOWN')}",
                               route.w - 2), "text", BOLD)
        route.bar(1, 18, route.w - 13, mission.get("have", 0), max(1, mission.get("qty", 1)), "accent")
        route.right(1, 18, route.w - 2,
                    f"{mission.get('have', 0)}/{mission.get('qty', 1)}",
                    "accent" if mission.get("done") else "faint", BOLD if mission.get("done") else 0)
        route.hline(1, 20, route.w - 2, "line", "-")
        route.put(1, 22, "DESTINATION", "dim", BOLD)
        route.put(1, 23, clip(str(mission.get("where", "anywhere")).upper(), route.w - 2), "cyan", BOLD)
        route.put(1, 25, "Deploy, resolve the operation, then report to the board.", "faint")

        party = app.state.get("party") or []
        readiness.put(1, 1, "PARTY", "faint", BOLD)
        readiness.right(1, 1, readiness.w - 2, f"{len(party)}/4", "green")
        y = 3
        for mon in party[:2]:
            readiness.put(1, y, clip(mon.get("name", "COMPANION").upper(), readiness.w - 10), "text")
            readiness.right(1, y, readiness.w - 2, f"L{mon.get('level', 1)}", "faint")
            readiness.bar(1, y + 1, readiness.w - 3, mon.get("hp", 0), max(1, mon.get("max_hp", 1)), "green")
            y += 3
        if not party:
            readiness.put(1, 4, "No companion bound.", "faint")
        readiness.hline(1, 9, readiness.w - 2, "line", "-")
        readiness.put(1, 10, "Route data follows the contract.", "faint")

        reward.put(1, 1, "ON COMPLETION", "faint", BOLD)
        reward.put(1, 3, "GOLD", "faint", BOLD)
        reward.right(1, 3, reward.w - 2, f"{mission.get('gold', 0)}g", "amber")
        reward.put(1, 5, "SHARDS", "faint", BOLD)
        reward.right(1, 5, reward.w - 2, str(mission.get("shards", 0)), "magenta")
        reward.put(1, 7, "EXPERIENCE", "faint", BOLD)
        reward.right(1, 7, reward.w - 2, str(mission.get("xp", 0)), "green")
        reward.hline(1, 9, reward.w - 2, "line", "-")
        reward.put(1, 10, "STATUS", "faint", BOLD)
        reward.put(1, 11, "READY TO REPORT" if mission.get("done") else "OBJECTIVE ACTIVE",
                   "accent" if mission.get("done") else "amber", BOLD)

        idx = next((q["i"] for q in app.state.get("quests", []) if q["uid"] == mission["uid"]), 0)
        if mission.get("done"):
            primary_label = "Claim Reward"
            primary_action = lambda: app.act("turn_in", {"index": idx})
            primary_note = "The operation is complete. Report to the board."
        else:
            primary_label = "Deploy Operation"
            primary_action = lambda: app.act("start_quest_run", {"index": idx, "depth": "deep"})
            primary_note = "Enter this contract's exact operation area."
    y = 29
    folio_action(app, r, 1, y, 27, primary_label, primary_action, primary_note, "1")
    folio_action(app, r, 29, y, 27, "Mission Board", app.back,
                 "Return to every available and active contract.", "2")
    folio_action(app, r, 57, y, 27, "Check Party", lambda: app.go("gate.pack"),
                 "Review the party before deployment.", "3")
    folio_action(app, r, 85, y, 27, "Return Gate", lambda: app.root("gate"),
                 "Leave the operation front.", "4")
    r.put(1, r.h - 1, "OPERATION FRONT  ·  every signed contract owns its route, objective, and return cycle", "faint")


# --- the look ---------------------------------------------------------------
def place_look(app, r: Region) -> None:
    """Every colour on the screen, and the glass in front of it."""
    from . import theme as TH
    from .screen import PALETTE
    t = TH.current()

    r.put(2, 0, "THE LOOK", "dim", BOLD)
    r.right(0, 0, r.w - 1, t.get("label", t["name"]), "accent")
    r.put(2, 1, clip(t.get("note", ""), r.w - 24), "faint")

    item(app, r, 3, "Panel Geometry", lambda: app.go("gate.layout"),
         hint="cinematic · balanced · wide · party · command", hint_at=22,
         fg="accent")
    r.put(2, 5, "PALETTE", "dim", BOLD)
    y = 6
    for pre in TH.presets():
        chosen = pre["name"] == t["name"]
        item(app, r, y, pre["label"], (lambda n=pre["name"]: pick_look(app, n)),
             hint=clip(pre.get("note", ""), 30), hint_at=20,
             mark="•" if chosen else "")
        x = r.w - 13
        for role in ("bg", "text", "accent", "amber", "red", "magenta", "blue"):
            r.put(x, y, "██" if role != "bg" else "▒▒", TH.swatch(pre["name"], role))
            x += 2
        y += 1

    r.hline(1, y, r.w - 2, "line")
    y += 1
    style = t.get("bars", "hashes")
    full, empty = TH.BAR_STYLES[style]
    item(app, r, y, "Bars", (lambda: cycle_bars(app)), hint=style, hint_at=16)
    r.right(0, y, r.w - 1, full * 9 + empty * 4, "green")
    y += 1
    crisp = bool(t.get("crisp", True))
    item(app, r, y, "Sharp Text", (lambda: toggle_crisp(app)),
         hint="ON" if crisp else "SOFT", hint_at=16,
         fg="accent" if crisp else "text")
    r.right(0, y, r.w - 1, "pixel-clean terminal letters" if crisp else "soft monitor lettering", "faint")
    y += 1
    for key, label in (("bloom", "Glow"), ("scanlines", "Scanlines"),
                       ("vignette", "Vignette")):
        val = float(t.get(key, 0.0))
        item(app, r, y, label, (lambda k=key: bump(app, k)),
             hint=f"{val:.2f}", hint_at=16)
        filled = int(round(val * 14))
        r.right(0, y, r.w - 1, full * filled + empty * (14 - filled), "accent")
        y += 1

    r.put(2, r.h - 1, "advanced: colour accent #ff9c00 · glow/scanlines/vignette 0-1", "faint")


def pick_look(app, name: str) -> None:
    from . import theme as TH
    t = TH.use(name, app.b)
    TH.save(t)
    app.say(f"the look is now {t.get('label', name)}.", "accent")


def cycle_bars(app) -> None:
    from . import theme as TH
    order = list(TH.BAR_STYLES)
    cur = TH.current().get("bars", "hashes")
    nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else order[0]
    TH.set_bars(nxt, app.b)
    TH.save()
    app.say(f"bars are {nxt} now.", "dim")


def toggle_crisp(app) -> None:
    from . import theme as TH
    crisp = TH.toggle_crisp(app.b)
    TH.save()
    app.say("sharp terminal text is on." if crisp else "soft CRT text is on.", "accent")


def bump(app, key: str) -> None:
    from . import theme as TH
    val = TH.nudge(key, 0.1, app.b)
    if val > 0.95:
        val = TH.nudge(key, -val, app.b)
    TH.save()
    app.say(f"{key} {val:.2f}", "faint")


# --- in the Void ------------------------------------------------------------
KIND_WORD = {"fight": "a fight", "elite": "something bigger", "gather": "pickings",
             "cache": "someone else's luck", "shrine": "still water",
             "boss": "the bottom", "gate": "the way in"}
KIND_COL = {"fight": "red", "elite": "amber", "gather": "green", "cache": "amber",
            "shrine": "cyan", "boss": "red", "gate": "dim"}


def place_run(app, r: Region) -> None:
    """Live expedition folio: a readable route, choices, and carried haul."""
    run = app.state.get("run")
    if not run:
        r.put(2, 1, "you are not in the Void.", "faint")
        return
    m = run["map"]
    here = next((n for row in m["rows"] for n in row if n["id"] == m["current"]), None)
    mission = app.state.get("mission") if run.get("quest_uid") else None
    runbook = folio_panel(r, 0, 0, 27, 28, "EXPEDITION STATUS",
                           f"DEPTH {m.get('row', 0)}")
    route = folio_panel(r, 28, 0, 58, 28, "THE DESCENT",
                        f"{max(0, int(m.get('rows_total', 1)) - 1)} ROOMS")
    choices = folio_panel(r, 87, 0, 27, 15, "THE WAY ON")
    haul = folio_panel(r, 87, 16, 27, 12, "UNBANKED HAUL")

    if here:
        runbook.put(1, 1, clip(here["name"].upper(), runbook.w - 2), "bright", BOLD)
        runbook.put(1, 3, clip(KIND_WORD.get(here.get("kind"), "unknown").upper(), runbook.w - 2),
                    KIND_COL.get(here.get("kind"), "faint"), BOLD)
        runbook.put(1, 5, "CURRENT DEPTH", "faint", BOLD)
        runbook.right(1, 5, runbook.w - 2,
                      f"{m.get('row', 0)}/{max(0, int(m.get('rows_total', 1)) - 1)}", "amber")
    else:
        runbook.put(1, 3, "ROUTE REASSEMBLING", "faint", BOLD)
    runbook.hline(1, 7, runbook.w - 2, "line", "-")
    runbook.put(1, 9, "EXPEDITION AREA", "faint", BOLD)
    runbook.put(1, 10, clip(str(m.get("region", "UNKNOWN")).upper(), runbook.w - 2), "cyan")
    runbook.put(1, 12, "MODE", "faint", BOLD)
    runbook.put(1, 13, "SIGNED OPERATION" if mission else "FREE ROAM", "amber" if mission else "green", BOLD)
    if mission:
        runbook.hline(1, 15, runbook.w - 2, "line", "-")
        runbook.put(1, 17, "ACTIVE OBJECTIVE", "faint", BOLD)
        runbook.put(1, 18, clip(mission.get("title", "OPERATION").upper(), runbook.w - 2), "amber", BOLD)
        runbook.put(1, 20, clip(f"{mission.get('have', 0)}/{mission.get('qty', 1)}  {mission.get('target', 'UNKNOWN')}",
                                 runbook.w - 2), "text")
        runbook.bar(1, 22, runbook.w - 3, mission.get("have", 0),
                    max(1, mission.get("qty", 1)), "accent")
    else:
        runbook.hline(1, 15, runbook.w - 2, "line", "-")
        runbook.put(1, 17, "FREE ROAM", "faint", BOLD)
        runbook.wrap(1, 19, runbook.w - 2,
                     "Choose a way down. Extraction keeps every carried reward.",
                     "dim", limit=3)

    route.put(1, 1, clip(str(m.get("region", "THE VOID")).upper(), route.w - 2), "bright", BOLD)
    route.right(1, 1, route.w - 2,
                clip(mission.get("title", "FREE ROAM").upper(), 23) if mission else "FREE ROAM",
                "amber" if mission else "faint")
    route.hline(1, 2, route.w - 2, "line", "-")
    rows = m.get("rows") or []
    row_count = max(1, len(rows) - 1)
    for row_i, nodes in enumerate(rows):
        y = 4 + int(round(row_i * 18 / row_count))
        if y >= route.h - 2:
            continue
        if row_i > 0:
            route.put(max(1, route.w // 2), y - 1, "│", "line")
        usable_w = max(8, route.w - 8)
        for n, node in enumerate(nodes):
            x = 4 + int(round((n + 0.5) * usable_w / max(1, len(nodes))))
            state = node.get("state", "unseen")
            mark, fg = {
                "cleared": ("●", "green"), "current": ("◆", "accent"),
                "open": ("○", "cyan"), "skipped": ("×", "faint"),
                "unseen": ("·", "line"),
            }.get(state, ("·", "faint"))
            route.put(x, y, mark, fg, BOLD if state in ("current", "open") else 0)
            if state in ("current", "open"):
                route.put(x + 2, y, clip(node.get("name", "?????"), 14),
                          "text" if state == "current" else "faint")
    route.hline(1, 24, route.w - 2, "line", "-")
    route.put(1, 25, "◆ CURRENT   ● CLEARED   ○ OPEN   · UNSEEN", "faint")

    ways = [n for row in m["rows"] for n in row if n["id"] in m["available"]]
    choices.put(1, 1, "CHOOSE A NODE", "faint", BOLD)
    y = 3
    for n in ways[:3]:
        item(app, choices, y, n["name"] if n["state"] != "unseen" else "?????",
             (lambda nid=n["id"]: app.act("descend", {"node": nid})),
             hint=KIND_WORD.get(n["kind"], ""), hint_at=12,
             mark=n.get("icon", "·"), fg=KIND_COL.get(n.get("kind"), "text"))
        choices.put(3, y + 1, clip(str(n.get("kind", "unknown")).upper(), choices.w - 5), "faint")
        y += 2
    if not ways:
        choices.put(1, y + 1, "No route further down.", "amber")
    choices.hline(1, 10, choices.w - 2, "line", "-")
    choices.put(1, 11, "Choose a branch to keep", "faint")
    choices.put(1, 12, "the expedition moving.", "faint")

    haul.rich(1, 1, [(f"{run['gold']}g", "amber", BOLD), ("  ", "faint"),
                     (f"{run['shards']} shards", "magenta", BOLD)])
    haul.put(1, 3, f"{run['xp']} XP  ·  NOT BANKED", "green")
    counts: dict = {}
    for it in run["bag"]:
        counts[it] = counts.get(it, 0) + 1
    y = 5
    for name, qty in list(counts.items())[:3]:
        haul.put(1, y, clip(name.upper(), haul.w - 8), "text")
        haul.right(1, y, haul.w - 2, f"×{qty}", "faint")
        y += 1
    if not counts:
        haul.put(1, 5, "Nothing recovered yet.", "faint")

    y = 29
    folio_action(app, r, 1, y, 27, "Extract", lambda: app.act("extract", {}),
                 "Bank the carried gold, shards, experience, and loot.", "1")
    folio_action(app, r, 29, y, 27, "Check Party", lambda: app.go("gate.pack"),
                 "Inspect companions without abandoning the expedition.", "2")
    folio_action(app, r, 57, y, 27,
                 "Operation Brief" if mission else "Field Codex",
                 (lambda: app.go("gate.mission")) if mission else (lambda: app.go("gate.ledger")),
                 "Review the signed objective." if mission else "Review recorded species.", "3")
    folio_action(app, r, 85, y, 27, "Continue Route",
                 (lambda nid=ways[0]["id"]: app.act("descend", {"node": nid})) if ways else None,
                 "Take the first open route." if ways else "No open route remains.", "4")
    r.put(1, r.h - 1, "VOID EXPEDITION  ·  carried rewards are only safe once you extract", "faint")


# --- a fight ----------------------------------------------------------------
def turn_strip(app, r: Region, y: int, b: dict) -> None:
    """A compact initiative ribbon: the combat table's spine."""
    order = b.get("order") or []
    if not order:
        return
    tail = f"ROUND {b.get('round', 1):02} ╗"
    edge = r.w - len(tail) - 1
    r.put(0, y, "╔ INITIATIVE ", "line", BOLD)
    x = 13
    for i, t in enumerate(order[:6]):
        name = clip(t["name"], 13 if i == 0 else 11)
        if x + len(name) + 2 > edge:
            r.put(x, y, "…", "faint")
            break
        col = "accent" if t["side"] == "party" else "red"
        if i == 0:
            r.put(x, y, "▸", col, BOLD)
            x = r.put(x + 1, y, name, col, BOLD)
        else:
            x = r.put(x, y, name, "dim" if t["side"] == "party" else "faint")
        x = r.put(x, y, "  ·  ", "line")
    r.right(0, y, r.w - 1, tail, "line", BOLD)


def enemy_rows(app, r: Region, y: int, b: dict, pickable: bool) -> int:
    """The other side, with a bar you can read at a glance."""
    live = [u for u in b["enemies"] if u["alive"]]
    for n, u in enumerate(b["enemies"]):
        alive = u["alive"]
        chosen = u["uid"] == app.sel_target and alive
        if pickable and alive:
            i = item(app, r, y, "", (lambda uid=u["uid"]: aim_at(app, uid)))
            app.items[i]["label"] = u["name"]
            sel = i == app.cursor
        else:
            sel = False
        if alive:
            r.put(0, y, "▸" if sel else ("›" if chosen else "┝"),
                  "accent" if sel else "red", BOLD)
            r.put(0, y + 1, "└", "red")
        r.put(2, y, f"FOE {n + 1}", "faint")
        r.put(8, y, clip(u["name"], 17), "bright" if sel else ("red" if alive else "faint"),
              BOLD if (sel or u.get("acting")) else 0)
        r.put(26, y, f"L{u['level']}", "faint")
        if alive:
            r.bar(31, y, 18, u["hp"], u["max_hp"])
            r.put(50, y, f"{u['hp']}/{u['max_hp']}", "dim" if not sel else "bright")
        else:
            r.put(31, y, "── down ──", "faint")
        bits = []
        if u.get("known"):
            bits += [(f"{w['element']} ×{w['mult']:g}  ", el_col(w["element"]))
                     for w in (u.get("weak") or [])[:3]]
        elif alive:
            bits.append(("unscouted", "faint"))
        bits += [(f"[{s['key']} {s['rounds']}] ", "magenta") for s in u.get("statuses", [])]
        r.rich(31, y + 1, bits)
        y += 2
    return y


def ally_rows(app, r: Region, y: int, b: dict) -> None:
    """Your own side, pickable, for a move that helps rather than hurts."""
    allies = [u for u in (b.get("options") or {}).get("allies", []) if u["alive"]]
    for n, u in enumerate(allies):
        i = item(app, r, y, "", (lambda uid=u["uid"]: aim_at(app, uid)))
        app.items[i]["label"] = u["name"]
        sel = i == app.cursor
        r.put(0, y, "\u25b8" if sel else " ", "accent", BOLD)
        r.put(2, y, f"{n + 1}", "faint")
        r.put(4, y, clip(u["name"], 20), "bright" if sel else "text", BOLD if sel else 0)
        r.bar(26, y, 18, u["hp"], u["max_hp"])
        r.put(45, y, f"{u['hp']}/{u['max_hp']}", "bright" if sel else "dim")
        tags = " ".join(u.get("statuses", []))
        if tags:
            r.put(56, y, clip(f"[{tags}]", r.w - 58), "magenta")
        y += 1


def actor_readout(app, r: Region, y: int, opts: dict, b: dict) -> None:
    """Whose turn it is, and everything you need to know about them."""
    me = next((u for u in b["party"] if u["uid"] == opts.get("uid")), None)
    r.put(1, y, "TURN", "faint", BOLD)
    r.put(7, y, clip(opts.get("name", ""), 12).upper(), "accent", BOLD)
    r.put(21, y, f"L{opts.get('level', 1)}", "faint")
    r.put(25, y, "hp", "faint")
    r.bar(28, y, 10, opts.get("hp", 0), max(1, opts.get("max_hp", 1)))
    r.put(39, y, f"{opts.get('hp', 0)}/{opts.get('max_hp', 0)}", "dim")
    nxt = opts.get("xp_next", 0)
    if nxt:
        r.put(25, y + 1, "xp", "faint")
        r.bar(28, y + 1, 10, opts.get("xp_done", 0),
              max(1, opts.get("xp_span", 1)), "amber")
        r.put(39, y + 1, f"{nxt} to level {opts.get('level', 1) + 1}", "faint")
    if me:
        tags = "  ".join(f"[{s['key']} {s['rounds']}]" for s in me.get("statuses", []))
        if tags:
            r.put(48, y + 1, clip(tags, r.w - 50), "magenta")


def place_battle(app, r: Region) -> None:
    b = app.state.get("battle")
    if not b:
        r.put(2, 1, "the field is quiet.", "faint")
        return
    opts = b.get("options") or {}
    you = next((u for u in b.get("party", []) if u.get("active")), None)
    targets = opts.get("targets") or [u for u in b.get("enemies", []) if u.get("alive")]
    if not you or not targets:
        r.put(2, 1, "The field is changing.", "faint")
        return

    mode = getattr(app, "battle_mode", "main")
    if mode == "__retired_bag_overlay":
        _battle_overlay(app, r, "BAG // USE AN ITEM", "cyan")
        usable = [row for row in app.state.get("inventory", []) if row.get("usable")]
        if not usable:
            r.put(30, 7, "No usable field items in the bag.", "faint")
        for y, row in enumerate(usable[:6], 5):
            item(app, r, y, clip(row["name"].upper(), 30),
                 lambda name=row["name"], uid=you["uid"]: use_battle_item(app, name, uid),
                 hint=f"x{row['qty']}", hint_at=64, x=27)
        item(app, r, 16, "BACK", lambda: set_battle_mode(app, "main"), x=27)
        return
    if mode == "switch":
        _battle_overlay(app, r, "SWITCH // CHOOSE A COMPANION", "cyan")
        bench = opts.get("bench") or []
        if not bench:
            r.put(27, 7, "No other companion is bound to your party yet.", "faint")
        for y, row in enumerate(bench[:6], 5):
            item(app, r, y, clip(row["name"].upper(), 30),
                 (lambda uid=row["uid"]: switch_battle_creature(app, uid)) if row["alive"] else None,
                 hint=f"LV {row['level']}  HP {row['hp']}/{row['max_hp']}", hint_at=64, x=27,
                 fg="text" if row["alive"] else "faint")
        item(app, r, 16, "BACK", lambda: set_battle_mode(app, "main"), x=27)
        return

    _battle_header(app, r, b)
    _battle_creature_card(app, r, 1, 2, 31, 10, you, ally=True)

    count = min(3, len(targets))
    gap = 2
    card_w = min(31, max(21, (r.w - 37 - gap * (count - 1)) // max(1, count)))
    start_x = r.w - 1 - (card_w * count + gap * (count - 1))
    r.put(start_x, 1, "ENEMIES", "red", BOLD)
    for n, target in enumerate(targets[:count]):
        x = start_x + n * (card_w + gap)
        chosen = target["uid"] == app.sel_target
        _battle_creature_card(app, r, x, 2, card_w, 10, target,
                              enemy=True, selected=chosen, index=n + 1)
        _battle_target_item(app, r, x, 2, card_w, 10, target)

    r.put(1, 12, "XP", "green", BOLD)
    r.bar(5, 12, 26, you.get("xp_done", 0), max(1, you.get("xp_span", 1)), "green")
    r.put(33, 12, f"{you.get('xp_done', 0)}/{you.get('xp_span', 1)}", "green")
    tray = getattr(app, "tray", None) or {}
    hit = tray.get("e") or {}
    if tray.get("kind") == "hit" and hit.get("target_uid") == you.get("uid"):
        r.put(20, 12, f"{hit.get('amount', 0)} DMG", "red", BOLD)
    r.hline(1, 13, r.w - 2, "line", "─")

    # A standing menu down the left, one panel on the right that swaps with it.
    # Guard is gone: it is a move a creature can be authored with, not a free
    # button every creature gets. Bind names no odds — the player learns what
    # works by weakening things and trying it.
    menu_w, panel_x = 22, 25
    panel_w, panel_y, panel_h = r.w - panel_x - 1, 14, 17

    _battle_menu_button(app, r, 1, 14, menu_w, "FIGHT", "use a move",
                        mode in ("main", "fight"), lambda: enter_battle_panel(app, "fight"),
                        "amber")
    _battle_menu_button(app, r, 1, 18, menu_w, "BAG", "use a field item",
                        mode == "bag", lambda: enter_battle_panel(app, "bag"), "cyan")
    if opts.get("can_capture"):
        _battle_menu_button(app, r, 1, 22, menu_w, "CAPTURE", "attempt a bind",
                            mode == "capture", lambda: capture_target(app), "green")
    else:
        _battle_menu_button(app, r, 1, 22, menu_w, "CAPTURE", "cannot be bound",
                            False, None, "faint")
    if opts.get("can_flee"):
        _battle_menu_button(app, r, 1, 26, menu_w, "FLEE", "break off and run",
                            False, lambda: flee_battle(app), "faint")
    else:
        _battle_menu_button(app, r, 1, 26, menu_w, "FLEE", "no way out",
                            False, None, "faint")

    r.s.frame(r.x + panel_x, r.y + panel_y, panel_w, panel_h, "line")
    pending = getattr(app, "battle_confirm", None)
    flash = (getattr(app, "tray", None) or {}).get("kind")
    if pending:
        _battle_panel_confirm(r, panel_x, panel_y, panel_w, panel_h, pending)
    elif flash == "capture":
        _battle_panel_capture(app, r, panel_x, panel_y, panel_w, panel_h, targets)
    elif flash == "flee":
        _battle_panel_flee(app, r, panel_x, panel_y, panel_w, panel_h)
    elif mode == "bag":
        _battle_panel_bag(app, r, panel_x, panel_y, panel_w, panel_h, you)
    else:
        _battle_panel_moves(app, r, panel_x, panel_y, panel_w, panel_h, opts)
    r.put(2, 31, "Priority → SPD decides the exchange. PP is the only move resource.",
          "faint")


# How long a piece of battle feedback stays on screen. Long enough to read,
# short enough not to hold up the next exchange.
FLASH_LIFE = 1.0
STATUS_COLOUR = {"burn": "red", "poison": "green", "bleed": "red", "stun": "amber",
                 "sleep": "cyan", "stone": "faint", "silence": "magenta",
                 "blind": "faint", "slow": "cyan", "confuse": "magenta",
                 "shield": "cyan", "regen": "green", "haste": "amber"}


def _battle_flash(app, r: Region, unit: dict, x: int, y: int, w: int, h: int) -> None:
    """Float what just happened over the creature it happened to.

    Each kind of event gets its own motion so it is recognisable before it is
    read: damage punches in and settles, a crit lands harder and shakes, a
    miss drifts off rather than popping, a status rises and pulses.
    """
    tray = getattr(app, "tray", None) or {}
    event = tray.get("e") or {}
    kind = tray.get("kind")
    if kind not in ("hit", "miss", "status") or event.get("target_uid") != unit.get("uid"):
        return
    age = time.time() - float(tray.get("at") or 0.0)
    if age < 0 or age > FLASH_LIFE:
        return
    t = age / FLASH_LIFE                       # 0 at the moment of impact
    fade = 1.0 if t < 0.65 else max(0.0, 1.0 - (t - 0.65) / 0.35)
    cx, cy = x + w / 2.0, y + h / 2.0

    if kind == "hit":
        amount = int(event.get("amount", 0) or 0)
        if amount <= 0:
            return
        crit = bool(event.get("crit"))
        text = f"{amount} DAMAGE!" if not crit else f"CRIT!  {amount}"
        # A punch: overshoot on the first fifth of the life, then settle.
        peak = 2.4 if crit else 1.7
        rest = 1.35 if crit else 1.0
        grow = min(1.0, t / 0.2)
        scale = peak + (rest - peak) * grow
        shake = 0.0
        if crit and t < 0.35:
            shake = (0.45 if int(age * 60) % 2 else -0.45) * (1 - t / 0.35)
        r.s.flash(text, r.x + cx + shake, r.y + cy - t * 1.6,
                  "red" if crit else "amber", scale, fade)
        return

    if kind == "miss":
        # No punch. It drifts away, which is what a miss should feel like.
        r.s.flash("MISS", r.x + cx + t * 2.2, r.y + cy - t * 2.6,
                  "faint", 1.1, max(0.0, 1.0 - t))
        return

    key = str(event.get("status") or "").casefold()
    if not event.get("applied") or key not in STATUS_COLOUR:
        return
    # Statuses rise and pulse rather than punch.
    pulse = 1.15 + 0.18 * math.sin(age * 16.0)
    r.s.flash(f"{key.upper()}!", r.x + cx, r.y + cy - 1.0 - t * 2.4,
              STATUS_COLOUR[key], pulse, fade)


def _battle_menu_button(app, r: Region, x: int, y: int, w: int, label: str,
                        hint: str, selected: bool, action, fg: str) -> None:
    """One standing action down the left of the board.

    Selected state is a filled left rail plus a bright label, so which action
    is live reads without having to compare two shades of amber.
    """
    live = action is not None
    focused = getattr(app, "battle_focus", "menu") == "menu"
    index = None
    if live and focused:
        index = len(app.items)
    # Two different things were being shown with one colour: where the cursor
    # is, and which panel is open. The cursor is what the player is moving, so
    # it owns the bright highlight; the open panel gets a quieter marker.
    on_cursor = index is not None and index == app.cursor
    border = "amber" if on_cursor else ("cyan" if selected else ("line" if live else "faint"))
    r.s.frame(r.x + x, r.y + y, w, 4, border)
    if on_cursor:
        for row in range(1, 3):
            r.put(x + 1, y + row, "\u2588", "amber")
    elif selected:
        r.put(x + 1, y + 1, "\u2502", "cyan")
        r.put(x + 1, y + 2, "\u2502", "cyan")
    r.put(x + 3, y + 1, label,
          "bright" if on_cursor else (fg if live else "faint"), BOLD)
    r.put(x + 3, y + 2, clip(hint, w - 5), "dim" if on_cursor else "faint")
    if live:
        # Only the focused pane is selectable, so up/down can never wander out
        # of the column the player is actually working in.
        app.click_map[(r.y + y + 1, r.x + x, r.x + x + w)] = ("battle_menu", label)
        app.click_map[(r.y + y + 2, r.x + x, r.x + x + w)] = ("battle_menu", label)
        if focused:
            app.items.append({"action": action, "label": label,
                              "nav": (r.x + x + w // 2, r.y + y + 2)})


def _battle_panel_moves(app, r: Region, x: int, y: int, w: int, h: int,
                        opts: dict) -> None:
    """The four move slots, two across, filling the panel."""
    r.put(x + 2, y, " MOVES ", "amber", BOLD)
    moves = opts.get("moves", [])[:4]
    card_w = (w - 5) // 2
    card_h = (h - 3) // 2
    focused = getattr(app, "battle_focus", "menu") == "panel"
    for i in range(4):
        cx = x + 2 + (i % 2) * (card_w + 1)
        cy = y + 1 + (i // 2) * (card_h + 1)
        if i < len(moves):
            _battle_move_card(app, r, cx, cy, card_w, card_h, moves[i], i,
                              focusable=focused)
        else:
            _battle_empty_move_card(r, cx, cy, card_w, card_h, i)
    if not focused:
        r.put(x + 2, y + h - 1, " enter to choose a move ", "faint")


def _battle_panel_bag(app, r: Region, x: int, y: int, w: int, h: int,
                      you: dict) -> None:
    """Everything carried, laid out to be read rather than scrolled past."""
    r.put(x + 2, y, " BAG ", "cyan", BOLD)
    rows = [row for row in app.state.get("inventory", []) if row.get("usable")]
    if not rows:
        r.put(x + 3, y + 2, "Nothing here can be used in a fight.", "faint")
        return
    r.put(x + 3, y + 1, "ITEM", "faint", BOLD)
    r.put(x + w - 22, y + 1, "HAVE", "faint", BOLD)
    r.put(x + w - 14, y + 1, "EFFECT", "faint", BOLD)
    focused = getattr(app, "battle_focus", "menu") == "panel"
    for n, row in enumerate(rows[:h - 4]):
        line = y + 2 + n
        if focused:
            item(app, r, line, clip(str(row.get("name", "")).upper(), w - 26),
                 lambda name=row["name"], uid=you["uid"]: use_battle_item(app, name, uid),
                 x=x + 3, fg="text")
        else:
            r.put(x + 3, line, clip(str(row.get("name", "")).upper(), w - 26), "text")
        r.put(x + w - 22, line, f"x{row.get('qty', 1)}", "faint")
        r.put(x + w - 14, line, clip(str(row.get("effect") or row.get("desc") or ""), 12),
              "faint")


def _battle_panel_flee(app, r: Region, x: int, y: int, w: int, h: int) -> None:
    """Whether the way out opened, stated in as many words."""
    event = (getattr(app, "tray", None) or {}).get("e") or {}
    away = bool(event.get("success"))
    r.put(x + 2, y, " BREAK OFF ", "cyan", BOLD)
    r.put(x + 4, y + 4, "GOT AWAY." if away else "CORNERED.",
          "green" if away else "red", BOLD)
    r.put(x + 4, y + 6,
          "You slip back the way you came." if away
          else "There is no way out. It gets a free swing.",
          "faint")


def _battle_panel_confirm(r: Region, x: int, y: int, w: int, h: int,
                          pending: dict) -> None:
    """A deliberate stop before something that cannot be taken back."""
    r.put(x + 2, y, " CONFIRM ", "amber", BOLD)
    r.put(x + 4, y + 3, str(pending.get("title", "ARE YOU SURE?")), "bright", BOLD)
    r.put(x + 4, y + 5, str(pending.get("body", "")), "faint")
    r.put(x + 4, y + 8, "ENTER to continue", "amber", BOLD)
    r.put(x + 4, y + 9, "ESC to go back", "faint")


def _battle_panel_capture(app, r: Region, x: int, y: int, w: int, h: int,
                          targets: list) -> None:
    """The bind readout: a bar that either closes or cracks.

    It reports the outcome, never the odds. A player learns what makes a bind
    likely by weakening things and trying, which is the whole point of it.
    """
    r.put(x + 2, y, " BIND ", "green", BOLD)
    tray = getattr(app, "tray", None) or {}
    event = tray.get("e") or {}
    name = str(event.get("target") or (targets[0].get("name") if targets else "it"))
    bar_x, bar_y, bar_w = x + 4, y + 5, w - 8

    if tray.get("kind") != "capture":
        r.put(x + 4, y + 3, "The bind is ready.", "faint")
        r.put(x + 4, y + 4, "A weakened creature is far easier to hold.", "faint")
        return

    caught = bool(event.get("success"))
    elapsed = time.time() - float(tray.get("at") or 0.0)
    progress = min(1.0, elapsed / CAPTURE_FILL_SECONDS) if CAPTURE_FILL_SECONDS else 1.0
    settled = progress >= 1.0
    filled = int(bar_w * progress)
    r.put(x + 4, y + 3, f"Binding {name.upper()}...", "bright", BOLD)
    r.put(bar_x, bar_y, "[" + "\u2588" * filled + "\u00b7" * (bar_w - filled) + "]",
          "green" if (caught or not settled) else "red")
    if settled:
        r.put(x + 4, bar_y + 2,
              "HELD. It is yours." if caught else "IT CRACKED. The bind broke.",
              "green" if caught else "red", BOLD)


def _battle_overlay(app, r: Region, title: str, fg: str) -> None:
    """A calm, centered interruption for bag and party choices."""
    x, w = max(12, (r.w - 58) // 2), min(58, r.w - 24)
    r.s.frame(r.x + x, r.y + 2, w, min(16, r.h - 3), "line", title, fg)


def _battle_header(app, r: Region, b: dict) -> None:
    run = app.state.get("run") or {}
    room = f"ROOM {run.get('depth', 0)}/{run.get('rows', 0)}" if run else "FIELD ENGAGEMENT"
    r.put(1, 0, "RAID COMBAT", "bright", BOLD)
    r.put(15, 0, clip(str(b.get("title", "")), 38), "dim")
    r.right(0, 0, r.w - 1, f"{room}   TURN {b.get('round', 1)}", "amber", BOLD)
    r.hline(1, 1, r.w - 2, "line", "─")
    r.put(1, 1, "ALLY", "green", BOLD)


def _battle_creature_card(app, r: Region, x: int, y: int, w: int, h: int,
                          unit: dict, ally: bool = False, enemy: bool = False,
                          selected: bool = False, index: int = 0) -> None:
    frame_fg = "amber" if selected else "line"
    r.s.frame(r.x + x, r.y + y, w, h, frame_fg)
    if selected:
        r.put(x - 1, y + 1, "›", "amber", BOLD)
    mark = rarity_mark(unit)
    name = clip(unit.get("name", "UNKNOWN").upper(), max(6, w - 9))
    prefix = f"{index} " if index else ""
    r.put(x + 2, y + 1, prefix + mark + " " + name, rarity_fg(unit), BOLD)
    r.right(x + 1, y + 1, w - 2, f"L{unit.get('level', 1)}", "faint")
    if _pixels_ready(r, unit):
        r.s.sprite(unit["sprite_asset"], r.x + x + w // 2 - 5, r.y + y + 3, 10, 4)
    else:
        portrait = unit.get("portrait") or []
        lines = portrait[:3] if portrait else ["·"]
        for n, line in enumerate(lines):
            r.put(x + max(2, (w - len(line)) // 2), y + 3 + n, line,
                  rarity_fg(unit) if enemy else "accent")
    _battle_flash(app, r, unit, x, y, w, h)
    r.put(x + 2, y + h - 3, f"HP {unit.get('hp', 0)}/{unit.get('max_hp', 0)}", "bright" if ally else "text")
    r.bar(x + 2, y + h - 2, w - 4, unit.get("hp", 0), unit.get("max_hp", 1),
          "green" if ally else "red")


def _battle_target_item(app, r: Region, x: int, y: int, w: int, h: int, target: dict) -> None:
    # Clickable, but deliberately not in the keyboard ring: targets are chosen
    # with T or the number keys, so up/down stays inside the pane in hand.
    i = len(app.items)
    app.items.append({"action": lambda uid=target["uid"]: aim_at(app, uid),
                      "label": target.get("name", "target")})
    for row in range(y, y + h):
        app.click_map[(r.y + row, r.x + x, r.x + x + w)] = ("index", i)


def _battle_move_card(app, r: Region, x: int, y: int, w: int, h: int,
                      move: dict, slot: int, focusable: bool = True) -> None:
    usable = bool(move.get("usable"))
    selected = False
    if focusable:
        i = len(app.items)
        app.items.append({"action": (lambda m=move: choose_move(app, m)) if usable else None,
                          "label": move.get("name", "MOVE"),
                          "nav": (r.x + x + w // 2, r.y + y + h // 2)})
        selected = i == app.cursor
        for row in range(y, y + h):
            app.click_map[(r.y + row, r.x + x, r.x + x + w)] = ("index", i)
    r.s.frame(r.x + x, r.y + y, w, h, "amber" if selected else "line")
    fg = "bright" if selected else ("text" if usable else "faint")
    r.put(x + 2, y + 1, f"{slot + 1}  {clip(move.get('name', 'MOVE').upper(), w - 6)}", fg, BOLD if selected else 0)
    r.hline(x + 2, y + 2, min(w - 4, 14), "line", "─")
    if move.get("power"):
        pp = f"PP {move.get('pp_left', move.get('pp', 0))}/{move.get('pp', 0)}" if move.get("pp") else "PP ∞"
        r.put(x + 2, y + 3, pp, "cyan")
        r.put(x + 2, y + 4, f"DMG {move.get('damage', move.get('power', 0))}  {move.get('accuracy', 100):g}%", "amber")
    else:
        effect = clip(move.get("effect") or "Brace this round.", w - 4)
        pp = f"PP {move.get('pp_left', move.get('pp', 0))}/{move.get('pp', 0)}" if move.get("pp") else "PP ∞"
        r.put(x + 2, y + 3, pp, "cyan")
        r.put(x + 2, y + 4, effect, "green")


def _battle_empty_move_card(r: Region, x: int, y: int, w: int, h: int, slot: int) -> None:
    r.s.frame(r.x + x, r.y + y, w, h, "line")
    r.put(x + 2, y + 1, f"{slot + 1}  SLOT OPEN", "faint")
    r.hline(x + 2, y + 2, min(w - 4, 14), "line", "─")
    r.put(x + 2, y + 4, "AUTHOR IN FORGE", "faint")


def enter_battle_panel(app, mode: str) -> None:
    """Step from the standing menu into the panel it opens."""
    set_battle_mode(app, mode)
    app.battle_focus = "panel"
    app.cursor = 0
    app.snap_cursor = True


def leave_battle_panel(app) -> None:
    """Step back out to the menu."""
    app.battle_focus = "menu"
    app.cursor = 0
    app.snap_cursor = True


def ask_battle_confirm(app, title: str, body: str, action) -> None:
    """Hold an irreversible action behind one more press of enter."""
    app.battle_confirm = {"title": title, "body": body, "action": action}
    app.battle_focus = "menu"


def capture_target(app) -> None:
    """Attempt a bind, once the player has confirmed it."""
    def go():
        set_battle_mode(app, "capture")
        app.battle_focus = "menu"
        app.act("battle", {"move": "capture"})
    ask_battle_confirm(app, "ATTEMPT A BIND?",
                       "A failed bind still costs you the turn.", go)


def flee_battle(app) -> None:
    """Break off, once the player has confirmed it."""
    def go():
        app.battle_confirm = None
        app.act("battle", {"move": "flee"})
    ask_battle_confirm(app, "BREAK OFF AND RUN?",
                       "You will leave with nothing from this fight.", go)


def set_battle_mode(app, mode: str) -> None:
    app.battle_mode = mode
    app.cursor = 0


def classic_move(app, move: dict) -> None:
    app.battle_mode = "main"
    app.battle_focus = "menu"
    app.snap_cursor = True
    app.battle_confirm = None
    target = app.sel_target or (app.state.get("battle") or {}).get("active_enemy")
    app.act("battle", {"move": "skill", "skill": move["index"], "target": target})


def use_battle_item(app, name: str, uid: int) -> None:
    app.battle_mode = "main"
    app.battle_focus = "menu"
    app.snap_cursor = True
    app.battle_confirm = None
    app.act("use_item", {"name": name, "target": uid})


def switch_battle_creature(app, uid: int) -> None:
    app.battle_mode = "main"
    app.battle_focus = "menu"
    app.snap_cursor = True
    app.battle_confirm = None
    app.act("battle", {"move": "switch", "target": uid})


def _mult_against(app, m: dict, tgt: dict) -> list:
    """The element line, but only for a creature you have actually killed before."""
    known = next((u.get("known") for u in (app.state["battle"]["enemies"])
                  if u["uid"] == tgt["uid"]), 0)
    if not known or abs(m.get("mult", 1.0) - 1.0) < 0.01:
        return []
    mult = m["mult"]
    word = "very weak" if mult >= 1.5 else "weak" if mult > 1 else "resists"
    return [(f"    ×{mult:g} {word}", el_col(m.get("type") or m.get("element")))]


def _move_rows(app, r: Region, my: int, opts: dict) -> int:
    moves = opts.get("moves", [])
    room = max(1, r.h - my - 3)
    for i, m in enumerate(moves[:room]):
        y2 = my + i
        idx = item(app, r, y2, clip(m["name"], 20),
                   (lambda mv=m: choose_move(app, mv)) if m["usable"] else None,
                   fg="text" if m["usable"] else "faint", hint_at=99)
        sel = idx == app.cursor
        r.put(0, y2, str(i + 1), "faint")
        move_type = m.get("type") or m.get("element") or ""
        r.put(25, y2, move_type, el_col(move_type))
        pp = f"PP {m.get('pp_left', m.get('pp', 0))}/{m.get('pp', 0)}" if m.get("pp") else "PP ∞"
        r.put(35, y2, pp, "cyan")
        if m["hit"] is not None:
            mult = m.get("mult", 1.0)
            r.put(42, y2, f"{m['hit']:.0f}%", "accent" if sel else "dim")
            r.put(48, y2, f"≈{m['damage']}", "bright" if sel else "dim")
            if abs(mult - 1.0) > 0.01:
                r.put(55, y2, f"×{mult:g}", el_col(move_type))
        else:
            who = ("your pack" if m.get("aims_at") == "allies"
                   else "itself" if m.get("aims_at") == "self" else "")
            note = clip(m.get("effect") or m.get("rating") or "", r.w - 46)
            if who:
                r.put(42, y2, who, "green")
                r.put(53, y2, clip(note, r.w - 55), "faint")
            else:
                r.put(42, y2, note, "faint")
    return len(moves[:room])


def aim_pool(app, move: dict) -> list:
    """Who this move can be pointed at: your pack if it helps, the other side
    if it hurts. A heal that made you pick an enemy was the old bug."""
    b = app.state.get("battle") or {}
    if move.get("aims_at") == "allies":
        return [u for u in (b.get("options") or {}).get("allies", []) if u["alive"]]
    return [u for u in b.get("enemies", []) if u["alive"]]


def choose_move(app, move: dict) -> None:
    """One thing to point at and it just fires. More than one and you pick."""
    pool = aim_pool(app, move)
    if not move.get("picks_one") or len(pool) <= 1:
        fire(app, move, pool[0]["uid"] if (pool and move.get("picks_one")) else None)
        return
    app.aim = move
    if not any(u["uid"] == app.sel_target for u in pool):
        app.sel_target = pool[0]["uid"]
    app.cursor = next((i for i, u in enumerate(pool) if u["uid"] == app.sel_target), 0)


def aim_at(app, uid: int) -> None:
    app.sel_target = uid
    if app.aim:
        move, app.aim = app.aim, None
        fire(app, move, uid)


def fire(app, move: dict, target=None) -> None:
    app.aim = None
    app.act("battle", {"move": "skill", "skill": move["index"],
                       "target": target if target is not None else app.sel_target})


# --- what the fight was worth -----------------------------------------------
def place_spoils(app, r: Region) -> None:
    sp = app.state.get("spoils")
    if not sp:
        r.put(2, 1, "nothing to divide.", "faint")
        return
    r.put(1, 0, "THE FIELD IS YOURS", "accent", BOLD)
    r.right(0, 0, r.w - 1, clip(sp.get("title", ""), 28), "faint")

    r.rich(1, 2, [(f"{sp['xp']}", "amber", BOLD), (" xp", "faint"),
                  (f"      {sp['gold']}", "gold", BOLD), ("g", "faint"),
                  (f"      {sp['shards']}", "magenta", BOLD), (" shards", "faint")])
    if sp.get("in_run"):
        r.right(0, 2, r.w - 1, "carried until you extract", "faint")

    y = 4
    for m in sp["party"]:
        if m.get("down"):
            r.put(2, y, clip(m["name"], 18), "faint")
            r.put(22, y, "down — no share", "faint")
            y += 1
            continue
        r.put(2, y, clip(m["name"], 18), "text")
        r.put(22, y, f"L{m['level']}", "faint")
        span = max(1, m.get("xp_span", 1))
        got = min(span, m.get("xp_done", 0) + m["gain"])
        r.bar(27, y, 14, got, span, "amber")
        if m["levels"]:
            r.rich(43, y, [(f"→ L{m['new_level']}", "amber", BOLD),
                           (f"  +{m['levels']} level" + ("s" if m["levels"] > 1 else ""),
                            "dim")])
        else:
            r.put(43, y, f"{max(0, m['xp_next'] - m['gain'])} to L{m['level'] + 1}", "dim")
        y += 1

    y += 1
    r.hline(1, y, r.w - 2, "line")
    r.put(2, y + 1, "WHAT CAME OFF THEM", "dim", BOLD)
    r.right(0, y + 1, r.w - 1, "space leaves one behind", "faint")
    y += 2
    loot = sp.get("loot") or []
    if not loot:
        r.put(3, y, "nothing worth carrying.", "faint")
        y += 1
    for row in loot[: max(0, r.h - y - 3)]:
        keep = row["name"] not in app.leaving
        i = item(app, r, y, clip(row["name"], 26),
                 (lambda n=row["name"]: toggle_loot(app, n)),
                 hint_at=99, fg="text" if keep else "faint",
                 mark="✓" if keep else "·")
        r.put(32, y, f"×{row['qty']}", "dim" if keep else "faint")
        r.put(38, y, f"{row['value'] * row['qty']}g", "gold" if keep else "faint")
        if row.get("usable"):
            r.put(46, y, "usable", "cyan" if keep else "faint")
        r.put(56, y, "left behind" if not keep else "", "faint")
        y += 1

    kept = sum(x["value"] * x["qty"] for x in loot if x["name"] not in app.leaving)
    item(app, r, r.h - 2, "Take it and move on",
         lambda: claim(app), fg="accent",
         hint=f"{kept}g of goods" if loot else "", hint_at=24)


def toggle_loot(app, name: str) -> None:
    if name in app.leaving:
        app.leaving.discard(name)
    else:
        app.leaving.add(name)


def claim(app) -> None:
    leave = sorted(app.leaving)
    app.leaving = set()
    app.act("claim", {"leave": leave})


PLACES = {
    "main": place_main, "main.saves": place_main_saves, "main.starter": place_main_starter, "main.layout": place_layout,
    "main.settings": place_main_settings, "main.look": place_look,
    "gate": place_gate, "gate.void": place_void_pick, "gate.pack": place_pack,
    "gate.pack.card": place_card, "gate.pack.build": place_skill_build, "gate.pack.equip": place_equipment,
    "gate.pack.move": place_move_detail,
    "gate.ledger": place_ledger,
    "gate.ledger.card": place_dex, "gate.ledger.move": place_move_detail,
    "gate.stall": place_stall,
    "gate.circle": place_circle, "gate.board": place_board, "gate.mission": place_mission,
    "void": place_run, "battle": place_battle, "spoils": place_spoils,
    "gate.look": place_look, "gate.layout": place_layout, "gate.farm": place_farm,
    "gate.farm.plant": place_farm_plant, "gate.farm.quantity": place_farm_quantity,
    "gate.craft": place_craft,
}


# --- bare keys, only while the command line is empty -------------------------
def hotkey(app, ch: str) -> bool:
    st = app.state
    b = st.get("battle")
    fighting = b and not b.get("finished")

    if app.place == "gate" and not fighting:
        shortcuts = {"v": "gate.void", "q": "gate.board", "f": "gate.farm",
                     "p": "gate.pack", "c": "gate.ledger", "o": "gate.stall",
                     "r": "gate.circle", "k": "gate.craft"}
        if ch.lower() in shortcuts:
            app.go(shortcuts[ch.lower()])
            return True

    if fighting and app.aim is None:
        # No letter shortcuts on the board. Everything is reached by moving the
        # cursor and pressing enter, so there is one way to do a thing rather
        # than two that behave differently. Left with nothing further left
        # steps back out to the menu.
        low = ch.lower()
        if low == "a" and getattr(app, "battle_focus", "menu") == "panel":
            before = app.cursor
            app.move_cursor(-1, 0)
            if app.cursor == before:
                leave_battle_panel(app)
            return True

    if ch.lower() in ("w", "a", "s", "d"):
        dx, dy = {"w": (0, -1), "a": (-1, 0),
                  "s": (0, 1), "d": (1, 0)}[ch.lower()]
        app.move_cursor(dx, dy)
        return True
    if ch == "?":
        command(app, "help"); return True

    if ch.isdigit() and ch != "0":
        i = int(ch) - 1
        if fighting and app.aim is not None:
            pool = aim_pool(app, app.aim)
            if i < len(pool):
                aim_at(app, pool[i]["uid"])
            return True
        if fighting:
            return True         # numbers do not bypass the menu any more
        elif i < len(app.items):
            app.cursor = i
            app.choose()
            return True

    if app.place == "spoils" and ch == " ":
        app.choose()
        return True

    if fighting:
        # P and T survive only because nothing on the board reaches them: there
        # is no SWITCH entry in the menu and no other way to change target.
        if ch.lower() == "p" and app.aim is None:
            set_battle_mode(app, "switch"); return True
        if ch == "t":
            targets = (b.get("options") or {}).get("targets") or []
            if targets:
                uids = [t["uid"] for t in targets]
                j = (uids.index(app.sel_target) + 1) % len(uids) if app.sel_target in uids else 0
                app.sel_target = uids[j]
                name = next(t["name"] for t in targets if t["uid"] == app.sel_target)
                app.say(f"aiming at {name}.", "faint")
            return True

    if ch in ("l", "L") and app.place.startswith("gate") and not fighting:
        app.go("gate.look"); return True

    if app.place == "void" and ch == "e":
        app.act("extract", {}); return True

    if app.place == "gate.pack":
        roster = st["roster"]
        here = roster[app.cursor]["uid"] if app.cursor < len(roster) else None
        if ch == " " and here is not None:
            if app.marked is None:
                app.marked = here
                app.say("marked. move to another and press space to swap.", "faint")
            elif app.marked == here:
                app.marked = None
                app.say("unmarked.", "faint")
            else:
                app.act("reorder", {"a": app.marked, "b": here})
                app.marked = None
                app.say("swapped.", "dim")
            return True
    return False


HELP = [
    ("arrows / W A S D", "move in four directions · enter chooses · esc goes back"),
    ("1-9", "jump straight to a line"),
    ("space", "in the pack: mark one, then space on another to swap"),
    ("walk [region]", "go into the Void"),
    ("down [n] / extract", "take a way on, or come back up"),
    ("attack [n] / guard / bind / auto / flee", "in a fight; X is the auto hotkey"),
    ("t", "in a fight: switch which one you are aiming at"),
    ("use <item>", "a salve, an ether, a phoenix ember"),
    ("scout <monster>", "what the ledger knows about it"),
    ("sell <item> / sell junk / buy <item>", "at the stall"),
    ("summon", "at the circle"),
    ("look [name] / bars [style]", "change how the game looks"),
    ("layout [name]", "balanced, wide, or pack-focused terminal panes"),
    ("colour <role> <#hex>", "e.g. colour accent #ff9c00"),
    ("glow / scanlines / vignette <0-1>", "how hard the glass glows"),
    ("rest / save / quit / clear", "housekeeping"),
]


def find_monster(app, name: str):
    name = (name or "").strip().lower()
    if not name:
        return None
    b = app.s.game.bestiary
    return b.get(name) or next((t for t in b.all if name in t.name.lower()), None)


def command(app, line: str) -> None:
    from engine import elements as EL
    parts = line.strip().split()
    if not parts:
        return
    verb, args = parts[0].lower(), parts[1:]
    rest = " ".join(args)
    st = app.state

    if verb in ("look", "theme"):
        from . import theme as TH
        names = [t["name"] for t in TH.presets()]
        if not args:
            app.go("gate.look")
            return
        want = args[0].lower()
        if want not in names:
            app.say("looks: " + ", ".join(names), "faint")
            return
        pick_look(app, want)
        return

    if verb == "layout":
        from . import layout as LAYOUT
        if not args:
            app.go("gate.layout" if app.place.startswith("gate") else "main.layout")
            return
        chosen = LAYOUT.use(args[0].lower())
        if chosen:
            app.say(f"layout is now {chosen['label'].lower()}.", "accent")
        else:
            app.say("layouts: " + ", ".join(LAYOUT.PRESETS), "faint")
        return

    if verb in ("colour", "color"):
        from . import theme as TH
        from .screen import PALETTE
        if len(args) < 2:
            app.say("colour <role> <#hex>   roles: " + ", ".join(PALETTE), "faint")
            return
        role, value = args[0].lower(), args[1]
        if TH.set_color(role, value, app.b):
            TH.save()
            app.say(f"{role} is {value} now.", role)
        elif role not in PALETTE:
            app.say(f"no such role. try: {', '.join(PALETTE)}", "faint")
        else:
            app.say(f"{value!r} is not a colour. try #ff9c00.", "red")
        return

    if verb == "bars":
        from . import theme as TH
        if args and TH.set_bars(args[0].lower(), app.b):
            TH.save()
            app.say(f"bars are {args[0].lower()} now.", "dim")
        else:
            app.say("bars: " + ", ".join(TH.BAR_STYLES), "faint")
        return

    if verb in ("glow", "scanlines", "vignette"):
        from . import theme as TH
        key = {"glow": "bloom"}.get(verb, verb)
        if args:
            try:
                TH.current()[key] = max(0.0, min(1.0, float(args[0])))
                TH.apply(TH.current(), app.b)
                TH.save()
            except ValueError:
                app.say("a number between 0 and 1.", "red")
                return
        app.say(f"{verb} {TH.current().get(key, 0):.2f}", "faint")
        return

    if verb in ("help", "?", "commands"):
        app.say("how it works —", "accent")
        for cmd, what in HELP:
            app.say(f"  {cmd:<34}{what}", "dim")
        return
    if verb == "clear":
        app.log.clear(); return
    if verb in ("quit", "exit"):
        app.s.game.save(); app.running = False; return
    if verb == "save":
        app.act("save"); return
    if verb == "rest":
        app.act("rest"); return
    if verb == "summon":
        app.act("summon", {}); return
    if verb == "buy":
        spec = next((s for s in st.get("stock", []) if rest.lower() in s["name"].lower()), None)
        if spec:
            app.act("buy", {"name": spec["name"], "qty": 1})
        else:
            app.say("the stall doesn't carry that.", "red")
        return
    if verb == "sell":
        if rest.lower() in ("junk", "all", "materials"):
            app.act("sell_junk", {}); return
        it = next((i for i in st["inventory"] if rest.lower() in i["name"].lower()), None)
        if it:
            app.act("sell", {"name": it["name"], "all": True})
        else:
            app.say(f"no '{rest}' in the bag.", "red")
        return

    if verb in ("walk", "go", "enter"):
        regions = st["regions"]
        if not regions:
            app.say("The Void Atlas is empty. Create a monster and assign it to a Forge Void Area first.", "amber")
            return
        key = app.region or regions[0]["key"]
        if rest:
            if rest.isdigit() and 1 <= int(rest) <= len(regions):
                key = regions[int(rest) - 1]["key"]
            else:
                hit = next((r for r in regions if rest.lower() in r["name"].lower()), None)
                if not hit:
                    app.say(f"no region called '{rest}'.", "red"); return
                key = hit["key"]
        app.act("start_run", {"region": key, "depth": app.depth})
        return
    if verb == "depth":
        keys = [d["key"] for d in st["depths"]]
        if rest.lower() in keys:
            app.depth = rest.lower()
            app.say(f"depth set to {app.depth}.", "dim")
        else:
            app.say("depth: " + " / ".join(keys), "faint")
        return
    if verb in ("down", "descend"):
        run = st.get("run")
        if not run:
            app.say("you're not in the Void.", "red"); return
        avail = run["map"]["available"]
        i = int(args[0]) - 1 if args and args[0].isdigit() else 0
        if 0 <= i < len(avail):
            app.act("descend", {"node": avail[i]})
        else:
            app.say("no way on there.", "red")
        return
    if verb in ("extract", "out", "leave"):
        app.act("extract", {}); return

    b = st.get("battle")
    if verb in ("attack", "hit", "move", "cast"):
        if not b or b.get("finished"):
            app.say("nothing to attack.", "red"); return
        moves = (b.get("options") or {}).get("moves") or []
        i = int(args[0]) - 1 if args and args[0].isdigit() else app.cursor
        if 0 <= i < len(moves):
            fire(app, moves[i])
        else:
            app.say("no such move.", "red")
        return
    if verb in ("guard", "bind", "capture", "auto", "flee"):
        if b and not b.get("finished"):
            app.act("battle", {"move": "capture" if verb in ("bind", "capture") else verb})
        return
    if verb == "use":
        it = next((i for i in st["inventory"] if rest.lower() in i["name"].lower()), None)
        if not it:
            app.say(f"no '{rest}' in the bag.", "red"); return
        app.act("use_item", {"name": it["name"],
                             "target": st["party"][0]["uid"] if st["party"] else None})
        return

    if verb in ("scout", "codex", "dex"):
        t = find_monster(app, rest)
        if not t:
            app.say(f"nothing in the ledger matches '{rest}'.", "red"); return
        kills = app.s.game.kills.get(t.name, 0)
        app.say(f"{t.name} — {t.title or t.role}", "accent")
        app.say(f"  {t.primary}{'/' + t.secondary if t.secondary else ''} · {t.size} · "
                f"{t.family} · level {t.level} · {t.rarity} · killed {kills}×", "dim")
        if kills or t.id in app.s.game.seen:
            app.say("  weak    " + (", ".join(f"{e} ×{m:g}" for e, m in EL.weaknesses(t)[:4])
                                    or "nothing much"), "amber")
            app.say("  resists " + (", ".join(f"{e} ×{m:g}" for e, m in EL.resistances(t)[:4])
                                    or "nothing"), "cyan")
            app.say(f"  hp {t.stats['hp']}  atk {t.stats['atk']}  def {t.stats['def']}  "
                    f"mag {t.stats['mag']}  res {t.stats['res']}  spd {t.stats['spd']}", "dim")
        else:
            app.say("  unscouted. kill one and the ledger fills in.", "faint")
        if t.lore:
            app.say("  " + t.lore[:150], "dim")
        return
    if verb == "pack":
        if not rest:
            app.root("gate"); app.go("gate.pack"); return
        m = next((x for x in st["roster"] if rest.lower() in x["name"].lower()), None)
        if not m:
            app.say(f"nobody called '{rest}'.", "red"); return
        open_card(app, m["uid"], m["name"])
        return
    if verb == "swap":
        m = next((x for x in st["roster"] if rest.lower() in x["name"].lower()), None)
        if not m:
            app.say(f"nobody called '{rest}'.", "red"); return
        app.act("toggle_party", {"uid": m["uid"]})
        return

    app.say(f"'{verb}' isn't a command. try  help", "red")
