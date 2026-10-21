#!/usr/bin/env python3
"""Small, isolated checks for the save migration safety boundary.

Run with:

    .venv/bin/python3 tools/save_migration_selfcheck.py

It only writes inside a temporary directory.  These are synthetic envelope
fixtures, not a claim that we have captured every historical production save.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.data import Bestiary
from engine.migration import (CURRENT_SAVE_VERSION, SaveMigrationError,
                              UnsupportedSaveVersion, migrate_save)
from engine.state import Game, atomic_write_json
from engine import state


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"PASS  {label}")
        return
    raise AssertionError(label)


def test_pure_dispatcher() -> None:
    raw = {
        "version": 1,
        "hunter": "Ada",
        "gold": 44,
        "day": 3,
        "seen": ["mon_alpha"],
        "future_system": {"nested": ["leave", "me", "alone"]},
    }
    original = deepcopy(raw)
    migrated, report = migrate_save(raw)

    check("migration never mutates its input", raw == original)
    check("v1 reaches the current version",
          migrated["version"] == CURRENT_SAVE_VERSION
          and migrated["save_version"] == CURRENT_SAVE_VERSION)
    check("v1 receives deterministic clock compatibility data",
          migrated["world_clock"] == {"day": 3, "minute_of_day": 480})
    check("unknown nested data survives the pure migration",
          migrated["future_system"] == raw["future_system"])
    check("migration report names every envelope step",
          report.steps == [f"v{version}→v{version + 1}"
                           for version in range(1, CURRENT_SAVE_VERSION)])

    every_legacy_version_works = True
    for version in range(1, CURRENT_SAVE_VERSION):
        candidate, candidate_report = migrate_save({"version": version, "day": 2})
        every_legacy_version_works &= (
            candidate["save_version"] == CURRENT_SAVE_VERSION
            and candidate_report.source_version == version
            and len(candidate_report.steps) == CURRENT_SAVE_VERSION - version)
    check("every v1–v5 envelope has a migration path", every_legacy_version_works)

    save_key_only, save_key_report = migrate_save({"save_version": 5})
    check("new save_version key is accepted without legacy version",
          save_key_only["version"] == CURRENT_SAVE_VERSION
          and not save_key_report.used_legacy_version_key)

    again, repeat = migrate_save(migrated)
    check("current saves migrate idempotently", again == migrated and not repeat.changed)

    old_roster = {
        "version": 6,
        "roster": [{"template": "mon_alpha", "level": 999, "xp": 1400,
                    "cur_hp": 18, "max_hp": 64,
                    "skill_pp": {"Old Jab|physical": 3},
                    "skill_tree": [{"id": "old", "name": "Old route"}]}],
        "party": [0],
    }
    converted, converted_report = migrate_save(old_roster)
    row = converted["roster"][0]
    check("V2 creature migration assigns stable IDs and keeps numeric party membership",
          row["uid"].startswith("creature_legacy_") and converted["party"] == [row["uid"]])
    check("V2 creature migration preserves old records while exposing canonical aliases",
          row["species_id"] == "mon_alpha" and row["current_xp"] == 1400
          and row["current_hp"] == 18 and row["move_pp"] == {"Old Jab|physical": 3}
          and row["legacy_level"] == 999 and row["level"] == 50
          and row["legacy_skill_tree"] == old_roster["roster"][0]["skill_tree"])
    check("V2 creature migration explains irreversible runtime caps",
          any("Level 50" in note for note in converted_report.notes))

    try:
        migrate_save({"version": 5, "save_version": 4})
    except SaveMigrationError:
        conflict_rejected = True
    else:
        conflict_rejected = False
    check("conflicting version aliases are rejected", conflict_rejected)

    try:
        migrate_save({"save_version": CURRENT_SAVE_VERSION + 1})
    except UnsupportedSaveVersion:
        future_rejected = True
    else:
        future_rejected = False
    check("newer saves are never downgraded", future_rejected)


def test_atomic_save_and_passthrough() -> None:
    previous_save_dir = state.SAVE_DIR
    with tempfile.TemporaryDirectory(prefix="voidcaller-save-check-") as folder:
        state.SAVE_DIR = folder
        try:
            game = Game(Bestiary([]))
            game.hunter = "Atomic"
            game.gold = 17
            path = Path(game.save("safe"))
            first_bytes = path.read_bytes()
            check("first save creates a JSON file", json.loads(first_bytes)["gold"] == 17)
            check("first save does not fabricate a backup", not path.with_suffix(".json.bak").exists())

            game.gold = 18
            game.save("safe")
            backup = path.with_suffix(".json.bak")
            check("overwrite keeps the exact previous bytes in .bak",
                  backup.read_bytes() == first_bytes)
            check("primary receives the new save", json.loads(path.read_text())["gold"] == 18)
            check("atomic writer leaves no temporary neighbours",
                  not list(path.parent.glob(".safe.json.*.tmp")))

            new_only_path = Path(folder) / "new-only.json"
            atomic_write_json(str(new_only_path), {"save_version": CURRENT_SAVE_VERSION,
                                                    "hunter": "New", "roster": []})
            listed_slots = {slot for slot, _label in state.list_saves()}
            check("save listing recognises save_version-only documents", "new-only" in listed_slots)

            # A legacy fixture with a future top-level extension must remain
            # byte-identical after loading, then retain the extension when an
            # explicit later save writes the canonical envelope.
            legacy_path = Path(folder) / "legacy.json"
            legacy = {
                "version": 5,
                "hunter": "Legacy",
                "gold": 31,
                "day": 2,
                "roster": [],
                "party": [],
                "inventory": {},
                "future_system": {"flag": True, "rows": [1, 2, 3]},
            }
            atomic_write_json(str(legacy_path), legacy)
            legacy_bytes = legacy_path.read_bytes()
            loaded = Game.load("legacy", Bestiary([]))
            check("loading a legacy save is read-only", legacy_path.read_bytes() == legacy_bytes)
            check("loading alone creates no backup", not legacy_path.with_suffix(".json.bak").exists())
            check("legacy game loads", loaded is not None and loaded.gold == 31)

            assert loaded is not None
            loaded.gold = 32
            loaded.save("legacy")
            upgraded = json.loads(legacy_path.read_text())
            check("explicit save writes the new version aliases",
                  upgraded["version"] == CURRENT_SAVE_VERSION
                  and upgraded["save_version"] == CURRENT_SAVE_VERSION)
            check("unknown top-level extension survives load then explicit save",
                  upgraded["future_system"] == legacy["future_system"])
            check("legacy pre-upgrade bytes are backed up",
                  legacy_path.with_suffix(".json.bak").read_bytes() == legacy_bytes)
        finally:
            state.SAVE_DIR = previous_save_dir


def main() -> int:
    test_pure_dispatcher()
    test_atomic_save_and_passthrough()
    print("\nSave migration self-check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
