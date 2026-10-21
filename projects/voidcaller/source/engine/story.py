"""Mini story quests. Text, then teeth."""
from __future__ import annotations

import json
import os
import random

from . import combat, ui
from .data import GAME_DIR
from .entities import spawn

STORY_PATH = os.path.join(GAME_DIR, "data", "story.json")
RARITY_ORDER = ["Common", "Uncommon", "Rare", "Epic"]


def load_chapters() -> list[dict]:
    if not os.path.isfile(STORY_PATH):
        return []
    with open(STORY_PATH, encoding="utf-8") as f:
        return json.load(f).get("chapters", [])


def _pick_monsters(game, spec: dict, party_level: int):
    """Story battles name a shape, not an id, so they still work after you
    regenerate the bestiary."""
    b = game.bestiary
    fb = spec.get("fallback", {})
    pool = b.all
    if spec.get("monster"):
        t = b.get(spec["monster"])
        if t:
            pool = [t]
    if len(pool) > 1:
        if fb.get("highest"):
            pool = sorted(b.all, key=lambda t: t.level, reverse=True)[:3]
        else:
            if fb.get("boss"):
                pool = [t for t in pool if t.is_boss] or \
                       [t for t in b.all if t.rarity == "Epic"]
            if fb.get("min_rarity"):
                floor = RARITY_ORDER.index(fb["min_rarity"])
                pool = [t for t in pool if RARITY_ORDER.index(t.rarity) >= floor] or pool
            if fb.get("max_level"):
                pool = [t for t in pool if t.level <= fb["max_level"]] or pool
            near = [t for t in pool if abs(t.level - party_level) <= 10]
            pool = near or pool
    lead = random.choice(pool)
    lvl = max(1, party_level + int(spec.get("level_offset", 0)))
    return [spawn(lead, lvl, enemy=True) for _ in range(int(spec.get("count", 1)))]


def screen(game) -> None:
    chapters = load_chapters()
    if not chapters:
        ui.say(ui.c("  No story data found.", "red"))
        ui.pause()
        return
    lvl = max(1, sum(m.level for m in game.party) // max(1, len(game.party)))
    rows, playable = [], []
    for ch in chapters:
        done = game.story >= ch["id"]
        locked = ch["id"] > game.story + 1 or lvl < ch.get("requires_level", 1)
        tag = (ui.c("cleared", "grey") if done else
               ui.c(f"needs level {ch['requires_level']}", "red") if locked else
               ui.c("open", "bright_yellow"))
        rows.append(f"{ch['id']}. {ch['title']:<34} {tag}")
        playable.append(None if (done or locked) else ch)
    ui.header("THE THREAD", f"chapters cleared: {game.story}/{len(chapters)}")
    i = ui.menu("  Which chapter?", rows, back="leave")
    if i < 0:
        return
    ch = playable[i]
    if ch is None:
        ui.say(ui.c("  Not that one. Not yet.", "grey"))
        ui.pause()
        return
    play(game, ch, lvl)


def play(game, ch: dict, party_level: int) -> None:
    ui.clear()
    ui.header(f"CHAPTER {ch['id']}", ch["title"])
    for scene in ch["scenes"]:
        if "text" in scene:
            ui.say()
            for line in _wrap(scene["text"]):
                ui.say("  " + line)
            ui.pause()
        elif "battle" in scene:
            foes = _pick_monsters(game, scene["battle"], party_level)
            res = combat.battle(game.party, foes, game=game, allow_flee=False,
                                title=scene.get("title", "STORY BATTLE"))
            if res.wiped:
                ui.say()
                ui.say(ui.c("  You do not finish this chapter today.", "red"))
                for m in game.roster:
                    m.full_heal()
                ui.pause()
                return
            for f in foes:
                if not f.alive:
                    game.record_kill(f.template)
            game.gold += res.gold
            game.shards += res.shards
            for m in game.party:
                for lv in m.gain_xp(res.xp):
                    ui.say(ui.c(f"  {m.name} reaches level {lv}!", "bright_yellow"))
            for item in res.loot:
                game.add_item(item)

    r = ch.get("reward", {})
    game.gold += r.get("gold", 0)
    game.shards += r.get("shards", 0)
    if r.get("item"):
        game.add_item(r["item"])
    for m in game.party:
        for lv in m.gain_xp(r.get("xp", 0)):
            ui.say(ui.c(f"  {m.name} reaches level {lv}!", "bright_yellow"))
    game.story = max(game.story, ch["id"])
    ui.box([f"{ui.money(r.get('gold',0))}   {ui.shards(r.get('shards',0))}   "
            f"{ui.c(str(r.get('xp',0)) + ' xp', 'bright_green')}"
            + (f"   1x {r['item']}" if r.get("item") else "")],
           title="CHAPTER CLEARED")
    if ch.get("outro"):
        ui.say()
        for line in _wrap(ch["outro"]):
            ui.say("  " + ui.c(line, "grey"))
    for m in game.roster:
        m.full_heal()
    ui.pause()


def _wrap(text: str, width: int = 0) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width or max(40, ui.width() - 6))
