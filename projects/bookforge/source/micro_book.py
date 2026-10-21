#!/usr/bin/env python3
"""
MicroForge — Instant Micro Book Generator
===========================================
Interactive mode (just run it, it asks you everything):

    python micro_book.py

Flag mode (skips the wizard entirely):

    python micro_book.py --genre "cyberpunk horror" --pages 3 --words 600 \
        --detail "a hacker discovers her code is writing reality, not simulating it"
"""

import argparse
import itertools
import os
import re
import sys
import threading
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# CONFIG — mirrors book_forge.py so you can share the same Ollama setup
# ---------------------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("MODEL_ALL", "qwen3.6:35b")
CTX_WINDOW = int(os.environ.get("OLLAMA_CTX", 16384))
TEMP = float(os.environ.get("MICRO_TEMP", 0.9))

WORKDIR = Path(os.environ.get("BOOK_DIR", "book_output"))

DEFAULT_PAGES = 3
WORDS_PER_PAGE = 200

GENRE_PRESETS = [
    "cyberpunk horror",
    "space western",
    "dark fantasy",
    "literary sci-fi",
    "cosmic horror",
    "noir mystery",
    "magical realism",
    "post-apocalyptic",
]

# ---------------------------------------------------------------------------
# TERMINAL STYLING
# ---------------------------------------------------------------------------

class C:
    """ANSI codes, auto-disabled when piping to a file or NO_COLOR is set."""
    _on = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    RESET = "\033[0m" if _on else ""
    DIM = "\033[2m" if _on else ""
    BOLD = "\033[1m" if _on else ""
    RED = "\033[31m" if _on else ""
    GREEN = "\033[32m" if _on else ""
    YELLOW = "\033[33m" if _on else ""
    BLUE = "\033[34m" if _on else ""
    MAGENTA = "\033[35m" if _on else ""
    CYAN = "\033[36m" if _on else ""


BANNER = r"""
   __  __ _            ___
  |  \/  (_)__ _ _ ___| __|__ _ _ __ _ ___
  | |\/| | / _| '_/ _ \ _/ _ \ '_/ _` / -_)
  |_|  |_|_\__|_| \___/_|\___/_| \__, \___|
                                 |___/
"""


def banner():
    os.system("cls" if os.name == "nt" else "clear")
    print(f"{C.MAGENTA}{BANNER}{C.RESET}")
    print(f"  {C.BOLD}Instant Micro Book Generator{C.RESET}")
    print(f"  {C.DIM}A complete story, start to finish, in one pass.{C.RESET}")
    print(f"  {C.DIM}{'─' * 56}{C.RESET}\n")


def step(n: int, total: int, label: str):
    print(f"\n{C.CYAN}{C.BOLD}  [{n}/{total}]{C.RESET} {C.BOLD}{label}{C.RESET}")


def hint(text: str):
    print(f"  {C.DIM}{text}{C.RESET}")


def rule():
    print(f"  {C.DIM}{'─' * 56}{C.RESET}")


# ---------------------------------------------------------------------------
# INPUT HELPERS
# ---------------------------------------------------------------------------

def _prompt(label: str, default=None) -> str:
    suffix = f" {C.DIM}[{default}]{C.RESET}" if default not in (None, "") else ""
    try:
        return input(f"  {C.GREEN}>{C.RESET} {label}{suffix}: ").strip()
    except EOFError:
        raise KeyboardInterrupt


def ask_text(label: str, default: str = None, required: bool = False) -> str:
    while True:
        raw = _prompt(label, default)
        if raw:
            return raw
        if default is not None:
            return default
        if not required:
            return ""
        print(f"  {C.RED}!{C.RESET} This one's required.")


def ask_int(label: str, default: int, lo: int, hi: int) -> int:
    while True:
        raw = _prompt(label, default)
        if not raw:
            return default
        try:
            val = int(raw)
        except ValueError:
            print(f"  {C.RED}!{C.RESET} Numbers only.")
            continue
        if lo <= val <= hi:
            return val
        print(f"  {C.RED}!{C.RESET} Pick something between {lo} and {hi}.")


