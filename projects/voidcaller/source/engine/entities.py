"""Owned creature state for the canonical six-stat combat model.

Species data lives in :mod:`engine.data`; this file owns only an individual
creature's level, HP, PP, selected moves, build choices, and equipment.  It is
intentionally the only layer that derives current combat numbers.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from . import balance as B
from .data import BASIC_ATTACK, BASIC_DODGE, BASIC_STRUGGLE, MonsterTemplate, Skill
from .model import CORE_STATS, DISPLAY_STATS


STAT_KEYS = list(DISPLAY_STATS)
# Kept only to read old saves and show a transparent migration note. Potential
# grades never modify V2 combat stats; tendency is the new individual nudge.
POTENTIAL_KEYS = tuple(CORE_STATS)
POTENTIAL_MULTIPLIERS = {"D": 1.0, "C": 1.0, "B": 1.0, "A": 1.0, "S": 1.0}
HARD_CONTROL = {"sleep", "stone", "stun"}


def _new_uid() -> str:
    return f"creature_{uuid.uuid4().hex[:16]}"


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def potential_from_seed(_seed: int) -> dict[str, str]:
    """Legacy preservation helper.

    Pre-V2 saves stored six random potential grades. We retain neutral values
    in migrated save metadata instead of rerolling or silently discarding them.
    """
    return {key: "B" for key in POTENTIAL_KEYS}


def xp_for_level(level: int) -> int:
    """Total XP needed to reach ``level`` from Level 1."""
    return B.xp_total_for_level(level)


@dataclass
class Status:
    rounds: int = 2
    amount: float = 0.0


@dataclass
class StatMod:
    stat: str
    amount: float
    rounds: int


@dataclass
class Combatant:
    template: MonsterTemplate
    level: int = 1
    xp: int = 0
    nickname: str = ""
    uid: str = field(default_factory=_new_uid)
    cur_hp: int = -1
    statuses: dict[str, Status] = field(default_factory=dict)
    mods: list[StatMod] = field(default_factory=list)
    guarding: bool = False
    is_enemy: bool = False
    fatigue: int = 0
    tendency: dict = field(default_factory=dict)
    equipment: dict = field(default_factory=dict)
    skill_pp: dict[str, int] = field(default_factory=dict)
    learned_moves: list[str] = field(default_factory=list)
    active_moves: list[str] = field(default_factory=list)
    skill_tree_state: dict[str, int] = field(default_factory=dict)
    # Legacy save metadata—preserved but no longer feeds permanent stats.
    potential_seed: int = 0
    potential: dict = field(default_factory=dict)
    legacy_skill_tree: list = field(default_factory=list)
    legacy_level: int = 0

    def __post_init__(self) -> None:
        self.uid = str(self.uid or _new_uid())
        self.level = max(1, min(B.MAX_LEVEL, _int(self.level, 1)))
        self.xp = max(0, _int(self.xp, xp_for_level(self.level)))
        self.potential = {key: str((self.potential or {}).get(key, "B")).upper()
                          for key in POTENTIAL_KEYS}
        self.skill_tree_state = {str(key): max(0, _int(value))
                                 for key, value in (self.skill_tree_state or {}).items()}
        self.learned_moves = [str(move) for move in (self.learned_moves or [])]
        self.active_moves = [str(move) for move in (self.active_moves or [])][:4]
        self.tendency = self._normalize_tendency(self.tendency)
        self.legacy_skill_tree = list(self.legacy_skill_tree or [])
        self.legacy_level = max(0, _int(self.legacy_level))
        if self.cur_hp < 0:
            self.cur_hp = self.max_hp
        else:
            self.cur_hp = max(0, min(_int(self.cur_hp), self.max_hp))

    # -- identity -----------------------------------------------------------
    @property
    def name(self) -> str:
        return self.nickname or self.template.name

    @property
    def rarity(self) -> str:
        return self.template.rarity

    @property
    def rarity_mark(self) -> str:
        from .model import RARITY_MARKS
        return RARITY_MARKS.get(self.rarity, "○")

    @property
    def rarity_color(self) -> str:
        # Rarity never owns the creature-name colour in V2. Keep a neutral
        # compatibility token while the last legacy views are removed.
        return "bright"

    @property
    def alive(self) -> bool:
        return self.cur_hp > 0

    @staticmethod
    def _normalize_tendency(raw: object) -> dict[str, str]:
        raw = raw if isinstance(raw, dict) else {}
        up = str(raw.get("up") or "").casefold()
        down = str(raw.get("down") or "").casefold()
        allowed = set(CORE_STATS)
        if up not in allowed:
            up = ""
        if down not in allowed or down == up:
            down = ""
        return {"up": up, "down": down}

    # -- base and derived stats --------------------------------------------
    def _tree_rows(self) -> list[dict]:
        rows: list[dict] = []

        def append_tree(tree: object, *, prefix: str = "", source: str = "Species") -> None:
            """Flatten a V2 species or equipped-item tree into purchasable rows.

            Equipment paths are namespaced by slot, so a weapon's `edge_01`
            node cannot collide with an armour node of the same friendly name.
            Their prerequisites are scoped with the same prefix.
            """
            def scoped(value: object) -> str:
                text = str(value or "")
                return f"{prefix}:{text}" if prefix else text

            if isinstance(tree, dict):
                for branch_index, branch in enumerate(tree.get("branches") or []):
                    if not isinstance(branch, dict):
                        continue
                    raw_branch = str(branch.get("id") or f"branch_{branch_index}")
                    branch_id = scoped(raw_branch)
                    branch_name = str(branch.get("name") or raw_branch)
                    if source != "Species":
                        branch_name = f"{source} / {branch_name}"
                    for node_index, node in enumerate(branch.get("nodes") or []):
                        if not isinstance(node, dict):
                            continue
                        row = dict(node)
                        raw_node = str(row.get("id") or f"{raw_branch}_{node_index}")
                        row["id"] = scoped(raw_node)
                        row["branch"] = branch_id
                        row["branch_name"] = branch_name
                        row["source"] = source
                        prereqs = []
                        for requirement in row.get("prerequisites") or []:
                            if not isinstance(requirement, dict):
                                continue
                            copied = dict(requirement)
                            copied["node"] = scoped(copied.get("node"))
                            prereqs.append(copied)
                        row["prerequisites"] = prereqs
                        rows.append(row)
            elif isinstance(tree, list):
                # Imported linear lists remain visible, but cannot auto-apply
                # old V1 mechanics. A player may opt into their safe stat rows.
                branch_id = scoped("legacy")
                branch_name = "Imported" if source == "Species" else f"{source} / Imported"
                for index, node in enumerate(tree):
                    if not isinstance(node, dict):
                        continue
                    row = dict(node)
                    row["id"] = scoped(row.get("id") or f"legacy_{index}")
                    row["branch"] = branch_id
                    row["branch_name"] = branch_name
                    row["source"] = source
                    row.setdefault("max_rank", 1)
                    row.setdefault("cost_per_rank", 1)
                    if "effects_per_rank" not in row:
                        effect = {"kind": "stat_pct", "stat": row.get("stat"),
                                  "amount": row.get("amount", 0)}
                        row["effects_per_rank"] = [effect] if row.get("kind", "stat") == "stat" else []
                    row.setdefault("prerequisites", [])
                    rows.append(row)

        append_tree(self.template.skill_tree)
        for slot, gear in (self.equipment or {}).items():
            if not isinstance(gear, dict) or not gear.get("skill_tree"):
                continue
            label = str(gear.get("name") or str(slot).title())
            append_tree(gear.get("skill_tree"), prefix=f"gear_{slot}", source=label)
        return rows

    def _tree_row(self, node_id: str) -> dict | None:
        return next((node for node in self._tree_rows() if str(node.get("id")) == str(node_id)), None)

    def _tree_stat_bonus(self, stat: str) -> float:
        bonus = 0.0
        for node in self._tree_rows():
            rank = max(0, _int(self.skill_tree_state.get(str(node.get("id")), 0)))
            if not rank:
                continue
            for effect in node.get("effects_per_rank") or []:
                if not isinstance(effect, dict):
                    continue
                kind = str(effect.get("kind") or "").casefold()
                target = str(effect.get("stat") or effect.get("key") or "").casefold()
                if kind in {"stat_pct", "stat"} and target == stat:
                    bonus += _float(effect.get("amount")) * rank
        return bonus

    def _tree_move_bonus(self, skill: Skill | None, kinds: set[str]) -> float:
        if skill is None:
            return 0.0
        bonus = 0.0
        for node in self._tree_rows():
            rank = max(0, _int(self.skill_tree_state.get(str(node.get("id")), 0)))
            if not rank:
                continue
            for effect in node.get("effects_per_rank") or []:
                if not isinstance(effect, dict) or str(effect.get("kind") or "").casefold() not in kinds:
                    continue
                needed_tag = str(effect.get("move_tag") or effect.get("tag") or "").casefold()
                if needed_tag and needed_tag not in skill.tags:
                    continue
                needed_type = str(effect.get("type") or "").casefold()
                if needed_type and (skill.type or "").casefold() != needed_type:
                    continue
                bonus += _float(effect.get("amount")) * rank
        return bonus

    def move_crit_bonus(self, skill: Skill | None) -> float:
        return self._tree_move_bonus(skill, {"move_crit_bonus", "crit_bonus"})

    def move_damage_bonus(self, skill: Skill | None) -> float:
        kinds = {"physical_damage_pct"} if skill and skill.category == "physical" else {"magical_damage_pct"}
        kinds.add("move_damage_pct")
        return self._tree_move_bonus(skill, kinds)

    def _equipment_stat_bonus(self, stat: str) -> float:
        total = 0.0
        for gear in (self.equipment or {}).values():
            if not isinstance(gear, dict):
                continue
            total += _float((gear.get("stats") or {}).get(stat))
        return total

    def base(self, key: str) -> float:
        if key not in CORE_STATS:
            return 1.0
        value = self.template.stat_at(key, self.level)
        value += self._equipment_stat_bonus(key)
        value *= 1.0 + self._tree_stat_bonus(key)
        if self.tendency.get("up") == key:
            value *= 1.05
        if self.tendency.get("down") == key:
            value *= 0.95
        return max(1.0, value)

    @property
    def max_hp(self) -> int:
        return max(B.HP_FLOOR, int(round(self.base("hp"))))

    def modifier(self, key: str) -> float:
        """Additive temporary modifier such as ``accuracy`` or ``evasion``."""
        return sum(mod.amount for mod in self.mods if mod.stat == key)

    def stat(self, key: str) -> float:
        if key not in CORE_STATS:
            return 1.0
        value = self.base(key)
        value *= 1.0 + self.modifier(key)
        if key == "spd" and "slow" in self.statuses:
            value *= B.SLOW_FACTOR
        if key == "spd" and "haste" in self.statuses:
            value *= B.HASTE_FACTOR
        return max(1.0, value)

    def power_stat(self, skill: Skill) -> float:
        return self.stat("mag" if skill.is_magical else "atk")

    def guard_stat(self, skill: Skill) -> float:
        value = self.stat("res" if skill.is_magical else "def")
        if any(status in self.statuses for status in HARD_CONTROL):
            value *= 0.65
        return value

    def speed(self) -> float:
        return self.stat("spd")

    def resist_factor(self, status: str) -> float:
        tag = str((self.template.resist or {}).get(status, "normal")).casefold()
        return B.STATUS_RESIST_FACTOR.get(tag, 1.0)

    # Retired MP API: external legacy screens may call it during migration, but
    # it stores no resource and cannot affect a turn.
    @property
    def max_mp(self) -> int:
        return 0

    @property
    def cur_mp(self) -> int:
        return 0

    @cur_mp.setter
    def cur_mp(self, _value: object) -> None:
        pass

    def restore_mp(self, _amount: int) -> int:
        return 0

    def accuracy_stat(self) -> float:
        return 100.0

    def evade_stat(self) -> float:
        return 0.0

    def crit_rate(self) -> float:
        return B.BASE_CRIT

    def potential_grade(self, _key: str) -> str:
        """Compatibility view for old saves; V2 potential is neutral metadata."""
        return "B"

    # -- skill tree ---------------------------------------------------------
    @property
    def skill_points_total(self) -> int:
        return max(0, (self.level - 1) * B.SKILL_POINTS_PER_LEVEL)

    @property
    def skill_points_spent(self) -> int:
        total = 0
        for node in self._tree_rows():
            rank = max(0, _int(self.skill_tree_state.get(str(node.get("id")), 0)))
            total += rank * max(1, _int(node.get("cost_per_rank"), 1))
        return total

    @property
    def skill_points(self) -> int:
        return max(0, self.skill_points_total - self.skill_points_spent)

    def _requirements_met(self, node: dict) -> bool:
        for requirement in node.get("prerequisites") or []:
            if not isinstance(requirement, dict):
                continue
            needed = max(1, _int(requirement.get("rank"), 1))
            if _int(self.skill_tree_state.get(str(requirement.get("node")), 0)) < needed:
                return False
        return True

    def purchase_skill_node(self, node_id: str) -> tuple[bool, str]:
        node = self._tree_row(node_id)
        if node is None:
            return False, "Unknown skill node."
        ident = str(node.get("id"))
        current = _int(self.skill_tree_state.get(ident, 0))
        maximum = max(1, _int(node.get("max_rank"), 1))
        cost = max(1, _int(node.get("cost_per_rank"), 1))
        if current >= maximum:
            return False, "That node is already at its maximum rank."
        if not self._requirements_met(node):
            return False, "Its prerequisite rank has not been purchased."
        if self.skill_points < cost:
            return False, "Not enough Skill Points."
        self.skill_tree_state[ident] = current + 1
        return True, f"{node.get('name', 'Node')} is now rank {current + 1}."

    def skill_tree_nodes(self) -> list[dict]:
        return [node for node in self._tree_rows()
                if _int(self.skill_tree_state.get(str(node.get("id")), 0)) > 0]

    def skill_tree_view(self) -> list[dict]:
        rows = []
        for node in self._tree_rows():
            ident = str(node.get("id"))
            rank = _int(self.skill_tree_state.get(ident, 0))
            maximum = max(1, _int(node.get("max_rank"), 1))
            cost = max(1, _int(node.get("cost_per_rank"), 1))
            rows.append({
                "id": ident, "name": str(node.get("name") or "Untitled node"),
                "branch": str(node.get("branch") or "core"),
                "branch_name": str(node.get("branch_name") or node.get("branch") or "Core"),
                "source": str(node.get("source") or "Species"),
                "rank": rank, "max_rank": maximum, "cost_per_rank": cost,
                "prerequisites": list(node.get("prerequisites") or []),
                "keystone": bool(node.get("keystone")),
                "effects_per_rank": list(node.get("effects_per_rank") or []),
                "unlocked": rank > 0,
                "can_buy": rank < maximum and self._requirements_met(node) and self.skill_points >= cost,
                "description": str(node.get("description") or ""),
            })
        return rows

    # -- moves and PP -------------------------------------------------------
    @staticmethod
    def _skill_key(skill: Skill) -> str:
        return skill.id

    def _tree_moves(self) -> list[Skill]:
        found = []
        for node in self.skill_tree_nodes():
            for effect in node.get("effects_per_rank") or []:
                if not isinstance(effect, dict) or str(effect.get("kind", "")).casefold() not in {"unlock_move", "move"}:
                    continue
                raw = effect.get("move") or effect.get("value")
                if isinstance(raw, dict):
                    move = Skill.from_raw(raw)
                    if all(old.id != move.id for old in found):
                        found.append(move)
        return found

    @property
    def skills(self) -> list[Skill]:
        learned = self.template.moves_at_level(self.level) + self._tree_moves()
        seen: set[str] = set()
        learned = [move for move in learned if not (move.id in seen or seen.add(move.id))]
        if self.learned_moves:
            learned = [move for move in learned if move.id in self.learned_moves]
        if self.active_moves:
            selected = [move for move in learned if move.id in self.active_moves]
            if selected:
                learned = selected
        if not any(move.is_damage for move in learned):
            learned.insert(0, BASIC_ATTACK)
        if not any(move.category == "support" for move in learned):
            learned.append(BASIC_DODGE)
        return learned[:4]

    def pp_left(self, skill: Skill) -> int:
        maximum = max(0, _int(skill.pp))
        if maximum <= 0:
            return 0
        value = self.skill_pp.get(skill.id)
        if value is None:
            # Legacy saves keyed PP by a composite display string. Match on the
            # name prefix once, then V2 writes the stable move ID.
            prefix = skill.name.casefold() + "|"
            value = next((old for key, old in self.skill_pp.items()
                          if str(key).casefold().startswith(prefix)), maximum)
        return max(0, min(maximum, _int(value, maximum)))

    def spend_pp(self, skill: Skill) -> None:
        if skill.pp > 0:
            self.skill_pp[skill.id] = max(0, self.pp_left(skill) - 1)

    def restore_pp(self, amount: int, skill_id: str | None = None) -> int:
        """Restore PP to one move, or the first depleted move."""
        amount = max(0, _int(amount))
        choices = [move for move in self.skills if move.pp > 0]
        if skill_id:
            choices = [move for move in choices if move.id == skill_id]
        target = next((move for move in choices if self.pp_left(move) < move.pp), None)
        if target is None:
            return 0
        before = self.pp_left(target)
        self.skill_pp[target.id] = min(target.pp, before + amount)
        return self.skill_pp[target.id] - before

    def can_cast(self, skill: Skill) -> bool:
        if "silence" in self.statuses and skill.category == "magical":
            return False
        return skill.pp <= 0 or self.pp_left(skill) > 0

    def usable_skills(self) -> list[Skill]:
        moves = [move for move in self.skills if self.can_cast(move)]
        if not any(move.is_damage for move in moves):
            moves.append(BASIC_STRUGGLE)
        return moves or [BASIC_STRUGGLE]

    # -- battle state -------------------------------------------------------
    def damage(self, amount: int) -> int:
        amount = max(0, _int(amount))
        self.cur_hp = max(0, self.cur_hp - amount)
        return amount

    def heal(self, amount: int) -> int:
        amount = max(0, _int(amount))
        before = self.cur_hp
        self.cur_hp = min(self.max_hp, self.cur_hp + amount)
        return self.cur_hp - before

    def full_heal(self) -> None:
        self.cur_hp = self.max_hp
        self.skill_pp.clear()
        self.statuses.clear()
        self.mods.clear()

    def clear_battle_state(self) -> None:
        self.mods.clear()
        self.guarding = False
        for status in ("shield", "regen", "haste"):
            self.statuses.pop(status, None)

    def add_status(self, key: str, rounds: int, amount: float = 0.0) -> bool:
        key = str(key).casefold()
        rounds = max(1, _int(rounds, 1))
        if key in HARD_CONTROL:
            other = next((status for status in HARD_CONTROL if status != key and status in self.statuses), None)
            if other:
                return False
        current = self.statuses.get(key)
        if current:
            current.rounds = max(current.rounds, rounds)
            current.amount = max(current.amount, _float(amount))
            return True
        self.statuses[key] = Status(rounds, _float(amount))
        return True

    def add_mod(self, stat: str, amount: float, rounds: int) -> None:
        stat = str(stat).casefold()
        if stat not in {*CORE_STATS, "accuracy", "evasion"}:
            return
        self.mods.append(StatMod(stat, _float(amount), max(1, _int(rounds, 1))))

    def tick_mods(self) -> None:
        for mod in self.mods:
            mod.rounds -= 1
        self.mods = [mod for mod in self.mods if mod.rounds > 0]

    # -- progression --------------------------------------------------------
    @property
    def xp_span(self) -> int:
        return max(1, B.xp_required_for_next(self.level)) if self.level < B.MAX_LEVEL else 1

    @property
    def xp_done(self) -> int:
        return max(0, self.xp - xp_for_level(self.level))

    @property
    def xp_to_next(self) -> int:
        return max(0, xp_for_level(self.level + 1) - self.xp) if self.level < B.MAX_LEVEL else 0

    def gain_xp(self, amount: int) -> list[int]:
        if self.level >= B.MAX_LEVEL:
            return []
        self.xp += max(0, _int(amount))
        gained = []
        while self.level < B.MAX_LEVEL and self.xp >= xp_for_level(self.level + 1):
            previous_hp = self.max_hp
            self.level += 1
            self.cur_hp += self.max_hp - previous_hp
            gained.append(self.level)
        return gained

    @property
    def power(self) -> int:
        raw = (self.max_hp * 0.45 + (self.stat("atk") + self.stat("mag")) * 1.2
               + (self.stat("def") + self.stat("res")) * 0.85 + self.stat("spd") * 1.35
               + max((skill.power for skill in self.skills), default=20) * 0.8)
        return int(round(raw))

    # -- save/load ----------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "uid": self.uid, "species_id": self.template.id, "template": self.template.id,
            "level": self.level, "current_xp": self.xp, "xp": self.xp,
            "nickname": self.nickname, "current_hp": self.cur_hp, "cur_hp": self.cur_hp,
            "move_pp": dict(self.skill_pp), "skill_pp": dict(self.skill_pp),
            "learned_moves": list(self.learned_moves), "active_moves": list(self.active_moves),
            "equipment": self.equipment, "skill_tree": dict(self.skill_tree_state),
            "tendency": dict(self.tendency),
            "legacy_potential": {"seed": self.potential_seed, "grades": self.potential},
            "legacy_skill_tree": list(self.legacy_skill_tree),
            "legacy_level": self.legacy_level,
        }

    @classmethod
    def from_dict(cls, data: dict, bestiary) -> "Combatant | None":
        data = data if isinstance(data, dict) else {}
        template = bestiary.get(data.get("species_id") or data.get("template") or "")
        if template is None:
            return None
        legacy = data.get("legacy_potential") if isinstance(data.get("legacy_potential"), dict) else {}
        pp = data.get("move_pp") or data.get("skill_pp") or {}
        tree = data.get("skill_tree") or data.get("skill_tree_state") or {}
        current_hp = data.get("current_hp", data.get("cur_hp", -1))
        creature = cls(
            template=template, uid=data.get("uid") or _new_uid(),
            level=max(1, min(B.MAX_LEVEL, _int(data.get("level"), 1))),
            xp=max(0, _int(data.get("current_xp", data.get("xp", 0)))),
            nickname=str(data.get("nickname") or ""), cur_hp=_int(current_hp, -1),
            equipment=dict(data.get("equipment") or {}),
            skill_pp={str(key): _int(value) for key, value in pp.items()},
            learned_moves=[str(move) for move in (data.get("learned_moves") or [])],
            active_moves=[str(move) for move in (data.get("active_moves") or [])],
            skill_tree_state=dict(tree) if isinstance(tree, dict) else {},
            tendency=dict(data.get("tendency") or {}),
            potential_seed=_int(legacy.get("seed", data.get("potential_seed", 0))),
            potential=dict(legacy.get("grades", data.get("potential") or {})),
            legacy_skill_tree=list(data.get("legacy_skill_tree") or
                                   (data.get("skill_tree") if isinstance(data.get("skill_tree"), list) else [])),
            legacy_level=_int(data.get("legacy_level", 0)),
        )
        # V5 did not persist a useful stable UID or source max HP. If it did
        # include one, preserve the health percentage instead of silently
        # treating an old raw HP value as a V2 value.
        old_max = _int(data.get("max_hp"), 0)
        if old_max > 0 and current_hp is not None:
            creature.cur_hp = max(0, min(creature.max_hp,
                int(round(creature.max_hp * max(0, _int(current_hp)) / old_max))))
        return creature


def spawn(template: MonsterTemplate, level: int | None = None, enemy: bool = False) -> Combatant:
    """Create an encounter or an owned creature.

    Summoned/starting creatures default to Level 1. Callers that capture a
    wild creature may pass its encounter Level explicitly; enemies default to
    their species' recommended area level.
    """
    if level is None:
        level = template.level if enemy else 1
    level = max(1, min(B.MAX_LEVEL, _int(level, 1)))
    return Combatant(template=template, level=level, xp=xp_for_level(level), is_enemy=enemy)
