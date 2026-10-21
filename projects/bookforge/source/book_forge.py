#!/usr/bin/env python3
"""
BookForge — Multi-Round Multi-Agent Novel Writer for Ollama
============================================================
Give it a blurb + a few details -> it produces a full-length (~300 page)
sci-fi / comics / horror / mech novel through staged agent rounds:

    ROUND 1: Concept Agents        x2  (premise, world, themes, full outline)
    ROUND 2: Character Designers   x2  (character bible, arcs, voices)
    ROUND 3: Writers               x4  (draft chapters, rotating team)
    ROUND 4: Flow & Engagement     x4  (pacing, tension, hooks, transitions)
    ROUND 5: Grammar & Spellcheck  x2  (line edit, proofread)

Everything is checkpointed to disk, so you can stop/resume any time.

USAGE:
    python book_forge.py --blurb "A disgraced mech pilot discovers her machine
        is haunted by the ghost of its previous pilot" --details "dark tone,
        body horror, 22nd century orbital colonies" --title "Iron Requiem"

    # resume after interruption:
    python book_forge.py --resume

REQUIREMENTS:
    pip install requests
    ollama serve   (with a model pulled, e.g. `ollama pull llama3.1:70b`)
"""

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path

import requests

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# You can assign DIFFERENT models to different agent roles.
# NOTE: Qwen3.6 has no 32b tag on Ollama — sizes are 27b and 35b.
# Swap to "qwen3.6:35b" (24GB) or legacy "qwen3:32b" if you prefer.
DEFAULT_MODEL = os.environ.get("MODEL_ALL", "qwen3.6:35b")
MODELS = {
    "concept":   os.environ.get("MODEL_CONCEPT",  DEFAULT_MODEL),
    "character": os.environ.get("MODEL_CHARACTER", DEFAULT_MODEL),
    "writer":    os.environ.get("MODEL_WRITER",   DEFAULT_MODEL),
    "flow":      os.environ.get("MODEL_FLOW",     DEFAULT_MODEL),
    "grammar":   os.environ.get("MODEL_GRAMMAR",  DEFAULT_MODEL),
}

# Goosebumps-length book: ~120-140 pages => ~23,000 words,
# 25 short punchy chapters (~900 words each), every one ends on a cliffhanger.
TARGET_WORDS       = int(os.environ.get("TARGET_WORDS", 23000))
NUM_CHAPTERS       = int(os.environ.get("NUM_CHAPTERS", 25))
WORDS_PER_CHAPTER  = math.ceil(TARGET_WORDS / NUM_CHAPTERS)   # ~2700

NUM_CONCEPT_AGENTS   = 2
NUM_CHAR_AGENTS      = 2
NUM_WRITER_AGENTS    = 4
NUM_FLOW_AGENTS      = 4
NUM_GRAMMAR_AGENTS   = 2

CTX_WINDOW  = int(os.environ.get("OLLAMA_CTX", 16384))
TEMP_CREATIVE = 0.85
TEMP_EDIT     = 0.3

WORKDIR = Path(os.environ.get("BOOK_DIR", "book_output"))

# ----------------------------------------------------------------------------
# OLLAMA CLIENT
# ----------------------------------------------------------------------------

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

def ollama_generate(model: str, system: str, prompt: str,
                    temperature: float = 0.8, retries: int = 3) -> str:
    """Single-shot generation with retries.

    Qwen3.x are 'thinking' models: we disable thinking via the API flag
    (supported by recent Ollama versions) and additionally strip any
    <think>...</think> blocks that leak into the output so reasoning
    text never ends up inside the book.
    """
    payload = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "think": False,   # ignored by non-thinking models / old Ollama
        "options": {
            "temperature": temperature,
            "top_p": 0.8,
            "top_k": 20,
            "repeat_penalty": 1.1,   # helps quantized Qwen avoid loops
            "num_ctx": CTX_WINDOW,
            "num_predict": -1,
        },
    }
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(f"{OLLAMA_URL}/api/generate",
                              json=payload, timeout=1800)
            if r.status_code == 400 and "think" in r.text.lower():
                payload.pop("think", None)   # older Ollama: retry without flag
                continue
            r.raise_for_status()
            text = r.json()["response"]
            text = THINK_RE.sub("", text)           # closed think blocks
            text = re.sub(r"^.*?</think>", "", text, flags=re.DOTALL) \
                   if "</think>" in text and "<think>" not in text else text
            return text.strip()
        except Exception as e:
            print(f"    [!] Ollama error (attempt {attempt}/{retries}): {e}")
            time.sleep(5 * attempt)
    raise RuntimeError(f"Ollama failed after {retries} attempts for model {model}")


