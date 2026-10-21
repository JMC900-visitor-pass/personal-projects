#!/usr/bin/env python3
"""Compatibility entry point for the current V2 acceptance check.

    python3 tools/selftest.py

The original simulation below is retained as V1 investigation history. Its
assumptions (MP, multi-creature fights, affinity overrides, old story data)
are intentionally incompatible with the PP-only V2 engine. The command now
runs the focused V2 acceptance suite instead.
"""
from __future__ import annotations

import os
import json
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import balance as B
from engine import combat, quests, shop, story, summon, team, ui, void
from engine.data import load_bestiary
from engine.entities import spawn
from engine.state import Game

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


class Script:
    """Feeds scripted answers to ui.menu / ui.ask / ui.confirm."""
    BUDGET = 300

    def __init__(self, answers):
        self.answers = list(answers)
        self.asked = 0

    def menu(self, title, options, back="back", allow_back=True):
        self.asked += 1
        return self._next(-1 if allow_back else 0)

    def ask(self, prompt, default=""):
        self.asked += 1
        v = self._next(default)
        return str(v)

    def confirm(self, prompt):
        self.asked += 1
        return bool(self._next(False))

    def _next(self, fallback):
        if self.asked > self.BUDGET:
            raise RuntimeError("screen never handed control back (input loop)")
        return self.answers.pop(0) if self.answers else fallback


def with_script(answers):
    s = Script(answers)
    ui.menu, ui.ask, ui.confirm, ui.pause = s.menu, s.ask, s.confirm, lambda *a, **k: None
    return s


# ---------------------------------------------------------------------------
def test_load(bestiary):
    check("bestiary loads", len(bestiary) > 20, f"{len(bestiary)} species")
    bad = [t.name for t in bestiary.all if not (t.base_moves + t.skills)]
    check("every monster has a move", not bad, str(bad[:3]))
    dmg = [s for t in bestiary.all for s in t.base_moves + t.skills if s.is_damage]
    check("damage skills carry real power", all(s.power > 0 for s in dmg), f"{len(dmg)} skills")
    tricky = [t for t in bestiary.all
              if any(s.power > 0 and s.kind in ("physical", "magical")
                     and s.target in ("self", "all_allies") for s in t.base_moves + t.skills)]
    check("no damage skill aimed at its own team", not tricky, str([t.name for t in tricky][:3]))


def test_battles(bestiary, n=300):
    """Fair fight: same level both sides. A coin-flip means the maths is even."""
    ui.QUIET = True
    wins, rounds, lengths = 0, [], []
    for _ in range(n):
        lvl = random.randint(3, 30)
        pool = [t for t in bestiary.all if not t.is_boss]
        party = [spawn(random.choice(pool), lvl) for _ in range(4)]
        foes = [spawn(random.choice(pool), lvl, enemy=True) for _ in range(random.randint(2, 4))]
        res = combat.battle(party, foes, auto=True, allow_flee=False, title="sim")
        wins += bool(res.won)
        rounds.append(res.rounds)
        lengths.append(res.rounds)
    ui.QUIET = False
    wr = wins / n
    med = statistics.median(rounds)
    check("even fights are near a coin-flip", 0.35 <= wr <= 0.80, f"party win rate {wr:.0%}")
    check("fights are 2-12 rounds", 2 <= med <= 12, f"median {med} rounds, max {max(rounds)}")
    stuck = sum(1 for r in rounds if r >= B.MAX_ROUNDS)
    check("no unkillable stalemates", stuck == 0, f"{stuck} fights hit the round cap")


