"""Deterministic village crafting backed by data/recipes.json."""
from __future__ import annotations

import json
import os
import glob

from .data import GAME_DIR

RECIPE_FILE = os.path.join(GAME_DIR, "data", "recipes.json")


def load_recipes() -> list[dict]:
    rows = []
    paths = [RECIPE_FILE] + sorted(glob.glob(os.path.join(GAME_DIR, "data", "recipes", "*.json")))
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                blob = json.load(fh)
            rows += (blob.get("recipes", []) if isinstance(blob, dict) and "recipes" in blob
                     else [blob] if isinstance(blob, dict) else blob)
        except Exception:
            continue
    out = []
    for raw in rows:
        if not isinstance(raw, dict) or not raw.get("id") or not raw.get("name"):
            continue
        ingredients = [{"item": str(x.get("item", "")),
                        "qty": max(1, int(x.get("qty", 1)))}
                       for x in (raw.get("ingredients") or []) if x.get("item")]
        result = raw.get("result") or {}
        if not ingredients or not result.get("item"):
            continue
        out.append({"id": str(raw["id"]), "name": str(raw["name"]),
                    "book": str(raw.get("book", "field_manual")),
                    "station": str(raw.get("station", "craft_shop")),
                    "level": max(1, int(raw.get("level", 1))),
                    "ingredients": ingredients,
                    "result": {"item": str(result["item"]),
                               "qty": max(1, int(result.get("qty", 1)))},
                    "gold_cost": max(0, int(raw.get("gold_cost", 0))),
                    "description": str(raw.get("description", ""))})
    return out


def view(game) -> list[dict]:
    out = []
    for recipe in load_recipes():
        if recipe["book"] not in game.craft_books:
            continue
        row = dict(recipe)
        row["ingredients"] = [{**need, "have": game.count(need["item"])}
                              for need in recipe["ingredients"]]
        row["can_craft"] = (game.gold >= recipe["gold_cost"] and all(
            need["have"] >= need["qty"] for need in row["ingredients"]))
        out.append(row)
    return out


def craft(game, recipe_id: str) -> tuple[bool, str, dict | None]:
    recipe = next((r for r in load_recipes() if r["id"] == recipe_id), None)
    if recipe is None:
        return False, "No such recipe is pinned to the bench.", None
    if recipe["book"] not in game.craft_books:
        return False, "That recipe is unknown. Buy its craft book in the village.", None
    missing = [f"{n['qty'] - game.count(n['item'])}× {n['item']}"
               for n in recipe["ingredients"] if game.count(n["item"]) < n["qty"]]
    if missing:
        return False, "Still needed: " + ", ".join(missing) + ".", recipe
    if game.gold < recipe["gold_cost"]:
        return False, f"The forge fee is {recipe['gold_cost']}g.", recipe
    for need in recipe["ingredients"]:
        game.consume(need["item"], need["qty"])
    game.gold -= recipe["gold_cost"]
    game.add_item(recipe["result"]["item"], recipe["result"]["qty"])
    return True, (f"Crafted {recipe['result']['qty']}× {recipe['result']['item']}.") , recipe


def unknown_count(game) -> int:
    return sum(1 for recipe in load_recipes() if recipe["book"] not in game.craft_books)
