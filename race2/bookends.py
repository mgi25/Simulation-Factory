"""The bookends: a start stand and a finish stand, as visual structure only.

## Why this is a separate module and why it emits a spec

Race #2's course is *the collider the physics ran on* - `race2.export` writes
out the very rings `TrackRun` was swept from, and `race2_scene.gd` sweeps those
rings into the picture. That identity is the reason the film can be trusted,
and it is also the reason a bookend cannot be built the same way: anything
added to a module's `local_colliders` is added to the simulation, and the
simulation is locked.

So a bookend is **not a `MarbleModule`**. It is a parametric description -
boxes, cylinders and one hinge - written to JSON and instantiated by
`assets/marble_machine/course/race2_bookends.gd` under its own node. Nothing
here is ever handed to `marble3d`, there is no code path from this file into
`race2.race`, and `tests/test_race2_v33_bookends.py` asserts both.

The cost of that choice is honest and worth naming: a bookend is scenery. A
marble will roll through the finish gantry's pylon if the physics sends it
there. Every structure below is therefore sited *off* the racing line by
construction - `clearance()` reports the margin each one keeps - and the sites
are measured against the replay rather than asserted.

## Units

Everything in this module is in **layout units**, which are Godot world units:
`race2_scene.gd` scales the course node by `render_scale` (0.57) to convert the
simulation units the geometry is written in, and a bookend is parented at the
scene root instead, exactly as the contained stage is. A layout unit is a
racer diameter times 1.754 - `layout.MARBLE_RADIUS` is 0.285.

## The frame

A bookend is authored in its own `(along, up, across)` triple, where `along` is
the direction the field is travelling, `up` is world +Y and
`across = along x up`. That is `race2.kit.Frame`'s convention and it is stated
here because the two yaw conventions in this package do not agree: `Frame.yaw`
is `atan2(-forward.z, forward.x)` and `TrackRun.heading_deg` is
`atan2(forward.x, forward.z)`. `site_from_run` takes the *tangent*, never a
heading, so there is nothing here to get the wrong way round. `race2.kit`'s
convention note is where that rule is written down; see
`docs/race2_v331_runout_fix.md` for what happened to the one module that did
get it the wrong way round.

## Reusability

Nothing below knows what SWITCHYARD is, how many racers seed 8 has or where
the finish is. `start_site` and `finish_site` read a `Course`; `start_stand`
and `finish_stand` take a site, a racer count and a palette. A second race
course gets its bookends from the same two calls.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

__all__ = [
    "Site",
    "Field",
    "Palette",
    "StartStand",
    "FinishStand",
    "MACHINE_PALETTE",
    "site_from_run",
    "start_site",
    "finish_site",
    "start_stand",
    "finish_stand",
    "build",
    "clearance",
]

Vec3 = tuple[float, float, float]

# The one place a layout unit is named. Imported rather than redefined would
# couple this module to `sloped.layout`, which is Race #1's; the number is the
# same and the test asserts it is.
MARBLE_RADIUS = 0.285


# --- vector helpers ---------------------------------------------------------


def _add(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Sequence[float], k: float) -> Vec3:
    return (a[0] * k, a[1] * k, a[2] * k)


def _sub(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a: Sequence[float]) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: Sequence[float]) -> Vec3:
    length = _norm(a)
    if length < 1.0e-9:
        raise ValueError("cannot normalise a zero vector")
    return (a[0] / length, a[1] / length, a[2] / length)


def _round(v: Sequence[float], places: int = 5) -> list[float]:
    return [round(float(x), places) for x in v]


# --- the palette ------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    """Which renderer material key each part of a bookend is painted with.

    A dataclass rather than a dict so a caller that wants a different machine
    language names the surfaces it is changing and inherits the rest. Every
    value must be a key the renderer's palette answers; the builder fails
    loudly on one that is not, because a silently-defaulted material is the
    sort of thing that only shows up in a delivered frame.

    The keys are *strings that travel through JSON*, and that is the whole
    isolation story: nothing in this package imports, reads or knows about the
    palette itself, which `tests/test_race2_isolation.py` asserts over the
    source of every module in `race2/`.
    """

    base: str = "graphite"          # the plinth and the foundations
    frame: str = "graphite_soft"    # posts, gantry legs, back board body
    edge: str = "track_silver"      # the pearl edges and chamfers
    deck: str = "silver_deep"       # bay floors, run-out surface
    board: str = "dish_floor"       # the backdrop the racers are read against
    rail: str = "chrome"            # the gate bar and the hand rails
    accent: str = "gold"            # the restrained warm accent
    line: str = "gold_bright"       # the finish line inlay
    lit: str = "lit_white"          # the one lit edge on each stand

    def keys(self) -> tuple[str, ...]:
        return (self.base, self.frame, self.edge, self.deck, self.board,
                self.rail, self.accent, self.line, self.lit)


MACHINE_PALETTE = Palette()


# --- the site ---------------------------------------------------------------


@dataclass(frozen=True)
class Site:
    """Where a bookend stands, and which way the race runs through it.

    `origin` is a point on the racing surface: for a start, the deck top at the
    bay row's centre; for a finish, the channel centreline where the timing
    happens. `along` is the travel direction, `up` is world up, and `across` is
    derived so the triple is right-handed in `Frame`'s sense.
    """

    origin: Vec3
    along: Vec3
    up: Vec3 = (0.0, 1.0, 0.0)
    half_width: float = 2.0

    @property
    def across(self) -> Vec3:
        return _cross(self.along, self.up)

    def at(self, along: float, up: float, across: float) -> Vec3:
        """A point in the site's own coordinates, as a world layout point."""
        point = self.origin
        point = _add(point, _scale(self.along, along))
        point = _add(point, _scale(self.up, up))
        point = _add(point, _scale(self.across, across))
        return point

    def axes(self) -> tuple[Vec3, Vec3, Vec3]:
        return (self.along, self.up, self.across)

    def local(self, world: Sequence[float]) -> Vec3:
        """A world point, in this site's (along, up, across) coordinates."""
        delta = _sub(world, self.origin)
        return (_dot(delta, self.along), _dot(delta, self.up),
                _dot(delta, self.across))

    def describe(self) -> dict[str, Any]:
        return {
            "origin": _round(self.origin),
            "along": _round(self.along),
            "up": _round(self.up),
            "across": _round(self.across),
            "half_width": round(self.half_width, 4),
        }


def site_from_run(path: Sequence[Sequence[float]], index: int,
                  half_width: float, up: Vec3 = (0.0, 1.0, 0.0)) -> Site:
    """A site on a run's own path, oriented by the local tangent.

    **The tangent, never a heading.** `TrackRun.heading_deg` answers
    `atan2(x, z)` and `race2.kit.Frame.yaw` answers `atan2(-z, x)`; a site
    built by converting one through the other's inverse is rotated by 90
    degrees, which is a defect `race2.parts.RunOut` shipped from the commit
    that wrote it to V33, and which `docs/race2_v331_runout_fix.md` repairs.
    Differencing two path samples cannot express that mistake, and
    `race2.kit`'s convention note is where the rule is written down.
    """
    points = [tuple(float(c) for c in p) for p in path]
    if len(points) < 2:
        raise ValueError("a site needs a path of at least two samples")
    index = max(0, min(int(index), len(points) - 1))
    low = max(0, index - 1)
    high = min(len(points) - 1, index + 1)
    if low == high:
        low, high = 0, 1
    tangent = _sub(points[high], points[low])
    flat = (tangent[0], 0.0, tangent[2])
    if _norm(flat) < 1.0e-9:
        raise ValueError("a site needs a tangent with a horizontal component")
    return Site(origin=points[index], along=_unit(flat), up=up,
                half_width=float(half_width))


