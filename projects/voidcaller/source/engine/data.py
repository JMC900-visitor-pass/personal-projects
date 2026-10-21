"""Loads monsters straight out of the generator's own format.

Nothing here changes your dataset. Point it at any .jsonl / .json written by
generate_monsters.py -- drop new files into voidcaller/data/monsters/ (or just
regenerate output/monsters.jsonl) and the new monsters show up in the game, in
the Void, in the summon pool and on the quest board, with no code changes.
"""
from __future__ import annotations

import glob
import json
import os
import random
import statistics
from dataclasses import dataclass, field

from . import balance as B
from . import effects as FX
from .model import (COMBAT_TYPES, CORE_STATS, RARITY_BST, RARITY_MARKS,
                    canonical_rarity, canonical_role, canonical_type, slug)

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(GAME_DIR)
SOURCES_FILE = os.path.join(GAME_DIR, "data", "sources.json")
STARTERS_FILE = os.path.join(GAME_DIR, "data", "starters.json")

# Where the game looks for monsters, in order. The first two are the drop
# folder inside the game; the rest are the places a generator usually writes.
# If your dataset lives somewhere else entirely, say so in data/sources.json
# or set VOIDCALLER_MONSTERS -- see docs/IMPORT_EXPORT.md.
BUILTIN_SEARCH = [
    os.path.join(GAME_DIR, "data", "monsters", "*.jsonl"),
    os.path.join(GAME_DIR, "data", "monsters", "*.json"),
    os.path.join(REPO_DIR, "output", "monsters.jsonl"),
    os.path.join(REPO_DIR, "output", "monsters.json"),
    os.path.join(REPO_DIR, "MOnster gen", "monsters.jsonl"),
]


def _configured_sources() -> list:
    """Extra places to look, from data/sources.json and $VOIDCALLER_MONSTERS.

    Relative paths are resolved against the game folder, and a leading ~ is
    expanded, so a sources file can be moved between machines.
    """
    out = []
    env = os.environ.get("VOIDCALLER_MONSTERS", "")
    for chunk in env.split(os.pathsep):
        if chunk.strip():
            out.append(chunk.strip())
    try:
        with open(SOURCES_FILE, encoding="utf-8") as fh:
            blob = json.load(fh)
        out += [p for p in (blob.get("monsters") or []) if isinstance(p, str)]
    except Exception:
        pass
    resolved = []
    for p in out:
        p = os.path.expanduser(p)
        if not os.path.isabs(p):
            p = os.path.join(GAME_DIR, p)
        resolved.append(p)
    return resolved


def search_paths(extra_paths: list | None = None) -> list:
    """Every pattern that will be tried, in order, so a tool can report them."""
    return _configured_sources() + list(BUILTIN_SEARCH) + list(extra_paths or [])


# kept as a name because tools and docs refer to it
SEARCH = BUILTIN_SEARCH

MOVE_FILE = os.path.join(GAME_DIR, "data", "moves.json")

# Compatibility export for a few old tools.  Values are the canonical twelve
# combat Types now, not the retired eight-element affinity vocabulary.
ELEMENTS = list(COMBAT_TYPES)


