"""The hardening study, run as one command.

    python -m tools.marble3d_hardening --all --report

Every number in `docs/marble3d_physics_hardening.md` comes out of here rather
than being typed, the same way `tools/marble3d_validate.py` backs the core
document. The sections are ordered as the investigation actually went, because
each one only makes sense given the answer to the one before it:

  --floors        Is the dissipation in the collider or in the solver? One
                  marble rolling on an analytic half-space, an analytic box and
                  five level triangle meshes of different resolutions. The
                  analytic surfaces are the control: they have no edges, so
                  whatever they lose is the solver's doing and whatever they do
                  not lose is not.
  --rates         The rate matrix, on one marble in a bare bowl. Reproduces the
                  production report's rate sensitivity without the start
                  module, the queue, the collisions or the curve in the way.
  --tessellation  Sagitta budget and meridian spacing, at three rates.
  --solver        Every solver knob PyBullet exposes and this package does not
                  set, one at a time, scored by how much of the rate
                  sensitivity it removes.
  --resistance    The explicit rolling-resistance and exponential-decay models:
                  calibration first, then rate convergence.
  --candidates    Whole-machine comparison of the survivors against the 240 Hz
                  baseline, over several seeds.
  --throughput    Seeds per second at 8, 16, 32 and 64 marbles, per candidate.
  --determinism   In-process and child-process digest agreement, per candidate.

## The one number the whole study is scored on

`spread` is `max(turns) / min(turns)` across 120, 240 and 480 Hz on the same
configuration. A physical model integrated more finely would give the same
answer, so a converged model has `spread = 1`. The production baseline is about
2.0, and a candidate is only interesting if it gets substantially closer to 1
without spoiling anything else.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time
from dataclasses import replace
from typing import Any, Callable, Sequence

from marble3d.config import DEFAULT_CONFIG, CoreConfig
from marble3d.dissipation import (
    FLOORS,
    floor_edge,
    machine_with_sagitta,
    measure_floor,
    orbit_sweep,
    summarise_orbits,
)
from marble3d.hardening import HardeningConfig, ResistanceConfig, SolverConfig
from marble3d.metrics import summarise
from marble3d.modules.bowl import BowlModule, BowlSpec
from marble3d.simulation import environment_metadata, simulate
from marble3d.units import GRAVITY, MARBLE_RADIUS

DEFAULT_REPORT = os.path.join("docs", "validation", "marble3d", "hardening_study.json")

# The three rates the brief names. 960 is measured where it is cheap and is
# never a production candidate; 1920 is measured once, to record the cliff, and
# is excluded from every score.
RATES = (120, 240, 480)
WIDE_RATES = (120, 240, 480, 960)
SEEDS = (7, 11, 19, 23, 31)


def _header(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


def _median(values: Sequence[float]) -> float:
    return statistics.median(values) if values else 0.0


def spread(values: Sequence[float]) -> float:
    """`max / min`, the rate-convergence score. 1.0 is converged."""
    usable = [value for value in values if value > 1e-9]
    if len(usable) < 2:
        return math.inf
    return max(usable) / min(usable)


# --- variants -------------------------------------------------------------


def at_rate(config: CoreConfig, hz: int) -> CoreConfig:
    return config.with_overrides(physics__physics_hz=hz)


def with_solver(config: CoreConfig, **fields: Any) -> CoreConfig:
    hardening = config.hardening
    return config.with_overrides(
        hardening=replace(hardening, solver=replace(hardening.solver, **fields))
    )


def with_resistance(config: CoreConfig, **fields: Any) -> CoreConfig:
    hardening = config.hardening
    return config.with_overrides(
        hardening=replace(hardening, resistance=replace(hardening.resistance, **fields))
    )


# One name, one transformation, one reason. Written as a list rather than a
# dict so the report preserves the order the study ran them in.
Variant = tuple[str, Callable[[CoreConfig], CoreConfig], str]

SOLVER_VARIANTS: list[Variant] = [
    ("baseline", lambda c: c, "production, unchanged"),
    (
        "restitution=0",
        lambda c: c.with_overrides(marble__surface_restitution=0.0),
        "no bounce off the track at all: does the loss survive without restitution?",
    ),
    (
        "restitution=0.60",
        lambda c: c.with_overrides(marble__surface_restitution=0.60),
        "a bouncier track, to see which way restitution moves the loss",
    ),
    (
        "restitution_threshold=5",
        lambda c: with_solver(c, restitution_velocity_threshold=5.0),
        "suppress restitution below 5 wu/s, above g*dt at every rate in the matrix",
    ),
    (
        "restitution_threshold=0.01",
        lambda c: with_solver(c, restitution_velocity_threshold=0.01),
        "the opposite: apply restitution to everything, at every rate",
    ),
    (
        "break_threshold=0.002",
        lambda c: c.with_overrides(physics__contact_breaking_threshold=0.002),
        "a tenth of the manifold's persistence distance: fewer stale points",
    ),
    (
        "break_threshold=0.10",
        lambda c: c.with_overrides(physics__contact_breaking_threshold=0.10),
        "five times it: more stale points, held longer",
    ),
    (
        "iterations=10",
        lambda c: c.with_overrides(physics__solver_iterations=10),
        "a quarter of production's 40",
    ),
    (
        "iterations=150",
        lambda c: c.with_overrides(physics__solver_iterations=150),
        "nearly four times it; is 40 already converged?",
    ),
    (
        "no_split_impulse",
        lambda c: c.with_overrides(physics__split_impulse=False),
        "penetration recovery through Baumgarte only, which can inject energy",
    ),
    (
        "split_threshold=-0.001",
        lambda c: with_solver(c, split_impulse_penetration_threshold=-0.001),
        "send almost every penetration down the split-impulse path",
    ),
    (
        "erp=0.8",
        lambda c: with_solver(c, erp=0.8, contact_erp=0.8),
        "four times the default error reduction",
    ),
    (
        "erp=0.05",
        lambda c: with_solver(c, erp=0.05, contact_erp=0.05),
        "a quarter of it",
    ),
    (
        "cfm=1e-5",
        lambda c: with_solver(c, global_cfm=1e-5),
        "a softer constraint",
    ),
    (
        "no_warm_start",
        lambda c: with_solver(c, warm_starting_factor=0.0),
        "no impulse carried between steps",
    ),
    (
        "no_cone_friction",
        lambda c: with_solver(c, cone_friction=False),
        "box friction instead of the friction cone",
    ),
    (
        "no_internal_edge",
        lambda c: with_solver(c, internal_edge=False),
        "drop GEOM_CONCAVE_INTERNAL_EDGE: does the flag do anything on this build?",
    ),
    (
        "margin=0.04",
        lambda c: c.with_overrides(collider__mesh_margin=0.04),
        "Bullet's own default mesh margin instead of this package's 0.001",
    ),
    (
        "margin=0.0",
        lambda c: c.with_overrides(collider__mesh_margin=0.0),
        "no mesh margin at all",
    ),
    (
        "substeps=4",
        lambda c: with_solver(c, sub_steps=4),
        "integrate four times finer than the tick, with the tick unchanged",
    ),
]


# name, config, bowl sagitta, why. Each is a *hypothesis about the machine*
# rather than a set of numbers that happened to work, and each keeps the outer
# tick - and therefore the replay's clock, the actuator poses and every event
# timestamp - at the production 240 Hz.
def candidate_configs() -> list[tuple[str, CoreConfig, float, str]]:
    base = DEFAULT_CONFIG
    return [
        ("baseline_240", at_rate(base, 240), 0.02, "production, unchanged"),
        (
            "cheap_240",
            at_rate(
                with_resistance(
                    base.with_overrides(physics__contact_breaking_threshold=0.005),
                    model="rolling", crr=0.04,
                ),
                240,
            ),
            0.02,
            "one solver number and one physical coefficient; same collider, same cost",
        ),
        (
            "coarse_240",
            at_rate(
                with_resistance(
                    base.with_overrides(physics__contact_breaking_threshold=0.005),
                    model="rolling", crr=0.06,
                ),
                240,
            ),
            0.08,
            "the same, on a four-times-coarser bowl collider: fewer edges to cross",
        ),
        (
            "substepped_240",
            at_rate(
                with_resistance(
                    with_solver(
                        base.with_overrides(physics__contact_breaking_threshold=0.002),
                        sub_steps=2,
                    ),
                    model="rolling", crr=0.12,
                ),
                240,
            ),
            0.02,
            "integrate at 480 Hz inside a 240 Hz tick, with the loss supplied explicitly",
        ),
        (
            "exponential_240",
            at_rate(
                with_resistance(
                    base.with_overrides(physics__contact_breaking_threshold=0.005),
                    model="exponential", linear_rate=0.40, angular_rate=0.40,
                ),
                240,
            ),
            0.02,
            "the exactly rate-independent law instead of the Coulomb one",
        ),
    ]


# --- sections -------------------------------------------------------------


def section_floors(rates: Sequence[int] = (120, 240, 480, 960, 1920)) -> dict[str, Any]:
    """Is the loss in the collider or in the solver? One marble, level surfaces."""
    _header("Dissipation floor: one marble rolling on a level surface")
    print("  Crr = a/g, with every rolling, spinning and damping term at zero.")
    print("  A real glass marble on a hard track measures 0.001 to 0.002.\n")
    print(f"  {'surface':12} {'edge':>7} " + " ".join(f"{hz:>9}" for hz in rates))
    rows = []
    for floor in FLOORS:
        measured = []
        for hz in rates:
            result = measure_floor(floor, at_rate(DEFAULT_CONFIG, hz), seconds=4.0)
            measured.append(result)
        rows.append(
            {
                "floor": floor,
                "edge": floor_edge(floor),
                "rates": [r.to_json() for r in measured],
            }
        )
        print(
            f"  {floor:12} {floor_edge(floor):7.3f} "
            + " ".join(f"{r.crr:9.5f}" for r in measured)
        )
    print("\n  contact fraction (1.0 = never leaves the surface)")
    print(f"  {'surface':12} {'':7} " + " ".join(f"{hz:>9}" for hz in rates))
    for row in rows:
        print(
            f"  {row['floor']:12} {'':7} "
            + " ".join(f"{r['contact_fraction']:9.3f}" for r in row["rates"])
        )
    return {"rates": list(rates), "surfaces": rows}


def section_rates(
    rates: Sequence[int] = (120, 240, 480, 960, 1920), phases: int = 4
) -> dict[str, Any]:
    """The rate matrix on the isolated bowl, which is the study's reference curve."""
    _header("Rate matrix: one marble, one bowl, nothing else in the world")
    print(f"  {'hz':>5} {'turns':>7} {'range':>13} {'secs':>7} {'k':>7} {'Crr_eq':>8} "
          f"{'dr/dt':>7} {'contact':>8} {'pen':>8} {'wall':>7}  outcome")
    rows = []
    for hz in rates:
        summary = summarise_orbits(orbit_sweep(at_rate(DEFAULT_CONFIG, hz), phases=phases))
        rows.append(summary)
        print(
            f"  {hz:5} {summary['turns']:7.2f} "
            f"{summary['turns_min']:6.2f}-{summary['turns_max']:6.2f} "
            f"{summary['seconds']:7.2f} {summary['energy_decay']:7.4f} "
            f"{summary['equivalent_crr']:8.5f} {summary['radial_rate']:7.3f} "
            f"{summary['contact_fraction']:8.3f} {summary['worst_penetration']:8.4f} "
            f"{summary['wall_seconds']:7.2f}  {','.join(summary['outcomes'])}"
        )
    scored = [row for row in rows if row["physics_hz"] in RATES]
    turns_spread = spread([row["turns"] for row in scored])
    crr_spread = spread([row["equivalent_crr"] for row in scored])
    print(f"\n  spread over {RATES}: turns x{turns_spread:.2f}, Crr_eq x{crr_spread:.2f}")
    print("  g*dt against Bullet's 0.2 restitution velocity threshold:")
    for hz in rates:
        marker = "  <- below the threshold" if GRAVITY / hz < 0.2 else ""
        print(f"    {hz:5} Hz   g*dt = {GRAVITY / hz:6.3f} wu/s{marker}")
    return {
        "rows": rows,
        "turns_spread": turns_spread,
        "crr_spread": crr_spread,
        "g_dt": {str(hz): GRAVITY / hz for hz in rates},
    }