def word_count(text: str) -> int:
    return len(text.split())


# ----------------------------------------------------------------------------
# CHECKPOINTING
# ----------------------------------------------------------------------------

def save(name: str, content: str):
    WORKDIR.mkdir(parents=True, exist_ok=True)
    (WORKDIR / name).write_text(content, encoding="utf-8")

def load(name: str) -> str | None:
    p = WORKDIR / name
    return p.read_text(encoding="utf-8") if p.exists() else None

def save_state(state: dict):
    save("state.json", json.dumps(state, indent=2))

def load_state() -> dict:
    raw = load("state.json")
    return json.loads(raw) if raw else {}


# ----------------------------------------------------------------------------
# ROUND 1 — CONCEPT AGENTS x2
# ----------------------------------------------------------------------------

CONCEPT_SYS_A = """You are Concept Agent ALPHA, a legendary genre-fiction story architect.
You specialize in sci-fi, horror, mech fiction, and comic-book-style storytelling.
You take a rough blurb and expand it into a rich, original, high-concept premise:
world rules, technology, horror elements, factions, central mysteries, themes,
tone, and the emotional core. Be bold, specific, and cinematic. Avoid cliches
unless you subvert them."""

CONCEPT_SYS_B = """You are Concept Agent OMEGA, a ruthless story editor and structure expert.
You take a premise document and (1) critique its weaknesses, (2) fix them,
(3) produce the FINAL story bible and a complete chapter-by-chapter outline.
You structure books GOOSEBUMPS-STYLE: many SHORT chapters, relentless forward
momentum, and EVERY SINGLE CHAPTER ends on a cliffhanger, scare, reveal, or
'oh no' moment that forces the reader to turn the page. Some cliffhangers are
fake-outs (resolved harmlessly at the start of the next chapter), some are
real escalations — alternate them. Every chapter in your outline must state:
POV character, goal, conflict, events, and its exact CLIFFHANGER."""

def round1_concept(state: dict, blurb: str, details: str, title: str):
    if state.get("round1_done"):
        print("[Round 1] Concept — already done, skipping.")
        return

    print("\n" + "="*70)
    print("ROUND 1 — CONCEPT (2 agents)")
    print("="*70)

    print("  [Agent 1/2] ALPHA expanding blurb into premise...")
    premise = ollama_generate(
        MODELS["concept"], CONCEPT_SYS_A,
        f"BOOK TITLE: {title}\n\nBLURB FROM AUTHOR:\n{blurb}\n\n"
        f"EXTRA DETAILS FROM AUTHOR:\n{details}\n\n"
        f"Expand this into a full premise document (~1500 words): logline, "
        f"world & technology, horror elements, factions, protagonist's wound "
        f"and want, antagonistic force, central mystery, themes, tone/style "
        f"references (comics/manga/film influences allowed), and 5 signature "
        f"set-piece ideas.",
        TEMP_CREATIVE)
    save("01_premise.md", premise)

    print("  [Agent 2/2] OMEGA critiquing + building final outline...")
    outline = ollama_generate(
        MODELS["concept"], CONCEPT_SYS_B,
        f"BOOK TITLE: {title}\nTARGET LENGTH: {TARGET_WORDS} words in "
        f"{NUM_CHAPTERS} chapters (~{WORDS_PER_CHAPTER} words each).\n\n"
        f"PREMISE DOCUMENT FROM AGENT ALPHA:\n{premise}\n\n"
        f"First give a short critique + fixes. Then output the FINAL STORY "
        f"BIBLE followed by a numbered outline of ALL {NUM_CHAPTERS} chapters. "
        f"Format each chapter as:\n"
        f"### Chapter N: <Title>\nPOV: ...\nGoal: ...\nConflict: ...\n"
        f"Events: ...\nHook/Twist: ...\nEscalation: ...",
        TEMP_CREATIVE)
    save("02_outline.md", outline)

    state["round1_done"] = True
    save_state(state)
    print("  [OK] Premise + outline saved.")


