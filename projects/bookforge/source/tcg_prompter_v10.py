#!/usr/bin/env python3
"""
TCG Card Art Prompt Generator  v10.0  —  Anime + Cartoon Shade Edition
────────────────────────────────────────────────────────────────────────
Type your idea → agent distills it into 3 filmmaker-structured prompts.

What's different from v9:
  - Shade STYLES replace IP vibes. You pick a rendering TECHNIQUE
    (Clean Cel Anime, Painterly Anime, Bold Cartoon, etc.) not a franchise.
  - Prompts use a 4-part filmmaker structure instead of tag lists:
      SUBJECT     — who/what, physical traits, equipment, expression
      SETTING     — environment, background, atmosphere, scale
      COMPOSITION — shot distance, camera angle, lens feel
      STYLE       — light source, color temperature, shade technique
  - Copy-paste output is one coherent descriptive paragraph that SDXL
    reads as a scene, not a keyword dump.

Two modes:
  CREATIVE (default) — 3 different design angles on the idea
  STRICT   (:strict) — same creature, 3 different shots (attack/idle/portrait)

Image models : WAI Illustrious SDXL v160  |  Nova Anime XL
Shade styles : auto-detected per prompt (or lock with :switch-style)
Rarity       : common / uncommon / rare / legendary / mythic
Output       : 3 prompt variations per idea
LLM backend  : any local Ollama model
"""

import sys, json, re, os, urllib.request, urllib.error
from datetime import datetime

OLLAMA_BASE      = "http://localhost:11434"
STREAM           = True
DEBUG            = False
STRICT_MODE      = False   # toggle with :strict
FAST_MODE        = False   # toggle with :fast
EXTRA_NEGATIVES  = []      # persistent negative tags
HISTORY          = []      # past generations (capped at 20)
HISTORY_MAX      = 20


# ══════════════════════════════════════════════════════════════════════
#  THINKING-ONLY MODEL DETECTION
# ══════════════════════════════════════════════════════════════════════
THINKING_FAMILIES = {
    "nemotron_h_moe", "qwen3moe", "qwen3vlmoe",
    "deepseek_v3", "deepseek_r1",
}
THINKING_NAME_HINTS = ("thinking", "reasoning", "-r1", "cascade", "qwq")


# ══════════════════════════════════════════════════════════════════════
#  SHADE STYLES
#  Technique-based rendering descriptors — no IP, no franchise.
#  Each style tells the LLM HOW to describe the artistic treatment
#  in the STYLE section of the 4-part prompt.
# ══════════════════════════════════════════════════════════════════════
SHADE_STYLES = {
    "1": {
        "label":   "Anime — Clean Cel",
        "mood":    "crisp outlines · 2-tone hard shadows · vibrant palette",
        "color":   "\033[96m",
        "description": (
            "Clean, precise ink outlines with uniform stroke weight. "
            "Hard-edged cel shading using exactly two shadow tones — "
            "a mid-shadow and a deep-shadow — no soft gradients. "
            "Vibrant saturated colors with flat fill areas. "
            "Bright specular highlights as sharp white flares. "
            "Thin rim light separating subject from background."
        ),
        "style_words": (
            "clean anime line art, crisp ink outlines, hard cel shading, "
            "2-tone shadow, flat color fills, vibrant saturated palette, "
            "sharp specular highlights, thin rim light"
        ),
        "neg_extra": "painterly, soft gradients, blended shadows, airbrush, thick outlines, western cartoon",
    },
    "2": {
        "label":   "Anime — Painterly",
        "mood":    "soft blends · watercolor wash · semi-realistic light",
        "color":   "\033[94m",
        "description": (
            "Softly blended shading with no hard shadow edges — "
            "light flows across the form with ambient occlusion in recesses. "
            "Backgrounds use a loose watercolor wash quality. "
            "Semi-realistic rendering with warm-cool light separation. "
            "Linework may fade or dissolve into color at edges. "
            "Rich muted tones with deliberate accent color pops."
        ),
        "style_words": (
            "painterly anime style, soft blended shading, ambient occlusion, "
            "watercolor background wash, semi-realistic rendering, "
            "warm-cool light separation, muted tones with color accents"
        ),
        "neg_extra": "hard cel shading, flat fills, thick outlines, western cartoon, photorealistic",
    },
    "3": {
        "label":   "Anime — High Contrast",
        "mood":    "deep shadows · dramatic rim light · dark atmosphere",
        "color":   "\033[90m",
        "description": (
            "Extreme light-dark contrast — large areas of pure deep shadow. "
            "Subject lit by a single strong directional source "
            "creating a dramatic rim or backlight silhouette effect. "
            "Limited palette (3-4 colors max) with one high-saturation accent. "
            "Ink wash or flat-black shadow pools in background. "
            "Linework heavy at shadow edges, dissolving in lit areas."
        ),
        "style_words": (
            "high contrast anime illustration, deep shadow pools, "
            "dramatic rim lighting, limited dark palette, "
            "single-source directional light, ink wash background, "
            "heavy shadow linework"
        ),
        "neg_extra": "soft gradients, bright cheerful colors, western cartoon, flat fills, low contrast",
    },
    "4": {
        "label":   "Cartoon — Bold Pop",
        "mood":    "thick outlines · exaggerated shapes · graphic flat color",
        "color":   "\033[93m",
        "description": (
            "Heavy uniform black outlines (visually thick, cartoon-weight). "
            "Exaggerated proportions — oversized heads, chunky limbs, "
            "strong readable silhouettes. Flat color fills with "
            "minimal shading (one shadow tone at most, as a flat shape). "
            "Primary and secondary color palette — bold, graphic, high-chroma. "
            "Design must read clearly as a flat silhouette."
        ),
        "style_words": (
            "bold cartoon illustration, thick black outlines, "
            "exaggerated proportions, flat color fills, graphic pop style, "
            "bold primary palette, strong readable silhouette"
        ),
        "neg_extra": "anime shading, cel shading, screen tone, manga, soft gradients, photorealistic",
    },
    "5": {
        "label":   "Cartoon — Retro Flat",
        "mood":    "vintage animation · limited palette · halftone warmth",
        "color":   "\033[92m",
        "description": (
            "Vintage animation aesthetic from the mid-20th century. "
            "Strictly limited color palette (4-6 colors total). "
            "Shadow expressed as halftone dot patterns or flat offset shapes. "
            "Slightly warm, slightly desaturated tones — aged and nostalgic. "
            "Lines may vary in weight, loose and expressive. "
            "Background uses simplified flat shapes, no complex rendering."
        ),
        "style_words": (
            "retro cartoon style, limited color palette, halftone dot texture, "
            "vintage animation aesthetic, warm desaturated tones, "
            "expressive variable linework, flat simplified background"
        ),
        "neg_extra": "modern anime, cel shading, photorealistic, complex rendering, neon colors",
    },
    "6": {
        "label":   "Ink & Render",
        "mood":    "expressive linework · crosshatch shadows · tonal depth",
        "color":   "\033[95m",
        "description": (
            "Expressive pen-and-ink linework as the primary rendering method. "
            "Shadows built through hatching, crosshatching, or stipple texture — "
            "not flat fills. Linework varies in weight and energy: "
            "heavy at edges, lighter in mid-tones. "
            "Color used sparingly (duotone or limited wash) to accent the ink. "
            "Textured paper or rough surface feel in background."
        ),
        "style_words": (
            "pen and ink illustration, expressive linework, "
            "crosshatch shadow texture, variable line weight, "
            "duotone color accent, textured paper background, "
            "tonal depth through hatching"
        ),
        "neg_extra": "flat fills, anime shading, western cartoon, photorealistic, 3d render",
    },
    "7": {
        "label":   "Auto (pick per prompt)",
        "mood":    "agent chooses the best shade style for each idea",
        "color":   "\033[37m",
        "description": "",
        "style_words": "",
        "neg_extra": "",
    },
}


# ══════════════════════════════════════════════════════════════════════
#  RARITY TIERS — visual complexity per card
# ══════════════════════════════════════════════════════════════════════
RARITY_TIERS = {
    "1": {
        "label":  "Common",
        "color":  "\033[90m",
        "hint":   "simple silhouette · 2-3 colors · reads at thumbnail size",
        "guide":  (
            "COMMON: Keep everything simple. 2-3 dominant colors. Clean silhouette. "
            "Subject has minimal gear or ornamentation. Background is a single "
            "flat environment with no complex elements. The design must read "
            "instantly at small size."
        ),
    },
    "2": {
        "label":  "Uncommon",
        "color":  "\033[92m",
        "hint":   "moderate detail · 3-4 colors · small accent flourishes",
        "guide":  (
            "UNCOMMON: Moderate detail level. 3-4 colors. Subject may have one "
            "notable accessory or feature. Background hinted with a few elements "
            "but not busy. Small glow or particle accent is acceptable."
        ),
    },
    "3": {
        "label":  "Rare",
        "color":  "\033[94m",
        "hint":   "rich detail · 5+ colors · dynamic lighting + energy",
        "guide":  (
            "RARE: Rich detail. 5+ colors with a strong deliberate palette. "
            "Dynamic directional lighting. Detailed background that supports the subject. "
            "Notable energy or elemental effects. Subject in a confident pose or action."
        ),
    },
    "4": {
        "label":  "Legendary",
        "color":  "\033[93m",
        "hint":   "extreme detail · ornate · cinematic lighting · epic scale",
        "guide":  (
            "LEGENDARY: Extreme detail and ornamentation on subject. "
            "Intricate armor, costume, anatomy, or sigils. Dramatic cinematic lighting "
            "with clear key, fill, and rim sources. Bold particle or energy effects. "
            "Epic composition — background tells its own story. Hero or boss-tier presence."
        ),
    },
    "5": {
        "label":  "Mythic",
        "color":  "\033[95m",
        "hint":   "overwhelming complexity · gold filigree · multi-layer FX",
        "guide":  (
            "MYTHIC: Overwhelming visual complexity. Gold filigree or jewel ornamentation "
            "on every surface. Multi-layered particle and energy effects. "
            "Volumetric or divine lighting — the scene radiates power. "
            "Cosmic or world-altering presence. Background fully realized with "
            "meaningful symbolic detail. Worthy of the rarest pull."
        ),
    },
}


