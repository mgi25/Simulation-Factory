"""A seed in, a finished mp4 out: the first join of the 3D core to the visuals.

This is the only place in the project where the physics and the art meet, and
it exists so that the join is *checked* rather than assumed. PyBullet owns
every number that says where something is; Godot owns every number that says
what it looks like. Between them sits one JSON document - the presentation
contract - and most of what this driver does is refuse to render until that
document and the replay agree about the machine.

    python tools/marble3d_integrate.py --seed 1 --marbles 8
    python tools/marble3d_integrate.py --seed 1 --dry-run
    python tools/marble3d_integrate.py --replay output/marble_v1/integration_v1.json
    python tools/marble3d_integrate.py --seed 4 --duration 6 --shots start:0,bowl:40

## Why the contract is written and then argued with

`presentation_for_machine` reads a freshly assembled machine; the replay was
written by a run of a machine assembled the same way. "The same way" is an
assumption, and it is one a changed default spec breaks silently: the symptom
is not an exception, it is an authored bowl drawn a few units from the marbles
that are orbiting it. `check_against_replay` compares the two everywhere they
describe the same thing, and one disagreement stops the render before a single
frame is drawn.

## Why the physics rate is not a flag here

240 Hz is not a quality setting, it is part of the machine's behaviour - change
it and the marbles arrive somewhere else, at a different speed, in a different
order. `tools/marble3d_run.py` has a `--hz` because it is a research tool.
This one produces finished video, so it has no way to ask for a different
machine: the rate comes from `DEFAULT_CONFIG` and nothing on this command line
can reach it.

## Why the cuts come out of the replay

A hard-coded "cut to the bowl at 0.8s" is a number that is right for one seed.
The run already knows when the marbles reached the bowl, because it recorded it
as an event, so `shot_cuts` reads the events and the clip follows the marbles
whatever the seed does. `--shots` overrides it for the day an editor disagrees.

## What is not here

No simulation is ever re-run at render time and no geometry is invented on the
Godot side: Godot is handed the frozen replay and the contract, and draws them.
That is the same rule `tools/render_replay.py` works to, for the same reason -
the moment the renderer re-derives anything, cross-machine determinism is back
on the critical path for shipping a video.

Finding Godot, in order: `--godot`, then `$GODOT_BIN` or `$GODOT4_BIN`, then
the PATH. Same rule as every other render tool here, and no machine-specific
path is committed anywhere in this project.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from marble3d.config import DEFAULT_CONFIG  # noqa: E402
from marble3d.machines import start_bowl_curve  # noqa: E402
from marble3d.presentation import (  # noqa: E402
    CONTRACT_VERSION,
    MachinePresentation,
    check_against_replay,
    presentation_for_machine,
)
from marble3d.contact import ContactReport, check_contact  # noqa: E402
from marble3d.replay import (  # noqa: E402
    MARBLE3D_FORMAT,
    MARBLE3D_VERSION,
    write_replay,
)
from marble3d.simulation import simulate  # noqa: E402
from rendering import png_frames  # noqa: E402
from rendering.render_plan import (  # noqa: E402
    FRAME_DIGITS,
    FRAME_PREFIX,
    FRAME_SUFFIX,
    frame_filename,
    frame_index,
    relative_replay_path,
    sequence_problems,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT_PROJECT = os.path.join(PROJECT_ROOT, "godot")
RENDER_SCENE = "res://scenes/Marble3DRender.tscn"

DEFAULT_OUT_DIR = os.path.join("output", "marble_v1")
DEFAULT_NAME = "integration_v1"
DEFAULT_SEED = 1
DEFAULT_MARBLES = 8

RENDER_WIDTH = 1080
RENDER_HEIGHT = 1920
RENDER_FPS = 60

FRAMES_SUBDIR = "frames"
# One definition of how a frame is named, borrowed from the module that owns
# it, so ffmpeg's input pattern cannot drift from what the checker expects.
FRAME_PATTERN = f"{FRAME_PREFIX}%0{FRAME_DIGITS}d{FRAME_SUFFIX}"

GODOT_ENV_VARS = ("GODOT_BIN", "GODOT4_BIN")
GODOT_ON_PATH = ("godot", "godot4", "Godot_v4.7.2-stable_win64.exe")

# Encode settings. Visually lossless at this resolution and slow enough to
# earn it: this is a hero clip that gets looked at closely, not a daily.
VIDEO_CRF = 16
VIDEO_PRESET = "slow"

# The clip is at most three shots and they are always in this order: the
# marbles are released, they orbit the bowl, they take the curve. The names
# live here rather than being derived from the machine's module list, because
# a cut is a presentation decision - a machine that grows a fourth module
# should not silently grow a fourth shot.
SHOT_START = "start"
SHOT_BOWL = "bowl"
SHOT_CURVE = "curve"
SHOT_NAMES = (SHOT_START, SHOT_BOWL, SHOT_CURVE)

# Which module's arrival cuts to which shot. `start` is absent because it is
# never cut *to*: it is what the clip opens on.
SHOT_MODULES = {SHOT_BOWL: "bowl", SHOT_CURVE: "curve"}

# How far ahead of the arrival the cut lands. A cut on the event itself shows
# the marble already inside the module; a fifth of a second of lead means the
# camera is waiting when the first one gets there.
SHOT_LEAD_SECONDS = 0.20

# No shot shorter than this. Cuts derived from a physical run can land almost
# on top of each other - eight marbles drain within a second of each other -
# and two cuts six frames apart is a glitch, not an edit.
MIN_SHOT_SECONDS = 0.60

MIB = 1024 * 1024


class IntegrationError(RuntimeError):
    """The clip was not produced, or was not produced from what was asked for."""


# --- locating Godot -------------------------------------------------------


def find_godot(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise IntegrationError(f"--godot does not name an executable: {explicit}")

    for variable in GODOT_ENV_VARS:
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value

    for name in GODOT_ON_PATH:
        found = shutil.which(name)
        if found:
            return found

    raise IntegrationError(
        "cannot find Godot 4. Pass --godot PATH, set "
        f"{' or '.join('$' + name for name in GODOT_ENV_VARS)}, or put it on PATH."
    )


def godot_version(godot: str) -> str:
    """The version string the engine reports, for the sidecar.

    Recorded because a render is only reproducible against the engine that
    produced it, and Godot's renderer moves between patch releases. Asked for
    up front rather than after the render: a binary that cannot answer this is
    not one to hand a forty-second job to.
    """
    completed = subprocess.run(
        [godot, "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise IntegrationError(
            f"{godot} --version exited {completed.returncode};"
            " this is not a Godot 4 binary"
        )
    printed = (completed.stdout or "").splitlines()
    lines = [line.strip() for line in printed if line.strip()]
    if not lines:
        raise IntegrationError(f"{godot} --version printed nothing")
    return lines[-1]


# --- the replay -----------------------------------------------------------


def load_replay(path: str) -> dict[str, Any]:
    """One marble3d replay, as the raw document that will be shipped.

    Raw rather than a `Replay`, because the two are not interchangeable here:
    `read_replay` returns the numbers *after* they were rounded for storage,
    and the digest a run is judged on was taken before that. The file is the
    authority, so the file is what is read.
    """
    if not os.path.isfile(path):
        raise IntegrationError(f"no replay at {path}")
    with open(path, "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    if replay.get("format") != MARBLE3D_FORMAT:
        raise IntegrationError(
            f"{path}: format {replay.get('format')!r}, expected {MARBLE3D_FORMAT!r}."
            " The race replay schema is a different file and a different renderer."
        )
    version = int(replay.get("version", 0))
    if version != MARBLE3D_VERSION:
        raise IntegrationError(
            f"{path}: marble3d replay version {version}, this driver plays"
            f" v{MARBLE3D_VERSION}"
        )
    if not replay.get("frames"):
        raise IntegrationError(f"{path}: the replay has no frames")
    return replay


def simulate_replay(seed: int, marbles: int | None, path: str) -> dict[str, Any]:
    """Run one seed, write it, and then read back the file that was written.

    The file and not the object in memory, deliberately. Everything downstream
    - the contract check, the digests in the sidecar, the frames Godot draws -
    has to describe the replay that ships, and the surest way to keep that true
    is to stop using the run the moment it is on disk.

    The physics rate is `DEFAULT_CONFIG`'s and there is no way to change it
    from here; see the module docstring.
    """
    replay = simulate(
        seed=seed,
        machine=start_bowl_curve(),
        config=DEFAULT_CONFIG,
        marble_count=marbles,
    )
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    write_replay(replay, path)
    return load_replay(path)


def default_replay_path(out_dir: str, name: str) -> str:
    return os.path.join(out_dir, f"{name}.json")


def contract_path_for(replay_path: str) -> str:
    """The contract sits beside its replay and is named after it.

    Two files that only mean anything together should be impossible to
    separate by accident, and a shared stem is how the rest of this project
    says so.
    """
    return f"{os.path.splitext(replay_path)[0]}.contract.json"


# --- the contract ---------------------------------------------------------


def build_contract(replay: dict[str, Any]) -> MachinePresentation:
    """The presentation contract for the machine this replay was run on.

    The marble radius comes out of the replay rather than out of the config,
    because the contract has to describe the run that happened. They are the
    same number today; the day they are not, the renderer should size its
    marbles like the solver did, not like the defaults say.
    """
    marbles = replay.get("marbles") or []
    radius = float(marbles[0]["radius"]) if marbles else DEFAULT_CONFIG.marble.radius
    return presentation_for_machine(start_bowl_curve(), radius)


def write_contract(
    presentation: MachinePresentation, replay: dict[str, Any], path: str
) -> str:
    """Check the contract against the replay, then write it. Never the reverse.

    A contract that disagrees with the replay would place authored geometry
    where the marbles are not, and it is cheaper to find that out here than in
    a frame. Written indented because it is read by people at least as often
    as by Godot, and its size is measured in tens of kilobytes either way.
    """
    problems = check_against_replay(presentation, replay)
    if problems:
        raise IntegrationError(
            "the contract and the replay describe different machines:\n    "
            + "\n    ".join(problems)
        )
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(presentation.to_json(), handle, indent=1)
        handle.write("\n")
    return path


def check_marble_contact(
    replay: dict[str, Any], presentation: MachinePresentation
) -> ContactReport:
    """Where every marble is, against the surface that will be drawn under it.

    `check_against_replay` compares two documents; this compares the replay
    against the *geometry those documents imply*, which is the failure the
    documents cannot show. A contract can agree with a replay about where the
    bowl is and still describe a dish whose profile leaves the marbles a
    radius clear of it, and nothing before this point would notice.

    Deliberately a report and not an exception. Floating and penetration are
    matters of degree measured against a budget, and a render that trips the
    budget by a millimetre is still a render worth looking at - the caller
    prints what was found and carries on. What must never happen is finding
    out from the video.
    """
    return check_contact(replay, presentation.to_json())


def print_contact(report: ContactReport) -> None:
    """One line when the machine is sound, a short list when it is not."""
    if report.ok():
        print(
            f"    contact {report.samples} marble samples over "
            f"{report.frames_checked} frames, all on the drawn surface"
        )
        return
    counts = ", ".join(
        f"{kind} x{count}" for kind, count in sorted(report.by_kind().items())
    )
    print(f"    contact {len(report.findings)} findings: {counts}")
    print(
        f"      worst penetration {report.worst_penetration:.3f} wu,"
        f" worst clearance {report.worst_clearance:.3f} wu"
    )
    for finding in report.findings[:5]:
        print(
            f"      {finding.kind}: marble {finding.marble} in"
            f" {finding.module} at frame {finding.frame}"
            f" ({finding.time:.2f}s), {finding.value:.3f} wu"
        )


# --- shots ----------------------------------------------------------------


@dataclass(frozen=True)
class Shot:
    """One camera setup and the output frame it takes over on."""

    name: str
    start_frame: int

    def seconds(self, fps: int) -> float:
        return self.start_frame / fps


def _first_event_time(
    replay: dict[str, Any], kind: str, module: str | None = None
) -> float | None:
    """When something first happened, or None if it never did.

    The event list is written in simulated order as the run goes, so the first
    match is the earliest one and no sort is needed - or wanted, since a sort
    would quietly hide the day that stops being true.
    """
    for event in replay.get("events", []):
        if event.get("kind") != kind:
            continue
        if module is not None and event.get("module") != module:
            continue
        return float(event.get("t", 0.0))
    return None


def shot_cuts(replay: dict[str, Any], fps: int, frame_count: int) -> list[Shot]:
    """Where the clip cuts, taken from the run rather than from a stopwatch.

    `module_enter` is the only signal a replay carries for "a marble got
    there", and it is a soft one. The simulation decides which module a marble
    is in by AABB occupancy; the boxes overlap where two modules join, and the
    test carries hysteresis so a marble sitting on a boundary does not flicker
    between them. So the event says *roughly* when the bowl became the subject
    - which is all a cut needs, and it is treated as a hint throughout: leaded
    by `SHOT_LEAD_SECONDS`, held at least `MIN_SHOT_SECONDS` from its
    neighbours, never allowed before the marbles are released, and dropped
    entirely if the clip ends before there would be anything to watch.

    The release events set the floor rather than the opening cut, because the
    opening cut is not in question: something has to be on screen at frame 0.
    """
    release = _first_event_time(replay, "release")
    if release is None:
        raise IntegrationError(
            "the replay has no release event, so no marble ever left the chute;"
            " there is no run here to cut"
        )

    lead = int(round(SHOT_LEAD_SECONDS * fps))
    minimum = max(1, int(round(MIN_SHOT_SECONDS * fps)))
    shots = [Shot(SHOT_START, 0)]

    floor = int(round(release * fps)) + minimum
    for name in (SHOT_BOWL, SHOT_CURVE):
        arrival = _first_event_time(replay, "module_enter", SHOT_MODULES[name])
        if arrival is None:
            continue
        cut = max(floor, int(round(arrival * fps)) - lead)
        if cut > frame_count - minimum:
            continue
        shots.append(Shot(name, cut))
        floor = cut + minimum
    return shots


def parse_shots(text: str, frame_count: int) -> list[Shot]:
    """`--shots start:0,bowl:40,curve:300` as a cut list.

    Names are checked against the three the renderer knows. A typo would
    otherwise reach Godot as a shot nobody wrote, and the failure mode of that
    is a camera nowhere near the machine rather than an error.
    """
    shots: list[Shot] = []
    for piece in text.split(","):
        piece = piece.strip()
        if not piece:
            continue
        name, separator, value = piece.partition(":")
        name, value = name.strip(), value.strip()
        if not separator or not value.isdigit():
            raise IntegrationError(
                f"--shots wants name:frame pairs, got {piece!r}"
            )
        if name not in SHOT_NAMES:
            raise IntegrationError(
                f"--shots: unknown shot {name!r}; the renderer knows"
                f" {', '.join(SHOT_NAMES)}"
            )
        frame = int(value)
        if frame >= frame_count:
            raise IntegrationError(
                f"--shots: {name} starts at frame {frame}, past the end of a"
                f" {frame_count} frame clip"
            )
        if shots and frame <= shots[-1].start_frame:
            raise IntegrationError(
                f"--shots: {name} at {frame} does not come after"
                f" {shots[-1].name} at {shots[-1].start_frame}"
            )
        shots.append(Shot(name, frame))

    if not shots:
        raise IntegrationError("--shots is empty; a clip has to be shot on something")
    if shots[0].start_frame != 0:
        raise IntegrationError(
            f"--shots: the first shot starts at frame {shots[0].start_frame};"
            " frame 0 has to be on a camera"
        )
    return shots


def format_shots(shots: list[Shot]) -> str:
    """The cut list as Godot's `--shots` argument."""
    return ",".join(f"{shot.name}:{shot.start_frame}" for shot in shots)