def test_progression(bestiary):
    ui.QUIET = True
    g = Game(bestiary)
    for t in bestiary.starters(3):
        g.add_monster(t)
    start_power = sum(m.power for m in g.party)
    fights = 0
    for _ in range(25):
        lvl = max(1, sum(m.level for m in g.party) // len(g.party))
        foes = void.build_encounter(g, random.choice(bestiary.habitats()), lvl)
        res = combat.battle(g.party, foes, game=g, auto=True, allow_flee=False, title="sim")
        fights += 1
        if res.won:
            for m in g.party:
                m.gain_xp(res.xp)
            for item in res.loot:
                g.add_item(item)
            g.gold += res.gold
            g.shards += res.shards
            for f in foes:
                if not f.alive:
                    g.record_kill(f.template)
        for m in g.roster:
            m.full_heal()
    ui.QUIET = False
    end_level = max(m.level for m in g.party)
    check("the pack levels up by fighting", end_level > 1,
          f"top level {end_level} after {fights} fights, {g.gold}g, {len(g.inventory)} item kinds")
    check("power grows with levels", sum(m.power for m in g.party) > start_power)
    return g


def test_quests(g):
    ui.QUIET = True
    g.board = quests.generate_board(g, 6)
    ui.QUIET = False
    check("board generates contracts", len(g.board) >= 3, f"{len(g.board)} offers")
    kinds = {q.kind for q in g.board}
    fetch = [q for q in g.board if q.kind == "fetch"]
    if fetch:
        q = fetch[0]
        q.start(g)
        g.quests.append(q)
        before = g.gold
        g.add_item(q.target, q.qty)
        ok = q.done(g)
        ui.QUIET = True
        q.turn_in(g)
        ui.QUIET = False
        check("fetch quest completes and pays", ok and g.gold > before,
              f"+{g.gold - before}g")
    slay = [q for q in g.board if q.kind == "slay"]
    if slay:
        q = slay[0]
        q.start(g)
        base = q._base
        fam = q.target.replace("family:", "")
        g.kills[q.target] = base + q.qty
        check("slay quest tracks kills after acceptance", q.done(g),
              f"{fam} {q.have(g)}/{q.qty}")
    check("board offers variety", len(kinds) >= 2, str(sorted(kinds)))


def test_shop_and_summon(g):
    with_script([0, "all", -1])          # sell first stack, all of it, then leave
    before = g.gold
    ui.QUIET = True
    shop._sell(g)
    ui.QUIET = False
    check("selling loot pays gold", g.gold >= before, f"{before}g -> {g.gold}g")

    g.shards = 500
    n_before = len(g.roster)
    with_script([])
    ui.QUIET = True
    summon._summon(g, 3)
    ui.QUIET = False
    check("summoning adds monsters", len(g.roster) == n_before + 3,
          f"roster {n_before} -> {len(g.roster)}, {g.shards} shards left")


def test_save_roundtrip(g, bestiary):
    import tempfile
    from engine import state
    state.SAVE_DIR = tempfile.mkdtemp(prefix="voidcaller-test-")
    g.slot = "selftest"
    path = g.save()
    g2 = Game.load("selftest", bestiary)
    ok = (g2 is not None and g2.gold == g.gold and len(g2.roster) == len(g.roster)
          and g2.hunter == g.hunter and g2.inventory == g.inventory
          and len(g2.quests) == len(g.quests)
          and g2.clock.view() == g.clock.view() and g2.codex == g.codex)
    check("save survives a round trip", ok,
          f"{len(g.roster)} monsters, {len(g.inventory)} item kinds, {len(g.quests)} quests")
    if g2:
        same = all(a.level == b.level and a.xp == b.xp
                   and a.potential == b.potential
                   for a, b in zip(g.roster, g2.roster))
        check("levels, xp, and creature potential survive saving", same)
    os.remove(path)
    os.rmdir(state.SAVE_DIR)


def test_world_clock():
    """Time rolls across midnight, catches up offline, and stays serializable."""
    from engine.clock import WorldClock

    c = WorldClock(day=2, minute_of_day=23 * 60 + 55, last_seen_at=1_000.0)
    c.advance(10)
    crossed_midnight = c.day == 3 and c.label == "00:05"
    caught_up = c.sync(1_120.0) == 2 and c.label == "00:07"
    loaded = WorldClock.from_dict(c.to_dict())
    check("world clock advances and survives serialization",
          crossed_midnight and caught_up and loaded.view() == c.view(), c.label)


def test_individual_potential_and_codex(bestiary):
    """Same species can build differently, and discovery has real stages."""
    from engine.entities import POTENTIAL_KEYS, potential_from_seed, spawn

    t = bestiary.all[0]
    high = spawn(t, 20)
    low = spawn(t, 20)
    high.potential = {key: "S" for key in POTENTIAL_KEYS}
    low.potential = {key: "D" for key in POTENTIAL_KEYS}
    stable = potential_from_seed(412) == potential_from_seed(412)
    distinct = high.stat("atk") > low.stat("atk") and high.max_hp >= low.max_hp
    check("individual potential is stable and affects stats", stable and distinct,
          f"ATK {low.stat('atk'):.1f}–{high.stat('atk'):.1f}")

    g = Game(bestiary)
    g.discover(t, "encounter")
    first = g.codex_record(t)
    g.record_kill(t)
    second = g.codex_record(t)
    check("codex knowledge advances from encounter to defeat",
          first["encounters"] == 1 and first["defeats"] == 0
          and second["defeats"] == 1 and t.id in g.seen,
          f"encounters {second['encounters']} · defeats {second['defeats']}")


def test_story(g, bestiary):
    chapters = story.load_chapters()
    check("story chapters load", len(chapters) >= 3, f"{len(chapters)} chapters")
    ok = True
    for ch in chapters:
        for scene in ch["scenes"]:
            if "battle" in scene:
                foes = story._pick_monsters(g, scene["battle"], 20)
                if not foes:
                    ok = False
    check("every story battle can find a monster", ok)


def test_void_events(g, bestiary):
    ui.QUIET = True
    sizes = []
    for h in bestiary.habitats()[:6]:
        for lvl in (3, 15, 30):
            foes = void.build_encounter(g, h, lvl)
            sizes.append(len(foes))
            if not foes:
                sizes.append(0)
    boss = void.build_encounter(g, bestiary.habitats()[0], 20, boss=True)
    ui.QUIET = False
    check("every region can fill an encounter", all(1 <= s <= 4 for s in sizes),
          f"group sizes {min(sizes)}-{max(sizes)}")
    check("boss encounters resolve to one monster", len(boss) == 1,
          boss[0].name if boss else "none")


def test_screens(g, bestiary):
    """Every menu screen, driven blind, must survive and hand control back."""
    ui.QUIET = True
    screens = [
        ("quest board", quests.board_screen, [0, 0, True, -1]),
        ("stall", shop.screen, [1, 0, "1", -1]),
        ("trainer", shop._train, [0]),
        ("circle", summon.screen, [0, -1]),
        ("pack", team.screen, [0, 0, "Fang", -1]),
        ("choose four", team._choose_party, [0, 0, -1]),
        ("ledger", team.bestiary_screen, []),
        ("story", story.screen, [-1]),
        ("void region menu", void.region_menu, [-1]),
    ]
    ok = True
    broken = []
    for name, fn, answers in screens:
        with_script(answers)
        try:
            fn(g)
        except TypeError:
            try:
                fn()
            except Exception as e:
                ok = False
                broken.append(f"{name}: {e}")
        except Exception as e:
            ok = False
            broken.append(f"{name}: {type(e).__name__} {e}")
    ui.QUIET = False
    check("every screen opens and closes cleanly", ok, "; ".join(broken)[:120])


def test_story_playthrough(g, bestiary):
    """Chapter one, start to finish, on auto."""
    ui.QUIET = True
    with_script([])
    real_turn = combat.player_turn
    combat.player_turn = lambda *a, **k: "auto"
    chapters = story.load_chapters()
    before = g.gold
    for m in g.roster:
        m.level = max(m.level, 12)
        m.full_heal()
    ok, err = False, ""
    for attempt in range(8):            # the chapter is a real fight; it can be lost
        for m in g.roster:
            m.full_heal()
        try:
            story.play(g, chapters[0], 12)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            break
        if g.story >= 1:
            ok = True
            break
    if not ok and not err:
        err = "chapter never completed in 8 attempts"
    combat.player_turn = real_turn
    ui.QUIET = False
    check("a story chapter plays through", ok, err or f"story at {g.story}, +{g.gold-before}g")


def test_web_session(bestiary):
    """The browser only ever talks to Session. Drive a whole run through it."""
    from engine.session import Session
    from engine.state import Game as G

    ui.QUIET = True
    sess = Session(G(bestiary))
    st = sess.act("new_game", {"name": "Selftest"})
    ok_start = st["screen"] == "home" and len(st["party"]) == 1
    check("session starts a new hunt", ok_start,
          f"{len(st['party'])} starter, {len(st['regions'])} regions")
    keys = {"screen", "party", "regions", "depths", "inventory", "run", "battle", "events"}
    check("state carries everything the UI needs", keys <= set(st.keys()),
          str(sorted(keys - set(st.keys()))) if not keys <= set(st.keys()) else "")
    check("monsters arrive with a portrait", len(st["party"][0]["portrait"]) > 4,
          f"{len(st['party'][0]['portrait'])} rows")

    st = sess.act("start_run", {"region": st["regions"][0]["key"], "depth": "deep"})
    check("a run generates a branching map", st["screen"] == "descent"
          and len(st["run"]["map"]["rows"]) >= 5,
          f"{len(st['run']['map']['rows'])} rows, "
          f"{sum(len(r) for r in st['run']['map']['rows'])} nodes")

    fights = turns = 0
    for _ in range(60):
        if st["screen"] == "battle" and st["battle"]:
            b = st["battle"]
            if b["finished"]:
                st = sess.act("goto", {"screen": "descent" if st["run"] else "home"})
                continue
            o = b["options"]
            if not o.get("moves"):
                st = sess.act("battle", {"move": "auto"})
                continue
            turns += 1
            tgt = (o["targets"][0]["uid"] if o["targets"] else None)
            st = sess.act("battle", {"move": "skill", "skill": 0, "target": tgt})
            continue
        if st["screen"] != "descent" or not st["run"]:
            break
        avail = st["run"]["map"]["available"]
        if not avail:
            break
        before = st["screen"]
        st = sess.act("descend", {"node": avail[0]})
        if st["screen"] == "battle":
            fights += 1
    ui.QUIET = False
    check("a run plays through the API", fights >= 1 and turns >= 1,
          f"{fights} fights, {turns} player turns, ended on '{st['screen']}'")

    hit_shown = False
    ui.QUIET = True
    s2 = Session(G(bestiary))
    st2 = s2.act("new_game", {"name": "Odds"})
    st2 = s2.act("start_run", {"region": st2["regions"][0]["key"], "depth": "abyssal"})
    for _ in range(12):
        if st2["screen"] == "battle" and st2["battle"] and st2["battle"]["options"].get("moves"):
            for m in st2["battle"]["options"]["moves"]:
                if m["hit"] is not None and m["crit"] is not None:
                    hit_shown = True
            break
        if not st2["run"] or not st2["run"]["map"]["available"]:
            break
        st2 = s2.act("descend", {"node": st2["run"]["map"]["available"][0]})
    ui.QUIET = False
    check("the move picker knows the odds before you commit", hit_shown)


def test_elements(bestiary):
    from engine import elements as EL
    cfg = EL.config()
    check("element chart loaded", len(cfg.get("chart", {})) >= 6,
          f"{len(cfg.get('chart', {}))} defender types")
    t = next((x for x in bestiary.all if x.primary == "Plant"), bestiary.all[0])
    weak = EL.weaknesses(t)
    check("hybrid chart produces real weaknesses", len(weak) >= 1,
          f"{t.name}: " + ", ".join(f"{e} x{m}" for e, m in weak[:3]))
    diffs = 0
    for x in bestiary.all[:40]:
        for e, d in EL.profile(x).items():
            if abs(d["mult"] - d["chart"]) > 0.05:
                diffs += 1
    check("monsters still override the chart", diffs > 20,
          f"{diffs} per-monster deviations in the first 40 species")


class FakeBackend:
    """A backend that draws nowhere, so the shell can be driven in a test."""
    def __init__(self): self.cursor = None; self.frames = 0
    def poll(self): return []
    def render(self, screen): self.frames += 1; screen.dirty = False
    def save(self, path): pass
    def close(self): pass


def test_board(bestiary):
    """A contract has to be takeable, trackable and payable."""
    from engine.session import Session
    from engine.state import Game as G
    from engine.quests import load_authored

    authored = load_authored()
    check("hand-written contracts load", len(authored) >= 2,
          f"{len(authored)} in data/quests.json: " +
          ", ".join(q.title for q in authored[:3]))

    ui.QUIET = True
    sess = Session(G(bestiary))
    st = sess.act("new_game", {"name": "Board"})
    offers = st.get("board") or []
    hand = [q for q in offers if q.get("authored")]
    ui.QUIET = False
    check("the board is never empty", len(offers) >= 3,
          f"{len(offers)} posted, {len(hand)} of them hand-written")

    ui.QUIET = True
    st = sess.act("accept_quest", {"index": 0})
    taken = st["quests"]
    fetch = next((q for q in taken if q["kind"] == "fetch"), None)
    ui.QUIET = False
    check("a contract can be taken", len(taken) == 1,
          f"carrying '{taken[0]['title']}' — {taken[0]['have']}/{taken[0]['qty']}"
          if taken else "nothing taken")
    check("a contract says where to go", bool(taken and taken[0]["where"]),
          taken[0]["where"] if taken else "")

    if fetch:
        ui.QUIET = True
        before = sess.game.gold
        sess.game.add_item(sess.game.quests[0].target, fetch["qty"])
        st = sess.act("turn_in", {"index": 0})
        ui.QUIET = False
        check("a finished contract pays out", not st["quests"] and st["gold"] > before,
              f"+{st['gold'] - before}g")
    else:
        ui.QUIET = True
        st = sess.act("abandon_quest", {"index": 0})
        ui.QUIET = False
        check("a contract can be dropped", not st["quests"])


def test_shell(bestiary):
    """The fixed-frame shell, driven with no keyboard and no window."""
    from engine.session import Session
    from engine.state import Game as G
    from tui.app import App

    ui.QUIET = True
    sess = Session(G(bestiary))
    sess.act("new_game", {"name": "Shell"})
    back = FakeBackend()
    app = App(back, sess)

    def flush(limit=400):
        import time as _t
        for _ in range(limit):
            app.next_at = 0
            app.drain()
            app.draw()
            back.render(app.screen)
            if not app.busy:
                break

    painted = []
    app.draw(); back.render(app.screen)
    painted.append(sum(1 for _ in app.screen.runs()))

    # Level the one starter first: this is a shell test, not a test of odds.
    for m in sess.game.roster:
        m.level = max(m.level, 10)
        m.full_heal()

    app.run_command("walk 1"); flush()
    places_seen = {app.place}
    in_run = bool(app.state.get("run"))
    fights = turns = 0
    spoils_seen = []
    for _ in range(160):
        if not app.state.get("run") and not app.state.get("spoils") and fights and not spoils_seen:
            for m in sess.game.roster:      # wiped; go again
                m.full_heal()
            app.run_command("walk 1")
            flush()
            continue
        if app.state.get("battle") and not app.state["battle"]["finished"]:
            moves = (app.state["battle"].get("options") or {}).get("moves") or []
            pick = max((i for i, m in enumerate(moves) if m["usable"]),
                       key=lambda i: moves[i].get("damage", 0), default=0)
            app.hotkey(str(pick + 1))    # pick a move it can actually pay for
            if app.aim is not None:
                app.hotkey("1")          # then pick who gets it
            turns += 1
            flush()
            continue
        if app.state.get("spoils"):
            spoils_seen.append(app.state["spoils"])
            app.draw()
            app.act("claim", {"leave": []})
            flush()
            continue
        if app.state.get("battle") and app.state["battle"]["finished"]:
            app.act("goto", {"screen": "run" if app.state.get("run") else "village"})
            flush()
            continue
        if not app.state.get("run"):
            break
        avail = app.state["run"]["map"]["available"]
        if not avail:
            break
        app.run_command("down 1")
        flush()
        if app.state.get("battle"):
            fights += 1
        places_seen.add(app.place)
    app.draw(); back.render(app.screen)
    painted.append(sum(1 for _ in app.screen.runs()))
    ui.QUIET = False

    check("the shell paints a full frame", min(painted) > 60,
          f"{painted[0]} styled runs on the village frame, {painted[-1]} later")
    check("walking into the Void moves you there", in_run, f"ended in '{app.place}'")
    check("a fight can be fought from the shell", turns >= 1,
          f"{fights} fights entered, {turns} moves taken")

    won = [s for s in spoils_seen if s]
    check("winning a fight lays out the spoils", bool(won),
          f"{len(won)} victory screens")
    if won:
        sp = won[0]
        shaped = (all(k in sp for k in ("xp", "gold", "shards", "loot", "party"))
                  and all(all(k in m for k in ("name", "level", "xp_span", "gain"))
                          for m in sp["party"]))
        check("the spoils say what each monster gained",
              shaped, f"{sp['xp']} xp over {len(sp['party'])} of them, "
                      f"{len(sp['loot'])} kinds of loot")

    ui.QUIET = True
    app.run_command("scout gravehound")
    app.run_command("help")
    app.run_command("nonsense")
    app.run_command("pack")
    ui.QUIET = False
    log = " ".join(t for t, _ in app.log)
    check("command line answers", "Gravehound" in log and "isn't a command" in log,
          f"{len(app.log)} lines of history")

    # every place must build a menu and survive being drawn
    from tui.places import PLACES
    broken = []
    for name in PLACES:
        app.nav = [name]
        app.focus_uid = (app.state["roster"][0]["uid"] if name.endswith("pack.card")
                         else (app.s.game.bestiary.all[0].id if name.endswith("ledger.card")
                               else None))
        app.focus_name = "x"
        try:
            app.draw()
            back.render(app.screen)
        except Exception as exc:
            broken.append(f"{name}: {type(exc).__name__} {exc}")
    check("every place draws", not broken, "; ".join(broken)[:150])

    from tui.screen import Screen
    sc = Screen(40, 5)
    sc.bar(0, 0, 20, 5, 10)
    sc.put(0, 2, "x" * 100)
    check("the cell grid clips instead of overflowing",
          all(len(row) == 40 for row in sc.cells))


def test_no_dice(bestiary):
    """The maths is a formula now, and the odds shown are the odds used."""
    from engine import formula as F
    from engine.entities import spawn
    import os

    check("no module rolls dice any more",
          not os.path.isfile(os.path.join(
              os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
              "engine", "dice.py")))

    pool = [t for t in bestiary.all if not t.is_boss][:40]
    a = next(spawn(t, 20) for t in pool if any(s.is_damage for s in spawn(t, 20).skills))
    b = spawn(pool[1], 20, enemy=True)
    skill = max((s for s in a.skills if s.is_damage), key=lambda s: s.power)
    accs = [F.accuracy(spawn(t, 20), b, skill) for t in pool[:20]]
    check("accuracy is a percentage in range",
          all(30 <= x <= 99 for x in accs),
          f"{min(accs):.0f}% to {max(accs):.0f}% across 20 attackers")

    # damage is a ratio of attack to defence, so a fight at level 40 should run
    # about as long as the same fight at level 4. This is the whole point of the
    # formula, and the only honest way to check it is to fight both.
    def rounds_at(lvl, n=40):
        ui.QUIET = True
        out = []
        for i in range(n):
            party = [spawn(pool[(i * 3 + k) % len(pool)], lvl) for k in range(3)]
            foes = [spawn(pool[(i * 5 + k) % len(pool)], lvl, enemy=True) for k in range(2)]
            out.append(combat.battle(party, foes, auto=True, allow_flee=False,
                                     title="scale").rounds)
        ui.QUIET = False
        return statistics.median(out)

    low, high = rounds_at(4), rounds_at(40)
    check("a level 40 fight runs as long as a level 4 one",
          abs(low - high) <= max(2, max(low, high) * 0.4),
          f"median {low:.0f} rounds at L4, {high:.0f} at L40")

    events = []
    for _ in range(60):
        events += rules_hits(a, b, skill)
    keys = {e["k"] for e in events}
    check("a strike is one event, not a pile of dice", keys <= {"hit", "miss"},
          ", ".join(sorted(keys)))
    hits = [e for e in events if e["k"] == "hit"]
    check("every hit says what it did and what is left",
          all(all(k in e for k in ("amount", "chance", "crit", "hp", "max_hp"))
              for e in hits), f"{len(hits)} hits")


def rules_hits(a, b, skill):
    from engine import rules
    b.cur_hp = b.max_hp
    return rules.resolve_hit(a, b, skill)


def test_empty_monster_can_still_act(bestiary):
    """Out of mana is not the same as harmless."""
    from engine.entities import spawn
    from engine import rules

    stuck = [t for t in bestiary.all if all(s.mp_cost > 0 for s in t.base_moves + t.skills)]
    check("some monsters have no free move at all", True,
          f"{len(stuck)} of {len(bestiary.all)}")
    ok = True
    for t in stuck[:25] or bestiary.all[:25]:
        m = spawn(t, 12)
        m.cur_mp = 0
        foe = spawn(bestiary.all[0], 12, enemy=True)
        opts = rules.move_options(m, [foe])
        if not any(o["usable"] and o["damage"] > 0 for o in opts):
            ok = False
    check("a drained monster is still offered something that hurts", ok)


def test_finding_the_bestiary():
    """Where the monsters come from, and what happens when they do not."""
    from engine import data
    import os

    paths = data.search_paths()
    check("the search list is reported", len(paths) >= 5, f"{len(paths)} places")

    # the game carries its own bestiary, so it must load with nothing external
    inside_only = [p for p in data.BUILTIN_SEARCH if data.GAME_DIR in p]
    real = data.BUILTIN_SEARCH
    try:
        data.BUILTIN_SEARCH = inside_only
        alone = data.load_bestiary()
    finally:
        data.BUILTIN_SEARCH = real
    check("the game carries its own bestiary", len(alone.all) > 20,
          f"{len(alone.all)} species from data/monsters/ alone")

    # anything named in data/sources.json is tried before the built-ins, so a
    # live generator output always wins over a stale copy inside the game
    configured = data._configured_sources()
    if configured:
        check("configured sources are looked at first", paths[0] == configured[0],
              os.path.basename(paths[0]))

    real_search, real_sources = data.BUILTIN_SEARCH, data.SOURCES_FILE
    real_env = os.environ.pop("VOIDCALLER_MONSTERS", None)
    try:
        data.BUILTIN_SEARCH = [os.path.join("/nowhere", "*.jsonl")]
        data.SOURCES_FILE = "/nowhere/sources.json"
        empty = data.load_bestiary()
        check("an empty bestiary is empty, not a crash", not empty.all)
        why = data.explain_empty_bestiary(empty)
        check("and it says where it looked and what to do",
              "/nowhere" in why and "sources.json" in why
              and "VOIDCALLER_MONSTERS" in why)

        # the env var is honoured, and ~ and relative paths are resolved
        os.environ["VOIDCALLER_MONSTERS"] = os.path.join(real_sources, "..", "..",
                                                         "data", "monsters", "*.jsonl")
        resolved = data.search_paths()[0]
        check("VOIDCALLER_MONSTERS is picked up", "monsters" in resolved)
    finally:
        data.BUILTIN_SEARCH, data.SOURCES_FILE = real_search, real_sources
        os.environ.pop("VOIDCALLER_MONSTERS", None)
        if real_env is not None:
            os.environ["VOIDCALLER_MONSTERS"] = real_env

    from engine import quests
    from engine.state import Game
    check("a board on an empty bestiary is empty, not a crash",
          quests.generate_board(Game(data.Bestiary([]))) == [])


def test_friendly_moves(bestiary):
    """A move that helps goes to your own side. It used to ask you to pick an
    enemy and then quietly heal the caster."""
    from engine.entities import spawn
    from engine import rules

    friendly = [(t, s) for t in bestiary.all for s in t.base_moves + t.skills if s.is_friendly]
    check("the game knows which moves are friendly", len(friendly) > 10,
          f"{len(friendly)} of {sum(len(t.base_moves + t.skills) for t in bestiary.all)} moves")

    wrong = 0
    for t, sk in friendly[:60]:
        caster = spawn(t, 15)
        mate = spawn(bestiary.all[1], 15)
        foe = spawn(bestiary.all[2], 15, enemy=True)
        mate.cur_hp = max(1, mate.max_hp // 4)
        # deliberately hand it the enemy, the way the old interface did
        picked = rules.pick_targets(sk, caster, [caster, mate], [foe], chosen=foe)
        if any(p.is_enemy for p in picked):
            wrong += 1
    check("a friendly move never lands on the enemy", wrong == 0,
          f"{len(friendly[:60])} checked")

    healers = [(t, s) for t, s in friendly if any(f.kind == "heal" for f in s.fx)]
    if healers:
        t, sk = healers[0]
        caster, mate = spawn(t, 15), spawn(bestiary.all[1], 15)
        foe = spawn(bestiary.all[2], 15, enemy=True)
        caster.cur_hp, mate.cur_hp = caster.max_hp, max(1, mate.max_hp // 4)
        evs = rules.take_turn(caster, [caster, mate], [foe], sk, foe)
        healed = {e["target"] for e in evs if e["k"] == "heal"}
        check("a heal reaches the one who needs it",
              bool(healed) and foe.name not in healed, ", ".join(healed) or "nobody")

    # a debuff written tersely must not read as a buff
    from engine.effects import parse
    cases = {"-def": -1, "+atk": 1, "-20% evasion for two turns": -1,
             "increases wind resistance and decreases speed": None}
    ok = True
    for text, want in cases.items():
        fx = [e for e in parse(text) if e.kind == "stat"]
        if not fx:
            ok = False
        elif want is not None and not all((e.amount < 0) == (want < 0) for e in fx):
            ok = False
    mixed = {e.key: e.amount for e in
             parse("increases wind resistance and decreases speed") if e.kind == "stat"}
    check("terse debuffs parse as debuffs",
          ok and mixed.get("res", 0) > 0 and mixed.get("spd", 0) < 0,
          f"res {mixed.get('res', 0):+.0%}, spd {mixed.get('spd', 0):+.0%}")


def test_look():
    """Themes reach the palette, survive a save, and never paint nothing."""
    from tui import theme as TH, screen as SC

    names = [t["name"] for t in TH.presets()]
    check("looks load", len(names) >= 3, ", ".join(names))

    ok = True
    for name in names:
        t = TH.apply(TH.preset(name))
        roles = {"bg", "text", "bright", "dim", "faint", "line", "accent",
                 "green", "amber", "gold", "red", "magenta", "blue", "cyan"}
        if not roles <= set(t["colors"]):
            ok = False
        # text must actually be visible against the background it ships with
        bg, fg = SC.PALETTE["bg"], SC.PALETTE["text"]
        if abs(sum(fg) - sum(bg)) < 120:
            ok = False
    check("every look has every role, and text you can read on its own bg", ok)

    TH.use("amber")
    check("switching a look reaches the palette", SC.PALETTE["bg"] != (7, 12, 10))
    TH.set_bars("blocks")
    check("bar style reaches the grid", SC.BAR_FULL == "\u2588")
    TH.set_color("accent", "#ff0000")
    check("a custom colour sticks", SC.PALETTE["accent"] == (255, 0, 0))
    check("a bad colour is refused", not TH.set_color("accent", "puce"))
    check("a bad role is refused", not TH.set_color("nonsense", "#ffffff"))
    TH.use("phosphor")
    TH.set_bars("hashes")


def test_forge():
    """The forge builds prompts, checks records and knows where things go."""
    import forge

    lib = forge.library()
    check("the forge sees the dataset", lib["species"] > 0 and lib["habitats"],
          f"{lib['species']} species, {len(lib['habitats'])} regions")

    for kind in ("monster", "item", "quest", "story", "recipe"):
        system, user = forge.build_prompt(kind, {"level": 12, "brief": "a test"})
        if not user or len(user) < 40:
            check(f"{kind} prompt builds", False)
            break
    else:
        check("every kind builds a prompt", True, "monster, item, quest, story, recipe")

    good = {"kind": "fetch", "title": "T", "giver": "G", "text": "x",
            "target": "Venom Sac", "qty": 3, "gold": 200}
    check("a good record passes", forge.check("quest", good)["ok"])
    check("a broken record is caught",
          not forge.check("quest", {"kind": "fetch"})["ok"])
    recipe = {"id": "test_salve", "name": "Test Salve", "station": "craft_shop",
              "level": 4, "ingredients": [{"item": "Scrap", "qty": 2}],
              "result": {"item": "Test Salve", "qty": 1}, "gold_cost": 10,
              "description": "a deterministic test craft"}
    check("a crafting recipe passes", forge.check("recipe", recipe)["ok"])

    fenced = "```json\n{\"a\": 1}\n```"
    check("markdown fences are unwrapped", forge.coerce_json(fenced) == {"a": 1})
    check("a chatty reply is unwrapped",
          forge.coerce_json('Sure! {"a": 2} hope that helps') == {"a": 2})

    rows = forge.export("monster").splitlines()
    check("the bestiary exports as jsonl the game can read back",
          bool(rows) and all(json.loads(r).get("id") for r in rows[:20]),
          f"{len(rows)} records")

    ids = {t.id for t in forge.bestiary().all}
    check("a new monster id never collides", forge.next_monster_id() not in ids,
          forge.next_monster_id())


def test_redesign_systems(bestiary):
    """The new hub systems must be gameplay, not decorative screens."""
    from engine.session import Session
    from engine.state import Game as G
    from engine.entities import spawn

    sess = Session(G(bestiary))
    st = sess.act("new_game", {"name": "Systems"})
    st = sess.act("accept_quest", {"index": 0})
    check("signing a contract creates a mission front",
          bool(st.get("mission") and st["mission"]["uid"] == st["quests"][0]["uid"]),
          st["mission"]["title"] if st.get("mission") else "no mission")
    st = sess.act("start_quest_run", {"index": 0, "depth": "deep"})
    check("a signed mission owns its raid",
          bool(st.get("run") and st["run"]["quest_uid"] == st["mission"]["uid"]
               and st["mission"]["stages_left"] == 7),
          f"{st.get('mission', {}).get('stages_left', '?')} stages left")

    work = Session(G(bestiary))
    st = work.act("new_game", {"name": "Workers"})
    st = work.act("buy", {"name": "Bitterleaf Seed"})
    st = work.act("plant_crop", {"crop": "bitterleaf", "qty": 1})
    before = work.game.count("Herb Bundle")
    work.game.advance_time(360)
    st = work.act("harvest_farm", {})
    st = work.state()
    check("farm plots grow and harvest over world time",
          work.game.count("Herb Bundle") == before + 1 and st["farm"]["empty"] >= 1,
          f"{before} -> {work.game.count('Herb Bundle')} herbs")

    work.act("buy", {"name": "Hunter's Smithing Primer"})
    work.game.add_item("Scrap Iron", 2)
    work.game.add_item("Herb Bundle", 1)
    st = work.act("craft", {"recipe": "field_knife"})
    crafted = work.game.count("Field Knife")
    check("crafting consumes materials and creates gear", crafted == 1,
          st.get("message", ""))
    target = work.game.party[0]
    atk_before = target.stat("atk")
    st = work.act("equip", {"uid": target.uid, "name": "Field Knife"})
    check("creatures can equip stat-bearing weapons",
          target.stat("atk") >= atk_before + 3.9 and "weapon" in target.equipment,
          f"ATK {atk_before:.1f} -> {target.stat('atk'):.1f}")

    costly = next((t for t in bestiary.all
                   if not any(s.is_damage and s.mp_cost == 0 for s in t.base_moves + t.skills)), None)
    unit = spawn(costly, costly.level) if costly else None
    check("incomplete movesets receive a species-flavoured base attack",
          bool(unit and any(s.is_damage and s.mp_cost == 0 for s in unit.skills)),
          next((s.name for s in unit.skills if s.is_damage and s.mp_cost == 0), "none")
          if unit else "no candidate")


def main():
    from tools.v2_core_selfcheck import main as v2_main
    return v2_main()


if __name__ == "__main__":
    raise SystemExit(main())