# ══════════════════════════════════════════════════════════════════════
#  DESIGN ENGINE — 7-AXIS FORMULA
#  These axes drive what the LLM designs. They are applied internally
#  and map to the 4-part filmmaker structure:
#    Origin + Biome   → Setting description
#    Power + Function → Subject traits (auras, tools, role signals)
#    Mutation         → The unique differentiator per variation
#    Shape            → Composition framing choices
#    Density          → Controlled by Rarity tier
# ══════════════════════════════════════════════════════════════════════
DESIGN_AXES = [
    {
        "key":   "origin",
        "label": "Origin",
        "blurb": "Mythic / technological / natural root the design borrows from",
        "examples": (
            "Norse mythology · Egyptian gods · Hindu pantheon · Japanese yokai · "
            "Greek myth · Celtic legend · Sumerian · Aztec · cryptid folklore · "
            "ancient AI · alien progenitor · primordial elemental"
        ),
        "color": "\033[93m",
    },
    {
        "key":   "biome",
        "label": "Biome / Environment",
        "blurb": "Where it lives — environmental logic shapes anatomy and setting",
        "examples": (
            "deep sea trench · fungal forest · arctic tundra · volcanic vents · "
            "high desert · floating sky islands · radioactive wasteland · "
            "alien biosphere · underground caverns · coral reef · "
            "parasitic host body · void / vacuum"
        ),
        "color": "\033[92m",
    },
    {
        "key":   "power",
        "label": "Power Source",
        "blurb": "How its energy works — drives auras, light effects, transformations",
        "examples": (
            "solar / stellar · lunar tidal · electromagnetic · psionic / mind · "
            "geothermal · blood magic · soul / spirit · digital data stream · "
            "void / antimatter · sonic / vibration · time / temporal · "
            "elemental fire · crystalline resonance · parasitic drain"
        ),
        "color": "\033[94m",
    },
    {
        "key":   "function",
        "label": "Function / Role",
        "blurb": "What it does in the world — informs pose, equipment, expression",
        "examples": (
            "guardian · predator · scavenger · herald / messenger · "
            "warrior champion · scout / spy · siege weapon · "
            "support / healer · trickster · oracle / seer · "
            "harvester · executioner · architect · saboteur"
        ),
        "color": "\033[95m",
    },
    {
        "key":   "mutation",
        "label": "Mutation Twist",
        "blurb": "What makes THIS variation unique — the differentiating twist",
        "examples": (
            "broken armor / battle scars · cybernetic grafts · crystalline growths · "
            "corruption / dark form · time-displaced · fused with another species · "
            "missing limb replaced by energy · ghostly translucent · "
            "overgrown / vine-wrapped · mechanical decay · feral / awakened · "
            "reversed polarity · doubled / mirrored · hatchling / juvenile form"
        ),
        "color": "\033[91m",
    },
    {
        "key":   "shape",
        "label": "Shape Language",
        "blurb": "Silhouette geometry — drives composition and framing choices",
        "examples": (
            "round / soft / friendly → centered, low angle · "
            "triangle / sharp / aggressive → Dutch tilt, extreme low angle · "
            "serpentine / flowing → wide establishing shot · "
            "skeletal / angular → high contrast, rim light emphasis · "
            "radial / mandala → overhead or centered symmetry · "
            "asymmetric / chaotic → off-balance Dutch angle"
        ),
        "color": "\033[96m",
    },
    {
        "key":   "density",
        "label": "Density Tier",
        "blurb": "Visual complexity — controlled by Rarity, not set manually",
        "examples": (
            "common — minimal detail, 2-3 colors · "
            "uncommon — moderate, small flourishes · "
            "rare — rich, dynamic lighting · "
            "legendary — extreme ornamentation, cinematic · "
            "mythic — overwhelming complexity, multi-layer FX"
        ),
        "color": "\033[35m",
    },
]


# ══════════════════════════════════════════════════════════════════════
#  IMAGE MODELS
#  Both are Illustrious-based SDXL models. They handle natural
#  language descriptions well — the 4-part filmmaker structure
#  gives them better compositional direction than tag dumps.
#  Prepend quality tags, then the scene description paragraph.
# ══════════════════════════════════════════════════════════════════════
IMAGE_MODELS = {
    "1": {
        "label":  "WAI Illustrious SDXL v160",
        "file":   "waiIllustriousSDXL_v160.safetensors",
        "color":  "\033[96m",
        "settings": {
            "Sampler":    "Euler a",
            "Steps":      "25 – 40",
            "CFG":        "5 – 7",
            "Resolution": "1024×1024+",
            "Hires":      "1.5×  |  R-ESRGAN 4x+ Anime6B  |  denoise 0.35–0.5",
            "Clip Skip":  "1",
        },
        "rules": (
            "- Prepend quality header: masterpiece, best quality, amazing quality, "
            "highres, absurdres, official art\n"
            "- Then write the 4-part scene description as a natural language paragraph.\n"
            "- The paragraph IS the positive prompt — SDXL reads it as scene direction.\n"
            "- Do NOT use bare booru tags as the body — write descriptive sentences.\n"
            "- Negative uses comma-separated tags (still works universally):\n"
            "  bad quality, worst quality, sketch, text, watermark, deformed, blurry,\n"
            "  card border, card frame, card template, ui elements, 3d render, photo"
        ),
    },
    "2": {
        "label":  "Nova Anime XL",
        "file":   "novaAnimeXL_*.safetensors",
        "color":  "\033[95m",
        "settings": {
            "Sampler":    "Euler a",
            "Steps":      "20 – 30",
            "CFG":        "4 – 6  (lower = better)",
            "Resolution": "1024×1024  |  832×1216 portrait  |  1216×832 landscape",
            "Clip Skip":  "1 – 2",
            "Denoising":  "0.65 – 0.8 (hires fix)",
        },
        "rules": (
            "- Prepend: masterpiece, best quality, amazing quality, newest, "
            "absurdres, highres, very aesthetic, 4k\n"
            "- Then write the 4-part scene description as a natural language paragraph.\n"
            "- CRITICAL: NEVER put 'trading card', 'card game', 'tcg', 'card art', "
            "'card frame' in POSITIVE.\n"
            "- Use 'fantasy illustration', 'creature illustration', 'key visual' instead.\n"
            "- Negative MUST include weighted card terms:\n"
            "  (card border:1.5), (card frame:1.5), (card template:1.5),\n"
            "  (trading card:1.5), (card layout:1.5), (game card:1.5)\n"
            "- Plus: score_4, score_5, 3d, jpeg artifacts, watermark, signature,\n"
            "  worst quality, low quality, bad anatomy, bad hands, blurry, lowres"
        ),
    },
}


# ══════════════════════════════════════════════════════════════════════
#  COLORS + WIDTH-AWARE PADDING
# ══════════════════════════════════════════════════════════════════════
class C:
    RESET   = "\033[0m";  BOLD  = "\033[1m";  DIM   = "\033[2m"
    CYAN    = "\033[96m"; YELLOW= "\033[93m"; GREEN = "\033[92m"
    RED     = "\033[91m"; MAGENTA="\033[95m"; WHITE = "\033[97m"
    BLUE    = "\033[94m"; GRAY  = "\033[90m"

USE_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def c(col, txt):
    return f"{col}{txt}{C.RESET}" if USE_COLOR else txt

def cc(d, key, txt):
    col = d.get(key, {}).get("color", C.WHITE)
    return f"{col}{txt}{C.RESET}" if USE_COLOR else txt

def cpad(col, txt, width):
    return c(col, str(txt).ljust(width))

def ccpad(d, key, txt, width):
    return cc(d, key, str(txt).ljust(width))

def _div():
    return c(C.DIM, "─" * 72)


# ══════════════════════════════════════════════════════════════════════
#  BANNER
# ══════════════════════════════════════════════════════════════════════
BANNER = r"""
  ████████╗ ██████╗ ██████╗     ██████╗ ██████╗  ██████╗ ███╗   ███╗██████╗ ████████╗███████╗██████╗
     ██╔══╝██╔════╝██╔════╝     ██╔══██╗██╔══██╗██╔═══██╗████╗ ████║██╔══██╗╚══██╔══╝██╔════╝██╔══██╗
     ██║   ██║     ██║  ███╗    ██████╔╝██████╔╝██║   ██║██╔████╔██║██████╔╝   ██║   █████╗  ██████╔╝
     ██║   ██║     ██║   ██║    ██╔═══╝ ██╔══██╗██║   ██║██║╚██╔╝██║██╔═══╝    ██║   ██╔══╝  ██╔══██╗
     ██║   ╚██████╗╚██████╔╝    ██║     ██║  ██║╚██████╔╝██║ ╚═╝ ██║██║        ██║   ███████╗██║  ██║
     ╚═╝    ╚═════╝ ╚═════╝     ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝╚═╝        ╚═╝   ╚══════╝╚═╝  ╚═╝
"""

def print_banner():
    print(c(C.CYAN, BANNER))
    print(c(C.DIM, "  v10.0  ·  Anime + Cartoon Shade Edition  ·  Filmmaker Prompt Structure  ·  Ollama"))
    print()


# ══════════════════════════════════════════════════════════════════════
#  OLLAMA — model discovery
# ══════════════════════════════════════════════════════════════════════
def fetch_models():
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
    except Exception:
        return None
    models = []
    for m in data.get("models", []):
        raw  = m.get("name", ""); det = m.get("details", {}); sb = m.get("size", 0)
        parts  = raw.split(":")
        family = det.get("family", "") or ""
        is_thinking = (family in THINKING_FAMILIES) or any(
            h in raw.lower() for h in THINKING_NAME_HINTS
        )
        models.append({
            "name":     raw,
            "short":    parts[0],
            "tag":      parts[1] if len(parts) > 1 else "latest",
            "size_gb":  round(sb / 1e9, 1) if sb else 0,
            "family":   family,
            "params":   det.get("parameter_size", ""),
            "thinking": is_thinking,
        })
    return sorted(models, key=lambda x: x["short"].lower())


