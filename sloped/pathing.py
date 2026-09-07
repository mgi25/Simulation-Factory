"""The approved course's own path law, ported from GDScript, sample for sample.

The visible track is `v2_track.build`: a Catmull-Rom spline through the layout
table's control points, arc-length resampled, banked from its own horizontal
curvature, and swept with a per-sample width curve. A collider built from
anything else - a fresh spline through the same controls, an interpolation of
the 26-point centreline the layout JSON records, a circular-arc chain - lands
somewhere near the visible channel and not on it.

So this module is a transcription and not a re-derivation. Every function here
is the GDScript function of the same name in `lab_forms.gd` or `v2_forms.gd`,
including the parts that look like accidents:

* `smooth_path(controls, 26)` emits 4 * 26 + 27 = 131 points, not 26, because
  the last span of the padded spline emits one more step than the others;
* `flat_tangents` differences neighbours rather than taking the analytic
  derivative, so the first and last tangents are one-sided;
* `curvature` is a *plan-view* quantity - a diving track has large 3D curvature
  and must not bank for it;
* `smooth_series` is four box-blur passes, which is what stops the bank angle
  stepping at a spline-span joint;
* `auto_bank` eases the last six samples at each end to zero with a smoothstep,
  which is what lets a banked run meet a level module square.

Reproducing the accidents is the point. `tests/test_sloped_pathing.py` checks
the result against the 26 centreline points and the bank extreme that
`docs/validation/sloped_course/physics_layout.json` recorded from the built
scene, which is the only independent evidence available that this port is the
same curve the stills were photographed on.

Everything here is in **layout units**. `sloped.scale` converts.
"""

from __future__ import annotations

import math

__all__ = [
    "SPLINE_SAMPLES",
    "TRACK_SAMPLES",
    "BANK_EASE_ENDS",
    "smooth_path",
    "resample",
    "path_length",
    "flat_tangents",
    "curvature",
    "smooth_series",
    "auto_bank",
    "banked_basis",
    "width_curve",
    "build_path",
    "arc_lengths",
    "nearest_index",
]

Vec3 = tuple[float, float, float]

# `v2_track.build` is `V2Forms.resample(Forms.smooth_path(controls, 26), N)`,
# and N is **not** v2_track's own default of 132. `course_machine.gd` line 103
# passes 118, and every still in `docs/validation/sloped_course/` was
# photographed at that count. The difference is not cosmetic: 118 samples put
# the recorded 26-point centreline exactly where the contract says it is, and
# 132 puts it up to 0.31 units away - a marble diameter and a half of drift
# through the hairpins, where the samples are furthest apart.
SPLINE_SAMPLES = 26
TRACK_SAMPLES = 118
BANK_EASE_ENDS = 6


def _sub(a, b) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, k: float) -> Vec3:
    return (a[0] * k, a[1] * k, a[2] * k)


def _norm(a) -> Vec3:
    length = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    if length < 1e-12:
        raise ValueError("cannot normalise a zero vector")
    return (a[0] / length, a[1] / length, a[2] / length)


def _cross(a, b) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _lerp(a, b, t: float) -> Vec3:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    """Godot's `smoothstep`, which clamps before it eases."""
    if edge0 == edge1:
        return 0.0 if value < edge0 else 1.0
    u = (value - edge0) / (edge1 - edge0)
    u = min(1.0, max(0.0, u))
    return u * u * (3.0 - 2.0 * u)


def _catmull_rom(p0, p1, p2, p3, t: float) -> Vec3:
    t2 = t * t
    t3 = t2 * t
    out = []
    for axis in range(3):
        a, b, c, d = p0[axis], p1[axis], p2[axis], p3[axis]
        out.append(
            0.5
            * (
                2.0 * b
                + (c - a) * t
                + (2.0 * a - 5.0 * b + 4.0 * c - d) * t2
                + (-a + 3.0 * b - 3.0 * c + d) * t3
            )
        )
    return (out[0], out[1], out[2])


def smooth_path(controls, samples: int = SPLINE_SAMPLES) -> list[Vec3]:
    """`lab_forms.smooth_path`: Catmull-Rom with the end controls duplicated.

    The duplication is what makes the curve start and end exactly on the first
    and last control, which is what lets one run hand its end point to the next
    as an attachment. `samples` is steps *per span*, so six controls give five
    spans and 131 points.
    """
    controls = [tuple(float(v) for v in point) for point in controls]
    if len(controls) < 2:
        return list(controls)
    padded = [controls[0]] + controls + [controls[-1]]
    path: list[Vec3] = []
    spans = len(padded) - 3
    for span in range(spans):
        p0, p1, p2, p3 = padded[span], padded[span + 1], padded[span + 2], padded[span + 3]
        last = samples if span == spans - 1 else samples - 1
        for step in range(last + 1):
            path.append(_catmull_rom(p0, p1, p2, p3, step / samples))
    return path


def path_length(path) -> float:
    return sum(math.dist(path[i + 1], path[i]) for i in range(len(path) - 1))


def arc_lengths(path) -> list[float]:
    """Cumulative arc length at each sample, starting at zero."""
    out = [0.0]
    for index in range(len(path) - 1):
        out.append(out[-1] + math.dist(path[index + 1], path[index]))
    return out


def nearest_index(path, point) -> int:
    """The sample of `path` closest to `point`. How a module finds its station."""
    best, at = float("inf"), 0
    for index, sample in enumerate(path):
        distance = math.dist(sample, point)
        if distance < best:
            best, at = distance, index
    return at