def start_site(course: Any) -> Site:
    """The start module's own shelf, as a site.

    Read off the module rather than off the course table: a course that moves
    its start moves this with it, and a course with a different start kind
    supplies the same three attributes or is not a start.
    """
    module = course.machine.modules["start"]
    frame = module.frame
    return Site(
        origin=tuple(float(c) for c in frame.origin),
        along=tuple(float(c) for c in frame.forward),
        up=tuple(float(c) for c in frame.up),
        half_width=float(module.half_spread + 0.5 * module.BAY_PITCH),
    )


def finish_site(course: Any, run_name: str = "sprint",
                half_width: float | None = None) -> Site:
    """The last run's exit, as a site, with the channel's own half width.

    **`Socket.width` is not used and the reason is a unit.** `finish_line.width`
    is 6.596 and the exit's running surface is 2.95 wide; the first is in
    simulation units and includes the guard flare, the second is the layout
    half-width the marble actually rolls between, doubled. A gantry sized on
    the first would straddle a channel 2.3 times as wide as the one under it.
    `half_width` is therefore computed by the caller from the run's own width
    curve, and defaults here to the run's last sample only if the run exposes
    one.
    """
    run = course.runs[run_name]
    if half_width is None:
        half_width = _run_half_width(run)
    return site_from_run(run.path, len(run.path) - 1, float(half_width))


def _run_floor_up(run: Any) -> float:
    """How far the running surface sits below a run's centreline, in layout.

    `layout.FLOOR_Y` is the cradle's depth at a unit profile scale, so the run
    multiplies it by its own. The number matters because the finish line is a
    stripe *in* that surface: put it at the centreline instead and it is a
    0.52-unit step across the channel, which is what the first build shipped
    and `clearance` caught.
    """
    from sloped import layout as _layout

    return float(_layout.FLOOR_Y) * float(run.scale)


def _run_half_width(run: Any) -> float:
    """The running surface's half width at a run's exit, in layout units.

    `TrackRun` stores a per-sample width *factor*; the layout half width is
    `CHANNEL_HALF * scale * factor`, which is the expression
    `TrackRun.running_point` uses before it converts to simulation units. The
    constant is read off `sloped.layout` at call time rather than imported at
    module scope, so this file still imports nothing when a caller supplies
    the number itself.
    """
    from sloped import layout as _layout

    return float(_layout.CHANNEL_HALF) * float(run.scale) * float(run.widths[-1])


# --- parts ------------------------------------------------------------------


def _box(site: Site, name: str, material: str,
         along: tuple[float, float], up: tuple[float, float],
         across: tuple[float, float]) -> dict[str, Any]:
    """A box named by its own extents in the site's frame, not by a centre.

    Authoring a stand as spans rather than centres is the difference between
    "the back board's face is 1.75 behind the bay row" and "the back board is
    at -1.83 and is 0.16 thick", and only the first of those survives a change
    to the thickness.
    """
    centre = site.at(0.5 * (along[0] + along[1]), 0.5 * (up[0] + up[1]),
                     0.5 * (across[0] + across[1]))
    half = (0.5 * abs(along[1] - along[0]), 0.5 * abs(up[1] - up[0]),
            0.5 * abs(across[1] - across[0]))
    axis_along, axis_up, axis_across = site.axes()
    return {
        "kind": "box",
        "name": name,
        "material": material,
        "centre": _round(centre),
        "along": _round(axis_along),
        "up": _round(axis_up),
        "across": _round(axis_across),
        "half": [round(h, 5) for h in half],
        "span": {"along": [round(along[0], 5), round(along[1], 5)],
                 "up": [round(up[0], 5), round(up[1], 5)],
                 "across": [round(across[0], 5), round(across[1], 5)]},
    }


def _no_shadow(part: dict[str, Any]) -> dict[str, Any]:
    """Mark a part as receiving light but never casting it.

    **The back board and the portal need this and the reason is measured.**
    `contained_bay_v301`'s key is at rotation (-46, -58, 0), which travels
    (0.589, -0.719, -0.368): it arrives from *upstream*, 46 degrees up, and the
    board stands directly in its path. A board 1.74 tall throws its shadow
    1.14 downstream of its own face, which lands at `along` -0.48 - and the
    racers sit at -0.65, inside it. The first render of the stand has eight
    racers in shade in a shot whose whole job is their colour.

    Lowering the board to 0.89 would clear the shadow and would also stop it
    being a backdrop. A backdrop panel that does not cast is the ordinary
    answer, it changes no light and no other surface, and the racers get the
    key they had before the stand existed.
    """
    part["shadow"] = False
    return part


def _tube(site: Site, name: str, material: str, radius: float,
          start: tuple[float, float, float],
          end: tuple[float, float, float]) -> dict[str, Any]:
    return {
        "kind": "cylinder",
        "name": name,
        "material": material,
        "from": _round(site.at(*start)),
        "to": _round(site.at(*end)),
        "radius": round(float(radius), 5),
    }


# --- the start stand --------------------------------------------------------