def print_model_table(models):
    d = _div()
    print(d)
    print(c(C.DIM, f"  {'#':<5}{'Model':<26}{'Tag':<22}{'Size':>8}  {'Params':<10}Family"))
    print(d)
    for i, m in enumerate(models, 1):
        warn  = c(C.RED, " ⚠") if m["thinking"] else "  "
        sz    = c(C.YELLOW, f"{m['size_gb']:>6.1f} GB") if m["size_gb"] else c(C.DIM, "       ?")
        pr    = cpad(C.GREEN, m["params"], 10) if m["params"] else " " * 10
        num   = cpad(C.CYAN,  str(i),      5)
        short = cpad(C.WHITE, m["short"],  26)
        tag   = cpad(C.DIM,   m["tag"],    22)
        fam   = c(C.DIM, m["family"])
        print(f"  {num}{short}{tag}{sz}  {pr}{fam}{warn}")
    print(d)
    if any(m["thinking"] for m in models):
        print(c(C.DIM, "  ⚠ = thinking-only model — may return empty responses. Avoid if possible."))


# ══════════════════════════════════════════════════════════════════════
#  STEP 1 — Image model picker
# ══════════════════════════════════════════════════════════════════════
def select_image_model():
    print(c(C.BOLD, "\n  ── Step 1  Image generation model ──\n"))
    print(_div())
    print(c(C.DIM, f"  {'#':<5}{'Model':<32}File"))
    print(_div())
    for k, m in IMAGE_MODELS.items():
        print(f"  {cpad(C.CYAN, k+'.', 5)}"
              f"{ccpad(IMAGE_MODELS, k, m['label'], 32)}"
              f"{c(C.DIM, m['file'])}")
    print(_div())
    while True:
        try:
            raw = input(c(C.BOLD, "\n  Enter number: ")).strip()
        except (KeyboardInterrupt, EOFError):
            print(); sys.exit(0)
        if raw in IMAGE_MODELS:
            m = IMAGE_MODELS[raw]
            print(c(C.GREEN, f"\n  ✓ {cc(IMAGE_MODELS, raw, m['label'])}"))
            print(c(C.DIM, "\n  Recommended settings:"))
            for k2, v in m["settings"].items():
                print(c(C.DIM, f"    {k2:<12}: {v}"))
            return raw, m
        print(c(C.RED, f"  Enter {' or '.join(IMAGE_MODELS)}."))


# ══════════════════════════════════════════════════════════════════════
#  STEP 2 — Shade style (AUTO or manual lock up to 3)
# ══════════════════════════════════════════════════════════════════════
def select_shade_style():
    """
    Returns either:
      None            — AUTO mode (style picked per-prompt by the LLM)
      list of keys    — manual lock (up to 3, blended)
    """
    print(c(C.BOLD, "\n  ── Step 2  Shade style ──\n"))
    print(c(C.DIM, "  AUTO is recommended — the agent picks the best technique"))
    print(c(C.DIM, "  for each prompt. Lock only if you want every card in a"))
    print(c(C.DIM, "  consistent visual language (e.g. building a themed set).\n"))
    print(_div())
    print(c(C.DIM, f"  {'#':<5}{'Style':<30}Technique"))
    print(_div())
    print(f"  {cpad(C.CYAN, 'A.', 5)}"
          f"{cpad(C.GREEN, 'AUTO (recommended)', 30)}"
          f"{c(C.DIM, 'agent picks per prompt')}")
    print(c(C.DIM, "  ─" * 35))
    for k, s in SHADE_STYLES.items():
        if k == "7":
            continue  # auto option already shown above
        print(f"  {cpad(C.CYAN, k+'.', 5)}"
              f"{ccpad(SHADE_STYLES, k, s['label'], 30)}"
              f"{c(C.DIM, s['mood'])}")
    print(_div())
    print(c(C.DIM, "\n  Press Enter (or type 'A') for AUTO."))
    print(c(C.DIM, "  Or pick numbers comma-separated to lock (e.g. 1,4)."))

    while True:
        try:
            raw = input(c(C.BOLD, "\n  Style: ")).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print(); sys.exit(0)

        if raw in ("", "a", "auto"):
            print(c(C.GREEN, "\n  ✓ Shade Style: ") +
                  c(C.GREEN, c(C.BOLD, "AUTO")) +
                  c(C.DIM, " — picked per prompt"))
            return None

        parts = [p.strip() for p in raw.replace(" ", ",").split(",") if p.strip()]
        if not parts:
            print(c(C.RED, "  Enter for AUTO, or style numbers."))
            continue
        if len(parts) > 3:
            print(c(C.RED, "  Max 3 styles. Try again."))
            continue
        valid_keys = [k for k in SHADE_STYLES if k != "7"]
        if all(p in valid_keys for p in parts):
            chain = " + ".join(cc(SHADE_STYLES, k, SHADE_STYLES[k]["label"]) for k in parts)
            print(c(C.GREEN, f"\n  ✓ Style (locked): ") + chain)
            return parts
        bad = [p for p in parts if p not in valid_keys]
        print(c(C.RED, f"  Unknown: {', '.join(bad)}. Valid: A or {', '.join(valid_keys)}."))


# ══════════════════════════════════════════════════════════════════════
#  STEP 3 — Default rarity tier
# ══════════════════════════════════════════════════════════════════════
def select_rarity():
    print(c(C.BOLD, "\n  ── Step 3  Default rarity tier ──\n"))
    print(c(C.DIM, "  Sets the visual complexity for cards you generate."))
    print(c(C.DIM, "  Override anytime with :rarity\n"))
    print(_div())
    print(c(C.DIM, f"  {'#':<5}{'Tier':<28}Visual feel"))
    print(_div())
    for k, r in RARITY_TIERS.items():
        num   = cpad(C.CYAN,  k + ".", 5)
        label = ccpad(RARITY_TIERS, k, r["label"], 28)
        hint  = c(C.DIM, r["hint"])
        print(f"  {num}{label}{hint}")
    print(_div())
    while True:
        try:
            raw = input(c(C.BOLD, "\n  Enter number: ")).strip()
        except (KeyboardInterrupt, EOFError):
            print(); sys.exit(0)
        if raw in RARITY_TIERS:
            r = RARITY_TIERS[raw]
            print(c(C.GREEN, f"\n  ✓ Default rarity: {cc(RARITY_TIERS, raw, r['label'])}"))
            return raw
        print(c(C.RED, f"  Enter {' or '.join(RARITY_TIERS)}."))


# ══════════════════════════════════════════════════════════════════════
#  STEP 4 — Ollama LLM picker
# ══════════════════════════════════════════════════════════════════════
def select_llm_model(models):
    if not models:
        print(c(C.RED, "  No Ollama models found. Pull one: ollama pull llama3"))
        sys.exit(1)
    print(c(C.BOLD, "\n  ── Step 4  Ollama LLM ──\n"))
    print_model_table(models)
    while True:
        try:
            raw = input(c(C.BOLD, "\n  Enter model number: ")).strip()
        except (KeyboardInterrupt, EOFError):
            print(); sys.exit(0)
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(models):
                m = models[idx]
                if m["thinking"]:
                    print(c(C.RED, f"\n  ⚠  WARNING: {m['name']} is a thinking-only model."))
                    print(c(C.DIM, "     These often return empty responses for structured tasks."))
                    print(c(C.DIM, "     Recommended alternatives: gemma4, qwen3.5, llama3.2"))
                    confirm = input(c(C.BOLD, "\n     Use it anyway? (y/N): ")).strip().lower()
                    if confirm not in ("y", "yes"):
                        print(c(C.DIM, "     Pick a different model."))
                        continue
                print(c(C.GREEN, f"\n  ✓ LLM: {c(C.BOLD, m['name'])}"))
                if m["params"]:
                    print(c(C.DIM, f"  {m['params']}  ·  {m['size_gb']} GB  ·  {m['family']}"))
                return m["name"]
        print(c(C.RED, f"  Enter 1–{len(models)}."))


# ══════════════════════════════════════════════════════════════════════
#  EXAMPLE-LIST WRAP HELPER (used by :axes display)
# ══════════════════════════════════════════════════════════════════════
def wrap_examples(text, col, width=60, indent="  "):
    items = [t.strip() for t in text.split("·") if t.strip()]
    line  = ""
    for item in items:
        cand = f"{item} · "
        if len(line) + len(cand) > width and line:
            print(indent + c(col, line.rstrip(" ·")))
            line = cand
        else:
            line += cand
    if line:
        print(indent + c(col, line.rstrip(" ·")))