def ask_yes_no(label: str, default: bool = True) -> bool:
    hint_txt = "Y/n" if default else "y/N"
    while True:
        raw = _prompt(f"{label} ({hint_txt})").lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print(f"  {C.RED}!{C.RESET} y or n.")


def ask_menu(label: str, options: list, allow_custom: bool = True) -> str:
    for i, opt in enumerate(options, 1):
        print(f"     {C.YELLOW}{i:>2}{C.RESET}  {opt}")
    if allow_custom:
        print(f"     {C.YELLOW}{len(options) + 1:>2}{C.RESET}  {C.DIM}something else…{C.RESET}")
    print()

    while True:
        raw = _prompt(label, "1")
        if not raw:
            return options[0]
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
            if allow_custom and idx == len(options) + 1:
                custom = ask_text("Describe it", required=True)
                return custom
            print(f"  {C.RED}!{C.RESET} Out of range.")
            continue
        # Typed a genre directly instead of picking a number — that's fine.
        return raw


# ---------------------------------------------------------------------------
# SPINNER
# ---------------------------------------------------------------------------

class Spinner:
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, message: str):
        self.message = message
        self._stop = threading.Event()
        self._thread = None
        self._enabled = sys.stdout.isatty()

    def _spin(self):
        t0 = time.time()
        for frame in itertools.cycle(self.FRAMES):
            if self._stop.is_set():
                break
            elapsed = time.time() - t0
            sys.stdout.write(
                f"\r  {C.MAGENTA}{frame}{C.RESET} {self.message} "
                f"{C.DIM}({elapsed:.0f}s){C.RESET}  "
            )
            sys.stdout.flush()
            time.sleep(0.09)

    def __enter__(self):
        if self._enabled:
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        else:
            print(f"  {self.message}")
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join()
            sys.stdout.write("\r" + " " * 70 + "\r")
            sys.stdout.flush()
        return False


# ---------------------------------------------------------------------------
# OLLAMA CLIENT
# ---------------------------------------------------------------------------

def strip_reasoning(text: str) -> str:
    """Remove <think>...</think> blocks that some models emit."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"</?think>", "", text, flags=re.IGNORECASE)
    return text.strip()


def check_ollama(model: str) -> tuple:
    """Return (reachable, list_of_model_names). Never raises."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
        return True, names
    except Exception:
        return False, []


