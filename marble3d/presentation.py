"""The contract between the module that is simulated and the module that is drawn.

A marble machine has two descriptions of every part of it. PyBullet needs a
collider: a one-sided surface of revolution with no thickness, tessellated to a
sagitta budget, that exists only to be touched. Godot needs an object: a shell
with an inside and an outside, a rim with a top face, a gold collar round the
drain, an acrylic guard standing off on its own shoulder. Those two are not the
same mesh and should never be made into one. A collider fine enough to look
good is a collider too slow to solve, and a visual mesh coarse enough to solve
against is a visual mesh with facets on the highlight.

What they must agree on is not triangles. It is the handful of numbers that
decide whether a marble appears to touch what the physics says it touched:

    where the module is            origin and orientation
    how big it is                  the anchors: radii, depths, lengths
    where a marble enters          the entry socket, in world space
    where a marble leaves          the exit socket, in world space
    where it falls through         the drain centre and radius
    what moves                     actuator rest poses and travel

This module is where those numbers are written down once. Python owns it,
because Python owns the physics that determines them. Godot reads the document
this produces and builds its authored assets to fit; it derives no geometry of
its own and hard-codes no dimension of the machine.

## Why the assets are re-parameterised rather than scaled

The visual lab authored its bowl at an inner radius of 2.52 with a marble of
radius 0.30 - a dish about eight marble-radii across. The physics bowl is 12.5
with a marble of 0.5 - twenty-five. There is no single number you can multiply
the authored asset by that makes both the bowl and the marble come out right,
because the two were authored to different proportions. Scaling the asset to
match the bowl makes the marbles three times too small for it; scaling to match
the marble makes the bowl three times too small for them, and they climb
straight out of it.

So the authored assets take their dimensions from this contract instead. What
survives from the visual lab is the form language - the thick rim with a top
face, the standoff guard, the gold collar, the shell profile, the palette - and
the proportions that are genuinely proportions, which are kept as ratios of the
authored asset and re-applied to the physics dimension. What does not survive
is any absolute size, because the absolute sizes are the physics'.

## Coordinates

PyBullet is configured +Y up here, gravity -Y, the machine laid out in XZ, and
it is right-handed. Godot is +Y up and right-handed. The two frames are
therefore the same frame, and the conversion is the identity - on positions, on
directions, on velocities and on quaternions, whose components are (x, y, z, w)
in both.

That is a claim, not a convenience, and `tests/test_marble3d_presentation.py`
plus `godot/scripts/marble3d_axis_check.gd` test it from both ends against the
same golden vectors: a conversion that is the identity is exactly the kind of
thing that is never noticed to be wrong until a marble orbits the bowl
backwards.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from marble3d.geometry import Transform, quat_rotate

__all__ = [
    "PRESENTATION_SCALE",
    "CONTRACT_VERSION",
    "VISUAL_ASSETS",
    "to_render_position",
    "to_render_direction",
    "to_render_quaternion",
    "to_render_transform",
    "golden_vectors",
    "ModulePresentation",
    "MachinePresentation",
    "presentation_for_machine",
    "check_against_replay",
]


# One world unit of physics is one world unit of Godot. Not a scale factor set
# to 1.0 out of laziness: the alternative was a global multiplier, and a global
# multiplier is a number that has to be applied to positions, to radii, to
# camera distances and to near planes, and forgotten in exactly one of them.
# The physics units are already sensible for rendering - a 1 wu marble in a 38
# wu machine - so the presentation adopts them and there is nothing to forget.
PRESENTATION_SCALE = 1.0

CONTRACT_VERSION = 1

# Which authored asset draws which simulated module.
VISUAL_ASSETS = {
    "StartModule": "start_platform",
    "BowlModule": "hero_bowl",
    "CurveModule": "s_curve",
}


# --- coordinates ----------------------------------------------------------
#
# All of these are the identity. They exist as named functions anyway, because
# the alternative to one conversion that is the identity is fifteen call sites
# that each decided, separately and silently, that no conversion was needed.


def to_render_position(p: Sequence[float]) -> tuple[float, float, float]:
    """A PyBullet point in the render frame."""
    return (
        float(p[0]) * PRESENTATION_SCALE,
        float(p[1]) * PRESENTATION_SCALE,
        float(p[2]) * PRESENTATION_SCALE,
    )


def to_render_direction(v: Sequence[float]) -> tuple[float, float, float]:
    """A direction or linear velocity in the render frame."""
    return (
        float(v[0]) * PRESENTATION_SCALE,
        float(v[1]) * PRESENTATION_SCALE,
        float(v[2]) * PRESENTATION_SCALE,
    )


def to_render_angular_velocity(w: Sequence[float]) -> tuple[float, float, float]:
    """An angular velocity in the render frame.

    Separate from `to_render_direction` because it is not a length: rad/s does
    not scale with the presentation. Identical today, since the scale is 1.0,
    and deliberately not merged, because the day the scale stops being 1.0 is
    the day the difference matters and nobody will remember it.
    """
    return (float(w[0]), float(w[1]), float(w[2]))


def to_render_quaternion(q: Sequence[float]) -> tuple[float, float, float, float]:
    """A PyBullet quaternion in the render frame.

    Both engines store (x, y, z, w) and both rotate right-handed, so this
    reorders nothing. `Quaternion(x, y, z, w)` in GDScript takes the components
    in this order too.
    """
    return (float(q[0]), float(q[1]), float(q[2]), float(q[3]))


def to_render_transform(t: Transform) -> dict[str, Any]:
    return {
        "position": list(to_render_position(t.position)),
        "rotation": list(to_render_quaternion(t.rotation)),
    }


def golden_vectors() -> dict[str, Any]:
    """Cases both engines must agree on, so the identity claim is tested.

    Chosen to fail loudly under the mistakes that are actually made: a swapped
    Y and Z, a negated axis, a (w, x, y, z) quaternion read as (x, y, z, w),
    and a left-handed rotation. The 120-degree turn about (1,1,1)/sqrt(3)
    cycles the axes, so reading its components in the wrong order sends a test
    point somewhere obviously different rather than somewhere subtly different.
    """
    root = 1.0 / math.sqrt(3.0)
    half = math.sin(math.pi / 4.0)
    cases: list[dict[str, Any]] = [
        {
            # +90 deg about +Y. Right-handed, this takes +X to -Z.
            "name": "yaw_90_about_up",
            "quaternion": [0.0, half, 0.0, half],
            "point": [1.0, 0.0, 0.0],
        },
        {
            "name": "pitch_90_about_x",
            "quaternion": [half, 0.0, 0.0, half],
            "point": [0.0, 1.0, 0.0],
        },
        {
            "name": "roll_90_about_z",
            "quaternion": [0.0, 0.0, half, half],
            "point": [0.0, 1.0, 0.0],
        },
        {
            "name": "cycle_120_about_diagonal",
            "quaternion": [
                root * math.sin(math.pi / 3.0),
                root * math.sin(math.pi / 3.0),
                root * math.sin(math.pi / 3.0),
                math.cos(math.pi / 3.0),
            ],
            "point": [1.0, 2.0, 3.0],
        },
        {
            # The real placement of the start chute. Not axis-aligned, so it
            # catches an engine that composes quaternions in the other order.
            "name": "start_chute_placement",
            "quaternion": [
                0.09989766463164737,
                -0.7000146117054578,
                -0.09989766463164738,
                0.7000146117054579,
            ],
            "point": [14.625, 8.958783188715831, -10.277402395547233],
        },
    ]
    for case in cases:
        case["rotated"] = list(quat_rotate(case["quaternion"], case["point"]))
    return {"scale": PRESENTATION_SCALE, "cases": cases}


# --- the contract ---------------------------------------------------------


@dataclass
class ModulePresentation:
    """Everything the renderer is allowed to know about one module."""

    module_id: str
    module_type: str
    visual_asset: str
    origin: tuple[float, float, float]
    orientation: tuple[float, float, float, float]
    scale: float
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]]
    sockets: dict[str, dict[str, Any]]
    anchors: dict[str, Any]
    visual: dict[str, Any]
    actuators: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.module_id,
            "type": self.module_type,
            "visual_asset": self.visual_asset,
            "origin": list(self.origin),
            "orientation": list(self.orientation),
            "scale": self.scale,
            "bounds": [list(self.bounds[0]), list(self.bounds[1])],
            "sockets": self.sockets,
            "anchors": self.anchors,
            "visual": self.visual,
            "actuators": self.actuators,
        }


@dataclass
class MachinePresentation:
    name: str
    marble_radius: float
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]]
    modules: list[ModulePresentation]

    def to_json(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "name": self.name,
            "scale": PRESENTATION_SCALE,
            "frame": (
                "+Y up, gravity -Y, machine laid out in XZ; "
                "right-handed; quaternions xyzw"
            ),
            "marble_radius": self.marble_radius,
            "bounds": [list(self.bounds[0]), list(self.bounds[1])],
            "modules": [module.to_json() for module in self.modules],
        }

    def module(self, module_id: str) -> ModulePresentation:
        for module in self.modules:
            if module.module_id == module_id:
                return module
        have = ", ".join(module.module_id for module in self.modules)
        raise KeyError(f"no module {module_id!r} in the contract; it has [{have}]")


def _world_socket(module: Any, name: str, socket: Any) -> dict[str, Any]:
    """One socket, in world space.

    Worth spelling out because the replay does not do this. `to_json()` writes
    each module's sockets in the module's *local* frame while writing its
    transform in *world*, so a consumer that reads a socket position straight
    out of the replay and places something there puts it at the origin for
    every module that happens to be the anchored one. The start chute's exit
    socket serialises as (0, 0, 0).
    """
    frame = module.transform.compose(socket.frame)
    return {
        "name": name,
        "kind": socket.kind,
        "position": list(to_render_position(frame.position)),
        "rotation": list(to_render_quaternion(frame.rotation)),
        "flow": list(to_render_direction(quat_rotate(frame.rotation, (1.0, 0.0, 0.0)))),
        "up": list(to_render_direction(quat_rotate(frame.rotation, (0.0, 1.0, 0.0)))),
        "width": socket.width * PRESENTATION_SCALE,
        "height": socket.height * PRESENTATION_SCALE,
    }


def _world_bounds(module: Any) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """The module's local AABB, placed, re-fitted around the rotated corners."""
    box = module.local_bounds()
    (lx, ly, lz), (hx, hy, hz) = box.lower, box.upper
    corners = [
        module.transform.apply((x, y, z))
        for x in (lx, hx)
        for y in (ly, hy)
        for z in (lz, hz)
    ]
    low = tuple(min(corner[axis] for corner in corners) for axis in range(3))
    high = tuple(max(corner[axis] for corner in corners) for axis in range(3))
    return low, high