# ══════════════════════════════════════════════════════════════════════
#  SYSTEM PROMPT BUILDER
#  Outputs 4-part filmmaker-structured prompts for SDXL.
# ══════════════════════════════════════════════════════════════════════
def build_system_prompt(img_key, style_keys, rarity_key, strict=False):
    img    = IMAGE_MODELS[img_key]
    rarity = RARITY_TIERS[rarity_key]

    # ── Build shade style block ──
    styles_active = [SHADE_STYLES[k] for k in style_keys if SHADE_STYLES[k]["description"]]
    if styles_active:
        style_label = " + ".join(s["label"]       for s in styles_active)
        style_moods = " | ".join(s["mood"]         for s in styles_active)
        style_words = "  /  ".join(s["style_words"] for s in styles_active)
        neg_extras  = ", ".join(
            filter(None, (s["neg_extra"] for s in styles_active))
        )
        if len(styles_active) == 1:
            style_desc = styles_active[0]["description"]
            blend_note = "Single style — apply its full rendering description."
        else:
            style_desc = "\n".join(
                f"  [{s['label']}]: {s['description']}" for s in styles_active
            )
            blend_note = (
                f"BLENDING {len(styles_active)} styles: synthesize their techniques. "
                "Find the visual overlap (e.g. bold outlines + cel shading). "
                "Do not simply list both — find what they share and combine."
            )
    else:
        style_label = "Auto — agent chooses per variation"
        style_moods = "varies"
        style_desc  = (
            "Choose the most fitting shade style for each variation from this list:\n"
            "  1. Anime — Clean Cel: crisp outlines, hard cel shading, flat fills, vibrant palette\n"
            "  2. Anime — Painterly: soft blended shading, watercolor wash, semi-realistic\n"
            "  3. Anime — High Contrast: deep shadows, dramatic rim light, limited dark palette\n"
            "  4. Cartoon — Bold Pop: thick outlines, exaggerated shapes, flat bold colors\n"
            "  5. Cartoon — Retro Flat: vintage feel, limited palette, halftone dots, warm tones\n"
            "  6. Ink & Render: expressive linework, crosshatch shadows, tonal depth\n"
            "Pick whichever best fits the subject and mood of that variation."
        )
        style_words = "choose style per variation"
        neg_extras  = ""
        blend_note  = "Auto mode — the variation's subject drives the style choice."

    # ── Mode instruction block ──
    if strict:
        mode_block = (
            "STRICT MODE — SUBJECT LOCK:\n"
            "The user named a SPECIFIC subject. Keep it EXACTLY THE SAME across all 3 variations.\n"
            "  Variation A = ATTACK SHOT (mid-action, dynamic angle, power active)\n"
            "  Variation B = IDLE / NEUTRAL POSE (calm, signature stance, full body)\n"
            "  Variation C = PORTRAIT / CLOSE-UP (head-and-shoulders, expression focus)\n"
            "Same anatomy, colors, equipment, and design DNA across all three.\n"
            "Only POSE, FRAMING, and CAMERA ANGLE change between variations.\n"
        )
    else:
        mode_block = (
            "CREATIVE MODE — SUBJECT-RESPECTING DIVERGENCE:\n"
            "Three distinct design takes on the same SUBJECT TYPE.\n"
            "If the user said 'fire dragon' all 3 are fire dragons — different designs.\n"
            "If they said 'scout drone' all 3 are scout drones — different forms.\n"
            "NEVER substitute the core subject. Vary the design DNA (axes), not what it IS.\n"
            "  Variation A — one axis treatment (e.g. Norse origin, arctic biome)\n"
            "  Variation B — different axis treatment (e.g. cyber origin, void biome)\n"
            "  Variation C — third axis treatment (e.g. cryptid origin, fungal biome)\n"
        )

    return f"""\
You are a TCG card art director writing structured image prompts for {img['label']}.
Generate TCG-style card ARTWORK ONLY — never the full card with borders, frames, or text boxes.

=== YOUR JOB ===
The user gives you ONE short idea + a confirmed subject description.
Apply ALL the design knowledge below silently and output 3 prompt variations.

{mode_block}

=== THE 4-PART FILMMAKER STRUCTURE ===
Every variation must have FOUR clearly distinct sections:

SUBJECT — Who or what is the focal point. Describe:
  • What it is (creature type, character class, construct, spirit, etc.)
  • Physical traits: size, anatomy, distinctive features, proportions
  • Clothing, armor, markings, equipment, elemental sigils
  • Emotional state or expressive quality
  Write as 1-3 descriptive sentences. Be specific. Avoid vague adjectives like "amazing" or "cool".
  GOOD: "A four-armed stone colossus with a cracked chest cavity leaking molten gold,
         draped in a tattered battle standard, eyes blazing with solar light"
  BAD:  "A cool giant stone creature with glowing stuff"

SETTING — The world around the subject. Describe:
  • Location type: architectural, natural, cosmic, subterranean, etc.
  • Background elements that support the subject's identity
  • Atmospheric conditions: weather, light scatter, environmental mood
  • Scale references if relevant (tiny vs. world-filling)
  Write as 1-2 descriptive sentences.
  GOOD: "Standing at the rim of a collapsed volcanic caldera, obsidian columns framing
         the sky behind it, embers drifting upward through superheated air"

COMPOSITION — How the scene is framed. Describe:
  • Shot distance: extreme close-up / close-up / medium / full body / wide establishing
  • Camera angle: eye-level / low angle (looking up) / high angle / bird's eye / Dutch tilt
  • Lens feel: portrait lens compression / wide-angle expansion / macro detail
  • Subject placement: centered power pose / rule-of-thirds / silhouette emphasis
  Write as one precise sentence.
  GOOD: "Low-angle full-body shot looking up at the subject, slight Dutch tilt,
         portrait lens compression that emphasizes overwhelming scale"

STYLE — Artistic treatment and lighting. Describe:
  • Primary light source and direction (key light)
  • Color temperature: warm amber, cool violet, neutral grey, split tone, etc.
  • Apply the active shade technique (see below)
  • Line quality, rendering texture, any special surface effects
  Write as 1-2 descriptive sentences.
  GOOD: "Late-dusk sidelight, warm amber key with deep violet fill shadows;
         rendered in clean cel-shaded anime line art with crisp ink outlines,
         flat color fills, and a thin white rim light separating subject from background"

=== IMAGE MODEL RULES ===
{img['rules']}

When writing the combined copy-paste prompt, prepend the quality header, then
write SUBJECT. SETTING. COMPOSITION. STYLE. as one continuous paragraph.
The paragraph IS the positive prompt.

=== ACTIVE SHADE STYLE: {style_label} ===
Mood: {style_moods}
{blend_note}

Technique description:
{style_desc}

Style words to incorporate naturally into the STYLE section:
{style_words}

=== RARITY TIER: {rarity['label']} ===
{rarity['guide']}
Rarity controls ALL sections:
  Subject detail level — ornamentation, accessories, number of visual elements
  Setting complexity  — how much background narrative content appears
  Style intensity     — how many lighting layers, particle effects, rendering detail

=== DESIGN ENGINE — 7-AXIS FORMULA (apply silently) ===
DO NOT mention these axes in the output. Use them to generate design decisions.
  Origin   → informs Subject's cultural/mythic visual vocabulary
  Biome    → drives Setting description
  Power    → drives aura/glow/energy effects in Subject and Style
  Function → drives Subject pose, equipment, expression
  Mutation → THE differentiator — what makes this variation unique from the others
  Shape    → drives Composition framing (round → gentle centered; sharp → angled)
  Density  → controlled by Rarity above

=== NEGATIVE PROMPT GUIDANCE ===
Always include these core negatives:
  bad anatomy, bad hands, blurry, low quality, worst quality, watermark,
  signature, text, card border, card frame, card template, ui elements,
  3d render, photorealistic, photo, cropped, out of frame

Add style-specific negatives: {neg_extras or 'none'}

=== OUTPUT FORMAT — CRITICAL ===
Respond with raw JSON ONLY. No markdown, no backticks, no preamble.
Start with {{ and end with }}.

{{
  "variations": [
    {{
      "name":        "short evocative title (3-6 words)",
      "concept":     "one sentence: what makes this design take interesting",
      "subject":     "Subject paragraph (1-3 sentences)",
      "setting":     "Setting paragraph (1-2 sentences)",
      "composition": "Composition sentence",
      "style":       "Style sentence(s)",
      "negative":    "comma-separated negative tags"
    }},
    {{
      "name": "...", "concept": "...",
      "subject": "...", "setting": "...",
      "composition": "...", "style": "...", "negative": "..."
    }},
    {{
      "name": "...", "concept": "...",
      "subject": "...", "setting": "...",
      "composition": "...", "style": "...", "negative": "..."
    }}
  ]
}}
"""


# ══════════════════════════════════════════════════════════════════════
#  OLLAMA — streaming chat call
# ══════════════════════════════════════════════════════════════════════
def call_ollama(user_message, llm_model, system_prompt):
    chat_url = f"{OLLAMA_BASE}/api/chat"
    payload  = json.dumps({
        "model":    llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        "stream":  STREAM,
        "options": {"temperature": 0.65, "top_p": 0.9, "num_predict": 5000},
    }).encode()

    req = urllib.request.Request(
        chat_url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )

    content_parts, thinking_parts = [], []
    chunk_count = 0
    print(c(C.DIM, "\n  Generating"), end="", flush=True)

    with urllib.request.urlopen(req, timeout=240) as resp:
        for raw_line in resp:
            line = raw_line.decode().strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            chunk_count += 1
            msg = chunk.get("message", {})
            if isinstance(msg, dict):
                if msg.get("content"):  content_parts.append(msg["content"])
                if msg.get("thinking"): thinking_parts.append(msg["thinking"])
            if chunk_count % 10 == 0:
                print(c(C.DIM, "."), end="", flush=True)
            if chunk.get("done"):
                break
    print()

    content  = "".join(content_parts).strip()
    thinking = "".join(thinking_parts).strip()

    if DEBUG:
        print(c(C.DIM, f"  [debug] {chunk_count} chunks · "
                       f"content={len(content)}c thinking={len(thinking)}c"))

    # Fallback: mine thinking field if content is empty
    if not content and thinking and "{" in thinking and "}" in thinking:
        if DEBUG:
            print(c(C.YELLOW, "  [debug] No content — mining thinking field"))
        content = thinking

    return content


