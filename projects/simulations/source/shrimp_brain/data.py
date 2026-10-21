"""The data sheet: a genome of behaviour, not a rulebook.

Reads ``raw.data.sheet.csv`` the way a shrimp reads water -- as a gradient, a
pressure, a direction of least resistance. NA is *absence*, not zero: missing
source measurements remain absent in the matching simulated summary fields.
"""

from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# The 19 columns of raw.data.sheet.csv, in order.
COLUMNS = [
    "ID", "date", "time.x", "tracklength", "wall_dist", "area", "Trial.x",
    "time_arena", "tl_arena", "frz_arena", "shelter_duration", "Set.Up",
    "Order", "Sex.mm", "estimated.sex1", "size", "weight", "OFT_tot_frz",
    "food_latency2",
]

# Trial types that carry a shelter + food pellet (the combined arena).
SHELTER_FOOD = {"OFTSHELTFOOD1", "OFTSHELTFOOD2", "OFTSHELTFOOD3"}
# Open-field trials: a circle with a light, no shelter, no food.
OPEN_FIELD = {"OFT1", "OFT2", "OFT3"}


def _parse_number(raw):
    """NA is absence. Return None for NA / blank, else a float."""
    if raw is None:
        return None
    s = raw.strip()
    if s == "" or s.upper() == "NA":
        return None
    try:
        value = float(s)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _parse_int(raw):
    f = _parse_number(raw)
    return int(f) if f is not None else None


def _parse_text(raw):
    """Keep optional text values consistent with numeric NA handling."""
    if raw is None:
        return None
    value = raw.strip()
    return value if value and value.upper() != "NA" else None


@dataclass
class Trial:
    """One row of the data sheet: one shrimp, one 240-second trial."""

    id: str
    date: str
    time: str
    trial: str
    set_up: Optional[str]
    order: Optional[int]
    sex_mm: Optional[str]
    sex_est: Optional[str]
    size_mm: Optional[float]
    weight_g: Optional[float]
    # OFT columns
    tracklength: Optional[float]
    wall_dist: Optional[float]
    area: Optional[float]
    oft_tot_frz: Optional[float]
    # OFTSHELTFOOD columns
    time_arena: Optional[float]
    tl_arena: Optional[float]
    frz_arena: Optional[float]
    shelter_duration: Optional[float]
    food_latency2: Optional[float]

    @property
    def is_shelter_food(self):
        return self.trial in SHELTER_FOOD

    @property
    def is_open_field(self):
        return self.trial in OPEN_FIELD

    @property
    def sex_uncertain(self):
        """The shrimp is unsure of its own sex. This is not a bug. This is the shrimp."""
        mm = (self.sex_mm or "").lower()
        est = (self.sex_est or "").lower()
        return not mm or not est or est == "unsure" or mm == "unsure" or mm != est

    @property
    def timestamp(self):
        """The real date+time seeds the current. Different water, different path."""
        try:
            return datetime.strptime(
                f"{self.date} {self.time}", "%d/%m/%Y %H:%M:%S"
            )
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Invalid date/time for shrimp {self.id!r}: {self.date!r} {self.time!r}; "
                "expected DD/MM/YYYY HH:MM:SS"
            ) from exc

    @property
    def seed(self):
        """A stable integer seed derived from the trial's real date+time."""
        ts = self.timestamp
        return (
            (ts.year * 10000 + ts.month * 100 + ts.day) * 1000000
            + ts.hour * 3600 + ts.minute * 60 + ts.second
        )