# ----------------------------------------------------------------------------
# ROUND 2 — CHARACTER DESIGNERS x2
# ----------------------------------------------------------------------------

CHAR_SYS_A = """You are Character Designer ONE. You create deep, contradiction-rich
characters for genre fiction: backstory, psychology, fears, desires, physical
description, mech/gear design where relevant, and a distinct VOICE (speech
patterns, verbal tics, vocabulary). Every character must be able to surprise
the reader while staying consistent."""

CHAR_SYS_B = """You are Character Designer TWO, a relationships-and-arcs specialist.
Given a character roster, you design: the web of relationships (alliances,
grudges, secrets each character keeps from the others), each character's arc
across the book mapped to the chapter outline, and dialogue samples proving
each voice is distinct. You also flag and fix any two characters that feel
too similar."""

def round2_characters(state: dict, title: str):
    if state.get("round2_done"):
        print("[Round 2] Characters — already done, skipping.")
        return
    outline = load("02_outline.md")

    print("\n" + "="*70)
    print("ROUND 2 — CHARACTER DESIGN (2 agents)")
    print("="*70)

    print("  [Agent 1/2] Designer ONE building character roster...")
    roster = ollama_generate(
        MODELS["character"], CHAR_SYS_A,
        f"BOOK: {title}\n\nSTORY BIBLE + OUTLINE:\n{outline}\n\n"
        f"Create the full character bible: protagonist, antagonist, and "
        f"4-7 key supporting characters. For each: name, role, age, physical "
        f"description, backstory, psychological wound, want vs need, fears, "
        f"secrets, voice/speech pattern, and (if a pilot) their mech's name, "
        f"design, and quirks.",
        TEMP_CREATIVE)
    save("03_characters.md", roster)

    print("  [Agent 2/2] Designer TWO mapping arcs + relationships...")
    arcs = ollama_generate(
        MODELS["character"], CHAR_SYS_B,
        f"BOOK: {title}\n\nCHAPTER OUTLINE:\n{outline}\n\n"
        f"CHARACTER ROSTER:\n{roster}\n\n"
        f"Produce: (1) relationship web with secrets/tensions, (2) each "
        f"character's arc mapped chapter-by-chapter, (3) 2-line dialogue "
        f"sample per character proving distinct voice, (4) fixes for any "
        f"characters that overlap too much.",
        TEMP_CREATIVE)
    save("04_character_arcs.md", arcs)

    state["round2_done"] = True
    save_state(state)
    print("  [OK] Character bible + arcs saved.")


# ----------------------------------------------------------------------------
# ROUND 3 — WRITERS x4 (rotating team, chapter by chapter)
# ----------------------------------------------------------------------------

WRITER_PERSONAS = [
    ("Writer 1 — ACTION",
     "You are a master of kinetic action prose: mech combat, chase sequences, "
     "visceral horror encounters. Short punchy sentences in fights, sensory "
     "overload, real physical consequences."),
    ("Writer 2 — ATMOSPHERE",
     "You are a master of dread, atmosphere, and horror. Slow-burn tension, "
     "the uncanny, body horror rendered in precise sensory detail, silence "
     "that means something."),
    ("Writer 3 — CHARACTER",
     "You are a master of interiority and dialogue. Subtext-heavy "
     "conversations, emotional truth, character voices that never blur, "
     "quiet scenes that hit harder than explosions."),
    ("Writer 4 — WORLD & PLOT",
     "You are a master of worldbuilding woven into plot: reveals, "
     "foreshadowing payoffs, faction intrigue, tech that feels lived-in. You "
     "never info-dump; the world leaks through action and detail."),
]

