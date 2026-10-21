"""The single source of truth for persistent world time.

Gameplay systems should ask this clock for time instead of keeping their own
timestamps.  It deliberately knows nothing about farming, quests, or spawns;
those systems will store their deadlines in world minutes and compare them
against ``total_minutes``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


MINUTES_PER_DAY = 24 * 60


@dataclass
class WorldClock:
    """A serializable game calendar that advances while the player is away.

    One real minute maps to one world minute.  This is intentionally modest:
    it makes asynchronous systems predictable and can be tuned later without
    changing any persisted deadline format.
    """

    day: int = 1
    minute_of_day: int = 8 * 60
    last_seen_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self.day = max(1, int(self.day))
        self.minute_of_day = int(self.minute_of_day) % MINUTES_PER_DAY
        self.last_seen_at = float(self.last_seen_at)

    @property
    def total_minutes(self) -> int:
        return (self.day - 1) * MINUTES_PER_DAY + self.minute_of_day

    @property
    def hour(self) -> int:
        return self.minute_of_day // 60

    @property
    def minute(self) -> int:
        return self.minute_of_day % 60

    @property
    def label(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}"

    def advance(self, minutes: int) -> None:
        """Advance by an explicit amount of world time."""
        total = max(0, self.total_minutes + int(minutes))
        self.day = total // MINUTES_PER_DAY + 1
        self.minute_of_day = total % MINUTES_PER_DAY

    def sync(self, now: float | None = None) -> int:
        """Apply complete real-time minutes since the last observed moment.

        Keeping the fractional remainder prevents frequent UI refreshes from
        silently discarding elapsed time.
        """
        now = time.time() if now is None else float(now)
        elapsed = max(0, int((now - self.last_seen_at) // 60))
        if elapsed:
            self.advance(elapsed)
            self.last_seen_at += elapsed * 60
        return elapsed

    def touch(self, now: float | None = None) -> None:
        """Mark the clock observed without changing world time."""
        self.last_seen_at = time.time() if now is None else float(now)

    def to_dict(self) -> dict:
        return {"day": self.day, "minute_of_day": self.minute_of_day,
                "last_seen_at": self.last_seen_at}

    def view(self) -> dict:
        return {"day": self.day, "hour": self.hour, "minute": self.minute,
                "label": self.label, "total_minutes": self.total_minutes}

    @classmethod
    def from_dict(cls, raw: dict | None, fallback_day: int = 1) -> "WorldClock":
        raw = raw or {}
        return cls(day=raw.get("day", fallback_day),
                   minute_of_day=raw.get("minute_of_day", 8 * 60),
                   last_seen_at=raw.get("last_seen_at", time.time()))