# ══════════════════════════════════════════════════════════════════════
#  PREFLIGHT INTERPRETER
#  Fast LLM call → { subject, styles }
#  If locked_styles is None (AUTO) → LLM picks 1-3 style keys.
#  If locked_styles is a list      → returned as-is.
# ══════════════════════════════════════════════════════════════════════
def interpret_subject(idea, llm_model, locked_styles, rarity_key, strict):
    rar_label = RARITY_TIERS[rarity_key]["label"]
    mode_str  = "STRICT (3 shots, same creature)" if strict else "CREATIVE (3 angles)"

    style_catalog = "\n".join(
        f'  "{k}" = {SHADE_STYLES[k]["label"]}: {SHADE_STYLES[k]["mood"]}'
        for k in SHADE_STYLES if k != "7"
    )

    auto_mode = locked_styles is None

    if auto_mode:
        interpret_system = f"""You are a creative director's assistant for a TCG card art tool.

The user gave a short idea. Do TWO things:
1. SUBJECT: write ONE short sentence (max 25 words) describing EXACTLY what
   the card art should be. Be specific about WHAT, not HOW it looks.
2. STYLES: pick 1-3 shade style keys from the catalog below that best match
   the idea's mood. Pick fewer if only one fits — don't force blends.

SHADE STYLE CATALOG:
{style_catalog}

Context:
- Rarity: {rar_label}
- Mode: {mode_str}

Respond with raw JSON ONLY (no markdown, no explanation):
{{"subject": "<sentence>", "styles": ["<key>", ...]}}

EXAMPLES:
User: "fire mech with flame cannon"
{{"subject": "A compact four-legged combat mech with a mounted flame cannon", "styles": ["1"]}}

User: "shadow witch summoning ritual"
{{"subject": "A robed witch performing a dark summoning ritual", "styles": ["3"]}}

User: "cute fluffy electric mouse creature"
{{"subject": "A small round fluffy electric-type rodent creature", "styles": ["4"]}}

User: "ancient dragon king on throne"
{{"subject": "An ancient dragon ruler seated on an ornate obsidian throne", "styles": ["2", "3"]}}
"""
    else:
        locked_label = " + ".join(SHADE_STYLES[k]["label"] for k in locked_styles)
        interpret_system = f"""You are a creative director's assistant.
The user gave a short idea for a TCG card. Write ONE short sentence
(max 25 words) describing EXACTLY what the card art should be.
Be specific about WHAT it is, not HOW it looks.

Context:
- Shade style (locked): {locked_label}
- Rarity: {rar_label}
- Mode: {mode_str}

Respond with raw JSON ONLY:
{{"subject": "<sentence>"}}
"""

    chat_url = f"{OLLAMA_BASE}/api/chat"
    payload  = json.dumps({
        "model":    llm_model,
        "messages": [
            {"role": "system", "content": interpret_system},
            {"role": "user",   "content": f"Idea: {idea}"},
        ],
        "stream":  False,
        "options": {"temperature": 0.3, "num_predict": 600},
    }).encode()

    req = urllib.request.Request(
        chat_url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )

    try:
        print(c(C.DIM, "  Interpreting..."), end="", flush=True)
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
        print(c(C.DIM, " done"))
    except Exception as e:
        print(c(C.RED, f"\n  Interpretation failed: {e}"))
        return None

    raw = ""
    msg = data.get("message", {})
    if isinstance(msg, dict):
        raw = (msg.get("content") or "").strip() or (msg.get("thinking") or "").strip()

    if DEBUG:
        print(c(C.DIM, f"  [debug] interpret raw ({len(raw)}c): {raw[:200]}"))

    if not raw:
        return None

    parsed = None
    # Strategy 1: clean parse
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy 2: find {...} block
    if parsed is None:
        s = raw.find("{"); e = raw.rfind("}") + 1
        if s != -1 and e > s:
            try:
                parsed = json.loads(raw[s:e])
            except json.JSONDecodeError:
                pass

    # Strategy 3: strip markdown fences
    if parsed is None:
        clean = re.sub(r"```(?:json)?\s*", "", raw)
        clean = re.sub(r"```", "", clean).strip()
        s = clean.find("{"); e = clean.rfind("}") + 1
        if s != -1 and e > s:
            try:
                parsed = json.loads(clean[s:e])
            except json.JSONDecodeError:
                pass

    if isinstance(parsed, dict) and parsed.get("subject"):
        subject = str(parsed["subject"]).strip()

        if auto_mode:
            picked = parsed.get("styles", [])
            if not isinstance(picked, list):
                picked = []
            valid_keys = [k for k in SHADE_STYLES if k != "7"]
            valid = []
            for v in picked:
                vstr = str(v).strip()
                if vstr in valid_keys and vstr not in valid:
                    valid.append(vstr)
                if len(valid) >= 3:
                    break
            if not valid:
                valid = ["1"]  # default to clean cel anime
            return {"subject": subject, "styles": valid}
        else:
            return {"subject": subject, "styles": list(locked_styles)}

    # Last resort: treat response as plain-text subject
    fallback = raw.strip().strip('"').strip("'").strip()
    if "\n" in fallback:
        for line in fallback.split("\n"):
            line = line.strip().strip('"').strip("'").strip()
            if line and not line.startswith("{") and not line.startswith("```"):
                fallback = line
                break
    if fallback and 5 < len(fallback) < 500:
        return {
            "subject": fallback,
            "styles":  list(locked_styles) if locked_styles else ["1"],
        }
    return None


def confirm_subject(idea, interpretation):
    """Show interpreted subject + style to user. Accept/refine/override."""
    subject = interpretation["subject"]
    styles  = interpretation["styles"]

    style_chain = " + ".join(
        cc(SHADE_STYLES, k, SHADE_STYLES[k]["label"]) for k in styles
    )

    print()
    print(c(C.DIM, "  ─── Interpreted ──────────────────────────────"))
    print(c(C.YELLOW, c(C.BOLD, f"  Subject : {subject}")))
    print(c(C.DIM, "  Style   : ") + style_chain)
    print(c(C.DIM, "  ──────────────────────────────────────────────"))
    print(c(C.DIM, "  Press Enter to accept."))
    print(c(C.DIM, "  Or type a refinement (e.g. 'female warrior, not male')."))
    print(c(C.DIM, "  Or type :s 1,4 to override style (numbers from :help)."))
    try:
        refine = input(c(C.BOLD, "  › ")).strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return None

    if not refine:
        return interpretation

    # Style override: ":s 1,4" or "style 1,4"
    low = refine.lower()
    if low.startswith(":s ") or low.startswith("style ") or low.startswith("s "):
        parts_raw = refine.split(None, 1)[1] if " " in refine else ""
        parts = [p.strip() for p in parts_raw.replace(" ", ",").split(",") if p.strip()]
        valid_keys = [k for k in SHADE_STYLES if k != "7"]
        if all(p in valid_keys for p in parts) and 1 <= len(parts) <= 3:
            interpretation["styles"] = parts
            new_chain = " + ".join(
                cc(SHADE_STYLES, k, SHADE_STYLES[k]["label"]) for k in parts
            )
            print(c(C.GREEN, f"  ✓ Style overridden: ") + new_chain)
            return interpretation
        else:
            print(c(C.RED, f"  Invalid style keys. Valid: {', '.join(valid_keys)}."))
            return interpretation

    # Free-text refinement
    interpretation["subject"] = f"{subject}. Refinement: {refine}"
    return interpretation


# ══════════════════════════════════════════════════════════════════════
#  JSON PARSING — multi-strategy + truncation repair
# ══════════════════════════════════════════════════════════════════════
def strip_fences(t):
    t = re.sub(r"```(?:json)?\s*", "", t)
    return re.sub(r"```", "", t).strip()


def repair_truncated_json(raw):
    """Attempt to salvage a truncated JSON response."""
    text = strip_fences(raw).strip()
    s    = text.find("{")
    if s == -1:
        return None
    text = text[s:]
    in_string, last_safe_comma = False, -1
    for i, ch in enumerate(text):
        if ch == '"' and (i == 0 or text[i-1] != "\\"):
            in_string = not in_string
        if ch == "," and not in_string:
            last_safe_comma = i
    if in_string and last_safe_comma > 0:
        candidate = text[:last_safe_comma] + '"'
        try:
            r = json.loads(candidate + "}")
            if isinstance(r, dict):
                r.setdefault("subject", "")
                r.setdefault("setting", "")
                r.setdefault("composition", "")
                r.setdefault("style", "")
                r.setdefault("negative", "bad quality, blurry, watermark, card border")
                return r
        except json.JSONDecodeError:
            pass
    for i in range(len(text) - 1, 0, -1):
        if text[i] == ",":
            try:
                r = json.loads(text[:i] + "}")
                if isinstance(r, dict) and "subject" in r:
                    return r
            except json.JSONDecodeError:
                continue
    return None


def parse_result(raw):
    if not raw:
        return None
    candidates = [raw.strip(), strip_fences(raw)]
    s, e = raw.find("{"), raw.rfind("}") + 1
    if s != -1 and e > s:
        candidates.append(raw[s:e].strip())
    blocks = re.findall(r"\{(?:[^{}]|\{[^{}]*\})*\}", raw, re.DOTALL)
    if blocks:
        candidates.append(max(blocks, key=len))
    sf = strip_fences(raw); s2, e2 = sf.find("{"), sf.rfind("}") + 1
    if s2 != -1 and e2 > s2:
        candidates.append(sf[s2:e2].strip())

    for cd in candidates:
        if not cd:
            continue
        try:
            r = json.loads(cd)
            if isinstance(r, dict):
                if "variations" in r and isinstance(r["variations"], list) and r["variations"]:
                    return r
                if "subject" in r:  # single variation fallback
                    return r
        except json.JSONDecodeError:
            continue
    return repair_truncated_json(raw)


# ══════════════════════════════════════════════════════════════════════
#  DISPLAY — 4-part filmmaker layout
# ══════════════════════════════════════════════════════════════════════
def wrap_print(text, col, width=66, indent="    "):
    """Print text word-wrapped at width."""
    words = text.split()
    line  = ""
    for word in words:
        cand = word + " "
        if len(line) + len(cand) > width and line:
            print(indent + c(col, line.rstrip()))
            line = cand
        else:
            line += cand
    if line:
        print(indent + c(col, line.rstrip()))