WRITER_BASE_SYS = """You are a professional novelist ghost-writing one SHORT chapter of a
fast-paced novel (Goosebumps-style pacing: short punchy chapters, high
momentum, vivid but economical prose, every chapter ends on a cliffhanger).
Write ONLY the chapter prose — no meta commentary, no outline notes, no
'Chapter N' header (it will be added). Keep paragraphs short. Maintain
continuity with the summary of previous chapters. Match the established POV
and voice. The FINAL LINE of the chapter must be the cliffhanger specified
in the outline — land it hard and stop immediately.
SPECIALTY: {specialty}"""

def get_chapter_outline_block(outline: str, n: int) -> str:
    """Extract the outline block for chapter n; fall back to whole outline."""
    pattern = rf"###\s*Chapter\s+{n}\b.*?(?=###\s*Chapter\s+{n+1}\b|\Z)"
    m = re.search(pattern, outline, re.DOTALL | re.IGNORECASE)
    return m.group(0).strip() if m else outline

def summarize_chapter(text: str, n: int) -> str:
    return ollama_generate(
        MODELS["grammar"],  # small fast model is fine for summaries
        "You summarize book chapters for continuity tracking. Be factual and dense.",
        f"Summarize Chapter {n} in 120 words max: key events, reveals, "
        f"character/emotional changes, where everyone is at the end.\n\n{text}",
        0.2)

def round3_writing(state: dict, title: str):
    outline = load("02_outline.md")
    characters = load("03_characters.md")
    arcs = load("04_character_arcs.md")

    done = state.setdefault("chapters_done", 0)
    summaries = state.setdefault("summaries", [])

    if done >= NUM_CHAPTERS:
        print("[Round 3] Writing — already done, skipping.")
        return

    print("\n" + "="*70)
    print(f"ROUND 3 — DRAFTING ({NUM_WRITER_AGENTS} writers, "
          f"{NUM_CHAPTERS} chapters, ~{WORDS_PER_CHAPTER} words each)")
    print("="*70)

    for n in range(done + 1, NUM_CHAPTERS + 1):
        persona_name, specialty = WRITER_PERSONAS[(n - 1) % NUM_WRITER_AGENTS]
        ch_outline = get_chapter_outline_block(outline, n)
        recent_summaries = "\n".join(
            f"Ch{idx+1}: {s}" for idx, s in enumerate(summaries[-8:], start=max(0, len(summaries)-8))
        ) or "This is the first chapter."

        print(f"  [Chapter {n}/{NUM_CHAPTERS}] {persona_name} drafting...")
        chapter = ollama_generate(
            MODELS["writer"],
            WRITER_BASE_SYS.format(specialty=specialty),
            f"BOOK: {title}\n\n"
            f"CHARACTER BIBLE (reference):\n{characters[:6000]}\n\n"
            f"CHARACTER ARCS (reference):\n{arcs[:4000]}\n\n"
            f"SUMMARY OF STORY SO FAR:\n{recent_summaries}\n\n"
            f"OUTLINE FOR THIS CHAPTER:\n{ch_outline}\n\n"
            f"Write Chapter {n} now. Target length: {WORDS_PER_CHAPTER} words "
            f"(minimum {int(WORDS_PER_CHAPTER*0.85)}). Prose only.",
            TEMP_CREATIVE)

        # If the model came up short, ask it to extend the chapter once.
        if word_count(chapter) < int(WORDS_PER_CHAPTER * 0.7):
            print(f"    [~] Only {word_count(chapter)} words — extending...")
            extension = ollama_generate(
                MODELS["writer"],
                WRITER_BASE_SYS.format(specialty=specialty),
                f"Here is the chapter so far:\n\n{chapter}\n\n"
                f"Continue it seamlessly (do not repeat text) with roughly "
                f"{WORDS_PER_CHAPTER - word_count(chapter)} more words, ending "
                f"on this hook: {ch_outline[-500:]}",
                TEMP_CREATIVE)
            chapter = chapter + "\n\n" + extension

        save(f"draft_ch{n:02d}.md", chapter)
        summary = summarize_chapter(chapter, n)
        summaries.append(summary)
        state["chapters_done"] = n
        state["summaries"] = summaries
        save_state(state)
        print(f"    [OK] {word_count(chapter)} words. Summary logged.")

    print("  [OK] All chapters drafted.")


