"""Forge-authored Void areas and their explicit monster rosters.

Areas used to be inferred from a monster's free-form ``habitat`` text.  That
made it impossible to deliberately say which species belonged in a region.
This module makes the Atlas a small piece of editable data instead: an area
names the monster IDs that spawn there.
"""
from __future__ import annotations

import json
import os

from .data import GAME_DIR

FILE = os.path.join(GAME_DIR, "data", "areas.json")


def load() -> list[dict]:
    """Load valid area records. A blank file is a valid empty Atlas."""
    try:
        with open(FILE, encoding="utf-8") as fh:
            blob = json.load(fh)
        rows = blob.get("areas", []) if isinstance(blob, dict) else blob
    except Exception:
        rows = []
    out, seen = [], set()
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("id") or "").strip().lower()
        name = str(raw.get("name") or "").strip()
        if not key or not name or key in seen:
            continue
        seen.add(key)
        ids, assigned = [], set()
        for monster_id in raw.get("monster_ids") or []:
            monster_id = str(monster_id).strip()
            if monster_id and monster_id not in assigned:
                assigned.add(monster_id)
                ids.append(monster_id)
        out.append({"id": key, "name": name, "description": str(raw.get("description") or ""),
                    "monster_ids": ids, "boss_ids": [str(x) for x in raw.get("boss_ids") or []
                    if str(x).strip()]})
    return out


def templates_for(bestiary, area_id: str, *, bosses: bool | None = None) -> list:
    """Return only the species deliberately assigned to this area."""
    area_id = str(area_id or "").lower()
    area = next((a for a in load() if a["id"] == area_id), None)
    if area is None:
        return []
    rows, assigned = [], list(area["monster_ids"])
    # A boss-only assignment is still a real authored member of the area.  It
    # is included for boss encounters and for quest lookups, but never makes
    # the area appear on the normal Atlas by itself.
    if bosses is not False:
        assigned += list(area.get("boss_ids") or [])
    for monster_id in assigned:
        monster = bestiary.get(monster_id)
        if monster and (bosses is None or bool(monster.is_boss) == bosses):
            if monster not in rows:
                rows.append(monster)
    return rows


def regions(bestiary, player_level: int) -> list[dict]:
    """Atlas rows with a real, editable spawn roster behind each one."""
    out = []
    weight = {"Common": 1.0, "Uncommon": 1.15, "Rare": 1.35, "Epic": 1.6}
    for area in load():
        pool = templates_for(bestiary, area["id"], bosses=False)
        if not pool:
            continue
        calibre = sum(weight.get(t.rarity, 1.0) for t in pool) / len(pool)
        danger = ("quiet" if calibre < 1.12 else "fair" if calibre < 1.28
                  else "hard" if calibre < 1.45 else "lethal")
        out.append({"key": area["id"], "name": area["name"],
                    "description": area["description"], "level": max(1, int(player_level)),
                    "native_level": int(sum(t.level for t in pool) / len(pool)),
                    "species": len(pool), "danger": danger, "calibre": round(calibre, 2),
                    "monster_ids": [t.id for t in pool]})
    return sorted(out, key=lambda row: (row["calibre"], row["name"]))


def area_for_monster(bestiary, monster_or_name) -> dict | None:
    """Find the first authored area containing a monster or one of its names."""
    ident = getattr(monster_or_name, "id", monster_or_name)
    text = str(ident or "").lower()
    for area in load():
        for monster_id in area["monster_ids"]:
            monster = bestiary.get(monster_id)
            if monster and (monster.id.lower() == text or monster.name.lower() == text):
                return area
    return None


def area_for_quest_target(bestiary, target: str) -> dict | None:
    target = str(target or "")
    family = target[7:].lower() if target.startswith("family:") else ""
    for area in load():
        for monster in templates_for(bestiary, area["id"], bosses=None):
            if monster.name.lower() == target.lower() or (family and monster.family.lower() == family):
                return area
    return None
