"""
Only one creature from each side is on the field at a time. A chosen move is
followed by the wild creature's response; when a creature falls, the next
healthy companion is sent out automatically (or selected from Switch). This
keeps fights legible even after the player has a full party.
"""
from __future__ import annotations

from . import balance as B
from . import formula as F
from . import rules
from .data import BASIC_STRUGGLE
from .entities import Combatant


def _sprite_for(template) -> str:
    """The creature's 16px PNG path, written on demand.

    One definition shared by the snapshot and the target list. They used to
    build their dicts separately and only one of them carried the art.
    """
    from . import v2_art
    return v2_art.write_monster(template.id, template.portrait_seed, template.primary,
                                getattr(template, "sprite_archetype", "Core"))


def _portrait_for(template) -> list:
    """The ASCII sigil, kept for terminals that cannot draw pixels."""
    from . import portraits
    return portraits.for_template(template)


class Battle:
    def __init__(self, party: list[Combatant], enemies: list[Combatant],
                 title: str = "BATTLE", allow_flee: bool = True, auto: bool = False):
        self.party = list(party)
        # V2's battle promise is one active creature versus one active enemy.
        # Areas now build a single encounter; slicing here makes old group data
        # degrade safely instead of silently turning into a multi-target fight.
        self.enemies = list(enemies[:1])
        self.title = title
        self.allow_flee = allow_flee and not any(e.template.is_boss for e in self.enemies)
        self.auto = auto
        self.round = 0
        self.finished = False
        self.outcome = ""            # win | lose | draw | flee | capture
        self.rewards: dict = {}
        self.waiting_uid: str | None = None
        self.events: list[dict] = []
        self.active_party_uid = next((c.uid for c in party if c.alive), None)
        self.active_enemy_uid = next((c.uid for c in self.enemies if c.alive), None)
        for c in self.party + self.enemies:
            c.clear_battle_state()
            c._down_announced = not c.alive
        for c in party:
            c._voidcaller_active_battle = True

    # -- active creatures ---------------------------------------------------
    @property
    def everyone(self) -> list[Combatant]:
        return self.party + self.enemies

    def by_uid(self, uid: str | None) -> Combatant | None:
        return next((c for c in self.everyone if c.uid == uid), None)

    @property
    def waiting(self) -> Combatant | None:
        return self.by_uid(self.waiting_uid)

    @property
    def active_party(self) -> Combatant | None:
        return self.by_uid(self.active_party_uid)

    @property
    def active_enemy(self) -> Combatant | None:
        return self.by_uid(self.active_enemy_uid)

    @staticmethod
    def alive(group) -> list[Combatant]:
        return [c for c in group if c.alive]

    def _next_party(self, out: list[dict], announced: bool = True) -> Combatant | None:
        current = self.active_party
        if current and current.alive:
            return current
        nxt = next((c for c in self.party if c.alive), None)
        self.active_party_uid = nxt.uid if nxt else None
        if nxt and announced:
            out.append(rules.ev("switch", side="party", who=nxt.name, uid=nxt.uid,
                                reason="sent out"))
        return nxt

    def _next_enemy(self, out: list[dict]) -> Combatant | None:
        current = self.active_enemy
        if current and current.alive:
            return current
        nxt = next((c for c in self.enemies if c.alive), None)
        self.active_enemy_uid = nxt.uid if nxt else None
        if nxt:
            out.append(rules.ev("switch", side="enemy", who=nxt.name, uid=nxt.uid,
                                reason="appeared"))
        return nxt

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> list[dict]:
        first = [rules.ev("battle_start", title=self.title,
                          enemies=[e.name for e in self.enemies],
                          quote=next((e.template.quote for e in self.enemies
                                      if e.template.quote), ""))]
        if self.active_party:
            first.append(rules.ev("switch", side="party", who=self.active_party.name,
                                  uid=self.active_party.uid, reason="sent out"))
        if self.active_enemy:
            first.append(rules.ev("switch", side="enemy", who=self.active_enemy.name,
                                  uid=self.active_enemy.uid, reason="appeared"))
        self.events = list(first)
        return first + self._begin_round()

    def advance(self) -> list[dict]:
        """Advance a non-interactive legacy battle loop one step.

        The CRT client drives a battle through :meth:`act`, but the original
        text-mode client still asks the battle to progress whenever no player
        decision is pending.  Keeping this tiny bridge means both front ends
        use the same V2 rules rather than maintaining a second combat engine.
        """
        if self.finished or self.waiting is not None:
            return []
        return self._begin_round()

    def _check_end(self, out: list[dict]) -> bool:
        party_up = bool(self.alive(self.party))
        foes_up = bool(self.alive(self.enemies))
        if party_up and foes_up:
            return False
        self.finished = True
        self.waiting_uid = None
        if party_up and not foes_up:
            self.outcome = "win"
            self.rewards = rules.battle_rewards(self.enemies)
        elif foes_up and not party_up:
            self.outcome = "lose"
        else:
            self.outcome = "draw"
            for c in self.party:
                if c.cur_hp <= 0:
                    c.cur_hp = 1
        out.append(rules.ev("end", result=self.outcome, rewards=self.rewards,
                            rounds=self.round))
        for c in self.party:
            c.clear_battle_state()
            c._voidcaller_active_battle = False
        return True

    def _clear_party_battle_state(self) -> None:
        for creature in self.party:
            creature.clear_battle_state()
            creature._voidcaller_active_battle = False

    def _begin_round(self) -> list[dict]:
        out: list[dict] = []
        if self._check_end(out):
            self.events += out
            return out
        player = self._next_party(out)
        enemy = self._next_enemy(out)
        if player is None or enemy is None or self._check_end(out):
            self.events += out
            return out
        self.round += 1
        player.guarding = False
        for foe in self.alive(self.enemies):
            foe.guarding = False
        out.append(rules.ev("round", n=self.round,
                            order=[],
                            field=[self._field_row(player), self._field_row(enemy)]))
        reason = rules.skip_reason(player)
        if reason:
            out.append(rules.ev("skip", who=player.name, uid=player.uid, reason=reason))
            out += rules.tick_statuses(player)
            if self._check_end(out):
                self.events += out
                return out
            out += self._enemy_response()
            self.events += out
            return out
        self.waiting_uid = player.uid
        self.events += out
        return out

    @staticmethod
    def _field_row(c: Combatant) -> dict:
        return {"uid": c.uid, "name": c.name, "level": c.level,
                "side": rules.side(c), "hp": c.cur_hp, "max_hp": c.max_hp,
                "alive": c.alive, "type": c.template.primary,
                "secondary": c.template.secondary,
                "statuses": sorted(c.statuses), "rarity": c.rarity,
                "rarity_mark": c.rarity_mark, "rarity_color": c.rarity_color}

    def _enemy_response(self) -> list[dict]:
        out: list[dict] = []
        enemy = self._next_enemy(out)
        player = self._next_party(out)
        if enemy is None or player is None or self._check_end(out):
            return out
        reason = rules.skip_reason(enemy)
        if reason:
            out.append(rules.ev("skip", who=enemy.name, uid=enemy.uid, reason=reason))
        else:
            skill, target = rules.ai_choose(enemy, [enemy], [player])
            out += rules.take_turn(enemy, [enemy], [player], skill, target)
        out += rules.tick_statuses(enemy)
        if self._check_end(out):
            return out
        self._next_party(out)
        if self._check_end(out):
            return out
        return out + self._begin_round()

    def _resolve_exchange(self, player: Combatant, player_skill, player_target) -> list[dict]:
        """Resolve one selected player move against the enemy's chosen move.

        Both intents are selected before either effect runs, then strict move
        priority, effective SPD, and an unbiased tie-break decide the order.
        """
        out: list[dict] = []
        enemy = self._next_enemy(out)
        if enemy is None or self._check_end(out):
            return out
        enemy_skill, enemy_target = rules.ai_choose(enemy, [enemy], [player])
        intents = [
            (player, player_skill, player_target, [player], [enemy]),
            (enemy, enemy_skill, enemy_target, [enemy], [player]),
        ]
        sorted_actions = F.action_order([(actor, skill) for actor, skill, *_ in intents])
        out.append(rules.ev("turn_order", n=self.round, order=[
            {"uid": actor.uid, "name": actor.name, "side": rules.side(actor),
             "priority": skill.priority, "speed": round(actor.speed(), 1)}
            for actor, skill in sorted_actions]))
        intent_by_uid = {actor.uid: (actor, skill, target, allies, foes)
                         for actor, skill, target, allies, foes in intents}
        for actor, _skill in sorted_actions:
            actor, skill, target, allies, foes = intent_by_uid[actor.uid]
            if not actor.alive or self._check_end(out):
                continue
            reason = rules.skip_reason(actor)
            if reason:
                out.append(rules.ev("skip", who=actor.name, uid=actor.uid, reason=reason))
                continue
            out.extend(rules.take_turn(actor, allies, foes, skill, target))
            if self._check_end(out):
                break
        if not self.finished:
            for creature in (player, enemy):
                if creature.alive:
                    out.extend(rules.tick_statuses(creature))
            if self._check_end(out):
                return out
            self._next_party(out)
            self._next_enemy(out)
            if not self._check_end(out):
                out.extend(self._begin_round())
        return out

    # -- decisions ----------------------------------------------------------
    def options(self) -> dict:
        actor, foe = self.waiting, self.active_enemy
        live_foes = self.alive(self.enemies)
        if actor is None or foe is None:
            return {}
        target = self.active_enemy
        can_capture = bool(target and target.alive and not target.template.is_boss)
        return {
            "uid": actor.uid, "name": actor.name,
            "hp": actor.cur_hp, "max_hp": actor.max_hp,
            "xp": actor.xp, "xp_next": actor.xp_to_next, "level": actor.level,
            "xp_span": actor.xp_span, "xp_done": actor.xp_done,
            "moves": rules.move_options(actor, [foe]),
            "can_flee": self.allow_flee,
            "flee_chance": F.flee_chance([actor], [foe]) if self.allow_flee else 0,
            "can_capture": can_capture,
            "capture_chance": self.capture_chance() if can_capture else 0.0,
            # A target row is drawn as a full creature card, so it needs the
            # creature's art as well as its numbers.  Without these the enemy
            # side of a fight rendered as a bare "." while the ally showed its
            # sprite, because the ally card reads the richer snapshot dict.
            "targets": [{"uid": target.uid, "name": target.name, "hp": target.cur_hp,
                         "max_hp": target.max_hp, "level": target.level,
                         "rarity": target.rarity, "rarity_mark": target.rarity_mark,
                         "rarity_color": target.rarity_color,
                         "active": target.uid == self.active_enemy_uid,
                         "role": target.template.role, "type": target.template.primary,
                         "portrait": _portrait_for(target.template),
                         "sprite_asset": _sprite_for(target.template),
                         "statuses": sorted(target.statuses)} for target in live_foes],
            "allies": [{"uid": a.uid, "name": a.name, "hp": a.cur_hp,
                        "max_hp": a.max_hp, "alive": a.alive,
                        "active": a.uid == self.active_party_uid,
                        "statuses": sorted(a.statuses)} for a in self.party],
            "bench": [{"uid": a.uid, "name": a.name, "hp": a.cur_hp,
                       "max_hp": a.max_hp, "alive": a.alive,
                       "level": a.level} for a in self.party if a.uid != actor.uid],
        }

    def act(self, action: str, skill_index: int | None = None,
            target_uid: str | None = None) -> list[dict]:
        actor = self.waiting
        if actor is None or self.finished:
            return []
        out: list[dict] = []
        self.waiting_uid = None

        if action == "switch":
            target = next((a for a in self.party if a.uid == target_uid and a.alive), None)
            if target is None or target.uid == actor.uid:
                self.waiting_uid = actor.uid
                return []
            self.active_party_uid = target.uid
            out.append(rules.ev("switch", side="party", who=target.name, uid=target.uid,
                                reason="called out"))
        elif action == "flee":
            out += self._flee(actor)
            if self.finished:
                self.events += out
                return out
        else:
            live_foes = self.alive(self.enemies)
            foe = next((e for e in live_foes if e.uid == target_uid), self.active_enemy)
            if foe is None:
                return out
            # Choosing a card makes that creature the field target and the
            # next creature to answer.  That keeps multi-enemy encounters as
            # readable as a Pokémon battle while still permitting selection.
            self.active_enemy_uid = foe.uid
            if action == "auto":
                skill, target = rules.ai_choose(actor, [actor], live_foes)
            elif action == "guard":
                skill, target = rules.GUARD, None
            else:
                skills = actor.skills
                index = 0 if skill_index is None else max(0, min(len(skills), skill_index))
                skill = BASIC_STRUGGLE if index >= len(skills) else skills[index]
                if not actor.can_cast(skill):
                    skill = BASIC_STRUGGLE
                target = actor if skill.is_friendly else foe
            out += self._resolve_exchange(actor, skill, target)
            self.events += out
            return out

        out += self._enemy_response()
        self.events += out
        return out

    def _flee(self, actor: Combatant) -> list[dict]:
        if not self.allow_flee:
            self.waiting_uid = actor.uid
            return [rules.ev("note", text="There is no running from this one.")]
        foe = self.active_enemy
        pct = F.flee_chance([actor], [foe] if foe else [])
        ok = F.happens(pct)
        out = [rules.ev("flee", who=actor.name, chance=pct, success=ok)]
        if ok:
            self.finished = True
            self.outcome = "flee"
            out.append(rules.ev("end", result="flee", rewards={}, rounds=self.round))
            for c in self.party:
                c.clear_battle_state()
                c._voidcaller_active_battle = False
        return out

    def capture_chance(self) -> float:
        """A readable health-and-status capture chance for the active wild.

        The authored ``capture_rate`` is a species baseline, while weakening a
        creature contributes the larger part of the final chance.  It remains
        deliberately bounded so a full-health throw can work but is never the
        best answer, and a one-HP wild can still escape.
        """
        target = self.active_enemy
        if target is None or not target.alive or target.template.is_boss:
            return 0.0
        try:
            rate = float(target.template.capture_rate)
        except (TypeError, ValueError):
            rate = 0.25
        health = target.cur_hp / max(1, target.max_hp)
        chance = max(0.05, min(0.95, rate * (0.55 + 2.2 * (1.0 - health))))
        if any(status in target.statuses for status in ("sleep", "stone", "stun")):
            chance *= 1.25
        elif target.statuses:
            chance *= 1.1
        return round(max(5.0, min(95.0, chance * 100.0)), 1)

    def capture(self, game) -> list[dict]:
        """Attempt to bind the active wild into the player's roster.

        Capture is a real turn: a failed seal gives the wild an immediate
        response.  Bosses and full rosters are explained without consuming a
        turn, so the player never loses a round to a hidden rule.
        """
        actor, target = self.waiting, self.active_enemy
        if actor is None or target is None or self.finished:
            return []
        if target.template.is_boss:
            return [rules.ev("note", text="Boss creatures cannot be bound in the field.")]
        if len(getattr(game, "roster", [])) >= B.ROSTER_CAP:
            return [rules.ev("note", text="Your roster is full. Release a companion before binding another.")]

        chance = self.capture_chance()
        self.waiting_uid = None
        success = F.happens(chance)
        out = [rules.ev("capture", actor=actor.name, actor_uid=actor.uid,
                        target=target.name, target_uid=target.uid,
                        chance=chance, success=success)]
        if success:
            caught = game.add_monster(target.template, target.level)
            if caught is not None:
                self.finished = True
                self.outcome = "capture"
                self.rewards = {"xp": 0, "gold": 0, "shards": 0, "loot": [],
                                "captured": {"uid": caught.uid, "name": caught.name,
                                             "species": caught.template.id,
                                             "level": caught.level}}
                out.append(rules.ev("end", result="capture", rewards=self.rewards,
                                    rounds=self.round))
                self._clear_party_battle_state()
                self.events += out
                return out
            # A race is unlikely in a single-player session, but it must not
            # silently grant a successful capture with nowhere to put it.
            out[-1]["success"] = False
            out.append(rules.ev("note", text="The seal cannot find room in your roster."))

        out += self._enemy_response()
        self.events += out
        return out

    def use_item(self, game, name: str, target_uid: int | None) -> list[dict]:
        actor = self.waiting
        spec = (game.items.get(name) or {}).get("use")
        if actor is None or not spec or game.count(name) <= 0:
            return []
        target = next((c for c in self.party if c.uid == target_uid), None) or actor
        game.consume(name)
        self.waiting_uid = None
        out = [rules.ev("item", name=name, target=target.name, target_uid=target.uid)]
        if spec.get("flee"):
            self.finished = True
            self.outcome = "flee"
            out.append(rules.ev("end", result="flee", rewards={}, rounds=self.round))
            self.events += out
            return out
        if "heal_pct" in spec:
            got = target.heal(int(target.max_hp * spec["heal_pct"]))
            out.append(rules.ev("heal", target=target.name, target_uid=target.uid,
                                amount=got, hp=target.cur_hp, max_hp=target.max_hp))
        if "pp_restore" in spec:
            restored = target.restore_pp(int(spec["pp_restore"]))
            if restored:
                out.append(rules.ev("pp_restore", target=target.name, target_uid=target.uid,
                                    amount=restored))
        if spec.get("cleanse"):
            target.statuses.clear()
            out.append(rules.ev("cleanse", target=target.name, target_uid=target.uid,
                                what="all"))
        if "revive_pct" in spec:
            target.cur_hp = max(target.cur_hp, int(target.max_hp * spec["revive_pct"]))
            target._down_announced = False
            out.append(rules.ev("revive", target=target.name, target_uid=target.uid,
                                hp=target.cur_hp))
        if "buff" in spec:
            stat, amount, rounds = spec["buff"]
            target.add_mod(stat, amount, rounds)
            out.append(rules.ev("stat", target=target.name, target_uid=target.uid,
                                stat=stat, amount=amount, rounds=rounds))
        out += rules.tick_statuses(actor)
        if not self._check_end(out):
            out += self._enemy_response()
        self.events += out
        return out

    # -- presentation -------------------------------------------------------
    def upcoming(self, limit: int = 2) -> list[dict]:
        out = []
        if self.waiting:
            out.append({"uid": self.waiting.uid, "name": self.waiting.name,
                        "side": "party", "now": True})
        foe = self.active_enemy
        if foe and foe.alive:
            out.append({"uid": foe.uid, "name": foe.name, "side": "enemy", "now": not out})
        return out[:limit]

    def snapshot(self) -> dict:
        from . import elements as EL

        def unit(c: Combatant, known: bool = True) -> dict:
            d = {"uid": c.uid, "name": c.name, "species": c.template.name,
                 "level": c.level, "hp": c.cur_hp, "max_hp": c.max_hp,
                 "alive": c.alive,
                 "rarity": c.rarity, "rarity_mark": c.rarity_mark,
                 "rarity_color": c.rarity_color,
                 "role": c.template.role, "type": c.template.primary,
                 "secondary": c.template.secondary, "family": c.template.family,
                 "guarding": c.guarding, "active": c.uid in (self.active_party_uid,
                                                                 self.active_enemy_uid),
                 "statuses": [{"key": k, "rounds": v.rounds} for k, v in c.statuses.items()],
                 "xp": c.xp, "xp_next": c.xp_to_next, "xp_span": c.xp_span,
                 "xp_done": c.xp_done, "acting": c.uid == self.waiting_uid,
                 "skill_tree": c.skill_tree_view(),
                 "portrait": _portrait_for(c.template),
                 "sprite_asset": _sprite_for(c.template)}
            if known:
                d["weak"] = [{"element": e, "mult": m} for e, m in EL.weaknesses(c)[:3]]
            return d

        return {"title": self.title, "round": self.round, "finished": self.finished,
                "outcome": self.outcome, "rewards": self.rewards,
                "party": [unit(c) for c in self.party],
                "enemies": [unit(c) for c in self.enemies],
                "waiting": self.waiting_uid, "order": self.upcoming(),
                "options": self.options(), "auto": self.auto,
                "active_party": self.active_party_uid, "active_enemy": self.active_enemy_uid}