def display_results(result, llm, img_key, style_keys, rarity_key, idea):
    """Render 3 variations with 4-part filmmaker sections."""
    variations = result.get("variations", [])
    if not variations or not isinstance(variations, list):
        return False

    div        = _div()
    style_str  = " + ".join(cc(SHADE_STYLES, k, SHADE_STYLES[k]["label"]) for k in style_keys)
    rar_label  = cc(RARITY_TIERS, rarity_key, RARITY_TIERS[rarity_key]["label"])
    img_label  = cc(IMAGE_MODELS, img_key, IMAGE_MODELS[img_key]["label"])

    # ── header ──
    print(f"\n{div}")
    print(c(C.BOLD, "  Idea    : ") + c(C.WHITE, idea))
    print(c(C.BOLD, "  Style   : ") + style_str)
    print(c(C.BOLD, "  Rarity  : ") + rar_label)
    print(c(C.BOLD, "  Model   : ") + img_label)
    print(c(C.DIM,  f"  LLM     : {llm}"))
    print(div)

    labels     = ["A", "B", "C"]
    var_colors = [C.CYAN, C.MAGENTA, C.YELLOW]

    for i, var in enumerate(variations[:3]):
        letter  = labels[i] if i < len(labels) else str(i + 1)
        col     = var_colors[i] if i < len(var_colors) else C.WHITE
        name    = var.get("name",        "Untitled")
        concept = var.get("concept",     "")
        subj    = var.get("subject",     "")
        setting = var.get("setting",     "")
        comp    = var.get("composition", "")
        style   = var.get("style",       "")
        neg     = var.get("negative",    "")

        print()
        print(c(col, c(C.BOLD, f"  ╭── VARIATION {letter}  ─────────────────────────────────────")))
        print(c(col, "  │ ") + c(C.BOLD, c(C.WHITE, name)))
        if concept:
            print(c(col, "  │ ") + c(C.DIM, concept))
        print(c(col, "  ╰" + "─" * 58))
        print()

        if subj:
            print(c(C.GREEN, "    SUBJECT:"))
            wrap_print(subj, C.WHITE)
            print()

        if setting:
            print(c(C.BLUE, "    SETTING:"))
            wrap_print(setting, C.WHITE)
            print()

        if comp:
            print(c(C.YELLOW, "    COMPOSITION:"))
            wrap_print(comp, C.WHITE)
            print()

        if style:
            print(c(C.MAGENTA, "    STYLE:"))
            wrap_print(style, C.WHITE)
            print()

        if neg:
            print(c(C.RED, "    NEGATIVE:"))
            wrap_print(neg, C.RED)

    # ── copy-paste blocks ──
    print(f"\n{div}")
    print(c(C.BOLD, "\n  ── copy-paste ready ──"))
    print(c(C.DIM, "  Paste the POSITIVE as-is into SDXL. Paragraph form is intentional.\n"))

    # Get quality prefix from model rules hint
    quality_prefix = (
        "masterpiece, best quality, amazing quality, highres, absurdres"
        if img_key == "1"
        else "masterpiece, best quality, amazing quality, newest, absurdres, highres, very aesthetic, 4k"
    )

    for i, var in enumerate(variations[:3]):
        letter = labels[i] if i < len(labels) else str(i + 1)
        col    = var_colors[i] if i < len(var_colors) else C.WHITE

        # Build combined positive paragraph
        parts = [
            var.get("subject", "").strip(),
            var.get("setting", "").strip(),
            var.get("composition", "").strip(),
            var.get("style", "").strip(),
        ]
        combined = " ".join(p for p in parts if p)
        positive = f"{quality_prefix}, {combined}" if combined else quality_prefix

        neg = var.get("negative", "")
        if EXTRA_NEGATIVES:
            extra = ", ".join(EXTRA_NEGATIVES)
            neg   = f"{neg}, {extra}" if neg else extra

        print()
        print(c(col, c(C.BOLD, f"  [Variation {letter}]")))
        print(c(C.DIM, "  POSITIVE:"))
        print(f"  {positive}")
        print(c(C.DIM, "\n  NEGATIVE:"))
        print(f"  {neg}")

    print()
    return True


# ══════════════════════════════════════════════════════════════════════
#  STATUS + HELP
# ══════════════════════════════════════════════════════════════════════
def print_status(llm, img_key, style_keys, rarity_key):
    if style_keys is None:
        styles_str = c(C.GREEN, "AUTO") + c(C.DIM, " — picked per prompt")
    else:
        styles_str = " + ".join(cc(SHADE_STYLES, k, SHADE_STYLES[k]["label"]) for k in style_keys)
        styles_str += c(C.DIM, "  (locked)")
    rar_str = cc(RARITY_TIERS, rarity_key, RARITY_TIERS[rarity_key]["label"])
    if STRICT_MODE:
        mode_str = c(C.YELLOW, "STRICT  (3 shots, same creature)")
    else:
        mode_str = c(C.GREEN,  "CREATIVE (3 design angles, subject-locked)")
    print(c(C.DIM, "\n  ── current session ──"))
    print(c(C.DIM, "  Image model  : ") + cc(IMAGE_MODELS, img_key, IMAGE_MODELS[img_key]["label"]))
    print(c(C.DIM, "  Shade style  : ") + styles_str)
    print(c(C.DIM, "  Rarity       : ") + rar_str)
    print(c(C.DIM, "  Mode         : ") + mode_str)
    print(c(C.DIM, f"  LLM          : {llm}"))
    fast_str = c(C.GREEN, "ON  — skip interpreter") if FAST_MODE else c(C.DIM, "OFF")
    print(c(C.DIM, "  Fast mode    : ") + fast_str)
    if EXTRA_NEGATIVES:
        print(c(C.DIM, f"  Neg extras   : {', '.join(EXTRA_NEGATIVES)}"))
    print(c(C.DIM, f"  History      : {len(HISTORY)} entries"))
    print(c(C.DIM, f"  Debug        : {'ON' if DEBUG else 'OFF'}\n"))


CMDS = {
    ":help":          "Show this help",
    ":status":        "Show current session settings",
    ":history":       "Show past generations",
    ":save N":        "Export generation N to markdown (or :save N name.md)",
    ":export":        "Export the last generation to markdown",
    ":fast":          "Toggle fast mode (skip interpreter, halve latency)",
    ":strict":        "Toggle strict mode (3 shots vs 3 design angles)",
    ":neg add/rm":    "Manage persistent extra negatives",
    ":redo A|B|C":    "Re-roll one variation, keep the other two",
    ":switch-llm":    "Switch LLM model",
    ":switch-img":    "Switch image model (WAI / Nova)",
    ":switch-style":  "Switch shade style (auto or locked)",
    ":rarity":        "Change default rarity tier",
    ":axes":          "Show the 7 design engine axes (reference)",
    ":styles":        "List all shade styles with technique descriptions",
    ":config save":   "Save current settings to tcg_prompter.yaml",
    ":debug":         "Toggle debug output",
    ":quit":          "Exit",
}

def print_help(llm, img_key, style_keys, rarity_key):
    print(f"\n{_div()}")
    print(c(C.BOLD, "  Commands"))
    print(_div())
    for cmd, desc in CMDS.items():
        print(f"  {cpad(C.CYAN, cmd, 20)}{c(C.DIM, desc)}")
    print(_div())
    print_status(llm, img_key, style_keys, rarity_key)


def print_axes():
    print(c(C.BOLD, "\n  Design Engine — 7 Axes\n"))
    print(_div())
    for i, axis in enumerate(DESIGN_AXES, 1):
        print(c(axis["color"], c(C.BOLD, f"  {i}. {axis['label']}")))
        print(c(C.DIM, f"     {axis['blurb']}"))
        wrap_examples(axis["examples"], C.DIM, indent="     ")
        print()
    print(_div() + "\n")


def print_styles():
    print(c(C.BOLD, "\n  Shade Styles — rendering technique reference\n"))
    print(_div())
    for k, s in SHADE_STYLES.items():
        if k == "7":
            continue
        print(c(s["color"], c(C.BOLD, f"  {k}. {s['label']}")))
        print(c(C.DIM, f"     Mood: {s['mood']}"))
        # Wrap description
        words = s["description"].split()
        line  = "     "
        for word in words:
            if len(line) + len(word) + 1 > 72 and line.strip():
                print(c(C.DIM, line))
                line = "     " + word + " "
            else:
                line += word + " "
        if line.strip():
            print(c(C.DIM, line))
        print()
    print(_div() + "\n")


# ══════════════════════════════════════════════════════════════════════
#  HISTORY SYSTEM
# ══════════════════════════════════════════════════════════════════════
def history_add(idea, subject, style_keys, rarity_key, result, img_key):
    entry = {
        "id":         len(HISTORY) + 1,
        "timestamp":  datetime.now().strftime("%H:%M:%S"),
        "idea":       idea,
        "subject":    subject,
        "styles":     style_keys,
        "rarity":     rarity_key,
        "img_key":    img_key,
        "variations": result.get("variations", [])[:3],
    }
    HISTORY.append(entry)
    if len(HISTORY) > HISTORY_MAX:
        HISTORY.pop(0)
    return entry


def history_show():
    if not HISTORY:
        print(c(C.DIM, "\n  No history yet. Generate something first.\n"))
        return
    print(c(C.BOLD, f"\n  ── History ({len(HISTORY)} entries) ──\n"))
    print(_div())
    for entry in HISTORY:
        idx     = entry["id"]
        ts      = entry["timestamp"]
        idea    = entry["idea"][:40]
        rar     = RARITY_TIERS.get(entry["rarity"], {}).get("label", "?")
        sty_str = " + ".join(
            SHADE_STYLES.get(k, {}).get("label", "?")[:12]
            for k in entry.get("styles", [])
        )
        print(f"  {cpad(C.CYAN, str(idx), 4)}"
              f"{cpad(C.DIM,  ts,   10)}"
              f"{cpad(C.WHITE, idea, 42)}"
              f"{c(C.DIM, f'{rar} · {sty_str}')}")
    print(_div())
    print(c(C.DIM, "\n  Use :save N to export, :save N filename.md for custom name.\n"))


