"""Rigid transforms and the socket frames modules are connected by.

Small on purpose. Bullet's own quaternion helpers live behind a client handle
and are not available while a module is being *authored*, before any world
exists, so the few operations module composition needs are written out here in
plain Python. They are the same operations - the quaternion convention is
Bullet's, (x, y, z, w), so a transform can be handed straight to
`createMultiBody` without a reordering step that somebody will eventually get
backwards.

## Sockets, and why the flow convention is what it is

A socket is a named frame on a module's local geometry that says *where a
marble crosses the module's boundary and which way it is going*. Its axes are:

    +X   the direction of travel through the socket
    +Y   the local up - the surface normal a marble is resting on, for a
         guided socket; plain world up for a drop
    +Z   completes the right-handed frame; across the channel

Both an exit and an entry are stated in the direction of travel, so connecting
them is an identity rather than a flip: world(entry) == world(exit). The
alternative - entries facing back up the flow, the way a plug faces a socket -
reads more naturally in a diagram and produces a 180-degree rotation in the
composition that has to be got right in three places instead of none.

## Two kinds of socket

GUIDED means the surface is continuous across the join: a marble rolls out of
one module and into the next without leaving contact, so the two frames must
coincide exactly, position and orientation. A start chute feeding a bowl rim is
guided.

DROP means the marble is in free flight across the join. Only the position and
the *heading* - the flow direction projected onto the horizontal - are
meaningful; the downstream module keeps its own pitch, because a catch basin
under a drain is not obliged to be vertical just because the drain is. The
bowl's drain feeds the curve this way, and it is the connection that makes the
machine three-dimensional: the curve passes underneath the bowl, which is a
second surface over the same ground point and is the thing a height field
cannot express.

Both kinds are composed from socket frames alone. Nothing in this package
places a module by typing a world coordinate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

__all__ = [
    "Vec3",
    "Quat",
    "Transform",
    "Socket",
    "GUIDED",
    "DROP",
    "IDENTITY",
    "quat_from_axis_angle",
    "quat_from_basis",
    "quat_multiply",
    "quat_conjugate",
    "quat_rotate",
    "quat_normalise",
    "yaw_quaternion",
    "basis_from_forward_up",
]

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]  # x, y, z, w - Bullet's order

GUIDED = "guided"
DROP = "drop"

_EPS = 1e-12


# --- quaternions ---------------------------------------------------------


def quat_normalise(q: Sequence[float]) -> Quat:
    x, y, z, w = (float(value) for value in q)
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm < _EPS:
        raise ValueError("cannot normalise a zero quaternion")
    return (x / norm, y / norm, z / norm, w / norm)


def quat_from_axis_angle(axis: Sequence[float], angle: float) -> Quat:
    ax, ay, az = (float(value) for value in axis)
    norm = math.sqrt(ax * ax + ay * ay + az * az)
    if norm < _EPS:
        raise ValueError("rotation needs an axis with a direction")
    half = 0.5 * float(angle)
    s = math.sin(half) / norm
    return (ax * s, ay * s, az * s, math.cos(half))


def quat_multiply(a: Sequence[float], b: Sequence[float]) -> Quat:
    """a * b: the rotation that applies b first and then a."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def quat_conjugate(q: Sequence[float]) -> Quat:
    x, y, z, w = q
    return (-x, -y, -z, w)


def quat_rotate(q: Sequence[float], v: Sequence[float]) -> Vec3:
    x, y, z, w = q
    vx, vy, vz = v
    # t = 2 (q_vec x v); v' = v + w t + q_vec x t. Two cross products rather
    # than building a matrix, which matters only because this runs per vertex
    # over a hundred thousand of them when a module is placed.
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + y * tz - z * ty,
        vy + w * ty + z * tx - x * tz,
        vz + w * tz + x * ty - y * tx,
    )


