"""Deterministic 16px art made from Forge data.

The game never needs an image model or a network call for creature art.  A
creature's saved ``portrait_seed``, combat Type, and optional silhouette are
enough to recreate its PNG exactly.  The small PNG writer keeps this pipeline
dependency-free, so Forge can use it on a fresh Mac installation.
"""
from __future__ import annotations

import hashlib
import os
import random
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_ROOT = ROOT / "assets" / "V2"
GRID = 16

PALETTES = {
    "Fire": [(70,22,18), (160,45,24), (232,78,36), (255,165,55)],
    "Water": [(18,47,73), (25,83,128), (40,137,190), (190,244,248)],
    "Electric": [(45,44,16), (110,100,15), (220,198,25), (255,232,70)],
    "Nature": [(24,56,31), (39,98,48), (74,151,70), (210,234,150)],
    "Earth": [(52,44,39), (89,70,54), (132,98,66), (218,188,130)],
    "Wind": [(43,58,65), (77,111,118), (122,164,168), (224,241,239)],
    "Light": [(85,77,44), (156,140,67), (220,202,102), (255,240,166)],
    "Dark": [(29,21,40), (58,38,82), (95,55,128), (205,134,224)],
    "Cosmic": [(24,22,61), (52,45,117), (84,69,179), (239,132,224)],
    "Spirit": [(31,58,61), (42,101,95), (70,157,137), (212,255,236)],
    "Primal": [(58,32,24), (105,52,31), (166,80,38), (245,191,103)],
    "Arcane": [(45,29,69), (81,46,126), (129,73,179), (113,211,235)],
}
ARCHETYPES = ("Core", "Brute", "Wisp", "Crawler", "Tall", "Hound", "Wing", "Mask")


def _safe(value: object) -> str:
    return "".join(c for c in str(value or "untitled") if c.isalnum() or c in "-_") or "untitled"


def _seed(seed: object) -> int:
    text = str(seed or "").strip()
    try:
        return int(text[:16], 16)
    except ValueError:
        return int.from_bytes(hashlib.blake2s(text.encode(), digest_size=8).digest(), "big")


