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
        """Return the uids of the living units, fastest first."""
        alive = [unit for unit in self.units if unit.hp > 0]
        return [unit.uid for unit in sorted(alive, key=lambda unit: -unit.speed)]

    def end_round(self):
        """Start the next round."""
        self.round_no += 1


def save(battle):
    """Return the battle as JSON text."""
    units = [{"uid": u.uid, "speed": u.speed, "hp": u.hp} for u in battle.units]
    return json.dumps({"units": units})


def load(text):
    """Return the battle saved in text."""
    data = json.loads(text)
    return Battle([Unit(u["uid"], u["speed"], u["hp"]) for u in data["units"]])