@dataclass
class StartStand:
    """A grid of bays on a stand, behind a rail that lifts on the release.

    Every dimension is a field, so a course with ten racers or a wider pitch
    gets a stand rather than a redesign. The defaults are measured against
    Race #2's own start - `DropStart.BAY_PITCH` 0.82, eight bays, a 1.30-unit
    panel - and `start_stand` reads them off the module rather than repeating
    them.

    ## What the shapes are for

    The three failures the V32 opening is diagnosed with are: the racers read
    as already inside a machine, they are small, and the frame behind them is
    a dark void. The stand answers them in that order - the side towers and
    the back board make it a *stand*, the bay inlays and the raised fins
    separate the racers from each other, and the board is a mid-value surface
    so that a saturated ball has something to be saturated against.

    ## Why there is no plinth under the bays

    The obvious way to give a start stand mass is a block beneath it, and the
    first build of this file had one. `clearance` measured it at **0.000** from
    a racer: Race #2's start is a *trapdoor*, the field falls 1.4 units through
    the floor it is standing on and then rolls forward under the stand, so the
    volume directly below and directly in front of the bays is the racing line.
    The mass is therefore in two side towers outboard of the panel and one
    skirt behind it, and the middle and the front are deliberately open - which
    is also the brief's "obvious downward / forward route into the race", so
    the constraint and the composition want the same thing.
    """

    bays: int = 8
    bay_pitch: float = 0.82
    marble_radius: float = MARBLE_RADIUS

    # How far out the released field spreads and falls. Everything solid keeps
    # clear of this box; it is checked against the replay by `clearance`.
    panel_half_across: float = 3.32
    panel_back: float = -1.42
    panel_front: float = 0.10

    # The two towers, outboard of the panel.
    tower_back: float = -2.16
    tower_front: float = 0.92
    tower_top: float = 0.02
    tower_bottom: float = -2.45
    tower_width: float = 0.86
    tower_gap: float = 0.10          # clear of the panel's own edge

    # The skirt behind the bays, and the back board over it.
    skirt_back: float = -2.16
    skirt_front: float = -1.56
    skirt_bottom: float = -2.45

    chamfer: float = 0.13            # the pearl band along the towers' tops

    # The bay backing: one light panel behind each racer, in front of the
    # start's own back wall and clear of the fall line.
    back_panel_thick: float = 0.07
    back_panel_rise: float = 0.62

    # The dividers. Visual only, so they can be taller than the colliding fins.
    fin_rise: float = 0.40
    fin_thick: float = 0.12
    fin_back: float = -1.36
    fin_front: float = 0.08

    # The back board: the thing that stops the frame behind the racers being a
    # void. Its face is the plane the racers are photographed against.
    board_face: float = -1.62
    board_thick: float = 0.22
    board_rise: float = 1.74
    board_margin: float = 0.95
    board_cap: float = 0.13
    board_lit: float = 0.05

    # The portal the gate runs in. **Its header is above every sight line the
    # hook compositions use, and that is a solved number rather than a taste.**
    # At 2.52 it sat in the top of the elevated composition's cone and blocked
    # seven of the eight racers; `race2.bookends.blocked` found it, and
    # `tools/race2_v33_bookends.py hooks` re-runs the test on whatever
    # compositions are current.
    post_across_margin: float = 0.34
    post_thick: float = 0.28
    post_rise: float = 2.66
    header_depth: float = 0.32
    header_thick: float = 0.26

    # The gate. **It drops, and it is low.**
    #
    # Three forms were measured against the three hook compositions. A rail
    # *above* the bay mouths at 0.78-1.02 is inside the front composition's
    # sight cone - the ray from a 22-degree lens to a racer centre passes the
    # gate plane at 0.94 - and blocked all eight. A *lifting* rail sweeps up
    # through that same cone during the release, which is the half second a
    # viewer is choosing a colour in. A rail at the front of the deck, topped
    # below the lowest sight line and retracting into the plinth, is visible
    # as a barrier, cannot cross a racer at any elevation, and is the brief's
    # own "retracting front rail".
    gate_along: float = 0.44
    gate_low: float = -0.36
    gate_high: float = 0.02
    gate_depth: float = 0.17
    gate_lift: float = -0.62         # down, into the deck
    gate_cap: float = 0.13
    gate_post_rise: float = 0.24

    def half_spread(self) -> float:
        return 0.5 * (self.bays - 1) * self.bay_pitch

    def bay_across(self, index: int) -> float:
        """Bay 0 is the leftmost in `across`, which is `DropStart`'s bay 7.

        Stated because the two numberings are opposite and a stand that
        inherited the wrong one would put its widest inlay under the wrong
        racer. Nothing in the geometry is asymmetric, so the difference is
        only ever visible in a report; the report says which it used.
        """
        return -self.half_spread() + index * self.bay_pitch

    def tower_inner(self) -> float:
        return self.panel_half_across + self.tower_gap

    def half_across(self) -> float:
        return self.tower_inner() + self.tower_width

    def parts(self, site: Site, palette: Palette) -> tuple[list, list, dict]:
        """`(static, gate, meta)` - the two part lists and the motion record."""
        static: list[dict[str, Any]] = []
        inner = self.tower_inner()
        outer = self.half_across()
        board_half = self.half_spread() + self.board_margin
        post_across = board_half + self.post_across_margin + 0.5 * self.post_thick

        # 1. The two towers and the skirt: the stand's mass, all of it clear of
        #    the volume the field falls and rolls through.
        for side, sign in (("left", -1.0), ("right", 1.0)):
            lo = sign * inner
            hi = sign * outer
            static.append(_box(site, f"tower_{side}", palette.base,
                               (self.tower_back, self.tower_front),
                               (self.tower_bottom, self.tower_top),
                               (min(lo, hi), max(lo, hi))))
            static.append(_box(site, f"tower_cap_{side}", palette.edge,
                               (self.tower_back - 0.05, self.tower_front + 0.05),
                               (self.tower_top - self.chamfer, self.tower_top),
                               (min(lo, hi) - 0.05, max(lo, hi) + 0.05)))
            static.append(_box(site, f"tower_lit_{side}", palette.lit,
                               (self.tower_front - 0.30, self.tower_front - 0.06),
                               (self.tower_top - self.chamfer - 0.30,
                                self.tower_top - self.chamfer - 0.25),
                               (min(lo, hi) + 0.10, max(lo, hi) - 0.10)))
        static.append(_box(site, "skirt", palette.base,
                           (self.skirt_back, self.skirt_front),
                           (self.skirt_bottom, self.tower_top),
                           (-outer, outer)))
        static.append(_box(site, "skirt_cap", palette.edge,
                           (self.skirt_back - 0.05, self.skirt_front + 0.05),
                           (self.tower_top - self.chamfer, self.tower_top),
                           (-outer - 0.05, outer + 0.05)))

        # 2. The bays: a light panel *behind* each racer, a raised fin between.
        #
        # **Behind and not below, and that is the trapdoor again.** A light
        # floor plate under each racer is the obvious way to separate a ball
        # from a dark deck, and `clearance` measured every one of the eight at
        # 0.002 from a racer centre: the field falls straight down through the
        # floor it is standing on, so a static plate at deck level is a plate
        # the racers pass through. A panel at the back of the bay is never in
        # the fall line, and it is *better* for the picture anyway - it is
        # behind the ball in the lens rather than under it, so it separates
        # the silhouette instead of the contact shadow.
        for index in range(self.bays):
            centre = self.bay_across(index)
            inset = 0.5 * self.bay_pitch - 0.5 * self.fin_thick - 0.03
            static.append(_no_shadow(_box(site, f"bay_back_{index}", palette.edge,
                               (self.panel_back + 0.12,
                                self.panel_back + 0.12 + self.back_panel_thick),
                               (0.0, self.back_panel_rise),
                               (centre - inset, centre + inset))))
        for gap in range(self.bays + 1):
            centre = self.bay_across(0) - 0.5 * self.bay_pitch + gap * self.bay_pitch
            static.append(_box(site, f"fin_{gap}", palette.edge,
                               (self.fin_back, self.fin_front),
                               (0.0, self.fin_rise),
                               (centre - 0.5 * self.fin_thick,
                                centre + 0.5 * self.fin_thick)))

        # 3. The back board, its cap and its one lit line.
        static.append(_no_shadow(_box(site, "board", palette.board,
                                      (self.board_face - self.board_thick,
                                       self.board_face),
                                      (self.tower_top, self.board_rise),
                                      (-board_half, board_half))))
        static.append(_no_shadow(_box(site, "board_cap", palette.edge,
                                      (self.board_face - self.board_thick - 0.05,
                                       self.board_face + 0.05),
                                      (self.board_rise,
                                       self.board_rise + self.board_cap),
                                      (-board_half - 0.05, board_half + 0.05))))
        static.append(_box(site, "board_line", palette.lit,
                           (self.board_face, self.board_face + 0.035),
                           (self.board_rise - 0.22,
                            self.board_rise - 0.22 + self.board_lit),
                           (-board_half + 0.24, board_half - 0.24)))

        # 4. The portal: two posts and a header. **At the back of the stand,
        #    framing the board, not over the bay mouths.**
        #
        # A portal at the gate plane is in front of the racers from every
        # downstream composition, and raising it out of one shot's cone walks
        # it into another's - at 2.52 it blocked seven racers in the elevated
        # hook, at 3.26 the right-hand post still blocked one. Behind the row
        # it is structure a camera looks *past*, it gives the stand the top
        # edge the room needs, and no elevation can put it in the way.
        portal_along = self.board_face - 0.5 * self.board_thick
        for side, sign in (("left", -1.0), ("right", 1.0)):
            static.append(_no_shadow(_box(
                site, f"post_{side}", palette.frame,
                (portal_along - 0.5 * self.post_thick,
                 portal_along + 0.5 * self.post_thick),
                (self.tower_top, self.post_rise),
                (sign * post_across - 0.5 * self.post_thick,
                 sign * post_across + 0.5 * self.post_thick))))
            static.append(_tube(site, f"post_cap_{side}", palette.accent, 0.09,
                                (portal_along, self.post_rise,
                                 sign * post_across),
                                (portal_along, self.post_rise + 0.17,
                                 sign * post_across)))
        static.append(_no_shadow(_box(
            site, "header", palette.frame,
            (portal_along - 0.5 * self.header_depth,
             portal_along + 0.5 * self.header_depth),
            (self.post_rise - self.header_thick, self.post_rise),
            (-post_across - 0.5 * self.post_thick,
             post_across + 0.5 * self.post_thick))))
        static.append(_box(site, "header_line", palette.accent,
                           (portal_along - 0.5 * self.header_depth - 0.03,
                            portal_along + 0.5 * self.header_depth + 0.03),
                           (self.post_rise - self.header_thick - 0.055,
                            self.post_rise - self.header_thick),
                           (-post_across, post_across)))

        # 5. The gate: one rail and two caps, in two guides. It slides, it
        #    does not swing - a hinge puts the far end of the bar through the
        #    tower - and it slides *down*, so it never enters a sight cone.
        gate_across = self.half_spread() + 0.55
        for side, sign in (("left", -1.0), ("right", 1.0)):
            static.append(_box(site, f"gate_guide_{side}", palette.frame,
                               (self.gate_along - 0.5 * self.gate_depth - 0.05,
                                self.gate_along + 0.5 * self.gate_depth + 0.05),
                               (self.tower_top, self.gate_post_rise),
                               (sign * gate_across - 0.09,
                                sign * gate_across + 0.09)))
        gate: list[dict[str, Any]] = []
        gate.append(_box(site, "gate_rail", palette.rail,
                         (self.gate_along - 0.5 * self.gate_depth,
                          self.gate_along + 0.5 * self.gate_depth),
                         (self.gate_low, self.gate_high),
                         (-gate_across, gate_across)))
        for side, sign in (("left", -1.0), ("right", 1.0)):
            gate.append(_box(site, f"gate_cap_{side}", palette.accent,
                             (self.gate_along - 0.5 * self.gate_depth - 0.03,
                              self.gate_along + 0.5 * self.gate_depth + 0.03),
                             (self.gate_low - 0.03, self.gate_high + 0.03),
                             (sign * gate_across - self.gate_cap,
                              sign * gate_across + self.gate_cap)))

        meta = {
            "bays": self.bays,
            "bay_pitch": round(self.bay_pitch, 5),
            "bay_across": [round(self.bay_across(i), 5) for i in range(self.bays)],
            "half_across": round(outer, 5),
            "tower_inner": round(inner, 5),
            "board_face": round(self.board_face, 5),
            "board_rise": round(self.board_rise, 5),
            "gate_travel": round(self.gate_lift, 5),
            "gate_top_below_marble_top": round(
                2.0 * self.marble_radius - self.gate_high, 5),
            "fin_clear_of_marble": round(
                0.5 * self.bay_pitch - 0.5 * self.fin_thick - self.marble_radius, 5),
            "portal_rise": round(self.post_rise, 5),
        }
        return static, gate, meta


