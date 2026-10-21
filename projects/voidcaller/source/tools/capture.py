#!/usr/bin/env python3
"""Capture the real terminal screens, colours and all, as HTML fragments."""
from __future__ import annotations
import contextlib, io, json, os, random, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import balance as B, combat, quests, shop, story, summon, team, ui, void
from engine.data import load_bestiary
from engine.entities import spawn
from engine.state import Game
import main as game_main

random.seed(20)
ui.USE_COLOR = True
ui.QUIET = False

class Script:
    def __init__(self, answers): self.a = list(answers); self.n = 0
    def menu(self, title, options, back="back", allow_back=True):
        self.n += 1
        if title: ui.say(ui.c(title, "bold"))
        for i, o in enumerate(options, 1):
            ui.say(f"  {ui.c(str(i).rjust(2), 'bright_cyan')}. {o}")
        if allow_back: ui.say(f"   {ui.c('0', 'grey')}. {ui.c(back, 'grey')}")
        v = self.a.pop(0) if self.a else (-1 if allow_back else 0)
        ui.say(ui.c("> ", "bright_cyan") + str(v + 1 if isinstance(v, int) and v >= 0 else 0))
        return v
    def ask(self, p, d=""):
        self.n += 1
        v = self.a.pop(0) if self.a else d
        ui.say(ui.c(p, "bright_cyan") + str(v)); return str(v)
    def confirm(self, p):
        self.n += 1
        v = self.a.pop(0) if self.a else True
        ui.say(ui.c(p + " (y/n) ", "bright_cyan") + ("y" if v else "n")); return bool(v)

def drive(answers):
    s = Script(answers)
    ui.menu, ui.ask, ui.confirm, ui.pause = s.menu, s.ask, s.confirm, lambda *a, **k: None
    return s

def grab(fn, answers=(), limit=None):
    drive(answers)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try: fn()
        except Exception as exc: print(f"[capture stopped: {exc}]")
    out = buf.getvalue().rstrip("\n").split("\n")
    if limit: out = out[:limit]
    return "\n".join(out)

# --- ansi -> html ----------------------------------------------------------
PAL = {"30":"#0b1a18","31":"#c8524b","32":"#4bbf8f","33":"#c9a24a","34":"#5a8fc2",
       "35":"#a86cc9","36":"#4fb9ad","37":"#cfe8e1","90":"#5d817a",
       "91":"#e2554d","92":"#45e0b8","93":"#e0b451","96":"#6fd3e0"}
ANSI = re.compile(r"\033\[([0-9;]*)m")

def to_html(text: str) -> str:
    out, open_spans = [], 0
    pos = 0
    for m in ANSI.finditer(text):
        out.append(esc(text[pos:m.start()])); pos = m.end()
        codes = [c for c in m.group(1).split(";") if c] or ["0"]
        for c in codes:
            if c == "0":
                out.append("</span>" * open_spans); open_spans = 0
            elif c == "1":
                out.append('<span style="font-weight:600">'); open_spans += 1
            elif c == "2":
                out.append('<span style="opacity:.65">'); open_spans += 1
            elif c in PAL:
                out.append(f'<span style="color:{PAL[c]}">'); open_spans += 1
    out.append(esc(text[pos:]))
    out.append("</span>" * open_spans)
    return "".join(out)

def esc(s): return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

# --- build a game to photograph -------------------------------------------
b = load_bestiary()
g = Game(b)
g.hunter = "Ashgrove"
g.gold, g.shards, g.day = 1240, 62, 4
for t in (b.get("Gravehound"), b.get("Mushroom King"), b.get("Frostclaw"), b.get("Salt Mirage")):
    if t: g.add_monster(t, 11)
for m in g.roster: m.full_heal()
g.party[2].cur_hp = int(g.party[2].max_hp * 0.45)
for item in ("Gravebone Shard", "Mushroom Cap", "Void Salve", "Frostscale Fragment"):
    g.add_item(item, 3)
g.board = quests.generate_board(g, 5)
for q in g.board[:2]:
    q.start(g); g.quests.append(q)
g.board = g.board[2:]
for t in b.all[:28]: g.seen.add(t.id)
g.kills["Gravehound"] = 4

S = {}
S["title"] = to_html("\n".join([ui.c(game_main.TITLE, "bright_cyan"),
    ui.c("        a dice hunt in the dark   -   121 species bound to the ledger", "grey"),
    "", ui.c("  " + " 1. New hunt", "bright_cyan"), "   2. Continue", "   3. Quit",
    ui.c("> 1", "bright_cyan")]))

def hub_once():
    ready = sum(1 for q in g.quests if q.done(g))
    ui.header("THE GATE TOWN", f"day {g.day}  -  {g.hunter}  -  {g.gold}g  -  {g.shards} shards")
    for m in g.party:
        ui.say(f"  {ui.c(m.name, 'bold'):<28} L{m.level:<3} "
               f"{ui.bar(m.cur_hp, m.max_hp, 14)} {m.cur_hp}/{m.max_hp}")
    opts = [ui.c("Walk into the Void", "bright_cyan") + ui.c("   fight, gather, extract", "grey"),
        "Quest board" + (ui.c(f"   {ready} ready to turn in", "bright_yellow") if ready else ui.c(f"   {len(g.quests)} active", "grey")),
        "The stall" + ui.c("   buy and sell", "grey"),
        "The circle" + ui.c(f"   summon  ({g.shards} shards)", "grey"),
        "The thread" + ui.c(f"   story  ({g.story}/4 chapters)", "grey"),
        "The pack" + ui.c(f"   {len(g.roster)} monsters", "grey"),
        "The ledger" + ui.c(f"   {len(g.seen)}/{len(g.bestiary)} species", "grey"),
        "Rest" + ui.c("   heal everything, free", "grey"), "Save", "Save and quit"]
    ui.menu("", opts, allow_back=False)
S["hub"] = to_html(grab(hub_once, [0]))

def board():
    ui.header("QUEST BOARD", f"day {g.day} - {g.hunter} - {g.gold}g")
    ui.say(ui.c(" ACCEPTED", "bright_green"))
    for q in g.quests: ui.say("   " + q.label(g))
    ui.say(ui.c(" OFFERED", "bright_cyan"))
    for q in g.board: ui.say("   " + q.label())
    ui.menu("", ["Read / accept a contract", "Turn in", "Abandon a contract"], back="leave the board")
S["board"] = to_html(grab(board, [0]))

S["region"] = to_html(grab(lambda: void.region_menu(g), [-1]))

party = g.party
foes = [spawn(b.get("Fungal Drake"), 12, enemy=True),
        spawn(b.get("Mold Wraith") or b.get("Bone Wraith"), 11, enemy=True)]
g.kills["Fungal Drake"] = 2
S["battle"] = to_html(grab(lambda: combat.battle(party, foes, game=g, auto=True,
                     title="THE FUNGAL CAVERN - encounter 3/5"), limit=46))
for m in g.roster: m.full_heal()

S["card"] = to_html(grab(lambda: team.card(g, g.roster[0]), [-1]))
S["ledger"] = to_html(grab(lambda: team.bestiary_screen(g), [], limit=26))
S["stall"] = to_html(grab(lambda: shop.screen(g), [0, -1, -1]))
S["circle"] = to_html(grab(lambda: summon.screen(g), [0, -1]))
S["thread"] = to_html(grab(lambda: story.screen(g), [-1]))

json.dump(S, open("/tmp/vc_screens.json", "w"))
print("captured:", ", ".join(f"{k} ({len(v)}b)" for k, v in S.items()))