def section_tessellation(
    sagittas: Sequence[float] = (0.005, 0.01, 0.02, 0.04, 0.08),
    ring_steps: Sequence[float] = (0.25, 0.5, 1.0, 2.0),
    rates: Sequence[int] = RATES,
    phases: int = 2,
) -> dict[str, Any]:
    """Does collider resolution change the loss, and does it change its rate slope?"""
    _header("Bowl tessellation")
    print("  sagitta is the chord error of the circumferential tessellation;")
    print("  ring_step is the meridian spacing. Both change the number of")
    print("  triangle edges a marble crosses per revolution.\n")
    print(f"  {'sagitta':>8} {'/radius':>8} {'segments':>9} {'tris':>7} "
          + " ".join(f"{hz:>7}" for hz in rates) + f" {'spread':>7}")
    circumferential = []
    from marble3d.modules.bowl import BowlModule

    for sagitta in sagittas:
        bowl = BowlModule("bowl", BowlSpec(), sagitta_limit=sagitta)
        triangles = sum(mesh.triangle_count for mesh in bowl.local_colliders())
        turns = []
        for hz in rates:
            summary = summarise_orbits(
                orbit_sweep(at_rate(DEFAULT_CONFIG, hz), sagitta_limit=sagitta, phases=phases)
            )
            turns.append(summary)
        circumferential.append(
            {
                "sagitta": sagitta,
                "over_marble_radius": sagitta / MARBLE_RADIUS,
                "segments": bowl.segments,
                "triangles": triangles,
                "rates": turns,
                "spread": spread([row["turns"] for row in turns]),
            }
        )
        print(
            f"  {sagitta:8.3f} {sagitta / MARBLE_RADIUS:8.3f} {bowl.segments:9} "
            f"{triangles:7} " + " ".join(f"{row['turns']:7.2f}" for row in turns)
            + f" {circumferential[-1]['spread']:7.2f}"
        )

    print(f"\n  {'ring_step':>9} {'rings':>7} {'tris':>7} "
          + " ".join(f"{hz:>7}" for hz in rates) + f" {'spread':>7}")
    meridian = []
    for step in ring_steps:
        spec = BowlSpec(ring_step=step)
        bowl = BowlModule("bowl", spec)
        triangles = sum(mesh.triangle_count for mesh in bowl.local_colliders())
        turns = []
        for hz in rates:
            summary = summarise_orbits(
                orbit_sweep(at_rate(DEFAULT_CONFIG, hz), spec=spec, phases=phases)
            )
            turns.append(summary)
        rings = triangles // (2 * bowl.segments)
        meridian.append(
            {
                "ring_step": step,
                "rings": rings,
                "triangles": triangles,
                "rates": turns,
                "spread": spread([row["turns"] for row in turns]),
            }
        )
        print(
            f"  {step:9.3f} {rings:7} {triangles:7} "
            + " ".join(f"{row['turns']:7.2f}" for row in turns)
            + f" {meridian[-1]['spread']:7.2f}"
        )
    return {"circumferential": circumferential, "meridian": meridian}


