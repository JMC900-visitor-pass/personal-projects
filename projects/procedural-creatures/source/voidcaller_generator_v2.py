
from PIL import Image, ImageDraw
import random
import os
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

# ============================================================
# VOIDCALLER PROCEDURAL MONSTER GENERATOR v2
# True 16x16 sprites + deterministic seeds + 12 elemental types
# ============================================================

# ---------- SETTINGS ----------
GRID_SIZE = 16
DISPLAY_SCALE = 10
NUM_MONSTERS = 240
OUTPUT_DIR = r"E:\project\voidcaller_monsters"
MASTER_SEED = 20260902

SAVE_UPSCALED_PREVIEWS = True
SAVE_METADATA = True
SAVE_CONTACT_SHEET = True
BACKGROUND = (8, 10, 14, 255)

# ---------- TYPE PALETTES ----------
# Each type has a controlled palette. Sprites use only a handful
# of colours so they remain readable at 16x16.
TYPE_CONFIGS = {
    "Fire": {
        "palette": [(70, 22, 18), (160, 45, 24), (232, 78, 36), (255, 165, 55), (255, 226, 145)],
        "density": 0.58, "spikes": 0.72, "fragments": 0.13, "asymmetry": 0.08
    },
    "Water": {
        "palette": [(18, 47, 73), (25, 83, 128), (40, 137, 190), (91, 204, 225), (190, 244, 248)],
        "density": 0.56, "spikes": 0.15, "fragments": 0.06, "asymmetry": 0.06
    },
    "Electric": {
        "palette": [(45, 44, 16), (110, 100, 15), (220, 198, 25), (255, 232, 70), (255, 250, 190)],
        "density": 0.43, "spikes": 0.84, "fragments": 0.28, "asymmetry": 0.16
    },
    "Nature": {
        "palette": [(24, 56, 31), (39, 98, 48), (74, 151, 70), (132, 196, 92), (210, 234, 150)],
        "density": 0.60, "spikes": 0.36, "fragments": 0.08, "asymmetry": 0.12
    },
    "Earth": {
        "palette": [(52, 44, 39), (89, 70, 54), (132, 98, 66), (174, 132, 82), (218, 188, 130)],
        "density": 0.72, "spikes": 0.26, "fragments": 0.03, "asymmetry": 0.04
    },
    "Wind": {
        "palette": [(43, 58, 65), (77, 111, 118), (122, 164, 168), (175, 211, 211), (224, 241, 239)],
        "density": 0.39, "spikes": 0.30, "fragments": 0.24, "asymmetry": 0.14
    },
    "Light": {
        "palette": [(85, 77, 44), (156, 140, 67), (220, 202, 102), (255, 240, 166), (255, 252, 226)],
        "density": 0.53, "spikes": 0.18, "fragments": 0.04, "asymmetry": 0.02
    },
    "Dark": {
        "palette": [(29, 21, 40), (58, 38, 82), (95, 55, 128), (145, 78, 170), (205, 134, 224)],
        "density": 0.57, "spikes": 0.52, "fragments": 0.22, "asymmetry": 0.18
    },
    "Cosmic": {
        "palette": [(24, 22, 61), (52, 45, 117), (84, 69, 179), (150, 90, 211), (239, 132, 224)],
        "density": 0.47, "spikes": 0.32, "fragments": 0.42, "asymmetry": 0.26
    },
    "Spirit": {
        "palette": [(31, 58, 61), (42, 101, 95), (70, 157, 137), (127, 220, 191), (212, 255, 236)],
        "density": 0.40, "spikes": 0.12, "fragments": 0.30, "asymmetry": 0.18
    },
    "Primal": {
        "palette": [(58, 32, 24), (105, 52, 31), (166, 80, 38), (217, 125, 57), (245, 191, 103)],
        "density": 0.68, "spikes": 0.57, "fragments": 0.04, "asymmetry": 0.09
    },
    "Arcane": {
        "palette": [(45, 29, 69), (81, 46, 126), (129, 73, 179), (188, 108, 227), (113, 211, 235)],
        "density": 0.50, "spikes": 0.25, "fragments": 0.25, "asymmetry": 0.07
    },
}

