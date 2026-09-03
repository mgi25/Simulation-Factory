"""Modular powers: the registry and deterministic assignment helpers.

Assignment always draws from an explicitly passed seeded RNG, never from the
global `random` module, so a seed fully determines the matchup.
"""

from __future__ import annotations

import random
from typing import Iterable, Sequence

from powers.power import Power, seconds_to_ticks
from powers.rush import RushPower
from powers.titan import TitanPower

POWER_CLASSES: dict[str, type[Power]] = {
    RushPower.name: RushPower,
    TitanPower.name: TitanPower,
}
POWER_NAMES: tuple[str, ...] = tuple(POWER_CLASSES)

# Spread out the first activation a little so two identical powers do not
# fire in permanent lockstep. Seeded, therefore reproducible.
INITIAL_OFFSET_MAX_TICKS = seconds_to_ticks(1.5)

PowerSpec = str | Power | type[Power]

__all__ = [
    "INITIAL_OFFSET_MAX_TICKS",
    "POWER_CLASSES",
    "POWER_NAMES",
    "Power",
    "PowerSpec",
    "RushPower",
    "TitanPower",
    "assign_powers",
    "create_power",
    "power_class",
]


def power_class(name: str) -> type[Power]:
    try:
        return POWER_CLASSES[str(name).strip().lower()]
    except KeyError:
        raise ValueError(
            f"unknown power {name!r}; known powers: {', '.join(POWER_NAMES)}"
        ) from None


def create_power(spec: PowerSpec, rng: random.Random | None = None) -> Power:
    """Build a power from a name, a class or an already-configured instance.

    Ready-made instances are returned untouched, which is how tests and
    debugging sessions pin an exact activation schedule.
    """
    if isinstance(spec, Power):
        return spec
    cls = spec if isinstance(spec, type) and issubclass(spec, Power) else power_class(spec)
    delay = 0 if rng is None else rng.randrange(INITIAL_OFFSET_MAX_TICKS)
    return cls(initial_delay_ticks=delay)


def assign_powers(
    rng: random.Random, count: int, specs: Iterable[PowerSpec] | None = None
) -> list[Power]:
    """Return `count` powers, either drawn from `rng` or taken from `specs`."""
    if specs is None:
        chosen: Sequence[PowerSpec] = [rng.choice(POWER_NAMES) for _ in range(count)]
    else:
        chosen = list(specs)
        if len(chosen) != count:
            raise ValueError(f"expected {count} power specs, got {len(chosen)}")
    return [create_power(spec, rng) for spec in chosen]
