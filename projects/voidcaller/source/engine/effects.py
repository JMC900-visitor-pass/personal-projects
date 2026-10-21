"""Canonical structured move effects, with a legacy prose reader.

New Forge records must provide machine-readable effects.  The small prose
reader remains only as a migration bridge for old generated datasets; it never
creates new permanent combat stats or an MP mechanic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Statuses the combat engine knows how to apply.  Keep the internal values
# lower-case; presentation can title-case them at the edge.
STATUSES = {
    "poison": ["poison", "toxic", "venom"],
    "burn":   ["burn", "ignite", "scorch", "aflame", "on fire"],
    "sleep":  ["sleep", "slumber", "drowsy"],
    "silence": ["silence", "mute", "seal"],
    "blind":  ["blind", "darkness in the eyes", "dazzle"],
    "slow":   ["slow"],
    "stone":  ["stone", "petrif"],
    "stun":   ["stun", "paralyz", "freeze", "frozen", "immobil", "bind"],
    "confuse": ["confus", "charm", "berserk", "fear", "terror", "panic"],
    "bleed":  ["bleed", "hemorrhage"],
    "regen":  ["regen"],
    "haste":  ["haste", "quicken"],
    "shield": ["shield", "barrier", "protect", "ward"],
}
DEBUFFS = {"poison", "burn", "sleep", "silence", "blind", "slow", "stone",
           "stun", "confuse", "bleed"}

_STAT_WORDS = {"atk": "atk", "attack": "atk", "def": "def", "defense": "def",
               "defence": "def", "mag": "mag", "magic": "mag", "res": "res",
               "resistance": "res", "spd": "spd", "speed": "spd",
               "defensive stats": "def", "defenses": "def", "defences": "def",
               "armor": "def", "armour": "def"}

_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


@dataclass
class Effect:
    kind: str                     # status | stat | drain | heal | revive | cleanse
    key: str = ""                 # status name or stat name
    amount: float = 0.0           # magnitude (fraction for %, flat otherwise)
    rounds: int = 2
    chance: float = 100.0
    target: str = ""              # "" = follow the skill's own target
    text: str = ""                # original prose

    def __str__(self) -> str:
        return self.text or f"{self.kind}:{self.key}"


def from_raw(raw: object) -> Effect | None:
    """Read a V2 structured effect without accepting arbitrary mechanics.

    ``buff`` and ``debuff`` are presentation-friendly aliases for the engine's
    signed ``stat`` effect.  The return value is ``None`` for an unsupported
    record so callers can report it to the author instead of guessing.
    """
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "").strip().casefold()
    target = str(raw.get("target") or "").strip().casefold()
    try:
        amount = float(raw.get("amount", raw.get("max_hp_pct", raw.get("damage_heal_pct", 0))) or 0)
    except (TypeError, ValueError):
        amount = 0.0
    try:
        rounds = max(0, int(raw.get("turns", raw.get("rounds", 0)) or 0))
    except (TypeError, ValueError):
        rounds = 0
    try:
        chance = max(0.0, min(100.0, float(raw.get("chance", 100) or 100)))
    except (TypeError, ValueError):
        chance = 100.0

    if kind in {"buff", "debuff", "stat"}:
        stat = str(raw.get("stat") or raw.get("key") or "").casefold()
        if stat not in {"atk", "def", "mag", "res", "spd", "accuracy", "evasion"}:
            return None
        signed = abs(amount) if kind == "buff" else -abs(amount) if kind == "debuff" else amount
        return Effect("stat", stat, signed,
                      max(1, rounds), chance, target, str(raw.get("description") or ""))
    if kind == "status":
        key = str(raw.get("status") or raw.get("key") or "").casefold()
        if key not in STATUSES:
            return None
        return Effect("status", key, 0.0, max(1, rounds), chance, target,
                      str(raw.get("description") or ""))
    if kind == "heal":
        return Effect("heal", "hp", max(0.0, amount), 0, chance, target,
                      str(raw.get("description") or ""))
    if kind == "drain":
        return Effect("drain", "hp", max(0.0, amount), 0, chance, target,
                      str(raw.get("description") or ""))
    if kind in {"revive", "cleanse"}:
        key = str(raw.get("status") or raw.get("key") or ("hp" if kind == "revive" else "all"))
        return Effect(kind, key.casefold(), max(0.0, amount), rounds, chance, target,
                      str(raw.get("description") or ""))
    return None


def read_many(raw: object) -> tuple[list[Effect], list[str]]:
    """Read a structured effect list and return author-facing issues.

    This is intentionally non-throwing: malformed content should be flagged in
    the Forge/validator, not crash a live save or a terminal screen.
    """
    if raw is None:
        return [], []
    rows = raw if isinstance(raw, list) else [raw]
    effects, issues = [], []
    for index, row in enumerate(rows):
        effect = from_raw(row)
        if effect is None:
            issues.append(f"effects[{index}] is unsupported")
        else:
            effects.append(effect)
    return effects, issues


def _duration(s: str) -> int:
    m = re.search(r"(\d+)\s*(?:turn|round)", s)
    if m:
        return max(1, int(m.group(1)))
    for word, n in _NUM_WORDS.items():
        if re.search(rf"\b{word}\s+(?:turn|round)", s):
            return n
    return 2


def _chance(s: str) -> float:
    m = re.search(r"(\d+)\s*%\s*chance", s)
    if m:
        return float(m.group(1))
    m = re.search(r"chance[^\d]{0,12}(\d+)\s*%", s)
    if m:
        return float(m.group(1))
    return 100.0


def parse(text: str) -> list[Effect]:
    """Best-effort read of one effect string. Returns [] if nothing was understood."""
    if not text or not text.strip():
        return []
    s = text.strip()
    low = s.lower()
    out: list[Effect] = []
    chance = _chance(low)
    rounds = _duration(low)

    # --- statuses -----------------------------------------------------------
    for status, words in STATUSES.items():
        if any(w in low for w in words):
            # "cures poison" / "removes poison" is a cleanse, not an application
            if re.search(rf"(cure|remove|cleanse|dispel)[a-z]*\s+(all\s+)?\w*\s*{words[0]}", low):
                out.append(Effect("cleanse", status, 0, rounds, 100.0, text=s))
            else:
                out.append(Effect("status", status, 0, rounds, chance, text=s))

    # --- stat buffs / debuffs ----------------------------------------------
    stats_hit = []
    for word, key in _STAT_WORDS.items():
        for m in re.finditer(rf"\b{word}\b", low):
            if key not in [k for k, _ in stats_hit]:
                stats_hit.append((key, m.start()))
    if stats_hit:
        # every verb that pushes a stat one way or the other, and where it is,
        # so "increases wind resistance and decreases speed" can mean both
        verbs = []
        for m in re.finditer(r"\b(lower|reduce|decrease|drop|weaken|sap|debuff|down)\w*\b", low):
            verbs.append((m.start(), -1))
        for m in re.finditer(r"\b(raise|increase|boost|buff|enhance|empower|up)\w*\b", low):
            verbs.append((m.start(), 1))
        verbs.sort()

        m = (re.search(r"(\d+)\s*%", low) or re.search(r"by\s*(\d+)", low))
        mag = min(int(m.group(1)) / 100.0 if m else 0.25, 0.75)

        def nearest_verb(at: int) -> int:
            before = [v for pos, v in verbs if pos < at]
            if before:
                return before[-1]                # the last verb before this stat
            return verbs[0][1] if verbs else 1    # otherwise the first one at all

        for key, at in stats_hit:
            # a sign written immediately before this stat wins, so the terse
            # forms generators love -- "-def", "+crit +atk -res -def",
            # "-20% evasion" -- come out as the buffs and debuffs they are
            lead = low[max(0, at - 12):at]
            own = re.search(r"([-\u2212+])\s*\d*\s*%?\s*(?:to\s+)?$", lead)
            sign = nearest_verb(at)
            if own:
                sign = -1 if own.group(1) in "-\u2212" else 1
            here = re.search(r"([-\u2212+])\s*(\d+)\s*%?\s*(?:to\s+)?$", lead)
            amount = min(int(here.group(2)) / 100.0, 0.75) if here else mag
            out.append(Effect("stat", key, sign * amount, rounds, chance, text=s))

    # --- lifesteal / drain --------------------------------------------------
    m = re.search(r"(?:heal|restor|absorb|drain)[a-z]*[^.]{0,40}?(\d+)\s*%\s*of\s*(?:the\s*)?damage", low)
    if m:
        out.append(Effect("drain", "hp", int(m.group(1)) / 100.0, 0, 100.0, text=s))
    elif re.search(r"\b(drain|absorb|leech|siphon)\b", low) and "mp" not in low and not out:
        out.append(Effect("drain", "hp", 0.35, 0, 100.0, text=s))

    # --- healing ------------------------------------------------------------
    m = re.search(r"(?:heal|restor)[a-z]*[^.]{0,30}?(\d+)\s*%\s*(?:of\s*)?(?:max(?:imum)?\s*)?hp", low)
    if m and not any(e.kind == "drain" for e in out):
        out.append(Effect("heal", "hp", int(m.group(1)) / 100.0, 0, 100.0, text=s))

    if re.search(r"\brevive|resurrect|raise the fallen", low):
        out.append(Effect("revive", "hp", 0.5, 0, 100.0, text=s))

    # --- fallbacks: catch the loose prose the patterns above missed --------
    if not out:
        if "|" in low:                      # token style: "reduce_defense|reduce_resistance"
            for tok in low.split("|"):
                tok = tok.strip()
                for word, key in _STAT_WORDS.items():
                    if word in tok:
                        sign = -1 if any(k in tok for k in ("reduce", "lower", "decrease")) else 1
                        out.append(Effect("stat", key, sign * 0.25, rounds, chance, text=s))
        elif re.search(r"damage over time|dot\b", low):
            out.append(Effect("status", "burn", 0, rounds, chance, text=s))
        elif re.search(r"reduce[sd]?\s+damage taken|damage reduction|shield|barrier", low):
            out.append(Effect("status", "shield", 0, rounds, chance, text=s))
        elif re.search(r"\b(heal|recover|restore)", low):
            amt = 0.20
            tgt = "all_allies" if "allies" in low or "party" in low else ""
            out.append(Effect("heal", "hp", amt, 0, chance, target=tgt, text=s))
        elif re.search(r"flinch|knockback|interrupt|stagger", low):
            out.append(Effect("status", "stun", 0, 1, min(chance, 25.0), text=s))
        elif re.search(r"remove all debuff|dispel|cleanse", low):
            out.append(Effect("cleanse", "all", 0, 0, 100.0, text=s))
        elif re.search(r"\+\s*\d*\s*hp|hp per tick|regenerat", low):
            out.append(Effect("heal", "hp", 0.12, 0, 100.0, text=s))
        elif re.search(r"escape|flee|retreat", low):
            out.append(Effect("flee", "", 0, 0, 60.0, text=s))
        elif re.search(r"spirit|morale|focus|rally", low):
            out.append(Effect("stat", "atk", 0.15, rounds, chance, text=s))

    # de-duplicate identical mechanics
    seen, uniq = set(), []
    for e in out:
        sig = (e.kind, e.key, round(e.amount, 3))
        if sig not in seen:
            seen.add(sig)
            uniq.append(e)
    return uniq
