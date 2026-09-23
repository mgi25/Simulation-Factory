"""Deterministic musical scoring for the multiplying-shell arena.

This is the middle layer between the frozen V2 playback document and sample
synthesis. It reads canonical events and emits musical decisions; it imports
neither the simulator nor the synthesiser. That boundary is what lets audio
describe the physics and never influence it.

## The arena is one instrument with a growing cast

Test #2's redesign turns one ball into many, so the piece has to hold together
while the number of players rises from one to as many as fifteen. Two rules do
that work, and both are structural rather than corrective.

**One pitch collection for the whole run.** Every note any ball plays, in any
shell, at any moment, is drawn from a single five-note collection. The
collection is chosen so that no two of its members are a semitone or a tritone
apart *in any octave*, which makes every simultaneity consonant by
construction rather than by policing. This is why the module carries a ladder
instead of a per-shell transposition in semitones: transposing a pentatonic by
a fifth adds a sixth pitch class - a major pentatonic on A plus the same
collection on E contains both A and G# - and the guarantee is gone. Indexing
the shells into positions of one scale ladder keeps the union of everything
playable equal to the collection itself.

**Family, not randomness.** A ball's voice is its parent's voice plus a small
deterministic step - a walk down the lineage rather than a draw per ball. The
founder sits at the neutral centre of every axis, so siblings are near each
other, cousins further, and a fourth-generation descendant is recognisably of
the same family without being a copy. Nothing here is seeded from the run; the
same lineage always produces the same voice.

## What each canonical fact means

| Canonical fact | Musical decision |
| --- | --- |
| `collision.position.y / shell.radius` | degree inside the shell's five-note window |
| `collision.shell_id` | which window of the ladder, and how much weight and ring |
| `ball_id` lineage | overtone tint, attack, pan bias, register preference, detune |
| `impact_speed` | note gain and transient energy |
| `incidence` | articulation: head-on is short and struck, glancing is long and soft |
| `feature == "post"` | a sharper, higher transient |
| panel damage entering the contact | longer ring and a progressively stretched partial |
| `damage_state` transition | a brief ornament inside that collision's voice |
| `near_miss` and `signed_lead` | an unresolved neighbour degree, hanging, inside the voice |
| `panel_break` | a short palette chord, then space |
| `ball_spawn` | parent tone, then the child's own tone a mirrored fifth away |
| the run's first entry into a region | the progression lift |
| a repeat outward crossing | a quiet passage marker under the bed |
| `escape` | the collection's tonic chord, with the bed ducked around it |

## What this module refuses to do

It does not move an event. Every sounding instant is `round(t * 48000)`, and
`sync_report` proves the result is within half a sample of canonical time.
There is no grid, no quantiser and no tempo. It does not drop a collision
either: density is answered with shorter and quieter voices, never with
silence, because a bounce the viewer can see and cannot hear is the one defect
this layer cannot be forgiven.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Mapping, Sequence

__all__ = [
    "SCORE_VERSION",
    "SCHEMA_VERSION",
    "CONFIG_DIGEST",
    "EVENT_KINDS",
    "EVENT_TIER",
    "SYSTEMS",
    "CONFIGS",
    "DEFAULT_CONFIG",
    "SELECTED_SYSTEM",
    "LADDER_TOP",
    "ScoreError",
    "TonalSystem",
    "AudioConfig",
    "Voice",
    "AudioEvent",
    "AudioSchedule",
    "named_system",
    "named_config",
    "voices_for",
    "degree_for",
    "frequency_for_index",
    "semitones_for_index",
    "schedule",
    "score_document",
    "schedule_metrics",
]

SCORE_VERSION = "category3-test2-multiplying-shell-audio-score/1.0.0"
#: The only event stream this layer will read. Phase 1 froze it.
SCHEMA_VERSION = "category3-test2-multiplying-shell/2.0.0"
#: The locked Phase 1 arena. A document made with any other configuration is
#: refused rather than scored, because every register and threshold below was
#: chosen against this geometry.
CONFIG_DIGEST = "dcf3c2bf05879e087246bd3ae22bacbb273d64411405356fd5f329bf8c1ea0bd"

SAMPLE_RATE = 48_000

#: Ordered by the brief's importance hierarchy, lowest first. The order is also
#: the tie-break when two events land on the same sample.
EVENT_KINDS: tuple[str, ...] = (
    "crossing",
    "collision",
    "spawn",
    "break",
    "lift",
    "escape",
)

#: normal bounce < strong/frontier hit < near miss / damage transition <
#: spawn < panel break / progression lift < final escape. The first three tiers
#: all live on `collision`, because a near miss and a damage transition are
#: canonically *inside* a contact rather than beside one; the tier they earn
#: changes that contact's own voice instead of adding another to the count.
COLLISION_TIER_NORMAL = 1
COLLISION_TIER_STRONG = 2
COLLISION_TIER_MARKED = 3

EVENT_TIER: dict[str, int] = {
    "crossing": 0,
    "collision": COLLISION_TIER_NORMAL,
    "spawn": 4,
    "break": 5,
    "lift": 5,
    "escape": 6,
}

#: The highest ladder position the arena will play. Three octaves of the
#: collection above the root: with a root of 220 Hz that is a compass of
#: 220-1480 Hz, which survives a phone speaker at the bottom and does not turn
#: shrill at the top when fifteen balls are sounding.
LADDER_TOP = 14

DAMAGE_STATES: tuple[str, ...] = ("healthy", "damaged", "critical", "fractured", "broken")


class ScoreError(ValueError):
    """The canonical document or the audio configuration cannot be scored."""


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))


def _unit(*parts: object) -> float:
    """A stable float in [0, 1) from any tuple of parts.

    `hashlib` rather than `random`: the value must not depend on interpreter
    version, insertion order, or how many balls were asked about first.
    """
    blob = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(blob).digest()[:8], "big") / 2.0 ** 64


# --------------------------------------------------------------------------
# The tonal system
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TonalSystem:
    """One globally compatible vocabulary: a collection, and where shells sit in it.

    `scale` is the collection, in semitones above the root, and it is the whole
    pitch content of the run. `shell_bases` are positions in the ladder built
    from that collection - not transpositions in semitones - which is what
    keeps the union of everything playable equal to `scale` itself.
    """

    name: str
    scale: tuple[int, ...]
    shell_bases: tuple[int, ...]
    root_hz: float = 220.0
    #: How many ladder steps above its base a shell's window reaches.
    window: int = 4

    def __post_init__(self) -> None:
        if len(self.scale) < 4:
            raise ScoreError("a tonal collection needs at least four degrees")
        if self.scale[0] != 0 or list(self.scale) != sorted(set(self.scale)):
            raise ScoreError("the collection must start at 0 and be strictly increasing")
        if self.scale[-1] >= 12:
            raise ScoreError("the collection must fit inside one octave")
        harsh = self.harsh_intervals()
        if harsh:
            raise ScoreError(
                f"{self.name}: degrees {harsh[0][0]} and {harsh[0][1]} are "
                f"{harsh[0][2]} semitones apart modulo an octave, which is a "
                "semitone or a tritone in some voicing"
            )
        if not self.shell_bases:
            raise ScoreError("at least one shell window is needed")
        if list(self.shell_bases) != sorted(self.shell_bases):
            raise ScoreError("shell windows must rise outward")
        if self.shell_bases[-1] + self.window > LADDER_TOP:
            raise ScoreError(f"{self.name}: the outermost window runs off the ladder")

    def harsh_intervals(self) -> tuple[tuple[int, int, int], ...]:
        """Every pair of collection members a semitone or tritone apart, in any octave.

        Empty is the point of the check. A pair at 1, 6 or 11 semitones modulo
        12 is a minor second, a tritone or a major seventh depending on which
        octaves the two balls happen to be in, and a run does not get to choose.
        """
        out: list[tuple[int, int, int]] = []
        for index, low in enumerate(self.scale):
            for high in self.scale[index + 1:]:
                gap = (high - low) % 12
                if gap in (1, 6, 11):
                    out.append((low, high, gap))
        return tuple(out)

    def ladder_semitones(self, index: int) -> int:
        octave, step = divmod(index, len(self.scale))
        return self.scale[step] + 12 * octave

    def frequency(self, index: int) -> float:
        return self.root_hz * 2.0 ** (self.ladder_semitones(index) / 12.0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "scale": list(self.scale),
            "shell_bases": list(self.shell_bases),
            "root_hz": self.root_hz,
            "window": self.window,
        }


def frequency_for_index(system: TonalSystem, index: int) -> float:
    return system.frequency(index)


def semitones_for_index(system: TonalSystem, index: int) -> int:
    return system.ladder_semitones(index)


#: Three systems, differing on the axes that decide whether dense polyphony
#: coheres: the collection itself, and - through the timbre dials in the
#: configs below - how long and how bright a voice is. Same root and same
#: ladder height in all three, so the comparison is of musical systems and not
#: of absolute pitch or of loudness.
SYSTEMS: dict[str, TonalSystem] = {
    # Major pentatonic: the brightest of the three and the most familiar.
    "bright_pentatonic": TonalSystem(
        name="bright_pentatonic",
        scale=(0, 2, 4, 7, 9),
        shell_bases=(0, 2, 4, 6, 8),
    ),
    # Suspended pentatonic - the second mode of the same interval family, with
    # two stacked fourths inside it (0-5-10). It is what makes a dense passage
    # read as an open chord rather than as a melody fighting itself.
    "open_quartal": TonalSystem(
        name="open_quartal",
        scale=(0, 2, 5, 7, 10),
        shell_bases=(0, 2, 4, 6, 8),
    ),
    # Minor pentatonic: darkest, and the one that reads the multiplying arena
    # as pressure rather than as play.
    "deep_minor": TonalSystem(
        name="deep_minor",
        scale=(0, 3, 5, 7, 10),
        shell_bases=(0, 2, 4, 6, 8),
    ),
}


def named_system(name: str) -> TonalSystem:
    if name not in SYSTEMS:
        raise ScoreError(f"unknown tonal system {name!r}; known: {sorted(SYSTEMS)}")
    return SYSTEMS[name]


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AudioConfig:
    """Every score and synthesis dial that identifies one waveform."""

    name: str = "bright_pentatonic"
    system: str = "bright_pentatonic"
    sample_rate: int = SAMPLE_RATE

    # --- voice identity --------------------------------------------------
    #: How far one generation may step from its parent on each voice axis.
    lineage_spread: float = 0.30
    #: The widest detune a lineage walk can reach, in cents. Small enough to
    #: read as family width rather than as an out-of-tune arena.
    detune_cents: float = 7.0
    #: The stereo offset a lineage may accumulate, on top of position pan.
    lineage_pan: float = 0.16
    pan_depth: float = 0.30

    # --- the collision bed -----------------------------------------------
    collision_gain_low: float = 0.085
    collision_gain_high: float = 0.190
    collision_seconds: float = 0.190
    collision_decay: float = 0.080
    #: Voices shorten as the local rate rises. This is the whole answer to
    #: 5.9 collisions a second: nothing is dropped, everything gets tighter.
    density_window_seconds: float = 0.60
    density_tighten: float = 0.105
    density_floor: float = 0.45
    #: Above this many contacts in the backward window a bounce is also pulled
    #: down in level, so a cluster does not simply sum.
    density_gain_floor: float = 0.62
    resonance: float = 0.36
    transient: float = 0.20
    brightness: float = 0.50
    #: How much a shell's index adds to weight (sub-octave) and to ring.
    shell_weight: float = 0.42
    shell_ring: float = 0.30
    damage_colour: float = 0.34
    damage_ring: float = 0.55
    near_miss_colour: float = 0.24
    state_colour: float = 0.22
    #: A strong hit is one at or above this share of the reference speed, or on
    #: the run's frontier shell. It earns the second collision tier.
    strong_impact: float = 0.72
    strong_gain: float = 1.16

    # --- the marked events -----------------------------------------------
    crossing_gain: float = 0.055
    crossing_seconds: float = 0.150
    spawn_gain: float = 0.205
    #: How far to either side the two halves of a split are placed. The child
    #: always takes the side the parent did not, because a spawn that lands on
    #: top of its own parent is a louder note rather than a second ball.
    spawn_split_pan: float = 0.34
    #: A ball's first crossing of a shell is both what makes it reproduce and,
    #: when nobody has been out there before, the run's arrival in a new
    #: region - so every progression lift lands on the same sample as a spawn.
    #: The lift carries that moment and the spawn steps back under it rather
    #: than the two summing into the loudest thing before the escape.
    spawn_with_lift_gain: float = 0.70
    spawn_seconds: float = 0.300
    spawn_split_seconds: float = 0.085
    break_gain: float = 0.300
    break_seconds: float = 0.420
    lift_gain: float = 0.265
    lift_seconds: float = 0.520
    escape_gain: float = 0.400
    escape_seconds: float = 1.700

    # --- ducking ---------------------------------------------------------
    #: How far the collision bed steps aside for each tier, in decibels, and
    #: for how long. Shallow and short on purpose: the brief asks for space,
    #: not for pumping.
    duck_spawn_db: float = 2.0
    duck_break_db: float = 3.0
    duck_lift_db: float = 2.6
    duck_escape_db: float = 9.0
    duck_marked_hold: float = 0.090
    duck_marked_release: float = 0.220
    duck_escape_hold: float = 0.620
    duck_escape_release: float = 0.900
    #: A gain ramp, never an event move: the only thing in this layer that
    #: looks forward, and it looks 80 ms.
    duck_lead_seconds: float = 0.080
    duck_floor_db: float = 10.0

    # --- cluster management ----------------------------------------------
    #: Two notes inside this window are heard as one chord, so they are checked
    #: against each other for unison and for low-register crowding.
    cluster_seconds: float = 0.030
    #: A pitch repeating inside this window is nudged one ladder step and eased
    #: down, which is what stops a ball trapped between two panels from
    #: machine-gunning one note.
    repeat_seconds: float = 0.140
    repeat_gain: float = 0.80

    # --- tail ------------------------------------------------------------
    #: The pad after the last voice has decayed, not a fixed hold after the
    #: escape: the resolution decides how long the piece is, and the pad only
    #: guarantees the file ends in exact digital silence.
    tail_seconds: float = 0.450
    end_silence_seconds: float = 0.150

    # --- master ----------------------------------------------------------
    master_gain: float = 1.35
    peak_ceiling_dbfs: float = -2.5

    def __post_init__(self) -> None:
        if self.sample_rate != SAMPLE_RATE:
            raise ScoreError("multiplying-shell audio is mastered at 48 kHz")
        if self.system not in SYSTEMS:
            raise ScoreError(f"unknown tonal system {self.system!r}")
        if not 0.0 <= self.pan_depth <= 0.6:
            raise ScoreError("pan depth must preserve a strong mono centre")
        if not 0.0 < self.density_floor <= 1.0:
            raise ScoreError("the density floor must shorten a voice, not silence it")
        if self.end_silence_seconds >= self.tail_seconds:
            raise ScoreError("the ending needs sound before its final silence")
        if self.duck_floor_db < max(self.duck_escape_db, self.duck_break_db):
            raise ScoreError("the duck floor must be reachable by the deepest duck")

    @property
    def tonal(self) -> TonalSystem:
        return SYSTEMS[self.system]

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["tonal_system"] = self.tonal.as_dict()
        return out

    def fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


#: One config per system. The dials that differ are the ones the system implies:
#: a quartal collection wants longer, softer voices to let the fourths ring; a
#: minor collection wants a shorter, woodier note or it turns into a drone.
CONFIGS: dict[str, AudioConfig] = {
    "bright_pentatonic": AudioConfig(),
    "open_quartal": AudioConfig(
        name="open_quartal",
        system="open_quartal",
        collision_seconds=0.265,
        collision_decay=0.118,
        resonance=0.54,
        transient=0.13,
        brightness=0.44,
        shell_ring=0.40,
        damage_ring=0.65,
        density_tighten=0.125,
        break_seconds=0.470,
        lift_seconds=0.580,
        spawn_seconds=0.340,
    ),
    "deep_minor": AudioConfig(
        name="deep_minor",
        system="deep_minor",
        collision_seconds=0.140,
        collision_decay=0.056,
        resonance=0.26,
        transient=0.26,
        brightness=0.56,
        shell_weight=0.52,
        shell_ring=0.22,
        damage_ring=0.45,
        density_tighten=0.085,
        break_seconds=0.370,
        lift_seconds=0.470,
        spawn_seconds=0.265,
    ),
}
#: The system the Phase 2B comparison selected, and therefore the default.
#: `open_quartal` won on the one axis the redesign exists to produce - it grows
#: from the sparse opening to the crowded close by half a voice more than the
#: next system - while raising rather than lowering the share of energy
#: standing on palette pitches, and without costing a single audible bounce.
#: `docs/category3_multiplying_shell_audio_phase2b.md` carries the table.
SELECTED_SYSTEM = "open_quartal"
DEFAULT_CONFIG = CONFIGS[SELECTED_SYSTEM]


def named_config(name: str, **overrides: Any) -> AudioConfig:
    if name not in CONFIGS:
        raise ScoreError(f"unknown audio config {name!r}; known: {sorted(CONFIGS)}")
    return replace(CONFIGS[name], **overrides) if overrides else CONFIGS[name]


# --------------------------------------------------------------------------
# Voice identity, walked down the lineage
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Voice:
    """One ball's timbral identity, inherited rather than drawn."""

    ball_id: int
    parent_id: int | None
    generation: int
    lineage: tuple[int, ...]
    #: 0 is the founder's overtone mix; 1 is the brightest a lineage can walk to.
    tint: float
    #: 0 is the founder's attack; below is softer, above is sharper.
    edge: float
    #: Stereo offset, in [-1, 1], before `lineage_pan` scales it.
    pan_bias: float
    #: Ladder steps a ball prefers above or below its shell's window.
    register: int
    #: True when the ball takes the octave above, and only where it fits.
    octave_up: bool
    detune: float

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["lineage"] = list(self.lineage)
        return out