def section_solver(rates: Sequence[int] = RATES, phases: int = 2) -> dict[str, Any]:
    """Every exposed solver knob, one at a time, scored on rate convergence."""
    _header("Solver settings, one at a time")
    print(f"  {'variant':26} " + " ".join(f"{hz:>7}" for hz in rates)
          + f" {'spread':>7} {'Crr@240':>8}  reason")
    rows = []
    for name, transform, reason in SOLVER_VARIANTS:
        turns = []
        for hz in rates:
            try:
                summary = summarise_orbits(orbit_sweep(transform(at_rate(DEFAULT_CONFIG, hz)),
                                                       phases=phases))
            except Exception as error:  # a knob this build rejects is a finding
                summary = {"turns": 0.0, "equivalent_crr": 0.0, "error": str(error)}
            turns.append(summary)
        row = {
            "variant": name,
            "reason": reason,
            "rates": turns,
            "spread": spread([entry["turns"] for entry in turns]),
        }
        rows.append(row)
        at240 = next(
            (entry for entry, hz in zip(turns, rates) if hz == 240), turns[0]
        )
        print(
            f"  {name:26} " + " ".join(f"{entry['turns']:7.2f}" for entry in turns)
            + f" {row['spread']:7.2f} {at240.get('equivalent_crr', 0.0):8.5f}  {reason}"
        )
    return {"rates": list(rates), "variants": rows}


