"""A small player-tended farm made from persistent plots.

There are deliberately no workers. The hunter buys seed, chooses how many
empty plots to allocate, waits for world time to pass, then harvests by hand.
"""
from __future__ import annotations

import json
import hashlib
import math
import os
import random

from .data import GAME_DIR
from . import v2_art

FARM_FILE = os.path.join(GAME_DIR, "data", "farm.json")


def load_crops() -> dict:
    """Farm crops are Forge data. An empty crop list leaves the plots intact
    but makes planting unavailable until the designer adds a crop."""
    try:
        with open(FARM_FILE, encoding="utf-8") as fh:
            blob = json.load(fh)
        rows = blob.get("crops", []) if isinstance(blob, dict) else blob
    except Exception:
        rows = []
    out = {}
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("id") or "").strip().lower()
        if not key or key in out:
            continue
        seed, item = str(raw.get("seed") or "").strip(), str(raw.get("item") or "").strip()
        if not seed or not item:
            continue
        try:
            cycle = max(1, int(raw.get("cycle", 360)))
            amount = max(1, int(raw.get("yield", 1)))
        except (TypeError, ValueError):
            # A half-edited Forge record must not stop the whole game booting.
            continue
        try:
            seed_return = max(0, int(raw.get("seed_return", 1)))
        except (TypeError, ValueError):
            seed_return = 1
        out[key] = {"label": str(raw.get("label") or key.upper()), "seed": seed, "item": item,
                    "cycle": cycle, "yield": amount, "seed_return": seed_return,
                    "sprite_family": str(raw.get("sprite_family") or "Nature"),
                    "mark": str(raw.get("mark") or key[0].upper())[:1]}
    return out


CROPS = load_crops()
_CROPS_STAMP = None


def refresh_crops(force: bool = False) -> dict:
    """Re-read the crop ledger when the Forge has rewritten it.

    ``CROPS`` used to be read once at import, so a crop authored in the Forge
    did not exist for the running game until it was restarted.  Watching the
    file's timestamp keeps a live session honest without re-reading on every
    single frame.
    """
    global CROPS, _CROPS_STAMP
    try:
        stamp = os.path.getmtime(FARM_FILE)
    except OSError:
        stamp = None
    if force or stamp != _CROPS_STAMP:
        _CROPS_STAMP = stamp
        CROPS = load_crops()
    return CROPS


refresh_crops(force=True)

PLOT_COUNTS = (4, 9, 16, 25)
EXPAND_COSTS = (0, 240, 650, 1400)


def fresh(total_minutes: int = 0) -> dict:
    return {"last_minute": max(0, int(total_minutes)), "level": 1,
            "plots": [None for _ in range(PLOT_COUNTS[0])], "produced": {}}


def normalize(raw: dict | None, total_minutes: int = 0) -> dict:
    """Normalize plot saves and intentionally retire the old worker rota."""
    if not isinstance(raw, dict) or not isinstance(raw.get("plots"), list):
        return fresh(total_minutes)
    level = max(1, min(len(PLOT_COUNTS), int(raw.get("level", 1))))
    total = PLOT_COUNTS[level - 1]
    plots = []
    for row in raw.get("plots", [])[:total]:
        if not isinstance(row, dict) or row.get("crop") not in CROPS:
            plots.append(None)
            continue
        plots.append({"crop": str(row["crop"]),
                      "planted": max(0, int(row.get("planted", total_minutes)))})
    plots += [None] * (total - len(plots))
    return {"last_minute": max(0, int(raw.get("last_minute", total_minutes))),
            "level": level, "plots": plots,
            "produced": {str(k): max(0, int(v)) for k, v in
                         (raw.get("produced") or {}).items()}}


def tick(game) -> list[dict]:
    """Keep farm state current. Crops wait in their plots until harvested."""
    refresh_crops()
    game.farm = normalize(getattr(game, "farm", None), game.clock.total_minutes)
    game.farm["last_minute"] = game.clock.total_minutes
    return []