# ----------------------------------------------------------------------------
# ROUND 4 — FLOW & ENGAGEMENT x4
# ----------------------------------------------------------------------------

FLOW_PERSONAS = [
    ("Flow 1 — PACING",
     "You are a pacing editor. Cut drag, tighten slow passages, vary sentence "
     "and paragraph rhythm, make action fast and dread slow. Delete filler."),
    ("Flow 2 — HOOKS & TENSION",
     "You are a tension editor. Strengthen chapter openings and cliffhanger "
     "endings, sharpen stakes, plant/pay off micro-questions that keep pages "
     "turning."),
    ("Flow 3 — CONTINUITY & TRANSITIONS",
     "You are a continuity editor. Smooth transitions between scenes, fix "
     "contradictions with the story-so-far summary, keep timeline, injuries, "
     "and geography consistent."),
    ("Flow 4 — EMOTIONAL ENGAGEMENT",
     "You are an emotional-impact editor. Deepen interiority at key beats, "
     "make horror land in the body, make character moments earn their weight. "
     "Show don't tell."),
]

FLOW_BASE_SYS = """You are a professional developmental line editor revising one book
chapter. Output ONLY the full revised chapter text — no notes, no commentary,
no diff. Preserve plot events and chapter length (do not shorten by more than
10%). SPECIALTY: {specialty}"""

def round4_flow(state: dict, title: str):
    done = state.setdefault("flow_done", 0)
    if done >= NUM_CHAPTERS:
        print("[Round 4] Flow — already done, skipping.")
        return

    summaries = state.get("summaries", [])
    print("\n" + "="*70)
    print(f"ROUND 4 — FLOW & ENGAGEMENT ({NUM_FLOW_AGENTS} editors, sequential passes per chapter)")
    print("="*70)

    for n in range(done + 1, NUM_CHAPTERS + 1):
        text = load(f"draft_ch{n:02d}.md")
        context = "\n".join(f"Ch{i+1}: {s}" for i, s in enumerate(summaries))[:6000]

        for persona_name, specialty in FLOW_PERSONAS:
            print(f"  [Chapter {n}/{NUM_CHAPTERS}] {persona_name} pass...")
            revised = ollama_generate(
                MODELS["flow"],
                FLOW_BASE_SYS.format(specialty=specialty),
                f"BOOK: {title}\nSTORY CONTEXT:\n{context}\n\n"
                f"CHAPTER {n} TEXT:\n{text}\n\n"
                f"Revise per your specialty. Output the complete revised chapter.",
                TEMP_EDIT + 0.2)
            # Safety: if an editor accidentally truncates badly, keep prior version
            if word_count(revised) >= word_count(text) * 0.75:
                text = revised
            else:
                print("    [~] Pass truncated the chapter too much — keeping previous version.")

        save(f"flow_ch{n:02d}.md", text)
        state["flow_done"] = n
        save_state(state)
        print(f"    [OK] Chapter {n} flow-edited ({word_count(text)} words).")


# ----------------------------------------------------------------------------
# ROUND 5 — GRAMMAR & SPELLCHECK x2
# ----------------------------------------------------------------------------

GRAMMAR_PERSONAS = [
    ("Grammar 1 — LINE EDIT",
     "You are a line editor. Fix grammar, spelling, punctuation, tense slips, "
     "and awkward constructions. Remove repeated words/phrases. Do NOT change "
     "plot, voice, or meaning."),
    ("Grammar 2 — PROOFREADER",
     "You are a final proofreader. Catch remaining typos, punctuation errors, "
     "inconsistent capitalization of names/terms, and formatting glitches. "
     "Change as little as possible."),
]