def section_resistance(
    rates: Sequence[int] = WIDE_RATES, phases: int = 2
) -> dict[str, Any]:
    """The explicit models: does a rate-independent loss give rate-independent motion?"""
    _header("Explicit resistance models")

    print("  Calibration on the flat rig: what a stated coefficient actually costs.")
    print(f"  {'model':28} " + " ".join(f"{hz:>9}" for hz in rates))
    calibration = []
    flat_variants: list[tuple[str, Callable[[CoreConfig], CoreConfig]]] = [
        ("off", lambda c: c),
        ("rolling crr=0.002", lambda c: with_resistance(c, model="rolling", crr=0.002)),
        ("rolling crr=0.010", lambda c: with_resistance(c, model="rolling", crr=0.010)),
        ("rolling crr=0.030", lambda c: with_resistance(c, model="rolling", crr=0.030)),
        (
            "exponential k=0.35",
            lambda c: with_resistance(c, model="exponential", linear_rate=0.35, angular_rate=0.35),
        ),
    ]
    for name, transform in flat_variants:
        measured = [
            measure_floor("plane", transform(at_rate(DEFAULT_CONFIG, hz)), seconds=4.0)
            for hz in rates
        ]
        calibration.append({"model": name, "rates": [m.to_json() for m in measured]})
        print(f"  {name:28} " + " ".join(f"{m.crr:9.5f}" for m in measured))
    print("  (on the analytic plane, so the only loss present is the model's own)")

    print(f"\n  Bowl, {rates}:")
    print(f"  {'model':28} " + " ".join(f"{hz:>7}" for hz in rates) + f" {'spread':>7}")
    bowl_variants: list[tuple[str, Callable[[CoreConfig], CoreConfig]]] = [
        ("off (baseline)", lambda c: c),
        ("rolling crr=0.010", lambda c: with_resistance(c, model="rolling", crr=0.010)),
        ("rolling crr=0.030", lambda c: with_resistance(c, model="rolling", crr=0.030)),
        ("rolling crr=0.060", lambda c: with_resistance(c, model="rolling", crr=0.060)),
        (
            "exponential k=0.20",
            lambda c: with_resistance(c, model="exponential", linear_rate=0.20, angular_rate=0.20),
        ),
        (
            "exponential k=0.35",
            lambda c: with_resistance(c, model="exponential", linear_rate=0.35, angular_rate=0.35),
        ),
        (
            "exponential k=0.60",
            lambda c: with_resistance(c, model="exponential", linear_rate=0.60, angular_rate=0.60),
        ),
    ]
    bowl = []
    for name, transform in bowl_variants:
        turns = [
            summarise_orbits(orbit_sweep(transform(at_rate(DEFAULT_CONFIG, hz)), phases=phases))
            for hz in rates
        ]
        scored = [row for row, hz in zip(turns, rates) if hz in RATES]
        row = {
            "model": name,
            "rates": turns,
            "spread": spread([entry["turns"] for entry in scored]),
        }
        bowl.append(row)
        print(
            f"  {name:28} " + " ".join(f"{entry['turns']:7.2f}" for entry in turns)
            + f" {row['spread']:7.2f}"
        )
    return {"rates": list(rates), "calibration": calibration, "bowl": bowl}


