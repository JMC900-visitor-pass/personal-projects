#!/usr/bin/env python3
"""Rebuild every item's deterministic 16px PNG from data/items.json.

Companion to v2_monster_sprites.py and v2_crop_sprites.py. Safe to re-run:
the art is a pure function of the item's name, kind and description, so it is
byte-identical every time unless the record itself changed.

    python3 tools/v2_item_sprites.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import v2_art


def main() -> None:
    path = ROOT / "data" / "items.json"
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"could not read {path}: {exc}")
        return
    written = 0
    for name, spec in (blob or {}).items():
        if str(name).startswith("_") or not isinstance(spec, dict):
            continue
        kind = str(spec.get("kind") or "material")
        identity = "|".join((str(name), kind, str(spec.get("desc") or "")))
        seed = hashlib.blake2s(identity.encode("utf-8"), digest_size=8).hexdigest()
        v2_art.write_item(name, seed, kind)
        written += 1
    print(f"Reforged {written} item sprites in {v2_art.ASSET_ROOT / 'items'}")


if __name__ == "__main__":
    main()