# --- the plan -------------------------------------------------------------


@dataclass(frozen=True)
class IntegrationPlan:
    """Exactly which images this run produces, and what they are cut into."""

    name: str
    seed: int
    replay_path: str
    contract_path: str
    out_dir: str
    frames_dir: str
    video_path: str
    metadata_path: str
    width: int
    height: int
    fps: int
    start_frame: int
    frame_count: int
    replay_frames: int
    physics_hz: int
    replay_fps: int
    shots: tuple[Shot, ...]
    debug: bool
    no_glow: bool

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.fps

    @property
    def last_frame(self) -> int:
        return self.start_frame + self.frame_count - 1

    def frame_path(self, offset: int) -> str:
        """The file holding output frame `offset`, counted from the clip's start."""
        return os.path.join(self.frames_dir, frame_filename(self.start_frame + offset))


def plan_integration(
    replay: dict[str, Any],
    replay_path: str,
    contract_path: str,
    out_dir: str,
    name: str = DEFAULT_NAME,
    width: int = RENDER_WIDTH,
    height: int = RENDER_HEIGHT,
    fps: int = RENDER_FPS,
    duration: float | None = None,
    shots: str | None = None,
    start_frame: int = 0,
    debug: bool = False,
    no_glow: bool = False,
) -> IntegrationPlan:
    """Turn a replay and a set of choices into the clip they produce.

    Resampling is refused rather than implemented. The replay holds one pose
    per output frame at its own rate; asking for a different rate would mean
    interpolating poses, and an interpolated pose is a pose the solver never
    computed - which is exactly the thing this whole pipeline exists not to do.
    """
    replay_frames = len(replay.get("frames") or [])
    replay_fps = int(replay.get("replay_fps", fps))
    if replay_fps != fps:
        raise IntegrationError(
            f"the replay is sampled at {replay_fps} fps and the clip wants {fps};"
            " resampling is not something this renderer does"
        )

    frame_count = replay_frames
    if duration is not None:
        if duration <= 0.0:
            raise IntegrationError(f"--duration has to be positive, got {duration}")
        frame_count = min(replay_frames, int(round(duration * fps)))
    if frame_count < 1:
        raise IntegrationError("the clip works out at zero frames")

    cuts = (
        parse_shots(shots, frame_count)
        if shots
        else shot_cuts(replay, fps, frame_count)
    )

    return IntegrationPlan(
        name=name,
        seed=int(replay.get("seed", 0)),
        replay_path=replay_path,
        contract_path=contract_path,
        out_dir=out_dir,
        frames_dir=os.path.join(out_dir, FRAMES_SUBDIR),
        video_path=os.path.join(out_dir, f"{name}.mp4"),
        metadata_path=os.path.join(out_dir, f"{name}.metadata.json"),
        width=width,
        height=height,
        fps=fps,
        start_frame=start_frame,
        frame_count=frame_count,
        replay_frames=replay_frames,
        physics_hz=int(replay.get("physics_hz", 0)),
        replay_fps=replay_fps,
        shots=tuple(cuts),
        debug=debug,
        no_glow=no_glow,
    )