# --- authored proportions -------------------------------------------------
#
# Ratios lifted from the visual lab's assets, so the physics dimensions come
# back wearing the authored proportions. Each is the authored constant divided
# by the authored constant it was drawn against, and the comment says which.


# hero_bowl.gd draws its dish out to INNER_RADIUS 2.52 and hangs every piece
# of detail off that number. `detail_scale` below is the ratio between the
# simulated dish's outer edge and that one, and the asset multiplies its
# authored fillets, hoop stocks, bolt sizes and guard height by it. Primary
# dimensions are never scaled this way - they come from the physics directly.
AUTHORED_BOWL_DISH_RADIUS = 2.52
# s_curve.gd: WALL_HEIGHT 0.25 / HALF_WIDTH 0.40
CURVE_WALL_OVER_HALF_WIDTH = 0.25 / 0.40


def _bowl_visual(spec: Any, describe: dict[str, Any]) -> dict[str, Any]:
    """The authored bowl, dimensioned by the simulated one.

    `outer_radius` is the number that matters most here, and it is not the rim
    radius. The collider is an open surface of revolution with no wall at all:
    nothing stops a marble at `rim_radius`, and what actually contains the run
    is the dish continuing to climb out to `max_radius`. A visual bowl that
    ended at the rim would have marbles riding up a slope nobody drew.

    `profile_power` matters nearly as much. The authored dish is a cosine and
    the simulated one is a power law, and they are not close: at half the rim
    radius they differ by about two marble radii, which is the difference
    between a marble touching the surface and hovering over it. The asset
    takes the exponent from here and draws the surface the solver used.
    """
    inner = float(spec["rim_radius"])
    outer = float(spec["max_radius"])
    depth = float(spec["rim_depth"])
    power = float(spec["profile_power"])
    return {
        "inner_radius": inner,
        "outer_radius": outer,
        "depth": depth,
        "profile_power": power,
        # How far the dish's outer edge stands above its floor. The asset's
        # local origin is that edge, so this is also what the builder lifts
        # the node by to put its floor on the module origin.
        "outer_depth": depth * (outer / inner) ** power,
        "drain_radius": float(spec["drain_radius"]),
        "lip_radius": float(spec["lip_radius"]),
        "shaft_bottom": float(spec["shaft_bottom"]),
        "entry_radius": float(spec["entry_radius"]),
        "rim_elevation": depth,
        "drain_rim_height": float(describe.get("drain_rim_height", 0.0)),
        "segments": int(describe.get("segments", 64)),
        "detail_scale": outer / AUTHORED_BOWL_DISH_RADIUS,
    }