# ---------- BODY ARCHETYPES ----------
# These are silhouette "grammars", not literal species.
# The same archetype can look completely different under another type.
ARCHETYPES = {
    "Core": {
        "widths": [0,0,1,2,3,4,5,5,5,4,4,3,2,1,0,0],
        "eye_row": 6, "leg_rows": [12,13], "floaty": False
    },
    "Brute": {
        "widths": [0,1,2,3,5,6,6,6,6,6,5,5,4,3,2,1],
        "eye_row": 5, "leg_rows": [12,13,14], "floaty": False
    },
    "Wisp": {
        "widths": [0,0,1,2,3,4,4,4,3,3,2,2,1,1,0,0],
        "eye_row": 5, "leg_rows": [], "floaty": True
    },
    "Crawler": {
        "widths": [0,0,0,1,2,3,5,6,6,6,5,4,3,2,1,0],
        "eye_row": 6, "leg_rows": [10,11,12], "floaty": False
    },
    "Tall": {
        "widths": [0,0,1,2,3,3,3,4,4,4,3,3,3,2,1,0],
        "eye_row": 5, "leg_rows": [12,13,14], "floaty": False
    },
    "Hound": {
        "widths": [0,0,0,1,2,4,5,6,6,6,5,4,3,2,1,0],
        "eye_row": 6, "leg_rows": [11,12,13], "floaty": False
    },
    "Wing": {
        "widths": [0,0,1,2,4,6,7,6,5,4,3,2,1,1,0,0],
        "eye_row": 5, "leg_rows": [11,12], "floaty": True
    },
    "Mask": {
        "widths": [0,1,2,3,4,5,5,5,5,5,4,3,2,1,0,0],
        "eye_row": 6, "leg_rows": [], "floaty": True
    }
}

@dataclass
class MonsterMeta:
    index: int
    seed: int
    element: str
    archetype: str
    eye_count: int
    density: float
    spikes: float
    fragments: float
    asymmetry: float


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def weighted_colour(rng, palette, depth):
    """Use darker colours for base and brighter colours for features."""
    depth = clamp(depth, 0.0, 1.0)
    idx = int(depth * (len(palette) - 1))
    jitter = rng.choice([-1, 0, 0, 0, 1])
    return palette[clamp(idx + jitter, 0, len(palette) - 1)]


def set_px(grid, x, y, colour):
    if 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE:
        grid[y][x] = colour


def mirror_x(x):
    return GRID_SIZE - 1 - x


def generate_base_silhouette(rng, archetype, cfg):
    """
    Builds a coherent mirrored creature using row width profiles.
    This keeps the good emergent symmetry from your original generator,
    but stops the result becoming pure static/noise.
    """
    palette = cfg["palette"]
    grid = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
    profile = ARCHETYPES[archetype]
    center_left = GRID_SIZE // 2 - 1

    for y, half_width in enumerate(profile["widths"]):
        if half_width <= 0:
            continue

        row_density = cfg["density"]

        # Natural taper and variation
        jitter = rng.choice([-1, 0, 0, 0, 1])
        half_width = clamp(half_width + jitter, 1, 7)

        # Force a central core so sprites stay coherent.
        core_width = max(1, int(half_width * 0.45))

        for offset in range(half_width):
            x = center_left - offset
            p = row_density

            if offset < core_width:
                p += 0.32
            elif offset == half_width - 1:
                p -= 0.10

            if rng.random() < p:
                # central pixels are darker / outer pixels slightly brighter
                depth = 0.20 + 0.35 * (offset / max(1, half_width - 1))
                colour = weighted_colour(rng, palette, depth)
                set_px(grid, x, y, colour)
                set_px(grid, mirror_x(x), y, colour)

    return grid


def carve_negative_space(rng, grid, amount):
    """Small symmetrical holes add faces, joints and readable internal shapes."""
    holes = rng.randint(0, 2 + int(amount * 3))
    for _ in range(holes):
        y = rng.randint(4, 11)
        x = rng.randint(4, 7)
        if rng.random() < 0.7:
            grid[y][x] = None
            grid[y][mirror_x(x)] = None


