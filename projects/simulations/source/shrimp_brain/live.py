"""Persistent cherry-shrimp tank with one simulated second per wall-clock second.

Movement is illustrative and uses the source animals' historical profiles.
Cherry life-cycle defaults are 18 days carrying eggs and 30 days to maturity;
60 seconds of contact is a UI courtship model, not a biological measurement.
"""

from __future__ import annotations

import json
import math
import os
import random
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .data import DataSheet
from .nervous_field import sample_nervous_field

DAY = 86400.0
MAX_POPULATION = 200
MAX_PELLETS = 200
COLORS = ("#e6564e", "#e97561", "#bd373c", "#ee8b75", "#cf4945")


def _number(value, name, low=0.0, high=1e16):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"Invalid {name}")
    return float(value)


def _clamp(value, low, high):
    return max(low, min(high, value))


def _sex(trial):
    aliases = {"m": "M", "male": "M", "f": "F", "female": "F"}
    recorded = aliases.get((trial.sex_mm or "").lower())
    estimated = aliases.get((trial.sex_est or "").lower())
    return recorded if recorded and recorded == estimated else "?"


@dataclass
class LiveShrimp:
    id: str
    x: float
    y: float
    heading: float
    sex: str
    size_mm: float | None
    weight_g: float | None
    hunger: float
    state: str
    color: str
    generation: int = 0
    born_at: float | None = None
    eggs: int = 0
    hatch_at: float | None = None
    mother_id: str | None = None
    father_id: str | None = None
    egg_father_id: str | None = None
    speed: float = 2.0
    wall_preference: float = 5.0
    freeze_chance: float = 0.05
    shelter_preference: float = 0.5
    rest_until: float = 0.0
    target_size_mm: float = 20.0
    adult_weight_g: float | None = None


@dataclass
class FoodPellet:
    id: int
    x: float
    y: float
    remaining: float = 1.0