def print_plan(plan: IntegrationPlan, replay: dict[str, Any]) -> None:
    summary = replay.get("summary") or {}
    trimmed = (
        f", trimmed from {plan.replay_frames}"
        if plan.frame_count != plan.replay_frames
        else ""
    )
    print(
        f"\n=== {plan.name}  seed {plan.seed}  "
        f"{len(replay.get('marbles') or [])} marbles ===\n"
        f"    replay   {relative_replay_path(plan.replay_path, PROJECT_ROOT)}"
        f"  ({plan.replay_frames} frames @ {plan.replay_fps}fps,"
        f" {plan.physics_hz}Hz physics)\n"
        f"    contract {relative_replay_path(plan.contract_path, PROJECT_ROOT)}"
        f"  (v{CONTRACT_VERSION})\n"
        f"    clip     {plan.width}x{plan.height} @ {plan.fps}fps  "
        f"{plan.frame_count} frames ({plan.duration_seconds:.2f}s{trimmed})\n"
        f"    shots    "
        + "  ".join(
            f"{shot.name}:{shot.start_frame} ({shot.seconds(plan.fps):.2f}s)"
            for shot in plan.shots
        )
    )
    if summary.get("failure"):
        print(f"    RUN FAILURE: {summary['failure']}")


# --- rendering ------------------------------------------------------------