# ══════════════════════════════════════════════════════════════════════
#  MARKDOWN EXPORT
# ══════════════════════════════════════════════════════════════════════
def export_to_md(entry, filename=None):
    if filename is None:
        default_name = re.sub(r"[^a-zA-Z0-9_-]", "_", entry["idea"][:30]).strip("_")
        print(c(C.DIM, f"\n  Enter filename (without .md) or Enter for \"{default_name}\": "))
        try:
            raw = input(c(C.BOLD, "  › ")).strip()
        except (KeyboardInterrupt, EOFError):
            return None
        if not raw:
            raw = default_name
        filename = raw

    # Sanitize
    if os.sep in filename or filename.startswith("/"):
        dirn = os.path.dirname(filename)
        base = os.path.basename(filename)
        base = re.sub(r"[^a-zA-Z0-9_. -]", "_", base)
        if not base.endswith(".md"):
            base += ".md"
        filename = os.path.join(dirn, base)
    else:
        filename = re.sub(r"[^a-zA-Z0-9_. -]", "_", filename)
        if not filename.endswith(".md"):
            filename += ".md"

    styles_str = " + ".join(
        SHADE_STYLES.get(k, {}).get("label", "?") for k in entry.get("styles", [])
    )
    rar_label  = RARITY_TIERS.get(entry["rarity"],  {}).get("label", "?")
    img_label  = IMAGE_MODELS.get(entry["img_key"], {}).get("label", "?")
    quality_prefix = (
        "masterpiece, best quality, amazing quality, highres, absurdres"
        if entry["img_key"] == "1"
        else "masterpiece, best quality, amazing quality, newest, absurdres, highres, very aesthetic, 4k"
    )

    lines = []
    lines.append(f"# {entry['idea']}")
    lines.append("")
    lines.append(f"**Subject:** {entry.get('subject', entry['idea'])}")
    lines.append(f"**Shade Style:** {styles_str}")
    lines.append(f"**Rarity:** {rar_label}")
    lines.append(f"**Image model:** {img_label}")
    lines.append(f"**Generated:** {entry['timestamp']}")
    lines.append("")
    lines.append("---")
    lines.append("")

    labels = ["A", "B", "C"]
    for i, var in enumerate(entry["variations"]):
        letter = labels[i] if i < len(labels) else str(i + 1)
        lines.append(f"## Variation {letter}: {var.get('name', 'Untitled')}")
        lines.append("")
        if var.get("concept"):
            lines.append(f"*{var['concept']}*")
            lines.append("")

        lines.append("### Scene Breakdown")
        lines.append("")
        if var.get("subject"):
            lines.append(f"**Subject:** {var['subject']}")
            lines.append("")
        if var.get("setting"):
            lines.append(f"**Setting:** {var['setting']}")
            lines.append("")
        if var.get("composition"):
            lines.append(f"**Composition:** {var['composition']}")
            lines.append("")
        if var.get("style"):
            lines.append(f"**Style:** {var['style']}")
            lines.append("")

        # Build combined positive
        parts = [
            var.get("subject",     "").strip(),
            var.get("setting",     "").strip(),
            var.get("composition", "").strip(),
            var.get("style",       "").strip(),
        ]
        combined = " ".join(p for p in parts if p)
        positive = f"{quality_prefix}, {combined}" if combined else quality_prefix

        neg = var.get("negative", "")
        if EXTRA_NEGATIVES:
            extra = ", ".join(EXTRA_NEGATIVES)
            neg   = f"{neg}, {extra}" if neg else extra

        lines.append("### Positive Prompt")
        lines.append("```")
        lines.append(positive)
        lines.append("```")
        lines.append("")
        lines.append("### Negative Prompt")
        lines.append("```")
        lines.append(neg)
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

    if EXTRA_NEGATIVES:
        lines.append(f"**Persistent negatives:** {', '.join(EXTRA_NEGATIVES)}")
        lines.append("")

    content = "\n".join(lines)
    try:
        with open(filename, "w") as f:
            f.write(content)
        print(c(C.GREEN, f"\n  ✓ Saved: {os.path.abspath(filename)}\n"))
        return filename
    except Exception as e:
        print(c(C.RED, f"\n  ✗ Write failed: {e}\n"))
        return None


# ══════════════════════════════════════════════════════════════════════
#  PERSISTENT NEGATIVES
# ══════════════════════════════════════════════════════════════════════
def neg_add(tags_str):
    new_tags = [t.strip() for t in tags_str.replace(",", " ").split() if t.strip()]
    added    = [t for t in new_tags if t not in EXTRA_NEGATIVES]
    EXTRA_NEGATIVES.extend(added)
    if added:
        print(c(C.GREEN, f"  ✓ Added: {', '.join(added)}"))
    else:
        print(c(C.DIM, "  (all tags already in list)"))
    neg_show()


def neg_remove(tags_str):
    rm_tags = [t.strip() for t in tags_str.replace(",", " ").split() if t.strip()]
    removed = []
    for tag in rm_tags:
        if tag in EXTRA_NEGATIVES:
            EXTRA_NEGATIVES.remove(tag)
            removed.append(tag)
    if removed:
        print(c(C.GREEN, f"  ✓ Removed: {', '.join(removed)}"))
    else:
        print(c(C.DIM, "  (none of those tags were in list)"))
    neg_show()


def neg_show():
    if EXTRA_NEGATIVES:
        print(c(C.DIM, f"  Persistent negatives: {', '.join(EXTRA_NEGATIVES)}\n"))
    else:
        print(c(C.DIM, "  Persistent negatives: (empty)\n"))


# ══════════════════════════════════════════════════════════════════════
#  CONFIG — load/save tcg_prompter.yaml
# ══════════════════════════════════════════════════════════════════════
CONFIG_FILE = "tcg_prompter.yaml"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE) as f:
            config = {}
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if val.lower() in ("true", "yes"):
                        val = True
                    elif val.lower() in ("false", "no"):
                        val = False
                    elif val.startswith("[") and val.endswith("]"):
                        items = val[1:-1].split(",")
                        val   = [x.strip().strip('"').strip("'") for x in items if x.strip()]
                    else:
                        try:
                            val = int(val)
                        except ValueError:
                            pass
                    config[key] = val
            return config
    except Exception as e:
        print(c(C.DIM, f"  Config load warning: {e}"))
        return {}


def save_config(img_key, locked_styles, rarity_key, llm_model):
    styles_val = "auto" if locked_styles is None else f"[{', '.join(locked_styles)}]"
    neg_val    = f"[{', '.join(EXTRA_NEGATIVES)}]" if EXTRA_NEGATIVES else "[]"
    content = f"""# TCG Prompter v10 config — auto-generated
# Delete this file to go back to interactive setup

image_model: {img_key}
llm_model: {llm_model}
rarity: {rarity_key}
styles: {styles_val}
fast_mode: {str(FAST_MODE).lower()}
strict_mode: {str(STRICT_MODE).lower()}
extra_negatives: {neg_val}
"""
    try:
        with open(CONFIG_FILE, "w") as f:
            f.write(content)
        print(c(C.GREEN, f"  ✓ Config saved to {CONFIG_FILE}"))
        print(c(C.DIM,   "    Delete the file to go back to interactive setup.\n"))
    except Exception as e:
        print(c(C.RED, f"  ✗ Config save failed: {e}\n"))


