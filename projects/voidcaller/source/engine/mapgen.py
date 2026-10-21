"""The descent: a seeded, branching map of one trip into the Void.

Rows go down. Each row holds one to three nodes; you can only step to a node
the current one connects to, so the path you take is a real choice and the
shrine you walked past is a real regret. The seed is stored, so a run can be
saved half-finished and rebuilt exactly.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

KINDS = ["fight", "fight", "fight", "elite", "gather", "cache", "shrine"]

DEPTHS = {
    "shallow": {"rows": 5, "loot": 1.0, "label": "Shallow"},
    "deep":    {"rows": 8, "loot": 1.35, "label": "Deep"},
    "abyssal": {"rows": 11, "loot": 1.8, "label": "Abyssal"},
}

ICONS = {"gate": "◇", "fight": "⚔", "elite": "✦", "gather": "◈",
         "cache": "▣", "shrine": "☩", "boss": "☠"}

# name parts, picked by whatever the region is called
PLACE_WORDS = {
    "fen": ["Reedbank", "Black Water", "The Sink", "Drowned Steps", "Leech Shallows"],
    "marsh": ["Reedbank", "The Sink", "Mudmouth", "Rotten Causeway"],
    "cavern": ["Spore Shelf", "The Choke", "Dripstone", "Fungal Gallery", "Deadfall"],
    "mine": ["Cut Seven", "The Winze", "Collapsed Drift", "Ore Face", "The Ladder"],
    "forest": ["Stone Grove", "Petrified Ring", "The Splinters", "Old Root"],
    "cathedral": ["The Nave", "Broken Chancel", "Bell Room", "Ossuary Stair"],
    "library": ["Stack Nine", "The Reading Dark", "Fallen Shelves", "Index Hall"],
    "desert": ["Salt Pan", "The Glare", "Wind Cut", "Bone Field"],
    "steppe": ["Ice Field", "The White", "Frost Cut", "Windbreak"],
    "coast": ["Wreck Line", "The Spit", "Tide Cave", "Salt Stair"],
    "foundry": ["Gear Floor", "The Press", "Boiler Row", "Assembly Dark"],
    "caldera": ["Ash Slope", "The Vent", "Glass Field", "Magma Shelf"],
}
GENERIC = ["The Narrows", "Long Dark", "The Turn", "Low Ground", "The Hollow",
           "Deep Cut", "The Verge", "Still Room", "The Descent"]

FLAVOUR = {
    "gather": ["A seam of something glitters where the dark thins.",
               "Bones, picked clean, and something under them worth taking.",
               "A dead hunter's pack, still buckled. He will not need it.",
               "Fungus grows in a ring here, and the ring is worth money."],
    "cache": ["A strongbox, half swallowed by the floor.",
              "Coins in a hollow skull. Someone's idea of a joke.",
              "A caravan that never came back. Its cargo did not walk away."],
    "shrine": ["A shrine of stacked stones. The air here is kinder.",
               "Still water, and it does not reflect you. You drink anyway.",
               "Someone carved a prayer here and meant it."],
}


@dataclass
class Node:
    id: str
    row: int
    col: int
    kind: str
    name: str
    next: list = field(default_factory=list)
    state: str = "unseen"        # unseen | open | current | cleared | skipped

    def to_dict(self) -> dict:
        return {"id": self.id, "row": self.row, "col": self.col, "kind": self.kind,
                "name": self.name, "next": list(self.next), "state": self.state,
                "icon": ICONS.get(self.kind, "·")}


class DescentMap:
    def __init__(self, region: str, depth: str = "deep", seed: int | None = None):
        self.region = region
        self.depth = depth if depth in DEPTHS else "deep"
        self.seed = seed if seed is not None else random.randrange(1, 10 ** 9)
        self.nodes: dict[str, Node] = {}
        self.rows: list[list[str]] = []
        self.current: str = ""
        self._build()

    # -- generation ----------------------------------------------------------
    def _names(self, rng: random.Random, n: int) -> list[str]:
        pool = []
        for key, words in PLACE_WORDS.items():
            if key in self.region.lower():
                pool += words
        pool = pool or list(GENERIC)
        pool = pool + GENERIC
        rng.shuffle(pool)
        out, i = [], 0
        while len(out) < n:
            out.append(pool[i % len(pool)] if i < len(pool) else rng.choice(GENERIC))
            i += 1
        return out

    def _build(self) -> None:
        rng = random.Random(self.seed)
        rows_n = DEPTHS[self.depth]["rows"]
        widths = [1]
        for r in range(1, rows_n - 1):
            if r == 1:
                widths.append(1)
            else:
                widths.append(rng.choice([2, 2, 2, 3] if rows_n > 6 else [2, 2, 1]))
        widths.append(1)

        names = self._names(rng, sum(widths) + 4)
        name_i = 0
        for r, w in enumerate(widths):
            row_ids = []
            for c in range(w):
                nid = f"n{r}_{c}"
                if r == 0:
                    kind, name = "gate", "The Gate"
                elif r == len(widths) - 1:
                    kind, name = "boss", "?????"
                else:
                    weights = list(KINDS)
                    if r >= rows_n * 0.6:
                        weights += ["elite", "fight"]
                    kind = rng.choice(weights)
                    name = names[name_i]
                    name_i += 1
                row_ids.append(nid)
                self.nodes[nid] = Node(nid, r, c, kind, name)
            self.rows.append(row_ids)

        # edges: every node reaches at least one below, every node below is reachable
        for r in range(len(self.rows) - 1):
            here, below = self.rows[r], self.rows[r + 1]
            for i, nid in enumerate(here):
                if len(below) == 1:
                    picks = [below[0]]
                else:
                    lo = min(int(i * len(below) / max(1, len(here))), len(below) - 1)
                    picks = {below[lo]}
                    if rng.random() < 0.55 and len(below) > 1:
                        picks.add(below[min(lo + 1, len(below) - 1)])
                    picks = list(picks)
                self.nodes[nid].next = picks
            reached = {x for nid in here for x in self.nodes[nid].next}
            for nid in below:
                if nid not in reached:
                    self.nodes[rng.choice(here)].next.append(nid)

        self.current = self.rows[0][0]
        self.nodes[self.current].state = "current"
        self._open_next()

    # -- movement ------------------------------------------------------------
    def _open_next(self) -> None:
        for nid in self.nodes[self.current].next:
            if self.nodes[nid].state == "unseen":
                self.nodes[nid].state = "open"

    @property
    def available(self) -> list[str]:
        return [nid for nid in self.nodes[self.current].next
                if self.nodes[nid].state in ("open", "unseen")]

    @property
    def row(self) -> int:
        return self.nodes[self.current].row

    @property
    def depth_rows(self) -> int:
        return len(self.rows)

    def can_enter(self, nid: str) -> bool:
        return nid in self.available

    def enter(self, nid: str) -> Node:
        prev = self.nodes[self.current]
        prev.state = "cleared"
        for sib in self.rows[self.nodes[nid].row]:
            if sib != nid and self.nodes[sib].state in ("open", "unseen"):
                self.nodes[sib].state = "skipped"
        self.current = nid
        self.nodes[nid].state = "current"
        self._open_next()
        return self.nodes[nid]

    def finish_current(self) -> None:
        self.nodes[self.current].state = "cleared"

    @property
    def at_boss(self) -> bool:
        return self.nodes[self.current].kind == "boss"

    # -- save ----------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"region": self.region, "depth": self.depth, "seed": self.seed,
                "current": self.current,
                "states": {nid: n.state for nid, n in self.nodes.items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "DescentMap":
        m = cls(d["region"], d.get("depth", "deep"), d.get("seed"))
        for nid, state in (d.get("states") or {}).items():
            if nid in m.nodes:
                m.nodes[nid].state = state
        m.current = d.get("current", m.rows[0][0])
        return m

    def view(self) -> dict:
        return {
            "region": self.region, "depth": self.depth,
            "depth_label": DEPTHS[self.depth]["label"],
            "rows": [[self.nodes[n].to_dict() for n in row] for row in self.rows],
            "current": self.current, "available": self.available,
            "row": self.row, "rows_total": self.depth_rows,
        }