def _walk(base: float, unit: float, spread: float) -> float:
    """One generation's step away from the parent, bounded and centred."""
    return _clamp(base + spread * (2.0 * unit - 1.0), 0.0, 1.0)


def voices_for(balls: Sequence[Mapping[str, Any]],
               config: AudioConfig = DEFAULT_CONFIG) -> dict[int, Voice]:
    """A voice per ball, each one its parent's voice plus one small step.

    The founder is the neutral centre of every axis - 0.5 on the unit axes, no
    register preference, no detune - so the family has a middle rather than an
    arbitrary corner, and a descendant's distance from the founder is a
    readable measure of how far down the lineage it sits.
    """
    ordered = sorted(balls, key=lambda row: (float(row["birth_time"]), int(row["ball_id"])))
    voices: dict[int, Voice] = {}
    for row in ordered:
        ball_id = int(row["ball_id"])
        parent_id = row.get("parent_id")
        lineage = tuple(int(v) for v in row.get("lineage", (ball_id,)))
        generation = int(row.get("generation", 0))
        if parent_id is None:
            voices[ball_id] = Voice(
                ball_id=ball_id,
                parent_id=None,
                generation=generation,
                lineage=lineage,
                tint=0.5,
                edge=0.5,
                pan_bias=0.0,
                register=0,
                octave_up=False,
                detune=0.0,
            )
            continue
        parent = voices.get(int(parent_id))
        if parent is None:
            raise ScoreError(f"ball {ball_id} is born before its parent {parent_id}")
        spread = config.lineage_spread
        tint = _walk(parent.tint, _unit("tint", ball_id, parent_id), spread)
        edge = _walk(parent.edge, _unit("edge", ball_id, parent_id), spread)
        pan_bias = _clamp(
            parent.pan_bias + spread * (2.0 * _unit("pan", ball_id, parent_id) - 1.0),
            -1.0, 1.0,
        )
        # Register walks by whole ladder steps so a sibling is a scale degree
        # away rather than a few cents away, which is the difference between
        # two voices and one blurred one.
        roll = _unit("register", ball_id, parent_id)
        step = -1 if roll < 0.28 else (1 if roll > 0.72 else 0)
        register = max(-2, min(2, parent.register + step))
        octave_up = _unit("octave", ball_id, parent_id) > 0.78
        detune = _clamp(
            parent.detune + 0.5 * (2.0 * _unit("detune", ball_id, parent_id) - 1.0),
            -1.0, 1.0,
        )
        voices[ball_id] = Voice(
            ball_id=ball_id,
            parent_id=int(parent_id),
            generation=generation,
            lineage=lineage,
            tint=tint,
            edge=edge,
            pan_bias=pan_bias,
            register=register,
            octave_up=octave_up,
            detune=detune,
        )
    return voices