def prepare_frames_dir(plan: IntegrationPlan) -> str:
    """An empty frames directory, so a shorter clip cannot inherit a tail.

    Only the frames this driver writes are removed. Anything else in the
    directory is left where it is rather than deleted on the user's behalf.
    """
    os.makedirs(plan.frames_dir, exist_ok=True)
    for name in os.listdir(plan.frames_dir):
        if frame_index(name) is not None:
            os.remove(os.path.join(plan.frames_dir, name))
    return plan.frames_dir


def godot_command(godot: str, plan: IntegrationPlan) -> list[str]:
    """The exact command line the Godot side is written against.

    No `--headless` and no `--rendering-driver`, and their absence is
    load-bearing rather than an oversight: headless gives the process no
    rendering device, and a scene with no rendering device hands back a null
    image from `SubViewport.get_texture().get_image()`. The window that opens
    is the price of the pixels.
    """
    command = [
        godot,
        "--path",
        GODOT_PROJECT,
        RENDER_SCENE,
        "--",
        f"--replay={os.path.abspath(plan.replay_path)}",
        f"--contract={os.path.abspath(plan.contract_path)}",
        f"--out-dir={os.path.abspath(plan.frames_dir)}",
        f"--fps={plan.fps}",
        f"--width={plan.width}",
        f"--height={plan.height}",
        f"--frames={plan.frame_count}",
        f"--start-frame={plan.start_frame}",
        f"--shots={format_shots(list(plan.shots))}",
    ]
    if plan.debug:
        command.append("--debug=1")
    if plan.no_glow:
        command.append("--no-glow=1")
    return command