def quat_from_basis(right: Sequence[float], up: Sequence[float], back: Sequence[float]) -> Quat:
    """The rotation whose columns are the three given orthonormal axes.

    Shepperd's method: pick the largest of the four possible denominators so
    the division is never near zero. The naive `w = sqrt(1 + trace) / 2` branch
    loses all of its precision at a 180-degree rotation, which is exactly the
    orientation a socket pointing back along -X has.
    """
    m00, m10, m20 = right
    m01, m11, m21 = up
    m02, m12, m22 = back
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        q = ((m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s)
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        q = (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        q = ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        q = ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)
    return quat_normalise(q)


def basis_from_forward_up(forward: Sequence[float], up: Sequence[float]) -> Quat:
    """A socket frame from a travel direction and an approximate up.

    `forward` becomes +X exactly. `up` is orthogonalised against it, so a
    caller can pass world up and get the right frame on a banked or descending
    section without having to work out the perpendicular itself.
    """
    fx, fy, fz = forward
    length = math.sqrt(fx * fx + fy * fy + fz * fz)
    if length < _EPS:
        raise ValueError("a socket needs a direction of travel")
    fx, fy, fz = fx / length, fy / length, fz / length

    ux, uy, uz = up
    dot = ux * fx + uy * fy + uz * fz
    ux, uy, uz = ux - dot * fx, uy - dot * fy, uz - dot * fz
    length = math.sqrt(ux * ux + uy * uy + uz * uz)
    if length < 1e-6:
        raise ValueError("socket up is parallel to its direction of travel")
    ux, uy, uz = ux / length, uy / length, uz / length

    # +Z completes the right-handed frame: Z = X cross Y.
    zx = fy * uz - fz * uy
    zy = fz * ux - fx * uz
    zz = fx * uy - fy * ux
    return quat_from_basis((fx, fy, fz), (ux, uy, uz), (zx, zy, zz))


def yaw_quaternion(angle: float) -> Quat:
    """Rotation about +Y, which is the only free parameter of a drop join."""
    return quat_from_axis_angle((0.0, 1.0, 0.0), angle)


# --- transforms ----------------------------------------------------------


@dataclass(frozen=True)
class Transform:
    """A rigid placement: rotate, then translate. Bullet's own convention."""

    position: Vec3 = (0.0, 0.0, 0.0)
    rotation: Quat = (0.0, 0.0, 0.0, 1.0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "position", tuple(float(v) for v in self.position))
        object.__setattr__(self, "rotation", quat_normalise(self.rotation))

    def apply(self, point: Sequence[float]) -> Vec3:
        rx, ry, rz = quat_rotate(self.rotation, point)
        px, py, pz = self.position
        return (rx + px, ry + py, rz + pz)

    def apply_direction(self, direction: Sequence[float]) -> Vec3:
        """Rotate without translating - for normals, tangents and velocities."""
        return quat_rotate(self.rotation, direction)

    def compose(self, inner: "Transform") -> "Transform":
        """self * inner: apply `inner` first, then `self`."""
        return Transform(
            position=self.apply(inner.position),
            rotation=quat_multiply(self.rotation, inner.rotation),
        )

    def inverse(self) -> "Transform":
        inverse_rotation = quat_conjugate(self.rotation)
        moved = quat_rotate(inverse_rotation, self.position)
        return Transform(position=(-moved[0], -moved[1], -moved[2]), rotation=inverse_rotation)

    def axes(self) -> tuple[Vec3, Vec3, Vec3]:
        """The frame's +X, +Y and +Z, expressed in the parent frame."""
        return (
            quat_rotate(self.rotation, (1.0, 0.0, 0.0)),
            quat_rotate(self.rotation, (0.0, 1.0, 0.0)),
            quat_rotate(self.rotation, (0.0, 0.0, 1.0)),
        )

    def transform_points(self, points: Iterable[Sequence[float]]) -> list[Vec3]:
        return [self.apply(point) for point in points]


IDENTITY = Transform()


@dataclass(frozen=True)
class Socket:
    """Where a marble crosses a module boundary, and how.

    `frame` is in the module's local coordinates; `Machine` resolves it to
    world by composing with the module's placement. `width` and `height` are
    the free channel at the socket, quoted so a connection can check that the
    two sides of a join actually admit the same marble - a 2 wu chute feeding a
    1.2 wu channel is a jam waiting for a specific seed, and it should be a
    build error rather than a run that mysteriously stalls.
    """

    name: str
    frame: Transform
    kind: str = GUIDED
    width: float = 0.0
    height: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in (GUIDED, DROP):
            raise ValueError(f"socket {self.name!r}: unknown kind {self.kind!r}")

    def flow(self) -> Vec3:
        return self.frame.axes()[0]

    def up(self) -> Vec3:
        return self.frame.axes()[1]

    def heading(self) -> float:
        """The flow direction projected onto the horizontal, as an angle.

        Measured so that `yaw_quaternion(target - source)` is exactly the
        rotation that turns a socket with heading `source` to face `target`.
        `yaw_quaternion` rotates +X toward -Z, so the angle is atan2(-z, x).
        """
        fx, _, fz = self.flow()
        if abs(fx) < _EPS and abs(fz) < _EPS:
            return 0.0
        return math.atan2(-fz, fx)
