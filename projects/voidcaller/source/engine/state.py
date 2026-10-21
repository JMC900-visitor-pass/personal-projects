"""Everything the save file remembers."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from copy import deepcopy
from dataclasses import dataclass, field

from . import balance as B
from . import ui
from .clock import MINUTES_PER_DAY, WorldClock
from .data import Bestiary, build_item_catalog, load_bestiary
from .entities import Combatant, spawn
from . import farm as FARM
from .migration import (CURRENT_SAVE_VERSION, migrate_save, passthrough_fields)

SAVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "saves")


def atomic_write_json(path: str, data: dict) -> None:
    """Write one save safely, keeping the immediately previous copy as ``.bak``.

    The new JSON is completely written and synced in the destination directory
    before it replaces the live save.  If serialisation, backup, or replacement
    fails, the existing save is left untouched.  Loading never calls this
    function, so opening a legacy save cannot rewrite it behind the player's
    back.
    """
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    base = os.path.basename(path)
    fd, temporary = tempfile.mkstemp(prefix=f".{base}.", suffix=".tmp", dir=directory)
    backup_temporary: str | None = None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=1)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        if os.path.exists(path):
            backup_fd, backup_temporary = tempfile.mkstemp(
                prefix=f".{base}.", suffix=".bak.tmp", dir=directory)
            os.close(backup_fd)
            # Copy to a temporary neighbour first, so an existing .bak is
            # never exposed half-written if the copy is interrupted.
            shutil.copy2(path, backup_temporary)
            os.replace(backup_temporary, path + ".bak")
            backup_temporary = None

        os.replace(temporary, path)
        temporary = ""
    finally:
        for candidate in (temporary, backup_temporary):
            if candidate:
                try:
                    os.unlink(candidate)
                except FileNotFoundError:
                    pass


class Game:
    def __init__(self, bestiary: Bestiary | None = None):
        # `or` would swallow a deliberately empty bestiary, because an
        # empty one is falsy -- and then quietly load a different world
        self.bestiary = bestiary if bestiary is not None else load_bestiary()
        self.items = build_item_catalog(self.bestiary)
        self.hunter = "Hunter"
        self.gold = 250
        self.shards = 12
        self.clock = WorldClock()
        self.roster: list[Combatant] = []
        self.party_uids: list[str] = []
        self.inventory: dict[str, int] = {}
        self.craft_books: set[str] = set()
        self.quests: list = []          # active Quest objects
        self.board: list = []           # today's offers
        self.completed_quests = 0
        self.kills: dict[str, int] = {}
        self.seen: set[str] = set()
        self.codex: dict[str, dict[str, int]] = {}
        self.story: int = 0             # chapters cleared
        self.regions_cleared: dict[str, int] = {}
        self.deepest_run = 0
        self.tracked_quest = ""
        self.farm = FARM.fresh(self.clock.total_minutes)
        self.slot = "save1"
        # Unknown top-level fields survive a later explicit save.  This is an
        # envelope safeguard only; individual creature/content migrations will
        # own their nested fields when their schemas change.
        self._save_passthrough: dict = {}
        self.migration_report: dict | None = None

    # -- world time ---------------------------------------------------------
    # ``day`` remains a property so existing UI and game systems keep working
    # while new time-aware systems depend on the single WorldClock instead.
    @property
    def day(self) -> int:
        return self.clock.day

    @day.setter
    def day(self, value: int) -> None:
        self.clock.day = max(1, int(value))

    def advance_time(self, minutes: int) -> None:
        self.clock.advance(minutes)

    def sync_clock(self, now: float | None = None) -> int:
        return self.clock.sync(now)

    # -- party ---------------------------------------------------------------
    @property
    def party(self) -> list[Combatant]:
        by_uid = {m.uid: m for m in self.roster}
        out = [by_uid[u] for u in self.party_uids if u in by_uid]
        return out[:B.PARTY_SLOTS]

    def set_party(self, members: list[Combatant]) -> None:
        self.party_uids = [m.uid for m in members[:B.PARTY_SLOTS]]

    def add_monster(self, template, level: int | None = None) -> Combatant | None:
        if len(self.roster) >= B.ROSTER_CAP:
            return None
        m = spawn(template, level)
        self.roster.append(m)
        self.discover(template, "captured")
        if len(self.party_uids) < B.PARTY_SLOTS:
            self.party_uids.append(m.uid)
        return m

    def release(self, m: Combatant) -> int:
        """Send a monster back to the Void for shards."""
        self.roster = [x for x in self.roster if x.uid != m.uid]
        self.party_uids = [u for u in self.party_uids if u != m.uid]
        pay = 8 + m.level * 2 + {"Common": 0, "Uncommon": 5, "Rare": 12,
                                 "Epic": 25}.get(m.rarity, 0)
        self.shards += pay
        return pay

    def rest(self) -> None:
        for m in self.roster:
            m.full_heal()

    # -- stuff ---------------------------------------------------------------
    def add_item(self, name: str, qty: int = 1) -> None:
        if not name:
            return
        self.inventory[name] = self.inventory.get(name, 0) + qty
        self.items.setdefault(name, {"name": name, "kind": "material", "value": 15,
                                     "source": "?", "level": 1})

    def consume(self, name: str, qty: int = 1) -> bool:
        have = self.inventory.get(name, 0)
        if have < qty:
            return False
        self.inventory[name] = have - qty
        if self.inventory[name] <= 0:
            self.inventory.pop(name)
        return True

    def count(self, name: str) -> int:
        return self.inventory.get(name, 0)

    def value_of(self, name: str) -> int:
        return int(self.items.get(name, {}).get("value", 10))

    def record_kill(self, template) -> None:
        self.kills[template.name] = self.kills.get(template.name, 0) + 1
        if template.family:
            key = "family:" + template.family
            self.kills[key] = self.kills.get(key, 0) + 1
        self.discover(template, "defeat")

    def discover(self, template, observation: str = "encounter") -> dict[str, int]:
        """Record a progressive Codex observation without exposing its secrets.

        The legacy ``seen`` set remains the fast answer to 'has the player met
        this species?', while this record gives UI and future systems a real
        discovery history to reason about.
        """
        self.seen.add(template.id)
        row = self.codex.setdefault(template.id,
                                    {"encounters": 0, "defeats": 0, "captured": 0})
        key = {"encounter": "encounters", "defeat": "defeats",
               "captured": "captured"}.get(observation, "encounters")
        row[key] = int(row.get(key, 0)) + 1
        if key in ("defeats", "captured"):
            row["encounters"] = max(1, int(row.get("encounters", 0)))
        return row

    def codex_record(self, template) -> dict[str, int]:
        return {"encounters": 0, "defeats": 0, "captured": 0,
                **self.codex.get(template.id, {})}

    # -- save / load ---------------------------------------------------------
    def to_dict(self) -> dict:
        from .quests import Quest
        self.sync_clock()
        # Start with unrecognised data from a loaded save.  Known live state
        # below always wins, but a future system's unrelated top-level data is
        # not discarded merely because this client saved the game.
        payload = deepcopy(self._save_passthrough)
        payload.update({
            "save_version": CURRENT_SAVE_VERSION,
            # Retain the former key during the compatibility window.  Some
            # existing callers use it to tell saves apart from look settings.
            "version": CURRENT_SAVE_VERSION,
            "saved_at": time.time(),
            "hunter": self.hunter, "gold": self.gold, "shards": self.shards,
            "day": self.day, "world_clock": self.clock.to_dict(),
            "story": self.story, "completed_quests": self.completed_quests,
            "roster": [m.to_dict() for m in self.roster],
            # V2 party membership is stable creature IDs, not mutable roster
            # indexes. ``load`` still accepts index arrays from old saves.
            "party": list(self.party_uids),
            "inventory": self.inventory,
            "quests": [q.to_dict() for q in self.quests],
            "board": [q.to_dict() for q in self.board],
            "kills": self.kills, "seen": sorted(self.seen), "codex": self.codex,
            "regions_cleared": self.regions_cleared, "deepest_run": self.deepest_run,
            "tracked_quest": self.tracked_quest, "farm": self.farm,
            "craft_books": sorted(self.craft_books),
        })
        return payload

    def save(self, slot: str | None = None) -> str:
        slot = slot or self.slot
        path = os.path.join(SAVE_DIR, f"{slot}.json")
        atomic_write_json(path, self.to_dict())
        self.slot = slot
        return path

    @classmethod
    def load(cls, slot: str = "save1", bestiary: Bestiary | None = None) -> "Game | None":
        path = os.path.join(SAVE_DIR, f"{slot}.json")
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        # This is intentionally in-memory only.  A player must explicitly
        # save before a legacy file is upgraded on disk, at which point the
        # former contents are kept as ``.bak`` by atomic_write_json.
        d, _report = migrate_save(raw)
        from .quests import Quest
        g = cls(bestiary)
        g.slot = slot
        g.migration_report = _report.as_dict()
        g._save_passthrough = passthrough_fields(d)
        g.hunter = d.get("hunter", "Hunter")
        g.gold = int(d.get("gold", 0))
        g.shards = int(d.get("shards", 0))
        g.clock = WorldClock.from_dict(d.get("world_clock"), int(d.get("day", 1)))
        g.sync_clock()
        g.story = int(d.get("story", 0))
        g.completed_quests = int(d.get("completed_quests", 0))
        g.inventory = {k: int(v) for k, v in (d.get("inventory") or {}).items()}
        g.craft_books = {str(x) for x in (d.get("craft_books") or [])}
        g.kills = {k: int(v) for k, v in (d.get("kills") or {}).items()}
        g.seen = set(d.get("seen") or [])
        raw_codex = d.get("codex") or {}
        g.codex = {str(k): {"encounters": int(v.get("encounters", 0)),
                             "defeats": int(v.get("defeats", 0)),
                             "captured": int(v.get("captured", 0))}
                   for k, v in raw_codex.items() if isinstance(v, dict)}
        # Old saves only knew 'seen'. Preserve that knowledge as a first
        # encounter instead of making an existing ledger blank after upgrade.
        for tid in g.seen:
            g.codex.setdefault(tid, {"encounters": 1, "defeats": 0, "captured": 0})
        g.regions_cleared = d.get("regions_cleared") or {}
        g.deepest_run = int(d.get("deepest_run", 0))
        g.tracked_quest = str(d.get("tracked_quest", ""))
        g.farm = FARM.normalize(d.get("farm"), g.clock.total_minutes)
        for md in d.get("roster", []):
            m = Combatant.from_dict(md, g.bestiary)
            if m:
                g.roster.append(m)
        saved_party = d.get("party", [])
        if saved_party and all(isinstance(value, (int, float)) and not isinstance(value, bool)
                               for value in saved_party):
            g.party_uids = [g.roster[int(index)].uid for index in saved_party
                            if 0 <= int(index) < len(g.roster)]
        else:
            known = {monster.uid for monster in g.roster}
            g.party_uids = [str(uid) for uid in saved_party if str(uid) in known]
        if not g.party_uids:
            g.party_uids = [m.uid for m in g.roster[:B.PARTY_SLOTS]]
        g.quests = [Quest.from_dict(q) for q in d.get("quests", [])]
        g.board = [Quest.from_dict(q) for q in d.get("board", [])]
        if g.tracked_quest and not any(q.uid == g.tracked_quest for q in g.quests):
            g.tracked_quest = g.quests[0].uid if g.quests else ""
        return g


def list_saves() -> list[tuple[str, str]]:
    if not os.path.isdir(SAVE_DIR):
        return []
    out = []
    for fn in sorted(os.listdir(SAVE_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(SAVE_DIR, fn), encoding="utf-8") as f:
                d = json.load(f)
            # This directory also stores display/layout/look preferences.  A
            # Real hunts carry either the old version key or the explicit new
            # save_version key.  Look/layout preferences live in this same
            # directory, so they must stay out of the Load Game list.
            if not isinstance(d, dict) or not ({"version", "save_version"} & set(d)):
                continue
            label = (f"{d.get('hunter','?')}  day {d.get('day',1)}  "
                     f"{len(d.get('roster',[]))} monsters  {d.get('gold',0)}g")
        except Exception:
            label = "(unreadable)"
        out.append((fn[:-5], label))
    return out