@dataclass
class Shrimp:
    """A shrimp is its own history. N01 on 11/10 is not N01 on 24/10."""

    id: str
    trials: list = field(default_factory=list)

    def trials_sorted(self):
        """Order trials by real date, then time, then Order within a day."""
        return sorted(self.trials, key=lambda t: (t.timestamp, t.order or 0))

    def history_values(self, column, upto=None):
        """All recorded (non-NA) values of ``column`` for this shrimp.

        If ``upto`` is given, only trials strictly before it are used -- the
        nervous field is sampled from the shrimp's *past*, not its future.
        """
        vals = []
        cutoff = (upto.timestamp, upto.order or 0) if upto is not None else None
        for t in self.trials_sorted():
            if cutoff is not None and (t.timestamp, t.order or 0) >= cutoff:
                break
            v = getattr(t, column, None)
            if v is not None:
                vals.append(v)
        return vals

    def find_trial_by_type(self, trial_type):
        """Find the first trial of a given type for this shrimp."""
        for t in self.trials_sorted():
            if t.trial == trial_type:
                return t
        return None

    def body_at(self, trial):
        """The body *is* the numbers recorded for that trial. Mutable per trial."""
        return {
            "id": self.id,
            "sex": trial.sex_mm,
            "sex_est": trial.sex_est,
            "size_mm": trial.size_mm,
            "weight_g": trial.weight_g,
        }


class DataSheet:
    """The statistical weather the shrimp lives in."""

    def __init__(self, path):
        self.path = path
        self.shrimp = {}
        self._load()

    def _load(self):
        with open(self.path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            missing = [column for column in COLUMNS if column not in (reader.fieldnames or [])]
            if missing:
                raise ValueError("Data sheet is missing required columns: " + ", ".join(missing))
            for row in reader:
                missing = [column for column in COLUMNS if row[column] is None]
                if missing:
                    raise ValueError(
                        f"Data sheet row {reader.line_num} is missing cells: " + ", ".join(missing)
                    )
                for column in ("ID", "date", "time.x", "Trial.x"):
                    if _parse_text(row[column]) is None:
                        raise ValueError(f"Data sheet row {reader.line_num} requires {column}")
                trial = Trial(
                    id=row["ID"].strip(),
                    date=row["date"].strip(),
                    time=row["time.x"].strip(),
                    trial=row["Trial.x"].strip(),
                    set_up=_parse_text(row["Set.Up"]),
                    order=_parse_int(row["Order"]),
                    sex_mm=_parse_text(row["Sex.mm"]),
                    sex_est=_parse_text(row["estimated.sex1"]),
                    size_mm=_parse_number(row["size"]),
                    weight_g=_parse_number(row["weight"]),
                    tracklength=_parse_number(row["tracklength"]),
                    wall_dist=_parse_number(row["wall_dist"]),
                    area=_parse_number(row["area"]),
                    oft_tot_frz=_parse_number(row["OFT_tot_frz"]),
                    time_arena=_parse_number(row["time_arena"]),
                    tl_arena=_parse_number(row["tl_arena"]),
                    frz_arena=_parse_number(row["frz_arena"]),
                    shelter_duration=_parse_number(row["shelter_duration"]),
                    food_latency2=_parse_number(row["food_latency2"]),
                )
                # Invalid dates must not silently change the historical order.
                try:
                    trial.timestamp
                except ValueError as exc:
                    raise ValueError(f"Data sheet row {reader.line_num}: {exc}") from exc
                if trial.id not in self.shrimp:
                    self.shrimp[trial.id] = Shrimp(id=trial.id)
                self.shrimp[trial.id].trials.append(trial)

    def shrimp_ids(self):
        return sorted(self.shrimp.keys())

    def find_trial(self, shrimp_id, trial_type):
        """Find the first trial of a given type for a shrimp."""
        for t in self.shrimp[shrimp_id].trials_sorted():
            if t.trial == trial_type:
                return t
        return None

    def __len__(self):
        return len(self.shrimp)

    def __contains__(self, shrimp_id):
        return shrimp_id in self.shrimp


def default_sheet_path():
    """Locate raw.data.sheet.csv relative to the repo root."""
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(here, "..", "..", "raw.data.sheet.csv"),
        os.path.join(here, "..", "raw.data.sheet.csv"),
        os.path.join(os.getcwd(), "raw.data.sheet.csv"),
    ):
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    raise FileNotFoundError("raw.data.sheet.csv not found")