def add_eyes(rng, grid, archetype, cfg):
    palette = cfg["palette"]
    eye_row = ARCHETYPES[archetype]["eye_row"]

    # Mostly 2 eyes, but Voidcaller should occasionally produce stranger faces.
    eye_count = rng.choices([0,1,2,3,4], weights=[4,5,66,15,10], k=1)[0]
    eye_colour = palette[-1]

    if eye_count == 0:
        return eye_count

    if eye_count == 1:
        set_px(grid, 7 if rng.random() < 0.5 else 8, eye_row, eye_colour)

    elif eye_count == 2:
        gap = rng.choice([1,2,2,3])
        set_px(grid, 7-gap, eye_row, eye_colour)
        set_px(grid, 8+gap, eye_row, eye_colour)

    elif eye_count == 3:
        set_px(grid, 5, eye_row, eye_colour)
        set_px(grid, 7, eye_row, eye_colour)
        set_px(grid, 10, eye_row, eye_colour)

    else:
        for x in [5,7,8,10]:
            set_px(grid, x, eye_row, eye_colour)

    # Dark eye sockets around some bright eyes
    socket = palette[0]
    if rng.random() < 0.55:
        for x in range(3,13):
            if grid[eye_row][x] == eye_colour:
                for sx in (x-1, x+1):
                    if 0 <= sx < GRID_SIZE and grid[eye_row][sx] is None:
                        grid[eye_row][sx] = socket

    return eye_count


def add_horns_spikes(rng, grid, cfg):
    if rng.random() > cfg["spikes"]:
        return

    palette = cfg["palette"]
    colour = palette[min(3, len(palette)-1)]

    # Top horns
    horn_style = rng.choice(["short","wide","crown","side"])
    if horn_style == "short":
        for x in [5,10]:
            set_px(grid, x, 2, colour)
            set_px(grid, x, 1, colour)
    elif horn_style == "wide":
        for x in [3,12]:
            set_px(grid, x, 4, colour)
            set_px(grid, x, 3, colour)
    elif horn_style == "crown":
        for x in [5,7,8,10]:
            set_px(grid, x, 2, colour)
    else:
        for x,y in [(2,6),(13,6),(3,5),(12,5)]:
            set_px(grid, x, y, colour)


def add_limbs(rng, grid, archetype, cfg):
    palette = cfg["palette"]
    profile = ARCHETYPES[archetype]
    colour = palette[1]

    if profile["floaty"]:
        # tapered ghost/energy tail
        if rng.random() < 0.75:
            for y, xs in [(11,[6,9]), (12,[7,8]), (13,[7]), (14,[8])]:
                for x in xs:
                    if rng.random() < 0.8:
                        set_px(grid, x, y, colour)
        return

    if not profile["leg_rows"]:
        return

    leg_style = rng.choice(["two","four","stilt","claw"])
    if leg_style == "two":
        for y in profile["leg_rows"]:
            set_px(grid, 5, y, colour)
            set_px(grid, 10, y, colour)
    elif leg_style == "four":
        for y in profile["leg_rows"][:2]:
            for x in [3,6,9,12]:
                set_px(grid, x, y, colour)
    elif leg_style == "stilt":
        for y in profile["leg_rows"]:
            set_px(grid, 4, y, colour)
            set_px(grid, 11, y, colour)
        set_px(grid, 3, profile["leg_rows"][-1], colour)
        set_px(grid, 12, profile["leg_rows"][-1], colour)
    else:
        y = profile["leg_rows"][0]
        for x in [2,3,12,13]:
            set_px(grid, x, y, colour)