def section_breaking(
    thresholds: Sequence[float] = (0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.10),
    rates: Sequence[int] = RATES,
    phases: int = 2,
) -> dict[str, Any]:
    """The contact breaking threshold, which turns out to be the whole story.

    Bullet keeps a persistent manifold per pair and adds a contact point as soon
    as a feature is within `contactBreakingThreshold` of the body, holding it
    until it drifts further away than that. On a triangle mesh that means a
    rolling marble is in contact with the triangle it is on *and* with the
    neighbours it has not reached yet, each contributing its own normal impulse
    from its own face normal. Production sets 0.02 - Bullet's default, chosen
    for metre-scale objects, and a marble is one unit across so the scale is
    right - and 0.02 wu is twenty times the 0.001 mesh margin the core report
    solved for. The margin is not what decides how early a contact appears.
    This is.
    """
    _header("Contact breaking threshold")
    print("  How far from a surface Bullet still generates and keeps a contact.")
    print("  Production is 0.02 wu, which is 4% of a marble radius and 20x the")
    print("  0.001 mesh margin the core report chose.\n")
    print(f"  {'threshold':>10} {'/radius':>8} " + " ".join(f"{hz:>7}" for hz in rates)
          + f" {'spread':>7} {'Crr@240':>8} {'pen@240':>8} {'contacts':>9} {'rise@240':>9}")
    rows = []
    for threshold in thresholds:
        turns = []
        for hz in rates:
            summary = summarise_orbits(
                orbit_sweep(
                    at_rate(DEFAULT_CONFIG, hz).with_overrides(
                        physics__contact_breaking_threshold=threshold
                    ),
                    phases=phases,
                )
            )
            turns.append(summary)
        at240 = next((entry for entry, hz in zip(turns, rates) if hz == 240), turns[0])
        # A threshold small enough to break the contact every step would show up
        # as a marble that is airborne a lot and a machine that gains energy, so
        # both are carried rather than only the headline number.
        machine = _whole_machine(
            f"cbt={threshold}",
            DEFAULT_CONFIG.with_overrides(physics__contact_breaking_threshold=threshold),
            (7,),
        )
        row = {
            "threshold": threshold,
            "over_marble_radius": threshold / MARBLE_RADIUS,
            "rates": turns,
            "spread": spread([entry["turns"] for entry in turns]),
            "whole_machine": machine,
        }
        rows.append(row)
        print(
            f"  {threshold:10.4f} {threshold / MARBLE_RADIUS:8.4f} "
            + " ".join(f"{entry['turns']:7.2f}" for entry in turns)
            + f" {row['spread']:7.2f} {at240['equivalent_crr']:8.5f} "
            f"{at240['worst_penetration']:8.4f} {at240['contact_fraction']:9.3f} "
            f"{machine['max_energy_rise']:9.2e}"
        )
        for failure in machine["failures"]:
            print(f"      whole machine at 240 Hz: {failure}")
    return {"rates": list(rates), "rows": rows}