def run_godot(godot: str, plan: IntegrationPlan) -> float:
    """One Godot invocation. Returns wall seconds; raises on anything wrong.

    Stderr is captured and read afterwards, which the batch renderer does not
    bother with, because GDScript pushes parse and runtime errors to stderr
    *without failing the process* - so a zero exit is not on its own evidence
    that the scene built. Against a renderer still being written that is the
    difference between a clear error and two thousand pictures of empty sky.

    Stdout is deliberately *not* captured. It is where the scene reports the
    frames it has written, and a job of this length that prints nothing for
    minutes on end is indistinguishable from a job that has hung.
    """
    started = time.perf_counter()
    completed = subprocess.run(
        godot_command(godot, plan),
        cwd=PROJECT_ROOT,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.perf_counter() - started
    errors = "\n".join((completed.stderr or "").splitlines()[-25:])

    if completed.returncode != 0:
        raise IntegrationError(
            f"Godot exited {completed.returncode}; the render is incomplete"
            f"\n--- stderr ---\n{errors}"
        )
    for line in (completed.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise IntegrationError(f"Godot reported an error: {line.strip()}")
    if plan.debug and errors:
        print(f"    godot stderr:\n{errors}")
    return elapsed


def verify_sequence(plan: IntegrationPlan) -> list[str]:
    """Every planned frame, exactly once, at exactly the right size.

    Headers only: the whole sequence is checked, which two million pixels a
    frame would make far too slow, and the dimensions are the thing that has to
    be true of every single image.
    """
    # `sequence_problems` asks about a run numbered from zero and Godot numbers
    # from `--start-frame`, so the names are shifted rather than the checker
    # forked: one implementation of "is this sequence complete" in the project.
    #
    # Frames numbered below the start of the run are counted here rather than
    # handed over, because they are the one kind of leftover the shared checker
    # cannot see: shifted they would be negative, and unshifted they look like
    # perfectly ordinary members of the run.
    shifted: list[str] = []
    strays: list[str] = []
    early: list[str] = []
    for name in os.listdir(plan.frames_dir):
        index = frame_index(name)
        if index is None:
            strays.append(name)
        elif index < plan.start_frame:
            early.append(name)
        else:
            shifted.append(frame_filename(index - plan.start_frame))

    problems = sequence_problems(shifted + strays, plan.frame_count)
    if early:
        problems.append(
            f"{len(early)} frames before frame {plan.start_frame}, the start of the"
            f" run; first {sorted(early)[0]}"
        )
    if problems:
        return problems

    for offset in range(plan.frame_count):
        path = plan.frame_path(offset)
        header = png_frames.read_header(path)
        if header.width != plan.width or header.height != plan.height:
            problems.append(
                f"{os.path.basename(path)} is {header.width}x{header.height},"
                f" expected {plan.width}x{plan.height}"
            )
            break
        if header.color_type not in (
            png_frames.COLOR_TYPE_RGB,
            png_frames.COLOR_TYPE_RGBA,
        ):
            problems.append(
                f"{os.path.basename(path)} is {header.channels}, expected RGB or RGBA"
            )
            break
    return problems


def checkpoint_frames(plan: IntegrationPlan) -> dict[int, str]:
    """Which frames are decoded, and what each one is being asked to prove.

    Frame 0, the midpoint and the last frame answer "did anything move at all".
    The first frame of every shot answers "did every shot actually build",
    which matters more in this tool than anywhere else in the project: each
    shot is a different camera on a scene assembled out of a contract, and a
    cut to a camera that failed to place is a black rectangle in the middle of
    a clip that otherwise passes.
    """
    points: dict[int, str] = {}
    for shot in plan.shots:
        points.setdefault(shot.start_frame, f"shot {shot.name}")
    points.setdefault(0, "frame 0")
    points.setdefault(plan.frame_count // 2, "midpoint")
    points.setdefault(plan.frame_count - 1, "final frame")
    return points


def verify_content(plan: IntegrationPlan) -> list[str]:
    """A handful of frames decoded, to prove the sequence is a clip.

    Not image quality - just that something was drawn, that the run moved, and
    that the ending is not the middle.
    """
    problems: list[str] = []
    samples: dict[int, png_frames.FrameSample] = {}
    for offset, label in sorted(checkpoint_frames(plan).items()):
        path = plan.frame_path(offset)
        frame = png_frames.sample(path)
        samples[offset] = frame
        if frame.is_black:
            problems.append(f"{label} ({os.path.basename(path)}) is completely black")
        elif frame.is_blank:
            problems.append(f"{label} ({os.path.basename(path)}) is a flat colour")

    # Three distinct frames are needed before "the clip moves" is a question
    # that can be asked at all.
    if plan.frame_count >= 3:
        middle = plan.frame_count // 2
        if samples[0].digest == samples[middle].digest:
            problems.append("frame 0 and the midpoint frame are the same image")
        if samples[plan.frame_count - 1].digest == samples[middle].digest:
            problems.append("the final frame and the midpoint frame are the same image")
    return problems


def frames_bytes(plan: IntegrationPlan) -> int:
    return sum(
        os.path.getsize(plan.frame_path(offset)) for offset in range(plan.frame_count)
    )


def discard_frames(plan: IntegrationPlan) -> None:
    """Drop the PNGs once they are inside the mp4, and only those.

    A 1080x1920 sequence is a gigabyte of intermediates per clip. The directory
    is left in place if anything else is in it, on the same principle as
    `prepare_frames_dir`: this tool tidies up after itself and after nobody
    else.
    """
    for offset in range(plan.frame_count):
        path = plan.frame_path(offset)
        if os.path.isfile(path):
            os.remove(path)
    if os.path.isdir(plan.frames_dir) and not os.listdir(plan.frames_dir):
        os.rmdir(plan.frames_dir)


# --- encoding and stills --------------------------------------------------


def encode_video(plan: IntegrationPlan) -> str:
    """The PNG sequence as one mp4. No audio, and none of it generated here.

    `-frames:v` is belt and braces over an already-emptied directory: ffmpeg
    would otherwise happily encode a longer tail than the plan describes, and
    the metadata beside the file would then be a lie about its length.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise IntegrationError(
            "ffmpeg is not on PATH; the frames are rendered but not encoded"
        )
    os.makedirs(os.path.dirname(os.path.abspath(plan.video_path)), exist_ok=True)
    command = [
        ffmpeg,
        "-y",
        "-framerate",
        str(plan.fps),
        "-start_number",
        str(plan.start_frame),
        "-i",
        os.path.join(plan.frames_dir, FRAME_PATTERN),
        "-frames:v",
        str(plan.frame_count),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        VIDEO_PRESET,
        "-crf",
        str(VIDEO_CRF),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        plan.video_path,
    ]
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if completed.returncode != 0:
        tail = "\n".join((completed.stderr or "").splitlines()[-15:])
        raise IntegrationError(f"ffmpeg exited {completed.returncode}\n{tail}")
    return plan.video_path


def parse_stills(text: str, frame_count: int) -> dict[str, int]:
    """`--stills hero=120,drain=354` as names against clip frames.

    Frames are numbered from the start of the *clip*, not from the start of the
    replay, because that is the numbering every other line this tool prints
    uses - including the cut list a still is usually chosen off.
    """
    stills: dict[str, int] = {}
    for piece in text.split(","):
        piece = piece.strip()
        if not piece:
            continue
        name, separator, value = piece.partition("=")
        name, value = name.strip(), value.strip()
        if not separator or not value.isdigit() or not name:
            raise IntegrationError(f"--stills wants name=frame pairs, got {piece!r}")
        frame = int(value)
        if frame >= frame_count:
            raise IntegrationError(
                f"--stills: {name} asks for frame {frame} of a {frame_count} frame clip"
            )
        stills[name] = frame
    return stills


def write_stills(
    plan: IntegrationPlan, stills: dict[str, int], stills_dir: str | None = None
) -> list[str]:
    """Copy named frames out beside the video, so a still needs no re-render.

    `stills_dir` sends them somewhere else - `docs/validation/marble_v1` for
    the ones the brief asks to be committed. Worth an argument rather than a
    `cp` afterwards: a still that is produced by the same command that produced
    the video cannot be a still of a different render.
    """
    written = []
    target = os.path.abspath(stills_dir) if stills_dir else plan.out_dir
    if stills:
        os.makedirs(target, exist_ok=True)
    for name, offset in stills.items():
        destination = os.path.join(target, f"{name}.png")
        shutil.copyfile(plan.frame_path(offset), destination)
        written.append(destination)
    return written


# --- the sidecar ----------------------------------------------------------


def metadata(
    plan: IntegrationPlan,
    replay: dict[str, Any],
    version: str,
    replay_sha256: str,
    contract_sha256: str,
) -> dict[str, Any]:
    """What this clip is, written down beside it.

    Everything here except the engine string is derived from the replay and the
    plan, so two runs of the same seed produce the same sidecar. The engine
    string is a fact about the machine that drew it and is recorded anyway,
    because a frame is only reproducible against the renderer that made it.
    """
    summary = replay.get("summary") or {}
    return {
        "tool": "marble3d_integrate",
        "name": plan.name,
        "seed": plan.seed,
        "engine": version,
        "replay": {
            "path": relative_replay_path(plan.replay_path, PROJECT_ROOT),
            "sha256": replay_sha256,
            "digest": replay.get("digest", ""),
            "event_digest": replay.get("event_digest", ""),
            "physics_hz": plan.physics_hz,
            "replay_fps": plan.replay_fps,
            "frames": plan.replay_frames,
            "marbles": len(replay.get("marbles") or []),
        },
        "contract": {
            "path": relative_replay_path(plan.contract_path, PROJECT_ROOT),
            "sha256": contract_sha256,
            "version": CONTRACT_VERSION,
        },
        "video": {
            "path": relative_replay_path(plan.video_path, PROJECT_ROOT),
            "width": plan.width,
            "height": plan.height,
            "fps": plan.fps,
            "frame_count": plan.frame_count,
            "start_frame": plan.start_frame,
            "duration_seconds": round(plan.duration_seconds, 3),
        },
        "shots": [
            {
                "name": shot.name,
                "start_frame": shot.start_frame,
                "start_seconds": round(shot.seconds(plan.fps), 3),
            }
            for shot in plan.shots
        ],
        "run": {
            "finish_order": summary.get("finish_order", []),
            "failure": summary.get("failure"),
        },
    }


def write_metadata(
    plan: IntegrationPlan,
    replay: dict[str, Any],
    version: str,
    replay_sha256: str,
    contract_sha256: str,
) -> str:
    payload = metadata(plan, replay, version, replay_sha256, contract_sha256)
    with open(plan.metadata_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return plan.metadata_path


# --- one clip -------------------------------------------------------------


def integrate(
    godot: str,
    plan: IntegrationPlan,
    replay: dict[str, Any],
    stills: dict[str, int] | None = None,
    keep_frames: bool = False,
    stills_dir: str | None = None,
) -> str:
    """Render, check, encode, describe - and refuse to accept anything less.

    Nothing is reported as finished until the sequence has been counted, its
    frames measured, a few of them decoded, and both inputs confirmed
    untouched. A run that falls short raises rather than leaving an mp4 with a
    sidecar describing images that were never checked.
    """
    version = godot_version(godot)

    # Hashed before and after: rendering reads the replay and the contract and
    # must never write to either, and the only way to say that with confidence
    # is to check.
    replay_sha256 = png_frames.file_digest(plan.replay_path)
    contract_sha256 = png_frames.file_digest(plan.contract_path)

    prepare_frames_dir(plan)
    elapsed = run_godot(godot, plan)

    problems = verify_sequence(plan) or verify_content(plan)
    if problems:
        raise IntegrationError("; ".join(problems))

    if png_frames.file_digest(plan.replay_path) != replay_sha256:
        raise IntegrationError(
            f"the replay changed during rendering: {plan.replay_path}"
        )
    if png_frames.file_digest(plan.contract_path) != contract_sha256:
        raise IntegrationError(
            f"the contract changed during rendering: {plan.contract_path}"
        )

    total = frames_bytes(plan)
    encode_video(plan)
    written = write_stills(plan, stills or {}, stills_dir)
    write_metadata(plan, replay, version, replay_sha256, contract_sha256)

    print(
        f"    rendered in {elapsed:.1f}s"
        f"  ({plan.frame_count / max(elapsed, 1e-6):.1f} frames/sec,"
        f" {1000.0 * elapsed / plan.frame_count:.1f} ms/frame)\n"
        f"    {total / MIB:.1f} MiB of PNG"
        f"  ({total / plan.frame_count / 1024:.0f} KiB/frame)\n"
        f"    video    {relative_replay_path(plan.video_path, PROJECT_ROOT)}"
        f"  ({os.path.getsize(plan.video_path) / MIB:.1f} MiB,"
        f" {plan.duration_seconds:.2f}s)"
    )
    for path in written:
        print(f"    still    {relative_replay_path(path, PROJECT_ROOT)}")
    print(f"    metadata {relative_replay_path(plan.metadata_path, PROJECT_ROOT)}")

    if not keep_frames:
        discard_frames(plan)
    else:
        print(f"    frames   {relative_replay_path(plan.frames_dir, PROJECT_ROOT)}")
    return plan.video_path


# --- command line ---------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="simulate a marble machine seed and render it to a finished mp4"
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--marbles",
        type=int,
        default=DEFAULT_MARBLES,
        help="no more than the chute holds",
    )
    parser.add_argument(
        "--replay", default=None, help="render this replay instead of simulating a seed"
    )
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--stills-dir",
        default=None,
        help="write --stills here instead of beside the video",
    )
    parser.add_argument("--name", default=DEFAULT_NAME, help="stem for the clip's files")
    parser.add_argument("--width", type=int, default=RENDER_WIDTH)
    parser.add_argument("--height", type=int, default=RENDER_HEIGHT)
    parser.add_argument("--fps", type=int, default=RENDER_FPS)
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="clip length in seconds (default: the whole replay)",
    )
    parser.add_argument(
        "--shots",
        default=None,
        help="override the cuts, as name:frame,... (default: taken from the events)",
    )
    parser.add_argument(
        "--stills",
        default=None,
        help="also write named stills, as name=frame,... counted from the clip's start",
    )
    parser.add_argument("--godot", default=None, help="path to the Godot 4 executable")
    parser.add_argument(
        "--debug", action="store_true", help="ask the scene for its debug overlay"
    )
    parser.add_argument(
        "--no-glow", action="store_true", help="render the control, without bloom"
    )
    parser.add_argument(
        "--keep-frames", action="store_true", help="leave the PNG sequence behind"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "simulate, write the contract and print the plan, then stop before Godot."
            " The two halves of this integration are built in parallel, so producing"
            " and checking a contract must not require a scene that can draw it."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        out_dir = os.path.abspath(args.out_dir)
        os.makedirs(out_dir, exist_ok=True)

        if args.replay:
            replay_path = os.path.abspath(args.replay)
            replay = load_replay(replay_path)
        else:
            replay_path = default_replay_path(out_dir, args.name)
            replay = simulate_replay(args.seed, args.marbles, replay_path)

        contract_path = contract_path_for(replay_path)
        presentation = build_contract(replay)
        write_contract(presentation, replay, contract_path)

        plan = plan_integration(
            replay,
            replay_path=replay_path,
            contract_path=contract_path,
            out_dir=out_dir,
            name=args.name,
            width=args.width,
            height=args.height,
            fps=args.fps,
            duration=args.duration,
            shots=args.shots,
            debug=args.debug,
            no_glow=args.no_glow,
        )
        stills = parse_stills(args.stills, plan.frame_count) if args.stills else {}

        print_plan(plan, replay)
        # Before Godot, and on a dry run too: this is the check that says the
        # marbles will be touching what gets drawn, and it needs no renderer.
        print_contact(check_marble_contact(replay, presentation))
        if args.dry_run:
            print(
                "    dry run: the contract is written and checked,"
                " Godot was not called"
            )
            return 0

        godot = find_godot(args.godot)
        print(f"    godot    {godot}")
        integrate(godot, plan, replay, stills, args.keep_frames, args.stills_dir)
    except (IntegrationError, png_frames.PngError, OSError, ValueError) as error:
        print(f"marble3d_integrate: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
