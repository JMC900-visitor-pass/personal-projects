"""One player's session, driven by actions and returning state. No printing.

The browser talks to this and nothing else. Every action returns the full new
state plus the events that happened, so the front end never has to guess.
"""
from __future__ import annotations

import random
from copy import deepcopy

from . import balance as B
from . import elements as EL
from . import crafting as CRAFT
from . import farm as FARM
from . import areas as AREAS
from . import mapgen, portraits, quests, rules, v2_art
from .battle import Battle
from .entities import xp_for_level
from .model import CORE_STATS, DISPLAY_STATS, RARITY_MARKS
from .entities import spawn
from .mapgen import DescentMap
from .state import Game, list_saves


class Run:
    """One trip into the Void."""

    def __init__(self, region: str, depth: str, level: int, seed: int | None = None,
                 quest_uid: str = ""):
        self.map = DescentMap(region, depth, seed)
        self.level = level
        self.bag: list[str] = []
        self.gold = 0
        self.shards = 0
        self.xp = 0
        self.mult = mapgen.DEPTHS[self.map.depth]["loot"]
        self.over = False
        self.quest_uid = str(quest_uid or "")

    def to_dict(self) -> dict:
        return {"map": self.map.to_dict(), "level": self.level, "bag": self.bag,
                "gold": self.gold, "shards": self.shards, "xp": self.xp,
                "quest_uid": self.quest_uid}

    @classmethod
    def from_dict(cls, d: dict) -> "Run":
        r = cls(d["map"]["region"], d["map"].get("depth", "deep"), d.get("level", 1),
                d["map"].get("seed"), d.get("quest_uid", ""))
        r.map = DescentMap.from_dict(d["map"])
        r.bag = list(d.get("bag", []))
        r.gold, r.shards, r.xp = d.get("gold", 0), d.get("shards", 0), d.get("xp", 0)
        return r

    def view(self) -> dict:
        return {"map": self.map.view(), "bag": self.bag, "gold": self.gold,
                "shards": self.shards, "xp": self.xp,
                "depth": self.map.row, "rows": self.map.depth_rows,
                "quest_uid": self.quest_uid}


