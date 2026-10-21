"""All the tuning knobs live here. Change these, not the game code."""
from __future__ import annotations

# --- V2 six-stat combat model ------------------------------------------------
# The stat and damage curve is Pokemon's, retuned for a Level 1-50 cap.
# Pokemon divides by 100 for a Level 1-100 game; VOIDCALLER caps at 50, so the
# same shape uses LEVEL_DIVISOR = 50 and Level 50 here sits where Level 100
# sits there.
#
#   HP    = floor(2 x base x level / 50) + level + 10
#   other = floor(2 x base x level / 50) + 5
#
# HP getting "+ level + 10" where the others get "+ 5" is the whole trick, and
# it is why Pokemon can budget HP on the same scale as ATK without HP becoming
# a wasted stat.  Twenty base points buy +40 HP or +40 ATK — identical marginal
# value — so BST is finally an honest budget.  The previous model grew HP on
# its own flat per-level term, which made a point of HP worth a fraction of a
# point of ATK and let two Commons on the same 230 BST differ twelvefold in how
# long their fights ran.
LEVEL_DIVISOR      = 50     # Pokemon uses 100 for a 100-level game
HP_LEVEL_BONUS     = 10     # the "+ level + 10" tail on HP
STAT_FLAT_BONUS    = 5      # the "+ 5" tail on the other five stats
HP_FLOOR           = 10     # safety net for malformed records, not a design value

# Per-stat sanity bands, as a fraction of the species' own average stat
# (BST / 6).  A species may still have a defining strength and a real weakness
# — 0.60 to 1.40 is a 2.33x spread between its best and worst stat — but it
# cannot dump everything into ATK and read as a one-hit-kill machine.  Content
# is normalised into these bands rather than rejected for missing them.
STAT_BAND_LOW      = 0.60
STAT_BAND_HIGH     = 1.40
MIN_DAMAGE      = 1

# --- hitting things ---------------------------------------------------------
# Accuracy belongs to each move.  Creatures have no permanent HIT/EVA stats;
# temporary battle effects may adjust the move chance inside these bounds.
ACCURACY_FLOOR         = 30.0
ACCURACY_CEIL          = 100.0
GUARD_ACCURACY_PENALTY = 5.0    # guarding also makes you slightly harder to hit
BLIND_ACCURACY_PENALTY = 0.55
EVASION_CAP            = 0.40

# --- damage -----------------------------------------------------------------
# Pokemon's damage formula, unchanged apart from the level cap:
#
#   floor( floor( floor(2 x level / 5 + 2) x power x ATK / DEF ) / 50 ) + 2
#
# It is linear in ATK/DEF rather than quadratic in the attacker's stat, which
# is what stops a high-ATK species reading as a one-hit-kill machine, and the
# level term makes fights lengthen as a team grows — 4 hits to a knockout at
# Level 1, about 6.5 by Level 50.
DAMAGE_LEVEL_DIVISOR = 5.0
DAMAGE_LEVEL_BONUS   = 2.0
DAMAGE_DIVISOR       = 50.0
DAMAGE_FLAT          = 2.0
# Same Type Attack Bonus: a move matching one of the user's own Types hits
# half again as hard.  This is the single biggest reason Pokemon typing is a
# building decision and not just a defensive lookup table.
STAB_MULTIPLIER  = 1.5
DAMAGE_ROLL      = (0.85, 1.00)   # Pokemon's asymmetric damage roll
POWER_SCALE      = 105.0  # retired: kept so old saves and tools still import
GUARD_WEIGHT     = 1.0
DAMAGE_VARIANCE  = 0.10   # retired in favour of DAMAGE_ROLL
# A wild creature can never erase more than this share of a player creature's
# full health with one hit. It leaves room to read the field, heal, switch, or
# run instead of losing a fresh starter to an unlucky crit.
PLAYER_HIT_CAP = 0.34
CRIT_MULT        = 1.5    # Pokemon Gen 6+ critical multiplier
CRIT_CAP         = 40.0   # no monster crits more often than this
BASE_CRIT        = 5.0
GUARD_REDUCTION  = 0.55   # damage taken while guarding
SHIELD_REDUCTION = 0.60   # damage taken with a shield up

# --- the order of play ------------------------------------------------------
SPEED_JITTER     = 0.12   # +/- on spd when the round's order is worked out
SLOW_FACTOR      = 0.60
HASTE_FACTOR     = 1.40
FLEE_BASE        = 55.0
FLEE_SPEED_WEIGHT = 45.0  # percent per 100% speed advantage
FLEE_FLOOR       = 15.0
FLEE_CEIL        = 95.0
PRESSURE_START   = 12     # the Void starts crushing a fight that drags
PRESSURE_PCT     = 0.06   # of max hp, growing each round after that
MAX_ROUNDS       = 40