class LiveTank:
    """An in-memory tank. Call ``advance`` regularly, and ``save`` on changes."""

    def __init__(self, seed=None, now=None):
        self.rng = random.Random(seed)
        self.seed = seed
        self.created_at = _number(time.time() if now is None else now, "now")
        self.last_updated = self.created_at
        self.light_on = True
        self.shrimps: list[LiveShrimp] = []
        self.pellets: list[FoodPellet] = []
        self.events: list[str] = []
        self.incubation_days = 18.0
        self.maturity_days = 30.0
        self.breeding_pair: list[str] | None = None
        self.courtship_started_at: float | None = None
        self.next_pellet_id = 1
        self.next_shrimp_id = 1

    @classmethod
    def from_sheet(cls, sheet: DataSheet, seed=None, count=8, now=None):
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_POPULATION:
            raise ValueError(f"Founder count must be between 1 and {MAX_POPULATION}")
        tank = cls(seed=seed, now=now)
        candidates = [(s, s.trials_sorted()[-1]) for s in sheet.shrimp.values() if s.trials]
        if not candidates:
            raise ValueError("The data sheet contains no shrimp")
        tank.rng.shuffle(candidates)
        selected = []
        if count >= 2:
            for sex in ("F", "M"):
                found = next((row for row in candidates if _sex(row[1]) == sex), None)
                if found:
                    selected.append(found)
        selected.extend(row for row in candidates if row not in selected)
        for shrimp, row in selected[:count]:
            field = sample_nervous_field(shrimp, row, tank.rng)
            tank.shrimps.append(LiveShrimp(
                id=shrimp.id, x=tank.rng.uniform(10, 90), y=tank.rng.uniform(10, 55),
                heading=tank.rng.uniform(-math.pi, math.pi), sex=_sex(row),
                size_mm=row.size_mm, weight_g=row.weight_g, hunger=tank.rng.uniform(0.15, 0.4),
                state="SWIM", color=tank.rng.choice(COLORS),
                speed=_clamp(field.dash_drive / 240.0, 0.6, 4.5),
                wall_preference=_clamp(field.wall_pull, 2, 15),
                freeze_chance=_clamp(field.freeze_threshold / 240.0, 0.01, 0.4),
                shelter_preference=_clamp(field.shelter_gravity / 240.0, 0.1, 0.95),
                target_size_mm=row.size_mm or 20.0, adult_weight_g=row.weight_g,
            ))
        tank._event(f"Tank started with {len(tank.shrimps)} adult shrimp. Time runs at 1×.")
        return tank

    def _event(self, message):
        self.events.append(message)
        del self.events[:-40]

    def is_mature(self, shrimp):
        return shrimp.born_at is None or self.last_updated - shrimp.born_at >= self.maturity_days * DAY

    @property
    def breeding_status(self):
        if self.breeding_pair:
            ids = " + ".join(self.breeding_pair)
            if self.courtship_started_at is None:
                return f"{ids}: approaching each other"
            seconds = max(0, math.ceil(self.courtship_started_at + 60 - self.last_updated))
            return f"{ids}: courting, {seconds}s remaining"
        berried = [s for s in self.shrimps if s.eggs]
        if berried:
            left = max(0, min(s.hatch_at for s in berried) - self.last_updated)
            return f"{sum(s.eggs for s in berried)} eggs · next hatch in {left / DAY:.2f} real days"
        return "Choose Breed to pair fed, mature female and male shrimp."

    def feed(self, x=50.0, y=50.0):
        x, y = _number(x, "food x", 0, 100), _number(y, "food y", 0, 65)
        if len(self.pellets) > MAX_PELLETS - 5:
            return "There is plenty of food already. Let the shrimp finish it first."
        for _ in range(5):
            self.pellets.append(FoodPellet(
                self.next_pellet_id, _clamp(x + self.rng.uniform(-2, 2), 1, 99),
                _clamp(y + self.rng.uniform(-2, 2), 1, 64),
            ))
            self.next_pellet_id += 1
        message = "Five food pellets added. Hungry shrimp will approach and graze."
        self._event(message)
        return message

    def toggle_light(self):
        self.light_on = not self.light_on
        self._event("Light on: more shrimp will seek shelter." if self.light_on else "Light off: shrimp explore more freely.")
        return self.light_on

    def request_breeding(self):
        if self.breeding_pair:
            return self.breeding_status
        available = MAX_POPULATION - len(self.shrimps) - sum(s.eggs for s in self.shrimps)
        if available < 60:
            return "Breeding needs room for a full clutch (60 places); this tank holds 200 shrimp."
        eligible = [s for s in self.shrimps if self.is_mature(s) and s.hunger <= 0.65 and not s.eggs]
        female = next((s for s in eligible if s.sex == "F"), None)
        male = next((s for s in eligible if s.sex == "M"), None)
        if not female or not male:
            message = "Breeding needs a fed adult female and male. Feed hungry shrimp; juveniles mature after 30 real days."
            if any(s.sex == "?" for s in self.shrimps):
                message += " Shrimp with uncertain recorded sex cannot be paired."
            self._event(message)
            return message
        self.breeding_pair = [female.id, male.id]
        self.courtship_started_at = self.last_updated if math.hypot(female.x - male.x, female.y - male.y) <= 2.5 else None
        female.state = male.state = "COURT"
        message = f"{female.id} and {male.id} are pairing. After contact they court for 60 real seconds; eggs take 18 real days."
        self._event(message)
        return message

    def advance(self, now=None):
        now = _number(time.time() if now is None else now, "now")
        elapsed = max(0.0, now - self.last_updated)
        if elapsed == 0:
            return
        self.last_updated = now
        # Biology follows elapsed wall time; animation never races to catch up.
        motion_dt = min(elapsed, 1.0)
        self._finish_courtship(now)
        for mother in list(self.shrimps):
            if mother.eggs and mother.hatch_at <= now:
                self._hatch(mother)
        partners = {s.id: s for s in self.shrimps if self.breeding_pair and s.id in self.breeding_pair}
        for shrimp in self.shrimps:
            lived_elapsed = elapsed if shrimp.born_at is None else min(elapsed, max(0, now - shrimp.born_at))
            shrimp.hunger = min(1.0, shrimp.hunger + lived_elapsed / (36 * 3600))
            if shrimp.born_at is not None:
                age_fraction = _clamp((now - shrimp.born_at) / (self.maturity_days * DAY), 0, 1)
                shrimp.size_mm = 1.5 + (shrimp.target_size_mm - 1.5) * age_fraction
                if shrimp.adult_weight_g is not None:
                    shrimp.weight_g = shrimp.adult_weight_g * (shrimp.size_mm / shrimp.target_size_mm) ** 3
            partner = next((p for p in partners.values() if p.id != shrimp.id), None) if shrimp.id in partners else None
            self._move(shrimp, motion_dt, partner)
        self.pellets = [p for p in self.pellets if p.remaining > 0.001]
        if len(partners) == 2 and self.courtship_started_at is None:
            first, second = partners.values()
            if math.hypot(first.x - second.x, first.y - second.y) <= 2.5:
                self.courtship_started_at = now
                self._event(f"{first.id} and {second.id} made contact; courtship has begun.")

    def _move(self, shrimp, dt, partner):
        target = None
        speed = shrimp.speed
        if partner:
            shrimp.state = "COURT"
            if math.hypot(shrimp.x - partner.x, shrimp.y - partner.y) <= 1.5:
                return
            target = (partner.x, partner.y)
        else:
            pellet = min(self.pellets, key=lambda p: math.hypot(p.x - shrimp.x, p.y - shrimp.y), default=None)
            if pellet and pellet.remaining > 0 and shrimp.hunger > 0.03:
                target = (pellet.x, pellet.y)
                shrimp.state = "FORAGE"
                if math.hypot(shrimp.x - pellet.x, shrimp.y - pellet.y) < 2.4:
                    eaten = min(pellet.remaining, dt * 0.1, shrimp.hunger / 0.65)
                    pellet.remaining -= eaten
                    shrimp.hunger = max(0, shrimp.hunger - eaten * 0.65)
                    shrimp.state = "BERRIED" if shrimp.eggs else "GRAZE"
                    return
            elif self.light_on and shrimp.shelter_preference > 0.38:
                target = (85.0, 20.0)
                if math.hypot(shrimp.x - 85, shrimp.y - 20) < 8:
                    shrimp.state = "BERRIED" if shrimp.eggs else "HIDE"
                    return
                shrimp.state = "HIDE"
            elif self.last_updated < shrimp.rest_until:
                shrimp.state = "BERRIED" if shrimp.eggs else "REST"
                return
            elif self.rng.random() < shrimp.freeze_chance * dt * 0.1:
                shrimp.rest_until = self.last_updated + self.rng.uniform(1, 5)
                shrimp.state = "BERRIED" if shrimp.eggs else "REST"
                return
            else:
                shrimp.state = "BERRIED" if shrimp.eggs else "SWIM"
                margin = shrimp.wall_preference
                if min(shrimp.x, 100 - shrimp.x, shrimp.y, 65 - shrimp.y) < margin:
                    shrimp.heading += math.sin(math.atan2(32.5 - shrimp.y, 50 - shrimp.x) - shrimp.heading) * dt
                shrimp.heading += self.rng.uniform(-0.6, 0.6) * math.sqrt(dt)
        if target:
            desired = math.atan2(target[1] - shrimp.y, target[0] - shrimp.x)
            delta = (desired - shrimp.heading + math.pi) % (2 * math.pi) - math.pi
            shrimp.heading += _clamp(delta, -3 * dt, 3 * dt)
            speed = min(speed, math.hypot(target[0] - shrimp.x, target[1] - shrimp.y) / dt)
        if shrimp.born_at is not None:
            speed *= 0.4 + 0.6 * min(1, (shrimp.size_mm or 1.5) / shrimp.target_size_mm)
        current = 0.06 * math.sin(self.last_updated / 17 + shrimp.y / 20)
        shrimp.x = _clamp(shrimp.x + (math.cos(shrimp.heading) * speed + current) * dt, 1, 99)
        shrimp.y = _clamp(shrimp.y + math.sin(shrimp.heading) * speed * dt, 1, 64)
        if shrimp.x in (1, 99):
            shrimp.heading = math.pi - shrimp.heading
        if shrimp.y in (1, 64):
            shrimp.heading = -shrimp.heading
        shrimp.heading = (shrimp.heading + math.pi) % (2 * math.pi) - math.pi
        if shrimp.eggs:
            shrimp.state = "BERRIED"

    def _finish_courtship(self, now):
        if not self.breeding_pair or self.courtship_started_at is None or now < self.courtship_started_at + 60:
            return
        female, male = (next(s for s in self.shrimps if s.id == sid) for sid in self.breeding_pair)
        female.eggs = self.rng.randint(43, 60)
        female.egg_father_id = male.id
        female.hatch_at = self.courtship_started_at + 60 + self.incubation_days * DAY
        female.state = "BERRIED"
        self._event(f"{female.id} is carrying {female.eggs} eggs. Incubation: {self.incubation_days:g} real days.")
        self.breeding_pair = None
        self.courtship_started_at = None

    def _hatch(self, mother):
        father = next(s for s in self.shrimps if s.id == mother.egg_father_id)
        count, born_at = mother.eggs, mother.hatch_at
        for _ in range(count):
            while any(s.id == f"J{self.next_shrimp_id:04d}" for s in self.shrimps):
                self.next_shrimp_id += 1
            target_size = (mother.target_size_mm + father.target_size_mm) / 2
            self.shrimps.append(LiveShrimp(
                id=f"J{self.next_shrimp_id:04d}", x=_clamp(mother.x + self.rng.uniform(-3, 3), 1, 99),
                y=_clamp(mother.y + self.rng.uniform(-3, 3), 1, 64), heading=self.rng.uniform(-math.pi, math.pi),
                sex=self.rng.choice(("M", "F")), size_mm=1.5, weight_g=None, hunger=0.2,
                state="SWIM", color=self.rng.choice(COLORS), generation=max(mother.generation, father.generation) + 1,
                born_at=born_at, mother_id=mother.id, father_id=father.id,
                speed=(mother.speed + father.speed) / 2 * self.rng.uniform(0.9, 1.1),
                wall_preference=(mother.wall_preference + father.wall_preference) / 2,
                freeze_chance=(mother.freeze_chance + father.freeze_chance) / 2,
                shelter_preference=(mother.shelter_preference + father.shelter_preference) / 2,
                target_size_mm=target_size, adult_weight_g=mother.adult_weight_g,
            ))
            self.next_shrimp_id += 1
        mother.eggs, mother.hatch_at, mother.egg_father_id = 0, None, None
        self._event(f"{count} juveniles hatched from {mother.id}. Their development follows real elapsed time.")

    def save(self, path):
        payload = {key: getattr(self, key) for key in (
            "created_at", "last_updated", "light_on", "events", "incubation_days", "maturity_days",
            "breeding_pair", "courtship_started_at", "next_pellet_id", "next_shrimp_id", "seed",
        )}
        payload.update(version=1, species="cherry", shrimps=[asdict(s) for s in self.shrimps],
                       pellets=[asdict(p) for p in self.pellets], rng_state=self.rng.getstate())
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                             prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
                temporary = handle.name
                json.dump(payload, handle, allow_nan=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def save_state(self, directory):
        """Write an immutable, timestamped checkpoint distinct from the rolling autosave.

        The filename locks in the exact moment saved; the payload locks in the
        founding seed and the full living population (lives). Unlike ``save``,
        this never overwrites an existing file, so past checkpoints persist.
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(self.last_updated))
        path = directory / f"state-{stamp}.json"
        if path.exists():
            raise ValueError(f"A save state already exists for this second ({path.name})")
        self.save(path)
        return path

    @classmethod
    def load(cls, path, now=None):
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
            tank = cls._from_payload(payload)
        except (TypeError, KeyError, IndexError, OverflowError, RecursionError, ValueError) as exc:
            raise ValueError(f"Invalid tank save: {exc}") from exc
        tank.advance(now)
        return tank

    @classmethod
    def _from_payload(cls, data):
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1 or data.get("species") != "cherry":
            raise ValueError("Unsupported tank format or species")
        tank = cls(now=_number(data["created_at"], "created_at"))
        seed = data.get("seed")
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise ValueError("Invalid seed")
        tank.seed = seed
        for key in ("last_updated", "incubation_days", "maturity_days"):
            setattr(tank, key, _number(data[key], key))
        if tank.last_updated < tank.created_at or not 1 <= tank.incubation_days <= 365 or not 1 <= tank.maturity_days <= 365:
            raise ValueError("Invalid tank timeline")
        if type(data["light_on"]) is not bool:
            raise ValueError("Invalid light state")
        tank.light_on = data["light_on"]
        if not isinstance(data["events"], list) or len(data["events"]) > 40 or any(not isinstance(e, str) or len(e) > 1000 for e in data["events"]):
            raise ValueError("Invalid event log")
        tank.events = data["events"]
        if not isinstance(data["shrimps"], list) or not 1 <= len(data["shrimps"]) <= MAX_POPULATION:
            raise ValueError("Invalid shrimp population")
        tank.shrimps = [LiveShrimp(**row) for row in data["shrimps"]]
        ids = {s.id for s in tank.shrimps if isinstance(s.id, str) and 0 < len(s.id) < 100}
        if len(ids) != len(tank.shrimps):
            raise ValueError("Invalid or duplicate shrimp IDs")
        for s in tank.shrimps:
            for name, low, high in (("x", 0, 100), ("y", 0, 65), ("heading", -1e6, 1e6),
                                   ("hunger", 0, 1), ("speed", 0, 100), ("wall_preference", 0, 30),
                                   ("freeze_chance", 0, 1), ("shelter_preference", 0, 1),
                                   ("target_size_mm", 1.5, 200), ("rest_until", 0, 1e16)):
                _number(getattr(s, name), name, low, high)
            for name in ("size_mm", "weight_g", "adult_weight_g", "born_at", "hatch_at"):
                if getattr(s, name) is not None:
                    _number(getattr(s, name), name)
            if s.sex not in ("M", "F", "?") or s.state not in ("SWIM", "GRAZE", "REST", "HIDE", "COURT", "BERRIED", "FORAGE"):
                raise ValueError("Invalid shrimp sex or state")
            if not isinstance(s.color, str) or len(s.color) != 7 or s.color[0] != "#" or any(c not in "0123456789abcdefABCDEF" for c in s.color[1:]):
                raise ValueError("Invalid shrimp color")
            if type(s.generation) is not int or s.generation < 0 or type(s.eggs) is not int or not 0 <= s.eggs <= 60:
                raise ValueError("Invalid generation or clutch")
            if any(parent is not None and parent not in ids for parent in (s.mother_id, s.father_id, s.egg_father_id)):
                raise ValueError("Unknown parent")
            if bool(s.eggs) != (s.hatch_at is not None) or (s.eggs and (s.sex != "F" or s.egg_father_id is None)):
                raise ValueError("Invalid egg deadline or parent")
        if not isinstance(data["pellets"], list) or len(data["pellets"]) > MAX_PELLETS:
            raise ValueError("Invalid food list")
        tank.pellets = [FoodPellet(**row) for row in data["pellets"]]
        pellet_ids = set()
        for p in tank.pellets:
            if type(p.id) is not int or p.id < 1 or p.id in pellet_ids:
                raise ValueError("Invalid food ID")
            pellet_ids.add(p.id)
            _number(p.x, "food x", 0, 100)
            _number(p.y, "food y", 0, 65)
            _number(p.remaining, "food remaining", 0, 1)
        for key in ("next_pellet_id", "next_shrimp_id"):
            if type(data[key]) is not int or data[key] < 1:
                raise ValueError(f"Invalid {key}")
            setattr(tank, key, data[key])
        if pellet_ids and tank.next_pellet_id <= max(pellet_ids):
            raise ValueError("Invalid next food ID")
        pair = data["breeding_pair"]
        if pair is not None:
            if not isinstance(pair, list) or len(pair) != 2 or any(not isinstance(sid, str) or sid not in ids for sid in pair) or pair[0] == pair[1]:
                raise ValueError("Invalid breeding pair")
            female, male = (next(s for s in tank.shrimps if s.id == sid) for sid in pair)
            if female.sex != "F" or male.sex != "M" or female.eggs or not tank.is_mature(female) or not tank.is_mature(male):
                raise ValueError("Ineligible breeding pair")
        tank.breeding_pair = pair
        tank.courtship_started_at = data["courtship_started_at"]
        if tank.courtship_started_at is not None:
            _number(tank.courtship_started_at, "courtship_started_at", tank.created_at, tank.last_updated)
            if pair is None:
                raise ValueError("Courtship has no pair")
        if len(tank.shrimps) + sum(s.eggs for s in tank.shrimps) + (60 if pair else 0) > MAX_POPULATION:
            raise ValueError("Tank exceeds population capacity")
        def tuples(value):
            return tuple(tuples(v) for v in value) if isinstance(value, list) else value
        tank.rng.setstate(tuples(data["rng_state"]))
        return tank
