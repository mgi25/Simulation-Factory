"""Draw a replay. A neutral debug video, and nothing that looks like art.

    python -m tools.marble3d_video --replay output/marble3d/replays/marble3d_seed00007.json

Section 31 of the brief asks for simple debug visualisation and section 32 says
not to go near the production Godot scenes, so this is PyBullet's own software
renderer, flat colours, one light, and ffmpeg. It exists to answer "does the
marble actually orbit, actually collide, actually drain, actually take the
curve" - not to look like anything.

## It renders the replay, not a simulation

The single most important line in this file is that there is no
`stepSimulation` call in it. Every marble pose comes out of the replay file;
the physics client is a rasteriser holding bodies with no mass that are
teleported to recorded transforms. That is section 26 of the brief made
executable: once a seed is chosen the replay is the authority, the renderer
never re-simulates, and cross-machine determinism stops being on the critical
path for shipping a video.

The static geometry is rebuilt from the module classes, because geometry is a
pure function of a spec and no physics is involved in producing it. To make
sure that stays true, the tool compares every rebuilt module's transform
against the transform recorded in the replay and refuses to draw if they
differ - so a change to a default spec makes this fail loudly instead of
quietly drawing the wrong machine under the right marbles.
"""

from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile

from marble3d.machines import start_bowl_curve
from marble3d.mesh import cached_obj
from marble3d.replay import STATE_FINISHED, Replay, read_replay