def start_stand(site: Site, bays: int, bay_pitch: float,
                release_time: float, release_duration: float,
                palette: Palette = MACHINE_PALETTE,
                stand: StartStand | None = None) -> dict[str, Any]:
    """The start stand, with its gate timed to the physical release.

    `release_time` and `release_duration` come from the start module's own
    actuators. **Nothing here chooses them**: the brief's rule is that the
    visual gate moves with the authoritative release rather than the release
    moving for the gate, and passing them in is how that rule is expressed in
    the signature instead of in a comment.
    """
    stand = stand or StartStand(bays=bays, bay_pitch=bay_pitch)
    stand.bays = int(bays)
    stand.bay_pitch = float(bay_pitch)
    static, gate, meta = stand.parts(site, palette)
    return {
        "id": "start",
        "site": site.describe(),
        "static": static,
        "motion": {
            "kind": "slide",
            "axis": _round(site.up),
            "travel": round(stand.gate_lift, 5),
            "starts": round(float(release_time), 6),
            "duration": round(float(release_duration), 6),
            "ease": "smoothstep",
            "parts": gate,
        },
        "meta": meta,
    }


# --- the finish stand -------------------------------------------------------


@dataclass(frozen=True)
class Field:
    """Where the field actually ends up after the line, in the site's frame.

    Measured off the replay by `tools/race2_v33_bookends.py field`, never
    guessed, and the habit earned itself: when V33 measured this, Race #2's
    run-out was laid across the direction of travel, the field drained sideways
    and an apron sized on the course's *plan* would have been eight units from
    where the racers actually were. A structure sited on the record was right
    anyway. V33.1 repaired the deck - `docs/race2_v331_runout_fix.md` - and the
    same measurement now puts the field in front of the line, which is why the
    defaults below changed and why they are still only defaults.
    """

    along: tuple[float, float] = (0.0, 8.0)
    across: tuple[float, float] = (-5.25, 0.55)
    rest_up: float = -0.43
    surface_up: float = -0.52
    surface_fall: float = 0.0244      # d(up)/d(across) of the deck under it
    channel_fall: float = 0.2842      # d(up)/d(-along) of the sprint above it
    well_along: tuple[float, float] | None = None
    well_across: tuple[float, float] | None = None
    well_floor: float | None = None
    # Where the *camera* needs the plaza not to be. Measured, not chosen: see
    # `cutouts` and the document's section 10.2.
    sight_along: tuple[float, float] | None = None
    sight_across: tuple[float, float] | None = None

    def surface(self, across: float) -> float:
        return self.surface_up + self.surface_fall * across

    def channel(self, along: float) -> float:
        """The racing centreline's height at `along`, relative to the line.

        **The sprint descends and the colonnade has to descend with it.** The
        first build stood four portals on one datum and `clearance` put a beam
        at 0.000 from a racer: eight units up the channel the racing line is
        2.27 higher than it is at the finish, so a beam that clears the pack at
        the line is inside it further back.
        """
        return -self.channel_fall * along

    def describe(self) -> dict[str, Any]:
        return {
            "along": [round(v, 4) for v in self.along],
            "across": [round(v, 4) for v in self.across],
            "rest_up": round(self.rest_up, 4),
            "surface_up": round(self.surface_up, 4),
            "surface_fall": round(self.surface_fall, 5),
            "channel_fall": round(self.channel_fall, 5),
            "well_along": None if self.well_along is None
            else [round(v, 4) for v in self.well_along],
            "well_across": None if self.well_across is None
            else [round(v, 4) for v in self.well_across],
            "well_floor": None if self.well_floor is None
            else round(self.well_floor, 4),
            "sight_along": None if self.sight_along is None
            else [round(v, 4) for v in self.sight_along],
            "sight_across": None if self.sight_across is None
            else [round(v, 4) for v in self.sight_across],
        }

    def cutouts(self) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """The rectangles the plaza must leave open, as `(along, across)`.

        Two, and they are different kinds of constraint.

        The **pocket** is where the physics drops racers; a plate over it hides
        the thing it exists to catch.

        The **sight corridor** is where the final chase's own rays cross the
        plaza plane on their way to the pocket. Without it the plaza is a lid:
        measured on the delivered camera track, a solid plate puts
        `plaza_7_0` between the lens and **the winner for 175 frames** - 2.9
        seconds, over the whole of the payoff card - and V32's finish is built
        on m7 being on screen continuously from 15.23 s.

        Leaving it open costs about a hundred racer-frames in which a racer in
        *transit* crosses an opening rather than a plate. That band is where no
        racer comes to rest, and in the shipped film it is open anyway: Race
        #2's run-out deck is drawn backfacing and is not on screen at all, so
        the corridor is no worse than what Test #3 delivers there, while the
        winner being hidden would be strictly worse.
        """
        out: list[tuple[tuple[float, float], tuple[float, float]]] = []
        if (self.well_along is not None and self.well_across is not None):
            out.append((self.well_along, self.well_across))
        if (self.sight_along is not None and self.sight_across is not None):
            out.append((self.sight_along, self.sight_across))
        return out


