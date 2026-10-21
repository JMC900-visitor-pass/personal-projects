"""The quest board. Contracts are generated from whatever is in the bestiary,
so every monster you add brings its own drops, hunts and bounties with it."""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field

from . import luck, ui

GIVERS = ["Sable the Cartwright", "Old Mirren", "the Salt Priest", "Wick the Fence",
          "Deaconess Roul", "a masked buyer", "the Foundry Steward", "Hob the Ferryman",
          "the Widow Ansel", "a nervous scribe"]

FETCH_FLAVOUR = [
    "The alchemists pay stupid money for these. Don't ask what for.",
    "My daughter's wedding needs them. Long story. Bring {qty}.",
    "I burn through {item} faster than I can buy it. {qty} should hold me a week.",
    "It's for a ward. A real one, not the paper kind. {qty} pieces, no less.",
    "The guild says {qty}. The guild is never wrong about quantities, only about people.",
]
SLAY_FLAVOUR = [
    "They took the east road. They will not take the west one.",
    "Every night, closer to the fence line. Thin them out.",
    "Kill {qty}. Bring nothing back. I don't want to see it.",
    "A bounty, plain and honest: {qty} of them, and coin in your hand.",
]
HUNT_FLAVOUR = [
    "One creature. It has a name, and the name is a problem.",
    "It ate the last hunter's dogs. Then the last hunter.",
    "Bring me proof. A tooth will do. A whole head is showing off.",
]


@dataclass
class Quest:
    kind: str                     # fetch | slay | hunt
    title: str
    giver: str
    text: str
    target: str                   # item name, "family:X", or monster name
    qty: int = 1
    progress: int = 0             # for slay/hunt only
    gold: int = 0
    shards: int = 0
    xp: int = 0
    item: str = ""                # bonus item reward
    level: int = 1
    area_id: str = ""             # exact Forge-authored operation location
    accepted: bool = False
    authored: bool = False
    uid: str = field(default_factory=lambda: "q_" + uuid.uuid4().hex[:12])

    # -- state ---------------------------------------------------------------
    def have(self, game) -> int:
        if self.kind == "fetch":
            return game.count(self.target)
        return min(self.qty, game.kills.get(self.target, 0) - self.progress_base(game))

    def progress_base(self, game) -> int:
        return self._base

    _base: int = 0

    def start(self, game) -> None:
        self.accepted = True
        if self.kind in ("slay", "hunt"):
            self._base = game.kills.get(self.target, 0)

    def done(self, game) -> bool:
        return self.have(game) >= self.qty

    def turn_in(self, game) -> list[str]:
        lines = []
        if self.kind == "fetch":
            game.consume(self.target, self.qty)
            lines.append(f"handed over {self.qty}x {self.target}")
        game.gold += self.gold
        game.shards += self.shards
        lines.append(f"+{self.gold}g  +{self.shards} shards")
        if self.item:
            game.add_item(self.item)
            lines.append(f"+1 {self.item}")
        if self.xp:
            for m in game.party:
                for lv in m.gain_xp(self.xp):
                    lines.append(f"{m.name} reached level {lv}!")
            lines.append(f"+{self.xp} xp to the pack")
        game.completed_quests += 1
        return lines

    def label(self, game=None) -> str:
        prog = ""
        if game is not None:
            prog = ui.c(f"  [{min(self.have(game), self.qty)}/{self.qty}]",
                        "bright_green" if self.done(game) else "grey")
        name = self.target.replace("family:", "")
        what = {"fetch": f"bring {self.qty}x {name}",
                "slay": f"slay {self.qty} {name}",
                "hunt": f"hunt {name}"}[self.kind]
        return (f"{self.title:<30} {ui.c(what, 'white'):<34} "
                f"{ui.c(str(self.gold) + 'g', 'yellow')} "
                f"{ui.c(str(self.shards) + 'sh', 'magenta')}{prog}")

    # -- save ----------------------------------------------------------------
    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Quest":
        q = cls(kind=d["kind"], title=d["title"], giver=d["giver"], text=d["text"],
                target=d["target"], qty=int(d.get("qty", 1)),
                uid=str(d.get("uid") or ("q_" + uuid.uuid4().hex[:12])))
        for k in ("progress", "gold", "shards", "xp", "item", "level", "area_id", "accepted", "_base"):
            if k in d:
                setattr(q, k, d[k])
        return q