def _curve_visual(module: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """The authored channel, swept along the simulated centreline.

    The visual lab's S-curve already builds from a list of control points, so
    this is the one asset that needs no re-parameterising - only feeding. The
    points handed over are the exact frames the collider was swept along, in
    module-local space, so the drawn channel and the solved channel are the
    same curve sampled the same way.
    """
    fractions = module._fractions()
    centreline = []
    for fraction in fractions:
        frame = module.frame_at(fraction)
        centreline.append(
            {
                "t": fraction,
                "position": list(to_render_position(frame.position)),
                "rotation": list(to_render_quaternion(frame.rotation)),
            }
        )
    half_width = 0.5 * float(spec["width"])
    return {
        "centreline": centreline,
        "half_width": half_width,
        "wall_height": CURVE_WALL_OVER_HALF_WIDTH * half_width,
        "catch_width": float(spec["catch_width"]),
        "radius": float(spec["radius"]),
        "sweep_degrees": float(spec["sweep_degrees"]),
        "drop": float(spec["drop"]),
        "bank_deg": float(spec["bank_deg"]),
    }


def _start_visual(module: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """The authored platform, with its bays where the marbles actually rest.

    The visual lab drew eight bays side by side across a deck. The simulated
    chute queues eight marbles in single file along a 21 wu incline. Those are
    different machines, and the brief asks that marble positions match loading
    bays - so the bays are placed from `marble_starts()`, which is where the
    solver puts the marbles on tick zero. The bay is then correct by
    construction rather than by a number matching in two files.
    """
    bays = []
    for index, placement in enumerate(module.marble_starts()):
        bays.append(
            {
                "index": index,
                "position": list(to_render_position(placement.position)),
                "rotation": list(to_render_quaternion(placement.rotation)),
            }
        )
    return {
        "bays": bays,
        "channel_width": float(spec["width"]),
        "wall": float(spec["wall"]),
        "length": float(spec["length"]),
        "incline_deg": float(spec["incline_deg"]),
        "gate_offset": float(spec["gate_offset"]),
        "marble_spacing": float(spec["marble_spacing"]),
        "drop": float(spec["drop"]),
    }


def _actuator_json(module: Any, actuator: Any) -> dict[str, Any]:
    """An actuator, placed, with the rest rotation the replay drops.

    `LinearGate.to_json()` serialises only the rest *position*; a renderer that
    rebuilt the gate from the replay alone would draw an unrotated box lying
    across a chute that is itself rotated a long way off axis.
    """
    rest = module.transform.compose(actuator.rest)
    travel = module.transform.apply_direction(actuator.travel)
    return {
        "name": actuator.name,
        "kind": type(actuator).__name__,
        "half_extents": list(to_render_position(actuator.half_extents)),
        "rest": to_render_transform(rest),
        "travel": list(to_render_direction(travel)),
        "release_time": float(actuator.release_time),
        "duration": float(actuator.duration),
    }


_VISUAL_BUILDERS = {
    "BowlModule": lambda module, spec, describe: _bowl_visual(spec, describe),
    "CurveModule": lambda module, spec, describe: _curve_visual(module, spec),
    "StartModule": lambda module, spec, describe: _start_visual(module, spec),
}


def _anchors(module_type: str, module: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """The few numbers a contact check needs, in world space."""
    if module_type == "BowlModule":
        centre = module.transform.apply((0.0, 0.0, 0.0))
        return {
            "centre": list(to_render_position(centre)),
            "up": list(to_render_direction(
                quat_rotate(module.transform.rotation, (0.0, 1.0, 0.0)))),
            "rim_radius": float(spec["rim_radius"]),
            "max_radius": float(spec["max_radius"]),
            "rim_elevation": float(spec["rim_depth"]),
            "drain_centre": list(to_render_position(
                module.transform.apply((0.0, 0.0, 0.0)))),
            "drain_radius": float(spec["drain_radius"]),
            "shaft_bottom": float(spec["shaft_bottom"]),
            "profile_power": float(spec["profile_power"]),
        }
    if module_type == "CurveModule":
        return {
            "radius": float(spec["radius"]),
            "sweep_degrees": float(spec["sweep_degrees"]),
            "drop": float(spec["drop"]),
            "half_width": 0.5 * float(spec["width"]),
            "bank_deg": float(spec["bank_deg"]),
        }
    return {
        "length": float(spec.get("length", 0.0)),
        "channel_width": float(spec.get("width", 0.0)),
        "incline_deg": float(spec.get("incline_deg", 0.0)),
    }


def presentation_for_machine(machine: Any, marble_radius: float) -> MachinePresentation:
    """Read a built machine and write down what the renderer needs.

    Takes the assembled `Machine` rather than a replay because the replay is
    lossy on exactly the points presentation cares about: local sockets, no
    curve centreline, no gate rotation. `check_against_replay` then proves the
    two agree wherever they overlap, which is what keeps this from drifting
    into a second, quietly different description of the machine.
    """
    modules: list[ModulePresentation] = []
    for module_id in machine.order:
        module = machine.modules[module_id]
        module_type = type(module).__name__
        describe = module.describe()
        spec = describe.get("spec", {})
        builder = _VISUAL_BUILDERS.get(module_type)
        if builder is None:
            raise KeyError(
                f"module {module_id!r} is a {module_type}, which no authored asset "
                f"draws; add it to VISUAL_ASSETS and _VISUAL_BUILDERS together"
            )
        low, high = _world_bounds(module)
        modules.append(
            ModulePresentation(
                module_id=module_id,
                module_type=module_type,
                visual_asset=VISUAL_ASSETS[module_type],
                origin=to_render_position(module.transform.position),
                orientation=to_render_quaternion(module.transform.rotation),
                scale=PRESENTATION_SCALE,
                bounds=(to_render_position(low), to_render_position(high)),
                sockets={
                    name: _world_socket(module, name, socket)
                    for name, socket in module.local_sockets().items()
                },
                anchors=_anchors(module_type, module, spec),
                visual=builder(module, spec, describe),
                actuators=[
                    _actuator_json(module, actuator)
                    for actuator in module.local_actuators()
                ],
            )
        )

    machine_box = machine.bounds()
    low, high = machine_box.lower, machine_box.upper
    return MachinePresentation(
        name=machine.name,
        marble_radius=marble_radius * PRESENTATION_SCALE,
        bounds=(to_render_position(low), to_render_position(high)),
        modules=modules,
    )


def check_against_replay(
    presentation: MachinePresentation, replay: dict[str, Any], tolerance: float = 1e-9
) -> list[str]:
    """Every place the contract and the replay describe the same thing.

    The contract is built from a freshly assembled machine and the replay was
    written by a run of a machine assembled the same way. If those two ever
    stop being the same machine, this is where it shows up - before a render
    puts an authored bowl somewhere the marbles are not.
    """
    problems: list[str] = []
    replay_machine = replay.get("machine", {})

    if replay_machine.get("name") != presentation.name:
        problems.append(
            f"machine name: contract {presentation.name!r}, "
            f"replay {replay_machine.get('name')!r}"
        )

    by_id = {module["id"]: module for module in replay_machine.get("modules", [])}
    if set(by_id) != {module.module_id for module in presentation.modules}:
        problems.append(
            f"module ids: contract {sorted(m.module_id for m in presentation.modules)}, "
            f"replay {sorted(by_id)}"
        )
        return problems

    for module in presentation.modules:
        recorded = by_id[module.module_id]
        if recorded["type"] != module.module_type:
            problems.append(
                f"{module.module_id}: contract is a {module.module_type}, "
                f"replay a {recorded['type']}"
            )
        for axis in range(3):
            delta = abs(recorded["transform"]["position"][axis] - module.origin[axis])
            if delta > tolerance:
                problems.append(
                    f"{module.module_id}: origin axis {axis} differs by {delta:g}"
                )
        for axis in range(4):
            delta = abs(
                recorded["transform"]["rotation"][axis] - module.orientation[axis]
            )
            if delta > tolerance:
                problems.append(
                    f"{module.module_id}: orientation component {axis} differs "
                    f"by {delta:g}"
                )
        # The replay's sockets are local, so they are compared after placing
        # them - which is the whole reason this contract exists.
        for name, socket in recorded.get("sockets", {}).items():
            if name not in module.sockets:
                problems.append(f"{module.module_id}: replay has socket {name!r}, "
                                f"contract does not")
                continue
            placed = Transform(
                position=module.origin, rotation=module.orientation
            ).apply(socket["position"])
            for axis in range(3):
                delta = abs(placed[axis] - module.sockets[name]["position"][axis])
                if delta > 1e-6:
                    problems.append(
                        f"{module.module_id}.{name}: placed socket axis {axis} "
                        f"differs by {delta:g}"
                    )
    return problems