def view(game) -> dict:
    tick(game)
    state = game.farm
    now = game.clock.total_minutes
    plots = []
    for i, planted in enumerate(state["plots"]):
        if planted is None:
            plots.append({"index": i, "status": "empty", "mark": "."})
            continue
        crop = CROPS[planted["crop"]]
        elapsed = max(0, now - planted["planted"])
        remaining = max(0, crop["cycle"] - elapsed)
        stage_index = 3 if remaining == 0 else min(2, int(elapsed / max(1, crop["cycle"]) * 3))
        stage_name = ("seed", "sprout", "young", "mature")[stage_index]
        identity = "|".join((str(planted["crop"]), str(crop.get("label") or ""), str(crop.get("seed") or "")))
        seed = hashlib.blake2s(identity.encode("utf-8"), digest_size=8).hexdigest()
        v2_art.write_crop(planted["crop"], seed, crop.get("sprite_family") or "Nature")
        plots.append({"index": i, "status": "ready" if remaining == 0 else "growing",
                      "crop": planted["crop"], "label": crop["label"],
                      "mark": crop["mark"], "elapsed": min(elapsed, crop["cycle"]),
                      "cycle": crop["cycle"], "remaining": remaining,
                      "item": crop["item"], "yield": crop["yield"],
                      "sprite_asset": str(v2_art.crop_path(planted["crop"], stage_name))})
    total = len(plots)
    level = state["level"]
    return {"level": level, "plots": plots, "total": total,
            "cols": int(math.isqrt(total)),
            "empty": sum(1 for p in plots if p["status"] == "empty"),
            "ready": sum(1 for p in plots if p["status"] == "ready"),
            "crops": [{"key": key, **spec, "seeds": game.count(spec["seed"])}
                      for key, spec in CROPS.items()],
            "produced": dict(state["produced"]),
            "can_expand": level < len(PLOT_COUNTS),
            "expand_cost": EXPAND_COSTS[level] if level < len(PLOT_COUNTS) else 0,
            "next_total": PLOT_COUNTS[level] if level < len(PLOT_COUNTS) else total}


def plant(game, crop_key: str, qty: int) -> tuple[bool, str]:
    crop = CROPS.get(crop_key)
    if crop is None:
        return False, "That crop is not written in the farm ledger."
    state = normalize(getattr(game, "farm", None), game.clock.total_minutes)
    empty = [i for i, p in enumerate(state["plots"]) if p is None]
    if not empty:
        return False, "Every plot is already allocated."
    if game.count(crop["seed"]) <= 0:
        return False, f"Buy {crop['seed']} from the village shop first."
    qty = max(1, min(int(qty), len(empty), game.count(crop["seed"])))
    game.consume(crop["seed"], qty)
    for i in empty[:qty]:
        state["plots"][i] = {"crop": crop_key, "planted": game.clock.total_minutes}
    game.farm = state
    return True, f"Allocated {qty} plot{'s' if qty != 1 else ''} to {crop['label'].title()}."


def harvest(game) -> tuple[bool, str, list[dict]]:
    state = normalize(getattr(game, "farm", None), game.clock.total_minutes)
    now = game.clock.total_minutes
    made: dict[str, int] = {}
    for i, planted in enumerate(state["plots"]):
        if planted is None:
            continue
        crop = CROPS.get(planted["crop"])
        if crop is None or now - planted["planted"] < crop["cycle"]:
            continue
        made[crop["item"]] = made.get(crop["item"], 0) + crop["yield"]
        # A harvest hands back some of its own seed.  It averages just under
        # replacement, so a farm trends towards sustaining itself without ever
        # multiplying for free — the stall still sells seed to the unlucky.
        returned = _seed_return(crop)
        if returned:
            made[crop["seed"]] = made.get(crop["seed"], 0) + returned
        state["plots"][i] = None
    if not made:
        return False, "Nothing is ready to harvest yet.", []
    rows = []
    for name, qty in made.items():
        game.add_item(name, qty)
        state["produced"][name] = state["produced"].get(name, 0) + qty
        rows.append({"item": name, "qty": qty})
    game.farm = state
    summary = ", ".join(f"{qty}x {name}" for name, qty in made.items())
    return True, f"Harvested {summary}.", rows


def _seed_return(crop: dict) -> int:
    """0..seed_return seed back per plot, averaging a little under one."""
    ceiling = max(0, int(crop.get("seed_return", 1)))
    if ceiling <= 0:
        return 0
    return random.randint(0, ceiling)


def expand(game) -> tuple[bool, str]:
    state = normalize(getattr(game, "farm", None), game.clock.total_minutes)
    level = state["level"]
    if level >= len(PLOT_COUNTS):
        return False, "The farm already fills the whole terrace."
    cost = EXPAND_COSTS[level]
    if game.gold < cost:
        return False, f"The next terrace costs {cost}g."
    game.gold -= cost
    state["level"] = level + 1
    state["plots"] += [None] * (PLOT_COUNTS[level] - len(state["plots"]))
    game.farm = state
    return True, f"The farm expands to {len(state['plots'])} plots."


# Old action names remain harmless for migrated front ends and command clients.
def assign(game, uid: int, job_key: str) -> tuple[bool, str]:
    return False, "Farm workers have been retired. Allocate seed to plots instead."


def unassign(game, uid: int) -> tuple[bool, str]:
    return False, "There is no worker rota anymore."