GRAMMAR_SYS = """You are a copy editor. Output ONLY the corrected chapter text —
no commentary, no lists of changes. Preserve the author's style and length.
SPECIALTY: {specialty}"""

def round5_grammar(state: dict):
    done = state.setdefault("grammar_done", 0)
    if done >= NUM_CHAPTERS:
        print("[Round 5] Grammar — already done, skipping.")
        return

    print("\n" + "="*70)
    print(f"ROUND 5 — GRAMMAR & SPELLCHECK ({NUM_GRAMMAR_AGENTS} editors)")
    print("="*70)

    for n in range(done + 1, NUM_CHAPTERS + 1):
        text = load(f"flow_ch{n:02d}.md")
        for persona_name, specialty in GRAMMAR_PERSONAS:
            print(f"  [Chapter {n}/{NUM_CHAPTERS}] {persona_name} pass...")
            fixed = ollama_generate(
                MODELS["grammar"],
                GRAMMAR_SYS.format(specialty=specialty),
                f"CHAPTER TEXT:\n{text}\n\nOutput the corrected chapter.",
                TEMP_EDIT)
            if word_count(fixed) >= word_count(text) * 0.85:
                text = fixed
            else:
                print("    [~] Pass truncated too much — keeping previous version.")
        save(f"final_ch{n:02d}.md", text)
        state["grammar_done"] = n
        save_state(state)
        print(f"    [OK] Chapter {n} finalized.")


# ----------------------------------------------------------------------------
# ASSEMBLY
# ----------------------------------------------------------------------------

def assemble(title: str):
    print("\n" + "="*70)
    print("ASSEMBLING MANUSCRIPT")
    print("="*70)
    outline = load("02_outline.md") or ""
    # Try to recover chapter titles from the outline
    titles = dict(re.findall(r"###\s*Chapter\s+(\d+)\s*:\s*(.+)", outline))

    parts = [f"# {title}\n"]
    total = 0
    for n in range(1, NUM_CHAPTERS + 1):
        text = load(f"final_ch{n:02d}.md") or load(f"flow_ch{n:02d}.md") \
               or load(f"draft_ch{n:02d}.md")
        if not text:
            print(f"  [!] Chapter {n} missing — skipping.")
            continue
        ch_title = titles.get(str(n), "").strip()
        header = f"\n\n## Chapter {n}" + (f": {ch_title}" if ch_title else "")
        parts.append(header + "\n\n" + text)
        total += word_count(text)

    manuscript = "\n".join(parts)
    save("MANUSCRIPT.md", manuscript)
    pages = total // 180   # Goosebumps-style books run ~180 words/page
    print(f"  [DONE] {total:,} words ≈ {pages} paperback pages -> {WORKDIR/'MANUSCRIPT.md'}")


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Multi-agent Ollama novel writer")
    ap.add_argument("--blurb", help="Your rough story idea (the 'blur')")
    ap.add_argument("--details", default="", help="Extra details: tone, setting, influences")
    ap.add_argument("--title", default="Untitled", help="Book title")
    ap.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    args = ap.parse_args()

    state = load_state()

    if args.resume:
        if not state:
            sys.exit("No checkpoint found in ./book_output — run with --blurb first.")
        blurb  = state["blurb"]
        details = state["details"]
        title   = state["title"]
        print(f"Resuming '{title}'...")
    else:
        if not args.blurb:
            sys.exit("Provide --blurb (or use --resume).")
        blurb, details, title = args.blurb, args.details, args.title
        state.update({"blurb": blurb, "details": details, "title": title})
        save_state(state)

    # sanity check ollama
    try:
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    except Exception:
        sys.exit(f"Cannot reach Ollama at {OLLAMA_URL}. Run `ollama serve` first.")

    t0 = time.time()
    round1_concept(state, blurb, details, title)
    round2_characters(state, title)
    round3_writing(state, title)
    round4_flow(state, title)
    round5_grammar(state)
    assemble(title)
    print(f"\nTotal time: {(time.time()-t0)/3600:.1f} hours")


if __name__ == "__main__":
    main()