def ollama_generate(model: str, system: str, prompt: str,
                    temperature: float = 0.9, retries: int = 3) -> str:
    payload = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.85,
            "top_k": 20,
            "repeat_penalty": 1.1,
            "num_ctx": CTX_WINDOW,
            "num_predict": -1,
        },
    }

    attempt = 0
    while attempt < retries:
        attempt += 1
        try:
            r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=600)

            # Older Ollama builds reject the "think" key — drop it and retry
            # without burning a retry slot.
            if r.status_code == 400 and "think" in r.text.lower() and "think" in payload:
                payload.pop("think", None)
                attempt -= 1
                continue

            r.raise_for_status()
            text = r.json().get("response", "")
            if not text.strip():
                raise ValueError("Ollama returned an empty response")
            return strip_reasoning(text)

        except Exception as e:
            print(f"\n  {C.RED}[!]{C.RESET} Ollama error "
                  f"(attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(3 * attempt)

    raise RuntimeError(f"Ollama failed after {retries} attempts")


# ---------------------------------------------------------------------------
# GENERATE
# ---------------------------------------------------------------------------

MICRO_BOOK_SYS = """You are a master micro-fiction writer. You craft complete, emotionally resonant stories in exactly {pages} pages (chapters). Every story must feel whole — beginning, middle, end — packed into tiny space.

RULES:
- Exactly {pages} chapters (pages), labeled {page_labels}
- Each page is a self-contained reading experience but builds on the last
- Prose should be vivid, economical, and immersive — every sentence earns its place
- Include dialogue when it serves the story
- End the final page with a line that lingers
- Write ONLY the story prose. No titles, no notes, no meta-commentary."""


def generate_micro_book(genre: str, pages: int, target_words: int, detail: str,
                        title: str = None, model: str = DEFAULT_MODEL,
                        temperature: float = TEMP) -> str:

    pages = max(int(pages), 1)

    if pages <= 4:
        page_labels = ", ".join(f'"Page {i}"' for i in range(1, pages + 1))
    else:
        page_labels = f'"Page 1" through "Page {pages}"'

    genre_desc = f"Genre: {genre}" if genre else "Genre: open"
    page_desc = f"The story must be exactly {pages} pages."
    word_desc = (f"Target total word count: ~{target_words} words "
                 f"(keep this in mind for pacing).") if target_words > 0 else ""
    title_line = f"Title suggestion: {title}\n" if title else ""

    system = MICRO_BOOK_SYS.format(pages=pages, page_labels=page_labels)
    prompt = f"""Write a micro book based on these specifications:

{title_line}{genre_desc}
{page_desc}
{word_desc}
Author's detail / prompt:
{detail}

Generate the complete story now. Exactly {pages} pages/chapters. Prose only."""

    return ollama_generate(model, system, prompt, temperature=temperature)


# ---------------------------------------------------------------------------
# SAVE & DISPLAY
# ---------------------------------------------------------------------------

def slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]", "", (value or "").lower().replace(" ", "_"))
    return slug or fallback


def save_micro_book(story: str, genre: str, title: str = None) -> Path:
    WORKDIR.mkdir(parents=True, exist_ok=True)
    path = WORKDIR / f"micro_{slugify(title, 'micro')}_{slugify(genre, 'story')}.md"

    # Don't clobber an earlier run
    if path.exists():
        stem, n = path.stem, 2
        while path.exists():
            path = WORKDIR / f"{stem}_{n}.md"
            n += 1

    header = f"# {title}\n\n" if title else ""
    path.write_text(header + story, encoding="utf-8")
    return path


def display_book(story: str, title: str = None):
    print()
    rule()
    print(f"  {C.BOLD}{C.MAGENTA}{(title or 'MICRO BOOK').upper()}{C.RESET}")
    rule()
    print()
    for line in story.splitlines():
        if re.match(r"^\s*(#+\s*)?page\s*\d+", line, re.IGNORECASE):
            print(f"\n  {C.CYAN}{C.BOLD}{line.strip().lstrip('#').strip()}{C.RESET}")
        else:
            print(f"  {line}")
    print()
    rule()


# ---------------------------------------------------------------------------
# WIZARD
# ---------------------------------------------------------------------------