def _png(grid: list[list[tuple[int, int, int] | None]]) -> bytes:
    raw = b"".join(b"\x00" + b"".join(
        bytes((*pixel, 255)) if pixel else b"\x00\x00\x00\x00" for pixel in row)
        for row in grid)
    def chunk(name: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", GRID, GRID, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def monster_grid(seed: object, element: str = "Primal", archetype: str = "Core") -> list[list[tuple[int, int, int] | None]]:
    """Make a readable mirrored pixel creature from stable authored data."""
    rng = random.Random(_seed(seed))
    palette = PALETTES.get(str(element).title(), PALETTES["Primal"])
    kind = archetype.title() if archetype.title() in ARCHETYPES else "Core"
    grid = [[None for _ in range(GRID)] for _ in range(GRID)]
    width = {"Wisp": 4, "Tall": 4, "Wing": 6, "Crawler": 6, "Brute": 6, "Hound": 6, "Mask": 5}.get(kind, 5)
    top, bottom = (3, 13) if kind in ("Tall", "Wisp") else (2, 13)
    for y in range(top, bottom):
        phase = (y - top) / max(1, bottom - top - 1)
        taper = 1.0 - abs(phase - .45) * (1.35 if kind != "Brute" else .7)
        half = max(1, min(7, int(width * taper + rng.choice((0, 0, 0, 1, -1)))))
        for off in range(half):
            if off and rng.random() > .82:
                continue
            colour = palette[min(len(palette) - 1, 1 + int(rng.random() * 2))]
            for x in (7 - off, 8 + off):
                grid[y][x] = colour
    # Eyes and a small type-specific silhouette accent.
    eye = 6 if kind not in ("Tall", "Wisp") else 5
    grid[eye][6], grid[eye][9] = palette[-1], palette[-1]
    if kind in ("Brute", "Hound", "Crawler"):
        for x in (3, 12): grid[11][x] = palette[1]
    if kind in ("Wing", "Wisp", "Cosmic", "Spirit"):
        for x, y in ((2, 6), (13, 6), (3, 7), (12, 7)): grid[y][x] = palette[2]
    if element in ("Fire", "Electric", "Arcane"):
        for x in (5, 10): grid[2][x] = palette[-1]
    if element in ("Nature", "Earth", "Primal"):
        for x in (5, 10): grid[13][x] = palette[1]
    return grid


def monster_path(monster_id: object) -> Path:
    return ASSET_ROOT / "monsters" / f"{_safe(monster_id)}.png"


def write_monster(monster_id: object, portrait_seed: object, element: str, archetype: str = "Core") -> str:
    path = monster_path(monster_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png(monster_grid(portrait_seed or monster_id, element, archetype)))
    return str(path)


def crop_path(crop_id: object, stage: str) -> Path:
    return ASSET_ROOT / "crops" / _safe(crop_id) / f"{_safe(stage)}.png"


def crop_grid(seed: object, family: str, stage: int) -> list[list[tuple[int, int, int] | None]]:
    rng = random.Random(_seed(seed) + stage * 997)
    palette = PALETTES.get(str(family).title(), PALETTES["Nature"])
    grid = [[None for _ in range(GRID)] for _ in range(GRID)]
    if stage == 0:
        for x, y in ((7, 8), (8, 8), (7, 9), (8, 9)): grid[y][x] = palette[2]
        return grid
    height = (3, 6, 9, 11)[min(3, stage - 1)]
    for n in range(height): grid[14 - n][7 + (n // 5 if rng.random() > .7 else 0)] = palette[1]
    for y in (13 - height // 3, 13 - (height * 2) // 3):
        for x in (5, 6, 9, 10): grid[y][x] = palette[2]
    if stage >= 3:
        for x, y in ((7, 3), (8, 3), (6, 4), (9, 4)): grid[y][x] = palette[-1]
    return grid


def write_crop(crop_id: object, seed: object, family: str = "Nature") -> list[str]:
    names = ("seed", "sprout", "young", "mature")
    written = []
    for stage, name in enumerate(names):
        path = crop_path(crop_id, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_png(crop_grid(seed, family, stage)))
        written.append(str(path))
    return written


# --- items ------------------------------------------------------------------
# Materials, weapons, armour and seeds get the same treatment as creatures: a
# stable seed in, a deterministic 16px PNG out, no network and no image model.
#
# TO REPLACE THIS WITH YOUR OWN ART: rewrite `item_grid` only.  It must return
# a 16x16 list of rows, each entry either an (r, g, b) tuple or None for a
# transparent pixel.  Everything else — the PNG writer, the file naming, the
# Forge hook that calls it on save — keeps working untouched.
ITEM_PALETTES = {
    "material":  [(38,34,30), (86,74,60), (140,120,92), (214,196,150)],
    "weapon":    [(30,32,40), (74,80,96), (140,150,170), (232,240,250)],
    "armor":     [(34,30,26), (88,72,52), (150,124,84), (226,204,150)],
    "seed":      [(28,44,26), (54,92,46), (96,146,68), (198,226,140)],
    "consumable":[(44,26,44), (96,50,96), (158,84,150), (238,178,226)],
    "accessory": [(44,38,20), (104,88,36), (176,150,60), (248,226,140)],
    "treasure":  [(56,44,12), (128,100,24), (206,164,44), (255,232,140)],
    "key":       [(40,40,44), (92,92,100), (150,150,160), (236,236,244)],
}
ITEM_KINDS = tuple(ITEM_PALETTES)


def item_grid(seed: object, kind: str = "material") -> list[list[tuple[int, int, int] | None]]:
    """A small mirrored icon whose silhouette reads as its item kind."""
    rng = random.Random(_seed(seed))
    palette = ITEM_PALETTES.get(str(kind).casefold(), ITEM_PALETTES["material"])
    grid = [[None for _ in range(GRID)] for _ in range(GRID)]
    shape = str(kind).casefold()

    def put(x, y, colour):
        if 0 <= x < GRID and 0 <= y < GRID:
            grid[y][x] = colour

    if shape == "weapon":
        for y in range(3, 12):                       # a blade down the centre
            for x in (7, 8):
                put(x, y, palette[2 if y > 4 else 3])
        for x in range(5, 11):
            put(x, 12, palette[1])                   # crossguard
        for y in (13, 14):
            put(7, y, palette[1]); put(8, y, palette[1])
    elif shape == "armor":
        for y in range(3, 13):
            span = 5 - abs(y - 7) // 3
            for off in range(span):
                colour = palette[2] if off < span - 1 else palette[1]
                put(7 - off, y, colour); put(8 + off, y, colour)
        for x in (5, 10):
            put(x, 5, palette[3])                    # shoulder highlight, kept
            put(x, 6, palette[3])                    # wide so it is not a face
    elif shape == "seed":
        for y in range(6, 12):
            span = 3 - abs(y - 8) // 2
            for off in range(span):
                put(7 - off, y, palette[2]); put(8 + off, y, palette[2])
        put(7, 5, palette[1]); put(8, 4, palette[1]); put(9, 4, palette[3])
    elif shape in ("consumable", "treasure"):
        for y in range(5, 13):
            span = 4 if 6 < y < 12 else 2
            for off in range(span):
                put(7 - off, y, palette[2]); put(8 + off, y, palette[2])
        for x in (6, 7, 8, 9):
            put(x, 4, palette[1])                    # stopper / lid
        put(6, 7, palette[3]); put(6, 8, palette[3])
    else:                                            # material, accessory, key
        for y in range(4, 13):
            phase = (y - 4) / 8.0
            span = max(1, int(4 * (1.0 - abs(phase - 0.5) * 1.4)))
            for off in range(span):
                if off and rng.random() > 0.86:
                    continue
                colour = palette[1 + int(rng.random() * 2)]
                put(7 - off, y, colour); put(8 + off, y, colour)
        put(6, 6, palette[3]); put(9, 9, palette[3])
    return grid


def item_path(item_name: object) -> Path:
    return ASSET_ROOT / "items" / f"{_safe(item_name)}.png"


def write_item(item_name: object, seed: object = None, kind: str = "material") -> str:
    path = item_path(item_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png(item_grid(seed or item_name, kind)))
    return str(path)