def resample(path, count: int) -> list[Vec3]:
    """`v2_forms.resample`: `count` samples at equal arc length.

    A Catmull-Rom spline sampled at equal parameter bunches its points where
    the control polygon is dense. Every downstream quantity in this package -
    collider triangle size, bank smoothing, the arc position a module is
    anchored at - assumes even spacing, so this runs first.
    """
    if len(path) < 2 or count < 2:
        return list(path)
    lengths = arc_lengths(path)
    total = lengths[-1]
    out: list[Vec3] = []
    cursor = 0
    for step in range(count):
        want = total * step / (count - 1)
        while cursor < len(lengths) - 2 and lengths[cursor + 1] < want:
            cursor += 1
        a, b = lengths[cursor], lengths[cursor + 1]
        t = 0.0 if b - a < 1e-9 else (want - a) / (b - a)
        out.append(_lerp(path[cursor], path[cursor + 1], t))
    return out


def flat_tangents(path) -> list[Vec3]:
    """Unit forward per sample, in full 3D including the gradient."""
    out: list[Vec3] = []
    for index in range(len(path)):
        before = path[max(index - 1, 0)]
        after = path[min(index + 1, len(path) - 1)]
        forward = _sub(after, before)
        if forward[0] ** 2 + forward[1] ** 2 + forward[2] ** 2 < 1e-12:
            forward = (0.0, 0.0, 1.0)
        out.append(_norm(forward))
    return out


def curvature(path) -> list[float]:
    """Signed horizontal curvature per sample. Plan view only, on purpose."""
    out: list[float] = []
    for index in range(len(path)):
        a = path[max(index - 1, 0)]
        b = path[index]
        c = path[min(index + 1, len(path) - 1)]
        v0 = (b[0] - a[0], 0.0, b[2] - a[2])
        v1 = (c[0] - b[0], 0.0, c[2] - b[2])
        l0 = math.hypot(v0[0], v0[2])
        l1 = math.hypot(v1[0], v1[2])
        if l0 < 1e-6 or l1 < 1e-6:
            out.append(0.0)
            continue
        v0 = (v0[0] / l0, 0.0, v0[2] / l0)
        v1 = (v1[0] / l1, 0.0, v1[2] / l1)
        turn = v0[2] * v1[0] - v0[0] * v1[2]
        out.append(-turn / max((l0 + l1) * 0.5, 1e-4))
    return out


def smooth_series(values, passes: int = 3) -> list[float]:
    """Box-blur a per-sample series, so a bank angle has no step in it."""
    current = list(values)
    for _ in range(passes):
        nxt = []
        for index in range(len(current)):
            a = current[max(index - 1, 0)]
            b = current[index]
            c = current[min(index + 1, len(current) - 1)]
            nxt.append((a + b + c) / 3.0)
        current = nxt
    return current


def auto_bank(
    path, gain: float, max_degrees: float, ease_ends: int = BANK_EASE_ENDS
) -> list[float]:
    """A bank angle in radians per sample, from the path's own curvature."""
    limit = math.radians(max_degrees)
    raw = [min(limit, max(-limit, k * gain)) for k in curvature(path)]
    banks = smooth_series(raw, 4)
    count = len(banks)
    divisor = max(ease_ends, 1)
    for index in range(count):
        from_start = index / divisor
        from_end = (count - 1 - index) / divisor
        ease = min(1.0, max(0.0, min(from_start, from_end)))
        banks[index] = banks[index] * _smoothstep(0.0, 1.0, ease)
    return banks


def banked_basis(tangents, banks, index: int) -> tuple[Vec3, Vec3, Vec3]:
    """The rolled frame at one sample, as (lateral, up, forward).

    `v2_forms.banked_basis` recomputes the tangents on every call; they are
    passed in here instead, because this runs once per section point per sample
    and the result is identical.
    """
    forward = tangents[min(max(index, 0), len(tangents) - 1)]
    side = (forward[2], 0.0, -forward[0])
    if side[0] ** 2 + side[2] ** 2 < 1e-12:
        side = (1.0, 0.0, 0.0)
    side = _norm(side)
    up = _norm(_cross(forward, side))
    roll = banks[min(max(index, 0), len(banks) - 1)] if banks else 0.0
    cos_roll, sin_roll = math.cos(roll), math.sin(roll)
    lateral = _add(_mul(side, cos_roll), _mul(up, sin_roll))
    rolled_up = _sub(_mul(up, cos_roll), _mul(side, sin_roll))
    return (lateral, rolled_up, forward)


def width_curve(count: int, entry_flare: float = 0.14, exit_flare: float = 0.09) -> list[float]:
    """`v2_track.width_curve`: lateral scale per sample.

    Flared at the throat and the mouth, pinched a little through the middle.
    Carried into the collider because ignoring it would put the physical wall
    5.5% of a half-width *outside* the visible wall through the waist of every
    run, which is a marble visibly clipping a lip.
    """
    out: list[float] = []
    for index in range(count):
        t = index / max(count - 1, 1)
        entry = entry_flare * pow(min(1.0, max(0.0, 1.0 - t / 0.16)), 2.5)
        leaving = exit_flare * pow(min(1.0, max(0.0, (t - 0.84) / 0.16)), 2.2)
        waist = -0.055 * math.sin(min(1.0, max(0.0, (t - 0.18) / 0.62)) * math.pi)
        out.append(1.0 + entry + leaving + waist)
    return out


def build_path(controls, bank_gain: float, bank_max: float, samples: int = TRACK_SAMPLES):
    """One run's geometry, exactly as `v2_track.build` computes it.

    Returns `(path, banks, tangents, widths)`, all in layout units, all
    `samples` long.
    """
    path = resample(smooth_path(controls, SPLINE_SAMPLES), samples)
    banks = auto_bank(path, bank_gain, bank_max)
    tangents = flat_tangents(path)
    widths = width_curve(len(path))
    return path, banks, tangents, widths
