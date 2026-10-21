#!/usr/bin/env python3
"""What your V2 generator is actually producing.

    python3 tools/dataset_report.py            # read the usual places
    python3 tools/dataset_report.py file.jsonl # read one file

Prints V2 base-stat budgets, Types, move PP, finite skill-tree coverage, and
content slips. Feed the findings back into your Forge prompts.
"""
from __future__ import annotations

import collections
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import elements as EL
from engine.data import load_bestiary
from engine.model import CORE_STATS, RARITY_BST


def bar(frac: float, w: int = 22) -> str:
    n = max(0, min(w, int(round(frac * w))))
    return "#" * n + "." * (w - n)


def legacy_v1_main() -> None:
    paths = sys.argv[1:]
    b = load_bestiary(paths or None)
    if not len(b):
        print("no monsters found")
        return
    n = len(b)
    print(f"\nDATASET REPORT  ·  {n} monsters\n" + "=" * 72)

    print("\nLEVELS")
    levels = [t.level for t in b.all]
    print(f"  range {min(levels)}-{max(levels)}   median {statistics.median(levels):.0f}")
    buckets = collections.Counter(min(9, t.level // 5) for t in b.all)
    for k in sorted(buckets):
        label = f"{k*5}-{k*5+4}" if k < 9 else "45+"
        print(f"  {label:>7}  {bar(buckets[k]/n)} {buckets[k]}")

    print("\nTYPES AND RARITY")
    for name, counter in (("type", collections.Counter(t.primary for t in b.all)),
                          ("rarity", collections.Counter(t.rarity for t in b.all)),
                          ("role", collections.Counter(t.role for t in b.all))):
        top = ", ".join(f"{k} {v}" for k, v in counter.most_common(6))
        print(f"  {name:<7} {len(counter):>2} kinds - {top}")

    print("\nSTATS AGAINST THE FITTED CURVE")
    print("  the game stores each monster as a ratio to the average of its level,")
    print("  clamped to 0.62-1.70. Anything sitting at a clamp is being thrown away.\n")
    print(f"  {'stat':<6}{'curve at L10':>14}{'median ratio':>14}{'at floor':>10}{'at ceiling':>12}")
    for stat in CURVE_STATS:
        ratios = [t.ratio.get(stat, 1.0) for t in b.all]
        lo = sum(1 for r in ratios if r <= 0.63)
        hi = sum(1 for r in ratios if r >= 1.69)
        print(f"  {stat:<6}{curve_value(b.curve, stat, 10):>14.0f}"
              f"{statistics.median(ratios):>14.2f}{lo:>10}{hi:>12}")

    print("\nELEMENTS")
    print("  a monster's own affinity: >1 takes more, <1 takes less, <0 heals.\n")
    for e in ELEMENTS:
        vals = [t.affinity.get(e, 1.0) for t in b.all]
        absorb = sum(1 for v in vals if v < 0)
        weak = sum(1 for v in vals if v > 1.15)
        res = sum(1 for v in vals if 0 <= v < 0.85)
        flag = "  <-- skewed" if absorb > n * 0.15 else ""
        print(f"  {e:<10} weak {weak:>3}   resist {res:>3}   absorb {absorb:>3}{flag}")

    print("\nSKILLS")
    skills = [s for t in b.all for s in t.base_moves + t.skills]
    dmg = [s for s in skills if s.is_damage]
    powers = [s.power for s in dmg] or [0]
    print(f"  {len(skills)} moves - {len(skills)/n:.1f} per monster - {len(dmg)} deal damage")
    hot = sum(1 for p in powers if p > 90)
    print(f"  power {min(powers)}-{max(powers)}, median {statistics.median(powers):.0f}"
          f"   (aim for 20-90; {hot} moves are above 90)")
    print("  targeting: " + ", ".join(f"{k} {v}" for k, v in
                                      collections.Counter(s.target for s in skills).most_common()))
    free = sum(1 for s in skills if s.mp_cost == 0)
    armed = sum(1 for t in b.all if any(s.mp_cost == 0 for s in t.base_moves + t.skills))
    print(f"  {free} cost no mp ({free/max(1,len(skills)):.0%} of moves), and "
          f"{armed} monsters ({armed/n:.0%}) have at least one")

    print("\nCONNECTING AND DODGING")
    hits = [float(t.stats.get("hit", 75)) for t in b.all]
    evas = [float(t.stats.get("eva", 45)) for t in b.all]
    print("  accuracy is 70 + (attacker hit - target eva) x 0.5, floored at 30% "
          "and capped at 99%.")
    try:
        print(f"  hit    median {statistics.median(hits):.0f}   "
              f"eva    median {statistics.median(evas):.0f}   "
              f"-> a median attack connects "
              f"{max(30, min(99, 70 + (statistics.median(hits) - statistics.median(evas)) * 0.5)):.0f}% "
              f"of the time")
    except statistics.StatisticsError:
        pass

    texts = [(t.name, s.name, s.effect_text) for t in b.all for s in t.base_moves + t.skills if s.effect_text]
    unread = [(m, sk, tx) for m, sk, tx in texts if not FX.parse(tx)]
    print(f"\nEFFECT TEXT  -  {len(texts)} written, "
          f"{len(texts)-len(unread)} understood ({1-len(unread)/max(1,len(texts)):.0%})")
    if unread:
        print("  read as flavour only - tighten the prompt, or add a pattern to effects.py:")
        for m, sk, tx in unread[:12]:
            print(f"    {m} / {sk}: {tx[:54]}")

    print("\nDROPS")
    drops = [d for t in b.all for d in t.drops]
    names = collections.Counter(d.item for d in drops)
    print(f"  {len(drops)} drops - {len(names)} distinct items - {len(drops)/n:.1f} per monster")
    print("  kinds: " + ", ".join(f"{k} {v}" for k, v in
                                  collections.Counter(d.kind for d in drops).most_common()))
    shared = [(k, v) for k, v in names.most_common(5) if v > 1]
    if shared:
        print("  shared by several monsters: " + ", ".join(f"{k} x{v}" for k, v in shared))
    nodrop = [t.name for t in b.all if not t.drops]
    if nodrop:
        print(f"  {len(nodrop)} drop nothing: {', '.join(nodrop[:6])}")

    print("\nSLIPS WORTH FIXING")
    slips = []
    seen_names = collections.Counter(t.name.lower() for t in b.all)
    dupes = [k for k, v in seen_names.items() if v > 1]
    if dupes:
        slips.append(f"duplicate names: {', '.join(dupes[:6])}")
    for t in b.all:
        if not t.habitat:
            slips.append(f"{t.name}: no habitat, so the Void can never spawn it")
        if t.stats.get("hp", 0) <= 0:
            slips.append(f"{t.name}: hp {t.stats.get('hp')}")
        if t.base_moves + t.skills and all(s.mp_cost > 0 for s in t.base_moves + t.skills):
            slips.append(f"{t.name}: every move costs mp - it flails once empty")
    for s in slips[:14]:
        print("  " + s)
    if not slips:
        print("  none found.")
    print()


def main() -> None:
    """Report only the data the current combat engine really uses."""
    paths = sys.argv[1:]
    bestiary = load_bestiary(paths or None)
    if not len(bestiary):
        print("no monsters found")
        return

    rows = bestiary.all
    print(f"\nV2 DATASET REPORT  ·  {len(rows)} creatures\n" + "=" * 72)

    print("\nRARITY AND BST")
    for rarity, (low, high) in RARITY_BST.items():
        group = [template for template in rows if template.rarity == rarity]
        bst = [template.bst for template in group]
        outside = [template.name for template in group if not low <= template.bst <= high]
        summary = (f"BST {min(bst)}–{max(bst)}, median {statistics.median(bst):.0f}"
                   if bst else "no authored species")
        print(f"  {rarity:<10} {len(group):>3}  budget {low}–{high}  {summary}"
              + (f"  ! {len(outside)} outside" if outside else ""))

    print("\nTYPES AND ROLES")
    for label, values in (
            ("Type", (template.primary for template in rows)),
            ("Role", (template.role for template in rows)),
            ("Family", (template.family or "Unknown" for template in rows))):
        count = collections.Counter(values)
        text = ", ".join(f"{name} {amount}" for name, amount in count.most_common())
        print(f"  {label:<7} {text}")
    absent = [name for name in EL.config()["types"]
              if not any(name in (template.primary, template.secondary) for template in rows)]
    print("  Unused Types: " + (", ".join(absent) if absent else "none"))

    print("\nSIX-STAT SHAPES")
    print(f"  {'stat':<6}{'min':>7}{'median':>9}{'max':>7}")
    for stat in CORE_STATS:
        values = [template.base_stats[stat] for template in rows]
        print(f"  {stat.upper():<6}{min(values):>7}{statistics.median(values):>9.0f}{max(values):>7}")

    all_moves = [move for template in rows for move in template.base_moves + template.skills]
    base = [template for template in rows if len(template.base_moves) == 2]
    damage = [move for move in all_moves if move.is_damage]
    print("\nMOVES")
    print(f"  {len(all_moves)} authored moves · {len(all_moves) / len(rows):.1f} per creature · {len(damage)} damaging")
    if all_moves:
        pp = [move.pp for move in all_moves]
        kinds = collections.Counter(move.category for move in all_moves)
        print(f"  PP {min(pp)}–{max(pp)}, median {statistics.median(pp):.0f} · "
              + ", ".join(f"{kind} {count}" for kind, count in kinds.items()))
    print(f"  Two fundamental moves: {len(base)}/{len(rows)}")

    print("\nSKILL TREES")
    branch_counts, node_counts = [], []
    for template in rows:
        tree = template.skill_tree if isinstance(template.skill_tree, dict) else {}
        branches = tree.get("branches") or []
        branch_counts.append(len(branches))
        node_counts.append(sum(len(branch.get("nodes") or []) for branch in branches if isinstance(branch, dict)))
    print(f"  branches {min(branch_counts)}–{max(branch_counts)} · nodes {min(node_counts)}–{max(node_counts)}")

    slips = []
    for template in rows:
        slips.extend(f"{template.name}: {issue}" for issue in template.validation_issues())
        if not template.habitat:
            slips.append(f"{template.name}: no habitat flavour tag")
    print("\nSLIPS WORTH FIXING")
    if slips:
        for issue in slips[:20]:
            print("  " + issue)
    else:
        print("  none found.")
    print()


if __name__ == "__main__":
    main()
