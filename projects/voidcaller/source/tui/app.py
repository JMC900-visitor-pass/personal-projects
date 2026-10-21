"""The shell: a fixed terminal dashboard, one place at a time, WASD and enter.

There are no tabs. You are somewhere -- the gate, the stall, the pack, a fight --
and you move up and down a list, press enter to act, and escape to go back.
Every list works the same way, so nothing has to be learned twice.
"""
from __future__ import annotations

import time
from collections import deque

from engine.session import Session
from engine.state import Game
from engine.data import load_bestiary

from . import places as P
from . import layout as LAYOUT
from .screen import BOLD, DIM, Region, Screen

COLS, ROWS = 118, 45
MAIN_W = 78
LOG_W = COLS - 4


def set_grid(cols: int, rows: int | None = None) -> None:
    """Resize the logical character canvas before the shell is built.

    The board is drawn in character cells, and every screen lays itself out
    against the region it is handed rather than against fixed coordinates, so
    widening the grid simply gives each page more room. Matching the grid to
    the monitor's shape is what removes the pillarbox bars in fullscreen: the
    canvas already has the screen's aspect ratio, so nothing has to be
    letterboxed to fit.
    """
    global COLS, ROWS, LOG_W, BODY_H, Y_RULE2, Y_LOG, Y_RULE3
    global Y_CMD, Y_RULE4, Y_STATUS, FOLIO_BODY_H
    COLS = max(118, int(cols))
    if rows is not None:
        ROWS = max(45, int(rows))
    LOG_W = COLS - 4
    # The page absorbs whatever height the screen has. Everything below the
    # body is a fixed stack — a rule, the notebook, the prompt, the status
    # line — so the body takes the remainder rather than the constants being
    # written down twice.
    BODY_H = ROWS - 17
    Y_RULE2 = Y_BODY + BODY_H
    Y_LOG = Y_RULE2 + 1
    Y_RULE3 = Y_LOG + LOG_H
    Y_CMD = Y_RULE3 + 1
    Y_RULE4 = Y_CMD + 1
    Y_STATUS = Y_RULE4 + 1
    FOLIO_BODY_H = Y_STATUS - Y_BODY - 2

# The shell deliberately has breathing room. It is a field journal, not a
# bank of blinking panels: one quiet masthead, one page, a small notebook trail,
# then the command prompt.
Y_HEAD, Y_PROG, Y_RULE1 = 1, 2, 3
Y_BODY, BODY_H = 5, 28
Y_RULE2 = Y_BODY + BODY_H
Y_LOG, LOG_H = Y_RULE2 + 1, 6
Y_RULE3 = Y_LOG + LOG_H
Y_CMD = Y_RULE3 + 1
Y_RULE4 = Y_CMD + 1
Y_STATUS = Y_RULE4 + 1
FOLIO_BODY_H = Y_STATUS - Y_BODY - 2


