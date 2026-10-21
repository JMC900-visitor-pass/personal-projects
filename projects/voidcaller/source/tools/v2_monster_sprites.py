#!/usr/bin/env python3
"""Rebuild every creature's deterministic 16px PNG from its Forge data."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.data import load_bestiary
from engine import v2_art


def main() -> None:
    creatures = load_bestiary().all
    for creature in creatures:
        v2_art.write_monster(creature.id, creature.portrait_seed, creature.primary,
                             creature.sprite_archetype)
    print(f"Reforged {len(creatures)} monster sprites in {v2_art.ASSET_ROOT}")


if __name__ == "__main__":
    main()
