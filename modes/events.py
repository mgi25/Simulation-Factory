"""Battle events: the presentation contract between rules and renderers.

A renderer can read state - where a fighter is, how much health it has - out
of any replay frame. What it cannot read is the *moment* something happened:
frames are sampled at 60 Hz while physics runs at 120 Hz, and a hit that lands
between two samples leaves nothing behind but a health number that already
moved. Guessing those moments back out of health differences is exactly the
kind of gameplay inference the renderer must not do.

So the battle mode records them. This is not telemetry and not an event bus:
it is a flat, ordered, tick-stamped list of the few moments worth drawing.
Nothing in the rules reads it back, so recording an event can never change
what happens in a battle.
"""

from __future__ import annotations

from dataclasses import dataclass

# The three kinds of moment a renderer needs. Deliberately few: every new type
# is a new thing every renderer has to decide what to do with.
EVENT_POWER_ACTIVATE = "power_activate"
EVENT_HIT = "hit"
EVENT_ELIMINATION = "elimination"

# The only subtype not taken straight from a dynamic entity's `kind`: a
# fighter ramming another fighter has no entity to name it.
HIT_IMPACT = "impact"


@dataclass(frozen=True)
class BattleEvent:
    """One thing worth drawing, stamped with the simulation tick it happened on.

    Positions are in logical simulation pixels, like every other coordinate
    the replay carries. `magnitude` is real HP removed, after any mitigation,
    so a renderer never has to know what a damage multiplier is.
    """

    tick: int
    type: str
    x: float
    y: float
    source_id: int | None = None
    target_id: int | None = None
    subtype: str | None = None
    magnitude: float | None = None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        label = self.type if self.subtype is None else f"{self.type}/{self.subtype}"
        return f"<BattleEvent t={self.tick} {label} {self.source_id}->{self.target_id}>"