# Eight flat, well-separated hues plus a neutral for anything beyond them.
COLOURS = [
    (0.93, 0.28, 0.28, 1.0),
    (0.25, 0.61, 0.97, 1.0),
    (0.38, 0.84, 0.50, 1.0),
    (0.96, 0.77, 0.25, 1.0),
    (0.75, 0.45, 0.95, 1.0),
    (0.98, 0.55, 0.25, 1.0),
    (0.35, 0.87, 0.87, 1.0),
    (0.95, 0.45, 0.70, 1.0),
]
# One neutral tone per module, distinct enough to tell the three pieces apart
# in a still. Debug legibility, not art direction: the point of the video is to
# be able to say "that marble is in the curve" without counting pixels.
STRUCTURE = {
    "start": (0.58, 0.60, 0.66, 1.0),
    "bowl": (0.74, 0.75, 0.78, 1.0),
    "curve": (0.45, 0.52, 0.62, 1.0),
}
DEFAULT_STRUCTURE = (0.62, 0.64, 0.68, 1.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--replay", required=True)
    parser.add_argument("--out", default=os.path.join("output", "marble3d_core", "start_bowl_curve.mp4"))
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--fps", type=int, default=None, help="defaults to the replay rate")
    parser.add_argument("--orbit", type=float, default=50.0, help="degrees of camera yaw over the run")
    parser.add_argument("--yaw", type=float, default=35.0)
    parser.add_argument("--pitch", type=float, default=-34.0)
    parser.add_argument("--distance", type=float, default=None)
    parser.add_argument("--keep-frames", action="store_true")
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    return parser


def _double_sided(mesh):
    """The same triangles plus their mirrors, for the renderer only.

    A collider is a one-sided surface and Bullet is happy to collide with
    either face of it, but a rasteriser is not: half the bowl disappears when
    the camera swings round to the side its triangles face away from. Adding
    the reversed winding costs a visual shape twice the triangles and nothing
    else, and it is done here rather than in `marble3d.mesh` because a
    *collider* with both windings would fail the winding check in
    `marble3d.validation` - correctly, since a physics mesh with doubled
    triangles is a physics mesh with doubled contacts.
    """
    from marble3d.mesh import TriMesh

    indices = list(mesh.indices)
    for base in range(0, len(mesh.indices), 3):
        a, b, c = mesh.indices[base : base + 3]
        indices.extend((a, c, b))
    return TriMesh(mesh.vertices, indices, mesh.name + "_2s")


def _check_machine(replay: Replay, machine) -> None:
    recorded = {module["id"]: module["transform"] for module in replay.machine["modules"]}
    for module in machine:
        if module.id not in recorded:
            raise SystemExit(
                f"the replay has no module {module.id!r}; it was made by a different machine"
            )
        want = recorded[module.id]
        offset = math.dist(module.transform.position, want["position"])
        if offset > 1e-6:
            raise SystemExit(
                f"module {module.id!r} rebuilds at {module.transform.position} but the replay "
                f"records {tuple(want['position'])}. A default spec has changed since this "
                "replay was written, so the picture would not be of the machine that ran."
            )


def render(args: argparse.Namespace) -> int:
    import pybullet

    replay = read_replay(args.replay)
    machine = start_bowl_curve()
    _check_machine(replay, machine)

    # Frame the bowl and the curve, not the machine's bounding box. The start
    # chute is twenty units of ramp that nothing interesting happens on after
    # the first second, and letting it set the framing pushes the two modules
    # worth watching into a third of the picture.
    bowl = machine.modules["bowl"].bounds()
    curve = machine.modules["curve"].bounds()
    subject = bowl.merged(curve)
    centre = [0.5 * (lo + hi) for lo, hi in zip(subject.lower, subject.upper)]
    span = max(hi - lo for lo, hi in zip(subject.lower, subject.upper))
    distance = args.distance or span * 1.35

    client = pybullet.connect(pybullet.DIRECT)
    pybullet.setGravity(0.0, 0.0, 0.0, physicsClientId=client)
    cache = os.path.join("output", "marble3d", "meshes")

    for module in machine:
        colour = STRUCTURE.get(module.id, DEFAULT_STRUCTURE)
        for mesh in module.local_colliders():
            placed = _double_sided(mesh.transformed(module.transform, mesh.name))
            for chunk in placed.chunks(6000, 24000):
                shape = pybullet.createVisualShape(
                    pybullet.GEOM_MESH,
                    fileName=cached_obj(chunk, cache),
                    rgbaColor=colour,
                    physicsClientId=client,
                )
                pybullet.createMultiBody(
                    baseMass=0.0, baseVisualShapeIndex=shape, physicsClientId=client
                )

    marble_bodies: dict[int, int] = {}
    for info in replay.marbles:
        shape = pybullet.createVisualShape(
            pybullet.GEOM_SPHERE,
            radius=info.radius,
            rgbaColor=COLOURS[info.marble_id % len(COLOURS)],
            physicsClientId=client,
        )
        marble_bodies[info.marble_id] = pybullet.createMultiBody(
            baseMass=0.0, baseVisualShapeIndex=shape, physicsClientId=client
        )

    actuator_bodies: dict[str, int] = {}
    for module in machine:
        for actuator in module.local_actuators():
            shape = pybullet.createVisualShape(
                pybullet.GEOM_BOX,
                halfExtents=list(actuator.half_extents),
                rgbaColor=(0.85, 0.35, 0.20, 1.0),
                physicsClientId=client,
            )
            actuator_bodies[f"{module.id}.{actuator.name}"] = pybullet.createMultiBody(
                baseMass=0.0, baseVisualShapeIndex=shape, physicsClientId=client
            )

    projection = pybullet.computeProjectionMatrixFOV(
        fov=42.0, aspect=args.width / args.height, nearVal=0.5, farVal=distance * 4.0
    )

    frames_directory = tempfile.mkdtemp(prefix="marble3d_frames_")
    total = len(replay.frames)
    try:
        for index, frame in enumerate(replay.frames):
            for sample in frame.marbles:
                body = marble_bodies.get(sample.marble_id)
                if body is None:
                    continue
                if sample.state == STATE_FINISHED:
                    # Park a finished marble far away rather than leaving it
                    # frozen at the finish line pretending to still be racing.
                    pybullet.resetBasePositionAndOrientation(
                        body, [0.0, -1e4, 0.0], [0.0, 0.0, 0.0, 1.0], physicsClientId=client
                    )
                    continue
                pybullet.resetBasePositionAndOrientation(
                    body, list(sample.position), list(sample.orientation), physicsClientId=client
                )
            for name, pose in frame.actuators.items():
                body = actuator_bodies.get(name)
                if body is not None:
                    pybullet.resetBasePositionAndOrientation(
                        body, list(pose[0]), list(pose[1]), physicsClientId=client
                    )

            yaw = args.yaw + args.orbit * index / max(total - 1, 1)
            view = pybullet.computeViewMatrixFromYawPitchRoll(
                cameraTargetPosition=centre,
                distance=distance,
                yaw=yaw,
                pitch=args.pitch,
                roll=0.0,
                upAxisIndex=1,
                physicsClientId=client,
            )
            image = pybullet.getCameraImage(
                args.width,
                args.height,
                viewMatrix=view,
                projectionMatrix=projection,
                lightDirection=[0.4, 1.0, 0.5],
                shadow=0,
                renderer=pybullet.ER_TINY_RENDERER,
                physicsClientId=client,
            )
            _write_png(
                os.path.join(frames_directory, f"frame_{index:05d}.png"),
                args.width,
                args.height,
                image[2],
            )
            if index % 60 == 0:
                print(f"  {index}/{total} frames", flush=True)

        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        fps = args.fps or replay.replay_fps
        command = [
            args.ffmpeg, "-y", "-framerate", str(fps),
            "-i", os.path.join(frames_directory, "frame_%05d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
            args.out,
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode:
            print(completed.stderr[-3000:], file=sys.stderr)
            return completed.returncode
        size = os.path.getsize(args.out)
        print(f"{total} frames at {fps} fps -> {args.out} ({size / 1e6:.1f} MB)")
    finally:
        pybullet.disconnect(physicsClientId=client)
        if not args.keep_frames:
            shutil.rmtree(frames_directory, ignore_errors=True)
        else:
            print(f"frames kept in {frames_directory}")
    return 0


def _write_png(path: str, width: int, height: int, pixels) -> None:
    """A minimal RGBA PNG writer, so the tool needs no imaging dependency.

    PyBullet hands back a flat RGBA buffer. Writing it out is thirty lines of
    zlib and struct, which is cheaper than making the physics core depend on an
    image library for one debug video.
    """
    import struct
    import zlib

    raw = bytearray()
    stride = width * 4
    data = bytes(bytearray(pixels)) if not isinstance(pixels, (bytes, bytearray)) else bytes(pixels)
    for row in range(height):
        raw.append(0)                       # filter type 0, none
        raw.extend(data[row * stride : (row + 1) * stride])

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(chunk(b"IHDR", header))
        handle.write(chunk(b"IDAT", zlib.compress(bytes(raw), 6)))
        handle.write(chunk(b"IEND", b""))


def main(argv: list[str] | None = None) -> int:
    return render(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