def section_combined(rates: Sequence[int] = RATES, phases: int = 2) -> dict[str, Any]:
    """Suppress the numerical loss, then put a physical one back, and see if it converges.

    The two halves of the recommendation, measured together, because neither
    works alone: suppressing the numerical dissipation alone gives a bowl that
    does not contain marbles, and adding a physical coefficient alone is
    inaudible under a numerical one three times its size.
    """
    _header("Suppress the numerical loss, restore a physical one")
    suppressors: list[tuple[str, Callable[[CoreConfig], CoreConfig]]] = [
        ("none", lambda c: c),
        ("cbt=0.002", lambda c: c.with_overrides(physics__contact_breaking_threshold=0.002)),
        ("cbt=0.005", lambda c: c.with_overrides(physics__contact_breaking_threshold=0.005)),
        ("sagitta=0.08", lambda c: c),
        ("substeps=4", lambda c: with_solver(c, sub_steps=4)),
        (
            "cbt=0.002+substeps=4",
            lambda c: with_solver(
                c.with_overrides(physics__contact_breaking_threshold=0.002), sub_steps=4
            ),
        ),
    ]
    coefficients = (0.0, 0.02, 0.05, 0.10, 0.20)
    print(f"  {'suppressor':22} {'crr':>6} " + " ".join(f"{hz:>7}" for hz in rates)
          + f" {'spread':>7} {'Crr_eq@240':>11}")
    rows = []
    for name, transform in suppressors:
        sagitta = 0.08 if name == "sagitta=0.08" else 0.02
        for crr in coefficients:
            turns = []
            for hz in rates:
                config = transform(at_rate(DEFAULT_CONFIG, hz))
                if crr:
                    config = with_resistance(config, model="rolling", crr=crr)
                turns.append(
                    summarise_orbits(
                        orbit_sweep(config, sagitta_limit=sagitta, phases=phases)
                    )
                )
            at240 = next((entry for entry, hz in zip(turns, rates) if hz == 240), turns[0])
            row = {
                "suppressor": name,
                "sagitta": sagitta,
                "crr": crr,
                "rates": turns,
                "spread": spread([entry["turns"] for entry in turns]),
                "turns_240": at240["turns"],
                "crr_eq_240": at240["equivalent_crr"],
            }
            rows.append(row)
            print(
                f"  {name:22} {crr:6.3f} "
                + " ".join(f"{entry['turns']:7.2f}" for entry in turns)
                + f" {row['spread']:7.2f} {at240['equivalent_crr']:11.5f}"
            )
    # A candidate has to be believable as well as converged: the production bowl
    # is three revolutions, so anything far from it is a different machine.
    plausible = [row for row in rows if 2.2 <= row["turns_240"] <= 4.0]
    plausible.sort(key=lambda row: row["spread"])
    print("\n  best rate convergence among configurations that keep 2.2 to 4.0 turns at 240 Hz:")
    for row in plausible[:6]:
        print(f"    spread {row['spread']:5.2f}  turns@240 {row['turns_240']:5.2f}  "
              f"{row['suppressor']} + crr {row['crr']}")
    return {"rates": list(rates), "rows": rows, "ranked": plausible[:10]}


def _whole_machine(
    name: str, config: CoreConfig, seeds: Sequence[int], sagitta: float = 0.02
) -> dict[str, Any]:
    rows = []
    for seed in seeds:
        replay = simulate(seed=seed, machine=machine_with_sagitta(sagitta), config=config)
        rows.append(summarise(replay))
    return {
        "candidate": name,
        "physics_hz": config.physics.physics_hz,
        "sagitta": sagitta,
        "seeds": list(seeds),
        "revolutions_median": _median([row["revolutions_median"] for row in rows]),
        "revolutions_min": min(row["revolutions_min"] for row in rows),
        "revolutions_max": max(row["revolutions_max"] for row in rows),
        "sim_seconds": _median([row["sim_seconds"] for row in rows]),
        "wall_seconds": _median([row["wall_seconds"] for row in rows]),
        "collisions": _median([row["collisions"] for row in rows]),
        "top_speed": max(row["top_speed"] for row in rows),
        "worst_penetration": min(row["worst_penetration"] for row in rows),
        "max_energy_rise": max(row["max_energy_rise"] for row in rows),
        "finished": sum(row["finished"] for row in rows),
        "escaped": sum(row["escaped"] for row in rows),
        "unfinished": sum(row["unfinished"] for row in rows),
        "distinct_orders": len({tuple(row["finish_order"]) for row in rows}),
        "failures": [row["failure"] for row in rows if row["failure"]],
        "rows": rows,
    }