def add_type_signature(rng, grid, element, cfg):
    """Small visual rules that help each elemental family read differently."""
    palette = cfg["palette"]
    bright = palette[-1]
    mid = palette[-2]

    if element == "Fire":
        # rising flame tips
        for _ in range(rng.randint(1,3)):
            x = rng.choice([4,5,6,9,10,11])
            y = rng.choice([0,1,2,3])
            set_px(grid, x, y, rng.choice([mid, bright]))

    elif element == "Water":
        # round droplets / fins near sides
        for x,y in rng.sample([(2,7),(13,7),(3,9),(12,9),(4,12),(11,12)], k=2):
            set_px(grid, x, y, bright)

    elif element == "Electric":
        # zig-zag sparks
        for x,y in rng.sample([(2,4),(13,4),(3,7),(12,7),(2,10),(13,10)], k=3):
            set_px(grid, x, y, bright)

    elif element == "Nature":
        # leaf-like paired tips
        for x,y in [(3,5),(12,5),(4,3),(11,3)]:
            if rng.random() < 0.55:
                set_px(grid, x, y, mid)

    elif element == "Earth":
        # blocky feet / shoulders
        for x,y in [(2,7),(3,7),(12,7),(13,7),(4,13),(5,13),(10,13),(11,13)]:
            if rng.random() < 0.65:
                set_px(grid, x, y, mid)

    elif element == "Wind":
        # swept detached pixels
        side = rng.choice([-1,1])
        coords = [(1 if side < 0 else 14,5),(2 if side < 0 else 13,7),(0 if side < 0 else 15,9)]
        for x,y in coords:
            if rng.random() < 0.75:
                set_px(grid, x, y, bright)

    elif element == "Light":
        # halo
        for x,y in [(6,1),(7,0),(8,0),(9,1)]:
            set_px(grid, x, y, bright)

    elif element == "Dark":
        # void holes
        for _ in range(rng.randint(1,3)):
            x = rng.randint(4,7)
            y = rng.randint(5,10)
            grid[y][x] = None
            if rng.random() < 0.5:
                grid[y][mirror_x(x)] = None

    elif element == "Cosmic":
        # orbiting motes
        for x,y in rng.sample([(1,4),(14,4),(1,10),(14,10),(4,1),(11,1),(4,14),(11,14)], k=3):
            set_px(grid, x, y, bright)

    elif element == "Spirit":
        # trailing ectoplasm
        for x,y in [(5,13),(7,14),(9,13),(10,15)]:
            if rng.random() < 0.65:
                set_px(grid, x, y, bright)

    elif element == "Primal":
        # claws / fangs
        for x,y in [(4,8),(5,8),(10,8),(11,8),(3,12),(12,12)]:
            if rng.random() < 0.6:
                set_px(grid, x, y, bright)

    elif element == "Arcane":
        # rune/core diamond approximation
        for x,y in [(7,8),(8,8),(7,9),(8,9)]:
            set_px(grid, x, y, bright)


def apply_controlled_asymmetry(rng, grid, cfg):
    """
    Your original symmetry remains the backbone.
    We then deliberately break a few pixels to make monsters feel alive/digital.
    """
    count = int(cfg["asymmetry"] * 18)
    for _ in range(rng.randint(0, max(1, count))):
        x = rng.randrange(GRID_SIZE)
        y = rng.randrange(2, 14)

        if grid[y][x] is not None and rng.random() < 0.55:
            grid[y][x] = None
        elif grid[y][x] is None and rng.random() < 0.45:
            grid[y][x] = rng.choice(cfg["palette"][1:4])


def add_fragments(rng, grid, cfg):
    count = rng.randint(0, int(cfg["fragments"] * 10) + 1)
    available = [(x,y) for y in range(1,15) for x in [0,1,2,13,14,15]]
    rng.shuffle(available)

    for x,y in available[:count]:
        if rng.random() < 0.8:
            grid[y][x] = rng.choice(cfg["palette"][2:])


def row_shift_glitch(rng, grid, cfg):
    if rng.random() > cfg["fragments"] * 0.65:
        return

    y = rng.randint(4,11)
    shift = rng.choice([-1,1])
    row = grid[y][:]
    new_row = [None] * GRID_SIZE
    for x, c in enumerate(row):
        nx = x + shift
        if 0 <= nx < GRID_SIZE:
            new_row[nx] = c
    grid[y] = new_row