class App:
    def __init__(self, backend, session: Session | None = None):
        self.b = backend
        self.s = session or Session(Game(load_bestiary()))
        self.screen = Screen(COLS, ROWS)
        self.screen.pixels = bool(getattr(backend, "pixels", False))
        self.log: deque = deque(maxlen=400)
        self.cmd = ""
        self.hist: list[str] = []
        self.hist_i = 0
        self.nav: list[str] = ["gate" if self.s.game.roster else "main"]
        self.idx: dict[str, int] = {}
        self.items: list[dict] = []
        self.scroll = 0
        self.running = True
        self.pending: list = []
        self.next_at = 0.0
        self.tray = None
        self.depth = "deep"
        self.region = None
        self.marked = None            # uid held for a swap
        self.focus_uid = None         # monster or species being looked at
        self.move_origin = None       # pack | dex — source for move inspection
        self.move_index = 0
        self.focus_move_name = ""
        self.sel_target = None
        self.sel_move = 0
        self.aim = None               # the move waiting for a target
        self.battle_mode = "main"     # main cards | bag | switch
        self.farm_crop = None         # crop waiting for a plot quantity
        self.leaving = set()          # loot being left on the field
        self.click_map: dict = {}
        self.state = self.s.state()
        self.say("VOIDCALLER · the gate is a hole in the air behind the tannery.", "dim")
        self.say("WASD or arrows move · enter selects · esc goes back · ? opens help", "faint")
        self.sync()

    # -- where you are -------------------------------------------------------
    @property
    def place(self) -> str:
        return self.nav[-1]

    @property
    def cursor(self) -> int:
        return self.idx.get(self.place, 0)

    @cursor.setter
    def cursor(self, v: int) -> None:
        self.idx[self.place] = max(0, v)

    def go(self, place: str) -> None:
        if self.place != place:
            self.nav.append(place)
            self.idx.setdefault(place, 0)
            if place == "battle":
                # A fight always opens on its first action. Carrying a cursor
                # over from the last fight is how enter ends up firing FLEE.
                self.battle_focus = "menu"
                self.snap_cursor = True
                self.battle_confirm = None

    def back(self) -> None:
        if len(self.nav) > 1:
            self.nav.pop()

    def root(self, place: str) -> None:
        self.nav = [place]
        self.idx.setdefault(place, 0)

    def sync(self) -> None:
        """The world can move you: a fight starts, a run ends, a fight is won."""
        st = self.state
        if st.get("starter_choices"):
            if self.place != "main.starter":
                self.root("main.starter")
            return
        if not self.s.game.roster:
            if not self.place.startswith("main"):
                self.root("main")
            return
        if st.get("spoils"):
            if self.place != "spoils":
                self.root("spoils")
                self.cursor = 0
            return
        self.leaving = set()
        if st.get("battle") and not st["battle"].get("finished"):
            if self.place != "battle":
                self.root("battle")
                self.aim = None
                self.battle_mode = "main"
            opts = st["battle"].get("options") or {}
            targets = opts.get("targets") or []
            if not any(t["uid"] == self.sel_target for t in targets):
                self.sel_target = targets[0]["uid"] if targets else None
                self.aim = None
        elif st.get("battle"):
            self.root("battle")
        elif st.get("run"):
            if self.place != "void":
                self.root("void")
        elif self.place in ("battle", "void", "spoils"):
            self.root("gate")

    # -- log -----------------------------------------------------------------
    def say(self, text: str, fg: str = "text") -> None:
        import textwrap
        for chunk in str(text).split("\n"):
            if len(chunk) <= LOG_W:
                self.log.append((chunk, fg))
                continue
            indent = " " * (len(chunk) - len(chunk.lstrip()))
            for i, part in enumerate(textwrap.wrap(chunk, LOG_W - len(indent) - 2)):
                self.log.append(((indent if i == 0 else indent + "  ") + part, fg))
        self.scroll = 0

    def say_events(self, events) -> None:
        self.pending.extend(events or [])

    def drain(self) -> None:
        if not self.pending or time.time() < self.next_at:
            return
        e = self.pending.pop(0)
        text, fg = P.event_line(e)
        if text:
            self.say(text, fg)
        k = e.get("k")
        now = time.time()
        if k == "attack":
            self.tray = {"kind": "attack", "e": e, "at": now}
        elif k in ("damage", "hit", "heal"):
            # Hit events are the source of truth from the battle rules.  Keep
            # the last one visible long enough for the combat board to land a
            # proper damage number over its target card.
            self.tray = {"kind": "hit", "e": e, "at": now}
        elif k == "miss":
            self.tray = {"kind": "miss", "e": e, "at": now}
        elif k == "status":
            self.tray = {"kind": "status", "e": e, "at": now}
        elif k == "flee":
            self.tray = {"kind": "flee", "e": e, "at": now}
        elif k == "capture":
            # The board draws a bind bar from this; `at` is when it began
            # filling, so the bar animates rather than snapping to a result.
            self.tray = {"kind": "capture", "e": e, "at": now}
        elif k in ("round", "battle_start"):
            self.tray = None
        elif k == "end" and self.tray and self.tray.get("kind") == "capture":
            pass          # let a successful bind finish showing its bar
        elif k == "end":
            self.tray = None
        self.next_at = time.time() + P.EVENT_PACE.get(k or "", 0.16)

    @property
    def busy(self) -> bool:
        return bool(self.pending)

    # -- engine --------------------------------------------------------------
    def act(self, action: str, payload: dict | None = None) -> None:
        if self.busy:
            return
        self.state = self.s.act(action, payload or {})
        self.say_events(self.state.get("events"))
        if self.state.get("message"):
            self.say(self.state["message"], "amber")
        self.sync()

    # -- items the current place offers -------------------------------------
    def choose(self) -> None:
        pending = getattr(self, "battle_confirm", None)
        if pending and self.place == "battle":
            self.battle_confirm = None
            pending["action"]()
            return
        if 0 <= self.cursor < len(self.items):
            action = self.items[self.cursor].get("action")
            if action:
                action()

    def move_cursor(self, dx: int, dy: int) -> None:
        """Move to the nearest selectable item in a cardinal direction.

        Items publish their screen position while drawing, so the same code
        handles lists, two-column grids, the atlas and the dashboard.
        """
        if not self.items:
            return
        self.cursor = min(self.cursor, len(self.items) - 1)
        current = self.items[self.cursor].get("nav")
        if current is None:
            # Sitting on something that is drawn but not navigable (an enemy
            # card, say). Jump straight to the first real destination rather
            # than shuffling one slot per keypress.
            landing = next((i for i, row in enumerate(self.items)
                            if row.get("nav") is not None), None)
            self.cursor = landing if landing is not None else self.cursor
            return
        cx, cy = current
        choices = []
        for i, row in enumerate(self.items):
            if i == self.cursor or row.get("nav") is None:
                continue
            x, y = row["nav"]
            along = (x - cx) * dx + (y - cy) * dy
            if along <= 0:
                continue
            across = abs((x - cx) * dy - (y - cy) * dx)
            # Prefer staying in the same row/column, then the nearest item.
            choices.append((across * 4 + along, across, along, i))
        if choices:
            self.cursor = min(choices)[-1]

    # -- drawing -------------------------------------------------------------
    def draw(self) -> None:
        s, st = self.screen, self.state
        s.clear()
        self.click_map = {}
        # Combat is a full page like a folio: it displaces the generic NOTES
        # rail rather than sharing the screen with it. The end-of-fight summary
        # already reports what happened, so a running log underneath the board
        # is duplicated furniture.
        folio = P.is_folio_page(self.place) or self.place == "battle"

        run = st.get("run")
        mission = st.get("mission")
        has_world = bool(st.get("species"))
        where = (run["map"]["region"].upper() + "  /  " + run["map"]["depth_label"].upper()
                 if run else "THE GATE" if self.s.game.roster else "DRAFT WORLD")
        s.put(2, Y_HEAD, "VOIDCALLER", "bright", BOLD)
        if folio:
            s.put(14, Y_HEAD, "// " + P.folio_title(self.place), "green", BOLD)
            s.center(Y_HEAD, "TERMINAL › FIELD FOLIO", "faint", 0, 2, COLS - 4)
        else:
            s.put(14, Y_HEAD, "FIELD CONSOLE", "faint")
            s.center(Y_HEAD, where, "dim", BOLD if run else 0, 2, COLS - 4)
        clock = st.get("world_time") or {}
        s.right(2, Y_HEAD, COLS - 4,
                f"DAY {st['day']}  {clock.get('label', '')}  {st['gold']}g  {st['shards']} shards", "amber")

        if run:
            depth, total = run["map"]["row"], max(1, run["map"]["rows_total"] - 1)
            label = "MISSION RAID" if run.get("quest_uid") else "VOID EXPEDITION"
            s.put(2, Y_PROG, label, "amber" if mission and run.get("quest_uid") else "dim", BOLD)
            s.put(23, Y_PROG, "RAID PROGRESS", "bright", BOLD)
            node_total = min(7, max(3, total + 1))
            current = min(node_total - 1, int(round(depth / total * (node_total - 1))))
            for i in range(node_total):
                x = 43 + i * 5
                if i < current:
                    mark, fg = "●", "green"
                elif i == current:
                    mark, fg = "◉", "amber"
                else:
                    mark, fg = "○", "line"
                s.put(x, Y_PROG, mark, fg, BOLD)
                if i < node_total - 1:
                    s.put(x + 1, Y_PROG, "────", "green" if i < current else "line")
            s.put(80, Y_PROG, f"ROOM {depth}/{total}", "accent", BOLD)
            s.put(96, Y_PROG, f"{max(0, total-depth)} LEFT", "faint")
        elif mission:
            s.put(2, Y_PROG, "SIGNED MISSION", "amber", BOLD)
            s.put(19, Y_PROG, P.clip(mission["title"].upper(), 28), "text")
            s.bar(49, Y_PROG, 28, mission["have"], mission["qty"], "accent")
            s.put(79, Y_PROG, f"OBJECTIVE {mission['have']}/{mission['qty']}",
                  "accent" if mission["done"] else "faint", BOLD)
        else:
            party = st.get("party") or []
            hurt = sum(1 for m in party if m["hp"] < m["max_hp"])
            s.put(2, Y_PROG, "WORLD STATUS", "dim", BOLD)
            if has_world:
                s.put(18, Y_PROG, f"{len(party)} bound  ·  {hurt} wounded  ·  "
                                  f"ledger {st['seen']}/{st['species']}", "faint")
            else:
                s.put(18, Y_PROG, "no creatures, areas, or missions authored", "faint")
        s.hline(2, Y_RULE1, COLS - 4, "line", "─")

        landing = self.place.startswith("main")
        if landing:
            # The title and settings are full pages. An empty party rail beside
            # a new world makes the screen look unfinished.
            main = Region(s, 13, Y_BODY, COLS - 26, BODY_H)
            side = None
            content = main
            if self.place != "main":
                main.put(0, 0, P.breadcrumb(self), "dim", BOLD)
                main.hline(0, 1, main.w, "line", "─")
                content = main.sub(0, 3, main.w, main.h - 3)
        elif self.place == "battle":
            # Combat owns the whole page: a board needs room for the ally,
            # targets and move cards to read at one glance.
            main = Region(s, 2, Y_BODY, COLS - 4, FOLIO_BODY_H)
            side = None
            main.put(0, 0, P.breadcrumb(self), "dim", BOLD)
            main.hline(0, 1, main.w, "line", "─")
            content = main.sub(0, 3, main.w, main.h - 3)
        elif folio:
            # Field folios are full places, with room for a plot grid, a live
            # companion entry or a merchant's item card.  They deliberately
            # displace the generic log rail instead of cramming into it.
            main = Region(s, 2, Y_BODY, COLS - 4, FOLIO_BODY_H)
            side = None
            content = main
        else:
            main_w = max(56, min(COLS - 27, int(LAYOUT.current().get("main_width", MAIN_W))))
            main = Region(s, 2, Y_BODY, main_w, BODY_H)
            divider = main.x + main.w + 1
            s.vline(divider, Y_BODY, BODY_H, "line", "│")
            side = Region(s, divider + 2, Y_BODY, COLS - (divider + 4), BODY_H)
            main.put(0, 0, P.breadcrumb(self), "dim", BOLD)
            main.hline(0, 1, main.w, "line", "─")
            content = main.sub(0, 3, main.w, main.h - 3)

        self.items = []
        P.PLACES.get(self.place, P.place_gate)(self, content)
        self.cursor = min(self.cursor, max(0, len(self.items) - 1))
        # The cursor must never rest on something that is drawn but cannot be
        # chosen — an enemy card, say. Items only exist once the screen has
        # been drawn, so the landing spot is settled here rather than guessed
        # at the moment focus changed.
        resting = self.items[self.cursor] if self.items else None
        if getattr(self, "snap_cursor", False) or (
                resting is not None and resting.get("nav") is None):
            first = next((i for i, row in enumerate(self.items)
                          if row.get("nav") is not None), None)
            if first is not None:
                self.cursor = first
        self.snap_cursor = False
        if side is not None:
            P.sidebar(self, side)

        if folio:
            s.hline(2, Y_STATUS - 2, COLS - 4, "line", "─")
            if self.cmd:
                s.put(2, Y_STATUS, "› " + self.cmd[:COLS - 6], "bright")
                if hasattr(self.b, "cursor"):
                    self.b.cursor = (4 + min(len(self.cmd), COLS - 9), Y_STATUS)
            else:
                s.put(2, Y_STATUS, P.keyhints(self)[:COLS - 4], "faint")
                if hasattr(self.b, "cursor"):
                    self.b.cursor = None
            return

        s.hline(2, Y_RULE2, COLS - 4, "line", "─")
        lines = list(self.log)
        end = len(lines) - self.scroll
        shown = lines[max(0, end - (LOG_H - 1)):end]
        s.put(2, Y_LOG, "NOTES", "dim", BOLD)
        for i, (text, fg) in enumerate(shown):
            s.put(10, Y_LOG + i, text[:COLS - 12], fg)
        if not shown:
            s.put(10, Y_LOG, "No field notes yet.", "faint")
        if self.scroll:
            s.right(2, Y_LOG, COLS - 4, f"↑{self.scroll}", "faint")

        s.hline(2, Y_RULE3, COLS - 4, "line", "─")
        s.put(2, Y_CMD, "›", "accent", BOLD)
        s.put(4, Y_CMD, self.cmd[-(COLS - 8):], "bright")
        self.b.cursor = (4 + min(len(self.cmd), COLS - 9), Y_CMD)

        s.hline(2, Y_RULE4, COLS - 4, "line", "─")
        s.put(2, Y_STATUS, P.keyhints(self)[:COLS - 4], "faint")

    # -- input ---------------------------------------------------------------
    def handle(self, kind: str, value) -> None:
        if kind == "quit":
            self.running = False
        elif kind == "char":
            self.cmd += value
        elif kind == "click":
            self.on_click(value)
        elif kind == "key":
            self.on_key(value)

    def on_click(self, pos) -> None:
        col, row = pos
        for (y, x0, x1), (what, val) in self.click_map.items():
            if row == y and x0 <= col < x1:
                if what == "index":
                    self.cursor = val
                    self.choose()
                elif what == "place":
                    self.go(val)
                return

    def on_key(self, key: str) -> None:
        typing = bool(self.cmd)
        if key == "enter":
            if typing:
                line, self.cmd = self.cmd.strip(), ""
                self.hist.append(line)
                self.hist_i = len(self.hist)
                self.say("> " + line, "accent")
                P.command(self, line)
            else:
                self.choose()
            return
        if key == "backspace":
            if typing:
                self.cmd = self.cmd[:-1]
            elif self.place == "battle" and not self.state.get("battle", {}).get("finished"):
                # One step back inside the fight: cancel a confirmation, then
                # leave an open panel. Never unwind out of a live battle — that
                # left the screen looking locked.
                if getattr(self, "battle_confirm", None):
                    self.battle_confirm = None
                elif getattr(self, "battle_focus", "menu") == "panel":
                    P.leave_battle_panel(self)
                self.battle_mode = "main"
                return
            elif self.aim is not None:
                self.aim = None
                self.cursor = 0
            else:
                self.back()
            return
        if key == "esc":
            if typing:
                self.cmd = ""
            elif self.place == "battle" and not self.state.get("battle", {}).get("finished"):
                # One step back inside the fight: cancel a confirmation, then
                # leave an open panel. Never unwind out of a live battle — that
                # left the screen looking locked.
                if getattr(self, "battle_confirm", None):
                    self.battle_confirm = None
                elif getattr(self, "battle_focus", "menu") == "panel":
                    P.leave_battle_panel(self)
                self.battle_mode = "main"
                return
            elif self.aim is not None:
                self.aim = None
                self.cursor = 0
            else:
                self.back()
            return
        if key in ("up", "down"):
            if typing and self.hist:
                self.hist_i = max(0, min(len(self.hist), self.hist_i + (-1 if key == "up" else 1)))
                self.cmd = self.hist[self.hist_i] if self.hist_i < len(self.hist) else ""
            else:
                self.move_cursor(0, -1 if key == "up" else 1)
            return
        if key == "left":
            self.move_cursor(-1, 0); return
        if key == "right":
            self.move_cursor(1, 0); return
        if key == "tab":
            self.cursor = (self.cursor + 1) % max(1, len(self.items)); return
        if key == "pgup":
            self.scroll = min(max(0, len(self.log) - 1), self.scroll + LOG_H); return
        if key == "pgdn":
            self.scroll = max(0, self.scroll - LOG_H); return

    def run_command(self, line: str) -> None:
        P.command(self, line)

    def hotkey(self, ch: str) -> bool:
        return P.hotkey(self, ch)

    # -- loop ----------------------------------------------------------------
    def loop(self) -> None:
        while self.running:
            self.drain()
            for kind, value in self.b.poll():
                if kind == "char" and not self.cmd and self.hotkey(value):
                    continue
                self.handle(kind, value)
            self.draw()
            self.b.render(self.screen)
            time.sleep(0.004)