def section_candidates(
    seeds: Sequence[int] = SEEDS, rates: Sequence[int] = RATES
) -> dict[str, Any]:
    """The survivors against the baseline, on the whole machine, at all three rates.

    This is the deliverable the brief asks for and the orbit rig cannot give:
    the isolated bowl is the right instrument for finding out *why*, but the
    thing that has to remain believable, finish, not jam and not escape is the
    whole machine with eight marbles in it.
    """
    _header("Whole machine: candidates against the 240 Hz baseline")
    print(f"  {'candidate':16} {'hz':>4} {'turns':>7} {'range':>13} {'run':>6} "
          f"{'wall':>6} {'coll':>5} {'fin':>4} {'esc':>4} {'orders':>7} {'pen':>8} {'rise':>9}")
    rows = []
    for name, config, sagitta, reason in candidate_configs():
        per_rate = []
        for hz in rates:
            row = _whole_machine(name, at_rate(config, hz), seeds, sagitta)
            row["reason"] = reason
            per_rate.append(row)
            print(
                f"  {name:16} {row['physics_hz']:4} {row['revolutions_median']:7.2f} "
                f"{row['revolutions_min']:6.2f}-{row['revolutions_max']:6.2f} "
                f"{row['sim_seconds']:6.2f} {row['wall_seconds']:6.2f} "
                f"{row['collisions']:5.0f} {row['finished']:4} {row['escaped']:4} "
                f"{row['distinct_orders']:7} {row['worst_penetration']:8.4f} "
                f"{row['max_energy_rise']:9.2e}"
            )
            for failure in row["failures"]:
                print(f"      FAILURE: {failure}")
        rate_spread = spread([row["revolutions_median"] for row in per_rate])
        rows.append(
            {
                "candidate": name,
                "reason": reason,
                "sagitta": sagitta,
                "rates": per_rate,
                "spread": rate_spread,
                "config": config.to_json(),
            }
        )
        print(f"  {'':16} {'':4} spread over {tuple(rates)}: x{rate_spread:.2f}\n")
    print("  ranked by rate convergence, among candidates that keep every marble:")
    clean = [row for row in rows
             if all(entry["escaped"] == 0 and not entry["failures"] for entry in row["rates"])]
    for row in sorted(clean, key=lambda row: row["spread"]):
        at240 = next(entry for entry in row["rates"] if entry["physics_hz"] == 240)
        print(f"    spread {row['spread']:5.2f}  turns@240 {at240['revolutions_median']:5.2f}  "
              f"wall {at240['wall_seconds']:5.2f}s  {row['candidate']}")
    return {"seeds": list(seeds), "rates": list(rates), "candidates": rows}


def section_throughput(counts: Sequence[int] = (8, 16, 32, 64)) -> dict[str, Any]:
    """Seeds per second per candidate, at the field sizes a search actually uses."""
    from marble3d.modules.start import StartSpec

    _header("Throughput")

    def factory(count: int, sagitta: float):
        # The same widening `tools/marble3d_validate.py` uses, so this table and
        # the core report's throughput table are the same benchmark: a longer
        # chute for a longer queue, with the shelf slope scaled inversely so the
        # field's entry-speed spread does not grow with the field.
        base = StartSpec()
        return machine_with_sagitta(
            sagitta,
            StartSpec(
                marble_count=count,
                length=base.gate_offset + count * base.marble_spacing + 4.0,
                shelf_slope=base.shelf_slope * base.marble_count / count,
            ),
        )

    print("  wall seconds for one whole run, and how many of the field finished")
    print(f"  {'candidate':16} " + " ".join(f"{str(count) + ' marbles':>14}" for count in counts)
          + f" {'seeds/s':>9}")
    rows = []
    for name, config, sagitta, _ in candidate_configs():
        entries = []
        for count in counts:
            started = time.perf_counter()
            replay = simulate(
                seed=7, machine=factory(count, sagitta), config=config, marble_count=count
            )
            wall = time.perf_counter() - started
            entries.append(
                {
                    "marbles": count,
                    "wall_seconds": wall,
                    "sim_seconds": replay.summary["sim_seconds"],
                    "times_realtime": replay.summary["sim_seconds"] / max(wall, 1e-9),
                    "seeds_per_second": 1.0 / max(wall, 1e-9),
                    "finished": replay.summary["finished"],
                    "escaped": replay.summary["escaped"],
                    "unfinished": replay.summary["unfinished"],
                }
            )
        rows.append({"candidate": name, "counts": entries})
        print(
            f"  {name:16} "
            + " ".join(f"{entry['wall_seconds']:8.2f}s {entry['finished']:>3}/{entry['marbles']:<3}"
                       for entry in entries)
            + f" {entries[0]['seeds_per_second']:9.2f}"
        )
    return {"counts": list(counts), "candidates": rows}