class Session:
    def __init__(self, game: Game | None = None):
        self.game = game or Game()
        self.screen = "title" if not self.game.roster else "home"
        self.run: Run | None = None
        self.battle: Battle | None = None
        self.spoils: dict | None = None
        self.events: list[dict] = []
        self.message = ""
        # A new hunt pauses here until the player chooses one of the three
        # Forge-authored candidates.  It is deliberately session-only: saves
        # always contain the actual selected companion.
        self.starter_choices = []

    # -- helpers -------------------------------------------------------------
    @property
    def party_level(self) -> int:
        p = self.game.party
        return max(1, sum(m.level for m in p) // max(1, len(p)))

    def unit(self, m, full: bool = False) -> dict:
        sprite_asset = v2_art.write_monster(m.template.id, m.template.portrait_seed,
                                            m.template.primary,
                                            getattr(m.template, "sprite_archetype", "Core"))
        d = {
            "uid": m.uid, "name": m.name, "species": m.template.name,
            "title": m.template.title, "level": m.level, "rarity": m.rarity,
            "rarity_mark": m.rarity_mark, "rarity_color": m.rarity_color,
            "role": m.template.role, "type": m.template.primary,
            "secondary": m.template.secondary, "family": m.template.family,
            "hp": m.cur_hp, "max_hp": m.max_hp,
            "power": m.power, "xp": m.xp, "xp_next": m.xp_to_next,
            "xp_span": m.xp_span, "xp_done": m.xp_done,
            "in_party": m.uid in self.game.party_uids,
            "portrait": portraits.for_template(m.template),
            "portrait_sig": portraits.signature(m.template),
            "sprite_asset": sprite_asset,
            "equipment": {slot: dict(spec) for slot, spec in m.equipment.items()},
            "statuses": [{"key": k, "rounds": v.rounds} for k, v in m.statuses.items()],
        }
        if full:
            d["base_stats"] = dict(m.template.base_stats)
            d["stats"] = {k: int(m.stat(k)) for k in DISPLAY_STATS}
            d["temporary"] = {"accuracy": round(m.modifier("accuracy") * 100),
                              "evasion": round(m.modifier("evasion") * 100)}
            d["types"] = dict(m.template.types)
            d["elements"] = EL.profile(m)  # compatibility key for existing Codex clients
            d["skills"] = [{"id": s.id, "name": s.name, "category": s.category,
                            "type": s.type, "power": s.power, "accuracy": s.accuracy,
                            "pp": s.pp, "pp_left": m.pp_left(s), "target": s.target,
                            "priority": s.priority, "crit": s.crit, "tags": list(s.tags),
                            "effects": list(s.effects), "description": s.description,
                            "rating": s.rating} for s in m.skills]
            d["skill_tree"] = m.skill_tree_view()
            d["skill_points"] = m.skill_points
            d["tendency"] = dict(m.tendency)
            d["lore"] = m.template.lore
            d["appearance"] = m.template.appearance
            d["habitat"] = list(m.template.habitat)
            d["evolution"] = dict(m.template.evolution)
        return d

    def regions(self) -> list[dict]:
        out = AREAS.regions(self.game.bestiary, self.party_level)
        for row in out:
            row["cleared"] = self.game.regions_cleared.get(row["key"], 0)
        return out

    @staticmethod
    def starter_choice(t) -> dict:
        moves = t.moves_at_level(1)[:4]
        return {
            "id": t.id, "name": t.name, "title": t.title, "level": 1,
            "role": t.role, "type": t.primary, "rarity": t.rarity,
            "rarity_mark": RARITY_MARKS.get(t.rarity, "○"), "rarity_color": "bright",
            "secondary": t.secondary, "family": t.family,
            "stats": {key: int(t.stat_at(key, 1)) for key in CORE_STATS},
            "moves": [{"id": s.id, "name": s.name, "category": s.category, "type": s.type,
                       "power": s.power, "accuracy": s.accuracy, "pp": s.pp,
                       "description": s.description}
                      for s in moves],
        }

    # -- state ---------------------------------------------------------------
    def state(self) -> dict:
        g = self.game
        g.sync_clock()
        FARM.tick(g)
        if not g.board and g.roster:
            g.board = quests.generate_board(g)
        st = {
            "screen": self.screen,
            "message": self.message,
            "hunter": g.hunter, "gold": g.gold, "shards": g.shards, "day": g.day,
            "world_time": g.clock.view(),
            "story": g.story, "seen": len(g.seen), "species": len(g.bestiary),
            "party": [self.unit(m) for m in g.party],
            "roster": [self.unit(m) for m in g.roster],
            "board": [{"i": i, "uid": q.uid, "title": q.title, "kind": q.kind, "giver": q.giver,
                       "target": q.target.replace("family:", ""), "qty": q.qty,
                       "gold": q.gold, "shards": q.shards, "xp": q.xp,
                       "item": getattr(q, "item", ""), "text": q.text,
                       "authored": bool(getattr(q, "authored", False)),
                       "where": self.quest_where(q)} for i, q in enumerate(g.board)],
            "quests": [{"i": i, "uid": q.uid, "tracked": q.uid == g.tracked_quest,
                        "title": q.title, "kind": q.kind, "target": q.target.replace("family:", ""),
                        "have": min(q.have(g), q.qty), "qty": q.qty, "gold": q.gold,
                        "shards": q.shards, "xp": q.xp, "done": q.done(g),
                        "giver": q.giver, "text": q.text,
                        "where": self.quest_where(q)} for i, q in enumerate(g.quests)],
            "regions": self.regions(),
            "depths": [{"key": k, "label": v["label"], "rows": v["rows"], "loot": v["loot"]}
                       for k, v in mapgen.DEPTHS.items()],
            "inventory": [{"name": n, "qty": q, "value": g.value_of(n),
                           "kind": g.items.get(n, {}).get("kind", "material"),
                           "stats": dict(g.items.get(n, {}).get("stats") or {}),
                           "usable": bool(g.items.get(n, {}).get("use")),
                           "desc": g.items.get(n, {}).get("desc", "")}
                          for n, q in sorted(g.inventory.items()) if q > 0],
            "saves": [{"slot": s, "label": l} for s, l in list_saves()],
            "stock": [{"name": n, "buy": int(v.get("buy", 0)), "value": int(v.get("value", 0)),
                       "desc": v.get("desc", ""), "use": dict(v.get("use") or {}),
                       "stats": dict(v.get("stats") or {}),
                       "skill_tree": deepcopy(v.get("skill_tree") or {}),
                       "book": str(v.get("book") or ""), "have": g.count(n),
                       "learned": bool(v.get("book") in g.craft_books) if v.get("book") else False,
                       "kind": v.get("kind", "material")}
                      for n, v in sorted(g.items.items()) if v.get("buy")],
            "summon_cost": B.SUMMON_COST,
            "roster_cap": B.ROSTER_CAP,
            "mission": self.mission_view(),
            "farm": FARM.view(g),
            "recipes": CRAFT.view(g),
            "craft_books": sorted(g.craft_books),
            "unknown_recipes": CRAFT.unknown_count(g),
            "run": self.run.view() if self.run else None,
            "battle": self.scouted(self.battle.snapshot()) if self.battle else None,
            "spoils": self.spoils,
            "events": self.events[-60:],
            "starter_choices": [self.starter_choice(t) for t in self.starter_choices],
        }
        return st

    def scouted(self, snap: dict) -> dict:
        """You only see a creature's weaknesses once you have killed one.
        The ledger is the scouting system: kill it, learn it."""
        for u in snap.get("enemies", []):
            kills = self.game.kills.get(u.get("species", ""), 0)
            u["known"] = kills
            if kills < 1:
                u.pop("weak", None)
        return snap

    def quest_where(self, q) -> str:
        """The location shown on a contract's self-contained operation front."""
        area_id = str(getattr(q, "area_id", "") or "").lower()
        if area_id:
            area = next((row for row in AREAS.load() if row["id"] == area_id), None)
            if area:
                return area["name"]
        area = AREAS.area_for_quest_target(self.game.bestiary, q.target)
        if area:
            return area["name"]
        if q.kind == "fetch":
            for area in AREAS.load():
                if any(any(d.item == q.target for d in list(t.drops) + list(t.steal))
                       for t in AREAS.templates_for(self.game.bestiary, area["id"])):
                    return area["name"]
        return "anywhere"

    def quest_region(self, q) -> str:
        """Return the exact Forge-authored area used by the operation map."""
        regions = self.regions()
        fallback = regions[0]["key"] if regions else ""
        area_id = str(getattr(q, "area_id", "") or "").lower()
        if any(row["id"] == area_id for row in AREAS.load()):
            return area_id
        area = AREAS.area_for_quest_target(self.game.bestiary, q.target)
        if area:
            return area["id"]
        if q.kind == "fetch":
            for candidate in AREAS.load():
                if any(any(d.item == q.target for d in list(t.drops) + list(t.steal))
                       for t in AREAS.templates_for(self.game.bestiary, candidate["id"])):
                    return candidate["id"]
        return fallback

    def mission_view(self) -> dict | None:
        g = self.game
        q = next((x for x in g.quests if x.uid == g.tracked_quest), None)
        if q is None and g.quests:
            q = g.quests[0]
            g.tracked_quest = q.uid
        if q is None:
            return None
        have = q.have(g)
        map_view = None
        if self.run and self.run.quest_uid == q.uid:
            map_view = self.run.map.view()
            if q.kind == "fetch":
                have += self.run.bag.count(q.target)
        total = max(1, (map_view["rows_total"] - 1) if map_view else 1)
        stage = min(total, map_view["row"] if map_view else 0)
        return {"uid": q.uid, "title": q.title, "kind": q.kind,
                "target": q.target.replace("family:", ""), "qty": q.qty,
                "have": min(q.qty, have), "done": have >= q.qty,
                "giver": q.giver, "text": q.text, "where": self.quest_where(q),
                "region": self.quest_region(q), "area_id": getattr(q, "area_id", ""),
                "gold": q.gold, "shards": q.shards,
                "xp": q.xp, "deployed": bool(map_view), "stage": stage,
                "stages": total, "stages_left": max(0, total - stage)}

    # -- actions -------------------------------------------------------------
    def act(self, action: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        self.events = []
        self.message = ""
        if self.spoils and action not in ("claim", "save", "load", "quit"):
            # older front ends never ask: they just take everything and move on
            self._settle([])
        fn = getattr(self, f"do_{action}", None)
        if fn is None:
            self.message = f"unknown action: {action}"
        else:
            fn(payload)
        return self.state()

    def do_goto(self, p):
        target = p.get("screen", "home")
        if target != "battle" or self.battle:
            self.screen = target

    def do_new_game(self, p):
        g = Game(self.game.bestiary)
        g.hunter = (p.get("name") or "Hunter")[:20]
        self.game = g
        self.run = None
        self.battle = None
        self.spoils = None
        self.starter_choices = g.bestiary.starters(3)
        self.screen = "starter"
        if self.starter_choices:
            self.message = "Choose one companion. The other two remain in the wild."
        else:
            self.message = "No starter candidates exist yet. Add creatures in the Forge."

    def do_choose_starter(self, p):
        ident = str(p.get("id") or "")
        starter = next((t for t in self.starter_choices if t.id == ident), None)
        if starter is None:
            self.message = "Choose one of the three companions on the table."
            return
        self.game.add_monster(starter)
        self.game.board = quests.generate_board(self.game)
        self.starter_choices = []
        self.screen = "home"
        self.message = f"{starter.name} answers the bones. Everything else must be earned."

    def do_load(self, p):
        g = Game.load(p.get("slot", "save1"), self.game.bestiary)
        if g:
            self.game = g
            self.starter_choices = []
            self.screen = "home"
            report = g.migration_report or {}
            if report.get("changed"):
                self.message = (f"Welcome back, {g.hunter}. Save migrated in memory from "
                                f"v{report.get('source_version')} to v{report.get('target_version')}; "
                                "save when ready to keep the backup.")
            else:
                self.message = f"Welcome back, {g.hunter}."
        else:
            self.message = "No such save."

    def do_save(self, p):
        self.game.save(p.get("slot") or self.game.slot)
        self.message = "Saved."

    def do_rest(self, p):
        self.game.rest()
        self.message = "You sleep badly and wake whole."

    def do_set_party(self, p):
        uids = [str(u) for u in p.get("uids", [])][:B.PARTY_SLOTS]
        if uids:
            self.game.party_uids = uids

    def do_toggle_party(self, p):
        uid = str(p.get("uid", ""))
        if uid in self.game.party_uids:
            if len(self.game.party_uids) > 1:
                self.game.party_uids.remove(uid)
        elif len(self.game.party_uids) < B.PARTY_SLOTS:
            self.game.party_uids.append(uid)

    # -- contracts -----------------------------------------------------------
    def do_accept_quest(self, p):
        i = int(p.get("index", -1))
        if not (0 <= i < len(self.game.board)):
            return
        if len(self.game.quests) >= 5:
            self.message = "five contracts is all anyone will carry."
            return
        q = self.game.board.pop(i)
        q.start(self.game)
        self.game.quests.append(q)
        self.game.tracked_quest = q.uid
        self.events.append(rules.ev("accepted", title=q.title, giver=q.giver))

    def do_track_quest(self, p):
        i = int(p.get("index", -1))
        if 0 <= i < len(self.game.quests):
            self.game.tracked_quest = self.game.quests[i].uid
            self.message = f"Tracking {self.game.quests[i].title}."

    def do_turn_in(self, p):
        i = int(p.get("index", -1))
        if not (0 <= i < len(self.game.quests)):
            return
        q = self.game.quests[i]
        if not q.done(self.game):
            need = q.qty - min(q.have(self.game), q.qty)
            self.message = f"{need} more for {q.title}."
            return
        lines = q.turn_in(self.game)
        self.game.quests.pop(i)
        if self.game.tracked_quest == q.uid:
            self.game.tracked_quest = self.game.quests[0].uid if self.game.quests else ""
        self.events.append(rules.ev("paid", title=q.title, giver=q.giver,
                                    gold=q.gold, shards=q.shards, lines=lines))

    def do_abandon_quest(self, p):
        i = int(p.get("index", -1))
        if 0 <= i < len(self.game.quests):
            q = self.game.quests.pop(i)
            if self.game.tracked_quest == q.uid:
                self.game.tracked_quest = self.game.quests[0].uid if self.game.quests else ""
            self.events.append(rules.ev("note", text=f"you tear down {q.title}."))

    # -- the village ---------------------------------------------------------
    def do_assign_worker(self, p):
        self.message = "Farm workers are not enabled in this manual-garden build."

    def do_unassign_worker(self, p):
        self.message = "Farm workers are not enabled in this manual-garden build."

    def do_plant_crop(self, p):
        ok, message = FARM.plant(self.game, str(p.get("crop", "")), int(p.get("qty", 1)))
        self.message = message
        if ok:
            self.events.append(rules.ev("note", text=message))

    def do_harvest_farm(self, p):
        ok, message, rows = FARM.harvest(self.game)
        self.message = message
        if ok:
            for row in rows:
                self.events.append(rules.ev("found", items=[f"{row['qty']}x {row['item']}"]))

    def do_expand_farm(self, p):
        ok, message = FARM.expand(self.game)
        self.message = message
        if ok:
            self.events.append(rules.ev("note", text=message))

    def do_craft(self, p):
        ok, message, recipe = CRAFT.craft(self.game, str(p.get("recipe", "")))
        self.message = message
        if ok and recipe:
            self.events.append(rules.ev("crafted", name=recipe["result"]["item"],
                                        qty=recipe["result"]["qty"]))

    def do_equip(self, p):
        m = next((x for x in self.game.roster if x.uid == str(p.get("uid", ""))), None)
        if m is None:
            return
        name = str(p.get("name", ""))
        if not name:
            slot = str(p.get("slot", "weapon"))
            old = m.equipment.pop(slot, None)
            if old:
                self.game.add_item(old["name"])
                self.message = f"{m.name} removes {old['name']}."
            return
        spec = self.game.items.get(name) or {}
        kind = spec.get("kind")
        slot = {"weapon": "weapon", "armor": "armor", "accessory": "accessory",
                "equipment": "accessory"}.get(kind)
        if slot is None or self.game.count(name) <= 0:
            self.message = "That cannot be equipped."
            return
        stats = {str(k): int(v) for k, v in (spec.get("stats") or {}).items()}
        if not stats:
            level = max(1, int(spec.get("level", 1)))
            stats = ({"atk": 2 + level // 4} if slot == "weapon" else
                     {"def": 2 + level // 5} if slot == "armor" else {"spd": 2})
        old = m.equipment.get(slot)
        self.game.consume(name)
        if old:
            self.game.add_item(old["name"])
        m.equipment[slot] = {"name": name, "kind": kind, "stats": stats,
                             "skill_tree": deepcopy(spec.get("skill_tree") or {})}
        self.message = f"{m.name} equips {name}."

    def do_sell(self, p):
        name = p.get("name", "")
        qty = int(p.get("qty", 1))
        keep = {q.target for q in self.game.quests if q.kind == "fetch"}
        if name in keep and not p.get("force"):
            self.message = f"{name} is owed on a contract."
            return
        have = self.game.count(name)
        qty = have if p.get("all") else min(qty, have)
        if qty <= 0:
            return
        value = self.game.value_of(name) * qty
        self.game.consume(name, qty)
        self.game.gold += value
        self.events.append(rules.ev("sold", name=name, qty=qty, gold=value))

    def do_sell_junk(self, p):
        keep = {q.target for q in self.game.quests if q.kind == "fetch"}
        total = n = 0
        for name, qty in list(self.game.inventory.items()):
            spec = self.game.items.get(name, {})
            if spec.get("kind") != "material" or name in keep or qty <= 0:
                continue
            total += self.game.value_of(name) * qty
            n += qty
            self.game.consume(name, qty)
        self.game.gold += total
        self.events.append(rules.ev("sold", name="loose material", qty=n, gold=total))

    def do_buy(self, p):
        name = p.get("name", "")
        qty = max(1, int(p.get("qty", 1)))
        spec = self.game.items.get(name)
        if not spec or "buy" not in spec:
            self.message = "the stall doesn't carry that."
            return
        if spec.get("book") and spec["book"] in self.game.craft_books:
            self.message = "That craft book is already in your workshop."
            return
        if spec.get("book"):
            qty = 1
        cost = int(spec["buy"]) * qty
        if cost > self.game.gold:
            self.message = f"{cost}g, and you have {self.game.gold}g."
            return
        self.game.gold -= cost
        if spec.get("book"):
            self.game.craft_books.add(str(spec["book"]))
            self.message = f"Learned the recipes in {name}."
        else:
            self.game.add_item(name, qty)
        self.events.append(rules.ev("bought", name=name, qty=qty, gold=cost))

    def do_train(self, p):
        from .entities import xp_for_level
        m = next((x for x in self.game.roster if x.uid == str(p.get("uid", ""))), None)
        if not m:
            return
        cost = int(round(70 + 22 * m.level ** 1.15))
        if cost > self.game.gold:
            self.message = f"the trainer wants {cost}g."
            return
        self.game.gold -= cost
        gained = m.gain_xp(max(1, xp_for_level(m.level + 1) - xp_for_level(m.level)))
        self.events.append(rules.ev("trained", who=m.name, gold=cost,
                                    level=gained[-1] if gained else m.level))

    def do_purchase_skill(self, p):
        """Spend one or more earned Skill Points on an authored tree node."""
        m = next((x for x in self.game.roster if x.uid == str(p.get("uid", ""))), None)
        if m is None:
            self.message = "That companion is no longer in your roster."
            return
        ok, message = m.purchase_skill_node(str(p.get("node", "")))
        self.message = message
        if ok:
            self.events.append(rules.ev("skill_tree", who=m.name, uid=m.uid,
                                        node=str(p.get("node", "")), points=m.skill_points))

    def do_set_active_moves(self, p):
        """Choose up to four already learned moves for the field loadout."""
        m = next((x for x in self.game.roster if x.uid == str(p.get("uid", ""))), None)
        if m is None:
            self.message = "That companion is no longer in your roster."
            return
        requested = p.get("moves") or []
        if not isinstance(requested, list):
            self.message = "Choose moves as a list of move IDs."
            return
        available = {move.id for move in m.template.moves_at_level(m.level)}
        unique = []
        for move_id in requested:
            move_id = str(move_id)
            if move_id in available and move_id not in unique:
                unique.append(move_id)
        if not unique:
            self.message = "No legal learned moves were selected."
            return
        m.active_moves = unique[:4]
        self.message = f"{m.name}'s field moves are set."

    def do_summon(self, p):
        if self.game.shards < B.SUMMON_COST:
            self.message = f"a summon costs {B.SUMMON_COST} shards."
            return
        if len(self.game.roster) >= B.ROSTER_CAP:
            self.message = "your roster is full — release something first."
            return
        self.game.shards -= B.SUMMON_COST
        t = self.game.bestiary.roll_summon()
        m = self.game.add_monster(t)
        self.events.append(rules.ev("summon", name=t.name, title=t.title or t.role,
                                    rarity=t.rarity, level=m.level, hp=m.max_hp,
                                    power=m.power, appearance=t.appearance[:110]))

    def do_release(self, p):
        m = next((x for x in self.game.roster if x.uid == str(p.get("uid", ""))), None)
        if not m or len(self.game.roster) <= 1:
            return
        pay = self.game.release(m)
        self.events.append(rules.ev("released", who=m.name, shards=pay))

    def do_reorder(self, p):
        """Swap two monsters in the roster (and therefore in the four)."""
        a, b = str(p.get("a", "")), str(p.get("b", ""))
        ids = [m.uid for m in self.game.roster]
        if a not in ids or b not in ids or a == b:
            return
        i, j = ids.index(a), ids.index(b)
        self.game.roster[i], self.game.roster[j] = self.game.roster[j], self.game.roster[i]
        pu = self.game.party_uids
        if (a in pu) != (b in pu):
            self.game.party_uids = [b if u == a else a if u == b else u for u in pu]

    # -- the run -------------------------------------------------------------
    def do_start_run(self, p):
        self._begin_run(p.get("region"), p.get("depth", "deep"), "")

    def do_start_quest_run(self, p):
        i = int(p.get("index", -1))
        q = (self.game.quests[i] if 0 <= i < len(self.game.quests) else
             next((x for x in self.game.quests if x.uid == self.game.tracked_quest), None))
        if q is None:
            self.message = "Sign a mission at the board first."
            return
        self.game.tracked_quest = q.uid
        self._begin_run(self.quest_region(q), p.get("depth", "deep"), q.uid)
        if self.run:
            self.events.append(rules.ev("note", text=f"Operation deployed: {q.title}."))

    def _begin_run(self, region, depth: str, quest_uid: str) -> None:
        if not self.game.party:
            self.message = "You have no monsters to send in."
            return
        regions = self.regions()
        region = region or (regions[0]["key"] if regions else "")
        if not region:
            self.message = "The Void Atlas is empty. Create an area and assign a monster in the Forge."
            return
        self.run = Run(region, depth, self.party_level, quest_uid=quest_uid)
        self.screen = "descent"
        self.events = [rules.ev("note", text="The light behind you thins to a coin, "
                                             "then a pinprick, then nothing.")]

    def do_descend(self, p):
        if not self.run or self.screen != "descent":
            return
        nid = p.get("node", "")
        if not self.run.map.can_enter(nid):
            self.message = "You cannot reach that from here."
            return
        node = self.run.map.enter(nid)
        self._resolve_node(node)

    def _resolve_node(self, node):
        run = self.run
        g = self.game
        # A new hunter starts with one companion. Keep the first few wild
        # levels level with that companion; deeper raids rise gradually.
        lvl = max(1, run.level + max(0, node.row - 1) // 3)
        if node.kind in ("fight", "elite", "boss"):
            foes = self._encounter(run.map.region, lvl, node.kind)
            if not foes:
                # An area may be edited while a save is open.  Do not turn a
                # now-empty roster into a Battle with no enemies.
                run.map.finish_current()
                self.events.append(rules.ev("note", text=self.message or
                                            "Nothing answers from this area."))
                return
            title = {"fight": node.name, "elite": f"{node.name} — ELITE",
                     "boss": "THE THING AT THE BOTTOM"}[node.kind]
            self.battle = Battle(g.party, foes, title=title,
                                 allow_flee=node.kind != "boss")
            self.events += self.battle.start()
            self.screen = "battle"
            return
        if node.kind == "gather":
            found = self._gather(run.map.region, lvl, 2 + random.randint(1, 3))
            run.bag += found
            self.events += [rules.ev("note", text=random.choice(mapgen.FLAVOUR["gather"])),
                            rules.ev("found", items=found)]
        elif node.kind == "cache":
            gold = int((20 + lvl * 9) * run.mult * random.uniform(0.7, 1.5))
            shards = random.randint(1, 6)
            run.gold += gold
            run.shards += shards
            self.events += [rules.ev("note", text=random.choice(mapgen.FLAVOUR["cache"])),
                            rules.ev("cache", gold=gold, shards=shards)]
        elif node.kind == "shrine":
            for m in g.party:
                m.heal(int(m.max_hp * 0.35))
                m.restore_pp(6)
            self.events += [rules.ev("note", text=random.choice(mapgen.FLAVOUR["shrine"])),
                            rules.ev("shrine", hp=35, pp=6)]
        run.map.finish_current()

    @staticmethod
    def _label(foes):
        """Three Grotesque Drakes are unreadable. A, B and C are not."""
        from collections import Counter
        counts = Counter(f.template.name for f in foes)
        seen = {}
        for f in foes:
            n = f.template.name
            if counts[n] > 1:
                i = seen.get(n, 0)
                seen[n] = i + 1
                f.nickname = f"{n} {chr(65 + i)}"
        return foes

    def _encounter(self, region: str, level: int, kind: str):
        b = self.game.bestiary
        assigned = AREAS.templates_for(b, region, bosses=None)
        ordinary = [t for t in assigned if not t.is_boss]
        if kind == "boss":
            pool = [t for t in AREAS.templates_for(b, region, bosses=True)
                    if abs(t.level - level) <= 16]
            pool = pool or [t for t in assigned if t.is_boss] or ordinary
            if not pool:
                self.message = "This area has no assigned monsters. Edit it in the Forge."
                return []
            foes = self._label([spawn(random.choice(pool), max(1, level + 1), enemy=True)])
            for foe in foes:
                self.game.discover(foe.template, "encounter")
            return foes
        pool = ordinary
        if not pool:
            self.message = "This area has no non-boss monsters assigned in the Forge."
            return []
        if kind == "elite":
            strong = [t for t in pool if t.rarity in ("Rare", "Epic")] or pool
            lead = random.choice(strong)
            foes = self._label([spawn(lead, level + 1, enemy=True)])
            for foe in foes:
                self.game.discover(foe.template, "encounter")
            return foes
        lead = random.choice(pool)
        # The classic loop is one visible wild creature at a time. Groups made
        # the first starter feel as if it was being dog-piled before the player
        # had earned a second companion.
        foes = self._label([spawn(lead, level, enemy=True)])
        for foe in foes:
            self.game.discover(foe.template, "encounter")
        return foes

    def _gather(self, region: str, lvl: int, n: int) -> list[str]:
        pool = []
        for t in AREAS.templates_for(self.game.bestiary, region, bosses=False):
            pool += [d.item for d in t.drops if d.kind in ("material", "consumable")]
        pool = pool or ["Void Residue"]
        return [random.choice(pool) for _ in range(n)]

    # -- battle --------------------------------------------------------------
    def do_battle(self, p):
        if not self.battle or self.battle.finished:
            return
        move = p.get("move", "skill")
        if move == "capture":
            self.events += self.battle.capture(self.game)
        else:
            self.events += self.battle.act(move, p.get("skill"), p.get("target"))
        self._after_battle()

    def do_use_item(self, p):
        name = p.get("name", "")
        target = p.get("target")
        if self.battle and not self.battle.finished:
            self.events += self.battle.use_item(self.game, name, target)
            self._after_battle()
            return
        # out of battle: camp use
        spec = (self.game.items.get(name) or {}).get("use")
        if not spec or self.game.count(name) <= 0:
            return
        who = next((m for m in self.game.party if m.uid == target), None) or self.game.party[0]
        self.game.consume(name)
        if "heal_pct" in spec:
            got = who.heal(int(who.max_hp * spec["heal_pct"]))
            self.events.append(rules.ev("heal", target=who.name, target_uid=who.uid,
                                        amount=got, hp=who.cur_hp, max_hp=who.max_hp))
        if "pp_restore" in spec:
            restored = who.restore_pp(int(spec["pp_restore"]))
            if restored:
                self.events.append(rules.ev("pp_restore", target=who.name, target_uid=who.uid,
                                            amount=restored))
        if spec.get("cleanse"):
            who.statuses.clear()
        if "revive_pct" in spec:
            who.cur_hp = max(who.cur_hp, int(who.max_hp * spec["revive_pct"]))

    def _after_battle(self):
        bt = self.battle
        if not bt or not bt.finished:
            return
        g, run = self.game, self.run
        if bt.outcome == "win":
            for e in bt.enemies:
                if not e.alive:
                    g.record_kill(e.template)
            self.spoils = self._spoils(bt)
            self.battle = None
            self.screen = "spoils"
            return
        elif bt.outcome == "capture":
            self.spoils = self._spoils(bt)
            self.battle = None
            self.screen = "spoils"
            return
        elif bt.outcome == "lose":
            self._wipe()
            return
        else:                                   # flee or draw
            self.message = "You break contact and pull out."
            self.battle = None
            self.do_extract({"reason": bt.outcome})
            return
        self.battle = None

    def _spoils(self, bt) -> dict:
        """What the fight was worth, held back until the player takes it.

        Nothing here is awarded yet. The interface shows it, the player decides
        what to carry, and do_claim settles up.
        """
        g, run = self.game, self.run
        r = bt.rewards or {}
        xp = int(r.get("xp", 0))
        gold = int(r.get("gold", 0) * (run.mult if run else 1))

        counts: dict = {}
        for name in r.get("loot", []):
            counts[name] = counts.get(name, 0) + 1
        loot = [{"name": n, "qty": q, "value": g.value_of(n), "take": True,
                 "desc": g.items.get(n, {}).get("desc", ""),
                 "usable": bool(g.items.get(n, {}).get("use"))}
                for n, q in sorted(counts.items())]

        # what this xp does to each of them, worked out without touching anybody
        party = []
        for m in g.party:
            if not m.alive:
                party.append({"uid": m.uid, "name": m.name, "level": m.level,
                              "xp": m.xp, "xp_next": m.xp_to_next, "gain": 0,
                              "xp_span": m.xp_span, "xp_done": m.xp_done,
                              "levels": 0, "down": True})
                continue
            level, total, gained = m.level, m.xp + xp, 0
            while level < B.MAX_LEVEL and total >= xp_for_level(level + 1):
                level += 1
                gained += 1
            party.append({"uid": m.uid, "name": m.name, "level": m.level,
                          "xp": m.xp, "xp_next": m.xp_to_next, "gain": xp,
                          "xp_span": m.xp_span, "xp_done": m.xp_done,
                          "new_level": level, "levels": gained, "down": False,
                          "after_next": max(1, xp_for_level(level + 1) - total)
                                        if level < B.MAX_LEVEL else 0})
        return {"title": bt.title, "xp": xp, "gold": gold,
                "shards": int(r.get("shards", 0)), "loot": loot, "party": party,
                "boss": bool(run and run.map.at_boss), "in_run": bool(run),
                "captured": dict(r.get("captured") or {})}

    def do_claim(self, p):
        """Take the spoils. `leave` names anything being left behind."""
        if not self.spoils:
            return
        self._settle([str(x) for x in (p.get("leave") or [])])

    def _settle(self, leave: list) -> None:
        sp, g, run = self.spoils, self.game, self.run
        self.spoils = None
        if not sp:
            return
        left = {str(x).lower() for x in leave}
        taken, dropped = [], []
        for row in sp["loot"]:
            (dropped if row["name"].lower() in left else taken).extend(
                [row["name"]] * row["qty"])

        if run:
            run.gold += sp["gold"]
            run.shards += sp["shards"]
            run.xp += sp["xp"]
            run.bag += taken
            run.map.finish_current()
        else:
            g.gold += sp["gold"]
            g.shards += sp["shards"]
            for name in taken:
                g.add_item(name)
        for m in g.party:
            if m.alive:
                for lv in m.gain_xp(sp["xp"]):
                    self.events.append(rules.ev("level", who=m.name, uid=m.uid,
                                                level=lv, hp=m.max_hp, power=m.power))
        self.events.append(rules.ev("claimed", gold=sp["gold"], shards=sp["shards"],
                                    xp=sp["xp"], taken=len(taken), left=len(dropped)))
        if run and run.map.at_boss:
            g.regions_cleared[run.map.region] = g.regions_cleared.get(run.map.region, 0) + 1
            self.do_extract({"reason": "boss"})
            return
        self.screen = "descent" if run else "home"

    def _wipe(self):
        g, run = self.game, self.run
        lost_gold = int((run.gold if run else 0) * 0.5)
        kept = (run.bag[: len(run.bag) // 2] if run else [])
        for item in kept:
            g.add_item(item)
        if run:
            g.gold += run.gold - lost_gold
            self.events.append(rules.ev("wipe", gold_lost=lost_gold,
                                        items_lost=len(run.bag) - len(kept)))
        for m in g.roster:
            m.full_heal()
        g.advance_time(24 * 60)
        g.board = []
        self.run = None
        self.battle = None
        self.spoils = None
        self.screen = "home"
        self.message = "The pack falls. You wake at the gate, emptied."

    def do_extract(self, p):
        run = self.run
        g = self.game
        if not run:
            self.screen = "home"
            return
        counts: dict[str, int] = {}
        for item in run.bag:
            g.add_item(item)
            counts[item] = counts.get(item, 0) + 1
        g.gold += run.gold
        g.shards += run.shards
        g.advance_time(24 * 60)
        g.board = []
        g.deepest_run = max(g.deepest_run, run.map.row)
        for m in g.roster:
            m.clear_battle_state()
        self.events.append(rules.ev("extract", gold=run.gold, shards=run.shards,
                                    xp=run.xp, items=counts,
                                    depth=run.map.row, rows=run.map.depth_rows,
                                    reason=p.get("reason", "chosen")))
        self.run = None
        self.battle = None
        self.spoils = None
        self.screen = "home"