def run_wizard() -> dict:
    TOTAL = 6
    cfg = {}

    step(1, TOTAL, "Pick a genre")
    hint("Choose a number, or just type your own.")
    cfg["genre"] = ask_menu("Genre", GENRE_PRESETS)

    step(2, TOTAL, "How long?")
    hint(f"Each page runs about {WORDS_PER_PAGE} words.")
    cfg["pages"] = ask_int("Pages", DEFAULT_PAGES, 1, 20)

    suggested = cfg["pages"] * WORDS_PER_PAGE
    cfg["words"] = ask_int("Target word count", suggested, 50, 20000)

    step(3, TOTAL, "What's the story?")
    hint("One or two sentences. The seed everything grows from.")
    hint('e.g. "a lighthouse keeper realises the ships she guides are all the same ship"')
    cfg["detail"] = ask_text("Premise", required=True)

    step(4, TOTAL, "Title")
    hint("Leave blank and the story stays untitled.")
    cfg["title"] = ask_text("Title") or None

    step(5, TOTAL, "Model")
    reachable, models = check_ollama(DEFAULT_MODEL)
    if reachable:
        print(f"  {C.GREEN}●{C.RESET} Ollama is up at {C.DIM}{OLLAMA_URL}{C.RESET}")
        if models:
            hint("Installed: " + ", ".join(models[:6]) +
                 ("…" if len(models) > 6 else ""))
    else:
        print(f"  {C.RED}●{C.RESET} Can't reach Ollama at {OLLAMA_URL}")
        hint("Start it with `ollama serve`, or set OLLAMA_URL.")
    cfg["model"] = ask_text("Model", DEFAULT_MODEL)
    cfg["temp"] = TEMP

    step(6, TOTAL, "Confirm")
    print()
    print(f"     {C.DIM}Genre  {C.RESET} {cfg['genre']}")
    print(f"     {C.DIM}Length {C.RESET} {cfg['pages']} pages / ~{cfg['words']} words")
    print(f"     {C.DIM}Title  {C.RESET} {cfg['title'] or C.DIM + '(none)' + C.RESET}")
    print(f"     {C.DIM}Model  {C.RESET} {cfg['model']}")
    print(f"     {C.DIM}Premise{C.RESET} {cfg['detail']}")
    print()

    if not ask_yes_no("Forge it", True):
        print(f"\n  {C.DIM}Starting over…{C.RESET}")
        return run_wizard()

    return cfg


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def forge(cfg: dict) -> bool:
    """Generate, display, save. Returns False on failure."""
    print()
    t0 = time.time()
    try:
        with Spinner("Forging your micro book…"):
            story = generate_micro_book(
                cfg["genre"], cfg["pages"], cfg["words"], cfg["detail"],
                cfg.get("title"), model=cfg["model"],
                temperature=cfg.get("temp", TEMP),
            )
    except RuntimeError as e:
        print(f"  {C.RED}✗{C.RESET} {e}")
        return False

    elapsed = time.time() - t0
    display_book(story, cfg.get("title"))

    path = save_micro_book(story, cfg["genre"], cfg.get("title"))
    words = len(story.split())
    print(f"  {C.GREEN}✓{C.RESET} Saved to {C.BOLD}{path}{C.RESET}")
    print(f"  {C.DIM}{words} words · {elapsed:.1f}s{C.RESET}\n")
    return True


def parse_args():
    ap = argparse.ArgumentParser(
        description="Instant micro book generator. Run with no arguments "
                    "for the interactive wizard.")
    ap.add_argument("--genre", help='e.g. "cyberpunk horror", "space western"')
    ap.add_argument("--pages", type=int, help=f"Pages/chapters (default: {DEFAULT_PAGES})")
    ap.add_argument("--words", type=int, help=f"Target words (default: pages x {WORDS_PER_PAGE})")
    ap.add_argument("--detail", help="Your story premise")
    ap.add_argument("--title", help="Optional title")
    ap.add_argument("--model", help=f"Ollama model (default: {DEFAULT_MODEL})")
    ap.add_argument("--temp", type=float, help=f"Temperature (default: {TEMP})")
    return ap.parse_args()


def main():
    args = parse_args()

    # --detail is the trigger for non-interactive mode
    if args.detail:
        pages = args.pages if args.pages and args.pages > 0 else DEFAULT_PAGES
        cfg = {
            "genre": args.genre or "fantasy",
            "pages": pages,
            "words": args.words if args.words and args.words > 0 else pages * WORDS_PER_PAGE,
            "detail": args.detail,
            "title": args.title,
            "model": args.model or DEFAULT_MODEL,
            "temp": args.temp if args.temp is not None else TEMP,
        }
        return 0 if forge(cfg) else 1

    banner()
    while True:
        cfg = run_wizard()
        ok = forge(cfg)
        if not ok and not ask_yes_no("Try again", True):
            return 1
        if ok and not ask_yes_no("Write another", False):
            print(f"\n  {C.DIM}Happy writing.{C.RESET}\n")
            return 0
        banner()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n  {C.DIM}Cancelled.{C.RESET}\n")
        sys.exit(130)