# --------------------------------------------------------------------------
# Pitch
# --------------------------------------------------------------------------


def degree_for(position_y: float, radius: float, degrees: int) -> int:
    """Contact height inside a shell, as an equal-width band of the window.

    Equal-width rather than the rounded mapping the single-ball version used:
    rounding gives the two outer degrees half the width of the three inner
    ones, which with fifteen balls is a measurable bias towards the middle of
    every register.
    """
    if radius <= 0.0 or degrees < 2:
        raise ScoreError("pitch mapping needs a positive radius and at least two degrees")
    unit = _clamp(float(position_y) / radius, -1.0, 1.0)
    return min(degrees - 1, int((unit + 1.0) * 0.5 * degrees))


def _ladder_index(system: TonalSystem, shell_id: int, degree: int, voice: Voice) -> int:
    if not 0 <= shell_id < len(system.shell_bases):
        raise ScoreError(f"shell {shell_id} is outside the {len(system.shell_bases)}-shell instrument")
    index = system.shell_bases[shell_id] + degree + voice.register
    if voice.octave_up and index + len(system.scale) <= LADDER_TOP:
        index += len(system.scale)
    return max(0, min(LADDER_TOP, index))


def _pan(position_x: float, radius: float, voice: Voice, config: AudioConfig,
         scale: float = 1.0) -> float:
    positional = _clamp(float(position_x) / max(radius, 1e-9), -1.0, 1.0) * config.pan_depth
    return _clamp(
        (positional + voice.pan_bias * config.lineage_pan) * scale, -1.0, 1.0
    )