@dataclass
class FinishStand:
    """A gantry over the line, a threshold under it, and a plaza past it.

    ## The three jobs, in the order the brief puts them

    **Destination.** The gantry is the only thing in this film taller than the
    course, and it stands *at the line* so that a camera chasing the pack down
    the sprint has it in frame before the pack reaches it. Its legs straddle
    the channel and clear it by `leg_clear`, which is reported rather than
    assumed, and its header's underside is `header_clear` above the running
    surface.

    **Crossing.** A kerb with a warm inlay, `line_rise` proud of the deck and
    no more: the brief's "do not use a massive glowing plane" is a real
    constraint here because the marbles are 0.57 across and anything emissive
    beside them wins.

    **Somewhere to go.** The plaza is laid on `Field`, which is a measurement
    of the replay rather than a plan of the course, and it is laid in strips
    that follow the deck's own fall instead of as one plate, because one plate
    over a falling deck either floats at the low end or swallows a racer at
    the high one. `well` is the pocket for whatever the deck does not catch.
    """

    channel_half: float = 1.90
    # Where the running surface sits under the site's own origin: the site is
    # on the centreline and the cradle floor is a channel depth below it.
    # Supplied by the caller from the run's own profile.
    floor_up: float = -0.52

    # The threshold.
    line_depth: float = 0.46
    line_rise: float = 0.11
    line_inlay: float = 0.17
    line_overhang: float = 0.62

    # The gantry.
    # **Just upstream of the line, so the field crosses under the arch.** At
    # +0.62 the near leg sits between the final chase and the catch pocket for
    # 20 frames of the winner's ring; at -0.30 that falls to 9 frames across
    # the whole cut, and the line reads as being *inside* the gantry rather
    # than in front of it.
    leg_along: float = -0.30
    leg_across: float = 2.85
    leg_thick: float = 0.42
    leg_rise: float = 4.10
    leg_foot: float = 1.30
    leg_margin: float = 0.95         # how far the plaza reaches past a leg
    foot_rise: float = 0.30          # the pad each leg stands on
    header_depth: float = 0.56
    header_thick: float = 0.66
    banner_rise: float = 0.42
    banner_thick: float = 0.11
    brace_rise: float = 2.55
    brace_thick: float = 0.17

    # The plaza.
    strips: int = 12
    plate_lift: float = 0.018        # above the deck the physics uses
    plate_thick: float = 0.10
    margin_back: float = 1.20        # past the furthest racer, upstream
    margin_front: float = 1.20       # past the furthest racer, downstream
    margin_across: float = 0.60
    rim_rise: float = 0.50
    rim_thick: float = 0.28
    catch_rise: float = 1.15
    catch_thick: float = 0.36
    plinth_drop: float = 2.60
    plinth_inset: float = 0.70
    lit_inset: float = 0.55

    # The approach. **架 - a colonnade, and it is the answer to a measurement
    # rather than a decoration.** The gantry stands at the line and the final
    # chase frames the *pack*, which is still twenty units short of it: at
    # 15.0 s the gantry projects to x in [-6.78, -4.33] on a frame that runs
    # [-1, 1], four and a third frame-widths off to the side. No height fixes
    # that, because it is off sideways and not below. Architecture that reaches
    # back up the channel does, and the brief's own rule is that the
    # environment adapts to the camera rather than the other way round.
    approach_count: int = 4
    approach_spacing: float = 4.0
    approach_across: float = 3.25
    approach_thick: float = 0.30
    approach_rise_near: float = 3.40   # the frame closest to the line
    approach_rise_far: float = 1.85    # the one furthest up the channel
    approach_beam: float = 0.34
    # Which side's leg to leave out, as a sign in `across`, or 0 for both.
    # **The final chase never crosses the channel**: its lens is on the
    # negative-`across` side for all 389 frames of the last cut, so a leg on
    # that side is a leg between it and the racers. Cantilevering from the far
    # side removes 35 racer-frames of occlusion and costs nothing a camera on
    # this film can see.
    approach_open_side: float = -1.0

    # The well.
    well_wall: float = 0.22
    well_rim: float = 0.16

    def parts(self, site: Site, palette: Palette,
              field: Field) -> tuple[list, list, dict]:
        static: list[dict[str, Any]] = []
        half = self.channel_half + self.line_overhang

        # 1. The line. **Track-integrated, and that is a constraint rather
        #    than a style.** The first build put a kerb across the channel at
        #    the line and `clearance` measured it at 0.000 from a racer - a
        #    threshold standing 0.11 proud of a surface a 0.57 ball rolls along
        #    is a wall. So the stripe is set into the running surface, at
        #    `floor_up`, and declares `touch`: a marble is *supposed* to be in
        #    contact with the line it crosses. Everything raised is outboard of
        #    the channel, where nothing races.
        inlay = _box(site, "line_inlay", palette.line,
                     (-0.5 * self.line_inlay, 0.5 * self.line_inlay),
                     (self.floor_up - 0.06, self.floor_up + 0.004),
                     (-self.channel_half + 0.04, self.channel_half - 0.04))
        inlay["touch"] = True
        static.append(inlay)
        for side, sign in (("left", -1.0), ("right", 1.0)):
            lo = sign * (self.channel_half + 0.02)
            hi = sign * half
            static.append(_box(site, f"line_kerb_{side}", palette.base,
                               (-0.5 * self.line_depth, 0.5 * self.line_depth),
                               (self.floor_up - 0.30, self.line_rise),
                               (min(lo, hi), max(lo, hi))))
            static.append(_box(site, f"line_kerb_cap_{side}", palette.line,
                               (-0.5 * self.line_depth - 0.02,
                                0.5 * self.line_depth + 0.02),
                               (self.line_rise - 0.05, self.line_rise + 0.01),
                               (min(lo, hi) - 0.02, max(lo, hi) + 0.02)))
            static.append(_box(site, f"line_post_{side}", palette.edge,
                               (-0.5 * self.line_depth - 0.06,
                                0.5 * self.line_depth + 0.06),
                               (self.floor_up - 0.30, self.line_rise + 0.46),
                               (sign * half, sign * (half + 0.24))))

        # 2. The gantry. **Each leg starts at its own local plaza height**,
        #    not at a shared datum: the deck under it falls 0.20 across the
        #    width and a pair of legs footed at one height has one of them
        #    buried and the other in the air.
        for side, sign in (("left", -1.0), ("right", 1.0)):
            base = field.surface(sign * self.leg_across)
            static.append(_box(site, f"leg_{side}", palette.frame,
                               (self.leg_along - 0.5 * self.leg_thick,
                                self.leg_along + 0.5 * self.leg_thick),
                               (base - self.leg_foot, self.leg_rise),
                               (sign * self.leg_across - 0.5 * self.leg_thick,
                                sign * self.leg_across + 0.5 * self.leg_thick)))
            static.append(_box(site, f"leg_foot_{side}", palette.base,
                               (self.leg_along - 0.58, self.leg_along + 0.62),
                               (base, base + self.foot_rise),
                               (sign * self.leg_across - 0.58,
                                sign * self.leg_across + 0.58)))
            # The pearl edge is on the *inboard* face, so the camera looking
            # down the channel sees a lit vertical line either side of the
            # racers rather than a rim light on a silhouette.
            static.append(_box(site, f"leg_edge_{side}", palette.edge,
                               (self.leg_along - 0.5 * self.leg_thick - 0.04,
                                self.leg_along + 0.5 * self.leg_thick + 0.04),
                               (field.surface(sign * self.leg_across) + 0.30,
                                self.leg_rise - 0.25),
                               (sign * (self.leg_across - 0.5 * self.leg_thick
                                        - 0.05),
                                sign * (self.leg_across - 0.5 * self.leg_thick))))
            static.append(_box(site, f"brace_{side}", palette.frame,
                               (self.leg_along - 0.5 * self.brace_thick,
                                self.leg_along + 0.5 * self.brace_thick),
                               (self.brace_rise, self.brace_rise
                                + self.brace_thick),
                               (sign * (self.leg_across - 0.5 * self.leg_thick),
                                sign * (self.leg_across - 0.5 * self.leg_thick
                                        - 0.55))))

        top = self.leg_rise
        static.append(_box(site, "gantry_header", palette.frame,
                           (self.leg_along - 0.5 * self.header_depth,
                            self.leg_along + 0.5 * self.header_depth),
                           (top - self.header_thick, top),
                           (-self.leg_across - 0.5 * self.leg_thick,
                            self.leg_across + 0.5 * self.leg_thick)))
        static.append(_box(site, "gantry_cap", palette.edge,
                           (self.leg_along - 0.5 * self.header_depth - 0.06,
                            self.leg_along + 0.5 * self.header_depth + 0.06),
                           (top, top + 0.17),
                           (-self.leg_across - 0.5 * self.leg_thick - 0.06,
                            self.leg_across + 0.5 * self.leg_thick + 0.06)))
        static.append(_box(site, "gantry_accent", palette.accent,
                           (self.leg_along - 0.5 * self.header_depth - 0.035,
                            self.leg_along + 0.5 * self.header_depth + 0.035),
                           (top - self.header_thick - self.banner_rise,
                            top - self.header_thick),
                           (-self.leg_across + 0.34, self.leg_across - 0.34)))
        # The one lit edge, on the approach face only: a strip on both faces
        # is two light sources in a room whose whole grade is two keys.
        static.append(_box(site, "gantry_lit", palette.lit,
                           (self.leg_along - 0.5 * self.header_depth - 0.05,
                            self.leg_along - 0.5 * self.header_depth - 0.01),
                           (top - self.header_thick - self.banner_rise + 0.08,
                            top - self.header_thick - self.banner_rise + 0.08
                            + self.banner_thick),
                           (-self.leg_across + 0.46, self.leg_across - 0.46)))

        # 2b. The approach colonnade: `approach_count` portals up the channel,
        #     each shorter than the one in front of it, so the last stretch has
        #     a converging perspective pointing at the gantry. They straddle
        #     the channel at the gantry's own clearance and carry the same warm
        #     line on their undersides.
        for index in range(self.approach_count):
            back = -self.approach_spacing * (index + 1)
            phase = index / float(max(1, self.approach_count - 1))
            local = field.channel(back)
            rise = local + (self.approach_rise_near
                            + (self.approach_rise_far - self.approach_rise_near)
                            * phase)
            for side, sign in (("left", -1.0), ("right", 1.0)):
                if sign == self.approach_open_side:
                    continue
                static.append(_box(site, f"approach_{index}_{side}",
                                   palette.frame,
                                   (back - 0.5 * self.approach_thick,
                                    back + 0.5 * self.approach_thick),
                                   (field.surface(sign * self.approach_across)
                                    - 1.0, rise),
                                   (sign * self.approach_across
                                    - 0.5 * self.approach_thick,
                                    sign * self.approach_across
                                    + 0.5 * self.approach_thick)))
            static.append(_box(site, f"approach_{index}_beam", palette.frame,
                               (back - 0.5 * self.approach_thick,
                                back + 0.5 * self.approach_thick),
                               (rise - self.approach_beam, rise),
                               (-self.approach_across - 0.5 * self.approach_thick,
                                self.approach_across + 0.5 * self.approach_thick)))
            static.append(_box(site, f"approach_{index}_line", palette.accent,
                               (back - 0.5 * self.approach_thick - 0.03,
                                back + 0.5 * self.approach_thick + 0.03),
                               (rise - self.approach_beam - 0.10,
                                rise - self.approach_beam),
                               (-self.approach_across + 0.25,
                                self.approach_across - 0.25)))

        # 3. The plaza, in strips that follow the deck's own fall.
        #
        # **Three constraints, and each one is a shape rather than a number.**
        #
        # *The fall.* One plate over a deck that falls 0.20 across its width
        # either floats at the low end or swallows a racer at the high one.
        # The plaza is `strips` bands, each at its own band's surface height;
        # the step between neighbours is under 0.03 and is invisible at the
        # size a phone scrubs this film at.
        #
        # *The channel.* The plaza's `across` range has to reach past the
        # centreline to hold the gantry's other leg, and the volume at
        # `across` near zero and `along` below zero is *the racing channel*.
        # So the near half of the plaza starts at the line: `plaza_near_*`
        # only exists downstream of `along = 0`, where the swept channel has
        # already ended.
        #
        # *The well.* A strip that passes over the pocket is emitted as two
        # boxes with the pocket between them, because a plaza laid over the
        # well would hide the two racers the well exists to catch.
        lo_a = field.along[0] - self.margin_back
        hi_a = field.along[1] + self.margin_front
        lo_c = field.across[0] - self.margin_across
        hi_c = max(field.across[1] + self.margin_across,
                   self.leg_across + self.leg_margin)
        cutouts = field.cutouts()
        # **The pocket's edges and the corridor's are band boundaries.** With
        # bands on a fixed pitch, the ones that overlap a cutout are wider than
        # it, and the plaza between a band edge and a cutout edge gets removed
        # for no reason - a racer rolling there floats over a hole that is not
        # in the measurement. Inserting the cutouts' own edges into the
        # boundary list makes each cut exactly its rectangle.
        step = (hi_c - lo_c) / float(max(1, self.strips))
        edges = [lo_c + index * step for index in range(self.strips + 1)]
        for _along, across in cutouts:
            edges.extend(v for v in across if lo_c < v < hi_c)
        edges = sorted(set(round(e, 6) for e in edges))
        for index in range(len(edges) - 1):
            c0, c1 = edges[index], edges[index + 1]
            if c1 - c0 < 0.02:
                continue
            surface = field.surface(0.5 * (c0 + c1)) + self.plate_lift
            # Downstream of the line for the bands that overlap the channel,
            # the full run for the bands that do not.
            back = lo_a if c1 <= -self.channel_half else 0.0
            holes = sorted(along for along, across in cutouts
                           if c0 >= across[0] - 1.0e-6 and c1 <= across[1] + 1.0e-6)
            spans: list[tuple[float, float]] = []
            cursor = back
            for hole in holes:
                if hole[0] > cursor:
                    spans.append((cursor, min(hole[0], hi_a)))
                cursor = max(cursor, hole[1])
            if cursor < hi_a:
                spans.append((cursor, hi_a))
            for part, (a0, a1) in enumerate(spans):
                if a1 - a0 < 0.05:
                    continue
                plate = _box(site, f"plaza_{index}_{part}", palette.deck,
                             (a0, a1),
                             (surface - self.plate_thick, surface),
                             (c0, c1))
                # A surfacing layer over the deck the physics uses, `plate_lift`
                # proud of it, so a racer resting on that deck is in contact
                # with this by construction. Declared rather than tolerated.
                plate["touch"] = True
                static.append(plate)
        # The foundation hangs from the *lowest* point of the plaza it holds
        # up, not from its middle: a plinth topped at the mean height is above
        # the deck at the low end, which is where six of the eight racers stop.
        low = field.surface(lo_c) - self.plate_thick - 0.06
        static.append(_box(site, "plaza_plinth", palette.base,
                           (lo_a + self.plinth_inset, hi_a - self.plinth_inset),
                           (low - self.plinth_drop, low),
                           (lo_c + self.plinth_inset,
                            -self.channel_half - self.plinth_inset)))

        # The parapet. The far `across` edge and the two `along` ends: the
        # fourth side is where the race arrives and is deliberately open.
        surface = field.surface(lo_c)
        static.append(_box(site, "plaza_rim_far", palette.edge,
                           (lo_a, hi_a),
                           (surface, surface + self.rim_rise),
                           (lo_c, lo_c + self.rim_thick)))
        static.append(_box(site, "plaza_rim_near", palette.edge,
                           (0.0, hi_a),
                           (field.surface(hi_c),
                            field.surface(hi_c) + self.rim_rise),
                           (hi_c - self.rim_thick, hi_c)))
        for side, edge, back in (("back", lo_a, lo_c),
                                 ("front", hi_a, lo_c)):
            sign = 1.0 if side == "back" else -1.0
            end_hi = -self.channel_half if side == "back" else hi_c
            static.append(_box(site, f"plaza_end_{side}", palette.frame,
                               (edge, edge + sign * self.catch_thick),
                               (surface, surface + self.catch_rise),
                               (back, end_hi)))
            static.append(_box(site, f"plaza_end_cap_{side}", palette.edge,
                               (edge - 0.05, edge + sign * self.catch_thick
                                + 0.05),
                               (surface + self.catch_rise,
                                surface + self.catch_rise + 0.12),
                               (back - 0.05, end_hi + 0.05)))
        static.append(_box(site, "plaza_lit", palette.lit,
                           (hi_a - self.catch_thick - 0.03,
                            hi_a - self.catch_thick + 0.01),
                           (surface + self.catch_rise - 0.26,
                            surface + self.catch_rise - 0.26 + 0.055),
                           (lo_c + self.lit_inset, hi_c - self.lit_inset)))

        # 4. The well, if the measurement found racers below the deck.
        well = 0
        if (field.well_along is not None and field.well_across is not None
                and field.well_floor is not None):
            wa, wc, floor = field.well_along, field.well_across, field.well_floor
            # Pearl rather than the deck's grey: the pocket is 1.6 below the
            # plaza and gets almost no key, so a mid surface down there reads
            # as a hole in the floor rather than as a lined recess. The racers
            # it holds are the winner and the runner-up.
            well_floor = _box(site, "well_floor", palette.edge,
                              (wa[0], wa[1]),
                              (floor - self.well_wall, floor),
                              (wc[0], wc[1]))
            well_floor["touch"] = True
            static.append(well_floor)
            # **Three walls, not four, and the missing one is the deck's.**
            #
            # The pocket's far side *is* the run-out deck's edge - that edge is
            # what the racers fall off - so the plaza's own plate is its lip and
            # a second wall there has nowhere to stand but inside the volume.
            # Built inward it buries m1, which comes to rest 0.01 outside the
            # edge; built outward it is 0.22 of wall in the 0.28 of clearance
            # m1 has. `clearance` measured both. The near wall and the front
            # wall have the whole plaza behind them and are ordinary.
            static.append(_box(site, "well_side_right", palette.base,
                               (wa[0] - self.well_wall,
                                wa[1] + self.well_wall),
                               (floor - self.well_wall,
                                field.surface(wc[1])),
                               (wc[1], wc[1] + self.well_wall)))
            # **No upstream wall.** The two racers this pocket exists for
            # arrive by falling off the end of the channel, and a wall across
            # the mouth is exactly where they fall: `clearance` measured the
            # first build's at 0.000. The mouth faces the line, which is also
            # the only side a viewer ever sees into it from.
            static.append(_box(site, "well_end_front", palette.base,
                               (wa[1], wa[1] + self.well_wall),
                               (floor - self.well_wall,
                                field.surface(0.5 * (wc[0] + wc[1]))),
                               (wc[0], wc[1])))
            lip = field.surface(0.5 * (wc[0] + wc[1]))
            # A frame of four bars, not a slab. The first build wrote one box
            # over the whole footprint, which is a lid on the pocket.
            # **Flush, and they declare `touch`.** A 0.16 lip standing proud of
            # the plaza is a kerb a racer skims: `clearance` put one at 0.183
            # from a marble centre, which is inside the ball. Set into the
            # surface it marks the pocket just as well, and a racer rolling
            # over the marking is in contact with it on purpose - the same
            # rule, and the same flag, as the finish line itself.
            for name, along, across in (
                    ("near", (wa[0], wa[1] + self.well_rim),
                     (wc[1], wc[1] + self.well_rim)),
                    ("front", (wa[1], wa[1] + self.well_rim),
                     (wc[0], wc[1] + self.well_rim))):
                rim = _box(site, f"well_rim_{name}", palette.accent,
                           along, (lip - self.well_rim, lip + 0.006), across)
                rim["touch"] = True
                static.append(rim)
            well = 5

        meta = {
            "channel_half": round(self.channel_half, 5),
            "leg_clear": round(self.leg_across - 0.5 * self.leg_thick
                               - self.channel_half, 5),
            "header_clear": round(self.leg_rise - self.header_thick, 5),
            "gantry_rise": round(self.leg_rise, 5),
            "plaza_along": [round(lo_a, 4), round(hi_a, 4)],
            "plaza_across": [round(lo_c, 4), round(hi_c, 4)],
            "plaza_strips": self.strips,
            "well_parts": well,
            "line_rise": round(self.line_rise, 5),
            "approach_count": self.approach_count,
            "approach_clear": round(self.approach_across
                                    - 0.5 * self.approach_thick
                                    - self.channel_half, 5),
            "field": field.describe(),
        }
        return static, [], meta


