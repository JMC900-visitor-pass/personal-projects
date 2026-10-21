"""Pure, inspectable compatibility helpers for saved games.

The migration deliberately stays explicit and inspectable.  It owns the save
envelope and the small amount of creature-record normalisation needed for the
V2 combat model.  It never writes to disk; loading is read-only until the
player explicitly saves, at which point the previous bytes are kept as a
``.bak`` file by :mod:`engine.state`.

Run ``python -m engine.migration path/to/save.json`` to inspect what a load
would migrate.  The command is read-only.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


# ``version`` was the original public key.  ``save_version`` is the explicit
# name used by new saves.  We write both during the transition so older tools
# (notably the save picker) can continue to identify real game saves.
CURRENT_SAVE_VERSION = 7


KNOWN_TOP_LEVEL_FIELDS = frozenset({
    "version", "save_version", "saved_at",
    "hunter", "gold", "shards", "day", "world_clock",
    "story", "completed_quests", "roster", "party", "inventory",
    "quests", "board", "kills", "seen", "codex",
    "regions_cleared", "deepest_run", "tracked_quest", "farm",
    "craft_books",
})


class SaveMigrationError(ValueError):
    """The input cannot be safely treated as a supported game save."""


class UnsupportedSaveVersion(SaveMigrationError):
    """The save was created by a newer game and must not be downgraded."""


@dataclass
class MigrationReport:
    """A stable, value-only account of an in-memory migration.

    It intentionally records field names and decisions, not the save's
    contents, so it is safe to show in a diagnostic UI or paste into a bug
    report.
    """

    source_version: int
    target_version: int = CURRENT_SAVE_VERSION
    used_legacy_version_key: bool = False
    steps: list[str] = field(default_factory=list)
    defaults_added: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    preserved_top_level_keys: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return (self.source_version != self.target_version
                or bool(self.defaults_added)
                or bool(self.notes))

    def as_dict(self) -> dict[str, Any]:
        """Return deterministic JSON-ready diagnostic data."""
        return {
            "source_version": self.source_version,
            "target_version": self.target_version,
            "used_legacy_version_key": self.used_legacy_version_key,
            "changed": self.changed,
            "steps": list(self.steps),
            "defaults_added": list(self.defaults_added),
            "notes": list(self.notes),
            "preserved_top_level_keys": list(self.preserved_top_level_keys),
        }


def _parse_version(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise SaveMigrationError(f"{field_name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SaveMigrationError(f"{field_name} must be a positive integer") from exc
    if parsed < 1:
        raise SaveMigrationError(f"{field_name} must be a positive integer")
    return parsed


def _read_source_version(raw: Mapping[str, Any]) -> tuple[int, bool, list[str]]:
    """Read new and legacy version keys without guessing their precedence."""
    notes: list[str] = []
    has_new = "save_version" in raw
    has_old = "version" in raw
    if has_new:
        version = _parse_version(raw["save_version"], "save_version")
        if has_old:
            legacy = _parse_version(raw["version"], "version")
            if legacy != version:
                raise SaveMigrationError(
                    "save_version and version disagree; refusing an ambiguous migration")
        return version, False, notes
    if has_old:
        return _parse_version(raw["version"], "version"), True, notes
    # The earliest saves did not have an envelope version.  Treating them as
    # v1 is safer than pretending they are current and later writing over
    # missing fields.
    notes.append("save had no version key; treated as version 1")
    return 1, False, notes


def _ensure(data: dict[str, Any], key: str, value: Any, report: MigrationReport) -> None:
    """Add a missing known field without replacing a supplied value."""
    if key not in data:
        data[key] = deepcopy(value)
        report.defaults_added.append(key)


def _legacy_clock(data: Mapping[str, Any]) -> dict[str, int]:
    """A deterministic v1 clock seed; no wall-clock state enters migration."""
    try:
        day = max(1, int(data.get("day", 1)))
    except (TypeError, ValueError):
        day = 1
    return {"day": day, "minute_of_day": 8 * 60}


def _v1_to_v2(data: dict[str, Any], report: MigrationReport) -> None:
    _ensure(data, "world_clock", _legacy_clock(data), report)


def _v2_to_v3(data: dict[str, Any], report: MigrationReport) -> None:
    # Older saves only knew ``seen``.  Game.load still promotes this into a
    # first Codex encounter; the empty mapping keeps that compatibility.
    _ensure(data, "seen", [], report)
    _ensure(data, "codex", {}, report)


def _v3_to_v4(data: dict[str, Any], report: MigrationReport) -> None:
    _ensure(data, "farm", None, report)
    _ensure(data, "tracked_quest", "", report)
    _ensure(data, "craft_books", [], report)


def _v4_to_v5(data: dict[str, Any], report: MigrationReport) -> None:
    _ensure(data, "regions_cleared", {}, report)
    _ensure(data, "deepest_run", 0, report)


def _v5_to_v6(data: dict[str, Any], report: MigrationReport) -> None:
    # V6 establishes explicit save_version and atomic writes.  It is otherwise
    # intentionally envelope-only: creature/content migrations come later.
    return None


def _v6_to_v7(data: dict[str, Any], report: MigrationReport) -> None:
    """Make creature records safe for the six-stat, Level 1–50 runtime.

    This is intentionally additive wherever possible: old aliases and old
    build data remain in the record, while V2 receives stable IDs and explicit
    canonical aliases.  Values that cannot exist in V2 (for example Level 999)
    are capped for play *and* retained under ``legacy_level`` so a later Forge
    import or diagnostic can explain what happened.
    """
    roster = data.get("roster")
    if not isinstance(roster, list):
        return

    uids: list[str] = []
    uid_changes = level_caps = tree_copies = 0
    for index, record in enumerate(roster):
        if not isinstance(record, dict):
            continue
        raw_uid = record.get("uid")
        uid = str(raw_uid).strip() if raw_uid is not None else ""
        if not uid or uid in uids:
            # A deterministic legacy key makes repeated read-only migrations
            # idempotent and lets numeric party entries become stable IDs.
            base = f"creature_legacy_{index + 1:03d}"
            uid = base
            suffix = 2
            while uid in uids:
                uid = f"{base}_{suffix}"
                suffix += 1
            record["uid"] = uid
            uid_changes += 1
        elif raw_uid != uid:
            record["uid"] = uid
            uid_changes += 1
        uids.append(uid)

        species_id = record.get("species_id") or record.get("template")
        if species_id and not record.get("species_id"):
            record["species_id"] = str(species_id)
        if "current_xp" not in record and "xp" in record:
            record["current_xp"] = deepcopy(record["xp"])
        if "current_hp" not in record and "cur_hp" in record:
            record["current_hp"] = deepcopy(record["cur_hp"])
        if "move_pp" not in record and isinstance(record.get("skill_pp"), Mapping):
            record["move_pp"] = deepcopy(record["skill_pp"])

        try:
            level = int(record.get("level", 1))
        except (TypeError, ValueError):
            level = 1
        if level > 50:
            record.setdefault("legacy_level", level)
            record["level"] = 50
            level_caps += 1

        # Linear, auto-unlocking trees were the old model.  They are retained
        # verbatim but no longer auto-apply permanent stats in V2.
        if isinstance(record.get("skill_tree"), list) and "legacy_skill_tree" not in record:
            record["legacy_skill_tree"] = deepcopy(record["skill_tree"])
            tree_copies += 1

    party = data.get("party")
    if isinstance(party, list) and party and all(
            isinstance(value, (int, float)) and not isinstance(value, bool) for value in party):
        data["party"] = [uids[int(value)] for value in party
                         if 0 <= int(value) < len(uids)]
        report.notes.append("numeric party roster indexes converted to stable creature IDs")
    if uid_changes:
        report.notes.append(f"assigned or repaired {uid_changes} stable creature ID(s)")
    if level_caps:
        report.notes.append(f"capped {level_caps} legacy creature level(s) at V2's Level 50 cap; originals retained")
    if tree_copies:
        report.notes.append(f"preserved {tree_copies} legacy linear skill tree(s) as imported metadata")


MIGRATORS = {
    1: _v1_to_v2,
    2: _v2_to_v3,
    3: _v3_to_v4,
    4: _v4_to_v5,
    5: _v5_to_v6,
    6: _v6_to_v7,
}


def _ensure_current_shape(data: dict[str, Any], report: MigrationReport) -> None:
    """Supply absent envelope keys, while preserving any supplied values."""
    defaults = {
        "hunter": "Hunter",
        "gold": 0,
        "shards": 0,
        "day": 1,
        "story": 0,
        "completed_quests": 0,
        "roster": [],
        "party": [],
        "inventory": {},
        "quests": [],
        "board": [],
        "kills": {},
        "seen": [],
        "codex": {},
        "regions_cleared": {},
        "deepest_run": 0,
        "tracked_quest": "",
        "farm": None,
        "craft_books": [],
    }
    for key, value in defaults.items():
        _ensure(data, key, value, report)
    _ensure(data, "world_clock", _legacy_clock(data), report)


def migrate_save(raw: Mapping[str, Any]) -> tuple[dict[str, Any], MigrationReport]:
    """Return a current-format *copy* and a migration report.

    The input is never mutated and this function never writes to disk.  It
    retains every unknown top-level key and all nested data verbatim.  A save
    from a newer client is rejected rather than risk a destructive downgrade.
    """
    if not isinstance(raw, Mapping):
        raise SaveMigrationError("save root must be a JSON object")

    source, used_legacy_key, notes = _read_source_version(raw)
    if source > CURRENT_SAVE_VERSION:
        raise UnsupportedSaveVersion(
            f"save version {source} is newer than this game ({CURRENT_SAVE_VERSION})")

    data = deepcopy(dict(raw))
    report = MigrationReport(
        source_version=source,
        used_legacy_version_key=used_legacy_key,
        notes=list(notes),
        preserved_top_level_keys=sorted(
            str(key) for key in raw if key not in KNOWN_TOP_LEVEL_FIELDS),
    )

    version = source
    while version < CURRENT_SAVE_VERSION:
        migrate = MIGRATORS.get(version)
        if migrate is None:  # Defensive: a future edit must add every step.
            raise SaveMigrationError(f"no migration registered for version {version}")
        migrate(data, report)
        report.steps.append(f"v{version}→v{version + 1}")
        version += 1

    _ensure_current_shape(data, report)
    # Keep the legacy alias until callers outside this module no longer rely
    # on it.  Both values always agree after a successful migration.
    data["save_version"] = CURRENT_SAVE_VERSION
    data["version"] = CURRENT_SAVE_VERSION
    return data, report


def report_for_save(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Read-only convenience wrapper for diagnostics and tooling."""
    _, report = migrate_save(raw)
    return report.as_dict()


def passthrough_fields(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return unknown top-level data to retain on a later explicit save.

    This is intentionally top-level only.  Nested creature/content migration
    belongs to their owning systems and is not guessed by this envelope layer.
    """
    return {str(key): deepcopy(value) for key, value in raw.items()
            if key not in KNOWN_TOP_LEVEL_FIELDS}


def main(argv: list[str] | None = None) -> int:
    """Inspect a save without writing it."""
    parser = argparse.ArgumentParser(description="Inspect a Voidcaller save migration")
    parser.add_argument("path", type=Path, help="save JSON to inspect (read-only)")
    args = parser.parse_args(argv)
    try:
        with args.path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        print(json.dumps(report_for_save(raw), indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, SaveMigrationError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised as a CLI
    raise SystemExit(main())