def _number(value: object, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _integer(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _percent(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    # Content examples express a five-percent crit as 0.05, while UI and the
    # odds engine use percentages.  Normalize once at the data boundary.
    return number * 100.0 if 0.0 < number <= 1.0 else number


# ---------------------------------------------------------------------------
@dataclass
class Skill:
    """A canonical V2 move.

    The compatibility properties at the bottom deliberately keep old screen
    and tool code from crashing while the rest of the project migrates.  New
    content is stored and exposed using ``category``/``type``/``effects`` only.
    """
    id: str
    name: str
    category: str = "physical"    # physical | magical | support
    type: str | None = None
    power: int = 0
    accuracy: float = 100.0
    pp: int = 0                    # 0 = unlimited only for Struggle
    target: str = "single"        # single | all_enemies | random | self | all_allies
    priority: int = 0
    crit: float = 0.0
    effects: list = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    description: str = ""
    migration_notes: list[str] = field(default_factory=list)

    @property
    def is_damage(self) -> bool:
        return self.power > 0 and self.category in ("physical", "magical")

    @property
    def is_magical(self) -> bool:
        return self.category == "magical"

    @property
    def hits_enemies(self) -> bool:
        return self.target in ("single", "all_enemies", "random")

    # statuses that are good to be under, as opposed to good to inflict
    BOONS = ("regen", "haste", "shield")

    @property
    def is_friendly(self) -> bool:
        """A move meant for your own side: it does no damage, and everything it
        does is something you would want done to you.

        This is decided from the parsed effects rather than the dataset's
        `target` field, because generators write healing moves as
        `target: single` all the time -- and a heal aimed at the enemy is the
        single most confusing thing a fight can do.
        """
        if self.is_damage or not self.effects:
            return False
        for f in self.effects:
            if f.kind in ("heal", "revive", "cleanse"):
                continue
            if f.kind == "stat" and f.amount > 0:
                continue
            if f.kind == "status" and f.key in self.BOONS:
                continue
            return False            # a debuff, a drain, anything aimed outward
        return True

    @property
    def rating(self) -> str:
        """A short label for how hard the move hits, for lists and codex pages."""
        if not self.is_damage:
            return ""
        p = self.power
        band = ("light" if p < 30 else "solid" if p < 55 else
                "heavy" if p < 85 else "brutal")
        return f"pw {p} · {band}"

    # --- temporary source-compatibility aliases ---------------------------
    @property
    def kind(self) -> str:
        return self.category

    @property
    def element(self) -> str:
        return self.type.casefold() if self.type else "none"

    @property
    def effect_text(self) -> str:
        return self.description

    @property
    def fx(self) -> list:
        return self.effects

    @property
    def mp_cost(self) -> int:
        """Retired API: PP is the only move resource in V2."""
        return 0

    @property
    def weight(self) -> int:
        """Retired generated AI field; battle AI now evaluates move intent."""
        return 0

    @classmethod
    def from_raw(cls, raw: dict) -> "Skill":
        raw = raw if isinstance(raw, dict) else {}
        text = str(raw.get("description") or raw.get("effect") or "").strip()
        # Legacy move ``type`` was a category; V2 ``type`` is a combat Type.
        raw_type = str(raw.get("type") or "").strip()
        category = str(raw.get("category") or raw.get("kind") or "").casefold()
        if not category and raw_type.casefold() in ("physical", "magical", "support", "status"):
            category = raw_type.casefold()
        if category == "status":
            category = "support"
        if category not in ("physical", "magical", "support"):
            category = "physical"
        combat_type = canonical_type(raw_type if raw.get("category") else raw.get("element"))
        power = max(0, _integer(raw.get("power"), 0))
        target = (raw.get("target") or "single").lower()
        structured, issues = FX.read_many(raw.get("effects"))
        fx = structured if raw.get("effects") is not None else FX.parse(text)
        # the dataset sometimes files a damaging move under an ally-facing target.
        # a move that hurts people points at people who deserve it.
        friendly_fx = any(f.kind in ("heal", "revive", "cleanse") or
                          (f.kind == "stat" and f.amount > 0) for f in fx)
        if power > 0 and category in ("physical", "magical"):
            if not friendly_fx:
                if target == "all_allies":
                    target = "all_enemies"
                elif target == "self":
                    target = "single"
            elif target in ("self", "all_allies"):
                category = "support"   # data noise: a buff filed with a power value
        pp_default = 35 if power > 0 else 20
        return cls(
            id=str(raw.get("id") or slug(raw.get("name"), "move")),
            name=str(raw.get("name") or "Tackle"),
            category=category,
            type=combat_type,
            power=power,
            accuracy=max(1.0, min(100.0, _percent(raw.get("accuracy"), 100.0))),
            pp=max(0, int(raw.get("pp", pp_default) or 0)),
            target=target,
            priority=max(-7, min(7, int(raw.get("priority") or 0))),
            crit=max(0.0, min(B.CRIT_CAP, _percent(raw.get("crit"), 0.0))),
            effects=fx,
            tags=[slug(tag) for tag in
                  ([raw.get("tags")] if isinstance(raw.get("tags"), str) else (raw.get("tags") or []))
                  if str(tag).strip()],
            description=text,
            migration_notes=issues + (["legacy MP cost ignored"] if raw.get("mp_cost") else [])
                            + (["legacy AI weight ignored"] if raw.get("weight") else []),
        )


BASIC_ATTACK = Skill(id="tackle", name="Tackle", category="physical", type=None,
                     power=44, accuracy=100, pp=20, target="single",
                     tags=["basic", "melee"], description="A reliable close-range strike.")
BASIC_DODGE = Skill(id="dodge", name="Dodge", category="support", type=None,
                    power=0, accuracy=100, pp=12, target="self", priority=1,
                    tags=["basic", "guard"], description="Brace and reduce incoming damage this round.")
# A last-resort action is deliberately weaker than a real base move. It only
# appears after every finite-PP attack has been spent, so a battle can never
# dead-end because an author made a small move pool.
BASIC_STRUGGLE = Skill(id="struggle", name="Struggle", category="physical", type=None,
                       power=24, accuracy=100, pp=0, target="single",
                       tags=["fallback"], description="A last-resort physical attack.")


@dataclass
class Drop:
    item: str
    rate: float
    kind: str = "material"


@dataclass
class MonsterTemplate:
    """A species definition, not an owned creature.

    ``level`` survives as a recommended wild encounter level for existing area
    content.  It is never used to derive rarity or a player's combat Level.
    ``primary``/``secondary`` are compatibility-friendly names for the two
    canonical combat Types; ``family`` is deliberately separate.
    """
    id: str
    name: str
    title: str = ""
    level: int = 1
    rarity: str = "Common"
    role: str = "Bruiser"
    primary: str = "Primal"
    secondary: str | None = None
    size: str = "Medium"
    family: str = ""
    sex_mode: str = "unknown"
    capture_rate: float = 0.25
    habitat: list = field(default_factory=list)
    is_boss: bool = False
    min_group: int = 1
    max_group: int = 1
    ambush: float = 0.0
    stats: dict = field(default_factory=dict)  # exactly the six base stats
    rewards: dict = field(default_factory=dict)
    resist: dict = field(default_factory=dict)
    # Base moves are the two fundamentals a generated creature begins with:
    # one dependable melee action and one defensive/support action. Skills are
    # optional authored moves, while skill_tree moves arrive through levelling.
    base_moves: list = field(default_factory=list)
    skills: list = field(default_factory=list)
    learnset: list = field(default_factory=list)
    skill_tree: list = field(default_factory=list)
    drops: list = field(default_factory=list)
    steal: list = field(default_factory=list)
    appearance: str = ""
    lore: str = ""
    quote: str = ""
    tactic: str = ""
    evolution: dict = field(default_factory=dict)
    # A Forge-generated stable key for the creature's procedural portrait.
    # Older datasets do not need it: portraits derive a key from normal fields.
    portrait_seed: str = ""
    # Visual-only choice used by the deterministic 16px Forge renderer.
    sprite_archetype: str = "Core"

    # -- derived ------------------------------------------------------------
    @property
    def base_stats(self) -> dict:
        return {key: int(self.stats.get(key, 1)) for key in CORE_STATS}

    @property
    def bst(self) -> int:
        return sum(self.base_stats.values())

    @property
    def types(self) -> dict:
        return {"primary": self.primary, "secondary": self.secondary}

    @property
    def affinity(self) -> dict:
        """Retired compatibility surface; V2 Type maths never reads this."""
        return {}

    def attach_curve(self, _curve: dict) -> None:
        """No-op legacy hook retained for callers from the pre-V2 Bestiary."""

    def stat_at(self, stat: str, level: int) -> float:
        """Species base stat scaled to a combat Level (1–50), Pokemon-style.

            HP    = floor(2 x base x level / 50) + level + 10
            other = floor(2 x base x level / 50) + 5

        HP's larger tail is deliberate and is what lets HP sit in the same BST
        budget as ATK while still being worth buying.
        """
        level = max(1, min(B.MAX_LEVEL, int(level or 1)))
        base = float(self.base_stats.get(stat, 1))
        scaled = int(2.0 * base * level / B.LEVEL_DIVISOR)
        if stat == "hp":
            return max(float(B.HP_FLOOR), float(scaled + level + B.HP_LEVEL_BONUS))
        return max(1.0, float(scaled + B.STAT_FLAT_BONUS))

    @property
    def elements(self) -> list[str]:
        """Compatibility label: the creature's combat Types, not move elements."""
        return [value for value in (self.primary, self.secondary) if value]

    def weakness(self) -> list[str]:
        from . import elements as EL
        return [name for name, _ in EL.weaknesses(self)]

    def resistance(self) -> list[str]:
        from . import elements as EL
        return [name for name, _ in EL.resistances(self)]

    def moves_at_level(self, level: int) -> list[Skill]:
        """All learned moves at a level, keeping a stable authored order."""
        level = max(1, min(B.MAX_LEVEL, int(level or 1)))
        learned: list[Skill] = []
        for row in self.learnset:
            if not isinstance(row, dict) or int(row.get("level", 1) or 1) > level:
                continue
            move = row.get("skill")
            if isinstance(move, Skill) and all(old.id != move.id for old in learned):
                learned.append(move)
        if not learned:
            learned = list(self.base_moves + self.skills)
        return learned

    def validation_issues(self) -> list[str]:
        """Machine-readable content checks shared by Forge and import tools."""
        issues = []
        if self.rarity not in RARITY_BST:
            issues.append("rarity is invalid")
        low, high = RARITY_BST.get(self.rarity, (0, 10_000))
        if not low <= self.bst <= high:
            issues.append(f"BST {self.bst} is outside {self.rarity} budget {low}–{high}")
        if self.primary not in COMBAT_TYPES or self.secondary not in (None, *COMBAT_TYPES):
            issues.append("combat Type is invalid")
        if self.secondary == self.primary:
            issues.append("secondary Type duplicates primary Type")
        if len(self.base_moves) > 2:
            issues.append("species has more than two base moves")
        return issues

    @classmethod
    def from_raw(cls, raw: dict, move_library: dict[str, Skill] | None = None) -> "MonsterTemplate":
        raw = raw if isinstance(raw, dict) else {}
        old_type = raw.get("type") or {}
        raw_types = raw.get("types") or {}
        t = raw_types if isinstance(raw_types, dict) else {}
        old_type = old_type if isinstance(old_type, dict) else {}
        enc = raw.get("encounter") or {}
        enc = enc if isinstance(enc, dict) else {}
        source_stats = raw.get("base_stats") or raw.get("stats") or {}
        source_stats = source_stats if isinstance(source_stats, dict) else {}
        defaults = {"hp": 30, "atk": 35, "def": 30, "mag": 30, "res": 30, "spd": 35}
        st = {key: _number(source_stats.get(key), fallback) for key, fallback in defaults.items()}

        def resolve_move(ref: object) -> Skill | None:
            if isinstance(ref, Skill):
                return ref
            if isinstance(ref, dict):
                return Skill.from_raw(ref)
            ident = str(ref or "")
            return (move_library or {}).get(ident) or (move_library or {}).get(slug(ident))

        learned: list[dict] = []
        raw_learnset = raw.get("learnset")
        if isinstance(raw_learnset, list):
            for entry in raw_learnset:
                if isinstance(entry, dict):
                    skill = resolve_move(entry.get("move") or entry.get("id"))
                    at = max(1, min(B.MAX_LEVEL, int(entry.get("level", 1) or 1)))
                else:
                    skill, at = resolve_move(entry), 1
                if skill and all(row["skill"].id != skill.id for row in learned):
                    learned.append({"level": at, "move_id": skill.id, "skill": skill})

        raw_base = raw.get("base_moves")
        authored_moves = raw.get("moves", raw.get("skills") or [])
        if isinstance(raw_base, list):
            base_moves = [move for move in (resolve_move(row) for row in raw_base) if move][:2]
            later_moves = [move for move in (resolve_move(row) for row in authored_moves) if move]
        elif learned:
            base_moves = [row["skill"] for row in learned if row["level"] <= 1][:2]
            later_moves = [row["skill"] for row in learned if row["level"] > 1]
        else:
            # Legacy data put all moves under `skills`; retain the first two as
            # its authored fundamentals and move the rest into the learnset.
            old_moves = [move for move in (resolve_move(row) for row in authored_moves) if move]
            base_moves, later_moves = old_moves[:2], old_moves[2:]
        # A generation starts with exactly two dependable fundamentals: one
        # damaging melee/physical action and one defensive or supportive move.
        # Additional authored moves belong in the learnset rather than taking a
        # third starting slot.
        fundamental_damage = next((move for move in base_moves
                                   if move.category == "physical" and move.is_damage), BASIC_ATTACK)
        fundamental_support = next((move for move in base_moves if move.category == "support"), BASIC_DODGE)
        displaced = [move for move in base_moves
                     if move.id not in {fundamental_damage.id, fundamental_support.id}]
        later_moves = displaced + later_moves
        base_moves = [fundamental_damage, fundamental_support]
        base_rows = [{"level": 1, "move_id": move.id, "skill": move} for move in base_moves]
        if learned:
            # A hand-authored learnset must never make the two fundamental
            # moves disappear. Keep explicit later entries, then prepend any
            # missing starter moves in their stable authored order.
            known = {row["skill"].id for row in learned}
            learned = [row for row in base_rows if row["skill"].id not in known] + learned
        else:
            learned = (base_rows
                       + [{"level": min(B.MAX_LEVEL, index + 2), "move_id": move.id, "skill": move}
                          for index, move in enumerate(later_moves)])

        family = str(raw.get("family") or old_type.get("family") or old_type.get("primary") or "Unknown")
        primary = canonical_type(t.get("primary"))
        secondary = canonical_type(t.get("secondary"))
        if primary is None:
            # Old categories are families, not Types. Prefer an authored move's
            # Type, then use a small deterministic identity fallback.
            primary = next((move.type for move in base_moves + later_moves if move.type), None)
        if primary is None:
            by_family = {"plant": "Nature", "aquatic": "Water", "undead": "Spirit",
                         "demon": "Dark", "insect": "Wind", "dragon": "Primal",
                         "construct": "Earth", "elemental": "Arcane", "aberration": "Cosmic"}
            primary = by_family.get(family.casefold(), "Primal")
        return cls(
            id=raw.get("id") or raw.get("name", "mon"),
            name=raw.get("name", "Nameless Thing"),
            title=raw.get("title") or "",
            level=max(1, min(B.MAX_LEVEL, int(raw.get("recommended_level", raw.get("level", 1)) or 1))),
            rarity=canonical_rarity(raw.get("rarity"), legacy_level=int(raw.get("level") or 1)),
            role=canonical_role(raw.get("role")),
            primary=primary,
            secondary=secondary if secondary != primary else None,
            size=raw.get("size") or old_type.get("size") or "Medium",
            family=family,
            sex_mode=str(raw.get("sex_mode") or "unknown"),
            capture_rate=max(0.01, min(1.0, float(raw.get("capture_rate", 0.25) or 0.25))),
            habitat=[h.lower() for h in (raw.get("habitat") or [])],
            is_boss=bool(enc.get("is_boss")) or (raw.get("role") == "Boss"),
            min_group=int(enc.get("min_group") or 1),
            max_group=int(enc.get("max_group") or 1),
            ambush=float(enc.get("ambush_rate") or 0.0),
            stats=st,
            rewards=dict(raw.get("rewards") or {"gold": 10}),
            resist={str(key).casefold(): str(value).casefold()
                    for key, value in (raw.get("status_resist") or {}).items()
                    if str(value).casefold() in {"weak", "resist", "immune", "normal"}},
            base_moves=base_moves,
            skills=later_moves,
            learnset=learned,
            skill_tree=(dict(raw.get("skill_tree")) if isinstance(raw.get("skill_tree"), dict)
                        else [dict(node) for node in (raw.get("skill_tree") or [])
                              if isinstance(node, dict)]),
            drops=[Drop(d.get("item", "Scrap"), float(d.get("rate", 0.2)),
                        d.get("type", "material")) for d in (raw.get("drops") or [])],
            steal=[Drop(d.get("item", "Scrap"), float(d.get("rate", 0.2)), "material")
                   for d in (raw.get("steal") or [])],
            appearance=raw.get("appearance") or "",
            lore=raw.get("lore") or "",
            quote=raw.get("battle_quote") or "",
            tactic=raw.get("tactical_note") or "",
            evolution=(dict(raw.get("evolution"))
                       if isinstance(raw.get("evolution"), dict) else {}),
            portrait_seed=str(raw.get("portrait_seed") or ""),
            sprite_archetype=str(raw.get("sprite_archetype") or "Core"),
        )


# ---------------------------------------------------------------------------
# V2 content no longer fits a curve from the generated dataset.  Its six base
# stats are the authored species identity and the engine's level formula is
# deterministic.  The two tiny compatibility helpers keep older import tools
# from breaking while returning no hidden, data-dependent scaling.
CURVE_STATS = list(CORE_STATS)


def fit_curve(_templates: list) -> dict:
    return {}


def curve_value(_curve: dict, _stat: str, _level: int) -> float:
    return 1.0


class Bestiary:
    def __init__(self, templates: list[MonsterTemplate]):
        self.all = templates
        self.by_id = {t.id: t for t in templates}
        self.by_name = {t.name.lower(): t for t in templates}
        self.curve = {}

    def __len__(self):
        return len(self.all)

    def get(self, key: str) -> MonsterTemplate | None:
        return self.by_id.get(key) or self.by_name.get(str(key).lower())

    def near_level(self, level: int, spread: int = 4, boss: bool | None = None):
        pool = [t for t in self.all
                if abs(t.level - level) <= spread
                and (boss is None or t.is_boss == boss)]
        if not pool:
            pool = sorted(self.all, key=lambda t: abs(t.level - level))[:8]
        return pool

    def in_habitat(self, word: str, level: int, spread: int = 5):
        word = word.lower()
        pool = [t for t in self.near_level(level, spread, boss=False)
                if any(word in h for h in t.habitat)]
        return pool or self.near_level(level, spread, boss=False)

    def habitats(self) -> list[str]:
        seen = {}
        for t in self.all:
            for h in t.habitat:
                seen[h] = seen.get(h, 0) + 1
        return [h for h, _ in sorted(seen.items(), key=lambda kv: -kv[1])]

    def summon_pool(self):
        return [t for t in self.all if not t.is_boss]

    def roll_summon(self) -> MonsterTemplate:
        pool = self.summon_pool()
        weights = [B.RARITY_WEIGHT.get(t.rarity, 10) for t in pool]
        from .luck import pick_weighted
        return pick_weighted(pool, weights)

    def starters(self, n: int = 3) -> list[MonsterTemplate]:
        """The three starter candidates chosen in the Forge.

        `data/starters.json` is optional.  A blank project (or an older data
        folder) still gets a sensible rotating set, while a configured list
        is kept in its authored order and topped up only if it is incomplete.
        """
        configured = []
        try:
            with open(STARTERS_FILE, encoding="utf-8") as fh:
                raw = json.load(fh)
            ids = raw.get("monster_ids", []) if isinstance(raw, dict) else []
            for ident in ids:
                t = self.get(str(ident))
                if t and not t.is_boss and t not in configured:
                    configured.append(t)
        except Exception:
            pass
        pool = [t for t in self.all
                if not t.is_boss and t.level <= 8 and t.role != "Swarm"]
        pool = pool or self.near_level(3, 6, boss=False)
        remaining = [t for t in pool if t not in configured]
        if len(configured) >= n:
            return configured[:n]
        return configured + random.sample(remaining, min(n - len(configured), len(remaining)))


def _iter_raw(path: str):
    if path.endswith(".jsonl"):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
    else:
        with open(path, encoding="utf-8") as f:
            blob = json.load(f)
        rows = blob.get("monsters", []) if isinstance(blob, dict) else blob
        for r in rows:
            yield r


def load_move_library(path: str | None = None) -> dict[str, Skill]:
    """Load reusable V2 moves from ``data/moves.json``.

    Species can still carry legacy inline moves, but new Forge content should
    reference this library from ``learnset``.  Both the authored ID and a
    slugged display-name alias resolve during the transition.
    """
    path = path or MOVE_FILE
    library: dict[str, Skill] = {
        BASIC_ATTACK.id: BASIC_ATTACK,
        BASIC_DODGE.id: BASIC_DODGE,
        BASIC_STRUGGLE.id: BASIC_STRUGGLE,
    }
    try:
        with open(path, encoding="utf-8") as fh:
            blob = json.load(fh)
        rows = blob.get("moves", []) if isinstance(blob, dict) else blob
        for raw in rows if isinstance(rows, list) else []:
            if not isinstance(raw, dict):
                continue
            move = Skill.from_raw(raw)
            library[move.id] = move
            library.setdefault(slug(move.name), move)
    except (OSError, json.JSONDecodeError):
        pass
    return library


def load_bestiary(extra_paths: list[str] | None = None) -> Bestiary:
    seen, out = set(), []
    move_library = load_move_library()
    patterns = search_paths(extra_paths)
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            if not os.path.isfile(path):
                continue
            for raw in _iter_raw(path):
                if not isinstance(raw, dict) or "name" not in raw:
                    continue
                key = (raw.get("id") or "") + "|" + raw["name"].lower()
                if key in seen:
                    continue
                seen.add(key)
                try:
                    out.append(MonsterTemplate.from_raw(raw, move_library))
                except Exception:
                    continue
    b = Bestiary(out)
    b.searched = patterns
    return b


def explain_empty_bestiary(bestiary=None) -> str:
    """The game is nothing without monsters. If none were found, say exactly
    where we looked and what to do about it, rather than failing later on."""
    looked = getattr(bestiary, "searched", None) or search_paths()
    lines = [
        "",
        "  VOIDCALLER found no monsters, so there is no game to play.",
        "",
        "  It looked in:",
    ]
    for p in looked:
        lines.append(f"      {p}")
    lines += [
        "",
        "  Three ways to fix it:",
        "",
        "    1. Put your dataset inside the game, which makes it self-contained:",
        f"         mkdir -p {os.path.join(GAME_DIR, 'data', 'monsters')}",
        f"         cp /path/to/monsters.jsonl {os.path.join(GAME_DIR, 'data', 'monsters')}/",
        "",
        "    2. Point at where it already lives, and leave it there:",
        f"         edit {SOURCES_FILE}",
        '         {"monsters": ["~/wherever/monsters.jsonl"]}',
        "",
        "    3. Just for this run:",
        "         VOIDCALLER_MONSTERS=~/wherever/monsters.jsonl python3 crt.py",
        "",
        "  docs/IMPORT_EXPORT.md has the whole list of what gets read.",
        "",
    ]
    return "\n".join(lines)


def require_bestiary(bestiary) -> bool:
    """True if there is something to play with; otherwise print why not."""
    if bestiary is not None and bestiary.all:
        return True
    print(explain_empty_bestiary(bestiary))
    return False


# --- items -----------------------------------------------------------------
ITEM_BASE_VALUE = {"material": 12, "consumable": 25, "equipment": 60,
                   "weapon": 70, "armor": 70, "accessory": 55,
                   "rare": 90, "key": 0, "treasure": 45}


def build_item_catalog(bestiary: Bestiary) -> dict:
    """Every drop in the dataset becomes a sellable item, priced off the monster
    that drops it and how rarely it drops."""
    cat: dict[str, dict] = {}
    for t in bestiary.all:
        for d in list(t.drops) + list(t.steal):
            base = ITEM_BASE_VALUE.get(d.kind, 12)
            value = 0 if d.kind == "key" else max(4, int(round(
                (base + t.level * 1.4 + (1.0 - min(d.rate, 0.95)) * base) * 0.8)))
            cur = cat.get(d.item)
            if cur is None or value > cur["value"]:
                cat[d.item] = {"name": d.item, "kind": d.kind, "value": value,
                               "source": t.name, "level": t.level}
    # merge hand-written overrides / shop stock
    path = os.path.join(GAME_DIR, "data", "items.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for name, spec in json.load(f).items():
                entry = cat.setdefault(name, {"name": name, "kind": "consumable",
                                              "value": 25, "source": "Trader", "level": 1})
                entry.update(spec)
                entry["name"] = name
    return cat