def finish_stand(site: Site, palette: Palette = MACHINE_PALETTE,
                 stand: FinishStand | None = None,
                 field: Field | None = None,
                 floor_up: float | None = None) -> dict[str, Any]:
    stand = stand or FinishStand(channel_half=site.half_width)
    if floor_up is not None:
        stand.floor_up = float(floor_up)
    static, motion, meta = stand.parts(site, palette, field or Field())
    return {
        "id": "finish",
        "site": site.describe(),
        "static": static,
        "motion": {"kind": "none", "parts": motion},
        "meta": meta,
    }


# --- assembly ---------------------------------------------------------------


def build(course: Any, *, palette: Palette = MACHINE_PALETTE,
          start: StartStand | None = None,
          finish: FinishStand | None = None,
          field: Field | None = None,
          run_name: str = "sprint") -> dict[str, Any]:
    """Both bookends for one course, as the spec `race2_bookends.gd` reads.

    The only entry point a tool should need, and the only one that knows a
    `Course` at all - `start_stand` and `finish_stand` take sites, so a future
    course that is not a `race2.course.Course` reaches them directly.
    """
    module = course.machine.modules["start"]
    s_site = start_site(course)
    f_site = finish_site(course, run_name)
    releases = module.panel_release_times()
    if not releases:
        raise ValueError("the start module declares no release")
    if len(set(round(r, 9) for r in releases)) != 1:
        raise ValueError(f"the start releases at {sorted(set(releases))}, not "
                         "at one time; a single gate would be a lie")
    return {
        "format": "race2.bookends",
        "version": 1,
        "units": "layout",
        "course": getattr(course, "concept", "?"),
        "palette": {field_name: getattr(palette, field_name)
                    for field_name in palette.__dataclass_fields__},
        "stands": [
            start_stand(s_site, module.bays, module.BAY_PITCH,
                        releases[0], module.RELEASE_DURATION, palette,
                        start),
            finish_stand(f_site, palette, finish, field,
                         _run_floor_up(course.runs[run_name])),
        ],
    }