def render_grid(grid):
    img = Image.new("RGBA", (GRID_SIZE, GRID_SIZE), BACKGROUND)
    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            colour = grid[y][x]
            if colour is not None:
                img.putpixel((x,y), (*colour[:3], 255))
    return img


def generate_monster(seed, element=None, archetype=None, index=0):
    rng = random.Random(seed)

    if element is None:
        element = rng.choice(list(TYPE_CONFIGS))
    if archetype is None:
        archetype = rng.choice(list(ARCHETYPES))

    cfg = TYPE_CONFIGS[element]

    grid = generate_base_silhouette(rng, archetype, cfg)
    carve_negative_space(rng, grid, cfg["asymmetry"])
    eye_count = add_eyes(rng, grid, archetype, cfg)
    add_horns_spikes(rng, grid, cfg)
    add_limbs(rng, grid, archetype, cfg)
    add_type_signature(rng, grid, element, cfg)
    apply_controlled_asymmetry(rng, grid, cfg)
    add_fragments(rng, grid, cfg)
    row_shift_glitch(rng, grid, cfg)

    meta = MonsterMeta(
        index=index,
        seed=seed,
        element=element,
        archetype=archetype,
        eye_count=eye_count,
        density=cfg["density"],
        spikes=cfg["spikes"],
        fragments=cfg["fragments"],
        asymmetry=cfg["asymmetry"],
    )

    return render_grid(grid), meta


def make_contact_sheet(entries, path):
    cols = 12
    cell = 96
    rows = (len(entries) + cols - 1) // cols

    sheet = Image.new("RGB", (cols * cell, rows * cell), (18,20,25))
    draw = ImageDraw.Draw(sheet)

    for i, (img, meta) in enumerate(entries):
        cx = (i % cols) * cell
        cy = (i // cols) * cell

        preview = img.resize((64,64), Image.Resampling.NEAREST).convert("RGB")
        sheet.paste(preview, (cx+16, cy+4))

        # Pillow default font; intentionally tiny so no font dependency required.
        draw.text((cx+4, cy+70), f"{meta.element[:4]} {meta.archetype[:4]}", fill=(230,230,235))
        draw.text((cx+4, cy+82), f"{meta.seed % 100000:05d}", fill=(130,135,145))

    sheet.save(path)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    rng = random.Random(MASTER_SEED)

    metadata = []
    sheet_entries = []

    type_names = list(TYPE_CONFIGS)
    archetypes = list(ARCHETYPES)

    for i in range(NUM_MONSTERS):
        # Balanced type distribution instead of purely random types.
        element = type_names[i % len(type_names)]
        archetype = rng.choice(archetypes)
        seed = rng.randrange(1, 2_147_483_647)

        img, meta = generate_monster(
            seed=seed,
            element=element,
            archetype=archetype,
            index=i
        )

        type_dir = os.path.join(OUTPUT_DIR, element.lower())
        os.makedirs(type_dir, exist_ok=True)

        basename = f"{element.lower()}_{archetype.lower()}_{seed}"
        img.save(os.path.join(type_dir, basename + ".png"))

        if SAVE_UPSCALED_PREVIEWS:
            preview = img.resize(
                (GRID_SIZE * DISPLAY_SCALE, GRID_SIZE * DISPLAY_SCALE),
                Image.Resampling.NEAREST
            )
            preview.save(os.path.join(type_dir, basename + "_preview.png"))

        metadata.append(asdict(meta))
        sheet_entries.append((img, meta))

    if SAVE_METADATA:
        with open(os.path.join(OUTPUT_DIR, "monsters.json"), "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

    if SAVE_CONTACT_SHEET:
        make_contact_sheet(
            sheet_entries,
            os.path.join(OUTPUT_DIR, "voidcaller_contact_sheet.png")
        )

    print(f"Generated {NUM_MONSTERS} monsters in: {OUTPUT_DIR}")
    print("Each monster has:")
    print(" - true 16x16 sprite")
    print(" - deterministic seed")
    print(" - elemental type")
    print(" - body archetype")
    print(" - optional large preview")
    print(" - JSON metadata")
    print(" - contact sheet")


if __name__ == "__main__":
    main()