# ══════════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════════════════════════════
def main():
    global DEBUG, STRICT_MODE, FAST_MODE, EXTRA_NEGATIVES
    print_banner()

    # ── auto-load config ──
    config = load_config()
    if config:
        print(c(C.DIM, f"  Loaded config from {CONFIG_FILE}"))
        FAST_MODE   = config.get("fast_mode",    False)
        STRICT_MODE = config.get("strict_mode",  False)
        if isinstance(config.get("extra_negatives"), list):
            EXTRA_NEGATIVES = config["extra_negatives"]

    print(c(C.DIM, "  Connecting to Ollama..."), end="", flush=True)
    llm_models = fetch_models()
    if llm_models is None:
        print(c(C.RED, "\n\n  ERROR: Cannot reach Ollama at " + OLLAMA_BASE))
        print(c(C.DIM, "  Run:  ollama serve"))
        sys.exit(1)
    if not llm_models:
        print(c(C.RED, "\n\n  No models pulled."))
        print(c(C.DIM, "  Run:  ollama pull qwen3.5"))
        sys.exit(1)
    n           = len(llm_models)
    n_thinking  = sum(1 for m in llm_models if m["thinking"])
    msg = f" OK  ({n} model{'s' if n != 1 else ''})"
    if n_thinking:
        msg += f", {n_thinking} flagged as thinking-only"
    print(c(C.GREEN, msg + "\n"))

    # ── Config-driven quick start ──
    if config.get("image_model") and config.get("llm_model") and config.get("rarity"):
        img_key    = str(config["image_model"])
        img_model  = IMAGE_MODELS.get(img_key, IMAGE_MODELS["1"])
        rarity_key = str(config["rarity"])
        llm_model  = str(config["llm_model"])
        styles_cfg = config.get("styles", "auto")
        if styles_cfg == "auto" or styles_cfg is True:
            locked_styles = None
        elif isinstance(styles_cfg, list):
            valid_keys    = [k for k in SHADE_STYLES if k != "7"]
            locked_styles = [str(v) for v in styles_cfg if str(v) in valid_keys]
            if not locked_styles:
                locked_styles = None
        else:
            locked_styles = None

        # Verify LLM exists
        available_names = [m["name"] for m in llm_models]
        if llm_model not in available_names:
            matches = [n for n in available_names if llm_model.split(":")[0] in n]
            if matches:
                llm_model = matches[0]
            else:
                print(c(C.YELLOW, f"  Config LLM \"{llm_model}\" not found. Falling back to picker."))
                llm_model = select_llm_model(llm_models)

        print(c(C.GREEN, "\n  ── Quick start from config ──"))
        print(c(C.DIM, f"  Image model  : {img_model.get('label', img_key)}"))
        sty_str = "AUTO" if locked_styles is None else " + ".join(
            SHADE_STYLES.get(k, {}).get("label", "?") for k in locked_styles
        )
        print(c(C.DIM, f"  Shade style  : {sty_str}"))
        print(c(C.DIM, f"  Rarity       : {RARITY_TIERS.get(rarity_key, {}).get('label', '?')}"))
        print(c(C.DIM, f"  LLM          : {llm_model}"))
        print(c(C.DIM, "\n  Use :setup to reconfigure interactively."))
    else:
        # Interactive setup — same order as v9
        img_key, img_model = select_image_model()
        locked_styles      = select_shade_style()
        rarity_key         = select_rarity()
        llm_model          = select_llm_model(llm_models)

    print()
    print_status(llm_model, img_key, locked_styles, rarity_key)
    print(c(C.DIM, "  Type your card idea, or :help for commands.\n"))

    while True:
        try:
            print(c(C.CYAN, "  What do you want on your card?"))
            user_input = input(c(C.BOLD, "  › ")).strip()
        except (KeyboardInterrupt, EOFError):
            print(c(C.DIM, "\n\n  Goodbye!"))
            break

        if not user_input:
            continue
        low = user_input.lower()

        # ── Commands ──
        if low in (":quit", ":exit", "quit", "exit", "q"):
            print(c(C.DIM, "\n  Goodbye!"))
            break

        if low in (":help", "help", "?"):
            print_help(llm_model, img_key, locked_styles, rarity_key)
            continue

        if low in (":status", "status"):
            print_status(llm_model, img_key, locked_styles, rarity_key)
            continue

        if low in (":models", "models"):
            fresh = fetch_models()
            if fresh:
                print_model_table(fresh)
            else:
                print(c(C.RED, "  Could not reach Ollama."))
            print()
            continue

        if low in (":debug", "debug"):
            DEBUG = not DEBUG
            print(c(C.GREEN if DEBUG else C.DIM, f"  Debug mode: {'ON' if DEBUG else 'OFF'}\n"))
            continue

        if low in (":switch-llm", "switch-llm", "switch llm"):
            fresh = fetch_models()
            if fresh:
                llm_model = select_llm_model(fresh)
                print(c(C.GREEN, f"\n  LLM → {c(C.BOLD, llm_model)}\n"))
            continue

        if low in (":switch-img", "switch-img", "switch img"):
            img_key, img_model = select_image_model()
            print(c(C.GREEN, f"\n  Image → {cc(IMAGE_MODELS, img_key, img_model['label'])}\n"))
            continue

        if low in (":switch-style", "switch-style", ":switch-styles", "switch styles"):
            locked_styles = select_shade_style()
            print(c(C.GREEN, "\n  Shade style updated\n"))
            continue

        if low in (":rarity", "rarity", ":switch-rarity"):
            rarity_key = select_rarity()
            print(c(C.GREEN, "\n  Rarity updated\n"))
            continue

        if low in (":strict", "strict"):
            STRICT_MODE = not STRICT_MODE
            if STRICT_MODE:
                print(c(C.GREEN, "\n  ✓ STRICT MODE ON"))
                print(c(C.DIM,   "    Same creature across all 3 variations"))
                print(c(C.DIM,   "    A=attack, B=idle pose, C=portrait close-up\n"))
            else:
                print(c(C.GREEN, "\n  ✓ CREATIVE MODE (default)"))
                print(c(C.DIM,   "    Same subject type, 3 different design angles\n"))
            continue

        if low in (":fast", "fast"):
            FAST_MODE = not FAST_MODE
            print(c(
                C.GREEN if FAST_MODE else C.DIM,
                f"  Fast mode: {'ON — skipping interpreter' if FAST_MODE else 'OFF'}\n"
            ))
            continue

        if low in (":history", "history"):
            history_show()
            continue

        if low in (":axes", "axes"):
            print_axes()
            continue

        if low in (":styles", "styles"):
            print_styles()
            continue

        if low.startswith(":save") or low.startswith("save "):
            parts = low.split()
            if len(parts) < 2:
                if HISTORY:
                    export_to_md(HISTORY[-1])
                else:
                    print(c(C.DIM, "\n  No history to save.\n"))
                continue
            try:
                idx   = int(parts[1])
                entry = next((h for h in HISTORY if h["id"] == idx), None)
                if not entry:
                    print(c(C.RED, f"  Entry #{idx} not found. Use :history to see IDs.\n"))
                    continue
                export_to_md(entry, parts[2] if len(parts) > 2 else None)
            except ValueError:
                print(c(C.RED, "  Usage: :save N  or  :save N filename.md\n"))
            continue

        if low in (":export", "export"):
            if HISTORY:
                export_to_md(HISTORY[-1])
            else:
                print(c(C.DIM, "\n  No history to export.\n"))
            continue

        if low.startswith(":neg") or low.startswith("neg "):
            parts = low.split(None, 2)
            if len(parts) < 2:
                neg_show()
                continue
            action = parts[1]
            if action in ("add", "+") and len(parts) > 2:
                neg_add(parts[2])
            elif action in ("rm", "remove", "del", "-") and len(parts) > 2:
                neg_remove(parts[2])
            elif action in ("list", "show"):
                neg_show()
            elif action == "clear":
                EXTRA_NEGATIVES.clear()
                print(c(C.GREEN, "  ✓ Persistent negatives cleared.\n"))
            else:
                print(c(C.DIM, "  Usage: :neg add tag  |  :neg rm tag  |  :neg list  |  :neg clear\n"))
            continue

        if low.startswith(":redo") or low.startswith("redo "):
            parts = low.replace(":", "").split()
            if len(parts) < 2 or parts[1].upper() not in ("A", "B", "C"):
                print(c(C.YELLOW, "  Usage: :redo A  (or B / C)\n"))
                continue
            if not HISTORY:
                print(c(C.YELLOW, "  No previous generation to redo.\n"))
                continue
            last   = HISTORY[-1]
            choice = parts[1].upper()
            idx    = ord(choice) - ord("A")
            if idx >= len(last["variations"]):
                print(c(C.YELLOW, f"  Variation {choice} not available.\n"))
                continue

            keep_labels = [l for l in ["A", "B", "C"] if l != choice]
            keep_data   = []
            for kl in keep_labels:
                ki = ord(kl) - ord("A")
                if ki < len(last["variations"]):
                    v = last["variations"][ki]
                    keep_data.append(
                        f"Variation {kl}: name=\"{v.get('name','')}\" "
                        f"concept=\"{v.get('concept','')}\" "
                        f"subject=\"{v.get('subject','')[:60]}...\""
                    )
            keep_str = "\n".join(keep_data)

            redo_system = build_system_prompt(img_key, last["styles"], rarity_key, STRICT_MODE)
            redo_msg    = (
                f"Original idea: {last['idea']}\n"
                f"Subject: {last['subject']}\n\n"
                f"KEEP THESE EXACTLY AS-IS:\n{keep_str}\n\n"
                f"RE-GENERATE ONLY Variation {choice} with a completely different take.\n"
                f"Return the full JSON with all 3 variations. "
                f"Keep the other two identical.\nJSON only."
            )
            print(c(C.DIM, f"\n  Re-rolling variation {choice}..."))
            try:
                raw = call_ollama(redo_msg, llm_model, redo_system)
            except Exception as e:
                print(c(C.RED, f"  Error: {e}"))
                continue
            result = parse_result(raw)
            if result and "variations" in result:
                rendered = display_results(
                    result, llm_model, img_key, last["styles"], rarity_key, last["idea"]
                )
                if rendered:
                    history_add(
                        last["idea"], last["subject"], last["styles"], rarity_key, result, img_key
                    )
            else:
                print(c(C.YELLOW, "  Redo failed — could not parse response."))
                if raw:
                    print(c(C.DIM, f"  Raw ({len(raw)}c): {raw[:400]}"))
            print()
            continue

        if low in (":config save", "config save", ":config"):
            save_config(img_key, locked_styles, rarity_key, llm_model)
            continue

        if low in (":setup", "setup"):
            img_key, img_model = select_image_model()
            locked_styles      = select_shade_style()
            rarity_key         = select_rarity()
            llm_model          = select_llm_model(llm_models)
            print(c(C.GREEN, "\n  Setup updated.\n"))
            continue

        # ── Generate ──
        idea = user_input

        if FAST_MODE:
            confirmed_subject  = idea
            effective_styles   = locked_styles if locked_styles else ["1"]
        else:
            interpretation = interpret_subject(
                idea, llm_model, locked_styles, rarity_key, STRICT_MODE
            )
            if interpretation is None:
                print(c(C.DIM, "  Interpreter unavailable, using input directly.\n"))
                confirmed_subject = idea
                effective_styles  = locked_styles if locked_styles else ["1"]
            else:
                confirmed = confirm_subject(idea, interpretation)
                if confirmed is None:
                    print(c(C.DIM, "\n  Cancelled.\n"))
                    continue
                confirmed_subject = confirmed["subject"]
                effective_styles  = confirmed["styles"]

        system_prompt = build_system_prompt(img_key, effective_styles, rarity_key, STRICT_MODE)

        mode_label = "STRICT (3 shots)" if STRICT_MODE else "CREATIVE (3 angles)"
        neg_extra  = ""
        if EXTRA_NEGATIVES:
            neg_extra = (
                f"\nPERSISTENT NEGATIVES — append to EVERY negative: "
                f"{', '.join(EXTRA_NEGATIVES)}"
            )

        message = (
            f"Original idea: {idea}\n"
            f"Confirmed subject: {confirmed_subject}\n"
            f"Mode: {mode_label}\n"
            f"{neg_extra}\n\n"
            "Generate THREE prompt variations following the 4-part filmmaker structure. "
            "Each section (subject, setting, composition, style) must be descriptive "
            "sentences — not tag lists. JSON only."
        )

        try:
            raw = call_ollama(message, llm_model, system_prompt)
        except urllib.error.URLError as e:
            print(c(C.RED, f"\n  Connection error: {e}"))
            print(c(C.DIM, "  Is Ollama still running?"))
            continue
        except Exception as e:
            print(c(C.RED, f"\n  Error: {e}"))
            continue

        result   = parse_result(raw)
        rendered = False

        if result and "variations" in result:
            rendered = display_results(
                result, llm_model, img_key, effective_styles, rarity_key, confirmed_subject
            )
            if rendered:
                history_add(
                    idea, confirmed_subject, effective_styles, rarity_key, result, img_key
                )

        if not rendered:
            print(c(C.YELLOW, "\n  Could not parse 3-variation JSON from LLM."))
            if len(raw) == 0:
                print(c(C.RED, "  → Empty response (0 chars)."))
                print(c(C.DIM, "    Likely a thinking-only model. Try :switch-llm"))
                print(c(C.DIM, "    to gemma4 or qwen3.5. Run :debug for diagnostics."))
            elif not raw.rstrip().endswith("}"):
                print(c(C.RED, "  → Truncated response."))
                print(c(C.DIM, "    Try a shorter idea, or :switch-llm to a stronger model."))
                print(c(C.DIM, f"\n  Raw ({len(raw)} chars):\n"))
                print(c(C.DIM, "  " + raw[:1500].replace("\n", "\n  ")))
            else:
                print(c(C.DIM, "  → Malformed JSON. Try :switch-llm or rerun."))
                print(c(C.DIM, f"\n  Raw ({len(raw)} chars):\n"))
                print(c(C.DIM, "  " + raw[:1500].replace("\n", "\n  ")))
            print()


if __name__ == "__main__":
    main()