def clearance(spec: dict[str, Any],
              points: Iterable[Sequence[float]]) -> dict[str, Any]:
    """How close every bookend part comes to any point of the racing record.

    The honesty check named in the module docstring. `points` is every marble
    *centre* in the replay, in layout units; the answer is, per part, the
    smallest distance from that centre to the part's box, so a gap under one
    marble radius means the part is inside a racer at some frame.

    A part may declare `"touch": true` - the finish line's inlay does, because
    a threshold a marble rolls over is supposed to be in contact with it - and
    those are reported separately rather than excused silently.

    Cylinders are measured as their bounding box, which under-reports the gap
    and is the right way round for a guard.
    """
    samples = [tuple(float(c) for c in p) for p in points]
    out: dict[str, Any] = {}
    for stand in spec["stands"]:
        parts = list(stand["static"]) + list(stand.get("motion", {}).get("parts", []))
        per_part: list[dict[str, Any]] = []
        for part in parts:
            if part["kind"] == "box":
                centre = part["centre"]
                axes = (part["along"], part["up"], part["across"])
                half = part["half"]
            else:
                a, b = part["from"], part["to"]
                centre = [0.5 * (a[i] + b[i]) for i in range(3)]
                axes = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
                radius = part["radius"]
                half = [0.5 * abs(b[i] - a[i]) + radius for i in range(3)]
            best = math.inf
            best_point: list[float] = []
            for point in samples:
                delta = _sub(point, centre)
                gap = 0.0
                for axis, extent in zip(axes, half):
                    local = abs(_dot(delta, axis)) - extent
                    if local > 0.0:
                        gap += local * local
                gap = math.sqrt(gap)
                if gap < best:
                    best = gap
                    best_point = [round(c, 4) for c in point]
                    if best <= 0.0:
                        break
            per_part.append({
                "name": part["name"],
                "gap": round(best, 4),
                "at": best_point,
                "touch": bool(part.get("touch", False)),
            })
        guarded = [p for p in per_part if not p["touch"]]
        worst = min(guarded, key=lambda p: p["gap"]) if guarded else None
        out[stand["id"]] = {
            "min_gap": worst["gap"] if worst else None,
            "part": worst["name"] if worst else "",
            "at": worst["at"] if worst else [],
            "parts": len(parts),
            "inside_a_racer": sorted(
                p["name"] for p in guarded if p["gap"] < MARBLE_RADIUS),
            "touching_by_design": sorted(p["name"] for p in per_part if p["touch"]),
            "per_part": sorted(per_part, key=lambda p: p["gap"]),
        }
    return out