# --- levelling --------------------------------------------------------------
# Pokemon's "Medium Fast" growth group: the total XP to reach level n is n^3,
# so the step from n to n+1 costs 3n^2 + 3n + 1.  It is the default curve for
# most of the Pokedex and it front-loads early levels pleasantly (7 XP for the
# first) while still asking for real work at the cap (7,351 for 49 -> 50).
# Total for a full Level 1 -> 50 run: 125,000.
XP_GROWTH_EXPONENT = 3
MAX_LEVEL        = 50
# Base experience yield, Pokemon's `b` term.  Reward = b x enemy_level / 7.
XP_YIELD_BY_RARITY = {"Common": 60, "Uncommon": 85, "Rare": 120, "Epic": 170}
XP_YIELD_DIVISOR   = 7
XP_BOSS_MULTIPLIER = 3.0
XP_APEX_MULTIPLIER = 4.0
XP_NEXT_BASE     = 60     # retired constants, kept for old imports
XP_NEXT_LINEAR   = 18
XP_NEXT_QUADRATIC = 3.2
PARTY_SLOTS      = 4          # monsters that fight at once
ROSTER_CAP       = 30
SKILL_POINTS_PER_LEVEL = 1

# --- status effects: rounds and strength ---
POISON_PCT       = 0.07       # of max hp per round
BURN_PCT         = 0.09
REGEN_PCT        = 0.08
BUFF_STEP        = 0.25       # atk-up / def-up size

# a status lands on its own stated chance, multiplied by the target's resistance
STATUS_RESIST_FACTOR = {"weak": 1.4, "normal": 1.0, "resist": 0.45, "immune": 0.0}

# --- economy ---
SELL_RATE        = 1.0        # materials sell at full listed value
SHOP_MARKUP      = 1.0
SUMMON_COST      = 45         # void shards per summon
SHARDS_PER_FIGHT = (1, 3)
VOID_RUN_LENGTH  = (3, 5)     # encounters per run before the boss

# --- rarity -----------------------------------------------------------------
# Rarity is explicit content data, independent from combat Level.  It budgets
# a species' BST; it does not secretly multiply its actual stats.
RARITY_WEIGHT = {"Common": 50, "Uncommon": 28, "Rare": 14, "Epic": 6}
RARITY_POWER  = {"Common": 1.0, "Uncommon": 1.0, "Rare": 1.0, "Epic": 1.0}
RARITY_COLOR  = {"Common": "bright", "Uncommon": "green", "Rare": "cyan", "Epic": "magenta"}
RARITY_MARK   = {"Common": "○", "Uncommon": "□", "Rare": "★", "Epic": "★★"}
RARITY_UI_COLOR = dict(RARITY_COLOR)
# Read-only compatibility for legacy area/Forge listings.  New species use an
# explicit ``rarity`` field; nothing in V2 derives it from this table.
RARITY_BANDS = [(0, 8, "Common"), (9, 16, "Uncommon"),
                (17, 26, "Rare"), (27, MAX_LEVEL, "Epic")]


def xp_total_for_level(level: int) -> int:
    """Total XP to reach ``level`` from Level 1 — Pokemon Medium Fast, n^3."""
    level = max(1, min(MAX_LEVEL, int(level)))
    return level ** XP_GROWTH_EXPONENT - 1


def xp_required_for_next(level: int) -> int:
    """XP needed to advance from ``level`` to the next combat level."""
    level = max(1, min(MAX_LEVEL, int(level)))
    if level >= MAX_LEVEL:
        return 0
    return xp_total_for_level(level + 1) - xp_total_for_level(level)


def xp_reward(level: int, rarity: object = "Common", *, boss: bool = False,
              apex: bool = False) -> int:
    """Pokemon's yield formula: base yield x the fallen creature's level / 7."""
    level = max(1, min(MAX_LEVEL, int(level or 1)))
    yield_base = XP_YIELD_BY_RARITY.get(str(rarity or "").title(), XP_YIELD_BY_RARITY["Common"])
    total = yield_base * level / XP_YIELD_DIVISOR
    if apex:
        total *= XP_APEX_MULTIPLIER
    elif boss:
        total *= XP_BOSS_MULTIPLIER
    return max(1, int(total))
