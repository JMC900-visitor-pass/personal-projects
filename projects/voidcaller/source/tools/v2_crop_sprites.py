#!/usr/bin/env python3
"""Rebuild seed-to-mature 16px crop art from the Farm Crop ledger."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import farm, v2_art


def main() -> None:
    for crop_id, crop in farm.CROPS.items():
        identity = "|".join((crop_id, str(crop.get("label") or ""), str(crop.get("seed") or "")))
        seed = hashlib.blake2s(identity.encode("utf-8"), digest_size=8).hexdigest()
        v2_art.write_crop(crop_id, seed, crop.get("sprite_family", "Nature"))
    print(f"Reforged {len(farm.CROPS)} crop sprite sets in {v2_art.ASSET_ROOT}")


if __name__ == "__main__":
    main()
