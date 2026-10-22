"""Turn order and saved games for a tactics battle."""

import json
from dataclasses import dataclass


@dataclass
class Unit:
    uid: str
    speed: int
    hp: int
    delay: int = 0


@dataclass
class Battle:
    units: list[Unit]
    round_no: int = 1

    def order(self):
        """Return the uids of the living units for this round.

        The fastest goes first, by speed minus delay; units with the same
        effective speed go in ascending uid order.
        """
        alive = [unit for unit in self.units if unit.hp > 0]
        alive.sort(key=lambda unit: (-(unit.speed - unit.delay), unit.uid))
        return [unit.uid for unit in alive]

    def end_round(self):
        """Start the next round; every delay wears off by one, down to 0."""
        self.round_no += 1
        for unit in self.units:
            unit.delay = max(0, unit.delay - 1)


def save(battle):
    """Return the battle as JSON text; the same battle gives the same text."""
    units = [
        {"uid": unit.uid, "speed": unit.speed, "hp": unit.hp, "delay": unit.delay}
        for unit in battle.units
    ]
    return json.dumps({"round_no": battle.round_no, "units": units}, sort_keys=True)


def _field(data, name, kind):
    """Return data[name] when it is present and of exactly the given type."""
    if not isinstance(data, dict) or name not in data:
        raise ValueError(f"saved battle is missing {name!r}")
    value = data[name]
    if type(value) is not kind:
        raise ValueError(f"{name!r} must be of type {kind.__name__}")
    return value


def load(text):
    """Return the battle saved in text, or raise ValueError."""
    if not isinstance(text, (str, bytes, bytearray)):
        raise ValueError("a saved battle is text")
    try:
        data = json.loads(text)
    except ValueError as error:
        raise ValueError(f"saved battle is not valid JSON: {error}") from error
    round_no = _field(data, "round_no", int)
    units = [
        Unit(
            _field(row, "uid", str),
            _field(row, "speed", int),
            _field(row, "hp", int),
            _field(row, "delay", int),
        )
        for row in _field(data, "units", list)
    ]
    return Battle(units, round_no)