def blocked(spec: dict[str, Any], eye: Sequence[float],
            target: Sequence[float], skip: Sequence[str] = ()) -> str:
    """The first bookend part a sight line passes through, or "".

    A slab test in each part's own frame - the boxes are axis-aligned there
    even when they are not in the world, which is the whole reason the spec
    carries the axes rather than a quaternion. Cylinders are tested as their
    bounding box, which over-reports blocking and is the right way round for a
    composition guard.

    `skip` names parts that are allowed to be in the way: the finish gantry's
    header is over the channel by design and a racer passing under it is not
    an occlusion, it is the shot.
    """
    origin = tuple(float(c) for c in eye)
    direction = _sub(target, origin)
    length = _norm(direction)
    if length < 1.0e-9:
        return ""
    direction = _scale(direction, 1.0 / length)
    for stand in spec["stands"]:
        parts = list(stand["static"]) + list(stand.get("motion", {}).get("parts", []))
        for part in parts:
            if part["name"] in skip:
                continue
            if part["kind"] == "box":
                centre = part["centre"]
                axes = (part["along"], part["up"], part["across"])
                half = part["half"]
            else:
                a, b = part["from"], part["to"]
                centre = [0.5 * (a[i] + b[i]) for i in range(3)]
                axes = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
                half = [0.5 * abs(b[i] - a[i]) + part["radius"] for i in range(3)]
            delta = _sub(centre, origin)
            near, far = 0.0, length
            hit = True
            for axis, extent in zip(axes, half):
                along_axis = _dot(direction, axis)
                to_centre = _dot(delta, axis)
                if abs(along_axis) < 1.0e-9:
                    if abs(to_centre) > extent:
                        hit = False
                        break
                    continue
                t0 = (to_centre - extent) / along_axis
                t1 = (to_centre + extent) / along_axis
                if t0 > t1:
                    t0, t1 = t1, t0
                near = max(near, t0)
                far = min(far, t1)
                if near > far:
                    hit = False
                    break
            if hit and near < length - 1.0e-6:
                return str(part["name"])
    return ""