def _spawn_child_pan(parent_pan: float, child: Voice, config: AudioConfig) -> float:
    """The child takes the side its parent did not, by a width its lineage sets.

    Mirroring and then adding the child's own bias is the obvious version and
    it is wrong: a descendant that has walked far enough to one side can
    overpower the mirror and land back on top of its parent, which on this run
    happened to two spawns of fourteen. The side is decided first and the
    lineage only widens or narrows the gap.
    """
    side = 1.0 if parent_pan >= 0.0 else -1.0
    width = config.spawn_split_pan * (1.0 + 0.5 * child.pan_bias)
    return -side * _clamp(width, 0.12, 0.60)


def _sample_at(seconds: float, sample_rate: int = SAMPLE_RATE) -> int:
    return int(round(seconds * sample_rate))


# --------------------------------------------------------------------------
# The scheduled event
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AudioEvent:
    """One sounding decision, fixed to one canonical instant."""

    kind: str
    tier: int
    source_seconds: float
    sample_offset: int
    seconds: float
    gain: float
    pan: float
    frequency_hz: float
    ladder_index: int
    ball_id: int
    shell_id: int
    generation: int = 0
    panel_id: int | None = None
    degree: int = 0
    impact: float = 0.0
    incidence: float = 0.0
    feature: str | None = None
    route: str | None = None
    damage_before: float = 0.0
    damage_state: str = "healthy"
    state_step: int = 0
    strong: bool = False
    with_lift: bool = False
    near_miss: bool = False
    near_miss_direction: int = 0
    repeat_nudged: bool = False
    cluster_nudged: bool = False
    density: int = 1
    region: int = 0
    progress: float = 0.0
    tint: float = 0.5
    edge: float = 0.5
    detune: float = 0.0
    secondary_hz: float = 0.0
    secondary_index: int = 0
    secondary_pan: float = 0.0
    secondary_tint: float = 0.5
    chord: tuple[int, ...] = ()

    @property
    def at_seconds(self) -> float:
        return self.sample_offset / float(SAMPLE_RATE)

    @property
    def end_seconds(self) -> float:
        return self.source_seconds + self.seconds

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["chord"] = list(self.chord)
        return out