# --- contracts written by hand ---------------------------------------------
def load_authored() -> list["Quest"]:
    """data/quests.json plus anything in data/quests/*.json.

    These are mixed into the generated board, so a file of hand-written or
    generated contracts becomes part of the game with no code change."""
    import glob
    import json
    import os
    from .data import GAME_DIR

    out: list[Quest] = []
    paths = [os.path.join(GAME_DIR, "data", "quests.json")]
    paths += sorted(glob.glob(os.path.join(GAME_DIR, "data", "quests", "*.json")))
    for path in paths:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                blob = json.load(f)
        except Exception:
            continue
        rows = blob.get("quests", []) if isinstance(blob, dict) else blob
        for raw in rows:
            if not isinstance(raw, dict) or "kind" not in raw:
                continue
            try:
                q = Quest(kind=raw["kind"], title=raw.get("title", "A Job"),
                          giver=raw.get("giver", "a stranger"), text=raw.get("text", ""),
                          target=raw.get("target", ""), qty=int(raw.get("qty", 1)))
                for k in ("gold", "shards", "xp", "item", "level", "area_id"):
                    if k in raw:
                        setattr(q, k, raw[k])
                q.authored = True
                out.append(q)
            except Exception:
                continue
    return out


# ---------------------------------------------------------------------------
def _item_sources(bestiary):
    """item name -> (list of monsters that drop it, best rate)."""
    out = {}
    for t in bestiary.all:
        for d in list(t.drops) + list(t.steal):
            entry = out.setdefault(d.item, {"monsters": [], "rate": 0.0, "kind": d.kind})
            entry["monsters"].append(t)
            entry["rate"] = max(entry["rate"], d.rate)
    return out


def _title_for(kind: str, name: str) -> str:
    if kind == "fetch":
        return random.choice(["Supply Run", "A Small Errand", "Standing Order",
                              "The Alchemist's List", "Short of Stock"])
    if kind == "slay":
        return random.choice(["Culling", "Fence Line", "Bounty Notice", "Too Many Teeth"])
    return random.choice(["Named Beast", "A Reckoning", "The Thing in the Dark"])


def generate_board(game, count: int = 5) -> list[Quest]:
    lvl = max(1, sum(m.level for m in game.party) // max(1, len(game.party)))
    board: list[Quest] = []
    # Forge-first projects own their mission board.  We no longer invent
    # contracts from whatever happens to be in the bestiary: if the designer
    # has not made a quest yet, the board honestly says it is empty.
    authored = [q for q in load_authored() if abs(getattr(q, "level", lvl) - lvl) <= 12]
    random.shuffle(authored)
    taken = {(q.kind, q.target) for q in game.quests}
    for q in authored[:count]:
        if (q.kind, q.target) not in taken:
            board.append(q)
    return board


# --- the board screen -------------------------------------------------------
def board_screen(game) -> None:
    while True:
        ui.header("QUEST BOARD", f"day {game.day} - {game.hunter} - {game.gold}g")
        if not game.board:
            game.board = generate_board(game)

        active = [q for q in game.quests]
        if active:
            ui.say(ui.c(" ACCEPTED", "bright_green"))
            for q in active:
                mark = ui.c(" READY", "bright_yellow", "bold") if q.done(game) else ""
                ui.say("   " + q.label(game) + mark)
        ui.say(ui.c(" OFFERED", "bright_cyan"))
        for q in game.board:
            ui.say("   " + q.label())

        opts = ["Read / accept a contract"]
        ready = [q for q in active if q.done(game)]
        if ready:
            opts.append(ui.c(f"Turn in ({len(ready)} ready)", "bright_yellow"))
        opts.append("Abandon a contract" if active else "-")
        pick = ui.menu("", opts, back="leave the board")
        if pick < 0:
            return
        if pick == 0:
            _accept_screen(game)
        elif pick == 1 and ready:
            _turn_in(game, ready)
        elif opts[pick].startswith("Abandon") and active:
            i = ui.menu("  Drop which contract?", [q.label(game) for q in active])
            if i >= 0:
                game.quests.pop(i)
                ui.say(ui.c("  Contract torn down.", "grey"))


def _accept_screen(game) -> None:
    if len(game.quests) >= 5:
        ui.say(ui.c("  You are carrying five contracts already. Finish one.", "red"))
        ui.pause()
        return
    i = ui.menu("  Which notice?", [q.label() for q in game.board])
    if i < 0:
        return
    q = game.board[i]
    ui.box([ui.c(q.title, "bold"),
            ui.c(f"posted by {q.giver}", "grey"),
            "",
            q.text,
            "",
            ui.c(f"reward: {q.gold}g, {q.shards} shards, {q.xp} xp"
                 + (f", 1x {q.item}" if q.item else ""), "yellow")],
           title=q.kind.upper())
    if ui.confirm("  Take it?"):
        q.start(game)
        game.quests.append(q)
        game.board.pop(i)
        ui.say(ui.c("  Contract signed.", "bright_green"))
    ui.pause()


def _turn_in(game, ready: list[Quest]) -> None:
    i = ui.menu("  Turn in which?", [q.label(game) for q in ready])
    if i < 0:
        return
    q = ready[i]
    lines = q.turn_in(game)
    game.quests = [x for x in game.quests if x is not q]
    ui.box([ui.c(f"{q.giver} counts it out.", "grey")] + lines, title="PAID")
    ui.pause()