def section_determinism(
    seeds: Sequence[int] = (7, 31), repeats: int = 20
) -> dict[str, Any]:
    """Digest agreement for every candidate, in-process and across processes.

    The cross-process half is the one that matters and it is why this shells out
    to `tools.marble3d_run` rather than looping in this interpreter: a
    same-process repeat shares an allocator, a warm heap and a geometry cache
    with its predecessor and cannot see the failure that actually happens.
    A candidate that carries a resistance model has to be shown to be as
    reproducible as the baseline, because it reads engine state back and feeds
    it forward and that is exactly the kind of term that quietly is not.
    """
    _header(f"Determinism: {repeats} in-process and {repeats} child-process repeats")
    rows = []
    for name, config, sagitta, _ in candidate_configs():
        for seed in seeds:
            same = {
                simulate(
                    seed=seed, machine=machine_with_sagitta(sagitta), config=config
                ).digest()
                for _ in range(repeats)
            }
            arguments = [
                sys.executable, "-m", "tools.marble3d_run",
                "--seed", str(seed), "--digest-only",
                "--hz", str(config.physics.physics_hz),
                "--sagitta", str(sagitta),
                "--break-threshold", str(config.physics.contact_breaking_threshold),
            ]
            if config.hardening.solver.sub_steps:
                arguments += ["--substeps", str(config.hardening.solver.sub_steps)]
            resistance = config.hardening.resistance
            if resistance.active:
                arguments += [
                    "--resistance", resistance.model,
                    "--crr", str(resistance.crr),
                    "--decay", str(resistance.linear_rate),
                ]
            cross = set()
            events = set()
            for _ in range(repeats):
                completed = subprocess.run(
                    arguments, capture_output=True, text=True, check=True,
                    env={**os.environ, "PYTHONPATH": os.getcwd()},
                )
                digest, event_digest, _ = completed.stdout.strip().splitlines()[-1].split(" ", 2)
                cross.add(digest)
                events.add(event_digest)
            agree = len(same | cross) == 1
            rows.append(
                {
                    "candidate": name,
                    "seed": seed,
                    "repeats": repeats,
                    "in_process_digests": len(same),
                    "cross_process_digests": len(cross),
                    "event_digests": len(events),
                    "agree": agree,
                    "digest": sorted(same)[0],
                }
            )
            print(
                f"  {name:20} seed {seed:>3}: {len(same)} in-process, {len(cross)} "
                f"cross-process, {len(events)} event digest(s)"
                + ("" if agree else "   FAIL: more than one trajectory")
            )
    return {"seeds": list(seeds), "repeats": repeats, "rows": rows}


# --- the command ----------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="every section")
    parser.add_argument("--floors", action="store_true")
    parser.add_argument("--rates", action="store_true")
    parser.add_argument("--tessellation", action="store_true")
    parser.add_argument("--solver", action="store_true")
    parser.add_argument("--breaking", action="store_true")
    parser.add_argument("--resistance", action="store_true")
    parser.add_argument("--combined", action="store_true")
    parser.add_argument("--candidates", action="store_true")
    parser.add_argument("--throughput", action="store_true")
    parser.add_argument("--determinism", action="store_true")
    parser.add_argument("--phases", type=int, default=4,
                        help="starting azimuths per orbit configuration")
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--report", nargs="?", const=DEFAULT_REPORT, default=None,
                        help="write the whole thing as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    chosen = {
        "floors": args.floors, "rates": args.rates, "tessellation": args.tessellation,
        "solver": args.solver, "breaking": args.breaking, "resistance": args.resistance,
        "combined": args.combined, "candidates": args.candidates,
        "throughput": args.throughput, "determinism": args.determinism,
    }
    if args.all or not any(chosen.values()):
        chosen = {key: True for key in chosen}

    started = time.perf_counter()
    report: dict[str, Any] = {"environment": environment_metadata()}
    if chosen["floors"]:
        report["floors"] = section_floors()
    if chosen["rates"]:
        report["rates"] = section_rates(phases=args.phases)
    if chosen["tessellation"]:
        report["tessellation"] = section_tessellation(phases=max(2, args.phases // 2))
    if chosen["solver"]:
        report["solver"] = section_solver(phases=max(2, args.phases // 2))
    if chosen["breaking"]:
        report["breaking"] = section_breaking(phases=max(2, args.phases // 2))
    if chosen["resistance"]:
        report["resistance"] = section_resistance(phases=max(2, args.phases // 2))
    if chosen["combined"]:
        report["combined"] = section_combined(phases=max(2, args.phases // 2))
    if chosen["candidates"]:
        report["candidates"] = section_candidates()
    if chosen["throughput"]:
        report["throughput"] = section_throughput()
    if chosen["determinism"]:
        report["determinism"] = section_determinism(repeats=args.repeats)
    report["wall_seconds"] = time.perf_counter() - started

    print(f"\nwhole study: {report['wall_seconds']:.1f} s")
    if args.report:
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=1, sort_keys=True)
            handle.write("\n")
        print(f"report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