@dataclass(frozen=True)
class AudioSchedule:
    seed: int
    playback_digest: str
    config: AudioConfig
    voices: dict[int, Voice]
    events: tuple[AudioEvent, ...]
    total_seconds: float
    total_samples: int
    escape_seconds: float
    metrics: dict[str, Any] = field(default_factory=dict)

    def of_kind(self, kind: str) -> tuple[AudioEvent, ...]:
        return tuple(event for event in self.events if event.kind == kind)

    def as_dict(self) -> dict[str, Any]:
        return {
            "score_version": SCORE_VERSION,
            "kind": "category3_multiplying_shell_audio_score",
            "schema": SCHEMA_VERSION,
            "seed": self.seed,
            "playback_digest": self.playback_digest,
            "config": self.config.as_dict(),
            "config_fingerprint": self.config.fingerprint(),
            "total_seconds": self.total_seconds,
            "total_samples": self.total_samples,
            "escape_seconds": self.escape_seconds,
            "voices": [self.voices[key].as_dict() for key in sorted(self.voices)],
            "metrics": self.metrics,
            "events": [event.as_dict() for event in self.events],
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


def _validate_document(document: Mapping[str, Any]) -> None:
    if document.get("schema") != SCHEMA_VERSION:
        raise ScoreError(f"not the frozen V2 event schema {SCHEMA_VERSION}")
    if document.get("config_digest") != CONFIG_DIGEST:
        raise ScoreError("the playback was not made with the locked Phase 1 arena")
    for key in ("events", "shells", "balls", "summary"):
        if not document.get(key):
            raise ScoreError(f"the playback document has no {key}")


def _by_contact(events: Sequence[Mapping[str, Any]], kind: str) -> dict[tuple[float, int], Mapping[str, Any]]:
    """Index the satellite streams by the contact they belong to.

    Every `damage`, `damage_state`, `near_miss` and `panel_break` in the V2
    stream is emitted at the instant of a contact, by the ball that made it, so
    `(t, ball_id)` identifies the contact uniquely - there is no instant in any
    candidate run at which two balls touch a panel.
    """
    out: dict[tuple[float, int], Mapping[str, Any]] = {}
    for event in events:
        if event.get("kind") == kind:
            out[(float(event["t"]), int(event["ball_id"]))] = event
    return out


def _density_counts(times: Sequence[float], window: float) -> list[int]:
    """How many contacts landed in the `window` seconds up to and including each one.

    Backward-looking on purpose. A symmetric window would let a note that has
    not happened yet shorten one that already has, which is a small piece of
    clairvoyance that would be very hard to see in a waveform and very easy to
    leave in.
    """
    counts: list[int] = []
    start = 0
    for index, moment in enumerate(times):
        while times[start] < moment - window:
            start += 1
        counts.append(index - start + 1)
    return counts


def _state_index(name: str) -> int:
    try:
        return DAMAGE_STATES.index(name)
    except ValueError:
        return 0


def schedule(document: Mapping[str, Any],
             config: AudioConfig = DEFAULT_CONFIG) -> AudioSchedule:
    """Translate one canonical run into a deterministic musical schedule."""
    _validate_document(document)
    system = config.tonal
    degrees = system.window + 1
    canonical = document["events"]
    shells = {int(row["shell_id"]): row for row in document["shells"]}
    balls = {int(row["ball_id"]): row for row in document["balls"]}
    voices = voices_for(document["balls"], config)

    damage_at = _by_contact(canonical, "damage")
    state_at = _by_contact(canonical, "damage_state")
    near_at = _by_contact(canonical, "near_miss")
    break_at = _by_contact(canonical, "panel_break")

    collision_times = [float(e["t"]) for e in canonical if e["kind"] == "collision"]
    density = dict(zip(collision_times,
                       _density_counts(collision_times, config.density_window_seconds)))

    frontier = 0
    escape_seconds = 0.0
    events: list[AudioEvent] = []
    last_pitch_at: dict[int, float] = {}
    # `shell_exit` is emitted before the `ball_spawn` it causes, so by the
    # time a spawn is scored the lift that shares its instant is already in.
    lift_instants: set[float] = set()

    for source in canonical:
        kind = str(source["kind"])
        t = float(source["t"])

        if kind == "collision":
            ball_id = int(source["ball_id"])
            shell_id = int(source["shell_id"])
            panel_id = int(source["panel_id"])
            voice = voices[ball_id]
            radius = float(shells[shell_id]["radius"])
            position = source["position"]
            degree = degree_for(position[1], radius, degrees)
            index = _ladder_index(system, shell_id, degree, voice)

            impact = _clamp(float(source["impact_speed"]) / 20.0)
            incidence = _clamp(float(source["incidence"]) / 1.15)
            shell_norm = shell_id / max(1, len(system.shell_bases) - 1)

            contact = (t, ball_id)
            damage_event = damage_at.get(contact)
            damage_before = 0.0
            damage_state = "healthy"
            if damage_event is not None:
                threshold = float(damage_event["threshold"])
                before = float(damage_event["cumulative"]) - float(damage_event["contribution"])
                damage_before = _clamp(before / max(threshold, 1e-9))
            state_event = state_at.get(contact)
            state_step = 0
            if state_event is not None:
                damage_state = str(state_event["new_state"])
                state_step = _state_index(damage_state)
            elif damage_event is not None:
                damage_state = str(damage_event["state"])
            near_event = near_at.get(contact)
            direction = 0
            if near_event is not None:
                lead = float(near_event["signed_lead"])
                direction = 1 if lead > 0.0 else -1 if lead < 0.0 else 0

            local = density.get(t, 1)
            length_scale = max(config.density_floor,
                               1.0 / (1.0 + config.density_tighten * (local - 1)))
            density_gain = max(config.density_gain_floor,
                               1.0 / (1.0 + 0.5 * config.density_tighten * (local - 1)))
            seconds = (config.collision_seconds * length_scale
                       * (0.74 + 0.36 * impact)
                       * (1.0 + config.shell_ring * shell_norm)
                       * (1.0 + config.damage_ring * damage_before)
                       # A glancing contact rings; a head-on one is struck.
                       * (1.28 - 0.30 * incidence))

            gain = config.collision_gain_low + (
                config.collision_gain_high - config.collision_gain_low
            ) * (0.62 * math.sqrt(impact) + 0.38 * incidence)
            gain *= density_gain

            tier = COLLISION_TIER_NORMAL
            strong = impact >= config.strong_impact or shell_id >= frontier
            if strong:
                tier = COLLISION_TIER_STRONG
                gain *= config.strong_gain
            if near_event is not None or state_event is not None:
                tier = COLLISION_TIER_MARKED

            repeat_nudged = False
            previous = last_pitch_at.get(index)
            if previous is not None and t - previous < config.repeat_seconds:
                index = min(LADDER_TOP, index + 1)
                gain *= config.repeat_gain
                repeat_nudged = True
            last_pitch_at[index] = t

            events.append(AudioEvent(
                kind="collision",
                tier=tier,
                source_seconds=t,
                sample_offset=_sample_at(t, config.sample_rate),
                seconds=seconds,
                gain=gain,
                pan=_pan(position[0], radius, voice, config),
                frequency_hz=system.frequency(index),
                ladder_index=index,
                ball_id=ball_id,
                shell_id=shell_id,
                generation=voice.generation,
                panel_id=panel_id,
                degree=degree,
                impact=impact,
                incidence=incidence,
                feature=str(source["feature"]),
                damage_before=damage_before,
                damage_state=damage_state,
                state_step=state_step,
                strong=strong,
                near_miss=near_event is not None,
                near_miss_direction=direction,
                repeat_nudged=repeat_nudged,
                density=local,
                region=int(source["region"]),
                progress=shell_norm,
                tint=voice.tint,
                edge=voice.edge,
                detune=voice.detune,
            ))

            break_event = break_at.get(contact)
            if break_event is not None:
                chord = tuple(min(LADDER_TOP, index + step) for step in (0, 2, 3, 5))
                events.append(AudioEvent(
                    kind="break",
                    tier=EVENT_TIER["break"],
                    source_seconds=t,
                    sample_offset=_sample_at(t, config.sample_rate),
                    seconds=config.break_seconds,
                    gain=config.break_gain * (0.92 + 0.10 * shell_norm),
                    pan=_pan(position[0], radius, voice, config, scale=0.55),
                    frequency_hz=system.frequency(index),
                    ladder_index=index,
                    ball_id=ball_id,
                    shell_id=shell_id,
                    generation=voice.generation,
                    panel_id=panel_id,
                    degree=degree,
                    impact=impact,
                    incidence=incidence,
                    feature=str(source["feature"]),
                    damage_before=1.0,
                    damage_state="broken",
                    state_step=len(DAMAGE_STATES) - 1,
                    density=local,
                    region=int(source["region"]),
                    progress=shell_norm,
                    tint=voice.tint,
                    edge=voice.edge,
                    detune=voice.detune,
                    chord=chord,
                ))

        elif kind == "ball_spawn":
            child_id = int(source["ball_id"])
            parent_id = int(source["parent_id"])
            shell_id = int(source["birth_shell"])
            child = voices[child_id]
            parent = voices[parent_id]
            radius = float(shells[shell_id]["radius"])
            position = source["position"]
            degree = degree_for(position[1], radius, degrees)
            parent_index = _ladder_index(system, shell_id, degree, parent)
            # Mirrored consonant interval: the child answers a fifth above a low
            # parent and a fifth below a high one, so a split is always heard as
            # two notes opening outward rather than as a scale run.
            step = 3 if degree <= system.window // 2 else -3
            child_index = max(0, min(LADDER_TOP, parent_index + step + child.register))
            pan = _pan(position[0], radius, parent, config, scale=0.60)
            with_lift = t in lift_instants
            events.append(AudioEvent(
                kind="spawn",
                tier=EVENT_TIER["spawn"],
                source_seconds=t,
                sample_offset=_sample_at(t, config.sample_rate),
                seconds=config.spawn_seconds,
                gain=config.spawn_gain * (config.spawn_with_lift_gain if with_lift else 1.0),
                pan=pan,
                with_lift=with_lift,
                frequency_hz=system.frequency(parent_index),
                ladder_index=parent_index,
                ball_id=child_id,
                shell_id=shell_id,
                generation=int(source["generation"]),
                degree=degree,
                region=int(source["region"]),
                progress=shell_id / max(1, len(system.shell_bases) - 1),
                tint=parent.tint,
                edge=parent.edge,
                detune=parent.detune,
                secondary_hz=system.frequency(child_index),
                secondary_index=child_index,
                secondary_pan=_spawn_child_pan(pan, child, config),
                secondary_tint=child.tint,
            ))

        elif kind == "shell_exit":
            to_region = int(source["to_region"])
            shell_id = int(source["shell_id"])
            ball_id = int(source["ball_id"])
            voice = voices[ball_id]
            radius = float(shells[shell_id]["radius"])
            position = source["position"]
            degree = degree_for(position[1], radius, degrees)
            index = _ladder_index(system, shell_id, degree, voice)
            if to_region > frontier:
                frontier = to_region
                lift_instants.add(t)
                # The lift is the run arriving somewhere, not a ball moving, so
                # it is voiced on the collection's tonic rather than on whatever
                # degree the crossing happened to land on.
                base = system.shell_bases[min(shell_id, len(system.shell_bases) - 1)]
                chord = tuple(min(LADDER_TOP, base + step) for step in (0, 2, 3, 5))
                events.append(AudioEvent(
                    kind="lift",
                    tier=EVENT_TIER["lift"],
                    source_seconds=t,
                    sample_offset=_sample_at(t, config.sample_rate),
                    seconds=config.lift_seconds,
                    gain=config.lift_gain * (0.88 + 0.12 * to_region / max(1, len(shells))),
                    pan=_pan(position[0], radius, voice, config, scale=0.35),
                    frequency_hz=system.frequency(base),
                    ladder_index=base,
                    ball_id=ball_id,
                    shell_id=shell_id,
                    generation=voice.generation,
                    panel_id=int(source["panel_id"]),
                    degree=degree,
                    route=str(source["route"]),
                    region=to_region,
                    progress=to_region / max(1, len(shells)),
                    tint=voice.tint,
                    edge=voice.edge,
                    detune=voice.detune,
                    chord=chord,
                ))
            elif not bool(source["first_for_ball"]):
                events.append(AudioEvent(
                    kind="crossing",
                    tier=EVENT_TIER["crossing"],
                    source_seconds=t,
                    sample_offset=_sample_at(t, config.sample_rate),
                    seconds=config.crossing_seconds,
                    gain=config.crossing_gain,
                    pan=_pan(position[0], radius, voice, config, scale=0.80),
                    frequency_hz=system.frequency(index),
                    ladder_index=index,
                    ball_id=ball_id,
                    shell_id=shell_id,
                    generation=voice.generation,
                    panel_id=int(source["panel_id"]),
                    degree=degree,
                    route=str(source["route"]),
                    region=to_region,
                    progress=to_region / max(1, len(shells)),
                    tint=voice.tint,
                    edge=voice.edge,
                    detune=voice.detune,
                ))

        elif kind == "escape":
            ball_id = int(source["ball_id"])
            voice = voices[ball_id]
            shell_id = int(source["shell_id"])
            radius = float(shells[shell_id]["radius"])
            escape_seconds = t
            # The tonic chord of the collection, two octaves wide, with the
            # root doubled an octave down for weight.
            chord = (-len(system.scale), 0, 2, 3, 5, 5 + 2)
            events.append(AudioEvent(
                kind="escape",
                tier=EVENT_TIER["escape"],
                source_seconds=t,
                sample_offset=_sample_at(t, config.sample_rate),
                seconds=config.escape_seconds,
                gain=config.escape_gain,
                pan=_pan(source["position"][0], radius, voice, config, scale=0.20),
                frequency_hz=system.frequency(0),
                ladder_index=0,
                ball_id=ball_id,
                shell_id=shell_id,
                generation=int(source["generation"]),
                route=str(source["route"]),
                region=int(shell_id) + 1,
                progress=1.0,
                tint=voice.tint,
                edge=voice.edge,
                detune=voice.detune,
                chord=chord,
            ))

    if not any(event.kind == "escape" for event in events):
        raise ScoreError("audio proofs are built from runs that end in an escape")

    order = {kind: index for index, kind in enumerate(EVENT_KINDS)}
    events.sort(key=lambda event: (event.sample_offset, order[event.kind], event.ball_id))
    events = _manage_clusters(events, config)

    last_end = max(max(event.end_seconds for event in events),
                   float(document["summary"]["duration"]))
    total_samples = _sample_at(last_end + config.tail_seconds, config.sample_rate)
    total_seconds = total_samples / config.sample_rate
    metrics = schedule_metrics(events, total_seconds, escape_seconds, config, balls)
    return AudioSchedule(
        seed=int(document["seed"]),
        playback_digest=str(document["digest"]),
        config=config,
        voices=voices,
        events=tuple(events),
        total_seconds=total_seconds,
        total_samples=total_samples,
        escape_seconds=escape_seconds,
        metrics=metrics,
    )


def _manage_clusters(events: list[AudioEvent], config: AudioConfig) -> list[AudioEvent]:
    """Register management inside a cluster, rather than moving anything in time.

    Two balls hitting inside 30 ms are one chord to a listener. The collection
    already guarantees the chord holds no semitone and no tritone, so the only
    two faults left are a unison - which sounds like one louder hit, and loses
    a visible bounce - and two notes a scale step apart in the bottom octave,
    which is where a whole tone turns to mud. Both are answered by moving a
    note up the ladder, never by moving it in time.
    """
    system = config.tonal
    window = config.cluster_seconds
    out = list(events)
    start = 0
    for index, event in enumerate(out):
        if event.kind not in ("collision", "crossing"):
            continue
        while out[start].source_seconds < event.source_seconds - window:
            start += 1
        nudged = event.ladder_index
        for other in out[start:index]:
            if other.ladder_index != nudged:
                continue
            if nudged == other.ladder_index and nudged + 1 <= LADDER_TOP:
                nudged += 1
        if nudged < len(system.scale):
            for other in out[start:index]:
                if abs(other.ladder_index - nudged) == 1 and other.ladder_index < len(system.scale):
                    nudged = min(LADDER_TOP, nudged + len(system.scale))
                    break
        if nudged != event.ladder_index:
            out[index] = replace(
                event,
                ladder_index=nudged,
                frequency_hz=system.frequency(nudged),
                cluster_nudged=True,
            )
    return out


# --------------------------------------------------------------------------
# Metrics over the schedule
# --------------------------------------------------------------------------


def _polyphony_profile(events: Sequence[AudioEvent]) -> tuple[int, float, float, list[tuple[float, int]]]:
    """Maximum, time-weighted median and mean simultaneous voices, and the curve."""
    edges: list[tuple[float, int]] = []
    for event in events:
        edges.append((event.source_seconds, 1))
        edges.append((event.end_seconds, -1))
    edges.sort(key=lambda edge: (edge[0], edge[1]))
    curve: list[tuple[float, int]] = []
    live = 0
    peak = 0
    index = 0
    previous = edges[0][0] if edges else 0.0
    held: dict[int, float] = {}
    while index < len(edges):
        moment = edges[index][0]
        if moment > previous:
            held[live] = held.get(live, 0.0) + (moment - previous)
        while index < len(edges) and edges[index][0] == moment:
            live += edges[index][1]
            index += 1
        curve.append((round(moment, 6), live))
        peak = max(peak, live)
        previous = moment
    sounding = {count: seconds for count, seconds in held.items() if count > 0}
    total = sum(sounding.values())
    median = 0.0
    if total > 0.0:
        running = 0.0
        for count in sorted(sounding):
            running += sounding[count]
            if running >= total / 2.0:
                median = float(count)
                break
    mean = (sum(count * seconds for count, seconds in sounding.items()) / total) if total else 0.0
    return peak, median, mean, curve


def _repeat_runs(events: Sequence[AudioEvent]) -> dict[str, Any]:
    """How often the same ladder position sounds twice or more in a row, per ball."""
    longest = 0
    runs = 0
    by_ball: dict[int, tuple[int, int]] = {}
    for event in events:
        if event.kind != "collision":
            continue
        previous, length = by_ball.get(event.ball_id, (-999, 0))
        length = length + 1 if previous == event.ladder_index else 1
        by_ball[event.ball_id] = (event.ladder_index, length)
        longest = max(longest, length)
        if length == 3:
            runs += 1
    return {"longest_same_pitch_run": longest, "runs_of_three_or_more": runs}


def _harsh_incidence(events: Sequence[AudioEvent], config: AudioConfig) -> dict[str, Any]:
    """Simultaneous pairs a semitone, tritone or major seventh apart.

    The collection makes the answer zero, which is the reason for measuring it:
    a future palette that quietly breaks the guarantee shows up here and not in
    a listening session three phases later.
    """
    system = config.tonal
    window = config.cluster_seconds
    pitched = [e for e in events if e.kind in ("collision", "crossing", "break", "lift")]
    harsh = 0
    pairs = 0
    start = 0
    for index, event in enumerate(pitched):
        while pitched[start].source_seconds < event.source_seconds - window:
            start += 1
        for other in pitched[start:index]:
            pairs += 1
            gap = abs(system.ladder_semitones(event.ladder_index)
                      - system.ladder_semitones(other.ladder_index)) % 12
            if gap in (1, 6, 11):
                harsh += 1
    return {
        "simultaneous_pairs": pairs,
        "harsh_pairs": harsh,
        "harsh_fraction": round(harsh / pairs, 6) if pairs else 0.0,
    }


def _thirds(events: Sequence[AudioEvent], total_seconds: float,
            config: AudioConfig) -> dict[str, Any]:
    """Early, middle and late, on the clock rather than on the event count."""
    system = config.tonal
    bounds = (total_seconds / 3.0, 2.0 * total_seconds / 3.0)
    buckets: list[list[AudioEvent]] = [[], [], []]
    for event in events:
        slot = 0 if event.source_seconds < bounds[0] else (1 if event.source_seconds < bounds[1] else 2)
        buckets[slot].append(event)
    span = total_seconds / 3.0
    out: list[dict[str, Any]] = []
    for slot, bucket in enumerate(buckets):
        peak, median, mean, _ = _polyphony_profile(bucket) if bucket else (0, 0.0, 0.0, [])
        semitones = [system.ladder_semitones(e.ladder_index) for e in bucket
                     if e.kind in ("collision", "crossing", "break", "lift")]
        out.append({
            "third": ("early", "middle", "late")[slot],
            "events": len(bucket),
            "events_per_second": round(len(bucket) / span, 4) if span else 0.0,
            "collisions": sum(1 for e in bucket if e.kind == "collision"),
            "distinct_balls": len({e.ball_id for e in bucket}),
            "max_polyphony": peak,
            "mean_polyphony": round(mean, 4),
            "distinct_pitches": len(set(semitones)),
            "distinct_pitch_classes": len({s % 12 for s in semitones}),
            "mean_ladder_index": round(
                sum(e.ladder_index for e in bucket) / len(bucket), 4) if bucket else 0.0,
            "marked_events": sum(1 for e in bucket if e.tier >= 4),
        })
    return {"bounds_seconds": [round(bounds[0], 6), round(bounds[1], 6)], "thirds": out}


def schedule_metrics(events: Sequence[AudioEvent], total_seconds: float,
                     escape_seconds: float, config: AudioConfig,
                     balls: Mapping[int, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    counts = {kind: sum(event.kind == kind for event in events) for kind in EVENT_KINDS}
    collisions = [event for event in events if event.kind == "collision"]
    collision_times = [event.source_seconds for event in collisions]
    peak, median, mean, curve = _polyphony_profile(events)
    gaps = [b - a for a, b in zip(collision_times, collision_times[1:])]
    durations = sorted(event.seconds for event in collisions)
    span = max(collision_times[-1], 1e-9) if collision_times else 1e-9
    return {
        "events": len(events),
        "by_kind": counts,
        "by_tier": {str(tier): sum(event.tier == tier for event in events)
                    for tier in sorted({event.tier for event in events})},
        "collision_density_hz": round(len(collisions) / span, 4),
        "event_density_hz": round(len(events) / span, 4),
        "near_miss_collisions": sum(1 for event in events if event.near_miss),
        "state_transition_collisions": sum(1 for event in events
                                           if event.kind == "collision" and event.state_step),
        "strong_collisions": sum(1 for event in events if event.strong),
        "spawns_carrying_a_lift": sum(1 for event in events if event.with_lift),
        "repeat_nudged": sum(1 for event in events if event.repeat_nudged),
        "cluster_nudged": sum(1 for event in events if event.cluster_nudged),
        "max_scheduled_polyphony": peak,
        "median_scheduled_polyphony": median,
        "mean_scheduled_polyphony": round(mean, 4),
        "polyphony_curve": [[at, live] for at, live in curve],
        "voice_seconds_total": round(sum(event.seconds for event in events), 6),
        "collision_voice_seconds_median": round(durations[len(durations) // 2], 6) if durations else 0.0,
        "collision_voice_seconds_min": round(durations[0], 6) if durations else 0.0,
        "collision_voice_seconds_max": round(durations[-1], 6) if durations else 0.0,
        "median_collision_gap_seconds": round(sorted(gaps)[len(gaps) // 2], 6) if gaps else 0.0,
        "minimum_collision_gap_seconds": round(min(gaps), 6) if gaps else 0.0,
        "simultaneous_within_cluster": sum(1 for a, b in zip(collision_times, collision_times[1:])
                                           if b - a < config.cluster_seconds),
        "distinct_balls": len({event.ball_id for event in events}),
        "generations": (max(event.generation for event in events) if events else 0),
        "escape_seconds": round(escape_seconds, 6),
        "total_seconds": round(total_seconds, 6),
        **_repeat_runs(events),
        "consonance": _harsh_incidence(events, config),
        "progression": _thirds(events, total_seconds, config),
        "lineage_voices": len(balls) if balls else 0,
    }


def score_document(document: Mapping[str, Any],
                   config: AudioConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    return schedule(document, config).as_dict()
